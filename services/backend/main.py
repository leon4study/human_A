import os
from dotenv import load_dotenv
import json
import asyncio
import threading
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body
from fastapi.middleware.cors import CORSMiddleware
import paho.mqtt.client as mqtt

load_dotenv("../../.env")

app = FastAPI(title="Smart Farm Backend Hub")

# CORS 설정 (리액트 연결용)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ---------------------------------------------------------------------
# [웹소켓 관리자] 리액트에게 실시간 전송
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
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

# ---------------------------------------------------------------------
# [MQTT 로직] 브로커에서 데이터를 '계속' 가져오는 엔진
# ---------------------------------------------------------------------
def start_mqtt_loop(loop):
    # MQTT 콜백 함수들
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("✅ [MQTT] 브로커 연결 성공!")
            client.subscribe("sensor/data")
        else:
            print(f"❌ MQTT 연결 실패: {rc}")

    def on_message(client, userdata, msg):
        try:
            raw_data = json.loads(msg.payload.decode())
            print(f"📥 [RAW DATA] 브로커 수신 완료")
            
            # [수정 핵심] 메인 서버의 이벤트 루프에 broadcast 작업을 던집니다.
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({"type": "RAW", "payload": raw_data}),
                loop
            )
        except Exception as e:
            print(f"❌ 데이터 처리 에러: {e}")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=f"hub-{os.getpid()}")
    client.on_connect = on_connect
    client.on_message = on_message

    mqtt_host = os.getenv("BE_MQTT_BROKER_HOST", "127.0.0.1")
    client.connect(mqtt_host, 1883, 60)
    client.loop_forever()

# --- FastAPI 부분 ---
@app.on_event("startup")
async def startup_event():
    # 현재 실행 중인 메인 이벤트 루프를 가져옵니다.
    loop = asyncio.get_running_loop()
    # MQTT 스레드에 메인 루프를 전달합니다.
    thread = threading.Thread(target=start_mqtt_loop, args=(loop,), daemon=True)
    thread.start()

@app.websocket("/ws/smart-farm")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/api/inference-report")
async def receive_inference(data: dict = Body(...)):
    await manager.broadcast({"type": "INFERENCE", "payload": data})
    return {"status": "ok"}