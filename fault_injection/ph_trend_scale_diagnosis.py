"""
ph_trend_scale_diagnosis.py — ph_trend_30의 복원오차 폭발이 '스케일 artifact'인지 '피처 자체'인지 가른다.

[가설] 2933배 폭발은 ph_trend_30의 정상 분포가 너무 좁은데 꼬리(극단)가 있어, MinMaxScaler가 학습
범위로 정규화한 뒤 held-out의 꼬리값이 [0,1] 밖으로 외삽(extrapolate)돼 스케일값이 거대해지고, AE가
그걸 못 맞춰 오차가 터지는 것 — 즉 스케일/외삽 artifact일 수 있다. 이걸 데이터로 확인한다.

[보는 것]
  - 원시 ph_trend_30 분포(분위·IQR·min/max)와 스케일러 '학습 범위'.
  - held-out 정상값이 학습 범위를 벗어나나(외삽 발생?).
  - FP 윈도우에서 ph_trend_30의 원시값/스케일값/복원값 — 스케일값이 [0,1] 밖으로 튀나.

[판정]
  - FP 원시값이 정상 범위 안인데 스케일값만 극단 → 스케일/외삽 artifact → A3(RobustScaler)·A2(클리핑).
  - FP 원시값 자체가 극단 outlier → 피처가 진짜 튐 → A4(재정의)·A2(클리핑).

데이터: held-out v2. 모델/스케일러는 정본(옛 ph_trend_30 = ph_roll_mean_30.diff()).

실행:
    cd fault_injection && python ph_trend_scale_diagnosis.py
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

DOM = "nutrient"
PH = "ph_trend_30"


def main():
    cfg = json.load(open(os.path.join(MODELS_DIR, f"{DOM}_config.json"), encoding="utf-8"))
    model = tf.keras.models.load_model(os.path.join(MODELS_DIR, f"{DOM}_model.keras"))
    scaler = joblib.load(os.path.join(MODELS_DIR, f"{DOM}_scaler.pkl"))
    features = cfg["features"]
    caution = float(cfg["threshold_caution"])
    ph_idx = features.index(PH)

    fr = pd.read_csv(FAULTY_CSV); fr["timestamp"] = pd.to_datetime(fr["timestamp"])
    fr = fr.set_index("timestamp")
    da = window(fr)
    X = pd.DataFrame(index=da.index, columns=features, dtype=float)
    for f in features:
        X[f] = da[f].astype(float).values if f in da.columns else 0.0
    Xs = scaler.transform(X)
    pred = model.predict(Xs, batch_size=512, verbose=0)
    sq = (Xs - pred) ** 2
    # 점수는 scoring 피처 평균이지만, 여기선 ph 한 피처에 집중하므로 caution과 직접 비교용으로
    # scoring MSE를 그대로 구한다(다른 진단과 동일).
    scoring = cfg.get("scoring_features") or features
    smask = np.array([f in set(scoring) for f in features], dtype=bool)
    mse = sq[:, smask].mean(1)

    raw_ph = X[PH].to_numpy()
    scaled_ph = Xs[:, ph_idx]
    pred_ph = pred[:, ph_idx]

    # 스케일러 학습 범위(MinMax면 data_min_/data_max_)
    dmin = float(getattr(scaler, "data_min_", [np.nan] * len(features))[ph_idx])
    dmax = float(getattr(scaler, "data_max_", [np.nan] * len(features))[ph_idx])

    y = da["anomaly_label"].astype(int).to_numpy()
    su = startup_mask_of(da)
    normal = (y == 0) & (~su)
    fp = normal & (mse >= caution)
    clean = normal & (mse < caution)

    def pct(a, ps=(0, 1, 50, 99, 99.9, 100)):
        return {p: float(np.percentile(a, p)) for p in ps}

    print(f"=== ph_trend_30 스케일/외삽 진단 (FP {int(fp.sum())} / 정상 {int(normal.sum())}) ===\n")
    print(f"스케일러 학습 범위(MinMax): [{dmin:.5f}, {dmax:.5f}]")
    pr = pct(raw_ph[normal])
    print(f"held-out 정상 원시 ph 분위: min={pr[0]:.5f} P1={pr[1]:.5f} P50={pr[50]:.5f} "
          f"P99={pr[99]:.5f} P99.9={pr[99.9]:.5f} max={pr[100]:.5f}")
    over = (raw_ph[normal] < dmin) | (raw_ph[normal] > dmax)
    print(f"  → 학습 범위를 벗어난 정상값: {int(over.sum())}/{int(normal.sum())} ({over.mean():.1%})  (외삽 발생 비율)\n")

    print(f"  {'구간':<8}{'원시ph(중앙)':>13}{'원시ph(P99)':>12}{'스케일ph(중앙)':>14}{'스케일ph(최대)':>14}{'복원ph(중앙)':>13}")
    for name, m in [("FP", fp), ("정상", clean)]:
        if not m.any():
            continue
        print(f"  {name:<8}{np.median(raw_ph[m]):>13.5f}{np.percentile(raw_ph[m],99):>12.5f}"
              f"{np.median(scaled_ph[m]):>14.3f}{scaled_ph[m].max():>14.3f}{np.median(pred_ph[m]):>13.3f}")

    print("\n해석:")
    print("  - 스케일ph가 [0,1]을 크게 벗어나면(예 2~3, 음수): MinMax 외삽 = 스케일 artifact → A3(RobustScaler)/A2(클리핑).")
    print("  - FP 원시ph가 정상 P99 안쪽인데 스케일만 튀면: 순수 스케일 문제. 원시값 자체가 극단이면: 피처 재정의(A4).")
    print("  - 학습범위 이탈 비율이 높으면: 분포 꼬리가 학습에 안 잡혀 held-out서 외삽 → 클리핑/robust 스케일이 직접 처방.")


if __name__ == "__main__":
    main()