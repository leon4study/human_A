import os
import json
import joblib
import datetime
import numpy as np
import tensorflow as tf
import boto3
import pandas as pd
import sqlalchemy as sa
from io import BytesIO
from typing import Dict, Any
from fastapi import FastAPI, HTTPException, Body
from apscheduler.schedulers.background import BackgroundScheduler
from contextlib import asynccontextmanager # 최신 lifespan 규격용
from dotenv import load_dotenv

# 1. 환경 설정 로드
load_dotenv()

# =====================================================================
# 2. 모델 및 아티팩트 로드 (경로 및 JSON 키 자동 매핑)
# =====================================================================
print("⏳ Loading AI Models & Configs...")

# 파일 경로 자동 계산
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "models")

MODEL_PATH = os.path.join(MODEL_DIR, "model.keras")
SCALER_PATH = os.path.join(MODEL_DIR, "scaler.pkl")
CONFIG_PATH = os.path.join(MODEL_DIR, "model_config.json")

# 전역 변수 초기화
MODEL = None
SCALER = None
FEATURE_NAMES = []
# JSON 구조에 따른 3단계 임계치 변수
T_CAUT, T_WARN, T_ERR = 0.0, 0.0, 0.0

try:
    # 모델 및 스케일러 로드
    MODEL = tf.keras.models.load_model(MODEL_PATH)
    SCALER = joblib.load(SCALER_PATH)
    
    # 설정 파일 로드 및 키 매핑
    with open(CONFIG_PATH, "r") as f:
        MODEL_CONFIG = json.load(f)

    # [수정] JSON 파일의 실제 키 이름 반영
    T_CAUT = MODEL_CONFIG.get("threshold_caution", 0.003)
    T_WARN = MODEL_CONFIG.get("threshold_warning", 0.005) 
    T_ERR = MODEL_CONFIG.get("threshold_error", 0.038)
    FEATURE_NAMES = MODEL_CONFIG.get("features", [])

    print(f"✅ AI Engine Ready! (Thresholds: C:{T_CAUT:.4f}, W:{T_WARN:.4f}, E:{T_ERR:.4f})")
except Exception as e:
    print(f"❌ 아티팩트 로드 실패: {e}")

# 인프라 설정
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:9000")
S3_ACCESS_KEY = os.getenv("MINIO_ROOT_USER", "admin")
S3_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", "password123")
DB_URL = os.getenv("DATABASE_URL", "postgresql://admin:password123@localhost:5432/smartfarm")

s3 = boto3.client('s3', endpoint_url=S3_ENDPOINT, 
                  aws_access_key_id=S3_ACCESS_KEY, aws_secret_access_key=S3_SECRET_KEY)
engine = sa.create_engine(DB_URL)

