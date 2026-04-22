# src/ko_labels.py
# 프론트 UI 표시용 한국어 라벨 사전.
# API 응답의 영어 키/이름 옆에 "한글명" 형태로 함께 실어 프론트 가독성 확보.
# docs/COLUMNS_REFERENCE.md 원본 기준.

DOMAIN_KO = {
    "motor":     "모터",
    "hydraulic": "유압/유량",
    "nutrient":  "양액",
    "zone_drip": "구역 점적",
}

ALARM_KO = {
    "Normal":                 "정상",
    "Normal (startup gated)": "정상(기동 억제)",
    "Caution 🔸":             "주의 🔸",
    "Warning 🟠":             "경고 🟠",
    "Critical 🔴":            "위험 🔴",
}

# 피처명 → 한글 라벨. zone 1/2/3는 모두 열거.
FEATURE_KO = {
    # 환경
    "light_ppfd_umol_m2_s":       "광량(PPFD)",
    "air_temp_c":                 "공기 온도",
    "relative_humidity_pct":      "상대 습도",
    "co2_ppm":                    "CO₂ 농도",
    "calculated_vpd_kpa":         "증기압 결손(VPD)",
    "daily_light_integral_proxy": "DLI 프록시",
    "daily_light_integral_mol_m2_d": "일 누적 광량(DLI)",
    # 원수/탱크
    "raw_tank_level_pct":              "원수 탱크 수위",
    "raw_water_temp_c":                "원수 온도",
    "tank_a_level_pct":                "A통 수위",
    "tank_b_level_pct":                "B통 수위",
    "acid_tank_level_pct":             "산 탱크 수위",
    "raw_tank_level_change_pct_per_min": "원수 탱크 수위 변화율",
    "tank_a_est_hours_to_empty":       "A통 고갈 예상시간",
    "tank_b_est_hours_to_empty":       "B통 고갈 예상시간",
    "acid_tank_est_hours_to_empty":    "산 탱크 고갈 예상시간",
    # 펌프·모터
    "pump_rpm":                  "펌프 RPM",
    "flow_rate_l_min":           "메인 유량",
    "flow_baseline_l_min":       "기준 유량",
    "suction_pressure_kpa":      "흡입 압력",
    "discharge_pressure_kpa":    "토출 압력",
    "motor_current_a":           "모터 전류",
    "motor_power_kw":            "모터 전력",
    "motor_temperature_c":       "모터 온도",
    "bearing_vibration_rms_mm_s": "베어링 진동 RMS",
    "bearing_temperature_c":     "베어링 온도",
    # 필터
    "filter_pressure_in_kpa":  "필터 입구 압력",
    "filter_pressure_out_kpa": "필터 출구 압력",
    "turbidity_ntu":           "탁도",
    "filter_delta_p_kpa":      "필터 차압",
    # 양액 조제
    "mix_target_ec_ds_m":   "조제 목표 EC",
    "mix_ec_ds_m":          "조제 현재 EC",
    "mix_target_ph":        "조제 목표 pH",
    "mix_ph":               "조제 현재 pH",
    "mix_temp_c":           "조제 탱크 온도",
    "mix_flow_l_min":       "조제 탱크 유량",
    "dosing_acid_ml_min":   "산 주입 속도",
    "drain_ec_ds_m":        "배액 EC",
    # 양액 파생
    "pid_error_ec":           "EC PID 오차",
    "pid_error_ph":           "pH PID 오차",
    "ph_instability_flag":    "pH 불안정 플래그",
    "salt_accumulation_delta": "염류 축적 델타",
    "ph_roll_mean_30":        "pH 30분 이동평균",
    "ph_trend_30":            "pH 30분 트렌드",
    # 압력·유량·전력 파생
    "differential_pressure_kpa": "차압(토출−흡입)",
    "pressure_diff":             "토출압 1분 변화",
    "flow_diff":                 "유량 1분 변화",
    "flow_drop_rate":            "유량 하락률",
    "hydraulic_power_kw":        "유효 수력 동력",
    "wire_to_water_efficiency":  "전기→수력 효율",
    "pressure_flow_ratio":       "압력/유량 비",
    "dp_per_flow":               "차압/유량",
    "pressure_per_power":        "압력/전력",
    "flow_per_power":            "유량/전력",
    "pressure_roll_mean_10":     "차압 10분 이동평균",
    "pressure_trend_10":         "차압 10분 트렌드",
    "flow_roll_mean_10":         "유량 10분 이동평균",
    "flow_trend_10":             "유량 10분 트렌드",
    "pressure_volatility":       "압력 변동성",
    "flow_cv":                   "유량 변동계수",
    # 온도·진동·RPM 파생
    "temp_slope_c_per_s":   "모터 온도 변화율",
    "rpm_slope":            "RPM 변화율",
    "rpm_acc":              "RPM 가속도",
    "rpm_stability_index":  "RPM 안정도 지수",
    # 펌프 상태·이벤트
    "pump_on":                 "펌프 가동 여부",
    "pump_start_event":        "펌프 기동 이벤트",
    "pump_stop_event":         "펌프 정지 이벤트",
    "minutes_since_startup":   "기동 후 경과(분)",
    "minutes_since_shutdown":  "정지 후 경과(분)",
    "is_startup_phase":        "기동 구간 플래그",
    "is_off_phase":            "정지 구간 플래그",
    # 시간 인코딩
    "minute_of_day": "하루 경과(분)",
    "time_sin":      "시간 sin",
    "time_cos":      "시간 cos",
    # 구역별 Raw + 파생 (zone 1/2/3)
    "zone1_flow_l_min":                "구역1 유량",
    "zone2_flow_l_min":                "구역2 유량",
    "zone3_flow_l_min":                "구역3 유량",
    "zone1_pressure_kpa":              "구역1 압력",
    "zone2_pressure_kpa":              "구역2 압력",
    "zone3_pressure_kpa":              "구역3 압력",
    "zone1_substrate_moisture_pct":    "구역1 배지 수분",
    "zone2_substrate_moisture_pct":    "구역2 배지 수분",
    "zone3_substrate_moisture_pct":    "구역3 배지 수분",
    "zone1_substrate_ec_ds_m":         "구역1 배지 EC",
    "zone2_substrate_ec_ds_m":         "구역2 배지 EC",
    "zone3_substrate_ec_ds_m":         "구역3 배지 EC",
    "zone1_substrate_ph":              "구역1 배지 pH",
    "zone2_substrate_ph":              "구역2 배지 pH",
    "zone3_substrate_ph":              "구역3 배지 pH",
    "zone1_resistance":                "구역1 배관 저항",
    "zone2_resistance":                "구역2 배관 저항",
    "zone3_resistance":                "구역3 배관 저항",
    "zone1_moisture_response_pct":     "구역1 수분 반응",
    "zone2_moisture_response_pct":     "구역2 수분 반응",
    "zone3_moisture_response_pct":     "구역3 수분 반응",
    "zone1_ec_accumulation":           "구역1 EC 축적",
    "zone2_ec_accumulation":           "구역2 EC 축적",
    "zone3_ec_accumulation":           "구역3 EC 축적",
    "supply_balance_index":            "공급 밸런스 지수",
    # 이벤트
    "cleaning_event_flag": "세척 이벤트 플래그",
}


def ko_feature(name: str) -> str:
    """피처명 → 한글 라벨. 매핑 없으면 영문 그대로 돌려준다."""
    return FEATURE_KO.get(name, name)


def ko_alarm(label: str) -> str:
    """알람 라벨 → 한글. 매핑 없으면 원본 그대로."""
    return ALARM_KO.get(label, label)


def ko_domain(name: str) -> str:
    """도메인 코드 → 한글. 매핑 없으면 원본 그대로."""
    return DOMAIN_KO.get(name, name)
