"""
baseline_blockage_eval.py — 단일센서 임계값 baseline 대비 AE의 '막힘률(놓침률)' 측정.

[이 파일이 푸는 문제]
docs/DEVELOPMENT_ROADMAP.md §4 + docs/modeling/08 §2. 포트폴리오 발화 "단일 센서 임계값 baseline
대비 막힘률 10%→2%"의 '측정 로직'을 코드로 확보한다. 핵심은 숫자의 절대값이 아니라, 도메인이
인정하는 지표(막힘률)를 정의하고 baseline 대비 공정하게 비교했다는 사실 자체다.

[핵심 용어]
  - 막힘 사건(에피소드) = faulty_testset_v1의 fault_id별 [시작 → failure_time] 구간(현실적 하류 막힘).
  - 사전 감지            = 그 구간 안(= 고장 전)에 알람이 한 번이라도 떴는가.
  - 막힘률(놓침률)        = 사전 감지 못한 에피소드 / 전체 = 1 - 사전감지율.  (낮을수록 좋음)
  - lead-time            = 고장 시점보다 얼마나 일찍 알람을 띄웠나(시간). 예지보전의 진짜 가치.
  - FAR(오탐률)          = 정상 구간(anomaly_label==0)에서 알람이 잘못 뜬 비율.

[두 탐지기를 같은 라벨 testset에 적용해 공정 비교]
  - baseline : 단일 센서 임계값. 정상 분포 대비 |z-score|>3 인 센서가 '하나라도' 있으면 알람.
               (z-score = 정상 평균에서 표준편차의 몇 배만큼 떨어졌는가. 3이면 약 0.3%의 극단.)
  - AE       : 현재 4도메인 AutoEncoder. run_inference의 overall_alarm_level ≥ 1 이면 알람.

[주의] 지금은 현재 모델(PROJECT_ROOT/models)로 내는 '잠정' 수치다. 재학습(DOMAIN_ISOLATION·
기동 band) 후 다시 돌리면 '정본' 수치로 갱신된다. 에피소드 6건은 소표본이라 경향 확인용이다.

실행:
    cd fault_injection && python baseline_blockage_eval.py
"""
import os
import sys

import numpy as np
import pandas as pd

# 프로젝트 루트와 src 경로를 잡아, src의 전처리·평가 모듈을 그대로 재사용한다(중복 구현 방지).
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(PROJECT, "src")
sys.path.insert(0, SRC)

from preprocessing import step1_prepare_window_data          # noqa: E402  (윈도우 집계 = 학습/추론과 동일 파이프라인)
from evaluate_test_metrics import run_inference              # noqa: E402  (AE 추론 = 운영과 동일 경로, PROJECT_ROOT/models 사용)

CLEAN_CSV = os.path.join(PROJECT, "data", "generated_data_from_dabin_0420.csv")  # 정상(월1) 데이터 = baseline의 '정상 분포' 기준
FAULTY_CSV = os.path.join(PROJECT, "data", "faulty_testset_v1.csv")             # 막힘 6건이 주입된 라벨 testset
BASELINE_ROWS = 43200   # 월1(30일×1440분) 정상 구간만 사용해 평균·표준편차 산출
Z_CUT = 3.0             # 단일 센서 baseline의 민감도: |z|>3 (정상에서 매우 드문 값)이면 이상으로 본다

# 단일 센서 baseline이 감시할 '물리 센서' 목록. 시간/상태 컨텍스트나 라벨은 넣지 않는다
# (그것들은 이상 신호가 아니라 맥락 정보라서). 실제 존재하는 컬럼만 뒤에서 걸러 쓴다.
BASELINE_SENSORS = [
    "flow_rate_l_min", "discharge_pressure_kpa", "suction_pressure_kpa",
    "motor_current_a", "motor_power_kw", "pump_rpm",
    "bearing_vibration_rms_mm_s", "motor_temperature_c", "bearing_temperature_c",
    "mix_ec_ds_m", "mix_ph", "drain_ec_ds_m",
    "zone1_substrate_moisture_pct", "zone1_substrate_ec_ds_m",
]


def window(df_raw):
    """raw 1분 데이터를 10분 tumbling 윈도우로 집계한다(학습/추론과 동일하게 맞춰 공정 비교).
    anomaly_label은 평가 기준점이라 target_cols로 보존하고, NaN 행은 떨군다."""
    da, _ = step1_prepare_window_data(
        df_raw, window_method="tumbling", target_cols=["anomaly_label"]
    )
    return da.dropna()


