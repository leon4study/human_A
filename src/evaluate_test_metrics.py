"""
테스트 CSV(`anomaly_label` 포함)로 학습된 AE 모델의 FN/FP를 정량 측정.

실행:
    cd /Users/jun/GitStudy/human_A/src
    python evaluate_test_metrics.py

출력:
    - 콘솔: 구간별(학습/평가) × cutoff별(level≥1/≥2/≥3) × 도메인별 precision/recall/F1
    - CSV: ../data/evaluation_outputs/ 에 혼동행렬 · FN/FP 타임스탬프 저장
"""
from __future__ import annotations

import glob
import json
import os
import sys

import joblib
import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score

from preprocessing import step1_prepare_window_data
from inference_core import get_alarm_status, actionable_feature_mask
from repro import latest_run_dir

# [진단 시각화] matplotlib 부재 시에도 평가 자체는 진행되도록 import 실패를 흡수.
try:
    from viz import plot_threshold_diagnosis, build_contact_sheet
    _VIZ_AVAILABLE = True
except Exception:
    _VIZ_AVAILABLE = False

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_CSV = os.path.join(PROJECT_ROOT, "data", "generated_test_data_0420.csv")
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
OUT_DIR = os.path.join(PROJECT_ROOT, "data", "evaluation_outputs")

TRAIN_RANGE = ("2026-03-01", "2026-03-31")
EVAL_RANGE = ("2026-04-01", "2026-05-31")

LEVEL_CUTOFFS = [1, 2, 3]  # 각각 "Caution 이상 = 이상", "Warning 이상", "Critical 이상"

# A-2: nutrient 도메인은 타겟(mix_ec 등)과 최종 학습 피처(time/pump_rpm/motor_temp)가 어긋나
# 5월 정지 시간대에 FP를 독점 발생시킴 (547/581 = 94%).
# A-3(feature_selection 재검토)로 근본 수정 전까지 overall voting에서 제외.
EXCLUDE_FROM_OVERALL = {"nutrient"}


