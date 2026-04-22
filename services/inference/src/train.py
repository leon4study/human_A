# train.py
import os
import json
import joblib
import numpy as np
import pandas as pd
import tensorflow as tf
import time
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input, Dense, Dropout
from tensorflow.keras.callbacks import EarlyStopping
from sklearn.preprocessing import MinMaxScaler


# 우리가 만들어둔 '메인 셰프(파이프라인 매니저)' 모듈 불러오기
from feature_selection import run_feature_selection_experiment
from logger import get_logger, save_experiment_to_csv

# 로거 생성
logger = get_logger("TRAIN")


# ==============================================================================
# 🛠️ [모델 학습 및 아티팩트 저장 통합 함수]
# ==============================================================================
def train_and_save_model(X_train_ae, model_name):
    """
    특정 도메인(예: motor, hydraulic)의 데이터를 받아
    독립적인 AutoEncoder 모델을 학습하고 아티팩트를 저장합니다.
    """
    start_time = time.time()

    logger.info(f"🚀 [{model_name.upper()}] 모델 학습 및 저장 프로세스 시작")

    # 1. 데이터 스케일링
    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(X_train_ae)

    logger.info("🧠 [Phase 5-2] 텐서플로우 AutoEncoder 모델 구조 설계...")
    # 2. 모델 구조 설계 (입력 차원에 따라 병목 층 자동 조절 가능)
    input_dim = X_scaled.shape[1]
    input_layer = Input(shape=(input_dim,))

    # 도메인별 피처 수에 따라 유연하게 대응 (최소 2개 노드 보장)
    bottleneck_size = max(2, input_dim // 2)

    # 인코더 (Encoder)
    encoded = Dense(8, activation="relu")(input_layer)
    encoded = Dropout(0.1)(encoded)  # 과적합 방지 및 특정 센서 과의존 방지
    encoded = Dense(bottleneck_size, activation="relu")(
        encoded
    )  # 🌟 병목(Bottleneck) 동적 적용

    # 디코더 (Decoder)
    decoded = Dense(8, activation="relu")(encoded)
    output_layer = Dense(input_dim, activation="sigmoid")(decoded)

    autoencoder = Model(inputs=input_layer, outputs=output_layer)
    autoencoder.compile(optimizer="adam", loss="mse")

    logger.info("🚀 [Phase 5-3] AutoEncoder 모델 학습 시작...")
    early_stopping = EarlyStopping(
        monitor="val_loss", patience=10, restore_best_weights=True
    )

    autoencoder.fit(
        X_scaled,
        X_scaled,
        epochs=100,
        batch_size=64,
        validation_split=0.2,  # 데이터의 20%를 검증(Validation)용으로 자동 사용
        callbacks=[early_stopping],
        verbose=1,  # 딥러닝 진행바(Epoch)는 print 기반이므로 화면에만 나오고 로그엔 안 찍힙니다
    )

    logger.info("🎯 [Phase 5-4] 이상 탐지 3단계 임계값(Threshold) 설정...")
    reconstructed = autoencoder.predict(X_scaled)
    mse_scores = np.mean(np.power(X_scaled - reconstructed, 2), axis=1)

    # 🌟 [수정됨] 노트북 로직 반영: 3단계 임계값을 모두 계산합니다.
    thresh_caution = np.percentile(mse_scores, 85)  # 상위 15% (주의)
    thresh_warning = np.percentile(mse_scores, 95)  # 상위 5%  (경고)
    thresh_error = np.percentile(mse_scores, 99)  # 상위 1%  (위험/에러)

    logger.info(f"✅ 오토인코더 학습 완료!")
    logger.info(f"  -> 정상 데이터 평균 오차: {np.mean(mse_scores):.6f}")
    logger.info(f"  🔸 Caution(85%) 기준점: {thresh_caution:.6f}")
    logger.info(f"  🟠 Warning(95%) 기준점: {thresh_warning:.6f}")
    logger.info(f"  🔴 Error(99%)   기준점: {thresh_error:.6f}")

    logger.info("💾 [Phase 5-5] 서버 배포용 아티팩트(Artifacts) 저장...")
    # 동적 절대 경로 설정 (어디서 실행하든 꼬이지 않음)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    save_dir = os.path.join(project_root, "models")

    # 저장할 디렉토리가 없다면 생성
    os.makedirs(save_dir, exist_ok=True)

    # (1) 모델 저장
    autoencoder.save(os.path.join(save_dir, f"{model_name}_model.keras"))

    # (2) 스케일러 저장
    joblib.dump(scaler, os.path.join(save_dir, f"{model_name}_scaler.pkl"))

    # (3) 설정(Config) 저장
    # 🌟 [수정됨] inference_api.py에서 쓰기 위해 3단계 임계값을 모두 넘겨줍니다!
    config = {
        "model_name": model_name,
        "threshold_caution": float(thresh_caution),
        "threshold_warning": float(thresh_warning),
        "threshold_error": float(thresh_error),
        "features": X_train_ae.columns.tolist(),
    }
    with open(
        os.path.join(save_dir, f"{model_name}_config.json"), "w"
    ) as f:  # 🌟 파일명 변경
        json.dump(config, f)

    logger.info(
        f"✅ [{model_name.upper()}] 학습 및 저장 완료! ({save_dir} 위치에 아티팩트 생성됨)"
    )
    save_experiment_to_csv(
        model_name=model_name,
        mse_mean=np.mean(mse_scores),
        t_caut=thresh_caution,
        t_warn=thresh_warning,
        t_err=thresh_error,
    )

    end_time = time.time()
    minutes, seconds = divmod(end_time - start_time, 60)
    logger.info(
        f"⏱️ [{model_name.upper()}] 모델 생성 총 소요 시간: {int(minutes)}분 {seconds:.2f}초"
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

    logger.info("🏁 [MAIN] 다중 도메인(Multi-Domain) 예지보전 AI 파이프라인 학습 시작")

    # 🌟 [수정됨] 경로 하드코딩 제거 -> 동적 경로 탐색 로직 적용
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)

    # /Users/... 대신 project_main_folder/data 폴더를 찾아가도록 설정
    # (주의: 파일명은 주니어님이 사용하시는 데이터 파일명과 정확히 맞춰주세요)
    data_filename = "smartfarm_nutrient_pump_rawdata_3months_clog_focus_v2_stronger.csv"
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
        }
    }

    # 🌟 [수정포인트 4] For 루프를 돌면서 각각 독립적인 모델을 학습시킵니다.
    for system_name, target_dict in subsystem_targets.items():
        logger.info(f"[{system_name.upper()} 도메인] 분석 파이프라인 시작")

        # 1. 도메인별 피처 셀렉션
        robust_features, X_train_ae, _, _ = run_feature_selection_experiment(
            df_raw=df_raw, window_method="sliding", target_dict=target_dict
        )

        # 2. 도메인별 모델 학습 및 저장 (이름을 같이 넘겨줌)
        train_and_save_model(X_train_ae, model_name=system_name)

    total_end_time = time.time()
    t_min, t_sec = divmod(total_end_time - total_start_time, 60)
    logger.info(
        "🎉 모든 서브시스템(Motor, Hydraulic, Nutrient)의 모델 학습이 성공적으로 종료되었습니다!"
    )
    logger.info(
        f"🏆 전체 파이프라인 구동 완료! (총 소요 시간: {int(t_min)}분 {t_sec:.2f}초)"
    )
