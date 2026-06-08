"""
build_faulty_testset.py — held-out 정상 base에 4가지 고장을 多에피소드로 주입한 '신뢰 평가셋'.

[왜 v2로 바꿨나 — 평가 신뢰성]
이전 v1은 (a) 고장이 hydraulic clog 한 종류, (b) base가 '학습셋의 앞 30일'이라 정상 구간이
학습과 겹쳤다(FAR이 낙관적). 튜닝·before/after를 이 위에서 재면 6에피소드·1고장에 과적합한다.
v2는 두 가지를 고친다:
  1. 4가지 고장 전부(hydraulic clog·motor bearing·hydraulic suction·nutrient) × 에피소드 4건씩 = 16건.
     → bearing/suction/nutrient 검출까지 평가(귀인 일반화 확인).
  2. base를 'seed가 다른 독립 정상 데이터'로 생성(학습=seed 42, 테스트=다른 seed). 같은 달력·환경
     regime(in-distribution)이되 노이즈열이 학습과 겹치지 않아 FAR이 정직하다.
  ※ 모델은 애초에 clog-free 정상만 학습 → 어떤 고장도 학습에 없으므로 '검출'은 항상 held-out이다.
    held-out base가 추가로 바로잡는 건 '정상 구간 FAR'의 낙관 편향이다.

재현성: base는 generate_smartfarm_final_v5(seed=TEST_SEED)로, 고장 배치는 default_rng(seed)로 결정적.

실행:
    cd fault_injection && python build_faulty_testset.py
"""
import os
import sys

import numpy as np
import pandas as pd

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT, "src"))

from data_gen_jun import generate_smartfarm_final_v5   # noqa: E402  (held-out base 생성에 재사용)
from inject import inject_fault                          # noqa: E402

OUT_CSV = os.path.join(PROJECT, "data", "faulty_testset_v2.csv")

# 학습셋은 seed=42. 테스트 base는 다른 seed로 '독립 노이즈열'을 만든다(학습과 정상 패턴이 겹치지 않게).
TEST_SEED = 20260608
# 4가지 고장을 고르게 섞는다(fault_signatures.FAULT_SIGNATURES의 4종). 슬롯마다 1건씩 순환 주입.
TEST_MODES = (
    "hydraulic_clog_downstream",   # 하류 막힘(유량↓·토출압↑) — 광역 전파, root=hydraulic
    "motor_bearing_wear",          # 베어링 마모(진동·베어링온도↑) — motor 국소(failure_time 없음=열화)
    "hydraulic_suction_blockage",  # 흡입 막힘(고진공·토출압↓) — root=hydraulic, motor 동반
    "nutrient_imbalance",          # A/B 도징 이상(EC·pH 드리프트) — nutrient 국소
)


def build(
    out_csv: str = OUT_CSV,
    n_faults: int = 16,                 # 4종 × 4에피소드
    modes: tuple = TEST_MODES,
    base_days: int = 60,                # 60일(86,400분) → 슬롯 5,400분으로 ramp+hold 여유
    test_seed: int = TEST_SEED,
    seed: int = 42,                     # 고장 배치(위치·강도) 난수
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    # ── held-out 정상 base 생성(독립 seed, clog-free) ─────────────────────────────
    df = generate_smartfarm_final_v5(days=base_days, degradation=False, seed=test_seed)
    df = df.drop(columns=[c for c in df.columns if c.startswith("hidden_")])  # 학습셋과 동일 포맷
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp")
    n = len(df)

    # 라벨 누적기 — 각 윈도우/행이 어떤 고장에 속하는지 기록
    anomaly = np.zeros(n, dtype=int)
    severity = np.zeros(n, dtype=float)
    fault_mode = np.array([""] * n, dtype=object)
    fault_id = np.full(n, -1, dtype=int)
    failure_time = np.array(["NaT"] * n, dtype="datetime64[ns]")

    # N개를 균등 슬롯에 1개씩, 슬롯 안에서 랜덤 위치(에피소드끼리 겹침 방지)
    slot = n // n_faults
    episodes = []
    for k in range(n_faults):
        mode = modes[k % len(modes)]
        ramp_len = int(rng.integers(1440, 4320))   # 누적 1~3일
        hold_len = int(rng.integers(120, 720))     # 고장 유지 2~12시간
        win = ramp_len + hold_len
        slot_start = k * slot
        max_off = max(slot - win - 60, 1)
        start = slot_start + int(rng.integers(0, max_off))
        sev = float(rng.uniform(0.8, 1.0))

        df, lab = inject_fault(
            df, mode, start_idx=start, ramp_len=ramp_len,
            hold_len=hold_len, severity_max=sev, persist_after=False,
        )

        active = lab["anomaly_label"].to_numpy().astype(bool)
        anomaly[active] = 1
        severity = np.maximum(severity, lab["degradation_severity"].to_numpy())
        fault_mode[active] = mode
        fault_id[active] = k
        ft = lab["failure_time"].iloc[-1]
        if pd.notna(ft):
            failure_time[active] = np.datetime64(ft)
        episodes.append((k, mode, df.index[start], ft, round(sev, 2)))

    out = df.copy()
    out["anomaly_label"] = anomaly
    out["degradation_severity"] = severity.round(4)
    out["fault_mode"] = fault_mode
    out["fault_id"] = fault_id
    out["failure_time"] = failure_time

    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    out.to_csv(out_csv, encoding="utf-8-sig")

    print(f"[build_faulty_testset] 저장: {out_csv}")
    print(f"  held-out base: {base_days}일(seed={test_seed}), rows={n}, 고장 {n_faults}건, anomaly 비율 {anomaly.mean():.3f}")
    # 고장 유형별 건수
    from collections import Counter
    cnt = Counter(m for _, m, _, _, _ in episodes)
    print(f"  유형별: " + ", ".join(f"{m.split('_')[0]}:{c}" for m, c in cnt.items()))
    print(f"  {'#':>2} {'mode':<26} {'시작':<20} {'고장시점':<20} sev")
    for k, mode, st, ft, sv in episodes:
        print(f"  {k:>2} {mode:<26} {str(st):<20} {str(ft):<20} {sv}")
    return out


if __name__ == "__main__":
    build()