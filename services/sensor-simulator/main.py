import pandas as pd
import paho.mqtt.client as mqtt
import json
import time
import os
import boto3
from io import BytesIO
from datetime import datetime
from dotenv import load_dotenv # 추가

# 1. .env 파일 로드
# 프로젝트 루트에 있는 .env를 읽어옵니다.
load_dotenv()

# 환경 변수 (Docker Compose에서 주입받을 예정)
MQTT_HOST = os.getenv("MQTT_BROKER_HOST", "mqtt-broker")
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://data-lake:9000")
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
        print(f"Published to MQTT: {payload['timestamp']}")
        time.sleep(1)

if __name__ == "__main__":
    run_simulator()