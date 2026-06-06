import pandas as pd
import numpy as np
from pathlib import Path

# 난수 고정 및 출력 경로 설정
np.random.seed(42)
OUTPUT_DIR = Path("../data")  # 필요에 따라 경로 수정
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ==========================================
# 0. 센서 고유 독립 성분 헬퍼 (독립성 게이트 — docs/modeling/12)
# ==========================================
def ar1_process(n, sigma, phi=0.995, seed_offset=0):
    """
    센서마다 '그 센서만의 느린 독립 변동'을 만드는 1차 자기회귀(AR(1)) 과정.

    [왜 필요한가] 현재 데이터는 거의 모든 센서를 막힘강도(clog) 한 변수의 결정적 함수로 만들어,
    물리적으로 독립이어야 할 센서들(예: 진동 vs 압력)이 상관계수 ~1.00이 된다. 그러면 전처리의
    다중공선성 필터(corr>0.85)가 "중복"으로 제거해 학습 피처가 빈약해진다. 이 함수가 만드는
    '공유 드라이버와 무관한 고유 성분'을 각 센서에 더하면 그 인위적 상관이 깨진다(docs/modeling/12 §2-3).

    [수식] u[t] = phi*u[t-1] + e[t],  e ~ N(0, sigma).
      - phi(0~1): 1에 가까울수록 천천히 떠도는(random-walk에 가까운) 저주파 변동. 베어링 상태·센서
        드리프트처럼 서서히 변하는 물리량을 모사한다.
      - sigma: 고유 성분의 크기. 이 값을 키우면 다른 센서와의 상관이 내려간다(목표 상관 조절 손잡이).

    [재현성] 전역 np.random.seed와 별개로 default_rng(seed_offset)로 센서마다 독립 난수열을 쓴다.
      seed_offset을 센서별로 다르게 주어야 두 센서의 고유 성분이 서로 독립이 된다.
    """
    rng = np.random.default_rng(42 + seed_offset)
    e = rng.normal(0.0, sigma, n)        # 매 시점 새로 들어오는 충격(innovation)
    u = np.zeros(n)
    for t in range(1, n):
        u[t] = phi * u[t - 1] + e[t]     # 직전 값을 phi만큼 이어받아 '느린' 변동을 만든다
    return u


# ==========================================
# 1. 환경 변수 시뮬레이션 (Layer 0 — 공공데이터 딸기 앵커, docs/modeling/12 §0)
# ==========================================
def simulate_environment(n, minute_of_day):
    # daylight: 0(밤)~1(한낮)로 부드럽게 오르내리는 일주기. 오전 6시(360분) 기준 sin의 양수부만 사용.
    daylight = np.clip(
        np.sin(2 * np.pi * (minute_of_day - 360) / 1440), 0, None
    ).astype(float)

    # 기온: 공공데이터 딸기 개화·착과기 기준 — 주간 20~25℃ / 야간 7~10℃(야간 냉각).
    #   밤(daylight=0) ≈ 9℃, 한낮(daylight=1) ≈ 22.5℃ 가 되도록 baseline 9 + 진폭 13.5.
    #   (이전 값 21 + 7*daylight 는 야간 21℃로 딸기 야간(7~10℃)과 크게 어긋났음 → 공공데이터로 교정.)
    air_temp_c = (
        9.0
        + 13.5 * daylight
        + 0.8 * np.sin(2 * np.pi * minute_of_day / 1440 + 0.8)
        + np.random.normal(0, 0.35, n)
    )
    # 습도: 공공데이터 — 낮 60~70% / 밤 70~85%. 낮(daylight=1) ≈ 65%, 밤 ≈ 78%.
    relative_humidity_pct = np.clip(
        78
        - 13 * daylight
        + 2.2 * np.sin(2 * np.pi * minute_of_day / 1440 + 2.0)
        + np.random.normal(0, 1.0, n),
        55,
        90,
    )
    # CO2: 공공데이터 스마트팜 권장 800~1200 ppm. 밤엔 호흡으로 축적되어 높고(≈1150), 낮엔 광합성
    #   소비로 낮아짐(≈870). (이전 760 baseline은 권장 하한 800에도 못 미쳤음 → 교정.)
    co2_ppm = np.clip(
        1150 - 280 * daylight + np.random.normal(0, 15, n), 800, 1200
    )
    # 광량(PPFD): 공공데이터 권장 200~400 μmol/m²/s(일조 10~14h). 한낮 피크 ≈ 360.
    #   (이전 40 + 670*daylight 는 피크 710으로 권장(200~400)을 크게 초과 → 교정.)
    light_ppfd_umol_m2_s = np.clip(
        360 * daylight + np.random.normal(0, 15, n), 0, 420
    )

    return daylight, {
        "light_ppfd_umol_m2_s": np.round(light_ppfd_umol_m2_s, 2),
        "air_temp_c": np.round(air_temp_c, 2),
        "relative_humidity_pct": np.round(relative_humidity_pct, 2),
        "co2_ppm": np.round(co2_ppm, 2),
    }


