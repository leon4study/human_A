"""
AE(오토인코더) 성능 평가용 labeled 테스트 데이터 생성 스크립트.

[목적]
- 학습 데이터와 분포는 유사하지만 다른 seed에서 나온 "보지 못한 데이터" 생성
- 각 행에 정답 라벨(anomaly_label, 0/1)을 부여 → precision/recall/ROC 산출 가능

[동작 흐름]
1) data_gen_dabin.py를 환경변수로 오버라이드해 다른 seed + 다른 출력 경로로 재실행
2) 생성된 CSV 로드
3) 월1(days 0~30)을 "정상" 기준으로 삼아 분단위(mod) 베이스라인 계산
4) composite z-score 계산 → 임계값으로 T/F 라벨
5) 라벨 포함 CSV 저장

[라벨링 로직 설계 근거]
composite z-score 방식을 택한 이유 — "간단하지만 논리 튼튼"의 기준:

 (1) 월1 baseline은 이미 검증된 정상 구간
     - 월1 평탄성(discharge ±0.03 kPa, flow ±0.03 L/min)은 사전 검증 완료
     - AE가 학습하는 분포와 동일한 전제 → 라벨과 모델 판정이 같은 세계관 공유

 (2) 다변량 z-score 평균 = AE의 재구성 오차와 철학 동일
     - AE는 여러 센서의 이탈을 합쳐 이상을 탐지
     - 라벨도 동일하게 "여러 센서의 이탈 평균"으로 정의해야 모델 성능을 공정히 평가
     - 단일 센서 기반 라벨이면 AE가 다른 센서 조합으로 잡은 이상이 false positive로 보임

 (3) 임계값 2.0은 통계적 표준
     - 정규분포 기준 2σ는 상/하위 각 ~2.3% (합쳐 ~4.6%)
     - 4개 센서 |z|의 평균이 2.0 초과하려면 평균적으로 모두 2σ 이상 이탈해야 함 → 엄격
     - composite_z_score 컬럼도 저장해 사후에 임계값 재선택 가능하게 함

 (4) per-minute-of-day baseline (mod별)
     - 일중 변동이 큼: 야간(pump off, residual 45 kPa) vs 주간(175 kPa)
     - 기동 오버슛(+4.5 kPa at 06:00~06:30)은 정상 패턴인데 global std로는 이상처럼 보임
     - mod(0~1439)별 mean/std를 계산 → 기동은 기동끼리, 정상 운전은 운전끼리 비교
     - 정상 일중 패턴은 z ≈ 0, 월2/월3 drift만 z 상승

 (5) cleaning_event_flag=1 행은 라벨 0으로 강제
     - 주간 산 세척은 정상 운영 루틴 (월1부터 매주 발생)
     - baseline 산출에서도 제외 → baseline이 "비세척 정상"을 순수하게 대표

 (6) 핵심 센서 4개 선택 근거 — 막힘의 전형 physical signature
     - discharge_pressure_kpa  : 막힘 → 토출 저항 ↑ → 압력 상승
     - flow_rate_l_min         : 같은 RPM에 유량 감소 (drop)
     - motor_current_a         : 부하 증가 → 전류 상승
     - bearing_vibration_rms_mm_s : 기계 스트레스/cavitation → 진동 상승
     → 4개 방향이 모두 다르지만 |z|를 쓰므로 부호 무관하게 이탈 크기만 반영
     → 평균으로 단일 센서 노이즈 spike의 false positive 완화

[참고: window-level 라벨]
행 단위 라벨 + preprocessing(5분 sliding window)에서 max aggregation을 쓰면
윈도우 라벨로 변환 가능. preprocessing.py에서 cleaning_event_flag와 같은 방식으로
anomaly_label, composite_z_score 컬럼을 phase/max 집계 대상에 추가하면 됨.
"""
import os
import runpy
from pathlib import Path

import numpy as np
import pandas as pd

# ── [Step 1] 테스트 데이터 생성: 학습 seed와 다른 seed로 data_gen_dabin.py 재실행 ──
# 학습 데이터 seed: 20260501 (data_gen_dabin.py 기본값)
# 테스트 데이터 seed: 43 — 학습과 다른 noise 패턴으로 AE가 "보지 못한 데이터"를 만든다.
TEST_SEED = "43"
TEST_OUT_PATH = "/Users/jun/GitStudy/human_A/data/generated_test_data_0420.csv"

os.environ["DABIN_SEED"] = TEST_SEED
os.environ["DABIN_OUT_PATH"] = TEST_OUT_PATH

print(f"[1/3] Generating test data (seed={TEST_SEED}) ...")
# runpy로 실행하면 data_gen_dabin.py 내부의 __name__ == "__main__" 가드가 없어도 OK
# (현재 해당 파일은 top-level script이므로 그대로 실행됨)
runpy.run_path(
    "/Users/jun/GitStudy/human_A/src/data_gen_dabin.py",
    run_name="__main__",
)

# 실행 후 env 정리 (이 스크립트를 import해서 재사용할 가능성 대비)
os.environ.pop("DABIN_SEED", None)
os.environ.pop("DABIN_OUT_PATH", None)

