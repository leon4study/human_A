"""
ph_trend_redundancy_sim.py — ph_trend_30을 '빼는' 근본 수정안을 검증한다.

[배경] nutrient는 pH를 3개 신호로 본다: mix_ph(레벨)·pid_error_ph(목표 대비 오차)·ph_trend_30(변화율).
이 중 ph_trend_30(diff)만 heavy-tail이라 외삽 폭발→FP를 일으킨다. mix_ph·pid_error_ph가 잘 정의돼
있으니, ph_trend_30이 '중복'이면 trim/clip 대신 아예 빼는 게 가장 깨끗한 근본 수정이다(재학습 필요).

[이 시뮬의 질문]
  Q1. ph_trend_30 vs pid_error_ph: 어느 쪽이 heavy-tail/외삽 문제인가(꼬리·OOD 비교).
  Q2. ph_trend_30을 채점에서 빼면(=빼고 재학습의 근사) trim 없이도 FP 잡히고 검출 유지되나?
      ※ 모델은 ph_trend_30을 입력으로 여전히 받으므로 '근사'다(진짜 제거는 재학습). 그래도
        점수 단계 효과는 본다. trim은 '동적으로 최대 1개'를 버리지만, 제거는 'ph_trend만 항상' 빼므로
        진짜 고장의 다른 신호를 더 온전히 남길 수 있다(검출이 trim보다 나을 수도).

실행:
    python fault_injection/ph_trend_redundancy_sim.py
"""
import os
import sys
import json

import joblib
import numpy as np
import pandas as pd
import tensorflow as tf
from scipy.stats import kurtosis

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT, "src"))

from operating_point_eval import startup_mask_of, FAULTY_CSV, MODELS_DIR  # noqa: E402
from preprocessing import step1_prepare_window_data                      # noqa: E402
from inference_core import reconstruction_score                          # noqa: E402

DOM = "nutrient"
TRAIN_CSV = os.path.join(PROJECT, "data", "smartfarm_normal_train_v5.csv")


def dist_stats(name, train_v, hold_v):
    """학습 대비 held-out의 꼬리·외삽 정도."""
    tmin, tmax = np.percentile(train_v, 0), np.percentile(train_v, 100)
    span = tmax - tmin if tmax > tmin else 1e-12
    # held-out가 학습 범위를 얼마나 벗어나나(스케일 공간 외삽 배수 근사)
    over = ((hold_v - tmin) / span)
    ood = float(np.percentile(np.abs(over), 99.9))           # 99.9분위 스케일 위치(1이면 경계)
    return {
        "name": name, "train_max": float(tmax), "hold_max": float(np.max(hold_v)),
        "hold/train_max": float(np.max(hold_v) / (abs(tmax) + 1e-12)),
        "kurtosis": float(kurtosis(hold_v)), "scaled_p99.9": ood,
    }


