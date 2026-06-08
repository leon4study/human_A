"""
build_faulty_testset.py — 정상 데이터에 현실적 고장 에피소드 N건을 주입해 라벨 test set 생성.

docs/modeling/10_anomaly_signature_ledger.md §4. 각 고장은 '열화 ramp → 고장 → 정비 회복'의
유한 에피소드로, 서로 겹치지 않게 배치한다. 출력 CSV에는 모든 센서 컬럼(고장 주입됨) +
평가용 라벨(anomaly_label·degradation_severity·fault_mode·fault_id·failure_time)이 담긴다.

재현성: 고장 배치·파라미터는 np.random.default_rng(seed)로 결정적.

실행:
    cd fault_injection && python build_faulty_testset.py
"""
import os

import numpy as np
import pandas as pd

from inject import inject_fault

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN_CSV = os.path.join(PROJECT, "data", "generated_data_from_dabin_0420.csv")
OUT_CSV = os.path.join(PROJECT, "data", "faulty_testset_v1.csv")


def build(
    clean_csv: str = CLEAN_CSV,
    out_csv: str = OUT_CSV,
    n_faults: int = 6,
    modes: tuple = ("hydraulic_clog_downstream",),
    baseline_rows: int = 43200,   # 월1(정상) 30일 = 깨끗한 베이스라인
    seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    df = pd.read_csv(clean_csv, nrows=baseline_rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp")
    n = len(df)

    # 라벨 누적기
    anomaly = np.zeros(n, dtype=int)
    severity = np.zeros(n, dtype=float)
    fault_mode = np.array([""] * n, dtype=object)
    fault_id = np.full(n, -1, dtype=int)
    failure_time = np.array(["NaT"] * n, dtype="datetime64[ns]")

    # N개를 균등 슬롯에 1개씩, 슬롯 안에서 랜덤 위치(겹침 방지)
    slot = n // n_faults
    episodes = []
    for k in range(n_faults):
        mode = modes[k % len(modes)]
        ramp_len = int(rng.integers(1440, 5760))   # 누적 1~4일
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
    print(f"  rows={n}, 고장 {n_faults}건, anomaly 비율 {anomaly.mean():.3f}")
    print(f"  {'#':>2} {'mode':<26} {'시작':<20} {'고장시점':<20} sev")
    for k, mode, st, ft, sv in episodes:
        print(f"  {k:>2} {mode:<26} {str(st):<20} {str(ft):<20} {sv}")
    return out


if __name__ == "__main__":
    build()
