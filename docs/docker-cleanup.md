# Docker 용량 관리

> 이 프로젝트는 7개 컨테이너를 사용합니다.
> 데이터는 Docker 볼륨이 아닌 **프로젝트 폴더 바인드 마운트**로 저장됩니다.

---

## 컨테이너 & 데이터 위치

| 컨테이너 | 이미지 | 데이터 저장 위치 |
|---------|-------|----------------|
| mqtt-broker | eclipse-mosquitto | 설정만, 데이터 없음 |
| smart-db | postgres:15 | `./data/db-data/` |
| data-lake | minio/minio | `./data/s3-bucket/` |
| sensor-simulator | 로컬 빌드 | — |
| backend-hub | 로컬 빌드 | — |
| s3-sink | 로컬 빌드 | — |
| inference-api | 로컬 빌드 (linux/amd64) | `./services/inference/models/` (읽기 전용) |

> `inference-api`는 compose에 `platform: linux/amd64`가 이미 지정되어 있어
> **buildx multi-builder 없이도** Mac(ARM)에서 실행됩니다.

---

## 현재 용량 확인

```bash
docker system df
```

`docker system df`의 Volumes 항목은 거의 0에 가깝게 나옵니다. 이 프로젝트의 실제 데이터는
Docker 볼륨이 아니라 `./data/` 폴더에 직접 저장되기 때문입니다.

실제 데이터 크기 확인:
```bash
du -sh ./data/db-data/ ./data/s3-bucket/
```

---

## 용량 확보 단계별 메뉴

### 1단계 — 컨테이너 종료 (데이터 보존)

```bash
docker compose down
```

### 2단계 — 안 쓰는 이미지 제거 (~수 GB)

```bash
docker image prune -a -f
```

빌드된 서비스 이미지(sensor-simulator, backend-hub, s3-sink, inference-api)와
외부 이미지(mosquitto, postgres, minio)가 모두 삭제됩니다.
다음 `docker compose up --build` 시 재빌드/재다운로드됩니다.

### 3단계 — DB·S3 데이터까지 초기화 (완전 리셋)

```bash
# 컨테이너 종료 후
rm -rf ./data/db-data/
rm -rf ./data/s3-bucket/

# 재시작 시 빈 DB + 빈 버킷으로 자동 재생성
docker compose up --build
```

> ⚠ DB 데이터(알람 이력·추론 결과)가 전부 삭제됩니다. 개발·테스트 데이터라 문제없을 경우에만 사용.

### 빠른 전체 정리 (이미지 + 캐시)

```bash
docker compose down
docker system prune -a -f
```

---

## buildx 관련 메모

이 프로젝트는 `docker buildx`가 **필요 없습니다**.
compose.yaml의 `inference-api` 서비스에 `platform: linux/amd64`가 이미 지정되어 있어
Docker Desktop이 자동으로 처리합니다.

시스템에 `buildx multi-builder`가 남아있다면 다른 프로젝트에서 생성된 것입니다.
불필요하면 제거:
```bash
docker buildx rm multi-builder   # ~10GB 해제
```
