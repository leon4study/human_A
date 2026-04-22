FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY . .

# FastAPI(Uvicorn) 실행
# 0.0.0.0으로 설정해야 컨테이너 외부(호스트/리액트)에서 접속 가능합니다.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]