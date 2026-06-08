"""
startup_strategy_eval.py — 기동(startup) 스파이크 처리 전략 비교 실험.

질문(사용자): 기동을 통째로 무시(현재)하면 '비정상 기동'(평소 90까지 튀던 게 그날 130)도
놓친다. 통째 게이트 대신 regime별 threshold('울퉁불퉁')로 가면 비정상 기동을 잡으면서
정상 기동 오탐은 얼마나 늘어나는가? 성능 버전 vs 논리 버전을 데이터로 비교한다.

방법: 점수(per-window 재구성 MSE)는 현재 모델로 한 번만 뽑고, '결정 전략'만 오프라인으로
갈아끼워 공정 비교한다(재학습 불필요). 비정상 기동은 기동 윈도우의 actionable 센서를
배수로 들어올려 생성한다.

전략:
  A 통째게이트(성능) : 기동 윈도우는 무조건 Normal.
  B regime band(논리): 기동 윈도우는 '기동용 band'(정상 기동 점수의 p99)로 판정.
  C 처리없음         : 기동에도 정상상태 threshold를 그대로 적용(왜 통째게이트가 생겼는지 확인용).

지표(기동 윈도우):
  - 정상기동 FAR : 정상 기동을 알람으로 잘못 띄운 비율(낮을수록 좋음).
  - 비정상기동 recall : 비정상 기동(배수 주입)을 잡은 비율(높을수록 좋음).

실행:
    cd fault_injection && python startup_strategy_eval.py
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sensor_fault_eval import load_domain, per_feature_error, window  # noqa: E402

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN_CSV = os.path.join(PROJECT, "data", "smartfarm_normal_train_v5.csv")
DOMAIN = "hydraulic"
BASELINE_ROWS = 43200
# 비정상 기동: 기동 윈도우의 압력(+모터전력)을 배수로 상승. 여러 강도로 스윕.
ELEV_FACTORS = [1.1, 1.2, 1.3, 1.5]
ELEV_COLS = {"discharge_pressure_kpa": 1.0, "motor_power_kw": 0.5}  # 값=배수기여(1.0=완전, 0.5=절반)


def main():
    model, scaler, features, steady_thr = load_domain(DOMAIN)

    raw = pd.read_csv(CLEAN_CSV, nrows=BASELINE_ROWS)
    raw["timestamp"] = pd.to_datetime(raw["timestamp"])
    raw = raw.set_index("timestamp")
    raw["anomaly_label"] = 0
    da = window(raw)

    if "is_startup_phase" not in da.columns:
        print("is_startup_phase 없음 — 중단")
        return
    su = da["is_startup_phase"].to_numpy() >= 0.5
    n_su = int(su.sum())

    # 1) 정상 점수
    _, mse = per_feature_error(da, model, scaler, features)
    normal_startup = mse[su]
    # 기동용 band = 정상 기동 점수의 p99 (regime threshold)
    startup_thr = float(np.percentile(normal_startup, 99))

    print(f"도메인={DOMAIN}, 기동 윈도우={n_su}개")
    print(f"  정상상태 threshold(caution, cfg) = {steady_thr:.5f}")
    print(f"  기동용 band(정상기동 p99)        = {startup_thr:.5f}")
    print(f"  정상 기동 점수 median/p99/max    = "
          f"{np.median(normal_startup):.5f} / {np.percentile(normal_startup,99):.5f} / {normal_startup.max():.5f}\n")

    # 전략 A: 통째 게이트 — 항상 Normal
    far_A, rec_A = 0.0, 0.0
    # 정상기동 FAR (A는 0, B/C는 band 대비)
    far_B = float((normal_startup >= startup_thr).mean())
    far_C = float((normal_startup >= steady_thr).mean())

    print(f"  {'전략':<20}{'정상기동 FAR':>12}", end="")
    for f in ELEV_FACTORS:
        print(f"{'recall@'+str(f):>11}", end="")
    print()

    # 2) 비정상 기동 생성(배수 스윕) + 각 전략 recall
    recalls = {"A": [], "B": [], "C": []}
    for f in ELEV_FACTORS:
        da_bad = da.copy()
        for col, share in ELEV_COLS.items():
            if col in da_bad.columns:
                factor = 1.0 + (f - 1.0) * share
                vals = da_bad[col].to_numpy(dtype=float).copy()
                vals[su] = vals[su] * factor
                da_bad[col] = vals
        _, mse_bad = per_feature_error(da_bad, model, scaler, features)
        bad_startup = mse_bad[su]
        recalls["A"].append(0.0)
        recalls["B"].append(float((bad_startup >= startup_thr).mean()))
        recalls["C"].append(float((bad_startup >= steady_thr).mean()))

    def line(name, far, recs):
        print(f"  {name:<20}{far:>12.3f}", end="")
        for r in recs:
            print(f"{r:>11.3f}", end="")
        print()

    line("A 통째게이트(성능)", far_A, recalls["A"])
    line("B regime band(논리)", far_B, recalls["B"])
    line("C 처리없음", far_C, recalls["C"])

    print("\n해석:")
    print("  - A: 정상기동 FAR 0이지만 비정상기동 recall도 0 — 비정상 기동을 통째로 놓침(현재 결함).")
    print("  - B: 작은 FAR로 비정상기동을 잡기 시작 — 강도가 셀수록 recall↑. '논리 버전'.")
    print("  - C: 정상상태 threshold를 기동에 적용 → 정상기동 FAR 폭증(왜 통째게이트가 생겼는지).")
    print("  → B가 A의 사각지대(비정상 기동)를 작은 FAR 비용으로 메우는지 수치로 판단.")


if __name__ == "__main__":
    main()
