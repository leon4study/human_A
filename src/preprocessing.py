# 오직 Pandas를 이용해서 데이터를 지지고 볶는 '순수 데이터 전처리' 함수들만 모아둡니다.
# - filter_active_periods (유효 데이터 필터링)
# - create_modeling_features (도메인 파생변수 생성)
# - aggregate_time_window (슬라이딩 윈도우 집계)
# - step1_prepare_window_data (Step 1 조립)
# - step2_clean_and_drop_collinear (Step 2 정제)

# 💻 스마트팜 예지보전 데이터 전처리 및 피처 엔지니어링 파이프라인


import pandas as pd
import numpy as np

eps = 1e-6  # 0 나누기 방지


# ==============================================================================
# 1. 유효 데이터 필터링 (낮 시간 & 관수 가동 중)
# ==============================================================================
def filter_active_periods(df):
    """
    조명이 켜져 있는 주간 시간대이면서, 실제로 펌프나 구역 밸브가 작동한 시점만 필터링합니다.
    야간이나, 낮이더라도 물을 주지 않는 대기 시간은 분석에서 제외하여 노이즈를 줄입니다.
    """
    # 조건: 조명이 켜져있고(lights_on == 1) AND (펌프가 돌거나 OR 1~3구역 밸브 중 하나라도 열림)
    active_condition = (df["lights_on"] == 1) & (
        (df["pump_on"] == 1)
        | (df["zone1_valve_on"] == 1)
        | (df["zone2_valve_on"] == 1)
        | (df["zone3_valve_on"] == 1)
    )
    return df[active_condition].copy()


# ==============================================================================
# 2. 모델 학습용 파생변수 생성 (Raw 데이터 기반)
# ==============================================================================


