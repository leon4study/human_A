# 첫 실행 가이드 (Docker 온보딩)

이 문서는 저장소를 처음 클론한 사람이 전체 스택을 로컬에서 띄우기까지의 모든 단계를 안내한다.
프로젝트가 무엇인지부터 보려면 루트 [README.md](../README.md)와 [docs/README.md](README.md)를 먼저 본다.

전체 구성은 7개 서비스다(루트 [README.md](../README.md) §2 시스템 개요 참조).

| 서비스 | 컨테이너명 | 포트(호스트) | 역할 |
|---|---|---|---|
| MQTT 브로커 | `mqtt-broker` | 1883 | 센서 메시지 발행/구독 |
| PostgreSQL | `smart-db` | 5432 | 알람·점수 저장 |
| MinIO (S3 목업) | `data-lake` | 9000(API) / 9001(콘솔) | 배치 데이터 적재 |
| 센서 시뮬레이터 | `sensor-simulator` | — | 센서값 생성·발행 |
| 백엔드 허브 | `backend-hub` | 8080 | REST·WebSocket |
| S3 Sink | `s3-sink` | — | MQTT → MinIO 10분 적재 |
| 추론 API | `smart-inference-api` | 8000 | 4도메인 AE 추론 |

---

## 사전 준비

### 1. Docker

Docker Desktop(또는 Docker Engine) + Docker Compose v2 가 필요하다. 설치 확인:

```bash
docker --version
docker compose version
```

Apple Silicon(M1~) Mac 사용자: 추론 서비스는 `platform: linux/amd64` 로 빌드된다
(docker-compose.yaml 의 `inference-api`). 에뮬레이션으로 동작하므로 빌드·기동이 다소 느릴 수 있다.

### 2. 환경변수 파일 (.env)

루트의 `docker-compose.yaml` 은 `.env` 의 값을 읽는다. 템플릿을 복사해 채운다.

```bash
cp .env.example .env
# 편집기로 .env 를 열어 <CHANGE_ME> (DB·MinIO 비밀번호 등) 를 채운다
```

`.env` 는 `.gitignore` 대상이라 커밋되지 않는다(비밀값 보호). 공유용 템플릿은 `.env.example` 뿐이다.

### 3. 추론 모델 파일 (가장 흔한 함정)

추론 서비스는 `./services/inference/models/` 를 컨테이너로 마운트한다. 이 디렉터리에는
4개 도메인 각각의 4개 파일이 있어야 한다.

```
motor_model.keras      motor_config.json      motor_scaler.pkl      motor_shap.json
hydraulic_model.keras  hydraulic_config.json  hydraulic_scaler.pkl  hydraulic_shap.json
nutrient_model.keras   nutrient_config.json   nutrient_scaler.pkl   nutrient_shap.json
zone_drip_model.keras  zone_drip_config.json  zone_drip_scaler.pkl  zone_drip_shap.json
```

이 모델 산출물은 용량 때문에 git 에 포함하지 않는다(미추적). 클론 직후엔 비어 있을 수 있다.
없으면 추론 API 가 모델 로드에 실패한다. 다음 중 하나로 채운다.

- 직접 학습: `python src/train.py` 실행(학습 결과가 `models/` 에 저장됨). 학습 절차는
  [docs/modeling/07_training_runbook.md](modeling/07_training_runbook.md) 참조.
- 또는 팀에서 공유한 모델 산출물을 위 경로에 복사.

존재 확인:

```bash
ls services/inference/models/
```

---

## 실행

```bash
# 처음 실행 — 이미지 빌드 포함 (네트워크·플랫폼에 따라 수 분 소요)
docker compose up -d --build

# 코드 수정 없이 재시작 (재빌드 불필요)
docker compose up -d
```

`-d` 는 백그라운드 실행이다. 빌드 로그를 보려면 `-d` 없이 실행한다.

---

## 정상 동작 확인

### 1. 컨테이너 상태

