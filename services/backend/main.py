import os
import json
import asyncio
import threading
import requests
import pandas as pd
import boto3
from io import BytesIO
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body
from fastapi.middleware.cors import CORSMiddleware
import paho.mqtt.client as mqtt
from apscheduler.schedulers.background import BackgroundScheduler

# 1. 시스템 환경변수에서 ENV를 가져오고, 없으면 'local'로 간주합니다.
ENV = os.getenv("ENV", "local")

# 2. 'local' 환경일 때만 .env.local 파일을 로드합니다.
if ENV == "local":
    # 사용자님의 경로 설정 (../../.env.local) 반영
    env_path = "../../.env.local"
    
    if os.path.exists(env_path):
        load_dotenv(env_path)
        print(f"✅ [LOCAL] '{env_path}' 파일로부터 환경 변수를 로드했습니다.")
    else:
        print(f"⚠️ [WARNING] '{env_path}' 파일이 존재하지 않습니다. 시스템 설정을 확인하세요.")
else:
    # 배포 환경 (Docker 등)에서는 이 로그가 출력됩니다.
    print(f"🚀 [DEPLOY] '{ENV}' 모드입니다. 시스템(Docker) 환경 변수를 사용합니다.")


app = FastAPI(title="Smart Farm Backend Hub")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- 설정값 ---
INFERENCE_SERVER_URL = os.getenv("INFERENCE_SERVER_URL", "http://localhost:8000/predict")
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:9000")
S3_ACCESS_KEY = os.getenv("MINIO_ROOT_USER", "admin")
S3_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", "password123")
BUCKET_NAME = "raw-data"

s3 = boto3.client('s3', 
                  endpoint_url=S3_ENDPOINT, 
                  aws_access_key_id=S3_ACCESS_KEY, 
                  aws_secret_access_key=S3_SECRET_KEY,
                  region_name='us-east-1')

# ---------------------------------------------------------------------
# [웹소켓 관리자]
# ---------------------------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.active_connections = []
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try: await connection.send_json(message)
            except: pass

manager = ConnectionManager()

# ---------------------------------------------------------------------
# [S3 배치 스케줄러 로직] - 추론 서버에서 이사 옴
# ---------------------------------------------------------------------
def run_scheduled_batch():
    try:
        print(f"🕵️ [배치 감시] S3 최신 파일 탐색 중...")
        response = s3.list_objects_v2(Bucket=BUCKET_NAME)
        if 'Contents' not in response: return

        csv_files = [f for f in response['Contents'] if f['Key'].endswith('.csv')]
        if not csv_files: return

        latest_file = sorted(csv_files, key=lambda x: x['LastModified'], reverse=True)[0]
        obj = s3.get_object(Bucket=BUCKET_NAME, Key=latest_file['Key'])
        df = pd.read_csv(BytesIO(obj['Body'].read()))
        
        if not df.empty:
            avg_record = df.mean(numeric_only=True).to_dict()
            avg_record["timestamp"] = latest_file['LastModified'].isoformat()
            
            # 추론 서버에 분석 요청
            print(f"🚀 [배치] 추론 서버로 요청 전송: {latest_file['Key']}")
            requests.post(INFERENCE_SERVER_URL, json=avg_record, timeout=5)
    except Exception as e:
        print(f"❌ [Batch Error] {e}")

# ---------------------------------------------------------------------
# [MQTT 로직]
# ---------------------------------------------------------------------
def start_mqtt_loop(loop):
    def on_connect(client, userdata, flags, rc):
        if rc == 0: client.subscribe("sensor/data")
    
    def on_message(client, userdata, msg):
        try:
            raw_data = json.loads(msg.payload.decode())
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({"type": "RAW", "payload": raw_data}), loop
            )
        except Exception as e: print(f"❌ MQTT 처리 에러: {e}")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=f"hub-{os.getpid()}")
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(os.getenv("BE_MQTT_BROKER_HOST", "127.0.0.1"), 1883, 60)
    client.loop_forever()

# ---------------------------------------------------------------------
# [FastAPI 실행부]
# ---------------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    loop = asyncio.get_running_loop()
    # 1. MQTT 스레드 가동
    threading.Thread(target=start_mqtt_loop, args=(loop,), daemon=True).start()
    # 2. 배치 스케줄러 가동
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_scheduled_batch, 'interval', minutes=1)
    scheduler.start()
    print("✅ 백엔드 허브 및 스케줄러 가동 준비 완료")

@app.websocket("/ws/smart-farm")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True: await websocket.receive_text()
    except WebSocketDisconnect: manager.disconnect(websocket)

@app.post("/api/inference-report")
async def receive_inference(data: dict = Body(...)):
    # 추론 서버가 분석 결과를 이리로 쏴주면 리액트로 브로드캐스트
    await manager.broadcast({"type": "INFERENCE", "payload": data})
    return {"status": "ok"}