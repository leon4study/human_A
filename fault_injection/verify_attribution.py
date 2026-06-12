"""
verify_attribution.py — "12/12 검출"이 진짜 도메인 반응인지, 우연한 baseline 교차인지 검증한다.

[의심]
plot_early_warning에서 nutrient 막힘 4건을 전부 motor가 책임도메인으로 잡았다. 그런데
fault_signatures의 nutrient_imbalance는 propagates_to=["nutrient"](양액 도메인에만 전파)이고
nutrient는 overall voting에서 제외된다. 그러면 voting 도메인(motor)이 nutrient 막힘을 잡는 건
물리적으로 이상하다 → motor의 '검출'이 fault 반응이 아니라 평소 주기적 baseline 교차가 우연히
fault 구간에 겹친 것(허위 검출)일 수 있다.

[검증]
  T1. 유형×도메인 검출표 — 각 막힘 유형(clog/suction/nutrient)을 어느 도메인이 실제로 잡나.
  T2. nutrient 자기검출 — nutrient 도메인 자신은 nutrient 막힘을 잡나(voting 제외라 안 보였을 뿐).
  T3. motor 허위검출 테스트 — nutrient 막힘 구간에서 motor 알람률 vs motor 평소(정상 윈도우)
      알람률. 둘이 비슷하면 motor는 fault에 반응한 게 아니라 평소대로 울린 것(=허위).

실행:
    cd fault_injection && python verify_attribution.py
"""
import os
import sys

import numpy as np
import pandas as pd

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT, "src"))

from evaluate_test_metrics import run_inference                 # noqa: E402
from operating_point_eval import window, startup_mask_of, FAULTY_CSV  # noqa: E402
from plot_early_warning import build_episodes                   # noqa: E402  (fid·start·failure·mode)


def main():
    fr = pd.read_csv(FAULTY_CSV)
    fr["timestamp"] = pd.to_datetime(fr["timestamp"])
    fr = fr.set_index("timestamp")
    da = window(fr)
    df_pred, domains, _ = run_inference(da)
    idx = da.index
    eps = build_episodes(fr)

    # 각 도메인 윈도우별 알람(level>=1)
    alarm = {d: (df_pred[f"{d}_level"].to_numpy() >= 1) for d in domains}

    # ── T1. 유형 × 도메인 검출표 ─────────────────────────────────────────────────────
    #    에피소드 [시작,고장] 안에서 그 도메인이 한 번이라도 알람했나.
    types = sorted(set(e["mode"] for e in eps))
    print("=== T1. 유형 × 도메인 검출표 (그 유형 막힘 중 도메인이 잡은 건수) ===")
    print(f"  {'유형':<26}{'건수':>5}  " + "".join(f"{d[:8]:>10}" for d in domains))
    for ty in types:
        sub = [e for e in eps if e["mode"] == ty]
        line = f"  {ty:<26}{len(sub):>5}  "
        for d in domains:
            cnt = sum(
                ((idx >= e["start"]) & (idx <= e["failure"]) & alarm[d]).any() for e in sub
            )
            line += f"{cnt:>10}"
        print(line)

    # ── T2. nutrient 자기검출 ────────────────────────────────────────────────────────
    nut_eps = [e for e in eps if e["mode"].startswith("nutrient")]
    if nut_eps and "nutrient" in domains:
        self_det = sum(
            ((idx >= e["start"]) & (idx <= e["failure"]) & alarm["nutrient"]).any() for e in nut_eps
        )
        print(f"\n=== T2. nutrient 자기검출 ===")
        print(f"  nutrient 도메인이 nutrient 막힘을 잡은 건수: {self_det}/{len(nut_eps)} "
              f"(voting 제외라 overall엔 안 보였을 뿐 — 자신은 잡아야 정상)")

    # ── T3. motor 허위검출 테스트 ────────────────────────────────────────────────────
    #    nutrient 막힘 구간의 motor 알람률 vs motor의 평소(정상·비기동) 알람률.
    y_true = da["anomaly_label"].astype(int).to_numpy()
    startup = startup_mask_of(da)
    base_normal = (y_true == 0) & (~startup)
    if nut_eps and "motor" in domains:
        in_fault = np.zeros(len(idx), dtype=bool)
        for e in nut_eps:
            in_fault |= (idx >= e["start"]) & (idx <= e["failure"])
        motor_rate_fault = alarm["motor"][in_fault].mean() if in_fault.any() else 0.0
        motor_rate_base = alarm["motor"][base_normal].mean() if base_normal.any() else 0.0
        print(f"\n=== T3. motor 허위검출 테스트 (nutrient 막힘 구간) ===")
        print(f"  motor 알람률 — nutrient 막힘 구간: {motor_rate_fault:.1%}  vs  평소 정상: {motor_rate_base:.1%}")
        ratio = motor_rate_fault / motor_rate_base if motor_rate_base > 0 else float("inf")
        print(f"  배수: {ratio:.1f}x")
        if ratio < 1.5:
            print("  >> 판정: 평소와 비슷 → motor는 fault에 반응한 게 아니라 평소대로 울림 = 허위검출 의심.")
            print("     => nutrient 막힘의 voting 검출은 사실상 우연. '12/12' 중 nutrient 4건은 재해석 필요.")
        else:
            print("  >> 판정: 막힘 구간에서 유의하게 높음 → motor가 실제로 반응(데이터 결합 등). 검출 유효.")


if __name__ == "__main__":
    main()