import os
import json
import glob
import joblib
import datetime
import numpy as np
import pandas as pd
import tensorflow as tf
import sqlalchemy as sa
import requests
import boto3
from io import BytesIO
from fastapi import FastAPI, Body, HTTPException
from typing import Dict, Any
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler

# =====================================================================
# 1. 환경 설정 및 인프라 연결
# =====================================================================
load_dotenv("../../../.env")

# DB 및 백엔드 설정
DB_URL = os.getenv("AI_DATABASE_URL", "postgresql://farmer:plant_rich@smart-db:5432/smartfarm")
BACKEND_REPORT_URL = os.getenv("BACKEND_REPORT_URL", "http://backend-hub:8080/api/inference-report")

# S3(MinIO) 설정
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://data-lake:9000")
S3_ACCESS_KEY = os.getenv("MINIO_ROOT_USER", "admin")
S3_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", "password123")
BUCKET_NAME = "raw-data"

engine = sa.create_engine(DB_URL)
s3 = boto3.client('s3', 
                  endpoint_url=S3_ENDPOINT, 
                  aws_access_key_id=S3_ACCESS_KEY, 
                  aws_secret_access_key=S3_SECRET_KEY,
                  region_name='us-east-1')

# 모델 관리 변수
MODELS_DATA = {}

# [경로 설정]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # src 폴더
MODEL_DIR = os.path.join(os.path.dirname(BASE_DIR), "models")

print(f"DEBUG: 모델 폴더 탐색 경로 -> {MODEL_DIR}") # 확인용 로그

# =====================================================================
# 2. 핵심 비즈니스 로직 (추론 및 결과 전파)
# =====================================================================
def process_inference_and_save(data: Dict[str, Any], is_batch: bool = False):
    """실시간 데이터 혹은 배치 데이터를 받아 모델별 추론 후 DB/백엔드 전송"""
    if not MODELS_DATA:
        print("⚠️ 로드된 모델이 없어 추론을 건너뜁니다.")
        return None

    domain_reports = {}
    max_level = 0
    final_status = "Normal 🟢"

    try:
        for sys_name, assets in MODELS_DATA.items():
            conf = assets["config"]
            feats = conf["features"]
            
            # 1) 데이터 전처리 (누락 시 0.0 보간)
            input_vals = [float(data.get(f, 0.0)) for f in feats]
            scaled = assets["scaler"].transform(pd.DataFrame([input_vals], columns=feats))
            
            # 2) 모델 추론 (MSE 계산)
            pred = assets["model"].predict(scaled, verbose=0)
            mse = float(np.mean(np.power(scaled - pred, 2)))

            # 3) 알람 레벨 판별
            lvl, lbl = 0, "Normal"
            if mse >= conf["threshold_error"]: lvl, lbl = 3, "Error 🔴"
            elif mse >= conf["threshold_warning"]: lvl, lbl = 2, "Warning 🟠"
            elif mse >= conf["threshold_caution"]: lvl, lbl = 1, "Caution 🔸"

            # 4) 원인 분석 (RCA)
            feat_errors = np.power(scaled - pred, 2)[0]
            err_sum = np.sum(feat_errors) if np.sum(feat_errors) > 0 else 1e-10
            rca = sorted([
                {"feature": n, "contribution": round((float(e)/err_sum)*100, 1)}
                for n, e in zip(feats, feat_errors)
            ], key=lambda x: x["contribution"], reverse=True)[:3]

            domain_reports[sys_name] = {
                "score": round(mse, 6),
                "alarm": {"level": lvl, "label": lbl},
                "rca": rca
            }

            if lvl > max_level:
                max_level, final_status = lvl, lbl

        # 5) 최종 결과 패키징
        payload = {
            "sensor_id": "SF-ZONE-01-MAIN",
            "timestamp": data.get("timestamp", datetime.datetime.now().isoformat()),
            "overall_alarm_level": max_level,
            "overall_status": final_status,
            "domain_reports": domain_reports,
            "action_required": "System check needed" if max_level >= 2 else "Optimal"
        }

        # 6) DB 저장 (JSONB 활용)
        with engine.connect() as conn:
            query = sa.text("""
                INSERT INTO inference_history (
                    sensor_id, overall_level, overall_status, 
                    inference_result, action_required, data_timestamp
                ) VALUES (:sid, :lvl, :status, :res, :act, :ts)
            """)
            conn.execute(query, {
                "sid": payload["sensor_id"], "lvl": payload["overall_alarm_level"],
                "status": payload["overall_status"], "res": json.dumps(payload["domain_reports"]),
                "act": payload["action_required"], "ts": payload["timestamp"]
            })
            conn.commit()

        # 7) 백엔드 실시간 전송
        try:
            requests.post(BACKEND_REPORT_URL, json=payload, timeout=1)
        except:
            pass

        return payload

    except Exception as e:
        print(f"❌ [Inference Error] {e}")
        return {"error": str(e)}

