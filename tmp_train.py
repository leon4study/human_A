# train.py 는 1분단위의 데이터를 학습시켜야 성능이 우수함.
#
# 🎯 원본(train - 원본.py) 구조를 최대한 보존.
# 추가한 것은 세 가지뿐:
#   (1) Optuna 하이퍼파라미터 탐색 (train_and_save_model 맨 앞 블록)
#   (2) 학습/holdout 분리 (df_raw 슬라이싱 한 줄)
#   (3) 4~5월 이벤트 탐지 평가 + CSV 저장 (메인 루프 마지막 블록)
#
# 원본과 달라진 부분은 [+추가] 로 표시해두었음.

import os
import gc
import csv
import json
import time
import numpy as np
import pandas as pd
import tensorflow as tf
import optuna
from tensorflow.keras.callbacks import EarlyStopping
from sklearn.preprocessing import MinMaxScaler

from feature_selection import run_feature_selection_experiment
from preprocessing import (
    step1_prepare_window_data,
    step2_clean_and_drop_collinear,
)  # [+추가] eval 전처리용
from logger import (
    get_logger,
    save_experiment_to_csv,
    save_optuna_trial_to_csv,  # [+추가]
    save_optuna_best_to_json,  # [+추가]
)
from math_utils import calculate_mad_thresholds
from model_builder import build_autoencoder
from utils import save_model_artifacts

logger = get_logger("TRAIN")


# ==============================================================================
# [+추가] 전역 설정 (전부 여기서만 조절)
# ==============================================================================
# 🔄 (2026-04-19 업데이트) 학습 전략 재검토 — 3가지 동시 적용
#   1) TRAIN_RANGE 확장: 15일 → 31일 (3월 전체)
#   2) 별도 HOLDOUT_RANGE 폐지 → 학습 구간 내 80/20 랜덤 홀드아웃 (단일 split)
#   3) MAD 기반 Robust 임계값 + top_sigma/step = (9,3) 로 Caution=Mean 버그 수정
#   4) Self-cleaning 2-pass 학습 (학습 구간 내 상위 5% 재구성오차 제거 후 재학습)
TRAIN_RANGE = ("2026-03-01", "2026-03-25")  # 30일
EVAL_RANGE = ("2026-04-01 00:00:00", "2026-05-31 23:59:59")  # 이벤트 평가
HOLDOUT_FRACTION = 0.2  # 학습 구간 내 랜덤 홀드아웃 비율
HOLDOUT_RANDOM_SEED = 42  # 재현성
SELF_CLEAN_DROP_FRACTION = 0.0  # 1차 학습 후 제거할 상위 MSE 비율
# 🔄 2026-04-20 (재검토): 0.02 → 0.0 으로 self-cleaning 완전 비활성화.
#    이유: 매일 06:00 펌프 기동 전이가 "상위 MSE" 로 분류되어 학습 풀에서 제거됨 →
#    AE 가 정상 기동 패턴을 학습하지 못함 → 배포 후 06:00 크리티컬 오탐.
#    "정상 범위 내에서만 학습" 하려면 전이 구간도 정상에 포함시켜야 함.
#    (진짜 고장은 4~5월 평가 구간에만 있으므로, 3월 학습 구간은 전체가 정상)
THRESHOLD_TOP_SIGMA = 12  # μ + 12σ = Critical (FAR 하향 튜닝, 2026-04-19)
THRESHOLD_STEP = 3  # Caution = μ + 6σ
# 🆕 2026-04-21 v3: Hard Ceiling 마진 — max(training MSE) * (1 + ε) 초과 시
#    단발이라도 즉시 Critical. 모터 열화("기존 최대 압력 초과") 신호 포착용.
#    ε=0.10 은 "학습 데이터 내 자연 스파이크 + 10% 여유" → 정상 기동은 통과,
#    기존 패턴보다 10% 이상 세면 즉시 알람. 낮추면 민감(FP↑), 높이면 둔감(miss↑).
HARD_CEILING_EPSILON = 0.25
# ⚠️ 참고: 이 값은 train.py 재학습 시의 초기 임계값일 뿐.
#    실제 배포 임계값은 도메인별로 다름. 2026-04-20 튜닝 결과:
#      motor(12,3) / hydraulic(24,3) / nutrient(12,3)
#    도메인별 수정은 [src/recompute_thresholds.py](recompute_thresholds.py) 의
#    DOMAIN_THRESHOLD_SETTINGS 에서 관리하며, 재학습 없이 threshold 만 갱신 가능.
DOMAINS_TO_TRAIN = None  # 전 도메인 학습 모드
# 🆕 2026-04-20: "zone_drip" 4번째 도메인 추가 → 전체 4개 동시 학습 모드.
#    각 도메인 winner 는 DOMAIN_BEST_PARAMS 에 등록돼 있어 Optuna 를 건너뛰고 바로 2-pass.
#    전 도메인 2026-04-20 Optuna 탐색 완료 → DOMAIN_BEST_PARAMS 4개 모두 등록됨.

# 🧷 도메인별 사전 채택 best_params. 엔트리가 있으면 Optuna 를 건너뛰고 바로 2-pass 학습.
#    엔트리가 없거나 None 이면 해당 도메인만 Optuna 실행.
# 🔄 2026-04-22: 사용자 확정 Optuna winner 4종 등록 — F1 회복 재학습용 고정 HP.
#    (dropout 하한 0.1 강제 규칙은 Optuna 재탐색 시에만 적용 — preset 은 있는 그대로 사용)
DOMAIN_BEST_PARAMS = {
    # motor Winner (2026-04-20, Optuna 채택)
    "motor": {
        "hidden_1": 32,
        "hidden_2": 32,
        "bottleneck_size": 7,
        "dropout_rate": 0.1,
        "activation": "relu",
        "output_activation": "linear",
        "learning_rate": 0.004655619515979071,
        "batch_size": 128,
    },
    # hydraulic Winner (2026-04-20, Trial 14, obj=0.02152, FAR=1.01%, hit=5/5)
    "hydraulic": {
        "hidden_1": 16,
        "hidden_2": 32,
        "bottleneck_size": 6,
        "dropout_rate": 0.1,
        "activation": "elu",
        "output_activation": "linear",
        "learning_rate": 0.001601781368893847,
        "batch_size": 32,
    },
    # nutrient Winner (2026-04-20, Trial 18, obj=0.00337, FAR=0.08%, hit=5/5)
    "nutrient": {
        "hidden_1": 64,
        "hidden_2": 8,
        "bottleneck_size": 5,
        "dropout_rate": 0.0,
        "activation": "elu",
        "output_activation": "linear",
        "learning_rate": 0.0014276806900194404,
        "batch_size": 32,
    },
    # zone_drip Winner (2026-04-20, Trial 13, obj=0.00827, FAR=0.22%, hit=5/5)
    "zone_drip": {
        "hidden_1": 32,
        "hidden_2": 8,
        "bottleneck_size": 5,
        "dropout_rate": 0.2,
        "activation": "elu",
        "output_activation": "linear",
        "learning_rate": 0.004890355306372737,
        "batch_size": 32,
    },
}