# ==========================================
# 2. 관수 및 세척 스케줄 생성
# ==========================================
def generate_schedules(n, minute_of_day, days):
    irrigation_starts = np.array([6 * 60, 9 * 60, 12 * 60, 15 * 60, 18 * 60])
    irr_mask = np.zeros(n, dtype=float)
    for st in irrigation_starts:
        irr_mask += ((minute_of_day >= st) & (minute_of_day < st + 20)).astype(float)
    irr_mask = np.clip(irr_mask, 0, 1)

    clean_flag = np.zeros(n, dtype=int)
    for d in range(6, int(days), 7):
        start_min = d * 1440 + 120
        clean_flag[start_min : start_min + 30] = 1

    return irr_mask, clean_flag


# ==========================================
# 3. 배관 막힘(노후화) 및 세척 회복 시뮬레이션
# ==========================================
def simulate_degradation(n, day_num, irr_mask, clean_flag):
    clog = np.zeros(n, dtype=float)
    for i in range(1, n):
        if day_num[i] < 30:
            clog[i] = 0.0
        else:
            prev = clog[i - 1]
            days_after = day_num[i] - 30
            growth = (0.000003 + 0.000006 * (days_after / 30)) * irr_mask[i]
            c = prev + growth

            if clean_flag[i] == 1 and clean_flag[i - 1] == 0:
                c *= 0.97

            clog[i] = min(c, 0.40)

    blocked_ratio = np.clip((clog / 0.40) ** 1.5 * 0.45, 0, 1.0)

    cleaning_boost = np.zeros(n)
    clean_starts = np.where((clean_flag == 1) & (np.roll(clean_flag, 1) == 0))[0]
    for s in clean_starts:
        duration = min(18 * 60, n - s)
        decay = np.exp(-np.arange(duration) / (8 * 60))
        cleaning_boost[s : s + duration] += 1.2 * decay

    return clog, blocked_ratio, cleaning_boost