def create_modeling_features(df, extra_cols=None):
    """
    파생변수 생성 함수입니다.
    이 함수는 10분 단위 집계(Aggregation)를 하기 전, 1분 단위 Raw Data 상태에서 실행해야 가장 정확합니다.

    Parameters
    ----------
    extra_cols : list, optional
        SHAP 타겟 컬럼 등 model_cols 필터에서 반드시 살아남아야 할 컬럼들.

    Returns
    -------
    (df_model, df_interpret) : tuple
        df_model  — 오토인코더 입력용 (model_cols 필터 적용)
        df_interpret — 해석/모니터링용
    """
    df_feat = df.copy()
    eps = 1e-6

    # 시간 단위 변화율을 구하기 위해 인덱스의 시간차(초 단위) 계산 (연속된 데이터라 가정)
    # 인덱스가 datetime이어야 작동합니다.
    if pd.api.types.is_datetime64_any_dtype(df_feat.index):
        dt_seconds = df_feat.index.to_series().diff().dt.total_seconds().fillna(60)
    else:
        dt_seconds = 60  # 기본값 1분(60초)

    # 시간(Hour) 피처를 원형으로 변환하여 모델에게 '주기'를 알려줍니다.
    # 하루 중 몇 번째 '분(Minute)'인지 계산 (0 ~ 1439)
    df_feat["minute_of_day"] = df_feat.index.hour * 60 + df_feat.index.minute

    # 24 대신 1440(하루 전체 분)으로 나누어 완벽하게 부드러운 원(Circle)을 만듭니다.
    df_feat["time_sin"] = np.sin(2 * np.pi * df_feat["minute_of_day"] / 1440)
    df_feat["time_cos"] = np.cos(2 * np.pi * df_feat["minute_of_day"] / 1440)

    # "만약 오늘은 펌프를 평소보다 10분 늦게 켰다면?" AI는 시간이 어긋났다고 생각해 정상적인 스파이크를 에러로 오해할 수 있습니다.
    # 따라서 '펌프 가동 시점의 짧고 강한 변동'을 모델이 완벽하게 이해하게 만들려면, 시간 피처와 더불어 '변화량(Delta)' 피처를 하나 더 만들어주는 것이 MLOps의 필살기입니다.
    # [옵션] 이전 시간 대비 압력이 얼마나 급변했는지(Delta)를 피처로 줍니다.
    df_feat["pressure_diff"] = df_feat["discharge_pressure_kpa"].diff().fillna(0)

    # =====================================================================
    # 1. 압력 & 유량 & 전력 기본 조합 지표 (해석용과 학습용 공통 사용 가능)
    # =====================================================================
    # 차압 (Differential Pressure)
    # 펌프가 실제로 물을 끌어올려 밀어낸 순수 압력 에너지입니다.
    # [Rule] 차압이 급감하면 펌프 임펠러 손상이나 공기 유입(캐비테이션)을 의심해야 합니다.
    df_feat["differential_pressure_kpa"] = (
        df_feat["discharge_pressure_kpa"] - df_feat["suction_pressure_kpa"]
    )

    # ==========================================================================
    # [순서 중요] 운전 상태(pump_on)를 유량 파생 피처 이전에 먼저 계산.
    # flow_drop_rate 같은 공식이 기동 전환 구간에서 발산하지 않도록 게이트로 사용.
    # 변동성(rpm_std) + 유량 + rpm 수준으로 pump_on을 동적 판정 → 기동 스파이크 학습용.
    # ==========================================================================
    rpm_std = df_feat["pump_rpm"].rolling(window=5, min_periods=1).std().fillna(0)
    flow_on = df_feat["flow_rate_l_min"] > 0.1
    std_threshold = rpm_std.quantile(0.8)
    dynamic_on = rpm_std > std_threshold
    rpm_high = df_feat["pump_rpm"] > df_feat["pump_rpm"].quantile(0.7)

    df_feat["pump_on"] = (flow_on | dynamic_on | rpm_high).astype(int)
    df_feat["pump_on"] = df_feat["pump_on"].rolling(3, min_periods=1).max().astype(int)

    pump_on = df_feat["pump_on"].astype(int)

    start_event = pump_on.eq(1) & pump_on.shift(1, fill_value=0).eq(0)
    cycle_id = start_event.cumsum()
    on_steps = pump_on.groupby(cycle_id).cumsum()

    df_feat["minutes_since_startup"] = np.where(
        pump_on.eq(1), on_steps - 1, 0
    ).astype(int)

    # 유량 감소율 (Flow Drop Rate)
    # 정상적인 기준치 대비 현재 유량이 얼마나 줄었는지 백분율로 나타냅니다.
    # [Rule] 유량이 급감하면 공압, 실린더, 배관 막힘 등 물리적 저항이 발생했음을 의미합니다.
    # baseline은 최근 1시간(60분) 이동평균으로 설정.
    #
    # ⚠️ Phase A 3차(2026-04-20) 버그 픽스:
    # 기동 전환 시 baseline≈0 + flow_rate 급증으로 분모가 eps에 가까워 -3e7 같은 발산 발생.
    # 학습 데이터의 0.5% 샘플이 수천만 단위 극단값 → MinMaxScaler 왜곡 → AE MSE 폭발,
    # RCA 99.9%를 flow_drop_rate가 독점(실측). 세 단계 게이트로 해결:
    #   (1) pump_on=0이면 0   — 정지 중엔 "드롭" 개념 자체가 없음
    #   (2) baseline < 1 L/min이면 0 — 분모 발산 방지 (기동 직후 누적 부족 구간)
    #   (3) [0, 1] 클리핑      — 음수 drop(=surge/상승)은 "유량 감소" 의미에 맞지 않아 0으로 수렴
    # 결과: 0=정상, 1=완전 막힘의 직관적 드롭 신호만 남김.
    df_feat["flow_baseline_l_min"] = (
        df_feat["flow_rate_l_min"].rolling(window=60, min_periods=1).mean().shift(1)
    )
    MIN_BASELINE_LMIN = 1.0  # L/min — 이보다 작으면 baseline 신뢰도 낮음
    _raw_drop = (
        df_feat["flow_baseline_l_min"] - df_feat["flow_rate_l_min"]
    ) / (df_feat["flow_baseline_l_min"] + eps)
    df_feat["flow_drop_rate"] = _raw_drop.where(
        (df_feat["pump_on"] == 1)
        & (df_feat["flow_baseline_l_min"] >= MIN_BASELINE_LMIN),
        0.0,
    ).clip(0.0, 1.0)

    # =====================================================================
    # [추가] 1-2. 펌프 수력학 및 시스템 효율 지표
    # =====================================================================
    # 필터 전후 압력 차 (Filter Delta P)
    # df_feat['filter_delta_p_kpa'] = df_feat['filter_pressure_in_kpa'] - df_feat['filter_pressure_out_kpa']
    # 필터 전후 압력차 유의미한 결과 뽑기 힘들어서 제거

    # 유체에 전달된 유효 동력 (Hydraulic Power, kW)
    # 수식: (유량(L/min) * 차압(kPa)) / 60,000
    df_feat["hydraulic_power_kw"] = (
        df_feat["flow_rate_l_min"] * df_feat["differential_pressure_kpa"]
    ) / 60000

    # 모터 입력 대비 출력 효율 (Wire-to-Water Efficiency)
    # 수식: 유효 동력 / 전기 입력 전력
    df_feat["wire_to_water_efficiency"] = df_feat["hydraulic_power_kw"] / (
        df_feat["motor_power_kw"] + eps
    )

    # pump_on / minutes_since_startup 은 flow_drop_rate 이전에 먼저 계산됨 (위 블록 참고).

    df_feat["pump_start_event"] = start_event.astype(int)
    df_feat["is_startup_phase"] = (
        pump_on.eq(1) & df_feat["minutes_since_startup"].between(0, 5)
    ).astype(int)

    # OFF 상태 추적
    pump_off = (df_feat["pump_on"] == 0).astype(int)
    stop_event = pump_off.eq(1) & pump_off.shift(1, fill_value=0).eq(0)
    stop_cycle_id = stop_event.cumsum()
    off_steps = pump_off.groupby(stop_cycle_id).cumsum()

    df_feat["minutes_since_shutdown"] = np.where(
        pump_off.eq(1), off_steps - 1, 0
    ).astype(int)

    df_feat["pump_stop_event"] = stop_event.astype(int)
    df_feat["is_off_phase"] = (
        pump_off.eq(1) & df_feat["minutes_since_shutdown"].between(0, 5)
    ).astype(int)
    
    # =====================================================================
    # 2. 온도 & 진동 동특성 지표
    # =====================================================================
    # 초당 모터 온도 변화율 (Temperature Slope)
    df_feat["temp_slope_c_per_s"] = df_feat["motor_temperature_c"].diff() / dt_seconds

    # 유량/RPM 변화율 및 가속도
    df_feat["flow_diff"] = df_feat["flow_rate_l_min"].diff().fillna(0)
    df_feat["rpm_slope"] = df_feat["pump_rpm"].diff() / dt_seconds
    df_feat["rpm_acc"] = df_feat["rpm_slope"].diff().fillna(0)

    # RPM 안정성 지수 (RPM Stability Index)
    # [Rule] 펌프에 공기가 차거나 난류가 발생하면 RPM이 목표값을 유지하지 못하고 요동칩니다.
    rpm_mean_10 = df_feat["pump_rpm"].rolling(window=10, min_periods=1).mean()
    df_feat["rpm_stability_index"] = np.abs(df_feat["pump_rpm"] - rpm_mean_10) / (
        rpm_mean_10 + eps
    )

    # =====================================================================
    # 3. 양액/수질 및 환경 고도화 지표
    # =====================================================================
    # 제어기 목표 추종 오차 (PID Error EC / pH)
    # [Rule] 오차가 지속적으로 크면 조제기 밸브 노후화, 산/비료 원액 고갈, 혼합 모터 고장을 의미합니다.
    df_feat["pid_error_ec"] = df_feat["mix_ec_ds_m"] - df_feat["mix_target_ec_ds_m"]
    df_feat["pid_error_ph"] = df_feat["mix_ph"] - df_feat["mix_target_ph"]

    # pH 불안정성 (침전 발생 임계점 6.5 초과 여부)
    df_feat["ph_instability_flag"] = (df_feat["mix_ph"] > 6.5).astype(np.int8)

    # 누적 염분 부하량
    df_feat["salt_accumulation_delta"] = (
        df_feat["drain_ec_ds_m"] - df_feat["mix_ec_ds_m"]
    )

    # 추세형 피처
    df_feat["pressure_roll_mean_10"] = df_feat["differential_pressure_kpa"].rolling(
        window=10, min_periods=1
    ).mean()
    df_feat["flow_roll_mean_10"] = df_feat["flow_rate_l_min"].rolling(
        window=10, min_periods=1
    ).mean()
    df_feat["pressure_trend_10"] = df_feat["pressure_roll_mean_10"].diff().fillna(0)
    df_feat["flow_trend_10"] = df_feat["flow_roll_mean_10"].diff().fillna(0)
    df_feat["ph_roll_mean_30"] = df_feat["mix_ph"].rolling(window=30, min_periods=1).mean()
    df_feat["ph_trend_30"] = df_feat["ph_roll_mean_30"].diff().fillna(0)
    df_feat["pressure_flow_ratio"] = (
        df_feat["differential_pressure_kpa"] / (df_feat["flow_rate_l_min"] + eps)
    )

    # 광합성 유효 광량자속 밀도 누적 프록시 (DLI Proxy)
    # 순간 광량(PPFD)을 누적하여 하루 동안 식물이 받은 총 빛의 양(DLI)을 추정합니다.
    # [Rule] 빛을 많이 받을수록 식물은 물을 많이 먹습니다. 빛은 많은데 배액률이 늘어난다면 뿌리가 죽었거나 점적 핀이 빠진 것입니다.
    # DLI 공식: PPFD * 시간(초) / 1,000,000 = mol/m²/day
    df_feat["daily_light_integral_proxy"] = (
        df_feat["light_ppfd_umol_m2_s"] * dt_seconds
    ) / 1_000_000

    # 하루 누적 광량 (Daily Light Integral, mol/m²/d)
    # proxy 값을 날짜(Date) 단위로 그룹화하여 누적합(cumsum)을 구합니다.
    df_feat["daily_light_integral_mol_m2_d"] = df_feat.groupby(df_feat.index.date)[
        "daily_light_integral_proxy"
    ].cumsum()

    # =====================================================================
    # [추가] 3-2. 식물 환경 스트레스 지표 (VPD) 복구 완료
    # =====================================================================
    T = df_feat["air_temp_c"]
    RH = df_feat["relative_humidity_pct"]
    # Tetens formula 적용: 권장 VPD 범위는 0.5 ~ 1.2 kPa [cite: 30]
    e_s = 0.61078 * np.exp((17.27 * T) / (T + 237.3))
    df_feat["calculated_vpd_kpa"] = e_s - (e_s * (RH / 100))

    # =====================================================================
    # 4. 탱크 및 자원 소진 예측 지표
    # =====================================================================
    # 탱크 수위 변화율 (Tank Level Change Pct per Min)
    # 1분 동안 원수 탱크 수위가 몇 % 줄어드는지 소모 속도를 계산합니다.
    # [Rule] 관수를 안 하는데 수위가 줄어들면 탱크 누수이며, 펌프가 도는데 수위가 안 줄면 센서 고장이나 원수 밸브 막힘입니다.
    df_feat["raw_tank_level_change_pct_per_min"] = df_feat[
        "raw_tank_level_pct"
    ].diff() / (dt_seconds / 60)

    # A/B/산 탱크 고갈 예상 시간 (Estimated Hours to Empty)
    # 현재 소비 속도를 바탕으로 비료통이 언제 텅 빌지 예측합니다. (음수 변화량 활용)
    # [Rule] 값이 급격히 0에 수렴하면 농장주에게 비료를 타라고 알람을 주어야 합니다.
    for tank in ["tank_a", "tank_b", "acid_tank"]:
        # 최근 10분간의 평균 감소 속도 (%/min)
        consumption_rate = (
            -df_feat[f"{tank}_level_pct"]
            .diff()
            .rolling(window=10, min_periods=1)
            .mean()
        )
        consumption_rate = consumption_rate.clip(
            lower=eps
        )  # 0 이하(채우고 있는 중) 방지
        # 남은 시간(분) = 남은 잔량 / 분당 소모량 -> 시간(Hour)으로 변환
        df_feat[f"{tank}_est_hours_to_empty"] = (
            df_feat[f"{tank}_level_pct"] / consumption_rate
        ) / 60

    # =====================================================================
    # 5. 구역(Zone) 복합 제어 지표
    # =====================================================================
    # 활성 구역 개수 (Active Zone Count)
    # 현재 동시에 물이 들어가고 있는 베드의 개수입니다.
    # [Rule] 1구역만 열릴 때와 3구역이 동시에 열릴 때 펌프의 토출 압력과 유량 기준치가 달라야 합니다. (다중공선성을 막고 모델에 Context 제공)
    # df_feat['active_zone_count'] = df_feat['zone1_valve_on'] + df_feat['zone2_valve_on'] + df_feat['zone3_valve_on']

    # 공급 밸런스 지수 (Supply Balance Index)
    # 펌프가 밀어낸 총 유량 대비 각 구역으로 들어간 유량의 합의 비율입니다.
    # [Rule] 메인 펌프 유량은 100인데 구역 유량 합이 70이라면, 중간 배관 어딘가에서 누수가 발생한 것입니다.
    zone_flow_sum = (
        df_feat["zone1_flow_l_min"]
        + df_feat["zone2_flow_l_min"]
        + df_feat["zone3_flow_l_min"]
    )
    df_feat["supply_balance_index"] = zone_flow_sum / (df_feat["flow_rate_l_min"] + eps)

    # =====================================================================
    # [추가] 5-2. 구역별 수분 반응 지표
    # =====================================================================
    # 급액 후 수분 변화량 (Moisture Response)
    # 직전 1분 대비 현재 배지 수분이 얼마나 올랐는지(+) 계산합니다.
    for i in range(1, 4):
        df_feat[f"zone{i}_moisture_response_pct"] = df_feat[
            f"zone{i}_substrate_moisture_pct"
        ].diff()
        # -------------------------------------------------------------
        # [추가] 5-2. 구역별 배관 저항 및 염류 축적량 지표
        # -------------------------------------------------------------
        # 배관 저항 = 압력 / 유량 (유량이 0일 때 무한대 방지를 위해 eps 더함)
        df_feat[f"zone{i}_resistance"] = df_feat[f"zone{i}_pressure_kpa"] / (
            df_feat[f"zone{i}_flow_l_min"] + eps
        )

        # 염류 축적량 = 배지 측정 EC - 공급 양액 EC
        df_feat[f"zone{i}_ec_accumulation"] = (
            df_feat[f"zone{i}_substrate_ec_ds_m"] - df_feat["mix_ec_ds_m"]
        )

    # =========================================================
    # 7. 모델 입력용 / 해석용 분리
    # =========================================================
    model_cols = [
        # raw sensors
        "flow_rate_l_min", "motor_power_kw", "pump_rpm",
        "discharge_pressure_kpa", "suction_pressure_kpa", "motor_temperature_c",
        "mix_ph", "mix_ec_ds_m", "mix_target_ec_ds_m", "mix_target_ph", "drain_ec_ds_m",
        "air_temp_c", "relative_humidity_pct",
        # time / state
        "time_sin", "time_cos", "pump_on", "pump_start_event", "pump_stop_event",
        "minutes_since_startup", "minutes_since_shutdown", "is_startup_phase", "is_off_phase",
        # dynamics
        "pressure_diff", "differential_pressure_kpa", "flow_diff", "flow_drop_rate",
        "wire_to_water_efficiency", "rpm_slope", "rpm_acc", "rpm_stability_index",
        "temp_slope_c_per_s", "pid_error_ec", "pid_error_ph", "salt_accumulation_delta",
        "pressure_roll_mean_10", "flow_roll_mean_10", "pressure_trend_10", "flow_trend_10",
        "ph_roll_mean_30", "ph_trend_30", "pressure_flow_ratio",
    ]

    # extra_cols: SHAP 타겟처럼 반드시 보존해야 하는 컬럼들
    if extra_cols:
        model_cols = list(set(model_cols) | set(extra_cols))
    model_cols = [c for c in model_cols if c in df_feat.columns]
    df_model = df_feat[model_cols].copy()

    df_interpret = extract_interpretation_features(df_feat)

    return df_model, df_interpret


