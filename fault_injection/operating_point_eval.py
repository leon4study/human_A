"""
operating_point_eval.py — 운영점(operating point) 진단 + 임계 percentile sweep.

[이 파일이 푸는 문제]
"정확도를 높이자"의 첫걸음은 '지금 오탐(FAR)이 어디서 오는가'를 국소화하는 것이다. 막연히
재학습하지 말고, (1) FAR이 어느 도메인에서, (2) 기동(startup) 구간인지 정상 운전 구간인지
나눠 보고, (3) 같은 모델에서 임계값(percentile)을 바꾸면 '검출을 유지한 채 FAR을 더 낮출 여지'가
있는지 운영점 곡선으로 본다. 재학습 없이(=가벼운 추론만으로) 튜닝 여지를 측정한다.

[배경 — 임계는 어떻게 정해지나]
train.py는 정상 학습 데이터의 복원오차(MSE) 분포에서 '기동 구간을 뺀' 뒤 분위(percentile)로
임계를 잡는다(정본 P99/99.6/99.9). 그래서 여기서도 동일하게: 임계 후보는 'train 정상(기동 제외)
점수의 분위'로 만들고, 그 임계를 held-out 평가셋에 적용해 검출/FAR을 잰다(학습셋으로 임계를
정하고 테스트셋으로 평가 — 데이터 누수 없음).

[지표]
  - steady FAR  : 정상 운전(기동 아님) 구간에서 알람이 잘못 뜬 비율. 운영점 튜닝의 주 대상.
  - startup FAR : 기동 구간에서 알람이 잘못 뜬 비율. 별도 레버(기동 band 일반화, 재학습 필요).
  - 검출        : 막힘 에피소드[시작~고장] 안에서 알람이 한 번이라도 떴는가(사전 감지).

[voting]
  overall = nutrient를 뺀 voting 도메인들의 알람 OR(evaluate_test_metrics.EXCLUDE_FROM_OVERALL과 동일).

실행:
    cd fault_injection && python operating_point_eval.py
"""
import os
import sys
import glob
import json

import joblib
import numpy as np
import pandas as pd
import tensorflow as tf

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(PROJECT, "src")
sys.path.insert(0, SRC)

from preprocessing import step1_prepare_window_data          # noqa: E402  (학습/추론과 동일 윈도우)
from inference_core import actionable_feature_mask, reconstruction_score  # noqa: E402

MODELS_DIR = os.environ.get("MODELS_DIR", os.path.join(PROJECT, "models"))
CLEAN_CSV = os.path.join(PROJECT, "data", "smartfarm_normal_train_v5.csv")   # 임계 기준(train 정상)
FAULTY_CSV = os.path.join(PROJECT, "data", "faulty_testset_v2.csv")           # 평가(held-out + 고장 라벨)

# nutrient는 화학센서 노이즈로 FP를 독점 → overall voting 제외(evaluate_test_metrics와 동일 정책).
EXCLUDE_FROM_OVERALL = set()  # nutrient: ph_trend trim으로 FP 해결 → 포함(C)

# 운영점 sweep에서 훑을 'caution(주의) 분위' 후보. 낮을수록 민감(검출↑·FAR↑), 높을수록 보수적.
SWEEP_PCTS = [97.0, 98.0, 98.5, 99.0, 99.3, 99.5, 99.7, 99.9]


def window(df_raw):
    """raw → 10분 tumbling 집계(학습/추론과 동일). anomaly_label 보존, NaN 행 제거."""
    da, _ = step1_prepare_window_data(
        df_raw, window_method="tumbling", target_cols=["anomaly_label"]
    )
    return da.dropna()


def load_domain(dom):
    """도메인 모델/스케일러/설정 로드 + scoring_features 마스크 산출."""
    cfg = json.load(open(os.path.join(MODELS_DIR, f"{dom}_config.json"), encoding="utf-8"))
    model = tf.keras.models.load_model(os.path.join(MODELS_DIR, f"{dom}_model.keras"))
    scaler = joblib.load(os.path.join(MODELS_DIR, f"{dom}_scaler.pkl"))
    return model, scaler, cfg


