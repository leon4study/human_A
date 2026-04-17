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

# 3. 소스 및 모델 데이터 복사 (필요한 파일만 선택)
# src 폴더 내에서 필요한 파일 두 가지만 이미지의 src/ 폴더로 복사합니다.
COPY src/inference_api.py ./src/
COPY src/logger.py ./src/

# 모델 파일 폴더 전체 복사
COPY models/ ./models/

# 4. 환경 변수 및 실행 설정
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# uvicorn 실행 경로 설정
CMD ["uvicorn", "src.inference_api:app", "--host", "0.0.0.0", "--port", "8000"]