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

    # 4) 특이도(specificity) — 정상 구간 오탐 + 기동 스파이크 영향 확인
    #    lead-time 100%가 '진짜 막힘 감지'인지(아무 편차에나 반응 아님)를 보려면
    #    정상 구간(고장 없음) 오탐률이 낮아야 하고, 특히 기동 구간이 오탐을 키우지 않아야 한다.
    print("\n=== 특이도: 정상 구간 오탐(FAR) + 기동 스파이크 영향 ===")
    al = df_agg["anomaly_label"].reindex(alarm.index).fillna(0).to_numpy()
    normal = al == 0
    fired = alarm.to_numpy() >= 1
    if "is_startup_phase" in df_agg.columns:
        su = (df_agg["is_startup_phase"].reindex(alarm.index).fillna(0).to_numpy() >= 0.5)
    elif "minutes_since_startup" in df_agg.columns:
        su = (df_agg["minutes_since_startup"].reindex(alarm.index).fillna(99).to_numpy() <= 5)
    else:
        su = np.zeros(len(alarm), dtype=bool)

    def _far(mask):
        m = normal & mask
        return (fired[m].mean() if m.sum() else 0.0), int(m.sum())

    far_all, n_all = _far(np.ones(len(alarm), dtype=bool))
    far_su, n_su = _far(su)
    far_nonsu, n_nonsu = _far(~su)
    print(f"  정상 전체 FAR: {far_all:.3f} ({int((normal).sum())} 윈도우)")
    print(f"  - 기동 구간 FAR:    {far_su:.3f} ({n_su} 윈도우)")
    print(f"  - 비기동 구간 FAR:  {far_nonsu:.3f} ({n_nonsu} 윈도우)")
    verdict = "양호(기동≈비기동)" if far_su <= far_nonsu + 0.02 else "기동 오탐 의심(기동>비기동)"
    print(f"  판정: {verdict}")


if __name__ == "__main__":
    main()