# ==============================================================================
# 3. 데이터 시계열 윈도우 집계 (Tumbling vs Sliding)
# ==============================================================================
# 센서값(압력, 유량)은 .mean()으로 부드럽게 만들되,
# 시간값(time_sin 등)은 무조건 윈도우의 **가장 마지막 값(.last())**을 가져오도록
# 딕셔너리를 사용해 명확하게 분리해야 합니다.
def aggregate_time_window(
    df, method="tumbling", window_size="10min", slide_step="1min"
):
    """
    연속된 시계열 데이터를 머신러닝 모델이 소화하기 좋게 윈도우 단위로 묶어줍니다.
    """
    # 1. 전체 숫자형 컬럼 및 센서/시간/상태 컬럼 분리
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    # 바이너리/상태 플래그는 평균 집계하면 의미가 깨지므로 phase로 분리
    phase_cols = [
        "pump_on", "minutes_since_startup", "is_startup_phase",
        "pump_start_event", "pump_stop_event", "minutes_since_shutdown", "is_off_phase",
        "cleaning_event_flag",
        # data_gen_test.py가 부여하는 평가용 정답 라벨 — 평균 집계되면 안 되므로 phase로 분리
        "anomaly_label", "composite_z_score",
    ]
    time_cols = ["minute_of_day", "time_sin", "time_cos"]
    sensor_cols = [col for col in numeric_cols if col not in time_cols + phase_cols]

    if method == "tumbling":
        # 🌟 텀블링: resample은 'last'를 지원하므로 딕셔너리 방식 사용
        agg_dict = {col: "mean" for col in sensor_cols if col in df.columns}

        phase_agg = {
            "pump_on": "last", "minutes_since_startup": "last", "is_startup_phase": "max",
            "pump_start_event": "max", "pump_stop_event": "max",
            "minutes_since_shutdown": "last", "is_off_phase": "max",
            "cleaning_event_flag": "max",
            # 평가용 라벨: 윈도우 내 1개라도 이상이면 윈도우도 이상, worst-case z 유지
            "anomaly_label": "max",
            "composite_z_score": "max",
        }
        agg_dict.update({k: v for k, v in phase_agg.items() if k in df.columns})

        for t_col in time_cols:
            if t_col in df.columns:
                agg_dict[t_col] = "last"

        df_agg = df.resample(window_size).agg(agg_dict)  # ← 집계 실행

    elif method == "sliding":
        # 🌟 슬라이딩: rolling은 센서 데이터만 평균 계산! (연산 속도 최적화)
        df_sensor = df[sensor_cols].rolling(window=window_size).mean()

        # phase는 윈도우 끝 상태(last)가 중요
        _phase_cols = [
            c for c in ["pump_on", "minutes_since_startup", "is_startup_phase"] if c in df.columns
        ]
        df_phase = df[_phase_cols]

        # 윈도우 내 max로 유지해야 하는 플래그/스코어 컬럼:
        # - cleaning_event_flag : 1이면 윈도우에 세척 이벤트 포함 → 학습 제외 필터용
        # - anomaly_label       : data_gen_test.py 평가용 이진 정답 (한번이라도 이상이면 윈도우=이상)
        # - composite_z_score   : 평가용 연속 z-score (윈도우 worst-case 보존)
        maxflag_cols = ["cleaning_event_flag", "anomaly_label", "composite_z_score"]
        df_maxflags = pd.DataFrame(index=df_sensor.index)
        for _col in maxflag_cols:
            if _col in df.columns:
                df_maxflags[_col] = df[_col].rolling(window=window_size).max()

        df_agg = pd.concat([df_sensor, df_phase], axis=1)
        if not df_maxflags.empty:
            df_agg = pd.concat([df_agg, df_maxflags], axis=1)

        # 시간 데이터는 어차피 현재 인덱스의 값이 '윈도우의 끝점(last)'이므로
        # 원본(df)에서 그대로 복사해옵니다. (lambda 쓰는 것보다 훨씬 빠름)
        for t_col in time_cols:
            if t_col in df.columns:
                df_agg[t_col] = df[t_col]

        # rolling은 주파수를 바꾸지 않으므로, slide_step(예: 1분) 간격으로 솎아냄
        df_agg = df_agg.resample(slide_step).last()

    else:
        raise ValueError("method는 'tumbling' 또는 'sliding'이어야 합니다.")

    # 집계 후 결측치 발생 구간(가동 중지 구간, 초기 rolling 구간 등) 제거
    return df_agg.dropna()


