import pandas as pd
import paho.mqtt.client as mqtt
import json
import time
import os
import boto3
from io import BytesIO
from datetime import datetime
from dotenv import load_dotenv # 추가

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

# 환경 변수 (Docker Compose에서 주입받을 예정)
MQTT_HOST = os.getenv("MQTT_BROKER_HOST", "localhost")
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:9000")
S3_ACCESS_KEY = os.getenv("MINIO_ROOT_USER", "admin")
S3_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", "password123")
BUCKET_NAME = "sensor-data" 
FILE_NAME = "sensor.csv"

def run_simulator():
    # 1. S3(MinIO) 접속
    s3 = boto3.client(
        's3',
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY
    )
    
    # 2. 데이터 가져오기 (수동으로 넣었다고 가정)
    try:
        print(f"Connecting to MinIO at {S3_ENDPOINT}...")
        obj = s3.get_object(Bucket=BUCKET_NAME, Key=FILE_NAME)
        df = pd.read_csv(BytesIO(obj['Body'].read()))
        print(f"Successfully loaded {len(df)} rows from {FILE_NAME}")
    except Exception as e:
        print(f"Error: 버킷이나 파일이 없습니다. MinIO(9001)에서 직접 확인하세요. 상세: {e}")
        return

    # 3. MQTT 접속 및 발행
    client = mqtt.Client()
    client.connect(MQTT_HOST, 1883)
    
    print("Starting simulation (1 row/sec)...")
    for _, row in df.iterrows():
        payload = row.to_dict()
        payload['timestamp'] = datetime.now().isoformat() # 현재 시각 주입
        
        client.publish("sensor/data", json.dumps(payload))
        print(f"[RAW] Published | {json.dumps(payload, ensure_ascii=False)}")
        time.sleep(1)

if __name__ == "__main__":
    run_simulator()