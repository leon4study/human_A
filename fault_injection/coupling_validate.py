"""
coupling_validate.py — Phase 1 측정 도구 검증 + 현재 모델 baseline.

docs/modeling/10 §3·§6. 일반화된 영향 모델(fault_signatures)이 의도대로 동작하는지,
그리고 현재 6/2 모델이 각 고장 위치를 어떻게 잡는지를 한 번에 측정한다.

각 고장 위치마다:
  (a) 데이터 레벨 ripple — 주입 후 어떤 센서가 가중치대로 움직였나. propagates_to(정답지)와
      대조해 '의도한 도메인으로 번지는가'를 확인.
  (b) 모델 baseline    — 현재 모델(PROJECT_ROOT/models, 6/2)을 faulty 데이터에 돌려, 고장
      구간에서 어느 도메인이 알람을 띄우나. root_domain을 잡는가 / 헛도메인이 켜지나.

이 baseline이 이후 피처·재학습 변경을 재는 고정 기준이 된다.

실행:
    cd fault_injection && python coupling_validate.py
"""
import os
import sys

import numpy as np
import pandas as pd

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(PROJECT, "src")
sys.path.insert(0, SRC)

from preprocessing import step1_prepare_window_data      # noqa: E402
from evaluate_test_metrics import run_inference          # noqa: E402
from inject import inject_fault                           # noqa: E402
from fault_signatures import FAULT_SIGNATURES             # noqa: E402

CLEAN_CSV = os.path.join(PROJECT, "data", "generated_data_from_dabin_0420.csv")
BASELINE_ROWS = 43200
START = 20000
RAMP = 1440      # 24h 누적
HOLD = 720       # 12h 유지
REL_MOVE = 0.02  # 데이터 레벨: 2% 이상 변동을 'ripple'로 집계


def main():
    clean = pd.read_csv(CLEAN_CSV, nrows=BASELINE_ROWS)
    clean["timestamp"] = pd.to_datetime(clean["timestamp"])
    clean = clean.set_index("timestamp")

    for fault, sig in FAULT_SIGNATURES.items():
        print("\n" + "=" * 78)
        print(f"[{fault}]  root={sig['root_domain']}  기대 전파={sig['propagates_to']}")
        print(f"  {sig['description']}")

        base = clean.copy()
        faulty, lab = inject_fault(
            base, fault, start_idx=START, ramp_len=RAMP, hold_len=HOLD,
            severity_max=1.0, persist_after=False,
        )
        active = lab["anomaly_label"].to_numpy().astype(bool)
        ftime = lab["failure_time"].iloc[-1]

        # (a) 데이터 레벨 ripple — 고장 ON 구간에서 변동률 큰 센서
        print("  (a) 데이터 ripple (고장 구간 평균 변동률, |Δ|>2%):")
        moved = []
        for col in faulty.columns:
            o = clean[col].to_numpy(dtype=float)[active] if col in clean else None
            if o is None or not np.isfinite(o).all():
                continue
            f = faulty[col].to_numpy(dtype=float)[active]
            denom = np.mean(np.abs(o)) + 1e-9
            rel = np.mean(f - o) / denom
            if abs(rel) >= REL_MOVE:
                moved.append((col, rel))
        for col, rel in sorted(moved, key=lambda x: -abs(x[1]))[:12]:
            print(f"      {col:<30} {rel:+.1%}")
        print(f"      failure_time = {ftime}")

        # (b) 모델 baseline — 고장 구간에서 어느 도메인이 알람을 띄우나
        faulty["anomaly_label"] = active.astype(int)
        da, _ = step1_prepare_window_data(
            faulty, window_method="tumbling", target_cols=["anomaly_label"]
        )
        da = da.dropna()
        df_pred, domains, _ = run_inference(da)
        fmask = da["anomaly_label"].to_numpy() > 0
        print("  (b) 모델 baseline (고장 구간 도메인별 알람률 ≥Caution):")
        lit = []
        for dom in domains:
            rate = float((df_pred[f"{dom}_level"].to_numpy()[fmask] >= 1).mean()) if fmask.sum() else 0.0
            mark = ""
            if dom == sig["root_domain"]:
                mark = "  <- root"
            print(f"      {dom:<12} {rate:.2f}{mark}")
            if rate >= 0.3:
                lit.append(dom)
        # 판정
        root_ok = sig["root_domain"] in lit
        print(f"      => 켜진 도메인(≥0.3): {lit or '(없음)'} | root 검출: {'O' if root_ok else 'X'}")


if __name__ == "__main__":
    main()