# ==============================================================================
# 4. 결과 해석용 파생변수 생성 (강사님 지표 분리)
# ==============================================================================

# extract_interpretation_features 함수는 텀블링 윈도우든 슬라이딩 윈도우든 전혀 수정할 필요 없이 그대로 사용하면 됨.
def extract_interpretation_features(df_agg):
    """
    AutoEncoder의 입력으로 쓰지 않고,
    나중에 '왜 고장 징후(Anomaly)로 판별했는가?'를 해석할 때 모니터링용으로 쓸 강사님의 피처들입니다.
    윈도우 집계가 끝난 데이터(df_agg) 위에서 계산합니다.
    """
    eps = 1e-6
    df_interpret = pd.DataFrame(index=df_agg.index)

    # ---------------------------------------------------------
    # 1. 유량 대비 압력 비율 (Pressure Flow Ratio)
    # [Rule] 펌프 효율 저하 지표. 같은 압력을 가했는데 유량이 줄었다면 관로 막힘 의심, 반대면 누수 의심.
    df_interpret["pressure_flow_ratio"] = df_agg["discharge_pressure_kpa"] / (
        df_agg["flow_rate_l_min"] + eps
    )

    # ---------------------------------------------------------
    # 2. 차압 대비 유량 (Differential Pressure per Flow)
    # [Rule] 토출과 흡입 압력의 차이(순수 펌프 에너지) 대비 유량. 값이 상승하면 에너지만 쓰고 물은 못 밀어내는 비정상 부하 상태입니다.
    df_interpret["dp_per_flow"] = (
        df_agg["discharge_pressure_kpa"] - df_agg["suction_pressure_kpa"]
    ) / (df_agg["flow_rate_l_min"] + eps)

    # ---------------------------------------------------------
    # 3. 압력 대비 전력 효율 (Pressure per Power)
    # [Rule] 압력을 유지하기 위해 전력을 과하게 쓰고 있다면 모터의 베어링 마모 등 기계적 부하가 걸린 상태입니다.
    df_interpret["pressure_per_power"] = df_agg["discharge_pressure_kpa"] / (
        df_agg["motor_power_kw"] + eps
    )

    # ---------------------------------------------------------
    # 4. 유량 대비 전력 효율 (Flow per Power)
    # [Rule] 동일한 전력을 소모하는데 유량이 줄어들면, 모터나 펌프 내부의 기계적 마찰이 심해졌음을 의미합니다.
    df_interpret["flow_per_power"] = df_agg["flow_rate_l_min"] / (
        df_agg["motor_power_kw"] + eps
    )

    # ---------------------------------------------------------
    # 5. 유량 감소율 (Flow Drop Rate)
    # [Rule] 정상적인 기준치 대비 현재 얼마나 흐름이 약해졌는지 백분율로 나타냅니다.
    # 주의: 이 값은 1분 단위 원천 데이터에서 계산되어 df_agg로 넘어온 상태이므로 재계산하지 않고 가져옵니다.
    if "flow_drop_rate" in df_agg.columns:
        df_interpret["flow_drop_rate"] = df_agg["flow_drop_rate"]
    else:
        # 혹시 이전 단계에서 누락되었을 경우를 대비한 예외 처리 (10분 평균값 기반으로 임시 계산)
        flow_baseline_10m = (
            df_agg["flow_rate_l_min"].rolling(window=6, min_periods=1).mean().shift(1)
        )
        df_interpret["flow_drop_rate"] = (
            flow_baseline_10m - df_agg["flow_rate_l_min"]
        ) / (flow_baseline_10m + eps)

    # ---------------------------------------------------------
    # 0-time. 시간 피처 (VIP 주입용 — AE 입력 보강)
    # ---------------------------------------------------------
    for col in ["time_sin", "time_cos"]:
        if col in df_agg.columns:
            df_interpret[col] = df_agg[col]

    # ---------------------------------------------------------
    # 6-zone. 구역 점적 시스템 해석 컬럼
    # ---------------------------------------------------------
    for col in ["zone1_resistance", "zone1_moisture_response_pct", "zone1_ec_accumulation"]:
        if col in df_agg.columns:
            df_interpret[col] = df_agg[col]

    if "supply_balance_index" in df_agg.columns:
        df_interpret["supply_balance_index"] = df_agg["supply_balance_index"]

    if "ph_instability_flag" in df_agg.columns:
        df_interpret["ph_instability_flag"] = df_agg["ph_instability_flag"]

    # VPD (보조 모니터링용 — AE 타겟 아님)
    if "calculated_vpd_kpa" in df_agg.columns:
        df_interpret["calculated_vpd_kpa"] = df_agg["calculated_vpd_kpa"]

    # ---------------------------------------------------------
    # 6. 초기 Spike 탐지 (startup 구간 vs 비정상 구간 분리)
    # ---------------------------------------------------------
    for col in [
        "is_startup_phase", "pump_start_event", "minutes_since_startup",
        "is_off_phase", "pump_on"
    ]:
        if col in df_agg.columns:
            df_interpret[col] = df_agg[col]

    # 압력 spike: |pressure_diff| 가 rolling 80th 분위 초과
    if "pressure_diff" in df_agg.columns:
        df_interpret["pressure_diff"] = df_agg["pressure_diff"]
        p_thresh = df_agg["pressure_diff"].abs().rolling(window=60, min_periods=1).quantile(0.80)
        df_interpret["is_pressure_spike"] = (df_agg["pressure_diff"].abs() > p_thresh).astype(int)
    else:
        df_interpret["is_pressure_spike"] = 0

    # RPM spike: rpm_slope 가 rolling 80th 분위 초과
    if "rpm_slope" in df_agg.columns:
        df_interpret["rpm_slope"] = df_agg["rpm_slope"]
        r_thresh = df_agg["rpm_slope"].abs().rolling(window=60, min_periods=1).quantile(0.80)
        df_interpret["is_rpm_spike"] = (df_agg["rpm_slope"].abs() > r_thresh).astype(int)
    else:
        df_interpret["is_rpm_spike"] = 0

    # 복합 spike 여부 (압력 OR rpm)
    df_interpret["is_spike"] = (
        (df_interpret["is_pressure_spike"] == 1) | (df_interpret["is_rpm_spike"] == 1)
    ).astype(int)

    # 정상 spike: startup 구간 내 spike (예상된 거동)
    startup = df_interpret.get("is_startup_phase", 0)
    df_interpret["is_startup_spike"] = (
        (df_interpret["is_spike"] == 1) & (startup == 1)
    ).astype(int)

    # 비정상 spike: startup 구간 밖의 spike (이상 징후)
    df_interpret["is_anomaly_spike"] = (
        (df_interpret["is_spike"] == 1) & (startup != 1)
    ).astype(int)

    return df_interpret


