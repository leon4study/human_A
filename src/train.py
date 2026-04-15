# train.py
import os
import json
import joblib
import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input, Dense, Dropout
from tensorflow.keras.callbacks import EarlyStopping
from sklearn.preprocessing import MinMaxScaler

# 우리가 만들어둔 '메인 셰프(파이프라인 매니저)' 모듈 불러오기
from feature_selection import run_feature_selection_experiment


# ==============================================================================
# 🛠️ [모델 학습 및 아티팩트 저장 통합 함수]
# ==============================================================================
def train_and_save_model(X_train_ae, df_interpret):
    """
    AE용 최종 데이터(X_train_ae)를 받아 스케일링, 모델 설계, 학습, 임계값 계산 후
    서버 배포용 아티팩트를 저장하는 함수입니다.
    """
    print("\n🛠️ [Phase 5-1] 데이터 스케일링 시작...")
    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(X_train_ae)

    print("\n🧠 [Phase 5-2] 텐서플로우 AutoEncoder 모델 구조 설계...")
    input_dim = X_scaled.shape[1]

    # 인코더 (Encoder)
    input_layer = Input(shape=(input_dim,))
    encoded = Dense(8, activation="relu")(input_layer)
    encoded = Dropout(0.1)(encoded)  # 과적합 방지 및 특정 센서 과의존 방지
    encoded = Dense(4, activation="relu")(encoded)  # 병목(Bottleneck)

    # 디코더 (Decoder)
    decoded = Dense(8, activation="relu")(encoded)
    output_layer = Dense(input_dim, activation="sigmoid")(decoded)

    autoencoder = Model(inputs=input_layer, outputs=output_layer)
    autoencoder.compile(optimizer="adam", loss="mse")

    print("\n🚀 [Phase 5-3] AutoEncoder 모델 학습 시작...")
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
        verbose=1,
    )

    print("\n🎯 [Phase 5-4] 이상 탐지 3단계 임계값(Threshold) 설정...")
    reconstructed = autoencoder.predict(X_scaled)
    mse_scores = np.mean(np.power(X_scaled - reconstructed, 2), axis=1)

    # 🌟 [수정됨] 노트북 로직 반영: 3단계 임계값을 모두 계산합니다.
    thresh_caution = np.percentile(mse_scores, 85)  # 상위 15% (주의)
    thresh_warning = np.percentile(mse_scores, 95)  # 상위 5%  (경고)
    thresh_error = np.percentile(mse_scores, 99)  # 상위 1%  (위험/에러)

    print(f"✅ 오토인코더 학습 완료!")
    print(f"  -> 정상 데이터 평균 오차: {np.mean(mse_scores):.6f}")
    print(f"  🔸 Caution(85%) 기준점: {thresh_caution:.6f}")
    print(f"  🟠 Warning(95%) 기준점: {thresh_warning:.6f}")
    print(f"  🔴 Error(99%)   기준점: {thresh_error:.6f}")

    print("\n💾 [Phase 5-5] 서버 배포용 아티팩트(Artifacts) 저장...")
    # 동적 절대 경로 설정 (어디서 실행하든 꼬이지 않음)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    save_dir = os.path.join(project_root, "models")

    # 저장할 디렉토리가 없다면 생성
    os.makedirs(save_dir, exist_ok=True)

    # (1) 모델 저장
    autoencoder.save(os.path.join(save_dir, "model.keras"))

    # (2) 스케일러 저장
    joblib.dump(scaler, os.path.join(save_dir, "scaler.pkl"))

    # (3) 설정(Config) 저장
    # 🌟 [수정됨] inference_api.py에서 쓰기 위해 3단계 임계값을 모두 넘겨줍니다!
    config = {
        "threshold_caution": float(thresh_caution),
        "threshold_warning": float(thresh_warning),
        "threshold_error": float(thresh_error),
        "features": X_train_ae.columns.tolist(),
    }
    with open(os.path.join(save_dir, "model_config.json"), "w") as f:
        json.dump(config, f)

    print(f"✅ 학습 및 저장 완료! ({save_dir} 위치에 아티팩트 생성됨)")
    return autoencoder


# ==============================================================================
# ⚔️ [메인 실행 블록]
# ==============================================================================
if __name__ == "__main__":
    print("🏁 [MAIN] 스마트팜 예지보전 AI 파이프라인 재학습을 시작합니다.")

    # 🌟 [수정됨] 경로 하드코딩 제거 -> 동적 경로 탐색 로직 적용
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)

    # /Users/... 대신 project_main_folder/data 폴더를 찾아가도록 설정
    # (주의: 파일명은 주니어님이 사용하시는 데이터 파일명과 정확히 맞춰주세요)
    data_filename = "smartfarm_nutrient_pump_rawdata_3months_clog_focus_v2_stronger.csv"
    data_path = os.path.join(project_root, "data", data_filename)

    print(f"📂 데이터 로딩 경로: {data_path}")
    df_raw = pd.read_csv(data_path)

    # 🌟 [추가] timestamp 컬럼을 datetime 형으로 바꾸고 인덱스로 설정!
    df_raw['timestamp'] = pd.to_datetime(df_raw['timestamp'])
    df_raw = df_raw.set_index('timestamp')

    # 타겟 딕셔너리 세팅
    target_dictionary = {
        "motor_current_a": [
            "motor_power_kw",
            "wire_to_water_efficiency",
            "motor_temperature_c",
        ],
        "zone1_resistance": ["zone1_pressure_kpa", "zone1_flow_l_min"],
        "wire_to_water_efficiency": [
            "motor_power_kw",
            "differential_pressure_kpa",
            "flow_rate_l_min",
            "hydraulic_power_kw",
        ],
    }

    # 전처리 및 피처 셀렉션 파이프라인 실행
    robust_features, X_train_ae, df_interpret, shap_res = (
        run_feature_selection_experiment(
            df_raw=df_raw, window_method="sliding", target_dict=target_dictionary
        )
    )

    # 모델 학습 및 결과물 저장 (models 폴더에 쏙 들어갑니다)
    model = train_and_save_model(X_train_ae, df_interpret)

    print("\n🎉 모든 파이프라인이 성공적으로 종료되었습니다!")