# ==========================================
# 4. 구역(Zone)별 분배 및 말단 센서 데이터
# ==========================================
def simulate_zone_data(
    n,
    minute_of_day,
    daylight,
    irr_mask,
    clog,
    blocked_ratio,
    flow_rate,
    cleaning_boost,
    pump_on,
):
    z_mult = {1: 0.82, 2: 1.00, 3: 1.18}
    zone_dict = {}

    for z in [1, 2, 3]:
        zc = np.clip(clog * z_mult[z], 0, 0.98)
        zblock = np.clip(blocked_ratio * z_mult[z], 0, 1.0)

        # 펌프 가동 시에만 유량과 동압력 발생 (잔압은 45 언저리로 가정)
        z_flow = (
            (flow_rate / 3) * (1 - 0.02 * (z - 2)) * (1 - 0.15 * zc - 0.20 * zblock)
            + np.random.normal(0, 0.12, n)
        ) * pump_on
        z_press_base = (
            86 + 5 * irr_mask + 8.0 * zc + 12.0 * zblock + np.random.normal(0, 0.65, n)
        ) * pump_on
        z_press = np.where(
            pump_on == 1, z_press_base, 35 + np.random.normal(0, 0.5, n)
        )  # 구역 잔압 반영

        z_moist = (
            61
            + 4.2 * irr_mask
            - 8.0 * zc
            - 10.0 * zblock
            + 0.8 * daylight
            + np.random.normal(0, 0.45, n)
        )
        z_ec = (
            2.08
            + 0.05 * daylight
            + 0.3 * zc
            + 0.4 * zblock
            + np.random.normal(0, 0.025, n)
        )
        z_ph = (
            5.82
            - 0.02 * zc
            + 0.02 * np.sin(2 * np.pi * minute_of_day / 1440 + z)
            + np.random.normal(0, 0.012, n)
        )

        zone_dict.update(
            {
                f"zone{z}_flow_l_min": np.round(np.clip(z_flow, 0, None), 2),
                f"zone{z}_pressure_kpa": np.round(np.clip(z_press, 0, None), 2),
                f"zone{z}_substrate_moisture_pct": np.round(
                    np.clip(z_moist, 20, 90), 2
                ),
                f"zone{z}_substrate_ec_ds_m": np.round(np.clip(z_ec, 1.2, 4.5), 3),
                f"zone{z}_substrate_ph": np.round(np.clip(z_ph, 5.2, 6.5), 3),
            }
        )
    return zone_dict