# ── [Step 2] 라벨링 대상 데이터 로드 + 타이밍 변수 재계산 ─────────────────────
print("[2/3] Loading generated data for labeling ...")
df = pd.read_csv(TEST_OUT_PATH, parse_dates=["timestamp"])

# days: 시뮬레이션 시작 시점으로부터의 경과일(소수점 포함) — 월 경계 판정용
days_arr = (
    (df["timestamp"] - df["timestamp"].min()).dt.total_seconds() / 86400.0
).to_numpy()
# mod: 하루 중 분 인덱스 (0~1439) — per-minute-of-day baseline lookup 키
mod_arr = (df["timestamp"].dt.hour * 60 + df["timestamp"].dt.minute).to_numpy()

# ── [Step 3] composite z-score 기반 라벨링 ────────────────────────────────────
# 막힘 검출에 쓸 핵심 센서 4종. 각 센서는 막힘 시 서로 다른 방향으로 움직이지만
# |z| 평균으로 보면 부호 무관하게 "정상에서 얼마나 멀리 갔는가"를 잴 수 있다.
KEY_SENSORS = [
    "discharge_pressure_kpa",       # 막힘 시 상승 (토출 저항 ↑)
    "flow_rate_l_min",              # 막힘 시 하강 (같은 RPM 대비 유량 ↓)
    "motor_current_a",              # 부하 증가로 상승
    "bearing_vibration_rms_mm_s",   # 기계 스트레스/cavitation으로 상승
]

# 3-1) baseline용 마스크: 월1(days < 30) AND 비세척(cleaning_event_flag == 0)
# - 월1은 검증된 평탄 구간, 비세척은 정상 운영만 추출하기 위함
clean_flag = df["cleaning_event_flag"].to_numpy()
ref_mask = (days_arr < 30) & (clean_flag == 0)

# 3-2) mod(0~1439)별로 센서 mean/std 집계 → 일중 패턴을 그대로 baseline에 반영
# - 예: mod=360 (06:00)은 startup overshoot 포함한 정상값을 대표하게 됨
ref_df = df.loc[ref_mask, KEY_SENSORS].copy()
ref_df["mod"] = mod_arr[ref_mask]

mu_by_mod = ref_df.groupby("mod")[KEY_SENSORS].mean()   # shape (1440, 4)
sig_by_mod = ref_df.groupby("mod")[KEY_SENSORS].std()   # shape (1440, 4)

# std == 0 인 분단위가 있으면 division by zero → 아주 작은 floor로 대체
# (실제로 template + gaussian noise이므로 std=0는 거의 발생하지 않지만 방어)
sig_by_mod = sig_by_mod.fillna(1e-3).clip(lower=1e-3)

# 3-3) 매 행의 mod에 해당하는 baseline mean/std를 가져와 z-score 계산
# reindex(mod_arr): 각 행의 mod 값으로 baseline 테이블을 조회 → (N, 4) 배열 생성
mu_row = mu_by_mod.reindex(mod_arr).values   # shape (N, 4)
sig_row = sig_by_mod.reindex(mod_arr).values  # shape (N, 4)
vals = df[KEY_SENSORS].values                 # shape (N, 4)

# |z| = |(값 - 분단위 평균)| / 분단위 표준편차
z = np.abs(vals - mu_row) / sig_row           # shape (N, 4)

# composite_z = 4개 센서의 |z| 평균. 단일 센서 noise spike에 덜 민감해진다.
composite_z = z.mean(axis=1)                  # shape (N,)
df["composite_z_score"] = composite_z.round(3)

# 3-4) 임계값 2.0으로 이진 라벨. 세척 창은 정상이므로 강제로 0으로 덮어쓴다.
label = (composite_z > 2.0).astype(int)
label[clean_flag == 1] = 0
df["anomaly_label"] = label

# ── [Step 4] 저장 + 검증 요약 출력 ────────────────────────────────────────────
df.to_csv(TEST_OUT_PATH, index=False, encoding="utf-8-sig")
print(f"[3/3] Saved labeled test data → {TEST_OUT_PATH}")
print(f"       rows={len(df)}, columns={df.shape[1]}")

# 월별 라벨 분포 및 평균 z-score:
# - 월1: 라벨율 <5% (정상 오탐 낮아야 함)
# - 월2: 중간 (sqrt 램프로 drift 시작)
# - 월3: 라벨율 >50% 기대 (smoothstep drift로 본격 이상)
m1 = days_arr < 30
m2 = (days_arr >= 30) & (days_arr < 60)
m3 = days_arr >= 60

print("\n[검증] 월별 라벨 분포 (기대: 월1 낮음, 월3 높음):")
print(f"{'month':>7} | {'rows':>6} | {'anomaly':>8} | {'rate':>6} | {'mean_z':>7}")
print("-" * 50)
for name, m in [("month1", m1), ("month2", m2), ("month3", m3)]:
    total = int(m.sum())
    anom = int(label[m].sum())
    rate = anom / total * 100 if total else 0.0
    zmean = float(composite_z[m].mean())
    print(f"{name:>7} | {total:>6} | {anom:>8} | {rate:>5.1f}% | {zmean:>7.3f}")