LABELED_EVENTS = [
    ("2026-04-01 00:00:00", "2026-04-07 23:59:59"),
    ("2026-04-14 00:00:00", "2026-04-20 23:59:59"),
    ("2026-04-25 00:00:00", "2026-05-05 23:59:59"),
    ("2026-05-10 00:00:00", "2026-05-20 23:59:59"),
    ("2026-05-21 00:00:00", "2026-05-29 23:59:59"),
]
DETECTION_WINDOW_HOURS = 48  # 이벤트 시작 후 48h 내 울려야 hit
SIGMA_LEVELS = (2, 3, 6)  # 🔒 원본 값 유지 (레거시, 미사용)
FAR_PENALTY_WEIGHT = 2.0  # Optuna objective 의 FAR 가중치
N_TRIALS = 20

# 🔄 Optuna trial 전용 학습 설정 (최종 2-pass 학습은 그대로 epochs=100/patience=10 유지)
#    restore_best_weights=True 덕분에 patience 짧아도 best 가중치는 보존됨.
OPTUNA_EPOCHS = 50  # 100 → 50 (trial 당 ~1.5x 단축)
OPTUNA_PATIENCE = 5  # 10 → 5  (수렴 빠른 trial 조기 종료)


# ==============================================================================
# [+추가] 헬퍼 — 전부 stateless 함수. 원본 흐름 영향 X
# ==============================================================================
def _mask(df, start, end):
    return (df.index >= pd.to_datetime(start)) & (df.index <= pd.to_datetime(end))


def preprocess_for_eval(
    df_raw_slice, final_features, train_means, window_method="sliding"
):
    """임의 구간 raw → 같은 전처리 → 학습 피처 순서로 정렬"""
    df_agg, _ = step1_prepare_window_data(df_raw_slice, window_method=window_method)
    df_clean = step2_clean_and_drop_collinear(df_agg)
    X = pd.DataFrame(index=df_clean.index)
    for col in final_features:
        if col in df_clean.columns:
            X[col] = df_clean[col]
        else:
            X[col] = train_means.get(col, 0.0)  # 누락은 학습 평균으로 (0 대체는 이상값)
    return X[final_features].copy()


def score_mse_with_rca(ae, scaler, X):
    """MSE + RCA Top3 를 벡터화해서 한 번에 계산"""
    X_scaled = scaler.transform(X)
    recon = ae.predict(X_scaled, verbose=0)
    fe = np.power(X_scaled - recon, 2)
    mse = fe.mean(axis=1)

    sum_err = fe.sum(axis=1, keepdims=True)
    sum_err = np.where(sum_err <= 0, 1e-10, sum_err)
    contrib = fe / sum_err * 100.0
    top3_idx = np.argsort(-contrib, axis=1)[:, :3]
    names_arr = np.array(X.columns)
    top_feat = names_arr[top3_idx]
    top_contrib = np.take_along_axis(contrib, top3_idx, axis=1)
    return mse, top_feat, top_contrib


def compute_holdout_far(mse_holdout, thr):
    """정상 holdout 에서 Caution 이상 울린 비율 = 순수 false alarm rate"""
    if len(mse_holdout) == 0:
        return 0.0
    return float((mse_holdout >= thr["caution"]).sum()) / len(mse_holdout)


