import os
import json
import joblib
import time
import datetime
import numpy as np
import tensorflow as tf
import boto3
import pandas as pd
import sqlalchemy as sa
import requests
from io import BytesIO
from typing import Dict, Any
from fastapi import FastAPI, HTTPException, Body
from apscheduler.schedulers.background import BackgroundScheduler  # 오타 수정 완료
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# 1. 환경 설정 로드
load_dotenv()

# =====================================================================
# 2. AI 모델 및 인프라 설정 (경로 보정 완료)
# =====================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 만약 models 폴더가 main.py보다 한 단계 위에 있다면 아래와 같이 수정하세요.
# MODEL_DIR = os.path.join(os.path.dirname(BASE_DIR), "models")
MODEL_DIR = os.path.join(BASE_DIR, "models") 

MODEL_PATH = os.path.join(MODEL_DIR, "model.keras")
SCALER_PATH = os.path.join(MODEL_DIR, "scaler.pkl")
CONFIG_PATH = os.path.join(MODEL_DIR, "model_config.json")

MODEL = None
SCALER = None
FEATURE_NAMES = []
T_CAUT, T_WARN, T_ERR = 0.0, 0.0, 0.0

try:
    # 절대 경로를 사용하여 로드 시도
    MODEL = tf.keras.models.load_model(MODEL_PATH)
    SCALER = joblib.load(SCALER_PATH)
    with open(CONFIG_PATH, "r") as f:
        MODEL_CONFIG = json.load(f)

    T_CAUT = MODEL_CONFIG.get("threshold_caution", 0.003)
    T_WARN = MODEL_CONFIG.get("threshold_warning", 0.005)
    T_ERR = MODEL_CONFIG.get("threshold_error", 0.038)
    FEATURE_NAMES = MODEL_CONFIG.get("features", [])
    print(f"✅ AI 엔진 준비 완료! (항목 수: {len(FEATURE_NAMES)}, 기준 에러: {T_ERR})")
except Exception as e:
    print(f"❌ 로딩 실패 (경로 확인 요망): {e}")
    # 경로 디버깅을 위해 현재 BASE_DIR 출력
    print(f"현재 위치: {BASE_DIR}")

# 인프라 연결
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:9000")
S3_ACCESS_KEY = os.getenv("MINIO_ROOT_USER", "admin")
S3_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", "password123")
DB_URL = os.getenv("DATABASE_URL", "postgresql://farmer:plant_rich@localhost:5432/smartfarm")
BACKEND_REPORT_URL = os.getenv("BACKEND_REPORT_URL", "http://localhost:8080/api/inference-report")

s3 = boto3.client('s3', endpoint_url=S3_ENDPOINT, 
                  aws_access_key_id=S3_ACCESS_KEY, aws_secret_access_key=S3_SECRET_KEY)
engine = sa.create_engine(DB_URL)

