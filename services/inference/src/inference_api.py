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
from io import BytesIO
from fastapi import FastAPI, Body, HTTPException
from typing import Dict, Any
from dotenv import load_dotenv
from contextlib import asynccontextmanager

# =====================================================================
# 1. 환경 설정 및 인프라 연결
# =====================================================================

# 1. 시스템 환경변수에서 ENV를 가져오고, 없으면 'local'로 간주합니다.
ENV = os.getenv("ENV", "local")

# 2. 'local' 환경일 때만 .env.local 파일을 로드합니다.
if ENV == "local":
    # 사용자님의 경로 설정 (../../.env.local) 반영
    env_path = "../../../.env.local"
    
    if os.path.exists(env_path):
        load_dotenv(env_path)
        print(f"✅ [LOCAL] '{env_path}' 파일로부터 환경 변수를 로드했습니다.")
    else:
        print(f"⚠️ [WARNING] '{env_path}' 파일이 존재하지 않습니다. 시스템 설정을 확인하세요.")
else:
    # 배포 환경 (Docker 등)에서는 이 로그가 출력됩니다.
    print(f"🚀 [DEPLOY] '{ENV}' 모드입니다. 시스템(Docker) 환경 변수를 사용합니다.")

# DB 및 백엔드 설정
DB_URL = os.getenv("AI_DATABASE_URL", "postgresql://farmer:plant_rich@localhost:5432/smartfarm")
BACKEND_REPORT_URL = os.getenv("BACKEND_REPORT_URL", "http://localhost:8080/api/inference-report")

engine = sa.create_engine(DB_URL)

# 모델 관리 변수
MODELS_DATA = {}

# [경로 설정]
MODEL_DIR = "/app/models"
if not os.path.exists(MODEL_DIR):
    MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models")

print(f"DEBUG: 모델 폴더 탐색 경로 -> {MODEL_DIR}")

# =====================================================================
# 2. 핵심 비즈니스 로직 (추론 및 결과 전파)
# =====================================================================
def process_inference_and_save(data: Dict[str, Any]):
    """실시간 혹은 백엔드로부터 전달받은 배치 데이터를 모델별 추론 후 DB 저장 및 백엔드 전송"""
    if not MODELS_DATA:
        print("⚠️ 로드된 모델이 없어 추론을 건너뜁니다.")
        return {"error": "no models loaded"}

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

        # 6) DB 저장
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

        # 7) 백엔드 실시간 전송 (리액트 웹소켓 브로드캐스트용)
        try:
            requests.post(BACKEND_REPORT_URL, json=payload, timeout=1)
        except:
            pass

        return payload

    except Exception as e:
        print(f"❌ [Inference Error] {e}")
        return {"error": str(e)}

# =====================================================================
# 3. FastAPI Lifespan 및 서버 설정
# =====================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- 시작 시 모델 자동 로딩 ---
    config_files = glob.glob(os.path.join(MODEL_DIR, "*_config.json"))
    
    for config_path in config_files:
        sys_name = os.path.basename(config_path).replace("_config.json", "")
        if sys_name == "model":
            continue

        try:
            model_path = os.path.join(MODEL_DIR, f"{sys_name}_model.keras")
            scaler_path = os.path.join(MODEL_DIR, f"{sys_name}_scaler.pkl")

            if os.path.exists(model_path) and os.path.exists(scaler_path):
                MODELS_DATA[sys_name] = {
                    "model": tf.keras.models.load_model(model_path),
                    "scaler": joblib.load(scaler_path),
                    "config": json.load(open(config_path, "r", encoding='utf-8'))
                }
                print(f"✅ [Load Success] {sys_name.upper()} 모델 장착 완료")
        except Exception as e:
            print(f"❌ [Load Error] {sys_name} 로딩 실패: {e}")

    print(f"⏰ 총 {len(MODELS_DATA)}개 모델 로드됨. 외부 요청 대기 중...")
    yield
    print("🛑 시스템 종료")

app = FastAPI(title="Smart Farm AI Engine", lifespan=lifespan)

@app.post("/predict")
def predict_endpoint(data: Dict[str, Any] = Body(...)):
    """
    백엔드(Hub)에서 호출하는 API 엔드포인트.
    실시간 데이터 및 배치(평균값) 데이터 모두 여기서 처리함.
    """
    return process_inference_and_save(data)

@app.get("/health")
def health_check():
    return {
        "status": "running", 
        "models_loaded": list(MODELS_DATA.keys())
    }