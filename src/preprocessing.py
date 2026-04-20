# 오직 Pandas를 이용해서 데이터를 지지고 볶는 '순수 데이터 전처리' 함수들만 모아둡니다.
# - filter_active_periods (유효 데이터 필터링)
# - create_modeling_features (도메인 파생변수 생성)
# - aggregate_time_window (슬라이딩 윈도우 집계)
# - step1_prepare_window_data (Step 1 조립)
# - step2_clean_and_drop_collinear (Step 2 정제)

# 💻 스마트팜 예지보전 데이터 전처리 및 피처 엔지니어링 파이프라인


import pandas as pd
import numpy as np
import time

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


def create_modeling_features(df):
    """
    파생변수 생성 함수입니다.
    이 함수는 10분 단위 집계(Aggregation)를 하기 전, 1분 단위 Raw Data 상태에서 실행해야 가장 정확합니다.
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

    # 유량 감소율 (Flow Drop Rate)
    # 정상적인 기준치 대비 현재 유량이 얼마나 줄었는지 백분율로 나타냅니다.
    # [Rule] 유량이 급감(-)하면 공압, 실린더, 배관 막힘 등 물리적 저항이 발생했음을 의미합니다.
    # baseline은 최근 1시간(60분) 이동평균으로 설정
    df_feat["flow_baseline_l_min"] = (
        df_feat["flow_rate_l_min"].rolling(window=60, min_periods=1).mean().shift(1)
    )
    df_feat["flow_drop_rate"] = (
        df_feat["flow_baseline_l_min"] - df_feat["flow_rate_l_min"]
    ) / (df_feat["flow_baseline_l_min"] + eps)

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

    #"펌프가 켜진 지 몇 분 지났는가?" (Time Since Startup)
    # 펌프가 꺼져있으면 0, 켜지면 1, 2, 3... 분 단위로 카운트가 올라갑니다.
    # 이렇게 하면 AI가 "아! 켜진 직후 1~5분 사이에는 값이 튀는 게 정상이구나!" 라고 완벽히 학습합니다.
    pump_status = df_feat["pump_on"] # (실제 펌프 가동 여부를 나타내는 컬럼명 사용)
    # 펌프가 꺼지면 그룹을 나누기 위한 트릭
    pump_group = (pump_status != pump_status.shift()).cumsum()
    
    # 펌프가 켜져 있을 때만 누적 카운트 (꺼져있으면 0)
    df_feat["minutes_since_startup"] = df_feat.groupby(pump_group).cumcount()
    df_feat["minutes_since_startup"] = df_feat["minutes_since_startup"] * pump_status
    
    # [옵션] 가동 초기(Transient) 플래그: 켜진 직후 10분 이내인가? (1/0)
    df_feat["is_startup_phase"] = ((df_feat["minutes_since_startup"] > 0) & 
                                (df_feat["minutes_since_startup"] <= 5)).astype(int)
    
    # =====================================================================
    # 2. 온도 & 진동 동특성 지표
    # =====================================================================
    # 초당 모터 온도 변화율 (Temperature Slope)
    # 1초당 온도가 몇 도(℃) 상승/하강하는지 나타냅니다.
    # [Rule] 모터나 베어링이 갈리거나 장기적으로 막혀 부하가 심해지면, 온도가 서서히 올라가며 이 값이 지속적인 양수(+)를 띕니다.
    df_feat["temp_slope_c_per_s"] = df_feat["motor_temperature_c"].diff() / dt_seconds

    # RPM 안정성 지수 (RPM Stability Index)
    # 목표 RPM(또는 평균 RPM) 대비 현재 RPM의 떨림 정도입니다. (여기서는 직전 10분 평균 대비 차이로 계산)
    # [Rule] 펌프에 공기가 차거나 난류가 발생하면 RPM이 목표값을 유지하지 못하고 요동칩니다.
    rpm_mean = df_feat["pump_rpm"].rolling(window=10, min_periods=1).mean()
    df_feat["rpm_stability_index"] = np.abs(df_feat["pump_rpm"] - rpm_mean) / (
        rpm_mean + eps
    )

    # =====================================================================
    # 3. 양액/수질 및 환경 고도화 지표
    # =====================================================================
    # 제어기 목표 추종 오차 (PID Error EC / pH)
    # 기계가 목표로 한 EC/pH 값과 실제 섞여서 나온 값의 차이입니다.
    # [Rule] 오차가 지속적으로 크면 조제기 밸브 노후화, 산/비료 원액 고갈, 혼합 모터 고장을 의미합니다.
    df_feat["pid_error_ec"] = df_feat["mix_ec_ds_m"] - df_feat["mix_target_ec_ds_m"]
    df_feat["pid_error_ph"] = df_feat["mix_ph"] - df_feat["mix_target_ph"]

    # pH 불안정성 (침전 발생 임계점 6.5 초과 여부)
    # 배관 막힘의 주원인인 '칼슘/인산 침전'이 발생하는 pH 6.5 이상의 위험 상태를 플래그(1/0)로 만듭니다.
    # [Rule] 이 플래그가 켜진 상태가 오래 유지되면, 곧 배관이 막힌다는 강력한 예지 시그널입니다.
    df_feat["ph_instability_flag"] = (df_feat["mix_ph"] > 6.5).astype(np.int8)

    # 누적 염분 부하량 추정치 (Cumulative Salt Load)
    # 배지에서 빠져나오는 배액 EC와 들어가는 공급 EC의 차이를 의미합니다.
    # [Rule] 배액 EC가 공급 EC보다 지속적으로 높으면 염류가 축적(막힘 유발)되고, 낮으면 식물이 영양결핍 상태입니다.
    df_feat["salt_accumulation_delta"] = (
        df_feat["drain_ec_ds_m"] - df_feat["mix_ec_ds_m"]
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

    return df_feat


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
    # 1. 전체 숫자형 컬럼 및 센서/시간 컬럼 분리
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    time_cols = ["minute_of_day", "time_sin", "time_cos"]
    sensor_cols = [col for col in numeric_cols if col not in time_cols]

    if method == "tumbling":
        # 🌟 텀블링: resample은 'last'를 지원하므로 딕셔너리 방식 사용
        agg_dict = {col: "mean" for col in sensor_cols}
        for t_col in time_cols:
            if t_col in df.columns:
                agg_dict[t_col] = "last"
        df_agg = df.resample(window_size).agg(agg_dict)

    elif method == "sliding":
        # 🌟 슬라이딩: rolling은 센서 데이터만 평균 계산! (연산 속도 최적화)
        df_agg = df[sensor_cols].rolling(window=window_size).mean()

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

    return df_interpret


# ==============================================================================
# [Pipeline Step 1] 파생변수 생성 및 윈도우 집계
# ==============================================================================
def step1_prepare_window_data(df_raw, window_method="sliding"):
    print(f"⏳ [Step 1] 파생변수 생성 및 {window_method.upper()} 윈도우 집계 시작...")

    # 1. 로우 데이터에서 물리적 파생변수 생성 (공통)
    df_features = create_modeling_features(df_raw)

    # 2. 윈도우 집계 (인자에 따라 다르게 동작)
    if window_method == "sliding":
        df_agg = aggregate_time_window(
            df_features, method="sliding", window_size="10min", slide_step="1min"
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
# [Pipeline Step 2.5] 오토인코더 학습용 '순수 정상 데이터' 추출
# ==============================================================================
def extract_normal_training_data(df_clean):
    """
    오토인코더가 '정상'만을 완벽히 학습할 수 있도록,
    고장이 의심되거나 물리적으로 비정상적인 극단치(Outlier)를 학습 데이터에서 아예 도려냅니다.
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
    # 2. 통계적 이상치 제거 (IQR 방식을 적용한 꼬리 자르기)
    # ----------------------------------------------------------------
    # 오토인코더의 학습을 방해하는 극단적인 '튐(Spike)' 현상을 통계적으로 잘라냅니다.
    # 모델에 들어갈 모든 숫자형 변수에 대해 깐깐하게 검사합니다.
    numeric_cols = df_normal.select_dtypes(include=[np.number]).columns

    # 시간 관련 피처(원형 데이터)는 이상치 개념이 없으므로 제외
    exclude_cols = ["minute_of_day", "time_sin", "time_cos"]
    check_cols = [col for col in numeric_cols if col not in exclude_cols]

    for col in check_cols:
        # 상하위 5%, 95%를 기준으로 삼아 너무 빡빡하지 않게 이상치를 잡습니다.
        Q1 = df_normal[col].quantile(0.05)
        Q3 = df_normal[col].quantile(0.95)
        IQR = Q3 - Q1

        # IQR의 1.5배를 벗어나는 값은 '정상 범주를 벗어난 고장 데이터'로 간주하고 날립니다.
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR

        # 정상 범위 안에 있는 데이터만 남깁니다.
        df_normal = df_normal[
            (df_normal[col] >= lower_bound) & (df_normal[col] <= upper_bound)
        ]

    final_len = len(df_normal)
    removed_len = initial_len - final_len

    print(f"  -> 초기 데이터: {initial_len}개")
    print(f"  -> ✂️ 비정상/극단치 데이터 {removed_len}개 제거 완료!")
    print(f"  -> 🌟 최종 학습용 정상 데이터: {final_len}개 남음")

    return df_normal