# ==========================================
# 5. [메인] 데이터 통합 파이프라인 (총 50개 컬럼 완벽 세팅)
# ==========================================
def generate_smartfarm_final_v5(start="2026-03-01 00:00:00", days=60, freq="1min"):
    idx = pd.date_range(start=start, periods=days * 24 * 60, freq=freq)
    n = len(idx)
    minute_of_day = idx.hour * 60 + idx.minute
    day_num = ((idx - idx[0]).total_seconds() / 86400.0).astype(float)

    irr_mask, clean_flag = generate_schedules(n, minute_of_day, days)
    daylight, env_data = simulate_environment(n, minute_of_day)
    clog, blocked_ratio, cleaning_boost = simulate_degradation(
        n, day_num, irr_mask, clean_flag
    )

    # 🚨 주야간 펌프 가동 여부
    pump_on = np.clip(irr_mask + clean_flag, 0, 1)

    # 유량 (펌프 켜졌을 때만 발생)
    flow_baseline = (
        78 + 2.0 * np.sin(2 * np.pi * minute_of_day / 1440 - 0.2)
    ) * pump_on
    delivery_eff = np.clip(1 - 0.04 * clog - 0.08 * blocked_ratio, 0.75, 1.0)
    flow_noise_std = (0.30 + 1.5 * clog) * pump_on
    flow_rate = (
        flow_baseline * delivery_eff
        + cleaning_boost
        + np.random.normal(0, flow_noise_std, n)
    ) * pump_on
    flow_rate = np.clip(flow_rate, 0, None)

    # 🚨 점적기 개폐 스파이크 및 잔압 반영 로직
    discharge_pressure = np.zeros(n)
    residual_p = 45.0  # 잔압 (대기 중 압력)
    steady_p_base = 174.0  # 운영 압력 (정상 가동 중)
    startup_spike_base = 210.0  # 초기 개폐 시 발생하는 피크 압력

    discharge_pressure[0] = residual_p
    for i in range(1, n):
        if pump_on[i] == 1 and pump_on[i - 1] == 0:  # 펌프 가동 순간
            target_p = startup_spike_base + (20 * clog[i])
            alpha = 0.9
        elif pump_on[i] == 1:  # 펌프 가동 중 (안정화)
            target_p = steady_p_base + 15 * clog[i] + 18 * blocked_ratio[i]
            alpha = 0.3 if discharge_pressure[i - 1] > target_p else 0.6
        else:  # 펌프 종료 (잔압 유지)
            target_p = residual_p
            alpha = 0.1

        discharge_pressure[i] = (
            alpha * target_p + (1 - alpha) * discharge_pressure[i - 1]
        )

    discharge_pressure += np.random.normal(0, 0.5 + 3.0 * clog, n) * pump_on
    discharge_pressure = np.clip(discharge_pressure, 0, None)

    # 흡입압: 앞서 독립 노이즈를 과하게 주입해 토출압과 corr -0.02(같은 펌프인데 무상관 = 비물리적)로
    #   만든 것을 되돌린다. 흡입·토출은 같은 펌프가 구동하므로 물리적으로 상관돼야 정상이다.
    #   고장 신호(흡입 막힘)는 둘의 '관계 변화(divergence)'로 잡으며, 이는 관계 판별 피처가 담당한다
    #   (docs/modeling/12 — 상관 낮추기가 아니라 관계 피처로 구분). 따라서 원래 물리식으로 복원.
    suction_pressure = (
        -10.5 - 0.7 * irr_mask - 1.5 * clog
    ) * pump_on + np.random.normal(0, 0.1, n) * pump_on

    # 전기 및 진동 (펌프 가동 여부에 연동)
    voltage_v = (
        380.0
        - (1.5 * irr_mask + 4.5 * clog + 6.0 * blocked_ratio) * pump_on
        + np.random.normal(0, 0.8, n)
    )
    motor_current_a = (
        6.4 + 0.50 * irr_mask + 1.2 * clog + 1.5 * blocked_ratio
    ) * pump_on + np.random.normal(0, 0.05, n) * pump_on
    motor_power_kw = (
        2.08 + 0.12 * irr_mask + 0.3 * clog + 0.4 * blocked_ratio
    ) * pump_on + np.random.normal(0, 0.01, n) * pump_on
    pump_rpm = (1750 + 32 * irr_mask + 45 * clog) * pump_on + np.random.normal(
        0, 3, n
    ) * pump_on

    # 진동: 두 성분으로 구성한다. (1) 배관 막힘과 무관한 '베어링 상태'의 독립 변동(마모·정렬불량,
    #   AR(1)) — 이건 진짜 독립 물리라 유지한다. (2) clog/cavitation 동반 진동(원래 계수 0.8·0.9 복원).
    #   정상 운전(clog=0)에선 독립 성분만 작용해 압력과 무상관(게이트 통과)이고, 막힘이 진행되면 압력과
    #   '함께' 오르는데 이는 실제 물리(막힘→cavitation→진동↑)라 올바른 고장 시그니처다.
    #   앞서 노이즈 접근으로 clog 비중을 0.4로 줄였던 것은 과교정이라 0.8·0.9로 되돌린다. seed_offset=2.
    bearing_condition_indep = ar1_process(n, sigma=0.035, phi=0.99, seed_offset=2)
    bearing_vibration_rms = (
        1.18 + 0.18 * irr_mask + 0.8 * clog + 0.9 * blocked_ratio + bearing_condition_indep
    ) * pump_on + np.random.normal(0, 0.02, n) * pump_on
    vibration_high_freq = (
        0.25 + 0.05 * irr_mask + 1.2 * clog
    ) * pump_on + np.random.normal(0, 0.01, n) * pump_on
    vibration_peak = (
        bearing_vibration_rms
        * (1.414 + 1.5 * clog + np.random.normal(0, 0.05, n))
        * pump_on
    )

    # 온도 및 여과기 (발열은 기온 베이스)
    air_temp_arr = env_data["air_temp_c"]
    # 모터·베어링 온도: 이전엔 둘 다 'air_temp + 상수 + clog'라 corr 0.97(거의 복제). 실제로 둘은
    #   열원(모터 권선 vs 베어링 마찰)과 열 시정수가 달라 독립 성분이 있다. 베어링온도에 고유 마찰열
    #   AR(1)을 더해 모터온도와의 상관을 0.4~0.7로 낮춘다(둘 다 air_temp는 공유하므로 0은 아님).
    #   seed_offset=3(모터)·4(베어링)로 서로 독립.
    motor_winding_indep = ar1_process(n, sigma=0.30, phi=0.99, seed_offset=3)
    bearing_friction_indep = ar1_process(n, sigma=0.45, phi=0.99, seed_offset=4)
    motor_temp = (
        air_temp_arr + (13 + 2.5 * clog) * pump_on + motor_winding_indep + np.random.normal(0, 0.22, n)
    )
    bearing_temp = (
        air_temp_arr + (10 + 2.0 * clog) * pump_on + bearing_friction_indep + np.random.normal(0, 0.18, n)
    )

    filter_in = (145 + 8 * irr_mask + 5 * clog) * pump_on + np.random.normal(
        0, 0.75, n
    ) * pump_on
    filter_delta = (
        7.2 + 2.0 * clog + 1.0 * blocked_ratio
    ) * pump_on + np.random.normal(0, 0.18, n) * pump_on

    zone_data = simulate_zone_data(
        n,
        minute_of_day,
        daylight,
        irr_mask,
        clog,
        blocked_ratio,
        flow_rate,
        cleaning_boost,
        pump_on,
    )

    # 🚨 정답지(Risk Stage) 계산 - 펌프 꺼짐(유량0)에도 상태가 유지되도록 delivery_eff 사용
    risk_score = 0.35 * clog + 0.35 * blocked_ratio + 0.30 * (1.0 - delivery_eff)
    risk_stage = np.where(
        risk_score < 0.15,
        "normal",
        np.where(
            risk_score < 0.25, "watch", np.where(risk_score < 0.35, "warning", "danger")
        ),
    )

    # -- 50개 컬럼 딕셔너리 완벽 조립 --
    data_dict = {
        "timestamp": idx,
        **env_data,
        "raw_tank_level_pct": np.round(
            np.clip(
                74
                - 0.0003 * np.arange(n)
                + 1.8 * np.sin(2 * np.pi * day_num / 5)
                + np.random.normal(0, 0.30, n),
                40,
                95,
            ),
            2,
        ),
        "raw_water_temp_c": np.round(
            18.5
            + 2.7 * daylight
            + 0.6 * np.sin(2 * np.pi * day_num / 4)
            + np.random.normal(0, 0.16, n),
            2,
        ),
        "motor_voltage_v": np.round(voltage_v, 2),
        "motor_current_a": np.round(motor_current_a, 3),
        "motor_power_kw": np.round(motor_power_kw, 3),
        "pump_rpm": np.round(pump_rpm, 2),
        "flow_rate_l_min": np.round(flow_rate, 2),
        "suction_pressure_kpa": np.round(suction_pressure, 2),
        "discharge_pressure_kpa": np.round(discharge_pressure, 2),
        "bearing_vibration_rms_mm_s": np.round(bearing_vibration_rms, 3),
        "vibration_peak_mm_s": np.round(vibration_peak, 3),
        "vibration_bandpower_high_g": np.round(vibration_high_freq, 3),
        "motor_temperature_c": np.round(motor_temp, 2),
        "bearing_temperature_c": np.round(bearing_temp, 2),
        "filter_pressure_in_kpa": np.round(filter_in, 2),
        "filter_pressure_out_kpa": np.round(filter_in - filter_delta, 2),
        "turbidity_ntu": np.round(
            1.9 + 0.22 * irr_mask + 0.5 * clog + np.random.normal(0, 0.07, n), 3
        ),
        "mix_target_ec_ds_m": np.round(np.full(n, 1.80), 2),
        "mix_ec_ds_m": np.round(
            1.80
            + 0.02 * np.sin(2 * np.pi * minute_of_day / 1440)
            + 0.025 * clog
            + np.random.normal(0, 0.012, n),
            3,
        ),
        "mix_target_ph": np.round(np.full(n, 5.80), 2),
        "mix_ph": np.round(
            5.80
            + 0.02 * np.sin(2 * np.pi * minute_of_day / 1440 + 1.1)
            - 0.05 * clean_flag
            + np.random.normal(0, 0.012, n),
            3,
        ),
        "mix_temp_c": np.round(19.2 + 2.4 * daylight + np.random.normal(0, 0.10, n), 2),
        "mix_flow_l_min": np.round(
            flow_rate * (0.988 + np.random.normal(0, 0.0035, n)), 2
        ),
        "dosing_acid_ml_min": np.round(
            np.clip(
                5 + 0.12 * irr_mask + 55 * clean_flag + np.random.normal(0, 0.5, n),
                0,
                None,
            ),
            2,
        ),
        # 배액 EC: 이전엔 변동이 거의 daylight뿐이라 습도(역시 daylight 구동)와 corr 0.97(우연 artifact).
        #   실제 배액 EC는 배지 염류 축적이라는 '느리고 독립적인' 과정이 지배한다(공공데이터: 배액 EC가
        #   공급보다 높으면 염류 축적). 그 독립 누적 성분(AR(1), seed_offset=5)을 더하고 daylight 비중을
        #   낮춰 습도와의 인위적 상관을 깬다(목표 <0.3).
        "drain_ec_ds_m": np.round(
            2.02
            + 0.04 * daylight
            + 0.25 * clog
            + 0.3 * blocked_ratio
            + ar1_process(n, sigma=0.02, phi=0.99, seed_offset=5)
            + np.random.normal(0, 0.025, n),
            3,
        ),
        "tank_a_level_pct": np.round(
            np.clip(
                82
                - 0.0004 * np.arange(n)
                - 0.7 * irr_mask
                + 1.4 * np.sin(2 * np.pi * day_num / 6)
                + np.random.normal(0, 0.22, n),
                20,
                100,
            ),
            2,
        ),
        "tank_b_level_pct": np.round(
            np.clip(
                80
                - 0.0004 * np.arange(n)
                - 0.65 * irr_mask
                + 1.2 * np.sin(2 * np.pi * day_num / 6 + 0.5)
                + np.random.normal(0, 0.22, n),
                20,
                100,
            ),
            2,
        ),
        "acid_tank_level_pct": np.round(
            np.clip(
                78
                - 0.00015 * np.arange(n)
                - 1.2 * clean_flag
                + np.random.normal(0, 0.16, n),
                10,
                100,
            ),
            2,
        ),
        **zone_data,
        "cleaning_event_flag": clean_flag,
        "flow_baseline_l_min": np.round(flow_baseline, 2),
        "hidden_tip_clog_level": np.round(clog, 4),
        "hidden_risk_stage": risk_stage,
    }

    df = pd.DataFrame(data_dict)
    eps = 1e-6

    # 6. 파생 변수 (AE 해석 및 특징 추출용)
    df["fe_flow_drop_rate"] = np.round(
        (df["flow_baseline_l_min"] - df["flow_rate_l_min"])
        / (df["flow_baseline_l_min"] + eps),
        4,
    )
    # 밤에 baseline이 0이 되어 무한대가 나오는 것 방지
    df["fe_flow_drop_rate"] = np.where(pump_on == 0, 0.0, df["fe_flow_drop_rate"])

    df["fe_flow_delta_1m"] = np.round(df["flow_rate_l_min"].diff().fillna(0), 4)
    df["fe_pressure_flow_ratio"] = np.round(
        df["discharge_pressure_kpa"] / (df["flow_rate_l_min"] + eps), 4
    )
    df["fe_dp_per_flow"] = np.round(
        (df["discharge_pressure_kpa"] - df["suction_pressure_kpa"])
        / (df["flow_rate_l_min"] + eps),
        4,
    )
    df["fe_flow_per_power"] = np.round(
        df["flow_rate_l_min"] / (df["motor_power_kw"] + eps), 4
    )
    df["fe_temp_slope_sec"] = np.round(
        df["motor_temperature_c"].diff() / 60.0, 5
    ).fillna(0)

    return df