def evaluate_events(
    X_eval,
    mse,
    top_feat,
    top_contrib,
    thr,
    events,
    holdout_far,
    persistence_window=30,
    persistence_min_count=10,
    hourly_thresholds=None,
    hard_ceiling=None,
):
    """이벤트 탐지 평가. 탐지 윈도우는 48h로 제한해 delay 지표 의미 있게 유지.

    🔄 2026-04-20: 지속성 하이브리드 판정 도입 (inference_api 와 일관).
       - Warning/Critical 은 단발이어도 즉시 알람
       - Caution 은 최근 window 중 min_count 이상 초과해야 알람 (단발 스파이크 무시)
    🔄 2026-04-22 v2: window=5(5분)/min_count=2 → window=30(30분)/min_count=10.
       WHY: 1분 cadence eval 에서 5-샘플 창은 5분에 불과 → FP 억제력 거의 없음.
            옛 F1 0.95+ 수치를 내던 시점의 persistence 가 더 길었을 가능성 큼.
            30/10 = "30분 창 중 10분 이상 Caution 초과" 요구 → 단발/짧은 스파이크
            FP 대폭 억제, 진짜 드리프트 (시간 단위) 는 여전히 빠르게 포착.
    🔄 2026-04-20: 시간대별(hourly) 임계값 지원.
       - hourly_thresholds 가 주어지면 각 샘플의 hour 에 맞는 임계값 사용
       - 없으면 thr (전역 임계값) 사용
    🆕 2026-04-21 v4: hard_ceiling 인자 추가 — 추론 로직(inference_core)과 일관.
       - mse >= hard_ceiling → persistence 무시, 단발이라도 즉시 Critical.
       - 이전 버전은 학습 검증 경로에 ceiling 미적용 → 검증 hit_rate/FAR 가
         실제 배포 추론 결과와 불일치하던 버그 해소.
    """
    df = pd.DataFrame(index=X_eval.index)
    df["current_mse"] = mse

    # 시간대별 또는 전역 임계값 배열 생성
    if hourly_thresholds is not None:
        hours = X_eval.index.hour.values
        caut_arr = np.array([hourly_thresholds[str(int(h))]["caution"] for h in hours])
        warn_arr = np.array([hourly_thresholds[str(int(h))]["warning"] for h in hours])
        crit_arr = np.array([hourly_thresholds[str(int(h))]["critical"] for h in hours])
    else:
        caut_arr = np.full(len(mse), thr["caution"])
        warn_arr = np.full(len(mse), thr["warning"])
        crit_arr = np.full(len(mse), thr["critical"])

    # 순간값 기준 "raw" 레벨 (참고용 — 디버깅에 유용)
    raw_level = np.zeros(len(mse), dtype=int)
    raw_level[mse >= caut_arr] = 1
    raw_level[mse >= warn_arr] = 2
    raw_level[mse >= crit_arr] = 3

    # 🆕 Hard Ceiling: 학습 범위(99.9p*1.1) 를 넘는 단발은 즉시 Critical 후보로.
    #    raw_level 에 반영 (evaluate_events 의 critical 은 원래 persistence 무시 = 즉시).
    if hard_ceiling is not None:
        hc_mask = mse >= hard_ceiling
        raw_level[hc_mask] = 3

    # 지속성 판정 — Warning/Critical 은 즉시, Caution 은 rolling count 로.
    caution_mask = (mse >= caut_arr).astype(int)
    caution_rolling = (
        pd.Series(caution_mask, index=X_eval.index)
        .rolling(window=persistence_window, min_periods=1)
        .sum()
        .values
    )
    alarm_level = np.zeros(len(mse), dtype=int)
    alarm_level[(raw_level == 1) & (caution_rolling >= persistence_min_count)] = 1
    alarm_level[raw_level == 2] = 2
    alarm_level[raw_level == 3] = 3

    df["alarm_level"] = alarm_level
    df["raw_alarm_level"] = raw_level
    df["pred_is_anomaly"] = (df["alarm_level"] > 0).astype(int)
    for k in range(3):
        df[f"reason_top{k+1}_feature"] = top_feat[:, k]
        df[f"reason_top{k+1}_contribution_pct"] = np.round(top_contrib[:, k], 2)

    records, delays, hits, lates, misses = [], [], 0, 0, 0

    for i, (start_s, end_s) in enumerate(events, start=1):
        start_t = pd.to_datetime(start_s)
        window_end = start_t + pd.Timedelta(hours=DETECTION_WINDOW_HOURS)

        ev_slice = df.loc[_mask(df, start_s, end_s)]
        in_window = ev_slice.loc[ev_slice.index <= window_end]
        alerts_w = in_window[in_window["pred_is_anomaly"] == 1]
        alerts_f = ev_slice[ev_slice["pred_is_anomaly"] == 1]
        coverage = len(alerts_f) / len(ev_slice) if len(ev_slice) > 0 else 0.0

        if len(alerts_w) > 0:
            status = "hit"
            first = alerts_w.index[0]
            delay = (first - start_t).total_seconds() / 60.0
            hits += 1
            delays.append(delay)
            src = alerts_w.iloc[0]
        elif len(alerts_f) > 0:
            status = "late"
            first = alerts_f.index[0]
            delay = np.nan
            lates += 1
            src = alerts_f.iloc[0]
        else:
            status = "miss"
            first = pd.NaT
            delay = np.nan
            misses += 1
            src = None

        records.append(
            {
                "event_id": i,
                "event_start": start_s,
                "event_end": end_s,
                "status": status,
                "first_alert_time": first,
                "delay_min": round(delay, 2) if not pd.isna(delay) else np.nan,
                "event_alarm_count": len(alerts_f),
                "event_coverage": round(coverage, 4),
                "top1_reason": src["reason_top1_feature"] if src is not None else None,
                "top2_reason": src["reason_top2_feature"] if src is not None else None,
                "top3_reason": src["reason_top3_feature"] if src is not None else None,
            }
        )

    n = len(events)
    summary = {
        "event_count": n,
        "hit_count": hits,
        "late_count": lates,
        "miss_count": misses,
        "hit_rate": hits / n if n else 0.0,
        "any_detection_rate": (hits + lates) / n if n else 0.0,
        "false_alarm_rate_holdout": round(float(holdout_far), 6),
        "mean_delay_min": float(np.mean(delays)) if delays else np.nan,
    }
    return df, summary, pd.DataFrame(records)


def _logs_dir():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"
    )


def save_trial_eval(model_name, trial_num, obj_val, val_loss, far, summary, p):
    path = os.path.join(_logs_dir(), "optuna_trial_eval.csv")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    exists = os.path.isfile(path)
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(
                [
                    "Date",
                    "Domain",
                    "Trial",
                    "Objective",
                    "Val_Loss",
                    "Holdout_FAR",
                    "Events",
                    "Hit",
                    "Late",
                    "Miss",
                    "HitRate",
                    "AnyDet",
                    "MeanDelay_min",
                    "hidden_1",
                    "hidden_2",
                    "bottleneck",
                    "dropout",
                    "activation",
                    "out_act",
                    "lr",
                    "batch",
                ]
            )
        w.writerow(
            [
                pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                model_name,
                trial_num,
                round(float(obj_val), 8),
                round(float(val_loss), 8),
                round(float(far), 6),
                summary["event_count"],
                summary["hit_count"],
                summary["late_count"],
                summary["miss_count"],
                round(summary["hit_rate"], 4),
                round(summary["any_detection_rate"], 4),
                (
                    round(summary["mean_delay_min"], 2)
                    if not pd.isna(summary["mean_delay_min"])
                    else ""
                ),
                p["hidden_1"],
                p["hidden_2"],
                p["bottleneck_size"],
                p["dropout_rate"],
                p["activation"],
                p["output_activation"],
                p["learning_rate"],
                p["batch_size"],
            ]
        )


