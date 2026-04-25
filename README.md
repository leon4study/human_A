# 🌿 Smart Farm Anomaly Detection System (v2)

실시간 센서 데이터 스트리밍과 AI 추론을 활용한 스마트팜 이상 징후 감지 및 원인 분석(RCA) 시스템입니다.

## 🏗️ System Architecture
본 프로젝트는 데이터 엔지니어링 파이프라인의 전 과정을 포함합니다.
1. **Data Ingestion**: MinIO(S3)의 원천 데이터를 읽어 MQTT 브로커로 실시간 발행 (Sensor Simulator)
2. **Data Pipeline**: MQTT 데이터를 구독하여 실시간 모니터링 및 주기적 데이터 적재 (S3 Sink)
3. **AI Inference**: 적재된 데이터를 바탕으로 이상 수치 감지 및 근본 원인(RCA) 분석
4. **Storage**: 분석 인사이트(Alarm, Score) 저장을 위한 PostgreSQL (JSONB 활용)
5. **Visualization**: 실시간 대시보드 제공 (FastAPI & React)

## 폴더 구조

```
smart-farm-root/
├── docker-compose.yml         # 전체 서비스의 배치도 및 연결 정의
├── .env                       # DB 암호, API 키, 호스트 주소 등 민감 정보/설정
│
├── infra/                     # [이미 검증된 솔루션] 설정 파일만 관리
│   ├── mosquitto/             # MQTT 브로커 설정
│   │   └── config/
│   │       └── mosquitto.conf
│   ├── postgres/              # DB 초기화 스크립트 및 스키마
│   │   └── initdb.d/
│   │       └── schema.sql
│   └── minio/                 # S3 Mock (로컬 저장소)
│
├── services/                  # [비즈니스 로직] 직접 코딩하고 Docker 이미지 빌드
│   ├── frontend/              # React: 실시간 모니터링 대시보드
│   │   ├── Dockerfile
│   │   ├── package.json
│   │   └── src/
│   ├── backend/               # FastAPI: API 서버 및 실시간 데이터 중계(WebSocket)
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── app/
│   ├── sensor-simulator/      # 시뮬레이터: S3의 원천 데이터를 읽어 MQTT로 발행
│   │   ├── Dockerfile
│   │   └── main.py
│   ├── s3-sink-connector/     # 저장 로직: MQTT 메시지를 실시간으로 S3(MinIO)에 저장
│   │   ├── Dockerfile
│   │   └── connector.py
│   └── inference-engine/      # AI 추론: 10분 배치로 S3 데이터를 분석하여 DB 저장
│       ├── Dockerfile
│       ├── models/            # 학습된 모델 파일
│       └── predict.py
│
└── data/                      # [로컬 전용] 컨테이너 데이터 보존 (Git 제외)
    ├── db-data/               # PostgreSQL 데이터 파일 (파일 있으면 schema.sql 실행 안 된다. )
    └── s3-bucket/             # MinIO 저장소 파일

```

## 🛠️ Tech Stack
- **Language**: Python 3.12
- **Infrastructure**: Docker, MQTT(Mosquitto), MinIO (S3 Mock), PostgreSQL
- **Backend**: FastAPI, SQLAlchemy, Paho-MQTT
- **Data Science**: Pandas, Scikit-learn (Isolation Forest or LSTM-AE)

## 🚀 How to Run
1. **Infrastructure Up**
   ```bash
   docker-compose up -d