# ==============================================================================
# [Pipeline Step 1] 파생변수 생성 및 윈도우 집계
# ==============================================================================
def step1_prepare_window_data(df_raw, window_method="sliding", target_cols=None):
    print(f"⏳ [Step 1] 파생변수 생성 및 {window_method.upper()} 윈도우 집계 시작...")

    # 1. 로우 데이터에서 물리적 파생변수 생성 (공통)
    df_features, _ = create_modeling_features(df_raw, extra_cols=target_cols)

    # 2. 윈도우 집계 (인자에 따라 다르게 동작)
    if window_method == "sliding":
        df_agg = aggregate_time_window(
            df_features, method="sliding", window_size="5min", slide_step="1min"
        )
    elif window_method == "tumbling":
        df_agg = aggregate_time_window(
            df_features, method="tumbling", window_size="10min"
        )
    else:
        raise ValueError("window_method는 'sliding' 또는 'tumbling' 이어야 합니다.")

    # 3. [해석용 데이터] 모델 피처 삭제 전, 원본 윈도우 데이터에서 미리 분리
    df_interpret = extract_interpretation_features(df_agg)

    print(
        f"  -> 집계 완료! (집계 데이터: {df_agg.shape}, 해석용 데이터: {df_interpret.shape})"
    )
    return df_agg, df_interpret


