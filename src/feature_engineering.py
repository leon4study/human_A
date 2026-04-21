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