def save_final_results(model_name, ts_df, summary, events_df):
    d = os.path.join(_logs_dir(), "final_detection_results")
    os.makedirs(d, exist_ok=True)
    ts_df.to_csv(os.path.join(d, f"{model_name}_timeseries.csv"), encoding="utf-8-sig")
    events_df.to_csv(
        os.path.join(d, f"{model_name}_event_detail.csv"),
        index=False,
        encoding="utf-8-sig",
    )
    with open(
        os.path.join(d, f"{model_name}_event_summary.json"), "w", encoding="utf-8"
    ) as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
    logger.info(f"💾 [{model_name.upper()}] 최종 탐지 결과 저장: {d}")


# ==============================================================================
# [+추가] Optuna 탐색 (objective = val_loss + α × holdout_FAR)
# ==============================================================================
def run_optuna_search(X_train_ae, X_holdout, X_eval, model_name, n_trials):

    def objective(trial):
        p = {
            "hidden_1": trial.suggest_categorical("hidden_1", [16, 32, 64]),
            "hidden_2": trial.suggest_categorical("hidden_2", [8, 16, 32]),
            "bottleneck_size": trial.suggest_int(
                "bottleneck_size", 4, max(4, min(12, X_train_ae.shape[1]))
            ),
            # 🔄 2026-04-22: 하한 0.0 → 0.1 강제. dropout=0 AE 는 학습 데이터 과적합으로
            #    train MSE 분포가 인위적으로 좁아지고 → nutrient 정상 구간 FP 유발 원인.
            "dropout_rate": trial.suggest_float("dropout_rate", 0.1, 0.3, step=0.1),
            "activation": trial.suggest_categorical("activation", ["relu", "elu"]),
            "output_activation": trial.suggest_categorical(
                "output_activation", ["sigmoid", "linear"]
            ),
            "learning_rate": trial.suggest_float("learning_rate", 1e-4, 5e-3, log=True),
            "batch_size": trial.suggest_categorical("batch_size", [32, 64, 128]),
        }

        scaler = MinMaxScaler()
        X_tr = scaler.fit_transform(X_train_ae)

        ae = build_autoencoder(
            input_dim=X_tr.shape[1],
            hidden_1=p["hidden_1"],
            hidden_2=p["hidden_2"],
            bottleneck_size=p["bottleneck_size"],
            dropout_rate=p["dropout_rate"],
            activation=p["activation"],
            output_activation=p["output_activation"],
            learning_rate=p["learning_rate"],
        )

        hist = ae.fit(
            X_tr,
            X_tr,
            epochs=OPTUNA_EPOCHS,
            batch_size=p["batch_size"],
            validation_split=0.2,
            callbacks=[
                EarlyStopping(
                    monitor="val_loss",
                    patience=OPTUNA_PATIENCE,
                    restore_best_weights=True,
                )
            ],
            verbose=0,
        )
        val_loss = float(min(hist.history["val_loss"]))

        recon = ae.predict(X_tr, verbose=0)
        train_mse = np.mean(np.power(X_tr - recon, 2), axis=1)
        # 🔄 2026-04-22: σ → MAD (Robust) 전환. 기동 스파이크(sample_weight=8) 로 σ 가
        #    부풀려져 hydraulic/motor 의 threshold 가 너무 높아지고 → 5월 드리프트 지연
        #    탐지 문제 발생. MAD 는 heavy tail 에 둔감해 "정상 분포의 진짜 폭" 반영.
        thr = calculate_mad_thresholds(train_mse, sigma_levels=(2, 3, 5))

        # 🔑 holdout FAR (objective 에 반영 — 평가 데이터 누수 없음)
        holdout_mse, _, _ = score_mse_with_rca(ae, scaler, X_holdout)
        far = compute_holdout_far(holdout_mse, thr)

        # 이벤트 평가는 CSV 기록용 (objective 에 넣지 않음 = 라벨 누수 방지)
        eval_mse, top_f, top_c = score_mse_with_rca(ae, scaler, X_eval)
        _, summary, _ = evaluate_events(
            X_eval, eval_mse, top_f, top_c, thr, LABELED_EVENTS, far
        )

        obj = val_loss + FAR_PENALTY_WEIGHT * far

        save_optuna_trial_to_csv(
            model_name=model_name,
            trial_number=trial.number,
            objective_value=obj,
            params={
                **p,
                "epochs": OPTUNA_EPOCHS,
                "patience": OPTUNA_PATIENCE,
                "validation_split": 0.2,
            },
        )
        save_trial_eval(model_name, trial.number, obj, val_loss, far, summary, p)

        logger.info(
            f"🧪 [{model_name.upper()}][Trial {trial.number:02d}] "
            f"obj={obj:.6f} | val={val_loss:.6f} | FAR={far:.4f} | "
            f"hit={summary['hit_count']}/{summary['event_count']} "
            f"(late={summary['late_count']}) | delay={summary['mean_delay_min']}"
        )

        tf.keras.backend.clear_session()
        gc.collect()
        return obj

    logger.info(f"🔎 [{model_name.upper()}] Optuna 탐색 시작 (n_trials={n_trials})")
    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=n_trials)

    logger.info(f"🏆 [{model_name.upper()}] Best obj={study.best_value:.6f}")
    logger.info(f"  ▶ Best Params: {study.best_params}")

    save_optuna_best_to_json(
        model_name=model_name,
        best_value=study.best_value,
        best_params=study.best_params,
    )
    return study.best_params


