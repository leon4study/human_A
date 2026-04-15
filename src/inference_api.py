from fastapi import FastAPI, HTTPException, Body
from typing import Dict, Any
import numpy as np
import tensorflow as tf
import joblib
import json
import datetime

app = FastAPI(title="SmartFarm 예지보전 API 서버")

# =====================================================================
# 1. 서버가 부팅될 때 딱 한 번! 메모리에 모델을 올려둡니다 (Cold Start 방지)
# =====================================================================
print("⏳ Loading Models & Configs...")
try:
    MODEL = tf.keras.models.load_model("../models/model.keras")
    SCALER = joblib.load("../models/scaler.pkl")

    with open("../models/model_config.json", "r") as f:
        CONFIG = json.load(f)

    THRESHOLD = CONFIG["threshold"]
    FEATURE_NAMES = CONFIG["features"]
    print("✅ Server Ready! Waiting for data...")
except Exception as e:
    print(f"❌ Failed to load artifacts. 경로와 파일을 확인해주세요: {e}")


# =====================================================================
# 2. 데이터가 들어오는 API 엔드포인트
# =====================================================================
@app.post("/predict")
def predict_anomaly_and_rca(realtime_data_dict: Dict[str, Any] = Body(...)):
    """
    프론트엔드에서 JSON 형태로 센서 데이터를 보내면,
    FastAPI가 자동으로 realtime_data_dict 딕셔너리로 변환해줍니다.
    """
    try:
        # 1~3. 스케일링 및 모델 예측
        # 들어온 데이터 중 모델 학습에 사용된 피처만 순서대로 추출 (없으면 0.0 처리)
        input_values = [
            float(realtime_data_dict.get(feat, 0.0)) for feat in FEATURE_NAMES
        ]
        raw_array = np.array(input_values).reshape(1, -1)
        scaled_array = SCALER.transform(raw_array)

        pred_array = MODEL.predict(scaled_array, verbose=0)
        mse_score = np.mean(np.power(scaled_array - pred_array, 2))

        # (옵션) 프론트에서 로그 스케일 그래프를 그린다면 이 값도 같이 넘겨줌
        log_mse_score = np.log10(mse_score + 1e-10)

        # -----------------------------------------------------------------
        # 4. 3단계 알람 상태 판별
        # -----------------------------------------------------------------
        T_ERR = THRESHOLD
        T_WARN = THRESHOLD * 0.7  # 임시 비율
        T_CAUT = THRESHOLD * 0.4  # 임시 비율

        alarm_level = 0
        alarm_label = "Normal 🟢"

        if mse_score >= T_ERR:
            alarm_level = 3
            alarm_label = "Error 🔴"
        elif mse_score >= T_WARN:
            alarm_level = 2
            alarm_label = "Warning 🟠"
        elif mse_score >= T_CAUT:
            alarm_level = 1
            alarm_label = "Caution 🔸"

        is_anomaly = alarm_level == 3

        # -----------------------------------------------------------------
        # 5. 실시간 RCA 계산 (원인 분석)
        # -----------------------------------------------------------------
        feature_errors = np.power(scaled_array - pred_array, 2)[0]
        sum_error = np.sum(feature_errors) if np.sum(feature_errors) > 0 else 1e-10

        rca_list = [
            {
                "feature": name,
                "contribution_pct": round(float((err / sum_error) * 100), 1),
            }
            for name, err in zip(FEATURE_NAMES, feature_errors)
        ]

        # 내림차순 정렬 후 Top 3 추출
        rca_list = sorted(rca_list, key=lambda x: x["contribution_pct"], reverse=True)
        top3_rca = rca_list[:3]

        # -----------------------------------------------------------------
        # 6. 프론트엔드 맞춤형 최종 Response 구성
        # -----------------------------------------------------------------
        response = {
            "status": "success",
            "timestamp": realtime_data_dict.get(
                "timestamp", datetime.datetime.now().isoformat()
            ),
            "score": {
                "mse": round(float(mse_score), 6),
                "log_mse": round(float(log_mse_score), 6),
            },
            "thresholds": {
                "caution": round(float(T_CAUT), 6),
                "warning": round(float(T_WARN), 6),
                "error": round(float(T_ERR), 6),
            },
            "alarm_status": {
                "level": alarm_level,
                "label": alarm_label,
                "is_anomaly": is_anomaly,
            },
            "rca_report": top3_rca,
            "action_required": (
                f"Inspect {top3_rca[0]['feature']}"
                if alarm_level >= 2
                else "All systems normal."
            ),
        }

        # 💡 json.dumps()를 빼고 딕셔너리를 그대로 반환해야
        # FastAPI가 올바른 'application/json' 형태로 전달합니다.
        return response

    except Exception as e:
        # 에러 발생 시 HTTP 500 에러와 함께 원인을 반환하도록 수정
        raise HTTPException(status_code=500, detail=str(e))