# ==============================================================================
# [Pipeline Step 2] 데이터 정제 및 다중공선성 제거
# ==============================================================================
def step2_clean_and_drop_collinear(df_agg):
    print("\n🧹 [Step 2] 데이터 정제 및 다중공선성 변수 제거 시작...")

    # 2. 다중공선성 및 풍선효과 결과 변수들 수동 제거 리스트
    collinear_drop_list = [
        "tank_b_level_pct",
        "acid_tank_level_pct",
        "tank_a_est_hours_to_empty",
        "tank_b_est_hours_to_empty",
        "acid_tank_est_hours_to_empty",
        "zone2_flow_l_min",
        "zone3_flow_l_min",
        "zone2_pressure_kpa",
        "zone3_pressure_kpa",
        "zone2_substrate_moisture_pct",
        "zone3_substrate_moisture_pct",
        "zone2_substrate_ec_ds_m",
        "zone3_substrate_ec_ds_m",
        "zone2_resistance",
        "zone3_resistance",
        "relative_humidity_pct",
        "mix_temp_c",
        "raw_water_temp_c",
        "mix_flow_l_min",
        "filter_pressure_out_kpa",
        "hidden_tip_clog_level",
        ""
    ]

    # 1. 어차피 지울 컬럼들은 가장 먼저 쳐냅니다! (교집합 탐색으로 속도 UP)
    valid_cols_to_drop = list(set(collinear_drop_list).intersection(df_agg.columns))
    df_clean = df_agg.drop(columns=valid_cols_to_drop)

    # 2. 남은 핵심 피처들에 대해서만 결측치 연산을 수행하고,
    # inplace=True를 써서 새로운 메모리를 할당하지 않고 제자리에서 덮어씁니다.
    df_clean.replace([np.inf, -np.inf], np.nan, inplace=True)
    df_clean.fillna(df_clean.mean(numeric_only=True), inplace=True)

    print(
        f"  -> 중복/노이즈 변수 {len(collinear_drop_list)}개 제거 완료! (남은 피처 수: {len(df_clean.columns)})"
    )

    return df_clean