def domain_mse(df_agg, model, scaler, cfg):
    """scoring_features 기준 도메인 MSE(N,) 반환 — 서빙·평가와 동일한 채점 피처 셋."""
    features = cfg["features"]
    X = pd.DataFrame(index=df_agg.index, columns=features, dtype=float)
    for f in features:
        X[f] = df_agg[f].astype(float).values if f in df_agg.columns else 0.0
    Xs = scaler.transform(X)
    preds = model.predict(Xs, batch_size=512, verbose=0)
    sq = (Xs - preds) ** 2
    scoring = cfg.get("scoring_features")
    if scoring:
        mask = np.array([fc in set(scoring) for fc in features], dtype=bool)
    else:
        mask = actionable_feature_mask(features)
    if mask.sum() == 0:
        mask = np.ones(len(features), dtype=bool)
    return reconstruction_score(sq, mask, trim_top=cfg.get("recon_trim_top", 0))


def startup_mask_of(df_agg):
    """기동(startup) 윈도우 불리언 마스크. 컨텍스트 피처가 있으면 사용, 없으면 전부 False."""
    if "is_startup_phase" in df_agg.columns:
        return df_agg["is_startup_phase"].to_numpy() >= 0.5
    if "minutes_since_startup" in df_agg.columns:
        return df_agg["minutes_since_startup"].to_numpy() <= 5
    return np.zeros(len(df_agg), dtype=bool)


def episodes_of(fr):
    """fault_id별 [시작, 고장시점] 에피소드 목록(고장시점 있는 막힘만 — lead-time 정의 가능)."""
    eps = []
    for fid in sorted(int(x) for x in fr.loc[fr["fault_id"] >= 0, "fault_id"].unique()):
        sub = fr[fr["fault_id"] == fid]
        ft = pd.to_datetime(sub["failure_time"], errors="coerce").dropna()
        if len(ft):
            eps.append({"start": sub.index.min(), "failure": ft.iloc[0]})
    return eps


