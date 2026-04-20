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

# 분리해둔 추론 함수들 불러오기
from inference_core import get_alarm_status, calculate_rca, build_feature_details


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
            t_caut, t_warn, t_err = (
                config["threshold_caution"],
                config["threshold_warning"],
                config["threshold_critical"],
            )

            # 1. 데이터 추출 및 추론
            input_values = [float(realtime_data.get(f, 0.0)) for f in features]
            raw_df = pd.DataFrame([input_values], columns=features)

            scaled_array = scaler.transform(raw_df)
            pred_array = model.predict(scaled_array, verbose=0)
            mse_score = float(np.mean(np.power(scaled_array - pred_array, 2)))

            # 2. [함수 사용] 알람 레벨 판정
            alarm_level, label = get_alarm_status(mse_score, t_caut, t_warn, t_err)

            # 3. [함수 사용] RCA(원인 분석) 계산
            feature_errors = np.power(scaled_array - pred_array, 2)[0]
            rca = calculate_rca(feature_errors, features, top_n=3)

            # 4. [함수 사용] 프론트엔드 차트용 상세 데이터(시그마 밴드 등) 생성
            pred_raw_array = scaler.inverse_transform(pred_array)[
                0
            ]  # 1차원 리스트로 축소
            feature_stats = config.get("feature_stats", {})
            feature_details = build_feature_details(
                input_values, pred_raw_array, features, feature_stats
            )

            # 5. 결과 조립
            final_results[sys_name] = {
                "metrics": {
                    "current_mse": round(mse_score, 6),
                    "train_loss": config.get("train_loss", "N/A"),
                    "val_loss": config.get("val_loss", "N/A"),
                },
                "alarm": {"level": alarm_level, "label": label},
                "global_thresholds": {
                    "caution": round(t_caut, 6),
                    "warning": round(t_warn, 6),
                    "critical": round(t_err, 6),
                },
                "rca_top3": rca,
                "feature_details": feature_details,
            }

            # 전체 알람 수위 갱신 (가장 심각한 쪽 기준)
            if alarm_level > total_alarm_level:
                total_alarm_level = alarm_level
                overall_status = label

        # 6. 스파이크 정보 추출 (시뮬레이터가 전처리 후 넘겨준 값 passthrough)
        spike_info = {
            "is_spike": bool(realtime_data.get("is_spike", False)),
            "is_startup_spike": bool(realtime_data.get("is_startup_spike", False)),
            "is_anomaly_spike": bool(realtime_data.get("is_anomaly_spike", False)),
        }

        # 7. 최종 응답 페이로드
        response_payload = {
            "timestamp": realtime_data.get(
                "timestamp", datetime.datetime.now().isoformat()
            ),
            "overall_alarm_level": total_alarm_level,
            "overall_status": overall_status,
            "spike_info": spike_info,
            "domain_reports": final_results,
            "action_required": (
                "System check recommended" if total_alarm_level >= 2 else "Optimal"
            ),
        }

        if total_alarm_level > 0:
            spike_tag = ""
            if spike_info["is_anomaly_spike"]:
                spike_tag = " ⚡[이상 스파이크]"
            elif spike_info["is_startup_spike"]:
                spike_tag = " 🔄[기동 스파이크]"
            logger.warning(
                f"🚨 [이상 감지] Level {total_alarm_level} ({overall_status}){spike_tag} - 타임스탬프: {response_payload['timestamp']}"
            )

        return response_payload

    except Exception as e:
        # API 내부에서 파이썬 에러가 터졌을 때
        # exc_info=True 를 주면 에러가 난 몇 번째 줄인지 추적(Traceback) 정보까지 파일에 싹 다 저장됩니다.
        logger.error(f"❌ API 추론 중 내부 에러 발생: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    logger.info("🌐 Uvicorn 웹 서버를 시작합니다... (http://127.0.0.1:8000/docs)")
    uvicorn.run("inference_api:app", host="0.0.0.0", port=8000, reload=True)
