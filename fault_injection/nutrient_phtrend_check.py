"""
nutrient_phtrend_check.py — ph_trend_30를 채점에서 빼면 nutrient FAR·검출이 어떻게 되나(제외 시뮬).

[결정 질문]
ph_trend_30가 헛알람의 99%를 일으킨다. 그런데 이 피처가 '실제 고장 검출'에도 기여한다면 그냥
빼면 검출이 약해진다. 그래서 빼기 전에: (1) ph_trend_30가 고장 구간에서도 신호를 담나(판별력),
(2) 빼고 임계를 다시 잡으면 nutrient FAR·검출이 어떻게 되나를 잰다(재학습 없이 채점 마스크만 변경).

데이터: held-out v2(검출·FAR) + train 정상(임계 재산출). 모델 동일, scoring 마스크만 ph 제거.

실행:
    cd fault_injection && python nutrient_phtrend_check.py
"""
import os
import sys
import json

import joblib
import numpy as np
import pandas as pd
import tensorflow as tf

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT, "src"))

from operating_point_eval import window, startup_mask_of, FAULTY_CSV, MODELS_DIR, CLEAN_CSV  # noqa: E402
from inference_core import actionable_feature_mask                                          # noqa: E402
from plot_early_warning import build_episodes                                               # noqa: E402

DOM = "nutrient"
PH = "ph_trend_30"
PCT = 99.5   # 운영점(정본과 동일 분위)


def main():
    cfg = json.load(open(os.path.join(MODELS_DIR, f"{DOM}_config.json"), encoding="utf-8"))
    model = tf.keras.models.load_model(os.path.join(MODELS_DIR, f"{DOM}_model.keras"))
    scaler = joblib.load(os.path.join(MODELS_DIR, f"{DOM}_scaler.pkl"))
    features = cfg["features"]
    scoring = cfg.get("scoring_features")
    mask = (np.array([f in set(scoring) for f in features], dtype=bool)
            if scoring else actionable_feature_mask(features))
    assert PH in features, f"{PH} 없음"
    ph_idx = features.index(PH)
    mask_ex = mask.copy()
    mask_ex[ph_idx] = False     # ph_trend_30 채점 제외 마스크

    def sqerr(da):
        X = pd.DataFrame(index=da.index, columns=features, dtype=float)
        for f in features:
            X[f] = da[f].astype(float).values if f in da.columns else 0.0
        Xs = scaler.transform(X)
        pred = model.predict(Xs, batch_size=512, verbose=0)
        return (Xs - pred) ** 2

    # ── train 정상: 임계 재산출(기동 제외, P99.5) ──────────────────────────────────
    cl = pd.read_csv(CLEAN_CSV); cl["timestamp"] = pd.to_datetime(cl["timestamp"])
    cl = cl.set_index("timestamp"); cl["anomaly_label"] = 0
    dac = window(cl); suc = startup_mask_of(dac)
    sqc = sqerr(dac)
    thr_cur = float(np.percentile(sqc[:, mask].mean(1)[~suc], PCT))
    thr_ex = float(np.percentile(sqc[:, mask_ex].mean(1)[~suc], PCT))

    # ── held-out v2: FAR + nutrient 검출 ───────────────────────────────────────────
    fr = pd.read_csv(FAULTY_CSV); fr["timestamp"] = pd.to_datetime(fr["timestamp"])
    fr = fr.set_index("timestamp")
    da = window(fr); su = startup_mask_of(da); y = da["anomaly_label"].astype(int).to_numpy()
    sq = sqerr(da)
    mse_cur = sq[:, mask].mean(1); mse_ex = sq[:, mask_ex].mean(1)
    normal_steady = (y == 0) & (~su)
    far_cur = (mse_cur[normal_steady] >= thr_cur).mean()
    far_ex = (mse_ex[normal_steady] >= thr_ex).mean()

    # nutrient 고장 윈도우에서 ph_trend_30의 판별력(고장 vs 정상 오차)
    fm = fr["fault_mode"].astype(str).reindex(da.index, method="ffill").fillna("").to_numpy()
    nutf = (fm == "nutrient_imbalance") & (y == 1)
    clean = normal_steady
    e_ph_f = sq[nutf, ph_idx].mean() if nutf.any() else 0.0
    e_ph_c = sq[clean, ph_idx].mean() if clean.any() else 0.0
    share_ph_fault = e_ph_f / (sq[nutf][:, mask].sum(1).mean() + 1e-12) if nutf.any() else 0.0

    # nutrient 에피소드 검출(도메인 점수 기준)
    eps = [e for e in build_episodes(fr) if e["mode"].startswith("nutrient")]
    def det(mse, thr):
        c = 0
        for e in eps:
            seg = (da.index >= e["start"]) & (da.index <= e["failure"]) & (mse >= thr)
            c += bool(seg.any())
        return c, len(eps)
    det_cur = det(mse_cur, thr_cur); det_ex = det(mse_ex, thr_ex)

    print(f"=== ph_trend_30 판별력(고장에도 신호를 담나) ===")
    print(f"  고장구간 ph 오차={e_ph_f:.4f}  vs  정상 ph 오차={e_ph_c:.4f}  (배수 {e_ph_f/(e_ph_c+1e-12):.0f})")
    print(f"  고장 MSE 중 ph 비중={share_ph_fault:.0%}  → 비중 크면 검출도 ph에 의존(빼면 손실), 작으면 안전")
    print(f"\n=== 제외 시뮬: nutrient FAR / 검출 (재학습 없이 채점마스크만 변경) ===")
    print(f"  {'구성':<18}{'caution임계':>12}{'정상FAR':>10}{'nutrient검출':>14}")
    print(f"  {'현재(ph 포함)':<18}{thr_cur:>12.6f}{far_cur:>9.1%}{f'{det_cur[0]}/{det_cur[1]}':>14}")
    print(f"  {'ph 제외':<18}{thr_ex:>12.6f}{far_ex:>9.1%}{f'{det_ex[0]}/{det_ex[1]}':>14}")
    print("\n해석: ph 제외 시 FAR이 크게 떨어지고 검출이 유지되면 → '제외'가 정답(가벼움).")
    print("      검출이 떨어지면 → ph가 신호도 담은 것 → robust화로 신호 보존 필요.")


if __name__ == "__main__":
    main()