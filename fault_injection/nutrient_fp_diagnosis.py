"""
nutrient_fp_diagnosis.py — nutrient 도메인이 '왜 정상인데 과알람(FP)하나'를 국소화한다(수정안 C 1단계).

[배경]
nutrient는 FP 폭주(과거 EVAL FP의 94%)로 overall voting에서 제외돼 있다. 근본 수정(C)을 하려면
"어느 피처가, 어느 구간에서 헛알람을 일으키나"를 먼저 localize해야 한다(고칠 대상 특정).

[측정]
정상(고장 없는) 윈도우에서 nutrient 점수가 caution을 넘는 비율(FAR)과, 그 헛알람 윈도우에서
'어느 피처의 복원오차가 큰지'(= 그 피처를 AE가 정상인데도 잘 못 맞춤)를 분해한다. 헛알람 윈도우의
피처별 오차를 정상(비알람) 윈도우와 비교해, FP를 끌어올리는 주범 피처를 찾는다. 기동/정상도 분리.

데이터: held-out v2의 정상 윈도우(anomaly_label==0). 모델/임계는 정본(운영점 P99.5).

실행:
    cd fault_injection && python nutrient_fp_diagnosis.py
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

from operating_point_eval import window, startup_mask_of, FAULTY_CSV, MODELS_DIR  # noqa: E402
from inference_core import actionable_feature_mask                                # noqa: E402

DOM = "nutrient"


def main():
    cfg = json.load(open(os.path.join(MODELS_DIR, f"{DOM}_config.json"), encoding="utf-8"))
    model = tf.keras.models.load_model(os.path.join(MODELS_DIR, f"{DOM}_model.keras"))
    scaler = joblib.load(os.path.join(MODELS_DIR, f"{DOM}_scaler.pkl"))
    features = cfg["features"]
    caution = float(cfg["threshold_caution"])
    scoring = cfg.get("scoring_features")
    mask = (np.array([f in set(scoring) for f in features], dtype=bool)
            if scoring else actionable_feature_mask(features))

    fr = pd.read_csv(FAULTY_CSV)
    fr["timestamp"] = pd.to_datetime(fr["timestamp"])
    fr = fr.set_index("timestamp")
    da = window(fr)

    # nutrient 점수(scoring 피처 MSE) + per-feature 제곱오차 행렬
    X = pd.DataFrame(index=da.index, columns=features, dtype=float)
    for f in features:
        X[f] = da[f].astype(float).values if f in da.columns else 0.0
    Xs = scaler.transform(X)
    pred = model.predict(Xs, batch_size=512, verbose=0)
    sq = (Xs - pred) ** 2                      # (N, F) 스케일 공간 제곱오차
    mse = np.mean(sq[:, mask], axis=1)

    y = da["anomaly_label"].astype(int).to_numpy()
    su = startup_mask_of(da)
    normal = y == 0
    alarm = mse >= caution

    # ── FAR: 정상 / 기동 분리 ────────────────────────────────────────────────────
    far_all = alarm[normal].mean() if normal.any() else 0.0
    far_st = alarm[normal & ~su].mean() if (normal & ~su).any() else 0.0
    far_su = alarm[normal & su].mean() if (normal & su).any() else 0.0
    print(f"nutrient caution 임계={caution:.6f}, scoring 피처 {int(mask.sum())}개")
    print(f"FAR(정상 전체)={far_all:.2%}  |  정상운전={far_st:.2%}  |  기동={far_su:.2%}\n")

    # ── 어느 피처가 헛알람을 끌어올리나 ─────────────────────────────────────────────
    #    FP 윈도우(정상인데 알람) vs 정상-비알람 윈도우의 피처별 평균 오차 비교.
    fp = normal & alarm & ~su                  # 정상운전 헛알람 윈도우
    clean = normal & ~alarm & ~su              # 정상운전 비알람 윈도우
    scoring_feats = [f for f, m in zip(features, mask) if m]
    rows = []
    for j, f in enumerate(features):
        if not mask[j]:
            continue
        e_fp = sq[fp, j].mean() if fp.any() else 0.0
        e_cl = sq[clean, j].mean() if clean.any() else 0.0
        share = e_fp / (sq[fp][:, mask].sum(axis=1).mean() + 1e-12) if fp.any() else 0.0  # FP MSE 중 비중
        ratio = e_fp / (e_cl + 1e-12)
        rows.append((f, e_fp, e_cl, ratio, share))
    rows.sort(key=lambda r: -r[1])             # FP 오차 큰 순

    print(f"FP 윈도우 {int(fp.sum())}개 — 헛알람을 끌어올리는 피처(오차 큰 순):")
    print(f"  {'피처':<28}{'FP오차':>10}{'정상오차':>10}{'배수':>7}{'FP비중':>8}")
    for f, e_fp, e_cl, ratio, share in rows[:8]:
        print(f"  {f:<28}{e_fp:>10.5f}{e_cl:>10.5f}{ratio:>6.1f}x{share:>7.0%}")

    print("\n해석:")
    print("  - FP오차가 크고 정상오차 대비 배수가 큰 피처 = AE가 정상인데도 못 맞춰 헛알람 유발(주범).")
    print("  - FP비중이 한두 피처에 쏠리면: 그 피처 제거/평활/파생대체로 근본수정 가능(작업 작음).")
    print("  - 여러 피처에 고르게 퍼지면: 모델 용량/학습 부족(작업 큼) — 그땐 분리(B)가 현실적.")


if __name__ == "__main__":
    main()