# =====================================================================
# 3. 데이터 분석 및 저장 로직 (0.0 보간 로직 적용)
# =====================================================================
def process_inference_and_save(data_dict: Dict[str, Any], is_batch: bool = False):
    """분석 담당자의 철학대로 없는 데이터는 0.0으로 처리합니다."""
    try:
        # [핵심] 분석 담당자 스타일: .get(feat, 0.0)으로 누락 컬럼 대응
        input_values = [float(data_dict.get(feat, 0.0)) for feat in FEATURE_NAMES]
        raw_array = np.array(input_values).reshape(1, -1)
        scaled_array = SCALER.transform(raw_array)

        pred_array = MODEL.predict(scaled_array, verbose=0)
        mse_score = np.mean(np.power(scaled_array - pred_array, 2))
        log_mse_score = np.log10(mse_score + 1e-10)

        # 알람 등급 판별
        alarm_level, alarm_label = 0, "Normal 🟢"
        if mse_score >= T_ERR: alarm_level, alarm_label = 3, "Error 🔴"
        elif mse_score >= T_WARN: alarm_level, alarm_label = 2, "Warning 🟠"
        elif mse_score >= T_CAUT: alarm_level, alarm_label = 1, "Caution 🔸"

        response_body = {
            "status": "success",
            "timestamp": data_dict.get("timestamp", datetime.datetime.now().isoformat()),
            "score": {"mse": round(float(mse_score), 6), "log_mse": round(float(log_mse_score), 6)},
            "alarm_status": {"level": alarm_level, "label": alarm_label, "is_anomaly": alarm_level == 3}
        }

        with engine.connect() as conn:
            query = sa.text("""
                INSERT INTO inference_history (sensor_id, mse_score, log_mse_score, alarm_level, alarm_label, is_anomaly, data_timestamp)
                VALUES (:sid, :mse, :lmse, :lvl, :lbl, :anom, :ts)
            """)
            conn.execute(query, {
                "sid": data_dict.get("sensor_id", "SF-ZONE-01-MAIN"),
                "mse": response_body["score"]["mse"], "lmse": response_body["score"]["log_mse"],
                "lvl": response_body["alarm_status"]["level"], "lbl": response_body["alarm_status"]["label"],
                "anom": response_body["alarm_status"]["is_anomaly"], "ts": response_body["timestamp"]
            })
            conn.commit()

        # 2. 백엔드 실시간 보고 (DB 저장 성공 후 실행)
        # 배치(1분 주기)로 돌더라도 UI에 즉시 반영하고 싶다면 아래를 실행합니다.
        try:
            # 타임아웃을 짧게(1초) 주어 백엔드 응답 때문에 분석이 지연되지 않게 합니다.
            requests.post(BACKEND_REPORT_URL, json=response_body, timeout=1)
            print(f"📡 [실시간 전송] 백엔드로 분석 결과 보고 완료")
        except Exception as e:
            print(f"⚠️ [전송 실패] 백엔드 연결 불가 (하지만 DB 저장은 성공): {e}")

        # if not is_batch:
        #     try: requests.post(BACKEND_REPORT_URL, json=response_body, timeout=1)
        #     except: pass

        return response_body
    except Exception as e:
        print(f"❌ 분석 처리 중 오류: {e}")
        return {"status": "error", "message": str(e)}

# =====================================================================
# 4. 1분 단위 최신 파일 탐색 스케줄러 (Pandas 유연화 적용)
# =====================================================================
def run_scheduled_batch():
    try:
        print(f"🕵️ [배치 감시] S3 최신 파일 탐색 중... ({datetime.datetime.now().strftime('%H:%M:%S')})")
        
        response = s3.list_objects_v2(Bucket="raw-data")
        if 'Contents' not in response:
            print("⚠️ 버킷이 비어있습니다.")
            return

        csv_files = [f for f in response['Contents'] if f['Key'].endswith('.csv')]
        if not csv_files:
            print("⚠️ 분석할 CSV 파일이 없습니다.")
            return

        latest_file = sorted(csv_files, key=lambda x: x['LastModified'], reverse=True)[0]
        target_path = latest_file['Key']
        
        print(f"📂 [발견] 최신 데이터: {target_path}")

        obj = s3.get_object(Bucket="raw-data", Key=target_path)
        df = pd.read_csv(BytesIO(obj['Body'].read()))
        
        if not df.empty:
            # [수정] Pandas에서 에러가 나지 않도록 존재하는 컬럼만 먼저 계산
            available_features = [f for f in FEATURE_NAMES if f in df.columns]
            
            # 존재하는 항목은 평균값을 내고, 없는 항목은 0.0으로 딕셔너리 생성
            avg_record = df[available_features].mean().to_dict()
            
            # 모델이 요구하는 모든 항목이 딕셔너리에 있도록 보장 (없으면 0.0)
            for feat in FEATURE_NAMES:
                if feat not in avg_record:
                    avg_record[feat] = 0.0
            
            avg_record["timestamp"] = latest_file['LastModified'].isoformat()
            
            # 최종 분석 호출
            process_inference_and_save(avg_record, is_batch=True)
            print(f"✅ [배치 완료] {target_path} 처리 성공")

    except Exception as e:
        print(f"❌ 배치 작업 중 에러 발생: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = BackgroundScheduler()
    # apscheduler 오타 수정됨
    scheduler.add_job(run_scheduled_batch, 'interval', minutes=1)
    scheduler.start()
    print("⏰ 1분 주기 최신 파일 추적 스케줄러 시작됨")
    yield
    scheduler.shutdown()

app = FastAPI(title="Smart Farm AI 추론 서버", lifespan=lifespan)

@app.post("/predict")
def predict_endpoint(realtime_data: Dict[str, Any] = Body(...)):
    return process_inference_and_save(realtime_data)

@app.get("/health")
def health_check():
    return {"status": "ok", "model_loaded": MODEL is not None}