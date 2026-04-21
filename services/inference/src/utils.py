# src/utils.py
import os
import json
import joblib


def save_model_artifacts(model, scaler, config: dict, model_name: str, save_dir: str):
    """
    학습이 완료된 모델, 스케일러, 설정(Config) 데이터를
    지정된 폴더에 3종 세트로 깔끔하게 저장합니다.
    """
    # 저장할 디렉토리가 없다면 생성
    os.makedirs(save_dir, exist_ok=True)

    # (1) 모델 저장
    model_path = os.path.join(save_dir, f"{model_name}_model.keras")
    model.save(model_path)

    # (2) 스케일러 저장
    scaler_path = os.path.join(save_dir, f"{model_name}_scaler.pkl")
    joblib.dump(scaler, scaler_path)

    # (3) 설정(Config) JSON 저장
    config_path = os.path.join(save_dir, f"{model_name}_config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)
