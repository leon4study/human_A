FROM python:3.11-slim

# 1. 필수 시스템 패키지 및 시간대 설정
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Seoul
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# 2. 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 3. 소스 및 모델 데이터 복사 (추론 런타임에 필요한 파일만)
COPY src/inference_api.py ./src/
COPY src/inference_core.py ./src/
COPY src/preprocessing.py ./src/
COPY src/logger.py ./src/

# 모델 파일 폴더 전체 복사
COPY models/ ./models/

# 4. 환경 변수 및 실행 설정
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# inference_api.py가 `from logger import ...` 같은 top-level import를 쓰므로
# src/ 를 모듈 탐색 경로에 포함시킨다.
ENV PYTHONPATH=/app/src

EXPOSE 8000

# WORKDIR을 src로 바꿔서 `uvicorn inference_api:app` 형태로 실행
WORKDIR /app/src
CMD ["uvicorn", "inference_api:app", "--host", "0.0.0.0", "--port", "8000"]