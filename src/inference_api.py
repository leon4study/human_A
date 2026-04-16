# 로컬 실행 명령어 예시
# python -m uvicorn inference_api:app --reload (개발/테스트용)
# python -m uvicorn inference_api:app --host 0.0.0.0 --port 8000 (배포/실전용)

import os
import json
import glob
import joblib
import datetime
import numpy as np
import pandas as pd
import tensorflow as tf
from fastapi import FastAPI, Body, HTTPException
from typing import Dict, Any, List
from logger import get_logger

app = FastAPI(title="SmartFarm Multi-Domain 예지보전 API")
logger = get_logger("API")


# =====================================================================
# 1. 멀티 모델 및 설정 로드 (서버 기동 시)
# =====================================================================
MODELS_DATA = {}


# 경로 설정 (src/inference_api.py 기준 상위 models 폴더)
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
save_dir = os.path.join(project_root, "models")

# 🌟 [방법 1 적용] models 폴더를 뒤져서 config 파일 자동 찾기
logger.info("⏳ Loading Multi-Domain Models & Configs...")

# models 폴더 안에 있는 모든 '_config.json' 파일의 경로를 리스트로 가져옵니다.
config_files = glob.glob(os.path.join(save_dir, "*_config.json"))

# 파일명에서 앞부분(도메인 이름)만 쏙 빼서 SYSTEMS 리스트를 자동으로 만듭니다.
# 예: ".../models/motor_config.json" -> "motor"
SYSTEMS = [os.path.basename(f).replace("_config.json", "") for f in config_files]

if not SYSTEMS:
    logger.warning("⚠️ models 폴더에 학습된 모델(config)이 하나도 없습니다!")
else:
    logger.info(f"🔍 감지된 도메인 모델들: {SYSTEMS}")

try:
    for sys_name in SYSTEMS:
        # 각 시스템별 파일 로드
        model_path = os.path.join(save_dir, f"{sys_name}_model.keras")
        scaler_path = os.path.join(save_dir, f"{sys_name}_scaler.pkl")
        config_path = os.path.join(save_dir, f"{sys_name}_config.json")

        # # 3가지 아티팩트(모델, 스케일러, 설정) 중 하나라도 없으면 스킵
        if not all(os.path.exists(p) for p in [model_path, scaler_path, config_path]):
            logger.warning(
                f"⚠️ {sys_name.upper()} 모델 파일 일부가 누락되었습니다. 스킵합니다."
            )
            continue

        MODELS_DATA[sys_name] = {
            "model": tf.keras.models.load_model(model_path),
            "scaler": joblib.load(scaler_path),
            "config": json.load(open(config_path, "r")),
        }
    logger.info(f"✅ {len(MODELS_DATA)}개의 서브 시스템 모델 로드 완료!")

except Exception as e:
    logger.error(f"❌ 초기화 중 치명적 에러 발생: {e}")


# =====================================================================
# 2. 실시간 다중 도메인 추론 엔드포인트
# =====================================================================
@app.post("/predict")
def predict_multi_domain(realtime_data: Dict[str, Any] = Body(...)):
    if not MODELS_DATA:
        logger.error("❌ 추론 요청이 들어왔으나 로드된 모델이 없습니다.")
        raise HTTPException(status_code=503, detail="사용 가능한 모델이 없습니다.")

    final_results = {}
    total_alarm_level = 0
    overall_status = "Normal 🟢"

    try:
        for sys_name, data in MODELS_DATA.items():
            model = data["model"]
            scaler = data["scaler"]
            config = data["config"]
            features = config["features"]

            # 1. 해당 모델 피처만 추출
            input_values = [float(realtime_data.get(f, 0.0)) for f in features]
            raw_df = pd.DataFrame([input_values], columns=features)

            # 2. 추론
            scaled_array = scaler.transform(raw_df)
            pred_array = model.predict(scaled_array, verbose=0)
            mse_score = float(np.mean(np.power(scaled_array - pred_array, 2)))

            # 3. 임계값 비교 (저장된 설정값 사용)
            t_caut = config["threshold_caution"]
            t_warn = config["threshold_warning"]
            t_err = config["threshold_error"]

            alarm_level = 0
            label = "Normal"
            if mse_score >= t_err:
                alarm_level = 3
                label = "Error 🔴"
            elif mse_score >= t_warn:
                alarm_level = 2
                label = "Warning 🟠"
            elif mse_score >= t_caut:
                alarm_level = 1
                label = "Caution 🔸"

            # 4. RCA (원인 분석)
            feature_errors = np.power(scaled_array - pred_array, 2)[0]
            sum_err = np.sum(feature_errors) if np.sum(feature_errors) > 0 else 1e-10
            rca = sorted(
                [
                    {"feature": n, "contribution": round((float(e) / sum_err) * 100, 1)}
                    for n, e in zip(features, feature_errors)
                ],
                key=lambda x: x["contribution"],
                reverse=True,
            )[:3]

            # 결과 저장
            final_results[sys_name] = {
                "score": round(mse_score, 6),
                "alarm": {"level": alarm_level, "label": label},
                "thresholds": {
                    "caution": round(t_caut, 6),
                    "warning": round(t_warn, 6),
                    "error": round(t_err, 6),
                },
                "rca": rca,
            }

            # 전체 알람 수위 갱신 (가장 심각한 쪽 기준)
            if alarm_level > total_alarm_level:
                total_alarm_level = alarm_level
                overall_status = label

        response_payload = {
            "timestamp": realtime_data.get(
                "timestamp", datetime.datetime.now().isoformat()
            ),
            "overall_alarm_level": total_alarm_level,
            "overall_status": overall_status,
            "domain_reports": final_results,
            "action_required": (
                "System check recommended" if total_alarm_level >= 2 else "Optimal"
            ),
        }

        # 🌟 핵심 로그 1: 시스템에 주의(Caution) 이상의 이상징후가 포착되었을 때만 로그를 남김!
        if total_alarm_level > 0:
            logger.warning(
                f"🚨 [이상 감지] Level {total_alarm_level} ({overall_status}) - 타임스탬프: {response_payload['timestamp']}"
            )

        return response_payload

    except Exception as e:
        # API 내부에서 파이썬 에러가 터졌을 때
        # exc_info=True 를 주면 에러가 난 몇 번째 줄인지 추적(Traceback) 정보까지 파일에 싹 다 저장됩니다.
        logger.error(f"❌ API 추론 중 내부 에러 발생: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