# ==============================================================================
# [Pipeline Step 2 - 동적 버전] 상관계수 기반 다중공선성 동적 제거 (권장)
# ==============================================================================
def step2_clean_and_drop_collinear_dynamic(df_agg, corr_threshold=0.85, protected_cols=None):
    print(f"\n🧹 [Step 2] 데이터 정제 및 다중공선성(상관계수 > {corr_threshold}) 변수 동적 제거 시작...")

    df_clean = df_agg.copy()

    # 1. 결측치 및 무한대 처리 (시계열 특성 반영: 선형 보간 → bfill)
    df_clean.replace([np.inf, -np.inf], np.nan, inplace=True)
    df_clean = df_clean.interpolate(method='time')
    df_clean.bfill(inplace=True)

    # 2. 보호해야 할 핵심 도메인 피처 (절대 자동 삭제되면 안 되는 변수들)
    whitelist = [
        # ── 기본 센서 (도메인 핵심값)
        "calculated_vpd_kpa", "mix_ec_ds_m", "mix_ph", "air_temp_c",
        "discharge_pressure_kpa", "flow_rate_l_min", "motor_power_kw",
        "pump_rpm", "motor_temperature_c",
        # ── 시간/주기
        "time_sin", "time_cos",
        # ── Spike 탐지 필수 (상관필터에서 절대 제거 금지)
        "pump_on", "pump_start_event", "is_startup_phase",
        "minutes_since_startup", "pressure_diff", "rpm_slope", "rpm_acc",
        # ── 환경 도메인 핵심
        "zone1_substrate_moisture_pct", "daily_light_integral_mol_m2_d",
    ]
    if protected_cols:
        whitelist = list(set(whitelist) | set(protected_cols))

    # 3. 상관계수 행렬 계산 (숫자형 변수만)
    corr_matrix = df_clean.select_dtypes(include=[np.number]).corr().abs()

    # 4. 상삼각행렬(Upper triangle) 추출 (자기 자신(1.0) 및 중복 비교 제거)
    upper = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))

    # 5. 임계값 초과 컬럼 탐색 → whitelist 구출
    to_drop = [column for column in upper.columns if any(upper[column] > corr_threshold)]
    final_drop_list = [col for col in to_drop if col not in whitelist]

    df_clean.drop(columns=final_drop_list, inplace=True, errors='ignore')

    print(f"  -> 동적 중복/노이즈 변수 {len(final_drop_list)}개 제거 완료!")
    print(f"  -> 삭제된 컬럼: {final_drop_list}")
    print(f"  -> 남은 피처 수: {len(df_clean.columns)}")

    return df_clean


