"""
recall_far_breakdown.py — held-out v2에서 (1) FAR을 기동/정상으로 쪼개고 (2) confusion matrix
(precision/recall/F1·놓침률)를 낸다. serve와 동일한 추론 경로(run_inference)를 쓴다.

[이 파일이 답하는 질문]
  Q1. "FAR 1.8%가 전부 기동(startup) spike에서 오나?" → 정상 윈도우를 기동/정상으로 나눠
      각각의 FAR과, '전체 헛알람 중 기동이 차지하는 비율'을 본다.
  Q2. "반대로 고장을 놓친 비율은? recall/precision은?" → 윈도우 단위 혼동행렬을 낸다.

[윈도우 단위 recall의 함정 — 같이 해석해야 함]
  막힘 에피소드는 [시작 → 고장]까지 서서히 진행한다. 초반(전조가 미미한 구간)은 label=1(고장)
  이지만 아직 신호가 약해 '안 울리는 게 정상'이다(너무 일찍 울리면 그게 오탐). 그래서 윈도우
  단위 recall은 구조적으로 낮게 나오고, 이건 '나쁨'이 아니다. 예지보전에서 의미 있는 지표는
  '에피소드를 고장 전에 한 번이라도 잡았나'(=에피소드 단위 검출, baseline_blockage_eval의 12/12)
  와 lead-time이다. 윈도우 recall은 참고로만 본다.

실행:
    cd fault_injection && python recall_far_breakdown.py
"""
import os
import sys

import numpy as np
import pandas as pd

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT, "src"))

from evaluate_test_metrics import run_inference                 # noqa: E402  (serve와 동일 추론·voting·기동 band)
from operating_point_eval import window, startup_mask_of, episodes_of, FAULTY_CSV  # noqa: E402


def main():
    # ── held-out v2 로드 + tumbling 윈도우(서빙과 동일) ─────────────────────────────
    fr = pd.read_csv(FAULTY_CSV)
    fr["timestamp"] = pd.to_datetime(fr["timestamp"])
    fr = fr.set_index("timestamp")
    da = window(fr)

    # serve와 동일한 알람: run_inference가 도메인 점수→레벨, 기동 band, voting(OR, nutrient 제외)까지 처리
    df_pred, domains, _ = run_inference(da)
    overall = df_pred["overall_alarm_level"].to_numpy()
    alarm = overall >= 1                                  # 윈도우별 알람(0/1)

    y_true = da["anomaly_label"].astype(int).to_numpy()   # 0=정상, 1=고장
    startup = startup_mask_of(da)                          # 기동 윈도우 마스크
    normal = y_true == 0
    fault = y_true == 1

    # ── Q1. FAR을 기동/정상으로 쪼개기 ───────────────────────────────────────────────
    FP = alarm & normal                                   # 헛알람(고장 아닌데 울림)
    n_norm = int(normal.sum())
    n_norm_su = int((normal & startup).sum())
    n_norm_st = int((normal & ~startup).sum())
    far_all = FP.sum() / max(n_norm, 1)
    far_su = (FP & startup).sum() / max(n_norm_su, 1)      # 기동 정상 윈도우 중 헛알람 비율
    far_st = (FP & ~startup).sum() / max(n_norm_st, 1)     # 정상 운전 윈도우 중 헛알람 비율
    fp_total = int(FP.sum())
    fp_su = int((FP & startup).sum())
    fp_st = int((FP & ~startup).sum())

    print("=== Q1. FAR(오탐) 기동 vs 정상 운전 분해 ===")
    print(f"  정상 윈도우 {n_norm}개 = 기동 {n_norm_su} + 정상운전 {n_norm_st}")
    print(f"  전체 FAR     : {far_all:.2%}  (헛알람 {fp_total}건)")
    print(f"  기동 FAR     : {far_su:.2%}  (헛알람 {fp_su}건 / 기동 {n_norm_su})")
    print(f"  정상운전 FAR : {far_st:.2%}  (헛알람 {fp_st}건 / 정상운전 {n_norm_st})")
    if fp_total:
        print(f"  >> 전체 헛알람 중 기동이 차지: {fp_su}/{fp_total} = {fp_su/fp_total:.0%}  "
              f"(정상운전 {fp_st/fp_total:.0%})")

    # ── Q2. 윈도우 단위 confusion matrix ─────────────────────────────────────────────
    TP = int((alarm & fault).sum())
    FN = int((~alarm & fault).sum())                      # 고장인데 안 울림(놓침)
    TN = int((~alarm & normal).sum())
    precision = TP / max(TP + fp_total, 1)
    recall = TP / max(TP + FN, 1)                          # 윈도우 단위(=1-놓침률)
    f1 = 2 * precision * recall / max(precision + recall, 1e-12)
    miss_rate = FN / max(int(fault.sum()), 1)

    print("\n=== Q2. 윈도우 단위 혼동행렬(overall, level>=1) ===")
    print(f"  고장 윈도우 {int(fault.sum())} / 정상 윈도우 {n_norm}")
    print(f"  TP={TP}  FP={fp_total}  FN={FN}  TN={TN}")
    print(f"  precision={precision:.3f}  recall(윈도우)={recall:.3f}  F1={f1:.3f}")
    print(f"  놓침률(고장 윈도우 중 안 울림) = {miss_rate:.2%}")

    # ── 에피소드 단위 검출(진짜 의미 있는 지표) — 윈도우 recall과 대비 ────────────────
    eps = episodes_of(fr)
    det = 0
    for e in eps:
        span = (da.index >= e["start"]) & (da.index <= e["failure"]) & alarm
        if span.any():
            det += 1
    print("\n=== 참고: 에피소드 단위 검출(예지보전의 실제 지표) ===")
    print(f"  막힘 {len(eps)}건 중 고장 전 사전감지 = {det}/{len(eps)}")
    print(f"  >> 윈도우 recall({recall:.2f})이 낮아 보여도, 에피소드는 {det}/{len(eps)} 잡음.")
    print(f"     이유: 막힘 초반(전조 미미)은 label=1이지만 '아직 안 울리는 게 정상'이라 윈도우 FN이 쌓임.")
    print(f"     예지보전은 '고장 전에 한 번이라도 잡고 충분한 lead-time 확보'가 목적 → 에피소드 검출이 맞는 잣대.")


if __name__ == "__main__":
    main()