# ==============================================================================
# 🛠️ [원본 구조 유지] 모델 학습 및 아티팩트 저장 통합 함수
# ==============================================================================
def train_and_save_model(X_train_ae, X_holdout, X_eval, model_name, n_trials=N_TRIALS):
    """
    원본과 동일한 흐름:
      스케일링 → 모델 생성 → 학습 → threshold → config 조립 → 저장
    추가된 것: 함수 맨 앞의 Optuna 탐색 블록 + X_holdout/X_eval 인자

    🧷 DOMAIN_BEST_PARAMS 에 엔트리가 있으면 Optuna 생략 (사전 채택 HP 사용).
    """
    start_time = time.time()
    logger.info(f"🚀 [{model_name.upper()}] 모델 파이프라인 시작")

    # --- [+추가] 0. Optuna 탐색 (또는 사전 채택 HP 사용) ---------------------
    # 🔒 2026-04-20: Optuna 재탐색 완료 → DOMAIN_BEST_PARAMS 의 HP 로 바로 학습.
    #    재탐색이 필요한 경우 아래 주석을 해제하고 DOMAIN_BEST_PARAMS 를 비우면 됨.
    preset = DOMAIN_BEST_PARAMS.get(model_name)
    if preset is not None:
        best_params = dict(preset)  # 전역 dict 오염 방지를 위해 shallow copy
        logger.info(
            f"🧷 [{model_name.upper()}] DOMAIN_BEST_PARAMS 사전 채택 HP 사용 — Optuna 생략: {best_params}"
        )
    else:
        # 🔄 2026-04-22: DOMAIN_BEST_PARAMS 비워짐 → 전 도메인 Optuna 재탐색.
        logger.info(
            f"🔎 [{model_name.upper()}] DOMAIN_BEST_PARAMS 엔트리 없음 — Optuna 재탐색 진입"
        )
        best_params = run_optuna_search(
            X_train_ae, X_holdout, X_eval, model_name, n_trials
        )

    # --- 1. 데이터 스케일링 (1차 학습) --------------------------------------
    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(X_train_ae)

    # 타겟 변경으로 피처 수가 달라진 경우 bottleneck_size 가 input_dim 초과 방지
    n_features = X_scaled.shape[1]
    if best_params["bottleneck_size"] >= n_features:
        safe_bottleneck = max(4, n_features // 2)
        logger.warning(
            f"⚠️ [{model_name.upper()}] bottleneck_size({best_params['bottleneck_size']}) >= "
            f"feature_dim({n_features}) → {safe_bottleneck} 으로 자동 조정"
        )
        best_params["bottleneck_size"] = safe_bottleneck

    # --- 2. 모델 구조 설계 ---------------------------------------------------
    logger.info("🧠 [Phase 5-2] 텐서플로우 AutoEncoder 모델 구조 설계...")

    def _build():
        return build_autoencoder(
            input_dim=X_scaled.shape[1],
            hidden_1=best_params["hidden_1"],
            hidden_2=best_params["hidden_2"],
            bottleneck_size=best_params["bottleneck_size"],
            dropout_rate=best_params["dropout_rate"],
            activation=best_params["activation"],
            output_activation=best_params["output_activation"],
            learning_rate=best_params["learning_rate"],
        )

    # --- 3. 단일-pass 학습 (self-cleaning 비활성화) -------------------------
    # 🔄 2026-04-20 (재검토): 2-pass → 1-pass 로 단순화.
    #    이유: self-cleaning 이 매일 06:00 펌프 기동 전이를 "상위 MSE" 로 분류해
    #    학습 풀에서 제거함 → AE 가 정상 기동 패턴을 학습하지 못함.
    #    3월 학습 구간 전체를 "정상" 으로 간주하고 전부 학습에 사용.
    logger.info("🚀 [Phase 5-3] AutoEncoder 학습 (전체 학습 구간)...")

    # 🆕 2026-04-21: 기동(부르릉) 샘플 오버샘플링용 sample_weight
    #    WHY: 기동 전이는 학습 데이터의 ~0.7% 밖에 안 됨 → 배치 loss 에 묻힘 →
    #    AE 가 steady-state 만 최적화 → 기동 순간 재구성 실패 → MSE tail 발생 →
    #    σ(1,2,3) 임계값을 초과 → training-period FP.
    #    HOW: is_startup_phase > 0.3 (10min window 중 30%+ 가 startup) 샘플에 8배 가중.
    #    AE loss 가 부르릉 재구성에 집중하게 돼 training MSE 분포가 평탄화됨.
    #    [Path B: startup context feature 입력 과 시너지 — context 가 제공됐을 때만
    #     가중치가 의미 있게 작동함. 둘 다 있어야 조건부 학습이 성립.]
    if "is_startup_phase" in X_train_ae.columns:
        startup_mask = X_train_ae["is_startup_phase"].values > 0.3
        sample_weight = np.ones(len(X_scaled), dtype=np.float32)
        # 🔄 2026-04-22: 8.0 → 3.0 하향. shape 피처 (peak/auc/width) 가 이미 기동 context
        #    을 명시적으로 공급하므로 weight 중복 강조 불필요. 8.0 은 steady-state 재구성
        #    정확도 저하시켜 normal 구간 MSE 상승 → Precision 하락 요인이었음.
        sample_weight[startup_mask] = 3.0
        logger.info(
            f"🔥 [{model_name.upper()}] Startup oversampling: "
            f"{int(startup_mask.sum())}/{len(X_scaled)} samples → weight=3.0"
        )
    else:
        sample_weight = None
        logger.warning(
            f"⚠️ [{model_name.upper()}] is_startup_phase 피처 없음 — sample_weight 미적용"
        )

    early_stopping = EarlyStopping(
        monitor="val_loss", patience=10, restore_best_weights=True
    )
    autoencoder = _build()
    history = autoencoder.fit(
        X_scaled,
        X_scaled,
        epochs=100,
        batch_size=best_params["batch_size"],
        validation_split=0.2,
        callbacks=[early_stopping],
        verbose=1,
        sample_weight=sample_weight,
    )

    # 학습 데이터의 복원오차 → 임계값 계산 대상
    reconstructed = autoencoder.predict(X_scaled, verbose=0)
    mse_scores = np.mean(np.power(X_scaled - reconstructed, 2), axis=1)
    gc.collect()

    # --- 4. MAD 기반 Robust 임계값 계산 (Median + 1σ̂ / 2σ̂ / 3σ̂ ; σ̂=1.4826·MAD) -----
    # 🔄 2026-04-22: σ → MAD (Robust) 전환.
    #    문제: sample_weight=8 로 오버샘플링된 기동 스파이크가 학습 MSE 의 heavy tail
    #          을 만들어 σ 를 부풀림 → Critical = μ+3σ 가 실제 "드리프트 영역" 보다 훨씬
    #          높이 잡힘 → 5월 초 클로깅 드리프트가 5월 중순까지 알람 미발화 (2주 지연).
    #    해결: median/MAD 는 heavy tail 의 영향 없음. σ̂ 이 σ 보다 작게 잡혀
    #          Caution/Warning/Critical 이 "정상 분포 폭" 을 정확히 반영 → 드리프트 조기
    #          탐지. nutrient(σ 너무 작아 FP) 도 median 기반으로 안정화.
    #    downstream 호환: thresholds dict 의 'mean'/'std' 키는 유지되지만 실제 값은
    #          median 과 1.4826*MAD (이전 버전 config 와 필드 구조 동일).
    # 🔄 2026-04-22 v2: sigma_levels (1,2,3) → (2,3,5).
    #    (1,2,3) 은 Caution ≈ 68p 로 너무 민감 → 학습 정상의 32% 가 Caution 후보 →
    #    persistence 강화해도 FP 잔여. (2,3,5) 는 Caution ≈ 95p / Warning ≈ 99p /
    #    Critical ≈ 99.9p 스케일로 옛 σ(μ+2/3/6σ) 방식과 대응.
    logger.info(
        "🎯 [Phase 5-4] 이상 탐지 임계값(Threshold) 계산 — MAD Robust (Median + 2/3/5σ̂)..."
    )

    thresholds = calculate_mad_thresholds(mse_scores, sigma_levels=(2, 3, 5))

    # 🆕 2026-04-21 v4: Hard Ceiling = percentile(training MSE, 99.9) * (1 + ε)
    #    🔄 v3 → v4: np.max() → np.percentile(99.9)
    #    WHY (비판적 리뷰):
    #      - np.max() 는 학습 데이터 단 1개 outlier(센서 글리치 등)에 지배됨.
    #      - 배포 시 "학습 max 를 약간 초과하는 novel spike" 가 inflated ceiling
    #        아래에 깔려 miss → 사용자 요구("학습 범위 밖 단발 스파이크는 즉시 잡기")
    #        미충족.
    #    HOW:
    #      - 99.9 percentile 로 상위 0.1% outlier 절단 → "학습 데이터의 진짜 상한"
    #      - 이 robust 상한 × (1+ε) = hard_ceiling
    #      - 기존 sigma-based critical 보다 낮아지지 않도록 하한 clip
    robust_max_mse = float(np.percentile(mse_scores, 99.9))
    absolute_max_mse = float(np.max(mse_scores))
    hard_ceiling = robust_max_mse * (1.0 + HARD_CEILING_EPSILON)
    hard_ceiling = max(hard_ceiling, float(thresholds["critical"]))

    logger.info(
        f"✅ MAD Robust 임계값 설정 완료! (median={thresholds['mean']:.6f}, σ̂=1.4826·MAD={thresholds['std']:.6f}) — "
        f"Caution:{thresholds['caution']:.6f} / Warning:{thresholds['warning']:.6f} / "
        f"Critical:{thresholds['critical']:.6f}"
    )
    logger.info(
        f"📏 training MSE — 99.9p={robust_max_mse:.6f} / max={absolute_max_mse:.6f} "
        f"(outlier gap={(absolute_max_mse/max(robust_max_mse,1e-12)-1)*100:.1f}%)"
    )
    logger.info(
        f"🧱 Hard Ceiling (99.9p × {1+HARD_CEILING_EPSILON:.2f}): "
        f"{hard_ceiling:.6f} — 단발 초과 시 즉시 Critical 발화"
    )

    # hard_ceiling 을 thresholds dict 에 주입 → 검증(evaluate_events)이 추론과 동일 로직 사용
    thresholds["hard_ceiling"] = hard_ceiling

    # --- 5. 프론트엔드용 메타데이터 Config 조립 (원본 그대로 + best_params) --
    logger.info("💾 [Phase 5-5] 서버 배포용 아티팩트(Artifacts) 저장...")
    config = {
        "model_name": model_name,
        "features": X_train_ae.columns.tolist(),
        "threshold_caution": thresholds["caution"],
        "threshold_warning": thresholds["warning"],
        "threshold_critical": thresholds["critical"],
        "threshold_hard_ceiling": hard_ceiling,  # 🆕 v3: 단발 즉시 Critical 기준
        "hard_ceiling_epsilon": HARD_CEILING_EPSILON,
        "metrics": {
            "train_loss": [float(l) for l in history.history["loss"]],
            "val_loss": [float(l) for l in history.history["val_loss"]],
            "final_mse_mean": thresholds["mean"],
        },
        "feature_stds": X_train_ae.std().to_dict(),
        "best_hyperparameters": best_params,  # [+추가]
    }

    # --- 6. 아티팩트 저장 (원본 그대로) -------------------------------------
    current_dir = os.path.dirname(os.path.abspath(__file__))
    save_dir = os.path.join(os.path.dirname(current_dir), "models")
    save_model_artifacts(autoencoder, scaler, config, model_name, save_dir)
    logger.info(f"✅ [{model_name.upper()}] 학습 및 아티팩트 저장 완료! ({save_dir})")

    # --- 7. 실험 기록 (원본 그대로) -----------------------------------------
    save_experiment_to_csv(
        model_name=model_name,
        mse_mean=thresholds["mean"],
        t_caut=thresholds["caution"],
        t_warn=thresholds["warning"],
        t_cri=thresholds["critical"],
    )

    elapsed = time.time() - start_time
    logger.info(f"⏱️ 모델링 소요 시간: {int(elapsed // 60)}분 {elapsed % 60:.2f}초")

    # 최종 평가를 위해 model/scaler/thresholds 를 반환
    return autoencoder, scaler, thresholds


# ==============================================================================
# ⚔️ [원본 구조 유지] 메인 실행 블록
# ==============================================================================
if __name__ == "__main__":
    total_start_time = time.time()
    logger.info("🏁 [MAIN] 다중 도메인(Multi-Domain) 예지보전 AI 파이프라인 학습 시작")

    # --- 경로 설정 (원본 그대로) ---------------------------------------------
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    data_filename = "C:/Users/ui203/OneDrive/문서/green/human_A/services/inference/data/generated_data_from_dabin_0420.csv"
    data_path = os.path.join(project_root, "data", data_filename)
    logger.info(f"📂 데이터 로딩 경로: {data_path}")

    df_raw = pd.read_csv(data_path)
    df_raw["timestamp"] = pd.to_datetime(df_raw["timestamp"])
    df_raw = df_raw.set_index("timestamp")

    # --- [+추가] 2분할 — 학습 구간 전체 + 평가 구간 ---------------------------
    # 🔄 HOLDOUT 은 학습 데이터 내부에서 K-fold 스타일 랜덤 분할로 뒤에서 생성.
    df_train = df_raw.loc[_mask(df_raw, *TRAIN_RANGE)].copy()
    df_eval = df_raw.loc[_mask(df_raw, *EVAL_RANGE)].copy()

    logger.info("=" * 72)
    logger.info("📌 시간 기반 데이터 분리")
    logger.info(
        f"  ▶ 학습용(31일): {TRAIN_RANGE[0][:10]} ~ {TRAIN_RANGE[1][:10]} | {len(df_train):,}행"
    )
    logger.info(
        f"  ▶ Eval        : {EVAL_RANGE[0][:10]} ~ {EVAL_RANGE[1][:10]} | {len(df_eval):,}행"
    )
    logger.info(
        f"  ▶ Holdout     : 학습 구간 내 랜덤 {int(HOLDOUT_FRACTION*100)}% (seed={HOLDOUT_RANDOM_SEED})"
    )
    logger.info("=" * 72)

    # --- 도메인별 타겟 (2026-04-20 개편: motor/hydraulic/nutrient/zone_drip) -----
    subsystem_targets = {
        "motor": {  # 전기/회전 이상 도메인
            "motor_current_a": [
                "motor_power_kw",
                "motor_temperature_c",
                "wire_to_water_efficiency",
                "bearing_vibration_rms_mm_s",
            ],
            "rpm_stability_index": ["pump_rpm"],
        },
        "hydraulic": {  # 수력/압력/유량 도메인
            "zone1_resistance": ["zone1_pressure_kpa", "zone1_flow_l_min"],
            "differential_pressure_kpa": [
                "discharge_pressure_kpa",
                "suction_pressure_kpa",
            ],
        },
        "nutrient": {  # 양액/EC 제어 품질 도메인
            "pid_error_ec": ["mix_ec_ds_m", "mix_target_ec_ds_m"],
            "salt_accumulation_delta": ["drain_ec_ds_m", "mix_ec_ds_m"],
        },
        "zone_drip": {  # 구역 점적 시스템 도메인 (수분 반응 + EC 축적)
            "zone1_moisture_response_pct": ["zone1_substrate_moisture_pct"],
            "zone1_ec_accumulation": ["zone1_substrate_ec_ds_m", "mix_ec_ds_m"],
        },
    }

    # --- 도메인별 학습 루프 (원본 구조 유지) ---------------------------------
    for system_name, target_dict in subsystem_targets.items():
        # 🔄 DOMAINS_TO_TRAIN 가 지정되면 해당 도메인만 학습 (nutrient 먼저 검증용)
        if DOMAINS_TO_TRAIN is not None and system_name not in DOMAINS_TO_TRAIN:
            logger.info(f"⏭️ [{system_name.upper()}] DOMAINS_TO_TRAIN 필터로 스킵")
            continue

        logger.info(f"[{system_name.upper()} 도메인] 분석 파이프라인 시작")

        # 1. 피처 셀렉션 (원본 그대로) — 단, df_raw 대신 df_train 만 넣음
        robust_features, X_train_ae, df_agg, _ = run_feature_selection_experiment(
            df_raw=df_train, window_method="sliding", target_dict=target_dict
        )

        # 🛡️ 안전장치: robust 결과가 비면 해당 도메인은 스킵 (scaler 폭발 방지)
        if X_train_ae.shape[1] == 0:
            logger.error(
                f"❌ [{system_name.upper()}] robust 피처 0개 — "
                f"target_dict={list(target_dict.keys())}. 이 도메인 스킵."
            )
            continue

        # VIP 프리패스 — feature_selection 이 떨궈도 강제 주입되는 필수 피처들
        # 🆕 2026-04-21: 기동 context 3피처 추가 (부르릉 정상 학습용).
        #    AE 가 "지금 기동 중" 을 알고 조건부 재구성하도록 context signal 공급.
        # 🆕 2026-04-22: 기동 스파이크 shape 피처 도메인별 주입.
        #    motor    → motor_current_a 의 peak/auc/width (inrush 파형)
        #    hydraulic→ discharge_pressure_kpa + flow_rate_l_min shape (램프 파형)
        #    nutrient → 기동 shape 무관 (EC 제어 축이 다름) — 주입 안 함
        #    zone_drip→ 유량 기반이므로 flow_rate shape 만 주입
        #    AE 가 shape 분포를 학습하면 "평소보다 10% 높거나 2분 길다" 도 MSE 로 검출.
        vip_cols = [
            "time_sin",
            "time_cos",
            "pump_start_event",
            "is_startup_phase",
            "minutes_since_startup",
        ]
        _SHAPE_STATS = ["startup_peak", "startup_auc", "startup_width_min"]
        _DOMAIN_SHAPE_SIGNALS = {
            "motor": ["motor_current_a"],
            "hydraulic": ["discharge_pressure_kpa", "flow_rate_l_min"],
            "zone_drip": ["flow_rate_l_min"],
            # "nutrient" 는 shape 피처 불필요
        }
        for _sig in _DOMAIN_SHAPE_SIGNALS.get(system_name, []):
            for _stat in _SHAPE_STATS:
                vip_cols.append(f"{_sig}_{_stat}")
        missing_vips = [
            col
            for col in vip_cols
            if col not in X_train_ae.columns and col in df_agg.columns
        ]
        if missing_vips:
            logger.info(
                f"🔗 오토인코더 입력 데이터에 VIP 피처 강제 주입: {missing_vips}"
            )
            time_features = df_agg[missing_vips]
            X_train_ae = pd.concat([X_train_ae, time_features], axis=1)

        # 🚫 2026-04-22: 도메인 분리 필터 — 기계 도메인(motor / hydraulic) 에서
        #    다른 도메인 signal 을 솎아낸다.
        #
        #    WHY: feature_selection 은 상관 기반 투표이므로 pump_on 과 동조하는 신호는
        #         전부 끌어올려진다 — 예) motor 에 `mix_ec_ds_m`, hydraulic 에 `turbidity_ntu`.
        #         이는 (1) 도메인 분리 원칙 위반 (2) SHAP 에 다른 도메인 피처가 섞여 발표
        #         설명력 훼손 (3) hydraulic 의 `zone1_resistance` 는 V/I 비율이라 학습
        #         구간 외 extrapolation 시 scaled 값이 폭발 → MSE 지배 → 단일 피처 독점.
        #
        #    SCOPE: motor / hydraulic 만 필터. nutrient(EC/양액) + zone_drip(점적 tip) 은
        #           각자 핵심 signal 이 제외 토큰과 겹치므로 **무필터**.
        #
        #    TOKENS (per domain, substring match):
        #      motor     : pH/EC 7토큰 + turbidity (수질은 기계 도메인 무관)
        #      hydraulic : pH/EC 7토큰 + turbidity + zone1_resistance (V/I extrapolation)
        _DOMAIN_FEATURE_EXCLUSIONS = {
            "motor": (
                "ec_ds_m",
                "ec_accumulation",
                "pid_error_ec",
                "salt_accumulation",
                "mix_ph",
                "ph_ds_m",
                "pid_error_ph",
                "turbidity",
            ),
            "hydraulic": (
                "ec_ds_m",
                "ec_accumulation",
                "pid_error_ec",
                "salt_accumulation",
                "mix_ph",
                "ph_ds_m",
                "pid_error_ph",
                "turbidity",
                "zone1_resistance",
            ),
        }
        if system_name in _DOMAIN_FEATURE_EXCLUSIONS:
            tokens = _DOMAIN_FEATURE_EXCLUSIONS[system_name]
            blacklist = [c for c in X_train_ae.columns if any(t in c for t in tokens)]
            if blacklist:
                logger.info(
                    f"🚫 [{system_name.upper()}] 도메인 분리 필터 "
                    f"({len(blacklist)}개): {blacklist}"
                )
                X_train_ae = X_train_ae.drop(columns=blacklist)
            else:
                logger.info(
                    f"🚫 [{system_name.upper()}] 도메인 분리 필터 대상 없음 (이미 깨끗)"
                )

        # 🔍 선택된 피처 즉시 로깅 (feature_selection 붕괴 재발 감지)
        logger.info(
            f"🎯 [{system_name.upper()}] 선택된 피처 {len(X_train_ae.columns)}개: "
            f"{X_train_ae.columns.tolist()}"
        )

        # 🔄 [랜덤 홀드아웃] 전처리 완료된 학습 데이터에서 단일 80/20 split
        # 이유: 학습 구간 말일의 드리프트 초입이 holdout 에 편향되지 않게 하려고.
        rng = np.random.default_rng(HOLDOUT_RANDOM_SEED)
        n = len(X_train_ae)
        shuffled = rng.permutation(n)
        holdout_n = max(1, int(n * HOLDOUT_FRACTION))
        holdout_idx = np.sort(shuffled[:holdout_n])
        train_idx = np.sort(shuffled[holdout_n:])
        X_holdout = X_train_ae.iloc[holdout_idx].copy()
        X_train_ae = X_train_ae.iloc[train_idx].copy()
        logger.info(
            f"🎲 [{system_name.upper()}] 랜덤 홀드아웃 split: "
            f"train={len(X_train_ae):,}행 / holdout={len(X_holdout):,}행"
        )

        # [+추가] eval 구간은 동일 전처리로 변환 (holdout 은 학습 내부에서 이미 분리)
        final_features = X_train_ae.columns.tolist()
        train_means = X_train_ae.mean().to_dict()
        X_eval = preprocess_for_eval(df_eval, final_features, train_means)

        # 2. 도메인별 모델 학습 및 저장 (원본 호출 + Optuna 옵션)
        autoencoder, scaler, thresholds = train_and_save_model(
            X_train_ae,
            X_holdout,
            X_eval,
            model_name=system_name,
            n_trials=N_TRIALS,
        )

        # [+추가] 3. 최종 모델로 4~5월 탐지 평가 + CSV 저장
        holdout_mse, _, _ = score_mse_with_rca(autoencoder, scaler, X_holdout)
        final_far = compute_holdout_far(holdout_mse, thresholds)

        eval_mse, top_f, top_c = score_mse_with_rca(autoencoder, scaler, X_eval)
        ts_df, summary, events_df = evaluate_events(
            X_eval,
            eval_mse,
            top_f,
            top_c,
            thresholds,
            LABELED_EVENTS,
            final_far,
            hard_ceiling=thresholds.get("hard_ceiling"),  # 🆕 v4: 추론과 동일 로직
        )
        save_final_results(system_name, ts_df, summary, events_df)

        logger.info(
            f"✅ [{system_name.upper()}] "
            f"hit={summary['hit_count']}/{summary['event_count']} | "
            f"late={summary['late_count']} | miss={summary['miss_count']} | "
            f"FAR={final_far:.4f} | delay={summary['mean_delay_min']}"
        )

        tf.keras.backend.clear_session()
        gc.collect()

    total_end_time = time.time()
    t_min, t_sec = divmod(total_end_time - total_start_time, 60)
    logger.info(
        "🎉 모든 서브시스템(Motor, Hydraulic, Nutrient, Zone_Drip)의 모델 학습이 성공적으로 종료되었습니다!"
    )
    logger.info(
        f"🏆 전체 파이프라인 구동 완료! (총 소요 시간: {int(t_min)}분 {t_sec:.2f}초)"
    )