# ==============================================================================
# [Pipeline Step 2.5] 오토인코더 학습용 '순수 정상 데이터' 추출
# ==============================================================================
def extract_normal_training_data(df_clean, df_interpret=None):
    """
    오토인코더가 '정상'만을 완벽히 학습할 수 있도록,
    고장이 의심되거나 물리적으로 비정상적인 극단치(Outlier)를 학습 데이터에서 아예 도려냅니다.

    df_interpret가 주어지면 is_anomaly_spike로 "startup 밖 spike"를 추가 제외합니다.
    startup 구간 내 spike(is_startup_spike=1)는 정상 과도 동작이므로 학습에 포함.
    """
    print(
        "\n🛡️ [Step 2.5] 오토인코더 학습을 위한 '순수 정상 범주' 데이터 필터링 시작..."
    )
    df_normal = df_clean.copy()
    initial_len = len(df_normal)

    # ----------------------------------------------------------------
    # 1. 도메인 규칙 기반 하드 필터링 (Domain Rules)
    # ----------------------------------------------------------------
    # 예시: 펌프 토출 압력이나 유량이 마이너스(-)인 물리적 오류 데이터 제거
    if "discharge_pressure_kpa" in df_normal.columns:
        df_normal = df_normal[df_normal["discharge_pressure_kpa"] >= 0]

    if "flow_rate_l_min" in df_normal.columns:
        df_normal = df_normal[df_normal["flow_rate_l_min"] >= 0]

    # ----------------------------------------------------------------
    # 2. 플래그 기반 이상 데이터 제외 (IQR 필터는 사용하지 않음)
    # ----------------------------------------------------------------
    # IQR 꼬리 자르기는 startup overshoot·야간 전환 같은 "정상 과도 패턴"까지 잘라내
    # AE가 매일 아침 startup을 이상으로 오판하게 됨. 따라서 사용 금지.
    # 대신 preprocessing에서 이미 생성한 명시적 플래그로 필터링:
    #   - is_anomaly_spike==1  : startup 밖에서 발생한 spike (비정상)
    #   - cleaning_event_flag==1 : 주기적 산 세척 이벤트 (학습 제외)
    # startup spike(is_startup_spike==1)는 정상 과도 구동이므로 **유지**.
    drop_mask = pd.Series(False, index=df_normal.index)
    if "cleaning_event_flag" in df_normal.columns:
        drop_mask |= df_normal["cleaning_event_flag"] == 1
    # is_anomaly_spike는 df_interpret에만 있으므로 인덱스로 조인해서 참조
    if df_interpret is not None and "is_anomaly_spike" in df_interpret.columns:
        spike = df_interpret["is_anomaly_spike"].reindex(df_normal.index).fillna(0)
        drop_mask |= spike == 1
    df_normal = df_normal[~drop_mask]

    final_len = len(df_normal)
    removed_len = initial_len - final_len

    print(f"  -> 초기 데이터: {initial_len}개")
    print(f"  -> ✂️ 비정상/극단치 데이터 {removed_len}개 제거 완료!")
    print(f"  -> 🌟 최종 학습용 정상 데이터: {final_len}개 남음")

    return df_normal
