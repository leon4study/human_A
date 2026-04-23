import paho.mqtt.client as mqtt
import json
import os
import boto3
import pandas as pd
from datetime import datetime
from io import StringIO
from dotenv import load_dotenv

# 1. 환경 설정 로드
# 프로젝트 루트 혹은 현재 폴더의 .env를 읽어옵니다.

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

# 환경 변수 (설정이 없으면 기본값 사용)
MQTT_HOST = os.getenv("MQTT_BROKER_HOST", "localhost")
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:9000")
S3_ACCESS_KEY = os.getenv("MINIO_ROOT_USER", "admin")
S3_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", "password123")
BUCKET_NAME = "raw-data"

# 상태 관리 변수 (메모리 버퍼)
data_buffer = []
# 1분(60초) 주기 — 대시보드 실시간 테스트용
FLUSH_INTERVAL = 60
last_flush_time = datetime.now()

def upload_to_s3(buffer):
    """메모리에 쌓인 데이터를 CSV로 변환하여 MinIO(S3)에 적재합니다."""
    if not buffer:
        print("Empty buffer, skipping upload.")
        return

    try:
        # S3 클라이언트 생성
        s3 = boto3.client(
            's3',
            endpoint_url=S3_ENDPOINT,
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY,
            region_name='us-east-1' # MinIO 호환성을 위한 가상 리전
        )
        
        # 버킷 존재 여부 확인 및 생성
        try:
            s3.head_bucket(Bucket=BUCKET_NAME)
        except:
            s3.create_bucket(Bucket=BUCKET_NAME)
            print(f"Created new bucket: {BUCKET_NAME}")

        # 데이터 변환 (JSON List -> Pandas DataFrame -> CSV)
        df = pd.DataFrame(buffer)
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)
        
        # 파일 경로 설계 (Hive Partitioning: year/month/day/file.csv)
        now = datetime.now()
        # 1분 단위 파일명 (FLUSH_INTERVAL=60초와 짝을 맞춰 덮어쓰기 방지)
        file_name = f"sensor_{now.strftime('%H%M')}.csv"
        path = f"year={now.year}/month={now.month:02d}/day={now.day:02d}/{file_name}"
        
        # 업로드 실행
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=path,
            Body=csv_buffer.getvalue()
        )
        print(f"✅ [SUCCESS] {len(buffer)}개의 행을 '{path}'에 저장했습니다.")
        
    except Exception as e:
        print(f"❌ [ERROR] S3 업로드 중 오류 발생: {e}")

def on_connect(client, userdata, flags, rc, properties=None):
    """MQTT 브로커 연결 성공 시 호출"""
    if rc == 0:
        print(f"Connected to MQTT Broker at {MQTT_HOST}")
        client.subscribe("sensor/data")
    else:
        print(f"Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    """메시지 수신 시 버퍼링 및 주기적 Flush"""
    global last_flush_time, data_buffer
    
    try:
        payload = json.loads(msg.payload.decode())
        print(f"[RAW] MQTT 수신 | {json.dumps(payload, ensure_ascii=False)}")
        data_buffer.append(payload)

        if len(data_buffer) % 10 == 0:
            print(f"📦 현재 버킷에 {len(data_buffer)}개 데이터 쌓임...")
        
        # 현재 시간과 마지막 저장 시간 비교
        elapsed = (datetime.now() - last_flush_time).seconds
        if elapsed >= FLUSH_INTERVAL:
            print(f"⏰ {elapsed}초 경과. 배치를 실행합니다...")
            upload_to_s3(data_buffer)
            
            # 초기화
            data_buffer = []
            last_flush_time = datetime.now()
            
    except Exception as e:
        print(f"Data processing error: {e}")

# Main 실행부
if __name__ == "__main__":
    # Paho-MQTT v2 API 사용
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"S3 Sink Connector 시작 중... (Target: {S3_ENDPOINT})")
    
    try:
        client.connect(MQTT_HOST, 1883, 60)
        # 루프 시작 (백그라운드에서 계속 메시지 대기)
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nS3 Sink Connector 종료 중...")
        # 종료 전 남아있는 데이터가 있다면 저장 시도
        if data_buffer:
            upload_to_s3(data_buffer)