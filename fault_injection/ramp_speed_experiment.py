"""
ramp_speed_experiment.py — 고장 진행 속도(램프)에 따라 검출/lead-time이 어떻게 변하는지 비교.

[질문]
지금 테스트셋의 막힘은 1~3일에 진행한다. 현실의 점진적 막힘(스케일·biofilm)은 주 단위라 더 느리다.
느린 막힘이면 lead-time이 길어질까? 그리고 느려도(기울기 작아도) 여전히 잡을까?

[설계 — 유형별 물리 기반 램프]
유형마다 현실 진행 속도가 다르므로 일괄로 늦추지 않는다(사용자 지적). nutrient(도징 오류)는 원래
빠르므로 거의 유지하고, clog(스케일/biofilm)·suction(스트레이너)만 현실적으로 늦춘다.

  유형                        현재     현실적      스트레스   (일)
  clog(scale/biofilm)        1~3      7~12       16~22
  suction(strainer)          1~3      3~6        8~12
  nutrient(dosing)           1~3      0.5~1.5    1~2

[측정]
각 변형 셋에서 유형별 (검출률, 평균 lead-time) + 전체 FAR. serve 동일 추론(run_inference).
램프를 sequential로 배치해 base 길이를 자동으로 맞춘다(긴 램프도 슬롯 부족 없이 들어가게).

실행:
    cd fault_injection && python ramp_speed_experiment.py
"""
import os
import sys

import numpy as np
import pandas as pd

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT, "src"))

from data_gen_jun import generate_smartfarm_final_v5          # noqa: E402
from inject import inject_fault                                # noqa: E402
from evaluate_test_metrics import run_inference                # noqa: E402
from operating_point_eval import window, startup_mask_of       # noqa: E402

TYPES = ["hydraulic_clog_downstream", "hydraulic_suction_blockage", "nutrient_imbalance"]
N_PER_TYPE = 2

# 유형 x 변형별 램프 범위(일). nutrient는 도징 오류라 빠른 게 현실 → 거의 유지.
RAMP_DAYS = {
    "현재":   {"hydraulic_clog_downstream": (1, 3),  "hydraulic_suction_blockage": (1, 3),  "nutrient_imbalance": (1, 3)},
    "현실적": {"hydraulic_clog_downstream": (7, 12), "hydraulic_suction_blockage": (3, 6),  "nutrient_imbalance": (0.5, 1.5)},
    "스트레스": {"hydraulic_clog_downstream": (16, 22), "hydraulic_suction_blockage": (8, 12), "nutrient_imbalance": (1, 2)},
}
GAP_MIN = 2 * 1440      # 에피소드 사이 간격(2일) — 서로 겹치지 않게
MARGIN_MIN = 2 * 1440   # 맨 앞 여유(2일)


def build_variant(variant, seed):
    """변형 하나의 라벨 테스트셋 생성(base 길이는 램프 합으로 자동 결정)."""
    rng = np.random.default_rng(seed)
    # 에피소드 목록(유형·램프·hold) 먼저 정하고, sequential 배치로 base 길이 산출
    specs = []
    for ty in TYPES:
        lo, hi = RAMP_DAYS[variant][ty]
        for _ in range(N_PER_TYPE):
            ramp = int(rng.uniform(lo, hi) * 1440)
            hold = int(rng.integers(120, 720))
            specs.append((ty, ramp, hold))
    rng.shuffle(specs)                         # 유형 순서 섞기
    placed, pos = [], MARGIN_MIN
    for (ty, ramp, hold) in specs:
        placed.append((ty, pos, ramp, hold))
        pos += ramp + hold + GAP_MIN
    base_days = int(np.ceil((pos + MARGIN_MIN) / 1440))

    df = generate_smartfarm_final_v5(days=base_days, degradation=False, seed=seed)
    df = df.drop(columns=[c for c in df.columns if c.startswith("hidden_")])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp")
    n = len(df)

    anomaly = np.zeros(n, dtype=int)
    fault_mode = np.array([""] * n, dtype=object)
    fault_id = np.full(n, -1, dtype=int)
    failure_time = np.array(["NaT"] * n, dtype="datetime64[ns]")
    episodes = []
    for k, (ty, start, ramp, hold) in enumerate(placed):
        sev = float(rng.uniform(0.85, 1.0))
        df, lab = inject_fault(df, ty, start_idx=start, ramp_len=ramp,
                               hold_len=hold, severity_max=sev, persist_after=False)
        active = lab["anomaly_label"].to_numpy().astype(bool)
        anomaly[active] = 1
        fault_mode[active] = ty
        fault_id[active] = k
        ft = lab["failure_time"].iloc[-1]
        if pd.notna(ft):
            failure_time[active] = np.datetime64(ft)
        episodes.append({"fid": k, "mode": ty, "start": df.index[start],
                         "failure": pd.Timestamp(ft) if pd.notna(ft) else None,
                         "ramp_days": round(ramp / 1440, 1)})
    df["anomaly_label"] = anomaly
    df["fault_mode"] = fault_mode
    df["fault_id"] = fault_id
    df["failure_time"] = failure_time
    return df, episodes, base_days