# =====================================================================
# 3. S3 배치 스케줄러 로직
# =====================================================================
def run_scheduled_batch():
    """1분마다 S3 최신 CSV를 읽어 평균값 분석 수행"""
    try:
        print(f"🕵️ [배치 감시] S3 최신 파일 탐색 중... ({datetime.datetime.now().strftime('%H:%M:%S')})")
        
        response = s3.list_objects_v2(Bucket=BUCKET_NAME)
        if 'Contents' not in response:
            return

        csv_files = [f for f in response['Contents'] if f['Key'].endswith('.csv')]
        if not csv_files:
            return

        # 최신 수정된 파일 탐색
        latest_file = sorted(csv_files, key=lambda x: x['LastModified'], reverse=True)[0]
        target_path = latest_file['Key']
        
        print(f"📂 [발견] 최신 데이터 처리: {target_path}")

        obj = s3.get_object(Bucket=BUCKET_NAME, Key=target_path)
        df = pd.read_csv(BytesIO(obj['Body'].read()))
        
        if not df.empty:
            # 모든 모델에서 요구하는 피처 목록 추출
            all_feats = []
            for assets in MODELS_DATA.values():
                all_feats.extend(assets["config"]["features"])
            unique_feats = list(set(all_feats))

            # 존재하는 컬럼만 평균 계산 및 보간
            avg_record = df.mean(numeric_only=True).to_dict()
            for f in unique_feats:
                if f not in avg_record:
                    avg_record[f] = 0.0
            
            avg_record["timestamp"] = latest_file['LastModified'].isoformat()
            process_inference_and_save(avg_record, is_batch=True)
            print(f"✅ [배치 완료] {target_path} 분석 성공")

    except Exception as e:
        print(f"❌ [Batch Error] {e}")

# =====================================================================
# 4. FastAPI Lifespan 및 서버 설정
# =====================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- 1. 시작 시 모델 자동 로딩 (분석 코드 스타일) ---
    print(f"DEBUG: 모델 폴더 탐색 경로 -> {MODEL_DIR}")
    
    # models 폴더 내의 모든 '_config.json' 파일을 찾음
    config_files = glob.glob(os.path.join(MODEL_DIR, "*_config.json"))
    
    for config_path in config_files:
        # 파일명에서 도메인 이름 추출 (예: 'motor_config.json' -> 'motor')
        sys_name = os.path.basename(config_path).replace("_config.json", "")
        
        # [중요] 기존에 에러를 냈던 'model_config.json'은 실제 모델이 아니므로 스킵 처리
        if sys_name == "model":
            continue

        try:
            # 분석가 규칙: {도메인}_model.keras / {도메인}_scaler.pkl
            model_path = os.path.join(MODEL_DIR, f"{sys_name}_model.keras")
            scaler_path = os.path.join(MODEL_DIR, f"{sys_name}_scaler.pkl")

            if os.path.exists(model_path) and os.path.exists(scaler_path):
                MODELS_DATA[sys_name] = {
                    "model": tf.keras.models.load_model(model_path),
                    "scaler": joblib.load(scaler_path),
                    "config": json.load(open(config_path, "r", encoding='utf-8'))
                }
                print(f"✅ [Load Success] {sys_name.upper()} 모델 장착 완료")
            else:
                print(f"⚠️ [Load Skip] {sys_name} 관련 파일 일부 누락 (model 또는 scaler 없음)")

        except Exception as e:
            print(f"❌ [Load Error] {sys_name} 로딩 중 오류 발생: {e}")

    # --- 2. 스케줄러 설정 ---
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_scheduled_batch, 'interval', minutes=1)
    scheduler.start()
    print(f"⏰ 총 {len(MODELS_DATA)}개 모델 로드됨. S3 배치 스케줄러 가동")
    
    yield
    
    scheduler.shutdown()
    print("🛑 시스템 종료")

# FastAPI 앱 객체 생성 (데코레이터 이전에 정의)
app = FastAPI(title="Smart Farm Multi-Model AI Engine", lifespan=lifespan)

@app.post("/predict")
def predict_endpoint(realtime_data: Dict[str, Any] = Body(...)):
    """실시간 추론 API 엔드포인트"""
    return process_inference_and_save(realtime_data)

@app.get("/health")
def health_check():
    """서버 상태 및 모델 로드 현황 확인"""
    return {
        "status": "running", 
        "models_loaded": list(MODELS_DATA.keys()),
        "model_dir": MODEL_DIR
    }