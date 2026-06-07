# src/feature_engineering.py
"""
피처 엔지니어링 레이어 (모델 무관).

Dense AE / LSTM-AE 어느 쪽으로 가도 재사용되도록 Scaler 앞단 변환만 둡니다.
현재는 'SHAP이 놓치기 쉬운 운전 모드 피처'를 AE 입력에 강제 주입하는 헬퍼만 제공.
"""
from __future__ import annotations

import pandas as pd


# preprocessing.py가 이미 생성·집계하는 운전 모드 피처들 (Canonical 정의).
# 기동/정지 스파이크를 '맥락 있는 정상'으로 학습시키려면 AE 입력에 반드시 포함되어야 함.
#
# ⚠️ 희소 binary 피처(예: is_startup_phase 0.7%)는 그대로 넣지 말 것.
# AE는 다수 클래스(0)에만 맞춰 학습 → 추론 시 1 들어오면 복원 오차가 다른 피처의 100배로
# 폭발해 MSE와 RCA를 독점한다. (2026-04-20 Phase A 1차 실험에서 확인됨.)
# 맥락은 연속값(minutes_since_startup)으로 충분히 전달되므로 binary는 분포 균형 맞는 것만.
MODE_FEATURES: list[str] = [
    "pump_on",                 # 펌프 on/off 이진 (50:50 분포 → 학습 안전)
    "minutes_since_startup",   # 기동 후 경과 분 (연속값, 기동 맥락의 핵심 정보원)
    # ----------------------------------------------------------------------
    # 🛑 Phase A 1차에서 제거된 피처들 — 아래 전제 조건이 충족될 때만 재활성화.
    #
    # "is_startup_phase",       # 기동 직후 5분 플래그. 희소 0.7% → AE 독성.
    #   재활성화 조건:
    #     (a) sample_weight로 is_startup_phase=1 구간에 가중치 부여, 또는
    #     (b) 기동 구간을 oversampling하여 클래스 비율 ≥ 10%로 맞춘 뒤.
    #
    # "is_off_phase",           # 정지 유지 플래그. pump_on=0과 정보 중복.
    #   재활성화 조건:
    #     - pump_on을 빼고 is_off_phase만 쓰기로 결정하거나,
    #     - 정지 모드의 다양성(예: 정상 정지 vs 비상 정지)을 세분화할 때.
    # ----------------------------------------------------------------------
]

# 기존 train.py가 관리하던 시간 피처 + 모드 피처를 한 곳에 모아 둔 VIP 리스트.
VIP_FEATURES: list[str] = ["time_sin", "time_cos"] + MODE_FEATURES


# 도메인별 "반드시 모델 입력에 들어가야 하는" 센서·파생 피처.
# SHAP robust selection이 빈 결과를 반환해도 이 리스트는 강제 주입되어,
# AE가 시간·상태 피처만으로 학습되는 퇴행을 막는다.
#
# 규칙:
# - 각 도메인 타깃 컬럼은 leakage 방지를 위해 입력 피처로 넣지 않음.
# - zone 2·3은 preprocessing에서 drop되므로 zone1만 사용.
# - 파생이 원본보다 신호 대 잡음비가 좋을 때는 파생을 우선 (예: rpm_slope > pump_rpm).
SENSOR_MANDATORY: dict[str, list[str]] = {
    "motor": [
        "motor_power_kw",
        "motor_temperature_c",
        "bearing_vibration_rms_mm_s",
        "bearing_temperature_c",
        "wire_to_water_efficiency",
        "pump_rpm",
        "rpm_slope",
        "temp_slope_c_per_s",
        # 피처 1차 배치 (09 원장 §3-4)
        "bearing_thermal_margin",
        "load_per_speed",
        # §7 관계 피처(12 §7·§8) — 부하 정규화 진동, 베어링 마모 직격(ISO 10816 기반)
        "vibration_per_load",
    ],
    "hydraulic": [
        "flow_rate_l_min",
        "discharge_pressure_kpa",
        "suction_pressure_kpa",
        "flow_drop_rate",
        "pressure_flow_ratio",
        "pressure_trend_10",
        "flow_trend_10",
        # 유령 mandatory 제거(2026-06-07): hydraulic_power_kw·filter_delta_p_kpa는 raw에 없어
        # "df_agg에 없는 피처" 경고만 냈음. 필터는 룰기반 도메인이라 filter_delta_p 불필요.
        # 피처 1차 배치 (09 원장 §3-2) — 막힘 직격
        "system_resistance",
        "specific_energy",
        # §7 관계 피처(12 §7·§8) — 환경 기대 수요(VPD×광량). flow와의 어긋남으로 막힘 포착
        "transpiration_demand",
        # 도메인 경계 정리(2026-06-02): supply_balance_index는 유량 균형 지표(구역합/메인,
        # 누수 탐지)라 유량 성격 → zone_drip에서 hydraulic으로 이동. docs/DOMAIN_DESIGN.md.
        "supply_balance_index",
    ],
    "nutrient": [
        "mix_ph",
        "mix_ec_ds_m",
        "mix_target_ec_ds_m",
        "drain_ec_ds_m",
        "pid_error_ph",
        "mix_temp_c",
        "ph_trend_30",
        # §7 관계 피처(12 §7·§8) — 배액/공급 EC 비. >1 누적 = 염류 축적(공공데이터 근거)
        "leaching_ratio",
    ],
    "zone_drip": [
        # 구역 배지(substrate) 상태 도메인 — 말단 각 구역의 뿌리 환경(수분·EC). docs/DOMAIN_DESIGN.md.
        #   배지 수분/EC는 펌프와 무관한 구역 고유 정보(Critical). 펌프 중복인 zone 압력/유량은 제외(공선성).
        #   유량 균형 지표(supply_balance_index)는 유량 성격이라 hydraulic으로 이동(2026-06-02 경계 정리).
        "zone1_substrate_moisture_pct",
        "zone1_substrate_ec_ds_m",
        # 피처 1차 배치 (09 원장 §3-1) — 구역 간 편차·집적속도로 국부 막힘/염해 탐지
        "zone_ec_variance",
        "zone_moisture_variance",
        "substrate_ec_accum_rate",
    ],
}