# ==========================================
# 6. 저장 및 메타데이터(Excel) 자동화
# ==========================================
def save_data_and_metadata():
    full_df = generate_smartfarm_final_v5()

    # 1) Hidden 컬럼 제거 후 CSV 저장
    export_df = full_df.drop(
        columns=[col for col in full_df.columns if col.startswith("hidden_")]
    )
    csv_path = OUTPUT_DIR / "smartfarm_nutrient_pump_raw_v5.csv"
    export_df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    # 2) Data Dictionary (Excel) 자동 생성
    data_dict_info = {
        "Column Name": export_df.columns.tolist(),
        "Description": [
            (
                "데이터 기록 시각 (1분 단위)"
                if "time" in c
                else (
                    "목표/이상적 기준 유량 (모델 정상 기준점)"
                    if c == "flow_baseline_l_min"
                    else (
                        "실제 센서 측정 유량 (막힘 시 감소)"
                        if c == "flow_rate_l_min"
                        else (
                            "모터 과부하 시 발생하는 미세 전압 강하량"
                            if c == "motor_voltage_v"
                            else (
                                "진동의 순간 최대 충격량 (난류 발생 시 급증)"
                                if c == "vibration_peak_mm_s"
                                else (
                                    "고주파 대역 진동 크기 (캐비테이션/이물질 감지)"
                                    if c == "vibration_bandpower_high_g"
                                    else (
                                        "필터 자체가 막혔을 때 발생하는 전/후단 압력 차이 확인용"
                                        if c == "filter_pressure_out_kpa"
                                        else (
                                            "관수관 세척(산세척) 진행 상태 (1=진행중)"
                                            if c == "cleaning_event_flag"
                                            else (
                                                "유량 감소율 (baseline 대비 비율)"
                                                if c == "fe_flow_drop_rate"
                                                else (
                                                    "1분 전 대비 유량 변화량 (기동 스파이크 감지용)"
                                                    if c == "fe_flow_delta_1m"
                                                    else (
                                                        "토출압력 / 유량 비율 (막힘 시 폭증)"
                                                        if c == "fe_pressure_flow_ratio"
                                                        else (
                                                            "차압 / 유량 비율 (막힘 시 폭증)"
                                                            if c == "fe_dp_per_flow"
                                                            else (
                                                                "유량 / 모터전력 비율 (에너지 효율, 막힘 시 급감)"
                                                                if c
                                                                == "fe_flow_per_power"
                                                                else (
                                                                    "초당 모터 온도 변화량 (가동 시 발열 속도)"
                                                                    if c
                                                                    == "fe_temp_slope_sec"
                                                                    else "원본 센서 및 시스템 제어값 (원본 유지)"
                                                                )
                                                            )
                                                        )
                                                    )
                                                )
                                            )
                                        )
                                    )
                                )
                            )
                        )
                    )
                )
            )
            for c in export_df.columns
        ],
    }
    excel_path = OUTPUT_DIR / "smartfarm_data_dictionary.xlsx"
    pd.DataFrame(data_dict_info).to_excel(excel_path, index=False)

    print(f"✅ CSV 저장 완료 (Hidden 칼럼 제외): {csv_path}")
    print(f"✅ Data Dictionary 엑셀 저장 완료: {excel_path}")
    print(f"📊 최종 데이터 형태(Shape): {export_df.shape} (50개 컬럼 + fe_ 파생변수)")


# 스크립트 실행
if __name__ == "__main__":
    save_data_and_metadata()