def main():
    # ── 1) 정상 분포(평균 mu·표준편차 sd) 학습 — baseline의 z-score 기준선 ──────────────
    #    "정상일 때 각 센서가 보통 어느 범위인가"를 월1 정상 데이터에서 구한다.
    clean = pd.read_csv(CLEAN_CSV, nrows=BASELINE_ROWS)
    clean["timestamp"] = pd.to_datetime(clean["timestamp"])
    clean = clean.set_index("timestamp")
    clean["anomaly_label"] = 0                      # 정상 데이터이므로 라벨 0(윈도우 함수 통과용)
    da_clean = window(clean)
    sensors = [s for s in BASELINE_SENSORS if s in da_clean.columns]   # 실제 존재하는 센서만
    mu = da_clean[sensors].mean()                  # 센서별 정상 평균
    sd = da_clean[sensors].std().replace(0, np.nan)  # 센서별 정상 표준편차(0이면 나눗셈 폭발 방지로 NaN)
    print(f"baseline 감시 센서 {len(sensors)}개: {sensors}\n")

    # ── 2) 라벨 testset 로드 + 동일 윈도우 집계 ─────────────────────────────────────
    fr = pd.read_csv(FAULTY_CSV)
    fr["timestamp"] = pd.to_datetime(fr["timestamp"])
    fr["failure_time"] = pd.to_datetime(fr["failure_time"], errors="coerce")  # 고장 시점(없으면 NaT)
    fr = fr.set_index("timestamp")
    da = window(fr)

    # 막힘 에피소드 목록: fault_id별 [시작, 고장시점]. 원본(분 단위)에서 뽑는다(윈도우보다 정밀).
    episodes = []
    for fid in sorted(int(x) for x in fr.loc[fr["fault_id"] >= 0, "fault_id"].unique()):
        sub = fr[fr["fault_id"] == fid]            # 이 막힘 1건에 해당하는 행들
        ft = sub["failure_time"].dropna()
        episodes.append({"fid": fid,
                         "start": sub.index.min(),                       # 막힘 시작
                         "failure": ft.iloc[0] if len(ft) else None})    # 고장 도달 시점

    # ── 3) 두 탐지기의 '윈도우별 알람(0/1)' 산출 ────────────────────────────────────
    #    baseline: 각 센서를 z-score로 바꾼 뒤, 한 센서라도 |z|>3 이면 그 윈도우는 알람(1).
    #              z = (관측값 - 정상평균) / 정상표준편차.  abs로 위·아래 양방향 모두 본다.
    z = (da[sensors] - mu) / sd
    baseline_alarm = (z.abs() > Z_CUT).any(axis=1).astype(int)  # any(axis=1) = "센서 중 하나라도"
    baseline_alarm.index = da.index
    #    AE: 운영과 동일한 추론을 돌려 overall_alarm_level(0~3)을 받고, 1 이상이면 알람으로 본다.
    df_pred, _, _ = run_inference(da)
    ae_alarm = (df_pred["overall_alarm_level"] >= 1).astype(int)

    # ── 4) 에피소드별 사전 감지 / 막힘률 / lead-time 계산 ───────────────────────────
    def detect_rate(alarm):
        """한 탐지기의 알람 시계열을 받아 (감지한 에피소드 수, 전체 수, 평균 lead-time) 반환."""
        det = 0; n = 0; leads = []
        for ep in episodes:
            if ep["failure"] is None:              # 고장 시점이 없으면 lead-time 정의 불가 → 건너뜀
                continue
            n += 1
            # 이 막힘의 [시작, 고장] 구간에서 알람(>=1)이 뜬 윈도우만 추린다.
            win = alarm[(alarm.index >= ep["start"]) & (alarm.index <= ep["failure"]) & (alarm >= 1)]
            if len(win) > 0:                       # 고장 전에 한 번이라도 떴으면 '사전 감지 성공'
                det += 1
                first = win.index.min()            # 그중 가장 이른 알람 시각
                leads.append((ep["failure"] - first).total_seconds() / 3600.0)  # 고장까지 남은 시간(h)
        avg_lead = float(np.mean(leads)) if leads else 0.0
        return det, n, avg_lead

    # ── 5) FAR(오탐률) — 정상 구간(anomaly_label==0)에서 알람이 뜬 비율 ────────────────
    lab = da["anomaly_label"].to_numpy()
    normal = lab == 0                              # 막힘이 아닌 정상 윈도우 마스크
    def far(alarm):
        a = alarm.to_numpy()
        return float(a[normal].mean()) if normal.sum() else 0.0  # 정상 윈도우 중 알람 비율

    # ── 6) 결과 표 출력 ────────────────────────────────────────────────────────────
    print("=== 단일센서 baseline vs AE — 막힘 사전감지 / 막힘률 / lead-time / FAR ===\n")
    print(f"  {'탐지기':<14}{'사전감지':>10}{'막힘률':>9}{'평균 lead-time':>15}{'FAR':>10}")
    for name, alarm in [("baseline(z>3)", baseline_alarm), ("AE(4도메인)", ae_alarm)]:
        det, n, lead = detect_rate(alarm)
        miss = 1 - det / n if n else 0.0           # 막힘률 = 1 - 사전감지율
        print(f"  {name:<14}{f'{det}/{n}':>10}{miss:>8.0%}{lead:>13.1f}h{far(alarm):>10.3f}")

    print("\n해석:")
    print("  - 심한 막힘은 baseline·AE 둘 다 잡음(막힘률 동일) → 차이는 FAR(오탐)과 lead-time(얼마나 일찍).")
    print("  - AE FAR가 낮으면: 같은 검출에 헛알람↓ → 알람피로↓ → 실운영 막힘률↓로 이어지는 논거.")
    print("  - AE lead-time이 길면: 더 일찍 잡음 = 예지보전의 진짜 가치(정비 여유).")
    print(f"  - 에피소드 {len([e for e in episodes if e['failure']])}건(소표본) 잠정치. 재학습 후 재실행으로 정본화.")


if __name__ == "__main__":
    main()