# =====================================================================
# 3. 핵심 분석 및 DB 매핑 함수
# =====================================================================
def process_inference_and_save(data_dict: Dict[str, Any], is_batch: bool = False):
    # 1) 입력값 정규화
    input_values = [float(data_dict.get(feat, 0.0)) for feat in FEATURE_NAMES]
    raw_array = np.array(input_values).reshape(1, -1)
    scaled_array = SCALER.transform(raw_array)

    # 2) 모델 예측 및 MSE 계산
    pred_array = MODEL.predict(scaled_array, verbose=0)
    mse_score = np.mean(np.power(scaled_array - pred_array, 2))
    log_mse_score = np.log10(mse_score + 1e-10)

    # 3) [수정] 로드된 3단계 임계치로 알람 상태 판별
    alarm_level, alarm_label = 0, "Normal 🟢"
    if mse_score >= T_ERR: 
        alarm_level, alarm_label = 3, "Error 🔴"
    elif mse_score >= T_WARN: 
        alarm_level, alarm_label = 2, "Warning 🟠"
    elif mse_score >= T_CAUT: 
        alarm_level, alarm_label = 1, "Caution 🔸"

    # 4) RCA 계산
    feature_errors = np.power(scaled_array - pred_array, 2)[0]
    sum_error = np.sum(feature_errors) if np.sum(feature_errors) > 0 else 1e-10
    rca_list = sorted([
        {"feature": name, "contribution_pct": round(float((err / sum_error) * 100), 1)}
        for name, err in zip(FEATURE_NAMES, feature_errors)
    ], key=lambda x: x["contribution_pct"], reverse=True)
    top3_rca = rca_list[:3]

    # 5) 프론트엔드 맞춤형 Response 객체
    response_body = {
        "status": "success",
        "timestamp": data_dict.get("timestamp", datetime.datetime.now().isoformat()),
        "score": {"mse": round(float(mse_score), 6), "log_mse": round(float(log_mse_score), 6)},
        "thresholds": {"caution": T_CAUT, "warning": T_WARN, "error": T_ERR},
        "alarm_status": {"level": alarm_level, "label": alarm_label, "is_anomaly": alarm_level == 3},
        "rca_report": top3_rca,
        "action_required": f"Inspect {top3_rca[0]['feature']}" if alarm_level >= 2 else "All systems normal."
    }

    # 6) DB 스키마 규격에 맞춰 저장
    try:
        with engine.connect() as conn:
            query = sa.text("""
                INSERT INTO inference_history (
                    sensor_id, mse_score, log_mse_score, 
                    alarm_level, alarm_label, is_anomaly, 
                    rca_report, action_required, threshold_values, 
                    data_timestamp
                ) VALUES (
                    :sensor_id, :mse, :log_mse, 
                    :level, :label, :is_anomaly, 
                    :rca, :action, :thresholds, :data_ts
                )
            """)
            conn.execute(query, {
                "sensor_id": data_dict.get("sensor_id", "FARM_MASTER_01"),
                "mse": response_body["score"]["mse"],
                "log_mse": response_body["score"]["log_mse"],
                "level": response_body["alarm_status"]["level"],
                "label": response_body["alarm_status"]["label"],
                "is_anomaly": response_body["alarm_status"]["is_anomaly"],
                "rca": json.dumps(response_body["rca_report"]),
                "action": response_body["action_required"],
                "thresholds": json.dumps(response_body["thresholds"]),
                "data_ts": response_body["timestamp"]
            })
            conn.commit()
    except Exception as db_err:
        print(f"❌ DB 저장 오류: {db_err}")

    return response_body

# =====================================================================
# 4. 배치 로직 및 최신 Lifespan 이벤트 핸들러
# =====================================================================
def run_scheduled_batch():
    try:
        now = datetime.datetime.now() - datetime.timedelta(minutes=1)
        rounded_min = (now.minute // 10) * 10
        target_path = f"year={now.year}/month={now.month:02d}/day={now.day:02d}/sensor_{now.strftime('%H')}{rounded_min:02d}.csv"
        
        obj = s3.get_object(Bucket="raw-data", Key=target_path)
        df = pd.read_csv(BytesIO(obj['Body'].read()))
        
        if not df.empty:
            avg_record = df[FEATURE_NAMES].mean().to_dict()
            avg_record["timestamp"] = now.isoformat()
            process_inference_and_save(avg_record, is_batch=True)
            print(f"✅ [Batch] Success: {target_path}")
    except Exception as e:
        pass # 파일이 없을 경우 등에 대한 조용한 처리

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_scheduled_batch, 'interval', minutes=10)
    scheduler.start()
    print("⏰ Inference Batch Scheduler Started")
    yield
    # Shutdown
    scheduler.shutdown()

app = FastAPI(title="Smart Farm 예지보전 통합 추론 서버", lifespan=lifespan)

# =====================================================================
# 5. API 엔드포인트
# =====================================================================
@app.post("/predict")
def predict_endpoint(realtime_data: Dict[str, Any] = Body(...)):
    if MODEL is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return process_inference_and_save(realtime_data)

@app.get("/health")
def health_check():
    return {"status": "ok", "model_loaded": MODEL is not None}