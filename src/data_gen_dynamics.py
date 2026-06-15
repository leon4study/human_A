"""
data_gen_dynamics.py — 현실적 '동역학' 데이터 생성기 (Phase R, topic/10-realistic-datagen).

[왜 새 파일인가]
data_gen_jun.py(기존, 보존)는 대부분의 센서를 'setpoint + 독립 잡음'으로 만든다. 그래서 pH도
사실상 상수(5.80) + 백색잡음이라, 그 추세(diff)가 노이즈가 되는 문제가 있었다(docs/modeling/14).
여기서는 '상태가 시간에 따라 누적되는 동역학'으로 바꿔, 실제 양액 시스템처럼 값이 움직이게 한다.
data_gen_jun은 건드리지 않고 폴백/비교 기준으로 보존한다.

[레이어 계획 — 한 번에 다 넣지 않고 층층이 쌓아 각 층을 검증한다]
  L0 (이 파일의 현재 범위): 주간 산처리(세척) 사이클.
     - pH가 한 주에 걸쳐 서서히 염기(높은 pH)로 드리프트한다(양액에서 자연스러운 현상).
     - 주 1회 산처리(세척) 시 pH가 setpoint로 리셋되며, 그 순간 '산처리 스파이크'(투입 과도응답)가 난다.
     - 주기 위상 피처 days_since_cleaning을 노출 → 조건부 AE가 "위상 X에선 pH=Y가 정상"을 학습
       (지금 있는 일일 time_sin/cos의 '주간 버전'). 이게 있어야 feedforward AE가 주간 주기를 본다.
  L1 (예정): 월간 막힘(clog) 상태 누적 → 압력 완만 상승(염분 결정화·석출).
  L2 (예정): 주간 산처리가 막힘을 일부만 완화(순증) — 기존 simulate_degradation의 c*=0.97를 계승.
  L3 (예정): clog → pH 염기화 + 타 물리지표로 느린 전파(커플링).
  L4 (예정): 임계 초과 시 캐스케이드(와류 → 모터 진동 등 전체 요동, 비선형).

[기존 재사용] 7일 세척 스케줄(generate_schedules)·환경(simulate_environment)은 data_gen_jun에서 가져온다.

실행:
    python src/data_gen_dynamics.py        # 4주 샘플 생성 + pH 주간 사이클 플롯 저장
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 기존 생성기의 안정적인 부품을 재사용(중복 구현 방지). import 시 data_gen_jun의 전역 seed(42)도 고정된다.
from data_gen_jun import generate_schedules  # noqa: E402  (7일 세척 스케줄)

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PNG = os.path.join(PROJECT, "data", "evaluation_outputs", "datagen_L0_ph_cycle.png")

# ── pH 동역학 파라미터(L0) — 실제 양액 거동에 근거 ──────────────────────────────────
# 근거(원예 문헌·실무): 양액 최적 pH 5.5~6.5(스위트스폿 5.5~5.8). 순환식에서 pH는 시간이 지나며
# '상승(염기화)'한다 — 식물이 질산(NO3-)을 흡수하며 OH-를 방출하고, 보충수(pH 7.5~8)가 더해지기
# 때문. 또 낮 동안 광합성(조류·CO2 소비)으로 pH가 오르는 '일주기 변동'이 있다(onestopgrowshop·
# happyhydro). 그래서 — 주간 염기 드리프트(세척 사이 상승→산처리로 리셋) + 일주기 진동을 둔다.
# 합성이라 정확 복제가 아니라 '5.5~6.5 밴드 안에서 그럴듯한 변동'이 목표.
# [이전 문제] 기존 생성기는 pH=5.80+0.02·sin+N(0,0.012) → 범위 5.74~5.85(거의 상수). 일주기 0.02는
#   비현실적으로 작아, 변동을 근거값으로 상향한다(아래).
PH_SETPOINT = 5.80               # 산처리 직후 안정 pH(밴드 하단 5.5~5.8 부근)
PH_BASIC_DRIFT_PER_DAY = 0.05    # 평균 드리프트 +0.05/일 → 7일 +0.35 → 세척 직전 ≈ 6.15(밴드 안)
PH_BASIC_DRIFT_STD = 0.012       # 주(사이클)마다 기울기 랜덤(±) — 흡수율·보충수 변동으로 매주 동일하지 않음
PH_DAILY_AMP = 0.10              # 일주기 진폭(peak-to-peak ≈ 0.20) — 광합성·CO2 일변동(근거 상향)
PH_NOISE_STD = 0.02              # pH 센서 측정 잡음(현실적 수준; 이전 0.012보다 약간 큼)
ACID_SPIKE_DEPTH = 0.12          # 산처리 순간 과도 dip 깊이(산 투입 overshoot)
ACID_SPIKE_TAU_MIN = 20.0        # 그 dip가 가라앉는 시정수(분)

# ── 막힘(clog) 동역학 파라미터(L1) — data_gen_jun 계승 + 타임라인/가속 제어 ──────────
# 막힘은 양액 속 염분 결정화로 생긴다. 석출은 자가촉매적(석출핵 늘수록 빨라짐)이라 '가속형'이고,
# 주간 산처리로 일부만 완화돼(완전 해결 X) 조금씩 순증한다(사용자 시나리오). 물리지표(압력 등)는
# 크고 느리게 변한다. 압력 커플링 계수(174 + 15·clog + 18·blocked)는 data_gen_jun 공식 재사용.
CLOG_CAP = 0.40                  # 막힘 상한(정규화, data_gen_jun 계승)
CLOG_CASCADE_THRESHOLD = 0.30    # 이 위로 가면 캐스케이드(L4에서 전체 요동 발동)
CLOG_RELIEF_FACTOR = 0.97        # 세척 시 ×0.97 — 3%만 완화(부분, 완전 해결 X → 순증)
CLOG_RELIEF_COMP = 1.00          # 주간 부분완화 보정(1.0=무보정) — cascade_day에 clog≈임계가 되도록 튜닝
PRESS_STEADY_BASE = 174.0        # 정상 가동 차압(kPa, data_gen_jun)
PRESS_RESIDUAL = 45.0            # 펌프 정지 잔압(kPa)
PH_CLOG_COUPLING = 1.0           # L3: 막힘 누적 → pH 염기화(clog 1.0당 pH +1.0). clog 0.30(임계)서 +0.30 → 밴드 상단 초과

# ── L4 캐스케이드(데드헤드/재순환 cavitation) 파라미터 — 검색 근거 ──────────────────────
# clog가 임계 초과 → 작동점 shutoff 근처 → 데드헤드/재순환 cavitation. 하나의 드라이버로 여러 변수가
# 동시 거동(reasonable, 한 변수만 안 튐). cascade_intensity=clip((clog−임계)/(cap−임계),0,1)로 스케일.
# 근거: 데드헤드 수온 상승·재순환(Hayes Pump), 토출/재순환 cavitation 맥동 0~500Hz(Industrial Monitor·
# PMC6083716), 진동 ISO 10816 zone D>7.1(modeling/12 §8-3), 반경류 저유량서 동력·전류↓(Eng-Tips·
# Industrial Monitor). 모터전류는 방향 단정 회피로 '하락+erratic'.
FLOW_BASE = 30.0                 # 정상 유량(L/min, 대표값 — 통합 시 data_gen_jun과 맞춤)
FLOW_CLOG_DROP = 0.6             # 막힘 따라 유량↓(clog 1.0당 60% 감소)
VIB_BASE = 1.2                   # 정상 진동(mm/s, ISO 10816 zone A)
VIB_WEAR = 1.0                   # 점진 마모 진동↑(clog 비례)
VIB_CASCADE = 6.0                # 캐스케이드 진동 급증(intensity 1에서 +6 → zone D >7.1)
TEMP_BASE = 19.2                 # 정상 수온 base(℃, daylight 항 별도)
TEMP_CASCADE_RISE = 8.0          # 재순환 마찰열 수온 상승(℃, intensity 1에서 +8)
CUR_BASE = 5.0                   # 정상 모터 전류(A, 대표값)
CUR_CLOG_DROP = 0.15             # 막힘 따라 전류↓(반경류 동력곡선; clog 1.0당 15%↓)
PULSE_PRESS = 8.0                # 캐스케이드 토출압 맥동 RMS(kPa)
PULSE_FLOW = 4.0                 # 유량 맥동(L/min)
PULSE_VIB = 1.5                  # 진동 맥동(mm/s)
PULSE_CUR = 0.8                  # 전류 erratic 변동(A)


def minutes_since_cleaning(clean_flag):
    """각 시점의 '직전 세척 시작 이후 경과 분' = 주간 사이클 위상.

    세척이 시작되는 순간(0→1 전이)에서 0으로 리셋하고 1분씩 증가시킨다. 첫 세척 전 구간은
    데이터 시작(0)부터 누적한다. 생성은 1회성이라 명료한 루프로 둔다(벡터화 이득 작음).
    """
    n = len(clean_flag)
    onsets = set(np.where((clean_flag == 1) & (np.roll(clean_flag, 1) == 0))[0].tolist())
    out = np.zeros(n, dtype=float)
    cnt = 0
    for i in range(n):
        if i in onsets:
            cnt = 0            # 세척 시작 → 위상 리셋
        out[i] = cnt
        cnt += 1
    return out


def simulate_ph_dynamics(minute_of_day, clean_flag):
    """L0 pH 동역학 — 주간 염기 드리프트 + 산처리 리셋 + 과도 스파이크 + 일주기 + 잡음.

    [수식]
      days_since = (직전 세척 이후 경과)/1440  → 0(세척 직후)~7(다음 세척 직전)
      mix_ph = setpoint
             + basic_drift_per_day * days_since           # 주간 염기 드리프트(세척 시 0으로 리셋)
             + daily_amp * sin(2π·분/1440 + 1.1)           # 일주기
             + acid_spike                                  # 세척 시작 시 산투입 과도 dip(지수 감쇠)
             + N(0, noise_std)
    드리프트가 days_since에 비례하므로, 세척으로 days_since가 0이 되면 pH가 setpoint로 '리셋'된다.
    """
    n = len(clean_flag)
    msc = minutes_since_cleaning(clean_flag)
    days_since = msc / 1440.0
    onsets = np.where((clean_flag == 1) & (np.roll(clean_flag, 1) == 0))[0]

    # 사이클(세척 사이)마다 드리프트 기울기를 랜덤하게 → 주간 톱니 높이가 매주 다르다(흡수율·보충수
    # 변동). AE가 '한 패턴 암기'가 아니라 '주간 드리프트의 분포'를 배우게 한다(그래서 학습 기간도
    # 충분해야 함). 경계 [0, onset1, ..., n]의 각 구간에 N(mean, std) 기울기(음수 방지).
    bounds = [0] + list(onsets) + [n]
    drift_rate = np.empty(n)
    for k in range(len(bounds) - 1):
        rate = max(0.0, np.random.normal(PH_BASIC_DRIFT_PER_DAY, PH_BASIC_DRIFT_STD))
        drift_rate[bounds[k] : bounds[k + 1]] = rate

    # 산처리 과도 스파이크: 세척 시작에서 급격한 dip 후 지수 감쇠(투입 overshoot 모사)
    acid_spike = np.zeros(n)
    for s in onsets:
        dur = min(int(6 * ACID_SPIKE_TAU_MIN), n - s)     # 시정수의 6배까지(거의 0으로 수렴)
        acid_spike[s : s + dur] += -ACID_SPIKE_DEPTH * np.exp(-np.arange(dur) / ACID_SPIKE_TAU_MIN)

    mix_ph = (
        PH_SETPOINT
        + drift_rate * days_since                          # 사이클마다 기울기 랜덤(매주 다름)
        + PH_DAILY_AMP * np.sin(2 * np.pi * minute_of_day / 1440 + 1.1)
        + acid_spike
        + np.random.normal(0, PH_NOISE_STD, n)
    )
    # 위상 피처(일 단위)와 산처리 이벤트 플래그를 함께 반환 — 조건부 AE 입력용
    days_since_cleaning = days_since
    acid_treatment_event = (clean_flag == 1).astype(int)
    return mix_ph, days_since_cleaning, acid_treatment_event


def simulate_clog(n, day_num, irr_mask, clean_flag, onset_day, cascade_day):
    """막힘(clog) 상태 누적 — onset_day부터 '가속형' 성장 + 세척 시 부분완화(순증), cap에서 포화.

    [가속형] 염분 결정화/석출은 자가촉매적(석출핵 늘수록 빨라짐) → 성장률을 경과일에 비례시켜
      (days_after/span) 초반 완만(조기검출 난이도)·후반 급증으로 만든다. 성장은 관개 중에만(irr_mask).
    [부분완화] 주간 산처리는 막힘을 3%만 제거(×0.97). 완전 해결이 안 돼 조금씩 순증한다.
    [타임라인] onset_day에 0, cascade_day 근처에서 임계(CLOG_CASCADE_THRESHOLD) 도달하도록 성장 보정.
      cascade_day 이후로도 계속 자라 cap(0.40)에서 포화 → L4에서 그 구간에 캐스케이드(전체 요동)를 얹는다.
    """
    span = max(1, cascade_day - onset_day)
    irr_min_per_day = 100.0   # 관개 5회×20분 = 하루 관개 분(성장은 관개 중에만)
    # 가속형(growth ∝ days_after/span) 누적이 cascade_day에 임계(CLOG_CASCADE_THRESHOLD) 도달하도록
    # 성장계수 G를 자동 보정한다. 누적 ≈ G·irr_min·span/2 = threshold → G = 2·threshold/(irr_min·span),
    # 세척 부분완화로 깎이는 만큼 ×CLOG_RELIEF_COMP. (span·threshold가 바뀌어도 자동 스케일 → 타임라인 무관.)
    G = CLOG_RELIEF_COMP * 2.0 * CLOG_CASCADE_THRESHOLD / (irr_min_per_day * span)
    clog = np.zeros(n)
    for i in range(1, n):
        if day_num[i] < onset_day:
            continue
        days_after = day_num[i] - onset_day
        growth = G * (days_after / span) * irr_mask[i]   # 경과일 비례 = 가속
        c = clog[i - 1] + growth
        if clean_flag[i] == 1 and clean_flag[i - 1] == 0:           # 세척 시작 → 부분완화
            c *= CLOG_RELIEF_FACTOR
        clog[i] = min(c, CLOG_CAP)
    return clog


def build(days=90, scenario="test", onset_day=14, cascade_day=82,
          start="2026-06-01 00:00:00", freq="1min"):
    """동역학 데이터셋 생성.
      scenario="train": clog=0 전 구간(순수 정상, AE 학습용 — 주간 사이클만).
      scenario="test" : onset_day부터 막힘 가속 누적(held-out 평가용 — 정상→막힘→캐스케이드 구간).
    L0(pH 동역학·위상) + L1(clog 누적·압력 커플링)을 포함. L3·L4(clog→pH 염기화·캐스케이드)는 예정.
    """
    idx = pd.date_range(start=start, periods=days * 24 * 60, freq=freq)
    n = len(idx)
    minute_of_day = (idx.hour * 60 + idx.minute).to_numpy()
    day_num = ((idx - idx[0]).total_seconds() / 86400).astype(int).to_numpy()

    irr_mask, clean_flag = generate_schedules(n, minute_of_day, days)
    mix_ph, days_since_cleaning, acid_event = simulate_ph_dynamics(minute_of_day, clean_flag)

    if scenario == "train":
        clog = np.zeros(n)
    else:
        clog = simulate_clog(n, day_num, irr_mask, clean_flag, onset_day, cascade_day)
    blocked_ratio = np.clip((clog / CLOG_CAP) ** 1.5 * 0.45, 0, 1.0)  # data_gen_jun 계승(비선형)

    # L3: 막힘(염분 결정화) 누적 → pH 염기화. 주간 산처리가 pH는 낮춰도 막힘은 완전히 못 없애므로,
    # degradation 동안 pH 베이스라인(특히 세척 직후 바닥)이 서서히 올라간다 → nutrient 도메인이 감지.
    # train(clog=0)은 영향 없음. degradation 말기엔 pH가 밴드 상단(6.5)을 넘을 수 있다(=이상 신호).
    mix_ph = mix_ph + PH_CLOG_COUPLING * clog

    # 압력 커플링(L1, data_gen_jun 공식 재사용·간략): 펌프 가동(관개) 중 174+15·clog+18·blocked,
    # 정지 중 잔압 45. 잡음은 clog와 함께 커진다(막힐수록 변동↑). 펌프 가동은 관개 마스크로 근사.
    pump_on = (irr_mask > 0).astype(int)
    target = np.where(pump_on == 1,
                      PRESS_STEADY_BASE + 15 * clog + 18 * blocked_ratio,
                      PRESS_RESIDUAL)
    discharge_pressure = target + np.random.normal(0, 0.5 + 3.0 * clog, n) * pump_on

    # ── L4: 데드헤드/재순환 캐스케이드 — 임계 초과 시 여러 변수가 한 드라이버로 동시 거동 ──────
    # cascade_intensity: 임계 아래 0, cap에서 1(비선형 — 임계 위에서만 발동).
    cascade = np.clip((clog - CLOG_CASCADE_THRESHOLD) / (CLOG_CAP - CLOG_CASCADE_THRESHOLD), 0.0, 1.0)
    daylight = np.clip(np.sin(2 * np.pi * (minute_of_day - 360) / 1440), 0, None)  # 일주기(data_gen_jun 동일)
    # 유량: 막힘 따라 붕괴(↓) + 캐스케이드 erratic 맥동(가동 중만). 1분 샘플서 맥동은 RMS 포락선 근사.
    flow_rate = np.clip((FLOW_BASE * (1 - FLOW_CLOG_DROP * clog)
                         + PULSE_FLOW * cascade * np.random.normal(0, 1, n)) * pump_on, 0, None)
    # 토출압: L1 평균 위에 재순환 cavitation 맥동 추가(가동 중만).
    discharge_pressure = discharge_pressure + PULSE_PRESS * cascade * np.random.normal(0, 1, n) * pump_on
    # 진동: 점진 마모↑(clog) + 캐스케이드 급증(zone D >7.1) + 맥동.
    bearing_vibration = np.clip(VIB_BASE + VIB_WEAR * clog + VIB_CASCADE * cascade
                                + PULSE_VIB * cascade * np.random.normal(0, 1, n), 0, None)
    # 수온: 일주기 base + 재순환 마찰열 상승(데드헤드 핵심 증상).
    mix_temp = TEMP_BASE + 2.4 * daylight + TEMP_CASCADE_RISE * cascade + np.random.normal(0, 0.1, n)
    # 모터전류: 막힘 따라 하락(반경류 동력곡선 — 스파이크 아님) + 캐스케이드 erratic 변동.
    motor_current = np.clip((CUR_BASE * (1 - CUR_CLOG_DROP * clog)
                             + PULSE_CUR * cascade * np.random.normal(0, 1, n)) * pump_on, 0, None)

    return pd.DataFrame(
        {
            "timestamp": idx,
            "minute_of_day": minute_of_day,
            "day_num": day_num,
            "clean_flag": clean_flag,
            "pump_on": pump_on,
            "mix_ph": np.round(mix_ph, 3),
            "days_since_cleaning": np.round(days_since_cleaning, 4),
            "acid_treatment_event": acid_event,
            "clog": np.round(clog, 4),
            "blocked_ratio": np.round(blocked_ratio, 4),
            "cascade_intensity": np.round(cascade, 4),
            "discharge_pressure_kpa": np.round(discharge_pressure, 2),
            "flow_rate_l_min": np.round(flow_rate, 2),
            "bearing_vibration_rms_mm_s": np.round(bearing_vibration, 3),
            "mix_temp_c": np.round(mix_temp, 2),
            "motor_current_a": np.round(motor_current, 2),
        }
    ).set_index("timestamp")


def generate_full(scenario="test", days=90, onset_day=14, cascade_day=82,
                  start="2026-06-01 00:00:00", seed=None):
    """전체 컬럼(~50, 파이프라인 호환) 동역학 데이터셋 — data_gen_jun 커플링 재사용 + 동역학 주입 + L4.

    [방식] data_gen_jun에 clog_override·ph_override·current_dynamics를 넘겨 모든 센서 커플링
    (압력·진동·온도·EC·zone 등)을 그대로 재사용하고, L4 캐스케이드 맥동·온도상승만 여기서
    post-process로 얹는다(원본 data_gen_jun 무수정 보존).
      scenario="train": 정상(clog=0, 주간 사이클만). "test": 막힘 타임라인(onset~cascade)+캐스케이드.
    """
    from data_gen_jun import generate_smartfarm_final_v5  # 전체 컬럼 조립(커플링) — 지연 import

    idx = pd.date_range(start=start, periods=days * 24 * 60, freq="1min")
    n = len(idx)
    minute_of_day = (idx.hour * 60 + idx.minute).to_numpy()
    day_num = ((idx - idx[0]).total_seconds() / 86400).astype(int).to_numpy()
    irr_mask, clean_flag = generate_schedules(n, minute_of_day, days)
    pump_on = np.clip(irr_mask + clean_flag, 0, 1)            # data_gen_jun과 동일 정의

    # 동역학(L0 pH·L3 염기화) + 막힘 타임라인(L1) + 캐스케이드 강도(L4)
    mix_ph, days_since_cleaning, acid_event = simulate_ph_dynamics(minute_of_day, clean_flag)
    clog = (np.zeros(n) if scenario == "train"
            else simulate_clog(n, day_num, irr_mask, clean_flag, onset_day, cascade_day))
    mix_ph = mix_ph + PH_CLOG_COUPLING * clog                # L3: 막힘→pH 염기화
    cascade = np.clip((clog - CLOG_CASCADE_THRESHOLD) / (CLOG_CAP - CLOG_CASCADE_THRESHOLD), 0.0, 1.0)

    # 전체 컬럼 — data_gen_jun이 내 clog·pH로 모든 커플링 적용(전류·동력은 반경류 교정)
    df = generate_smartfarm_final_v5(start=start, days=days, seed=seed, degradation=False,
                                     clog_override=clog, ph_override=mix_ph, current_dynamics=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp")

    # L4 캐스케이드 post-process(가동 중만): 재순환 cavitation 맥동 + 마찰열 온도상승을 기존 컬럼 위에.
    def puls(amp):
        return amp * cascade * np.random.normal(0, 1, n) * pump_on
    df["discharge_pressure_kpa"] = np.round(df["discharge_pressure_kpa"].to_numpy() + puls(PULSE_PRESS), 2)
    df["flow_rate_l_min"] = np.round(np.clip(df["flow_rate_l_min"].to_numpy() + puls(PULSE_FLOW), 0, None), 2)
    df["motor_current_a"] = np.round(np.clip(df["motor_current_a"].to_numpy() + puls(PULSE_CUR), 0, None), 3)
    df["bearing_vibration_rms_mm_s"] = np.round(
        df["bearing_vibration_rms_mm_s"].to_numpy()
        + VIB_CASCADE * cascade + PULSE_VIB * cascade * np.random.normal(0, 1, n), 3)
    df["mix_temp_c"] = np.round(df["mix_temp_c"].to_numpy() + TEMP_CASCADE_RISE * cascade, 2)
    df["motor_temperature_c"] = np.round(df["motor_temperature_c"].to_numpy() + 0.6 * TEMP_CASCADE_RISE * cascade, 2)
    df["bearing_temperature_c"] = np.round(df["bearing_temperature_c"].to_numpy() + 0.5 * TEMP_CASCADE_RISE * cascade, 2)

    # 정상 운영 맥락(피처) — 정해진 세척 스케줄. 현장에도 있는 정보라 누수 아님.
    df["days_since_cleaning"] = np.round(days_since_cleaning, 4)
    df["acid_treatment_event"] = acid_event

    # ── 정답(truth) 컬럼 — 평가·시각화용. 정석(C): save_dataset에서 별도 파일로 분리해 학습 피처에
    #    절대 안 섞는다(누수 구조적 차단). 막힘 진행 = 고장 에피소드(onset부터 anomaly_label=1),
    #    캐스케이드(임계) 도달 = failure_time(예지보전 lead-time의 마감 시점).
    anomaly_label = (clog > 1e-9).astype(int)
    df["anomaly_label"] = anomaly_label
    df["fault_mode"] = np.where(anomaly_label == 1, "clog_degradation", "")
    df["fault_id"] = np.where(anomaly_label == 1, 0, -1)
    casc_on = int(np.argmax(cascade > 0)) if bool((cascade > 0).any()) else -1
    failure_time = np.array([np.datetime64("NaT")] * n, dtype="datetime64[ns]")
    if casc_on > 0:
        failure_time[anomaly_label == 1] = idx[casc_on].to_datetime64()
    df["failure_time"] = failure_time
    df["hidden_clog"] = np.round(clog, 4)
    df["hidden_cascade_intensity"] = np.round(cascade, 4)
    return df


# 정답(truth) 계열 — 피처 파일에서 분리할 컬럼. 현장에 없거나 정답을 직접 인코딩하는 것들.
TRUTH_COLS = [
    "anomaly_label", "fault_mode", "fault_id", "failure_time",
    "hidden_clog", "hidden_cascade_intensity", "hidden_tip_clog_level", "hidden_risk_stage",
]


def save_dataset(scenario, out_feature, out_truth, **kwargs):
    """generate_full을 피처/정답 두 파일로 분리 저장(정석 — 누수 구조적 차단).

    out_feature: 센서+운영맥락만(모델이 '보는' 것). out_truth: timestamp+정답(채점·시각화).
    둘 다 timestamp 인덱스라 평가·노트북에서 timestamp로 join한다. 데이콘/캐글의 train·test·solution 분리와 동일.
    """
    df = generate_full(scenario=scenario, **kwargs)
    truth_present = [c for c in TRUTH_COLS if c in df.columns]
    feat = df.drop(columns=truth_present)
    truth = df[truth_present]
    feat.to_csv(out_feature)
    truth.to_csv(out_truth)
    print(f"  {scenario}: 피처 {feat.shape} -> {out_feature}  |  정답 {truth.shape} -> {out_truth}")
    return feat, truth


def main():
    # 5개월안 검증: test 시나리오(60일) = lead-in 2주 + degradation ~5.5주 + 캐스케이드 1주.
    df = build(days=60, scenario="test", onset_day=14, cascade_day=53)
    on = df["pump_on"] == 1

    print("=== L1+L3 검증: test 60일 (onset day14 · cascade day53 — 5개월안 테스트 2개월) ===")
    ph_norm = df.loc[df["day_num"] < 14, "mix_ph"]
    print(f"  [L0] 정상구간(day<14) pH {ph_norm.min():.2f}~{ph_norm.max():.2f}, 밴드 5.5~6.5 "
          f"{'OK' if ph_norm.min() >= 5.5 and ph_norm.max() <= 6.5 else '이탈'}")
    c_casc = df.loc[df["day_num"] == 53, "clog"].max()
    print(f"  [L1 clog] day14 0 → cascade(day53) {c_casc:.3f}(임계 {CLOG_CASCADE_THRESHOLD}) → 말기 max {df['clog'].max():.3f}(cap {CLOG_CAP})")
    p_norm = df.loc[on & (df["day_num"] < 14), "discharge_pressure_kpa"].median()
    p_end = df.loc[on & (df["day_num"] >= 54), "discharge_pressure_kpa"].median()
    print(f"  [L1 압력] 차압(가동중) 정상 ~{p_norm:.0f} → 말기 ~{p_end:.0f} kPa (+{p_end - p_norm:.0f}, 막힘 따라 완만 상승)")
    # L3: 막힘 따라 pH 베이스라인(세척 직후 바닥) 상승(염기화)
    tr_early = df.loc[(df["day_num"] < 14) & (df["days_since_cleaning"] < 0.5), "mix_ph"].median()
    tr_late = df.loc[(df["day_num"] >= 45) & (df["days_since_cleaning"] < 0.5), "mix_ph"].median()
    print(f"  [L3 clog→pH] 세척직후 pH 바닥: 정상 ~{tr_early:.2f} → 말기 ~{tr_late:.2f} (+{tr_late - tr_early:.2f}, 염기화)")
    print(f"               pH 최대 {df['mix_ph'].max():.2f} (말기 밴드 6.5 초과 = 이상 신호; 정상구간은 밴드 내)")
    # L4: 캐스케이드 구간(day>=53) vs 정상(day<14) — 각 변수 방향(한 드라이버로 동시 거동 확인)
    nb = on & (df["day_num"] < 14)
    cb = on & (df["day_num"] >= 53)
    md = lambda col, m: df.loc[m, col].median()
    print(f"  [L4 캐스케이드] 정상 → 말기 (동시 거동, 한 변수만 안 튐):")
    print(f"    유량 {md('flow_rate_l_min', nb):.1f}→{md('flow_rate_l_min', cb):.1f} L/min (붕괴 ↓)")
    print(f"    진동 {md('bearing_vibration_rms_mm_s', nb):.2f}→{md('bearing_vibration_rms_mm_s', cb):.2f} mm/s (zone D 급증 ↑)")
    print(f"    수온 {md('mix_temp_c', nb):.1f}→{md('mix_temp_c', cb):.1f} ℃ (재순환 마찰열 ↑)")
    print(f"    전류 {md('motor_current_a', nb):.2f}→{md('motor_current_a', cb):.2f} A (반경류 하락 ↓, 스파이크 아님)")
    print(f"    토출압 std {df.loc[nb, 'discharge_pressure_kpa'].std():.1f}→{df.loc[cb, 'discharge_pressure_kpa'].std():.1f} kPa (맥동 ↑)")

    # ── 플롯 3패널: pH / clog·blocked / 차압(가동중 일평균) ──────────────────────────
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    for _f in ("AppleGothic", "Apple SD Gothic Neo", "NanumGothic"):
        try:
            plt.rcParams["font.family"] = _f
            break
        except Exception:
            continue
    plt.rcParams["axes.unicode_minus"] = False

    out_png = os.path.join(PROJECT, "data", "evaluation_outputs", "datagen_L4_cascade.png")
    t = df.index
    onset_t = df.index[df["day_num"] == 14][0]
    casc_t = df.index[df["day_num"] == 53][0]
    fig, ax = plt.subplots(3, 1, figsize=(13, 9), sharex=True)
    # ax0: pH(밴드)
    ax[0].plot(t, df["mix_ph"], color="#1f3b73", lw=0.5)
    ax[0].axhline(PH_SETPOINT, color="gray", ls=":", lw=0.8)
    ax[0].axhline(6.5, color="#c92a2a", ls=":", lw=0.8)
    ax[0].set_ylabel("pH")
    ax[0].set_title("L0~L4 (test 60일): 주간 pH 사이클 + 막힘 누적·pH 염기화 + 임계 초과 캐스케이드", fontsize=11)
    # ax1: clog + cascade_intensity(드라이버)
    ax[1].plot(t, df["clog"], color="#c92a2a", lw=1.0, label="clog")
    ax[1].plot(t, df["cascade_intensity"], color="#862e9c", lw=0.9, ls="--", label="cascade_intensity")
    ax[1].axhline(CLOG_CASCADE_THRESHOLD, color="gray", ls=":", lw=0.8, label=f"임계 {CLOG_CASCADE_THRESHOLD}")
    ax[1].set_ylabel("clog / intensity")
    ax[1].legend(loc="upper left", fontsize=8)
    # ax2: 캐스케이드 동시성 — 각 신호 일평균을 min-max 정규화([0,1]). day53서 함께 갈라짐(↑/↓).
    sigs = [("토출압", "discharge_pressure_kpa", "#c92a2a"),
            ("진동", "bearing_vibration_rms_mm_s", "#e8590c"),
            ("수온", "mix_temp_c", "#f08c00"),
            ("유량", "flow_rate_l_min", "#1971c2"),
            ("전류", "motor_current_a", "#2b8a3e")]
    for label, col, c in sigs:
        d = df.loc[on, col].resample("1D").mean()
        rng = d.max() - d.min()
        if rng > 0:
            ax[2].plot(d.index, (d.values - d.min()) / rng, color=c, lw=1.1, label=label)
    ax[2].set_ylabel("정규화[0,1]\n(가동중 일평균)")
    ax[2].set_xlabel("시간")
    ax[2].legend(loc="center left", fontsize=8, ncol=5)
    ax[2].set_title("L4 동시 거동: 압력·진동·수온 ↑ / 유량·전류 ↓ — 한 드라이버(데드헤드)로 day53서 함께", fontsize=10)
    for a in ax:
        a.axvline(onset_t, color="#1971c2", lw=0.9, alpha=0.5)   # 막힘 onset(day14)
        a.axvline(casc_t, color="#c92a2a", lw=0.9, alpha=0.6)    # 캐스케이드 시작(day53)
    fig.tight_layout()
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    fig.savefig(out_png, dpi=120)
    print(f"\n[plot] 저장: {out_png}")
    print("해석: day53(빨강) 임계 초과서 여러 신호가 '동시에'(압력·진동·수온↑, 유량·전류↓) 갈라지면 L4 성공.")
    print("      한 변수만 튀는 게 아니라 데드헤드/재순환 한 드라이버로 결합 → reasonable. 다음(통합): 전체 컬럼·재학습.")


if __name__ == "__main__":
    main()