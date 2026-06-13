"""
attribution_matrix.py — 전 4유형 x 4도메인 '귀인(어디서 문제인지) 정확성' 매트릭스.

[이 파일이 답하는 것 — 프로젝트 핵심 장점 검증]
"각 고장을 자기 소유주 도메인이 잡나? '어디서 문제'인지 올바로 역추적되나?"
각 고장 유형의 활성 구간에서 도메인별 알람률을, 평소(정상) 알람률과의 '배수'로 본다.
배수가 크면 그 도메인이 그 고장에 '진짜' 반응한 것, ~1이면 평소대로 울린 '허위'.
(배수 기준이라 에피소드가 길어도 우연 누적에 안 속는다 — caveat 자동 해소.)

[기대 소유주] fault_signatures.FAULT_SIGNATURES의 root_domain:
  clog->hydraulic, bearing->motor, suction->hydraulic, nutrient->nutrient.

[deployed RCA] 운영 RCA는 voting 도메인(nutrient 제외) 중 가장 크게 반응한 도메인을 원인으로
지목한다. 이게 소유주와 다르면 '오귀인'. nutrient는 voting 제외라, nutrient 고장이 voting 도메인의
허위 반응(motor)으로 오귀인되는지 직접 드러난다.

데이터: held-out v2(4유형 x 4에피소드, fault_mode 라벨). 모델/임계는 정본(운영점 P99.5).

실행:
    cd fault_injection && python attribution_matrix.py
"""
import os
import sys

import numpy as np
import pandas as pd

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT, "src"))

from evaluate_test_metrics import run_inference, EXCLUDE_FROM_OVERALL   # noqa: E402
from operating_point_eval import window, startup_mask_of, FAULTY_CSV    # noqa: E402
from fault_signatures import FAULT_SIGNATURES                           # noqa: E402

ROOT = {k: v["root_domain"] for k, v in FAULT_SIGNATURES.items()}       # 유형->기대 소유주
# 유형 짧은 이름(표 라벨용) — clog/suction이 둘 다 'hydraulic'으로 안 보이게 구분
TYPE_SHORT = {
    "hydraulic_clog_downstream": "clog",
    "motor_bearing_wear": "bearing",
    "hydraulic_suction_blockage": "suction",
    "nutrient_imbalance": "nutrient",
}
GENUINE = 1.5   # 배수 >= 1.5 면 '진짜 반응', 미만이면 '평소대로(허위)'


def main():
    fr = pd.read_csv(FAULTY_CSV)
    fr["timestamp"] = pd.to_datetime(fr["timestamp"])
    fr = fr.set_index("timestamp")
    da = window(fr)
    df_pred, domains, thr = run_inference(da)

    # 도메인별 알람(level>=1) + 점수여유(score/caution = 얼마나 세게 울렸나, RCA 지목용)
    alarm = {d: (df_pred[f"{d}_level"].to_numpy() >= 1) for d in domains}
    margin = {d: df_pred[f"{d}_score"].to_numpy() / max(thr[d]["caution"], 1e-12) for d in domains}

    y = da["anomaly_label"].astype(int).to_numpy()
    su = startup_mask_of(da)
    base = (y == 0) & (~su)
    base_rate = {d: alarm[d][base].mean() if base.any() else 0.0 for d in domains}

    # 평가셋에 실제 들어있는 유형(fault_mode), 윈도우로 가져오려면 da에 fault_mode가 있어야 함.
    # window()가 fault_mode를 떨궜으면 원본 분 단위에서 윈도우 시각으로 매핑.
    if "fault_mode" in da.columns:
        fm = da["fault_mode"].astype(str).to_numpy()
    else:
        # da 인덱스(10분)에 해당하는 fault_mode를 원본에서 근사 매핑(그 10분에 라벨 있으면 그 유형)
        fm_series = fr["fault_mode"].astype(str)
        fm = fm_series.reindex(da.index, method="ffill").fillna("").to_numpy()

    types = [t for t in pd.unique(fm) if t and t != "nan"]
    types = sorted(types, key=lambda t: list(FAULT_SIGNATURES).index(t) if t in FAULT_SIGNATURES else 99)

    short = {"hydraulic": "hydr", "motor": "moto", "nutrient": "nutr", "zone_drip": "zone"}
    dom_order = [d for d in ["hydraulic", "motor", "nutrient", "zone_drip"] if d in domains]
    voting = [d for d in dom_order if d not in EXCLUDE_FROM_OVERALL]

    print("배수 = (고장 구간 알람률) / (평소 알람률). >=1.5 진짜반응[*], ~1 허위. () 안은 소유주.\n")
    header = "  " + f"{'유형':<10}{'소유주':<10}" + "".join(f"{short[d]:>9}" for d in dom_order)
    print(header + f"{'RCA지목(voting)':>16}{'판정':>8}")
    for t in types:
        owner = ROOT.get(t, "?")
        fmask = (fm == t) & (y == 1)            # 그 유형의 고장 활성 윈도우
        if not fmask.any():
            continue
        cells = ""
        for d in dom_order:
            r = alarm[d][fmask].mean()
            ratio = r / base_rate[d] if base_rate[d] > 0 else (float("inf") if r > 0 else 0.0)
            star = "*" if ratio >= GENUINE else " "
            own = "(" if d == owner else " "
            cells += f"{own}{ratio:>6.1f}{star}"
        # deployed RCA: voting 도메인 중 점수여유 평균이 가장 큰 도메인
        rca = max(voting, key=lambda d: float(np.mean(margin[d][fmask])))
        verdict = "OK" if rca == owner else ("오귀인" if owner in dom_order else "—")
        print(f"  {TYPE_SHORT.get(t, t):<10}{short.get(owner, owner):<10}{cells}{short.get(rca, rca):>16}{verdict:>8}")

    print("\n해석:")
    print("  - 소유주 칸(괄호)에 [*]가 떠야 '자기 문제를 자기 도메인이 진짜 잡음'.")
    print("  - RCA지목 != 소유주 = '어디서 문제인지' 역추적이 틀림(오귀인).")
    print("  - nutrient는 voting 제외라, nutrient 고장의 RCA지목이 voting 도메인(motor 등)으로 새는지 확인.")


if __name__ == "__main__":
    main()