# train.py 는 1분단위의 데이터를 학습시켜야 성능이 우수함.

import os
import csv
import json
import joblib
import numpy as np
import pandas as pd
import tensorflow as tf
import time
from datetime import datetime
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input, Dense, Dropout
from tensorflow.keras.callbacks import EarlyStopping
from sklearn.preprocessing import MinMaxScaler


# 우리가 만들어둔 '메인 셰프(파이프라인 매니저)' 모듈 불러오기
from feature_selection import run_feature_selection_experiment
from logger import get_logger
from math_utils import calculate_sigma_thresholds
from model_builder import build_autoencoder
from utils import save_model_artifacts

# 로거 생성
logger = get_logger("TRAIN")


# ==============================================================================
# 실험 결과 기록 (리더보드 CSV)
# ==============================================================================
def save_experiment_to_csv(model_name, mse_mean, t_caut, t_warn, t_cri):
    """리더보드(CSV)에 실험 결과를 누적 저장합니다."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    csv_path = os.path.join(project_root, "logs", "experiment_board.csv")

    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    file_exists = os.path.isfile(csv_path)

    with open(csv_path, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(
                ["Date", "Domain", "Mean_MSE", "Threshold_Caution", "Threshold_Warning", "Threshold_Error"]
            )
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            model_name,
            round(mse_mean, 6),
            round(t_caut, 6),
            round(t_warn, 6),
            round(t_cri, 6),
        ])


# ==============================================================================
# 🛠️ [모델 학습 및 아티팩트 저장 통합 함수]
# ==============================================================================
def train_and_save_model(X_train_ae, model_name):
    """
    특정 도메인(예: motor, hydraulic)의 데이터를 받아
    독립적인 AutoEncoder 모델을 학습하고 아티팩트를 저장합니다.
    """
    start_time = time.time()

    logger.info(f"🚀 [{model_name.upper()}] 모델 파이프라인 시작")

    # 1. 데이터 스케일링
    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(X_train_ae)

    # 2. 모델 구조 설계 (AutoEncoder 모델 생성)
    logger.info("🧠 [Phase 5-2] 텐서플로우 AutoEncoder 모델 구조 설계...")
    autoencoder = build_autoencoder(input_dim=X_scaled.shape[1])

    # 3. 모델 학습
    logger.info("🚀 [Phase 5-3] AutoEncoder 모델 학습 시작...")
    early_stopping = EarlyStopping(
        monitor="val_loss", patience=10, restore_best_weights=True
    )

    # 시각화용 Loss 점수 저장을 위해 history 객체 수집
    history = autoencoder.fit(
        X_scaled,
        X_scaled,
        epochs=100,
        batch_size=64,
        validation_split=0.2,  # 데이터의 20%를 검증(Validation)용으로 자동 사용
        callbacks=[early_stopping],
        verbose=1,  # 딥러닝 진행바(Epoch)는 print 기반이므로 화면에만 나오고 로그엔 안 찍힙니다
    )

    # 4. 추론 및 시그마 임계값 계산 (math_utils.py 에게 외주)
    logger.info("🎯 [Phase 5-4] 이상 탐지 임계값(Threshold) 계산...")
    reconstructed = autoencoder.predict(X_scaled)
    mse_scores = np.mean(np.power(X_scaled - reconstructed, 2), axis=1)

    # 6-Sigma 기법
    """
    # 백분위수
    thresh_caution = np.percentile(mse_scores, 85)  # 상위 15% (주의)
    thresh_warning = np.percentile(mse_scores, 95)  # 상위 5%  (경고)
    thresh_critical = np.percentile(mse_scores, 99)  # 상위 1%  (치명)

    옵션 A (정석 3시그마): Caution=1, Warning=2, critical=3
    thresholds = calculate_sigma_thresholds(mse_scores, sigma_levels=(1, 2, 3))
    # thresholds_630 = calculate_topdown_sigma_thresholds(mse_scores, top_sigma=6, step=3)
    """

    # 옵션 B : Caution=2, Warning=3, critical=6
    thresholds = calculate_sigma_thresholds(mse_scores, sigma_levels=(2, 3, 6))

    logger.info(f"✅ 6-Sigma 236 임계값 설정 완료!")
    logger.info(f"  🔸 Caution(2σ): {thresholds['caution']:.6f}")
    logger.info(f"  🟠 Warning(3σ): {thresholds['warning']:.6f}")
    logger.info(f"  🔴 Critical(6σ): {thresholds['critical']:.6f}")

    # 5. 프론트엔드용 메타데이터(Config) 조립

    logger.info("💾 [Phase 5-5] 서버 배포용 아티팩트(Artifacts) 저장...")
    config = {
        "model_name": model_name,
        "features": X_train_ae.columns.tolist(),
        "threshold_caution": thresholds["caution"],
        "threshold_warning": thresholds["warning"],
        "threshold_critical": thresholds["critical"],
        "metrics": {
            "train_loss": [float(l) for l in history.history["loss"]],
            "val_loss": [float(l) for l in history.history["val_loss"]],
            "final_mse_mean": thresholds["mean"],
        },
        "feature_stds": X_train_ae.std().to_dict(),
    }

    # 6. 아티팩트 저장
    current_dir = os.path.dirname(os.path.abspath(__file__))
    save_dir = os.path.join(os.path.dirname(current_dir), "models")

    save_model_artifacts(autoencoder, scaler, config, model_name, save_dir)
    logger.info(f"✅ [{model_name.upper()}] 학습 및 아티팩트 저장 완료! ({save_dir})")

    # 7. 실험 기록 및 메모리 정리
    save_experiment_to_csv(
        model_name=model_name,
        mse_mean=thresholds["mean"],
        t_caut=thresholds["caution"],
        t_warn=thresholds["warning"],
        t_cri=thresholds["critical"],
    )

    end_time = time.time()
    logger.info(
        f"⏱️ 모델링 소요 시간: {int((end_time - start_time) // 60)}분 {(end_time - start_time) % 60:.2f}초"
    )
    # 🌟 메모리 누수 방지: 학습 완료 후 텐서플로우 세션 정리
    tf.keras.backend.clear_session()
    return None


# ==============================================================================
# ⚔️ [메인 실행 블록]
# ==============================================================================
if __name__ == "__main__":
    total_start_time = time.time()
    logger.info("🏁 [MAIN] 다중 도메인(Multi-Domain) 예지보전 AI 파이프라인 학습 시작")

    # 🌟 [수정됨] 경로 하드코딩 제거 -> 동적 경로 탐색 로직 적용
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)

    # /Users/... 대신 project_main_folder/data 폴더를 찾아가도록 설정
    # (주의: 파일명은 주니어님이 사용하시는 데이터 파일명과 정확히 맞춰주세요)
    data_filename = (
        "/Users/jun/GitStudy/human_A/data/generated_data_from_dabin_0420.csv"
    )
    data_path = os.path.join(project_root, "data", data_filename)

    logger.info(f"📂 데이터 로딩 경로: {data_path}")
    df_raw = pd.read_csv(data_path)

    # 🌟 [추가] timestamp 컬럼을 datetime 형으로 바꾸고 인덱스로 설정!
    df_raw["timestamp"] = pd.to_datetime(df_raw["timestamp"])
    df_raw = df_raw.set_index("timestamp")

    # 🌟 서브시스템별로 타겟 딕셔너리를 묶어서 정의합니다.
    # 각 도메인 성격에 맞는 타겟들을 지정해 주면 훨씬 똑똑한 피처가 뽑힙니다.
    subsystem_targets = {
        "motor": {
            "motor_current_a": [
                "motor_power_kw",
                "motor_temperature_c",
                "wire_to_water_efficiency",
                "bearing_vibration_rms_mm_s"
            ],
            "rpm_stability_index": ["pump_rpm"],
        },
        "hydraulic": {  # 수력/압력/유량 도메인
            "zone1_resistance": ["zone1_pressure_kpa", "zone1_flow_l_min"],
            "differential_pressure_kpa": [
                "discharge_pressure_kpa",
                "suction_pressure_kpa",
            ],
        },
        "nutrient": {  # 양액/수질/환경 도메인
            "pid_error_ec": ["mix_ec_ds_m", "mix_target_ec_ds_m"],
            "salt_accumulation_delta": ["drain_ec_ds_m", "mix_ec_ds_m"],
        },
        "zone_drip": {  # 구역 점적 시스템 도메인
            "zone1_moisture_response_pct": ["zone1_substrate_moisture_pct"],
            "zone1_ec_accumulation": ["zone1_substrate_ec_ds_m", "mix_ec_ds_m"],
        },
    }

    # 🌟 [수정포인트 4] For 루프를 돌면서 각각 독립적인 모델을 학습시킵니다.
    for system_name, target_dict in subsystem_targets.items():
        logger.info(f"[{system_name.upper()} 도메인] 분석 파이프라인 시작")

        # 1. 도메인별 피처 셀렉션
        robust_features, X_train_ae, df_interpret_result, _ = run_feature_selection_experiment(
            df_raw=df_raw, window_method="sliding", target_dict=target_dict
        )

        # VIP 피처 강제 주입 (time_sin/time_cos 가 SHAP 선택에서 빠졌을 때 보완)
        vip_cols = ["time_sin", "time_cos"]

        missing_vips = [
            col
            for col in vip_cols
            if col not in X_train_ae.columns and col in df_interpret_result.columns
        ]

        if missing_vips:
            logger.info(
                f"🔗 오토인코더 입력 데이터에 VIP 피처 강제 주입: {missing_vips}"
            )
            time_features = df_interpret_result[missing_vips]
            X_train_ae = pd.concat([X_train_ae, time_features], axis=1)

        # 2. 도메인별 모델 학습 및 저장 (이름을 같이 넘겨줌)
        train_and_save_model(X_train_ae, model_name=system_name)

    total_end_time = time.time()
    t_min, t_sec = divmod(total_end_time - total_start_time, 60)
    logger.info(
        "🎉 모든 서브시스템(Motor, Hydraulic, Nutrient, Zone Drip)의 모델 학습이 성공적으로 종료되었습니다!"
    )
    logger.info(
        f"🏆 전체 파이프라인 구동 완료! (총 소요 시간: {int(t_min)}분 {t_sec:.2f}초)"
    )
