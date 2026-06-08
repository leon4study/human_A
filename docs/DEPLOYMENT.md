# 배포 가이드

이 문서는 막힘주의보 스택을 서버(예: 단일 VM/EC2)에 올려 운영하는 절차를 다룬다.
로컬 첫 실행은 [ONBOARDING.md](ONBOARDING.md)를, 시스템 구성은 루트 [README.md](../README.md)를 본다.

현재 이 프로젝트는 CI/CD 파이프라인이 없다. 배포는 서버에서 직접 `docker compose`로 수행한다.
이 문서는 그 수동 절차를 문서화한 것이며, 자동화는 향후 과제다.

## 전제

- 배포 대상: Docker / Docker Compose v2가 설치된 Linux 서버.
- 포트 인바운드 개방 정책은 노출할 서비스에 맞춰 최소화한다(아래 표).
- 운영 비밀값은 `.env.prod`로 관리한다(저장소 미포함, `.gitignore` 대상).

| 서비스 | 컨테이너 포트 | 외부 노출 권장 |
|---|---|---|
| 추론 API | 8000 | 내부/제한적 |
| 백엔드 | 8080 | 필요 시 |
| MinIO 콘솔 | 9001 | 운영자 IP 한정 |
| PostgreSQL | 5432 | 미노출(내부 네트워크만) |
| MQTT | 1883 | 미노출 권장 |

실제 포트 매핑은 `docker-compose.yaml`을 기준으로 한다. 루트 README의 일부 포트 표기와
다를 수 있으니 compose 파일을 정본으로 본다.

## 1. 코드·환경 준비

```bash
git clone https://github.com/leon4study/human_A.git
cd human_A
git switch main && git pull

# 운영 환경변수 작성 (.env.example를 토대로 운영값 채움)
cp .env.example .env.prod
# .env.prod 의 비밀번호·접속 URL을 운영값으로 채운다 (DB 비밀번호는 강한 값으로)
```

운영에서는 `--env-file`로 `.env.prod`를 명시해 기동한다.

```bash
docker compose --env-file .env.prod up -d --build
```

## 2. 모델 산출물 배치

추론 컨테이너는 `./services/inference/models/`를 마운트한다. 4개 도메인의 모델 파일
(`*_model.keras`, `*_config.json`, `*_scaler.pkl`, `*_shap.json`)이 있어야 한다.
이 파일들은 용량 때문에 저장소에 포함하지 않으므로 배포 시 별도로 전달한다.

- 서버에서 직접 학습: `python src/train.py` (학습 데이터 필요).
- 또는 학습 머신에서 산출한 `models/`를 `scp`/`rsync`로 서버에 복사.

자세한 학습 절차는 [modeling/07_training_runbook.md](modeling/07_training_runbook.md) 참조.

## 3. 데이터 영속성

| 데이터 | 호스트 경로(바인드 마운트) | 비고 |
|---|---|---|
| PostgreSQL | `./data/db-data` | 알람·점수. 백업 대상 |
| MinIO 버킷 | `./data/s3-bucket` | 배치 적재 데이터 |

`docker compose down` 후에도 위 경로 데이터는 유지된다. 백업은 이 디렉터리를 대상으로 한다.
DB 초기화 스크립트(`./infra/postgres/initdb.d`)는 `db-data`가 없을 때 최초 1회만 실행된다.

## 4. 기동 확인

```bash
docker compose --env-file .env.prod ps
curl -s http://localhost:8000/health        # 추론 헬스체크
docker compose logs --tail=50 inference-api # 모델 4개 로드 확인
```

## 5. 업데이트 / 롤백

```bash
# 업데이트
git pull
docker compose --env-file .env.prod up -d --build

# 롤백 — 직전 커밋으로
git checkout <이전_커밋_SHA>
docker compose --env-file .env.prod up -d --build
```

## 6. 운영 보조 스크립트

- `run_pipeline.sh` — 파이프라인 일괄 실행 스크립트(저장소 루트). 용도·사용법은 스크립트
  내부 주석을 확인한 뒤 운영 절차에 편입한다.

## 향후 과제

- CI/CD 자동화(빌드·테스트·이미지 푸시·배포). 결정 시 [adr/](adr/)에 ADR로 기록한다.
- 모델 산출물 배포 방식 표준화(아티팩트 저장소 또는 오브젝트 스토리지).
- 비밀값 관리(현재 `.env.prod` 파일 → 시크릿 매니저 이관 검토).
