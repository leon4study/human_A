# 1. 파이썬 실행 환경 설정 (경량화된 슬림 버전)
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

# 2. OS 레벨의 필수 시스템 도구 설치
# - build-essential: C/C++ 컴파일러 (Pandas, Numpy 빌드 시 필요)
# - libpq-dev: PostgreSQL 라이브러리 (psycopg2 실행 시 필요)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 3. 컨테이너 내 작업 디렉토리 생성 및 이동
WORKDIR /app

# 4. 파이썬 라이브러리 설치 (캐시 효율을 위해 소스보다 먼저 복사)
# - requirements.txt에 명시된 모든 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 5. 소스 코드 및 AI 모델 파일 전체 복사
COPY . .

# 6. 서비스 포트 개방 및 실행
# - 0.0.0.0으로 열어야 외부(컨테이너 밖)에서 접근 가능합니다.
EXPOSE 8000
CMD ["python", "main.py"]