def main():
    cfg = json.load(open(os.path.join(MODELS_DIR, f"{DOM}_config.json"), encoding="utf-8"))
    model = tf.keras.models.load_model(os.path.join(MODELS_DIR, f"{DOM}_model.keras"))
    scaler = joblib.load(os.path.join(MODELS_DIR, f"{DOM}_scaler.pkl"))
    features = cfg["features"]
    caution = float(cfg["threshold_caution"])
    scoring = cfg.get("scoring_features") or features

    # held-out v2 (nut_flag로 nutrient 고장 표시)
    fr = pd.read_csv(FAULTY_CSV); fr["timestamp"] = pd.to_datetime(fr["timestamp"])
    fr = fr.set_index("timestamp")
    fr["nut_flag"] = fr["fault_mode"].astype(str).str.contains("nutrient").astype(float)
    da, _ = step1_prepare_window_data(fr, window_method="tumbling",
                                      target_cols=["anomaly_label", "nut_flag"])
    da = da.dropna()
    X = pd.DataFrame(index=da.index, columns=features, dtype=float)
    for f in features:
        X[f] = da[f].astype(float).values if f in da.columns else 0.0
    Xs = scaler.transform(X)
    pred = model.predict(Xs, batch_size=512, verbose=0)
    sq = (Xs - pred) ** 2

    y = (da["anomaly_label"].to_numpy() > 0.5).astype(int)
    su = startup_mask_of(da)
    normal = (y == 0) & (~su)
    nut_fault = (y == 1) & (da["nut_flag"].to_numpy() > 0.0)

    # ── Q1. ph_trend_30 vs pid_error_ph 꼬리/외삽 ───────────────────────────────────
    tr = pd.read_csv(TRAIN_CSV)
    tr["timestamp"] = pd.to_datetime(tr["timestamp"]); tr = tr.set_index("timestamp")
    tr["nut_flag"] = 0.0
    tda, _ = step1_prepare_window_data(tr, window_method="tumbling",
                                       target_cols=["anomaly_label", "nut_flag"])
    tda = tda.dropna()
    print("=== Q1. pH 신호별 꼬리/외삽 (held-out 정상 vs 학습) ===")
    print(f"  {'신호':<16}{'학습max':>10}{'held max':>10}{'held/학습배':>11}{'첨도':>9}{'스케일P99.9':>11}")
    for f in ["mix_ph", "pid_error_ph", "ph_trend_30"]:
        s = dist_stats(f, tda[f].to_numpy(), da[f].to_numpy()[normal])
        print(f"  {s['name']:<16}{s['train_max']:>10.4f}{s['hold_max']:>10.4f}"
              f"{s['hold/train_max']:>11.2f}{s['kurtosis']:>9.1f}{s['scaled_p99.9']:>11.2f}")

    # ── Q2. 채점에서 ph_trend_30 제거(근사) — 분리도/검출 ───────────────────────────
    def smask_of(drop=None):
        drop = drop or []
        return np.array([(f in set(scoring)) and (f not in drop) for f in features], dtype=bool)

    variants = [
        ("A 현재(전체, trim1)",       smask_of(),                 1),
        ("E ph_trend제거(trim0)",     smask_of(["ph_trend_30"]),  0),
        ("F 전체(trim0)=망가짐",      smask_of(),                 0),
    ]
    print("\n=== Q2. nutrient 점수 분리도 (정상P99.5 vs 막힘중앙, 분리도=막힘/정상) ===")
    print(f"  caution={caution:.5f}, 정상 {int(normal.sum())} / nutrient막힘 {int(nut_fault.sum())}\n")
    print(f"  {'변형':<22}{'정상P99.5':>11}{'막힘중앙':>11}{'분리도':>9}{'FP@caut':>9}{'검출@caut':>10}")
    for name, smask, trim in variants:
        s = reconstruction_score(sq, smask, trim_top=trim)
        n995 = float(np.percentile(s[normal], 99.5))
        fmed = float(np.median(s[nut_fault]))
        sep = fmed / n995 if n995 > 0 else float("inf")
        fp = float((s[normal] >= caution).mean())
        det = float((s[nut_fault] >= caution).mean())
        print(f"  {name:<22}{n995:>11.5f}{fmed:>11.5f}{sep:>8.0f}x{fp:>8.1%}{det:>10.1%}")

    print("\n해석:")
    print("  - Q1: ph_trend_30만 held/학습배·첨도·스케일P99.9가 크면 → 외삽 문제는 ph_trend_30 단독.")
    print("        mix_ph·pid_error_ph가 얌전하면 → pH 신호는 그 둘로 충분히 잡힘(중복 가능성).")
    print("  - Q2: E(ph_trend제거)의 분리도/검출이 A(현재 trim)와 비슷하거나 좋으면 → ph_trend_30은")
    print("        빼도 되는(중복) 신호 → 재학습으로 아예 제거가 trim보다 깨끗한 근본 수정.")


if __name__ == "__main__":
    main()