```bash
docker compose ps
```

7개 서비스가 모두 `running`(또는 `Up`) 이어야 한다. `sensor-simulator` 는 `restart: on-failure`
라서 의존 서비스가 늦게 뜨면 잠깐 재시작할 수 있다.

### 2. 로그

```bash
docker compose logs -f inference-api     # 모델 4개 로드 성공 메시지 확인
docker compose logs -f backend-hub       # WebSocket·DB 연결 확인
docker compose logs -f s3-sink           # MinIO 적재 동작 확인
```

### 3. URL / 헬스체크

| 대상 | URL | 확인 내용 |
|---|---|---|
| 추론 API 헬스 | http://localhost:8000/health | 응답 정상 |
| 추론 API 문서 | http://localhost:8000/docs | FastAPI Swagger UI |
| 백엔드 | http://localhost:8080 | REST 응답 |
| MinIO 콘솔 | http://localhost:9001 | `.env` 의 MINIO 계정으로 로그인 |

브라우저 없이 빠르게:

```bash
curl -s http://localhost:8000/health
```

---

## 종료

```bash
docker compose stop          # 컨테이너 정지 (삭제 안 함, 데이터 유지)
docker compose down          # 컨테이너·네트워크 삭제 (볼륨/바인드 데이터는 유지)
```

DB 데이터(`./data/db-data`)와 MinIO 데이터(`./data/s3-bucket`)는 바인드 마운트라
`down` 후에도 디스크에 남는다. 완전 초기화하려면 해당 디렉터리를 직접 비운다(주의: 데이터 삭제).

Docker 이미지·용량 정리는 [docs/docker-cleanup.md](docker-cleanup.md) 참조.

---

## 트러블슈팅

### 포트 충돌 — `bind: address already in use`

1883/5432/8000/8080/9000/9001 중 하나를 다른 프로세스가 쓰는 경우다.

```bash
# macOS / Linux — 예: 8000 포트 점유 프로세스 확인
lsof -i :8000
```

점유 프로세스를 종료하거나, `docker-compose.yaml` 의 호스트 포트를 바꾼다(예: `"8001:8000"`).

### 환경변수가 안 들어감

`.env` 변경 후에는 컨테이너를 재생성해야 반영된다.

```bash
docker compose up -d --force-recreate
```

컨테이너에 실제로 주입됐는지 확인:

```bash
docker compose exec inference-api env | grep DATABASE_URL
```

### 추론 API 가 계속 재시작됨

대개 모델 파일 누락(사전 준비 3)이거나 DB 연결 실패다. 로그를 본다.

```bash
docker compose logs --tail=50 inference-api
```

- "모델 로드 실패" 류 → `services/inference/models/` 채우기(사전 준비 3).
- DB 연결 거부 → `smart-db` 가 먼저 떴는지, `.env` 의 `AI_DATABASE_URL` 이 맞는지 확인.

### DB 초기화가 안 됨

`smart-db` 는 최초 1회만 `./infra/postgres/initdb.d` 의 스크립트를 실행한다. 이미 한 번 떠서
`./data/db-data` 가 생긴 뒤에는 초기화 스크립트가 다시 실행되지 않는다. 스키마를 새로 깔려면
`./data/db-data` 를 비우고 다시 `up` 한다(주의: 기존 DB 데이터 삭제).

### Apple Silicon 에서 추론 빌드가 느리거나 실패

`inference-api` 의 `platform: linux/amd64` 에뮬레이션 때문이다. Docker Desktop 의
Rosetta 가속(Settings → General → "Use Rosetta for x86/amd64 emulation")을 켜면 개선된다.

---

## 다음에 볼 문서

- 모델을 직접 학습·재현하려면: [docs/modeling/07_training_runbook.md](modeling/07_training_runbook.md)
- API 스펙(요청/응답): [docs/INFERENCE_API.md](INFERENCE_API.md)
- 전체 문서 인덱스: [docs/README.md](README.md)
