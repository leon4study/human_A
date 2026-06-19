"""
evaluate_dynamics_test.py — Phase R 동역학 test(피처/정답 분리본)로 학습 모델을 정직하게 평가.

[정석 누수 차단] 피처 파일에는 정답이 없다. 정답(anomaly_label·failure_time·hidden_clog)은
`_truth.csv`에서 timestamp로 join해 '평가에만' 쓴다(모델 입력으로는 절대 안 들어감).

[왜 recall 전체를 안 보나]
막힘(clog)은 onset(day15)부터 0에서 서서히 누적된다. 초반(clog≈0.01)은 물리적으로 노이즈에
묻혀 어떤 모델도 검출 불가다. 그래서 anomaly_label=1 전 구간 recall은 '초반 미검출' 때문에
낮은 게 정상이고, 그걸 성능 저하로 읽으면 안 된다. 예지보전의 정직한 지표는 두 가지다:
  1) 정상 구간 FAR — onset 전(주간 pH 사이클 포함) 오탐률. 위상 피처가 정상 드리프트를
     '정상'으로 흡수하는지의 직접 증거.
  2) lead-time — failure_time(실제 고장) 대비 '첫 지속 알람'이 얼마나 앞섰는지.

실행:
    cd /Users/jun/GitStudy/human_A/src && python evaluate_dynamics_test.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from preprocessing import step1_prepare_window_data  # noqa: E402
# run_inference/compute_metrics는 모델 무관(아티팩트만 읽음)이라 그대로 재사용한다.
from evaluate_test_metrics import run_inference  # noqa: E402

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEAT_CSV = os.path.join(PROJECT, "data", "smartfarm_dynamics_test.csv")
TRUTH_CSV = os.path.join(PROJECT, "data", "smartfarm_dynamics_test_truth.csv")

# 첫 알람을 '지속'으로 인정하는 최소 연속 윈도우 수(1분 해상도 → 30분).
# 단발 blip을 검출로 오인하지 않으려는 보수적 기준.
SUSTAIN_WINDOWS = 30


def first_sustained_alarm(levels: np.ndarray, index: pd.DatetimeIndex, k: int = SUSTAIN_WINDOWS):
    """level>=1이 k창 연속으로 처음 유지되는 시점을 반환(없으면 None)."""
    hit = (levels >= 1).astype(int)
    # 연속 길이 누적: run-length가 k에 도달하는 첫 위치
    run = 0
    for i, h in enumerate(hit):
        run = run + 1 if h else 0
        if run >= k:
            return index[i - k + 1]  # 지속 구간의 '시작' 시점
    return None


def main():
    # --- 1) 피처 + 정답 로드, timestamp로 join ---
    feat = pd.read_csv(FEAT_CSV, parse_dates=["timestamp"]).set_index("timestamp")
    truth = pd.read_csv(TRUTH_CSV, parse_dates=["timestamp"]).set_index("timestamp")

    # 정답을 피처 인덱스에 정렬해 붙인다(평가 전용). hidden_clog는 '검출 시 clog 수준' 보고용.
    feat["anomaly_label"] = truth["anomaly_label"].reindex(feat.index).fillna(0).astype(int)
    feat["hidden_clog"] = truth["hidden_clog"].reindex(feat.index).fillna(0.0)
    failure_time = (
        pd.to_datetime(truth["failure_time"].dropna().iloc[0])
        if truth["failure_time"].notna().any() else None
    )
    print(f"피처:{feat.shape} | 기간 {feat.index.min().date()}~{feat.index.max().date()} | failure_time={failure_time}")

    # --- 2) 윈도잉 (학습과 동일하게 sliding 5min — 임계치 비교가 정직하려면 윈도우 방식 일치) ---
    df_agg, _ = step1_prepare_window_data(
        feat, window_method="sliding",
        target_cols=["anomaly_label", "hidden_clog"],
    )
    df_agg = df_agg.dropna()
    y_true = df_agg["anomaly_label"].astype(int).to_numpy()
    clog = df_agg["hidden_clog"].to_numpy()
    idx = df_agg.index

    # --- [신중 모드] 위상피처 ablation: 인과 분리 + 서빙-0 시나리오 동시 검증 ---
    # 두 변화(현실 데이터 + 위상피처)를 동시에 줬으므로, FAR 개선이 무엇 덕인지 분리해야 한다.
    # 같은 학습 모델에 days_since_cleaning만 무력화해 추론하면, 모델이 그 피처에 '의존'하는지 본다.
    #   ABLATE_PHASE=zero    : 항상 0(세척 직후)으로 고정.
    #     = 서빙이 위상피처를 공급 못 하는 '망가진 시나리오'와 정확히 동일 -> 서빙 위험도 함께 측정.
    #   ABLATE_PHASE=mean    : 평균값 고정(정보 제거, 위치는 중앙).
    #   ABLATE_PHASE=shuffle : 무작위 셔플(분포 유지, 정보만 파괴) — '피처가 무의미'의 순수 대조.
    # 정상 FAR이 WITH 대비 튀어오르면 = 모델이 위상피처에 의존 = 위상피처가 인과적으로 FP를
    # 눌렀다는 증거(데이터 개선만의 효과가 아님). 안 변하면 = 데이터가 주역, 피처는 보조(정직 수정).
    ablate = os.environ.get("ABLATE_PHASE", "").strip().lower()
    if ablate and "days_since_cleaning" in df_agg.columns:
        _orig = df_agg["days_since_cleaning"]
        if ablate == "zero":
            df_agg["days_since_cleaning"] = 0.0
        elif ablate == "mean":
            df_agg["days_since_cleaning"] = float(_orig.mean())
        elif ablate == "shuffle":
            df_agg["days_since_cleaning"] = np.random.default_rng(42).permutation(_orig.to_numpy())
        else:
            print(f"[ABLATE_PHASE] 알 수 없는 값 '{ablate}' — 무시(zero/mean/shuffle 중 하나)")
        print(f"\n*** [ABLATE_PHASE={ablate}] 위상피처 무력화 모드 — WITH 결과의 nutrient FAR과 비교할 것 ***")
    else:
        print("\n[기준(WITH) 모드] 위상피처 정상 사용. 인과 비교는 ABLATE_PHASE=zero 로 재실행.")

    # --- 3) 도메인별 추론(학습된 아티팩트 로드) ---
    print("\n=== 추론 ===")
    df_pred, domains, thr_map = run_inference(df_agg)

    normal = (y_true == 0)   # onset 전 = 정상(주간 pH 사이클 포함)
    fault = (y_true == 1)    # onset 후 = 막힘 진행
    cols = domains + ["overall"]

    def lvl(dom):
        return df_pred["overall_alarm_level" if dom == "overall" else f"{dom}_level"].to_numpy()

    # === 4) 정상 구간 FAR (핵심: 위상 피처가 정상 드리프트에 FP 안 내는지) ===
    print(f"\n=== 정상 구간 FAR (n={int(normal.sum())} 윈도우, onset 전·주간 pH 사이클 포함) ===")
    print(f"  {'도메인':<10}{'FAR(≥1)':>10}{'FAR(≥2)':>10}{'FAR(≥3)':>10}")
    for dom in cols:
        L = lvl(dom)[normal]
        print(f"  {dom:<10}{(L>=1).mean():>10.4f}{(L>=2).mean():>10.4f}{(L>=3).mean():>10.4f}")

    # === 5) 검출 + lead-time (failure_time 대비) ===
    # [정직성] 정상구간(anomaly=0) 알람은 FP이므로 FAR로 따로 본다. lead-time은 '고장구간에서
    # 처음으로 지속 알람이 뜨는' 진짜 검출 시점으로만 잰다 → normal 구간 level을 0으로 눌러
    # FP 클러스터가 첫 알람으로 오염시키는 것을 차단.
    print(f"\n=== 첫 지속 알람({SUSTAIN_WINDOWS}창 연속, 고장구간 한정) + lead-time ===")
    print(f"  (정상구간 알람은 위 FAR로 별도 평가 — 여기선 onset 후 첫 '진짜' 검출만)")
    print(f"  {'도메인':<10}{'첫 지속알람':<22}{'lead-time':>14}{'그때 clog':>12}")
    for dom in cols:
        L = lvl(dom).copy()
        L[normal] = 0  # 정상구간 알람 제거(FP는 FAR로 평가) → 고장구간 첫 지속 알람만
        t0 = first_sustained_alarm(L, idx)
        if t0 is None:
            print(f"  {dom:<10}{'(없음)':<22}{'-':>14}{'-':>12}")
            continue
        lead = (failure_time - t0) if failure_time is not None else None
        clog_at = clog[idx.get_indexer([t0])[0]]
        lead_s = f"{lead.total_seconds()/86400:.1f}일 전" if lead is not None else "-"
        print(f"  {dom:<10}{str(t0):<22}{lead_s:>14}{clog_at:>12.3f}")

    # === 6) 고장 후기(failure 직전 7일) 검출률 — 의미있는 구간의 recall ===
    if failure_time is not None:
        late = fault & (idx >= failure_time - pd.Timedelta(days=7)) & (idx <= failure_time)
        print(f"\n=== 고장 후기(failure 직전 7일, n={int(late.sum())}) 검출률 ===")
        print(f"  {'도메인':<10}{'recall(≥1)':>12}{'recall(≥2)':>12}")
        for dom in cols:
            L = lvl(dom)[late]
            print(f"  {dom:<10}{(L>=1).mean():>12.4f}{(L>=2).mean():>12.4f}")

        # [정직성] 유량/전류 도메인(hydraulic·motor)은 펌프 ON일 때만 신호가 존재한다.
        # 펌프 OFF 윈도우(관수 사이 휴지)는 정상=고장 구분이 불가하므로 recall을 희석시킨다.
        # zone_drip(토양 EC/수분)은 펌프와 무관하게 연속 측정 → 후기 recall이 높은 게 정상.
        if "pump_on" in df_agg.columns:
            pon = df_agg["pump_on"].to_numpy() >= 0.5
            late_on = late & pon
            print(f"\n  [펌프 ON 한정, n={int(late_on.sum())}] — 유량/전류 도메인 정직 측정")
            print(f"  {'도메인':<10}{'recall(≥1)':>12}{'recall(≥2)':>12}")
            for dom in cols:
                L = lvl(dom)[late_on]
                print(f"  {dom:<10}{(L>=1).mean():>12.4f}{(L>=2).mean():>12.4f}")

    print("\n해석:")
    print("  - 정상 FAR이 낮으면(특히 nutrient) = 위상 피처가 정상 주간 pH 드리프트를 흡수 = 성공.")
    print("  - lead-time 양수(=failure 전 검출) + 후기 recall 높음 = 예지보전 유효.")
    print("  - 초반 clog≈0 미검출은 물리적 정상(노이즈에 묻힘) — 후기 recall로 본다.")


if __name__ == "__main__":
    main()