# ── 자유 파생피처의 도메인 소유권 + 도메인별 채점 제외(조건부 마스크) ──────────
# [배경] 각 도메인 AutoEncoder는 '입력은 넓게(인코더가 교차상관 활용), 채점은 좁게(그 도메인이
#   책임지는 신호만 알람 트리거)' 구조다(MODELING §5-2-1, 근거: Conditional Anomaly Detection).
#   시간·상태 컨텍스트는 inference_core.DEFAULT_CONTEXT_FEATURES로 이미 채점에서 빠진다.
# [문제] pressure_diff·flow_diff처럼 '어느 SENSOR_MANDATORY에도 안 잡힌 자유 파생피처'는
#   소유 도메인이 없어, SHAP이 엉뚱한 도메인(예: motor)에 배정하면 그 도메인 채점을 오염시켜
#   헛알람(FAR↑)을 낸다. DOMAIN_ISOLATION은 mandatory 원천센서만 막아 이들을 못 막는다.
# [해법] 자유 파생피처에 소유 도메인을 명시하고, 소유가 아닌 도메인에서는 '입력 유지 + 채점 제외'.
#   (제거가 아니라 채점 마스크에서만 빼므로 인코더가 쓰는 교차상관 신호는 보존된다.)
DERIVED_FEATURE_OWNER: dict[str, str] = {
    "pressure_diff": "hydraulic",   # 토출-흡입 차압 = 수력 도메인 물리량
    "flow_diff": "hydraulic",       # 유량 차분 = 수력 도메인 물리량
}

# 환경 컨텍스트(전 도메인 입력 전용): 계절성 외생 드리프트라 '어느 서브시스템의 고장 지표'도 아니다.
# 입력으로 조건짓되 채점에서는 빼 헛알람을 막는다(시간·상태 컨텍스트와 같은 취급).
ENVIRONMENT_CONTEXT: frozenset = frozenset({"air_temp_c"})


def _feature_owner_map() -> dict:
    """피처 -> 소유 도메인 맵. SENSOR_MANDATORY(도메인별 원천센서) ∪ DERIVED_FEATURE_OWNER(자유 파생)."""
    owner: dict = dict(DERIVED_FEATURE_OWNER)
    for dom, feats in SENSOR_MANDATORY.items():
        for f in feats:
            owner.setdefault(f, dom)
    return owner


def foreign_scoring_features(domain: str, features) -> set:
    """`domain`의 피처 목록 중, 이 도메인 채점(MSE 점수)에서 빼야 할 '외래' 피처 집합을 반환.

    제외 대상:
      - 환경 컨텍스트(ENVIRONMENT_CONTEXT): 어느 도메인 채점에도 부적합한 외생 드리프트.
      - 타 도메인 소유 피처: 소유가 명시됐는데 이 도메인이 아닌 경우(예: motor에 섞인 hydraulic pressure_diff).
    건드리지 않는 것: 이 도메인 소유 피처, 그리고 소유가 명시되지 않은 공용 파생피처(보수적 유지).
    반환된 피처는 '입력에는 남고 채점에서만' 빠진다(조건부 마스크).
    """
    owner = _feature_owner_map()
    foreign = set()
    for f in features:
        if f in ENVIRONMENT_CONTEXT:
            foreign.add(f)
        elif owner.get(f, domain) != domain:   # 소유가 명시됐고(맵에 있고) 내 도메인이 아니면 외래
            foreign.add(f)
    return foreign


def inject_vip_features(
    X_train_ae: pd.DataFrame,
    df_interpret: pd.DataFrame,
    vip_list: list[str] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """SHAP 선택에서 빠졌더라도 필수 피처(vip)를 AE 입력에 강제 주입한다.

    Parameters
    ----------
    X_train_ae : SHAP이 고른 AE 입력 DataFrame.
    df_interpret : 전처리 해석용 DataFrame (모드/시간 원본 피처 소스).
    vip_list : 주입할 피처 이름 리스트. 기본값은 VIP_FEATURES.

    Returns
    -------
    (X_train_ae_with_vip, injected_cols) — 주입 후 DataFrame과 실제 주입된 컬럼 리스트.
    """
    if vip_list is None:
        vip_list = VIP_FEATURES

    missing = [
        col
        for col in vip_list
        if col not in X_train_ae.columns and col in df_interpret.columns
    ]
    if not missing:
        return X_train_ae, []

    injected = df_interpret[missing]
    return pd.concat([X_train_ae, injected], axis=1), missing