def run_inference(df_agg: pd.DataFrame) -> tuple[pd.DataFrame, list[str], dict]:
    """도메인별 배치 예측 → `{domain}_level`·`{domain}_score` 컬럼 DataFrame + 임계치 맵 반환."""
    config_files = glob.glob(os.path.join(MODELS_DIR, "*_config.json"))
    systems = sorted(os.path.basename(f).replace("_config.json", "") for f in config_files)

    rows = {dom: np.zeros(len(df_agg), dtype=int) for dom in systems}
    scores = {dom: np.zeros(len(df_agg), dtype=float) for dom in systems}
    thr_map = {}  # 도메인별 임계치(mean/caution/warning/critical) — 시각화에서 재사용
    loaded = []

    for dom in systems:
        model_p = os.path.join(MODELS_DIR, f"{dom}_model.keras")
        scaler_p = os.path.join(MODELS_DIR, f"{dom}_scaler.pkl")
        config_p = os.path.join(MODELS_DIR, f"{dom}_config.json")
        if not all(os.path.exists(p) for p in [model_p, scaler_p, config_p]):
            print(f"⚠️  {dom}: 아티팩트 누락 → 스킵")
            continue

        model = tf.keras.models.load_model(model_p)
        scaler = joblib.load(scaler_p)
        cfg = json.load(open(config_p, "r", encoding="utf-8"))
        features = cfg["features"]
        t_caut = float(cfg["threshold_caution"])
        t_warn = float(cfg["threshold_warning"])
        t_err = float(cfg.get("threshold_critical", cfg.get("threshold_error")))
        thr_map[dom] = {
            "mean": float(cfg.get("metrics", {}).get("final_mse_mean", float("nan"))),
            "caution": t_caut, "warning": t_warn, "critical": t_err,
            "startup": cfg.get("threshold_startup"),   # 기동 전용 band(없으면 None)
        }

        X = pd.DataFrame(index=df_agg.index, columns=features, dtype=float)
        for f in features:
            X[f] = df_agg[f].astype(float).values if f in df_agg.columns else 0.0

        X_scaled = scaler.transform(X)
        preds = model.predict(X_scaled, batch_size=512, verbose=0)
        # 알람 점수는 train.py·inference_api와 '동일한 피처 셋'(scoring_features)으로 낸다.
        #   config에 scoring_features가 있으면 그 목록, 없으면 컨텍스트 제외 마스크로 폴백.
        #   [왜 중요] evaluate가 전체 피처 평균을 쓰면, 서빙이 제외하는 컨텍스트/외래 피처가
        #   점수에 섞여 측정 FAR이 서빙과 달라지고, scoring_features 변경(외래피처 채점 제외 등)이
        #   측정에 안 잡힌다. eval==serve를 맞춰야 측정도구가 서빙 모델을 정직하게 잰다.
        sq_err = (X_scaled - preds) ** 2
        _scoring = cfg.get("scoring_features")
        if _scoring:
            _mask = np.array([fc in set(_scoring) for fc in features], dtype=bool)
        else:
            _mask = actionable_feature_mask(features)
        if _mask.sum() == 0:
            _mask = np.ones(len(features), dtype=bool)
        mse = np.mean(sq_err[:, _mask], axis=1)

        levels = np.array(
            [get_alarm_status(float(m), t_caut, t_warn, t_err)[0] for m in mse]
        )
        rows[dom] = levels
        scores[dom] = mse
        loaded.append(dom)
        print(f"✅ {dom}: N={len(df_agg)}, thr_caut={t_caut:.4f} / warn={t_warn:.4f} / err={t_err:.4f}")

    df = pd.DataFrame(index=df_agg.index)
    for dom in loaded:
        df[f"{dom}_level"] = rows[dom]
        df[f"{dom}_score"] = scores[dom]

    voting_domains = [d for d in loaded if d not in EXCLUDE_FROM_OVERALL]
    df["overall_alarm_level"] = df[[f"{d}_level" for d in voting_domains]].max(axis=1)
    if EXCLUDE_FROM_OVERALL & set(loaded):
        df["overall_alarm_level_with_nutrient"] = df[[f"{d}_level" for d in loaded]].max(axis=1)
        print(f"🚫 overall voting 제외 도메인: {sorted(EXCLUDE_FROM_OVERALL & set(loaded))}")

    # 기동(startup) 처리 — STARTUP_MODE 로 두 전략을 공존시킨다(docs/modeling/03 §4-2).
    #   gate(성능)  : 기동 윈도우 알람을 통째로 Normal(0)로 억제. 정상기동 오탐 0이나
    #                 비정상 기동(평소보다 큰 기동 스파이크)도 놓친다.
    #   regime(논리): 기동 윈도우는 도메인별 '기동 band'로 재판정. 정상 기동은 통과,
    #                 비정상적으로 큰 기동만 알람. band가 없는 도메인은 gate로 폴백.
    #   기본 regime. 실험 근거: startup_strategy_eval.py(통째게이트 비정상기동 recall 0).
    mode = os.environ.get("STARTUP_MODE", "regime").lower()
    if "is_startup_phase" in df_agg.columns:
        su = df_agg["is_startup_phase"].to_numpy() >= 0.5
        for dom in loaded:
            band = thr_map[dom].get("startup")
            if mode == "regime" and band:
                sc = df[f"{dom}_score"].to_numpy()
                relvl = np.array([
                    get_alarm_status(float(m), band["caution"], band["warning"], band["critical"])[0]
                    for m in sc
                ])
                df.loc[su, f"{dom}_level"] = relvl[su]
            else:
                df.loc[su, f"{dom}_level"] = 0   # gate 또는 band 부재 → 통째 억제
        # overall 재계산(기동 윈도우 레벨이 바뀌었으므로)
        df["overall_alarm_level"] = df[[f"{d}_level" for d in voting_domains]].max(axis=1)
        if EXCLUDE_FROM_OVERALL & set(loaded):
            df["overall_alarm_level_with_nutrient"] = df[[f"{d}_level" for d in loaded]].max(axis=1)
    return df, loaded, thr_map


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, label: str) -> dict:
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    p = precision_score(y_true, y_pred, zero_division=0)
    r = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    total = len(y_true)
    pos = int(y_true.sum())
    return {
        "scope": label,
        "N": total,
        "positives": pos,
        "TP": int(tp),
        "FP": int(fp),
        "FN": int(fn),
        "TN": int(tn),
        "precision": round(p, 4),
        "recall": round(r, 4),
        "f1": round(f1, 4),
        "FAR": round(fp / max(tn + fp, 1), 4),  # False Alarm Rate
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"📂 CSV: {DATA_CSV}")
    df_raw = pd.read_csv(DATA_CSV)
    df_raw["timestamp"] = pd.to_datetime(df_raw["timestamp"])
    df_raw = df_raw.set_index("timestamp")
    print(f"1min raw: {df_raw.shape}")

    # anomaly_label / composite_z_score는 model_cols 화이트리스트에 없어서
    # create_modeling_features()에서 drop됨 → extra_cols(target_cols)로 보존 강제.
    df_agg, _ = step1_prepare_window_data(
        df_raw,
        window_method="tumbling",
        target_cols=["anomaly_label", "composite_z_score", "cleaning_event_flag"],
    )
    df_agg = df_agg.dropna()
    print(f"10min agg: {df_agg.shape}")

    if "anomaly_label" not in df_agg.columns:
        sys.exit("❌ df_agg에 anomaly_label 없음 — preprocessing passthrough 점검")

    y_true = df_agg["anomaly_label"].astype(int).values

    print("\n=== 도메인별 추론 실행 ===")
    df_pred, domains, thr_map = run_inference(df_agg)

    # 평가 구간 분할
    idx = df_agg.index
    mask_train = (idx >= pd.Timestamp(TRAIN_RANGE[0])) & (idx <= pd.Timestamp(TRAIN_RANGE[1]))
    mask_eval = (idx >= pd.Timestamp(EVAL_RANGE[0])) & (idx <= pd.Timestamp(EVAL_RANGE[1]))

    print(f"\n라벨 분포 (10min 윈도우 기준)")
    print(f"  전체 anomaly 비율: {y_true.mean():.4f} ({int(y_true.sum())}/{len(y_true)})")
    print(f"  학습구간 anomaly 비율: {y_true[mask_train].mean():.4f}")
    print(f"  평가구간 anomaly 비율: {y_true[mask_eval].mean():.4f}")

    # === 구간 × cutoff × 도메인 조합 metrics ===
    metrics_rows = []
    for scope_name, mask in [("TRAIN", mask_train), ("EVAL", mask_eval), ("ALL", np.ones(len(y_true), dtype=bool))]:
        yt = y_true[mask]
        for cut in LEVEL_CUTOFFS:
            # Overall (nutrient 제외 A-2 적용)
            yp = (df_pred["overall_alarm_level"].values[mask] >= cut).astype(int)
            m = compute_metrics(yt, yp, f"{scope_name} / overall(no_nutrient) / level>={cut}")
            metrics_rows.append(m)
            # Overall (nutrient 포함, 비교용)
            if "overall_alarm_level_with_nutrient" in df_pred.columns:
                yp_w = (df_pred["overall_alarm_level_with_nutrient"].values[mask] >= cut).astype(int)
                m_w = compute_metrics(yt, yp_w, f"{scope_name} / overall(with_nutrient) / level>={cut}")
                metrics_rows.append(m_w)
            # Per-domain
            for dom in domains:
                yp_d = (df_pred[f"{dom}_level"].values[mask] >= cut).astype(int)
                m_d = compute_metrics(yt, yp_d, f"{scope_name} / {dom} / level>={cut}")
                metrics_rows.append(m_d)

    metrics_df = pd.DataFrame(metrics_rows)
    metrics_csv = os.path.join(OUT_DIR, "metrics_summary.csv")
    metrics_df.to_csv(metrics_csv, index=False, encoding="utf-8-sig")

    # === 콘솔 출력: overall만 표로 ===
    print("\n=== Overall metrics (any domain level ≥ cutoff vs anomaly_label) ===")
    overall = metrics_df[metrics_df["scope"].str.contains("overall")].copy()
    print(overall.to_string(index=False))

    # === 평가구간 도메인별 cutoff=1 메트릭 ===
    print("\n=== EVAL 구간 · 도메인별 (cutoff level>=1) ===")
    dom_table = metrics_df[
        metrics_df["scope"].str.startswith("EVAL /")
        & metrics_df["scope"].str.endswith("level>=1")
        & ~metrics_df["scope"].str.contains("overall")
    ]
    print(dom_table.to_string(index=False))

    # === FN / FP 타임스탬프 저장 (overall, cutoff=1, EVAL 기준) ===
    yp_overall = (df_pred["overall_alarm_level"].values >= 1).astype(int)
    fn_mask = mask_eval & (y_true == 1) & (yp_overall == 0)
    fp_mask = mask_eval & (y_true == 0) & (yp_overall == 1)

    fn_df = df_agg.loc[fn_mask, ["anomaly_label", "composite_z_score"]].copy()
    for dom in domains:
        fn_df[f"{dom}_level"] = df_pred.loc[fn_mask, f"{dom}_level"]
        fn_df[f"{dom}_score"] = df_pred.loc[fn_mask, f"{dom}_score"].round(6)
    fn_df.to_csv(os.path.join(OUT_DIR, "fn_eval_overall.csv"), encoding="utf-8-sig")

    fp_df = df_agg.loc[fp_mask, ["anomaly_label", "composite_z_score"]].copy()
    for dom in domains:
        fp_df[f"{dom}_level"] = df_pred.loc[fp_mask, f"{dom}_level"]
        fp_df[f"{dom}_score"] = df_pred.loc[fp_mask, f"{dom}_score"].round(6)
    fp_df.to_csv(os.path.join(OUT_DIR, "fp_eval_overall.csv"), encoding="utf-8-sig")

    print(f"\n💾 저장:")
    print(f"  - {metrics_csv}")
    print(f"  - {os.path.join(OUT_DIR, 'fn_eval_overall.csv')}  ({int(fn_mask.sum())}건)")
    print(f"  - {os.path.join(OUT_DIR, 'fp_eval_overall.csv')}  ({int(fp_mask.sum())}건)")

    # === 진단 시각화: 도메인별 MSE 타임라인 + 임계치 + 이상 라벨 음영 ===
    # 데이터 구조상 월1(3월, 정상 학습) → 월2(4월, drift) → 월3(5월, 본격 이상)이므로,
    # 전체 구간을 그리면 3월엔 잠잠하다가 이상 음영(빨강) 구간에서 MSE가 임계선을 넘는지가
    # 한눈에 보인다. = "지정한 이상 구간부터 모델이 탐지하는가"의 직접 증거.
    # 그래프는 이 모델을 만든 학습 run의 figures/에 합류시켜 학습 그래프와 한 묶음으로 둔다.
    if _VIZ_AVAILABLE:
        try:
            run_dir = latest_run_dir(MODELS_DIR)
            fig_dir = (os.path.join(run_dir, "figures") if run_dir
                       else os.path.join(OUT_DIR, "figures"))

            # 학습/평가 경계 위치(평가 시작 인덱스) — 세로선으로 "학습은 여기까지" 표시
            boundary_pos = int((idx < pd.Timestamp(EVAL_RANGE[0])).sum())

            # 기동 마스크(있으면): 평가 집계본에 운전 맥락 피처가 남아 있을 때만
            startup_mask = None
            if "is_startup_phase" in df_agg.columns:
                startup_mask = (df_agg["is_startup_phase"].to_numpy() == 1)
            elif "minutes_since_startup" in df_agg.columns:
                startup_mask = (df_agg["minutes_since_startup"].to_numpy() <= 5)

            for dom in domains:
                plot_threshold_diagnosis(
                    df_pred[f"{dom}_score"].to_numpy(),
                    thr_map[dom],
                    model_name=dom,
                    save_path=os.path.join(fig_dir, f"{dom}__eval_timeline.png"),
                    startup_mask=startup_mask,
                    anomaly_mask=(y_true == 1),
                    boundary_index=boundary_pos,
                    boundary_label="train end (month1)",
                    show_excl_startup=False,  # 평가 데이터엔 이상값 혼재 → 보조선 비활성
                )
            sheet = build_contact_sheet(fig_dir)
            print(f"\n[viz] 평가 진단 그래프 저장: {fig_dir}")
            if sheet:
                print(f"   대조표: {sheet}")
        except Exception as e:
            print(f"[viz] 평가 시각화 실패(메트릭은 정상 저장됨): {e}")
    else:
        print("[viz] matplotlib 미가용으로 평가 시각화 생략")


if __name__ == "__main__":
    main()
