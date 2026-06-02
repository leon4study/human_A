"""
leadtime_eval.py — 현실적 고장 testset에서 '사전 감지 lead-time'을 측정.

docs/modeling/10 §5. 예지보전의 진짜 지표: 고장(failure_time)보다 얼마나 일찍 알람을 띄웠나.
각 고장 에피소드 [시작 → failure_time] 안에서 모델이 처음 알람을 띄운 시점을 찾아
  lead_time = failure_time - 첫 알람,  사전감지 = (failure_time 전에 알람 1건 이상)
을 집계한다.

현재 학습된 모델(models/)로 추론. AE는 정상으로 학습됐으니 막힘이 manifold를 벗어나면 잡힌다.

실행:
    cd fault_injection && python leadtime_eval.py
"""
import os
import sys

import numpy as np
import pandas as pd

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(PROJECT, "src")
sys.path.insert(0, SRC)

from preprocessing import step1_prepare_window_data          # noqa: E402
from evaluate_test_metrics import run_inference              # noqa: E402

FAULTY_CSV = os.path.join(PROJECT, "data", "faulty_testset_v1.csv")
CUTOFFS = [1, 2]   # 1=Caution 이상, 2=Warning 이상


def main():
    df_raw = pd.read_csv(FAULTY_CSV)
    df_raw["timestamp"] = pd.to_datetime(df_raw["timestamp"])
    df_raw["failure_time"] = pd.to_datetime(df_raw["failure_time"], errors="coerce")
    df_raw = df_raw.set_index("timestamp")

    # 1) 고장 에피소드: fault_id별 [시작, failure_time]
    episodes = []
    for fid in sorted(int(x) for x in df_raw.loc[df_raw["fault_id"] >= 0, "fault_id"].unique()):
        sub = df_raw[df_raw["fault_id"] == fid]
        fstart = sub.index.min()
        ftime = sub["failure_time"].dropna()
        ftime = ftime.iloc[0] if len(ftime) else None
        episodes.append({"fault_id": fid, "start": fstart, "failure": ftime})
    print(f"고장 에피소드 {len(episodes)}건 로드")

    # 2) 추론 (10분 윈도우 → 도메인별 알람 → overall). nutrient는 voting 제외(기존 운영).
    df_agg, _ = step1_prepare_window_data(
        df_raw, window_method="tumbling", target_cols=["anomaly_label"]
    )
    df_agg = df_agg.dropna()
    df_pred, domains, _ = run_inference(df_agg)
    alarm = df_pred["overall_alarm_level"]   # 10분 ts 인덱스

    # 3) 에피소드별 lead-time
    print("\n=== 사전 감지 lead-time (cutoff=알람 단계 기준) ===")
    for cutoff in CUTOFFS:
        rows, detected, leads = [], 0, []
        for ep in episodes:
            if ep["failure"] is None:
                continue
            win = alarm[(alarm.index >= ep["start"]) & (alarm.index <= ep["failure"]) & (alarm >= cutoff)]
            if len(win) > 0:
                first = win.index.min()
                lead_h = (ep["failure"] - first).total_seconds() / 3600.0
                detected += 1
                leads.append(lead_h)
                rows.append((ep["fault_id"], "감지", round(lead_h, 1)))
            else:
                rows.append((ep["fault_id"], "놓침", None))
        n = len([e for e in episodes if e["failure"] is not None])
        rate = detected / n if n else 0.0
        avg_lead = np.mean(leads) if leads else 0.0
        print(f"\n[cutoff>={cutoff}] 사전감지율 {detected}/{n} = {rate:.0%}, 평균 lead-time {avg_lead:.1f}h")
        print(f"  {'fault':>5} {'결과':<5} {'lead-time(h)':>12}")
        for fid, res, lead in rows:
            print(f"  {fid:>5} {res:<5} {('' if lead is None else lead):>12}")


if __name__ == "__main__":
    main()
