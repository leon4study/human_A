import os
import json
import asyncio
import threading
import sqlalchemy as sa
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import paho.mqtt.client as mqtt
from apscheduler.schedulers.background import BackgroundScheduler

ENV = os.getenv("ENV", "local")
if ENV == "local":
    env_path = "../../.env.local"
    if os.path.exists(env_path):
        load_dotenv(env_path)
        print(f"✅ [LOCAL] '{env_path}' 파일로부터 환경 변수를 로드했습니다.")
    else:
        print(f"⚠️ [WARNING] '{env_path}' 파일이 존재하지 않습니다. 시스템 설정을 확인하세요.")
else:
    print(f"🚀 [DEPLOY] '{ENV}' 모드입니다. 시스템(Docker) 환경 변수를 사용합니다.")


# --- 설정값 ---
DB_URL = os.getenv("BE_DATABASE_URL", "postgresql://farmer:plant_rich@localhost:5432/smartfarm")
engine = sa.create_engine(DB_URL)

main_loop = None

# 마지막으로 웹소켓에 broadcast 한 inference_history.id
# 서버 기동 시점의 MAX(id)로 초기화해 이미 존재하던 이력은 재전송하지 않는다.
# (프론트는 GET /inference/history 로 초기 이력을 별도 로드)
last_broadcast_inference_id = 0

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
# [DB 폴링] 5초 간격으로 "새로 생긴 이상(level > 0) 이력" 만 즉시 broadcast
# ---------------------------------------------------------------------
def run_scheduled_batch():
    global last_broadcast_inference_id
    try:
        with engine.connect() as conn:
            result = conn.execute(sa.text("""
                SELECT id, sensor_id, overall_level, overall_status,
                       inference_result, action_required, data_timestamp
                FROM inference_history
                WHERE id > :last_id AND overall_level > 0
                ORDER BY id ASC
            """), {"last_id": last_broadcast_inference_id})
            rows = result.fetchall()

        if not rows:
            return

        for row in rows:
            payload = {
                "sensor_id": row.sensor_id,
                "overall_alarm_level": row.overall_level,
                "overall_status": row.overall_status,
                "domain_reports": row.inference_result,
                "action_required": row.action_required,
                "timestamp": row.data_timestamp.isoformat() if row.data_timestamp else None
            }
            print(f"[INFERENCE] 신규 이상 감지 | id={row.id} | level={row.overall_level} | status={row.overall_status}")

            if main_loop:
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast({"type": "INFERENCE", "payload": payload}), main_loop
                )
            last_broadcast_inference_id = row.id
    except Exception as e:
        print(f"❌ [Batch Error] {e}")

# ---------------------------------------------------------------------
# [MQTT 로직] raw 센서 데이터 → WebSocket 브로드캐스트
# ---------------------------------------------------------------------
def start_mqtt_loop(loop):
    def on_connect(client, userdata, flags, rc):
        if rc == 0: client.subscribe("sensor/data")

    def on_message(client, userdata, msg):
        try:
            raw_data = json.loads(msg.payload.decode())
            print(f"[RAW] MQTT 수신 | {json.dumps(raw_data, ensure_ascii=False)}")
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
# [FastAPI 앱]
# ---------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global main_loop, last_broadcast_inference_id
    main_loop = asyncio.get_running_loop()

    # 기동 시점의 MAX(id)를 기준점으로 삼아 이미 있던 이력은 재전송하지 않음
    try:
        with engine.connect() as conn:
            max_id = conn.execute(
                sa.text("SELECT COALESCE(MAX(id), 0) FROM inference_history")
            ).scalar()
            last_broadcast_inference_id = int(max_id or 0)
            print(f"✅ 시작 시점 inference_history MAX(id) = {last_broadcast_inference_id}")
    except Exception as e:
        print(f"⚠️ MAX(id) 조회 실패 → 0으로 시작: {e}")

    threading.Thread(target=start_mqtt_loop, args=(main_loop,), daemon=True).start()
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_scheduled_batch, 'interval', seconds=5)
    scheduler.start()
    print("✅ 백엔드 허브 및 스케줄러 가동 준비 완료 (폴링 주기: 5초)")
    yield
    scheduler.shutdown()

app = FastAPI(title="Smart Farm Backend Hub", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.websocket("/ws/smart-farm")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True: await websocket.receive_text()
    except WebSocketDisconnect: manager.disconnect(websocket)

# ---------------------------------------------------------------------
# [REST] 누적된 추론 이력 조회 — 프론트 초기 로드용
# ---------------------------------------------------------------------
@app.get("/inference/history")
def get_inference_history(limit: int = 200):
    # Alert 이력은 "이상이 발생한 건"만 노출 → overall_level > 0 필터
    limit = max(1, min(limit, 1000))
    with engine.connect() as conn:
        result = conn.execute(sa.text("""
            SELECT sensor_id, overall_level, overall_status,
                   inference_result, action_required, data_timestamp
            FROM inference_history
            WHERE overall_level > 0
            ORDER BY created_at DESC
            LIMIT :limit
        """), {"limit": limit})
        rows = result.fetchall()

    return [
        {
            "sensor_id": row.sensor_id,
            "overall_alarm_level": row.overall_level,
            "overall_status": row.overall_status,
            "domain_reports": row.inference_result,
            "action_required": row.action_required,
            "timestamp": row.data_timestamp.isoformat() if row.data_timestamp else None,
        }
        for row in rows
    ]
