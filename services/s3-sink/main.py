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
load_dotenv()

# 환경 변수 (설정이 없으면 기본값 사용)
MQTT_HOST = os.getenv("MQTT_BROKER_HOST", "localhost")
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:9000")
S3_ACCESS_KEY = os.getenv("MINIO_ROOT_USER", "admin")
S3_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", "password123")
BUCKET_NAME = "raw-data"

# 상태 관리 변수 (메모리 버퍼)
data_buffer = []
# 10분(600초) 주기로 설정 (테스트 시에는 60으로 줄여서 확인하세요)
FLUSH_INTERVAL = 600 
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
        # 10분 단위로 올림 처리하여 파일명 생성 (예: 15시 12분에 저장 시 15시 10분 데이터로 명명)
        rounded_min = (now.minute // 10) * 10
        file_name = f"sensor_{now.strftime('%H')}{rounded_min:02d}.csv"
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
        data_buffer.append(payload)

        # [로그 추가] 데이터가 쌓이고 있는지 확인하세요
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