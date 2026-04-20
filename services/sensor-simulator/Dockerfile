# 1. 파이썬 경량 버전 사용 (빌드 속도와 이미지 용량 최적화)
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

# 2. 컨테이너 내 작업 디렉토리 생성 및 이동
WORKDIR /app

# 3. 의존성 설치 (캐시 활용을 위해 소스코드보다 먼저 복사)
# requirements.txt에 pandas, paho-mqtt, boto3, python-dotenv가 들어있어야 합니다.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. 소스 코드 복사 (로컬의 main.py를 컨테이너의 /app으로)
COPY main.py .

# 5. 실행 (python3 명령어로 스크립트 실행)
CMD ["python", "main.py"]