def main():
    print(f"models={MODELS_DIR}\n임계 기준=train 정상(기동 제외), 평가=held-out v2\n")

    # ── 1) train 정상(임계 기준) · held-out(평가) 윈도우 집계 ────────────────────────
    clean = pd.read_csv(CLEAN_CSV)
    clean["timestamp"] = pd.to_datetime(clean["timestamp"])
    clean = clean.set_index("timestamp")
    clean["anomaly_label"] = 0
    da_clean = window(clean)
    su_clean = startup_mask_of(da_clean)              # train 기동 마스크(임계는 기동 제외에서 산출)

    fr = pd.read_csv(FAULTY_CSV)
    fr["timestamp"] = pd.to_datetime(fr["timestamp"])
    fr = fr.set_index("timestamp")
    da_f = window(fr)
    su_f = startup_mask_of(da_f)                      # held-out 기동 마스크
    normal_f = da_f["anomaly_label"].to_numpy() == 0  # 정상(비고장) 윈도우 = FAR 분모
    eps = episodes_of(fr)

    # ── 2) 도메인별 점수 계산(voting 도메인만) ──────────────────────────────────────
    cfg_files = glob.glob(os.path.join(MODELS_DIR, "*_config.json"))
    all_doms = sorted(os.path.basename(f).replace("_config.json", "") for f in cfg_files)
    voting = [d for d in all_doms if d not in EXCLUDE_FROM_OVERALL]
    print(f"voting 도메인: {voting} (제외: {sorted(EXCLUDE_FROM_OVERALL & set(all_doms))})\n")

    train_mse, held_mse, cur_thr, band_thr = {}, {}, {}, {}
    for dom in voting:
        model, scaler, cfg = load_domain(dom)
        train_mse[dom] = domain_mse(da_clean, model, scaler, cfg)
        held_mse[dom] = domain_mse(da_f, model, scaler, cfg)
        cur_thr[dom] = float(cfg["threshold_caution"])          # 정상 운전 caution 임계
        sb = cfg.get("threshold_startup")                        # 기동 전용 band(없으면 None=gate)
        band_thr[dom] = float(sb["caution"]) if sb else None

    # ── 3) 진단: serve와 동일 판정으로 도메인별 FAR(기동/정상 분리) + 검출 기여 ────────
    #    serve(run_inference)는 정상 구간은 main 임계, 기동 구간은 '기동 band'로 판정한다.
    #    여기서도 똑같이 적용해야 정직하다(기동에 main 임계를 적용하면 band의 효과가 가려져
    #    기동 FAR이 과장된다). band가 없는 도메인은 기동을 통째 억제(gate)하는 serve 폴백을 따른다.
    print("=== [진단] serve 일치 판정(정상=main 임계 / 기동=기동 band) — 도메인별 ===")
    print(f"  {'도메인':<10}{'정상FAR':>9}{'기동FAR':>9}{'검출기여':>9}  band")
    for dom in voting:
        hm = held_mse[dom]
        steady_alarm = hm >= cur_thr[dom]
        if band_thr[dom] is not None:
            startup_alarm = hm >= band_thr[dom]                 # 기동은 band로 판정(serve 일치)
        else:
            startup_alarm = np.zeros(len(hm), dtype=bool)       # band 없음 → 기동 통째 억제(gate)
        combined = np.where(su_f, startup_alarm, steady_alarm)  # 구간별로 다른 임계(serve와 동일)
        steady_far = steady_alarm[normal_f & ~su_f].mean() if (normal_f & ~su_f).any() else 0.0
        startup_far = startup_alarm[normal_f & su_f].mean() if (normal_f & su_f).any() else 0.0
        det = sum(
            any((da_f.index >= e["start"]) & (da_f.index <= e["failure"]) & combined) for e in eps
        )
        has = "있음" if band_thr[dom] is not None else "없음(gate)"
        print(f"  {dom:<10}{steady_far:>8.1%}{startup_far:>9.1%}{f'{det}/{len(eps)}':>9}  {has}")

    # ── 4) 운영점 sweep: caution 분위를 바꾸며 overall 검출 vs FAR(정상 운전 구간) ───
    #    임계 = train 정상(기동 제외) 점수의 분위. 같은 분위를 모든 voting 도메인에 적용해
    #    overall(OR) 검출률과 정상 FAR을 추적한다. 기동 FAR은 별도 레버라 여기선 정상 구간만.
    print("\n=== [운영점] caution 분위 sweep — overall(정상 운전 구간) ===")
    print(f"  {'분위':>6}{'overall검출':>12}{'정상FAR':>10}{'평균lead':>10}{'  (도메인별 정상FAR)':<22}")
    base_steady = normal_f & ~su_f                      # FAR 분모: 정상·비기동 윈도우
    for p in SWEEP_PCTS:
        thr_p = {d: float(np.percentile(train_mse[d][~su_clean], p)) for d in voting}
        # overall 알람(OR): 어느 voting 도메인이든 임계 초과면 알람
        alarm_any = np.zeros(len(da_f), dtype=bool)
        per_dom_far = {}
        for d in voting:
            a = held_mse[d] >= thr_p[d]
            alarm_any |= a
            per_dom_far[d] = a[base_steady].mean() if base_steady.any() else 0.0
        far = alarm_any[base_steady].mean() if base_steady.any() else 0.0
        # 검출 + lead-time: 임계를 높이면 신호가 더 커진 뒤에야 알람 → 경고가 늦어지는(lead↓) trade-off 확인
        det, leads = 0, []
        for e in eps:
            win = da_f.index[(da_f.index >= e["start"]) & (da_f.index <= e["failure"]) & alarm_any]
            if len(win):
                det += 1
                leads.append((e["failure"] - win.min()).total_seconds() / 3600.0)
        avg_lead = float(np.mean(leads)) if leads else 0.0
        dom_str = " ".join(f"{d[:4]}{per_dom_far[d]:.0%}" for d in voting)
        star = "  <- 현재 정본(P99)" if abs(p - 99.0) < 1e-6 else ""
        print(f"  P{p:<5}{f'{det}/{len(eps)}':>12}{far:>9.1%}{avg_lead:>9.1f}h   {dom_str:<20}{star}")

    print("\n해석:")
    print("  - 검출 만점(N/N) 유지하며 분위↑ → FAR↓(검출 손실 없는 무료 튜닝). 단 lead-time이 줄면 경고가 늦어지는 비용.")
    print("  - 특정 도메인 정상FAR이 유독 높으면: 그 도메인이 FAR 주범 → 그 도메인만 분위↑ 또는 피처 보강.")
    print("  - 기동FAR이 크면: 운영점(정상 구간) 튜닝으로 안 줄어듦 → 기동 band 일반화(재학습) 레버.")


if __name__ == "__main__":
    main()