def measure(df, episodes):
    """serve 동일 추론으로 유형별 검출률·평균 lead + 전체 FAR + per-domain 검출(어느 센서군이 잡나)."""
    da = window(df)
    df_pred, domains, _ = run_inference(da)
    overall = df_pred["overall_alarm_level"].to_numpy() >= 1
    # 도메인별 알람(level>=1) — '어느 센서군이 이 고장을 잡나'(전조-센서 질문) 확인용
    dom_alarm = {dd: (df_pred[f"{dd}_level"].to_numpy() >= 1) for dd in domains}
    idx = da.index
    y = da["anomaly_label"].astype(int).to_numpy()
    su = startup_mask_of(da)
    far = overall[(y == 0) & (~su)].mean() if ((y == 0) & (~su)).any() else 0.0

    by_type = {}
    for e in episodes:
        if e["failure"] is None:
            continue
        in_ep = (idx >= e["start"]) & (idx <= e["failure"])      # 이 막힘의 [시작, 고장] 구간
        seg = in_ep & overall
        det = bool(seg.any())
        lead = (e["failure"] - idx[seg].min()).total_seconds() / 3600.0 if det else None
        d = by_type.setdefault(e["mode"], {"n": 0, "det": 0, "leads": [], "ramp": [], "dom": {}})
        d["n"] += 1
        d["ramp"].append(e["ramp_days"])
        if det:
            d["det"] += 1
            d["leads"].append(lead)
        for dd in domains:                                        # 어느 도메인이 이 구간에 알람했나
            if (in_ep & dom_alarm[dd]).any():
                d["dom"][dd] = d["dom"].get(dd, 0) + 1
    return by_type, far, domains


def main():
    short = {"hydraulic_clog_downstream": "clog", "hydraulic_suction_blockage": "suction",
             "nutrient_imbalance": "nutrient"}
    dshort = {"hydraulic": "hydr", "motor": "moto", "nutrient": "nutr", "zone_drip": "zone"}
    print("실험: 같은 모델·임계(운영점 P99.5)·고장 시그니처 고정, 고장 '진행 속도(ramp)'만 3수준으로 변경.")
    print("데이터: 변형마다 generate_smartfarm_final_v5로 정상 base 새로 생성 + inject_fault로 유형별 ramp 주입(정적 정상=drift 없음).\n")
    print(f"  {'변형':<8}{'유형':<10}{'램프(일)':>9}{'검출':>7}{'평균lead':>10}{'전체FAR':>9}  검출도메인(에피소드수)")
    for vi, variant in enumerate(["현재", "현실적", "스트레스"]):
        df, eps, base_days = build_variant(variant, seed=20260612 + vi)
        by_type, far, domains = measure(df, eps)
        for ty in TYPES:
            d = by_type.get(ty)
            if not d:
                continue
            ramp_avg = np.mean(d["ramp"])
            lead = f"{np.mean(d['leads']):.1f}h" if d["leads"] else "-"
            detstr = f"{d['det']}/{d['n']}"        # 중첩 f-string(백슬래시) 회피로 먼저 만든다
            dom_str = " ".join(f"{dshort.get(k, k)}{v}" for k, v in
                               sorted(d["dom"].items(), key=lambda kv: -kv[1]))
            print(f"  {variant:<8}{short[ty]:<10}{ramp_avg:>8.1f}일{detstr:>7}{lead:>10}{far:>8.1%}  {dom_str}")
        print()

    print("해석:")
    print("  - 램프가 느려질수록 평균 lead-time이 길어지면: '느린 현실 막힘 = 더 일찍 경보' 가설 확인.")
    print("  - 느린데도 검출이 유지되면: 작은 기울기에도 모델이 잡음(강건). 검출이 떨어지면: 너무 느린 전조는 놓침(한계).")
    print("  - 검출도메인 = 어느 센서군이 그 막힘을 잡나(전조-센서 질문). clog은 보통 hydraulic(압력/저항계)이 carry.")
    print("  - 정적 정상(drift 없음) 기준 best-case. 실제(drift 있음)에선 regime-aware 임계가 받쳐줘야 동일 성능.")


if __name__ == "__main__":
    main()