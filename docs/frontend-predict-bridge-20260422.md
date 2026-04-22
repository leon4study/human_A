# Frontend → Inference 직접 호출 브릿지 (2026-04-22)

## 배경

front-back 브랜치 작업 중 인프라가 의도치 않게 수정되어 추론 결과가 프론트로 전달되지 않는 상태였음. 사용자 요구사항:

- **인프라 일체 수정 금지** (services/, infra/, docker-compose.yaml, .env*, Dockerfile 모두 포함)
- 추론 서버 연결 문제를 frontend/ 안에서만 해결

## 진단

### 시스템 데이터 흐름 (정상 설계)

```
sensor-simulator → MQTT
   ├─→ s3-sink → MinIO bucket "raw-data"
   └─→ backend-hub → WebSocket "RAW" → frontend ✅

inference-api 배치 (1분) → MinIO 읽기 → DB inference_history
   → backend 5초 폴링 → WebSocket "INFERENCE" → frontend ✅
```

### 실제 상태 (망가진 부분)

- backend `[RAW] MQTT 수신` 로그 정상 (1초/건)
- DB `inference_history` 마지막 row: `2026-04-22 03:47:41` (13시간 전)
- `inference-api /health`의 `batch.last_error`:
  > `NoSuchBucket: The specified bucket does not exist`

### 근본 원인

| 위치 | 버킷명 |
|------|-------|
| `s3-sink/main.py` (하드코딩) | `raw-data` ← 데이터 여기 저장 |
| `inference_api.py` 기본값 | `raw-data` |
| `.env.prod` `S3_BUCKET_NAME` | `smart-farm-bucket` ← 존재하지 않음 |
| MinIO 실제 버킷 | `raw-data`, `sensor-data` |

`.env.prod`의 환경변수 오버라이드가 inference 컨테이너에서 잘못된 버킷명으로 들어가, 13시간째 추론 결과 0건. 정석은 `.env.prod` 한 줄 수정이지만, 사용자 요청에 따라 **인프라를 건드리지 않고 frontend에서만 우회**하기로 결정.

## 해결 방안 — Frontend Bridge

`inference-api`의 `/predict` 엔드포인트는 **동기 호출 시 정상 작동**함을 확인 (4 도메인 모델 전부 로드됨, RAW 페이로드 던지면 완전한 inference 응답 반환). S3 배치만 죽었지 추론 자체는 살아있음.

→ Frontend가 RAW 데이터를 받자마자 `/predict`에 직접 POST해서 INFERENCE 흐름을 살린다.

### 변경 1: Vite proxy 추가

[frontend/vite.config.ts](../frontend/vite.config.ts)

```ts
server: {
  proxy: {
    '/inference': 'http://localhost:8080',
    '/ws': { target: 'ws://localhost:8080', ws: true },
    '/predict': 'http://localhost:8000',  // ← 신규: inference-api 직통
  },
},
```

CORS 우회 (`inference-api`는 CORSMiddleware 없음 → 브라우저 직접 호출 불가) + 같은 origin으로 묶음.

### 변경 2: useDashboardSocket에 /predict 폴링 추가

[frontend/src/app/hooks/useDashboardSocket.ts](../frontend/src/app/hooks/useDashboardSocket.ts)

추가된 것:

1. `mapPredictResponseToInferencePayload()` — `/predict` 응답을 WS INFERENCE와 동일한 `InferencePayload`로 정규화
   - `/predict` 응답은 `rca_top3`, DB `inference_result`는 `rca` → 둘 다 수용
   - `domain_reports[X].alarm/rca/score/metrics` 등 추출
2. `lastSeenRawRef` — debounce ref와 분리된 "최근 RAW 데이터 항상 보관" ref
3. `processInferencePayload(payload, source)` — INFERENCE 처리 통합 헬퍼
   - 기존 WS INFERENCE 인라인 처리 코드 그대로 추출
   - `alarmEvents`, `latestInference`, `chartSnapshot`, `comparativeMetrics`, `alertItems` 모두 처리
   - 호출 출처를 `source` 인자로 받아 콘솔에 표시 (`[WS]` vs `[PREDICT]`)
4. 새 useEffect — 15초마다 `lastSeenRawRef`를 `/predict`에 POST → 응답 매핑 → `processInferencePayload(payload, "PREDICT")`
   - 첫 호출은 RAW 도착할 시간 2초 후 한 번 → 이후 15초 간격
   - 실패 시 console.error, 다음 주기 재시도

기존 WS INFERENCE 핸들러는 인라인 60줄 → 1줄(`processInferencePayload(message.payload, "WS")`)로 축약.

## 비판적 리뷰 (1차 → 2차)

| # | 잠재 이슈 | 평가 / 처리 |
|---|----------|------------|
| 1 | WS INFERENCE + /predict 동시 도착 race | 백엔드 INFERENCE 안 오는 상태라 충돌 없음. 향후 살아나도 마지막 setter가 이김 (안전) |
| 2 | RAW 도착 전 첫 /predict 호출 | `if (!raw) return` 가드 |
| 3 | /predict 실패 처리 | try/catch + console.error, 다음 15초 재시도 |
| 4 | Unmount 후 in-flight fetch | `cancelled` 플래그로 응답 무시 (AbortController는 미사용) |
| 5 | React Strict Mode 이중 호출 | cleanup → setup 동기 실행으로 setInterval 1개만 잔존 |
| 6 | 빈 응답 매핑 | 모든 필드 nullish fallback |
| 7 | **프로덕션 빌드는 vite proxy 없음** | dev 전용 솔루션. 프로덕션은 별도 처리 필요 (nginx proxy / 백엔드에 endpoint 추가 등) ⚠️ |
| 8 | 15초마다 ML 호출 부하 | 1인 dev OK. 다중 사용자/prod에서는 부하 증가 ⚠️ |
| 9 | 다중 탭 시 부하 배수 | dev에서 보통 1탭, 안전 |
| 10 | ref closure 신선도 | `.current`로 항상 최신값 읽음 |
| 11 | 빈 문자열 처리 | `?? null`은 nullish만 fallback, 빈 문자열은 그대로 통과 (의도) |
| 12 | 첫 호출까지 15초 대기 (체감) | **수정**: 2초 후 즉시 1회 호출 + 이후 15초 간격 |

## 검증

### 호스트에서 /predict 직접 호출
```bash
curl -X POST http://localhost:8000/predict -H "Content-Type: application/json" \
  -d '{"timestamp":"2026-04-22T07:38:35","pump_rpm":1804,"flow_rate_l_min":37.1,...}'
```
→ 정상 응답: `overall_alarm_level`, `domain_reports`(4개 도메인), `rca_top3` 등 완전한 페이로드.

### TypeScript
```
npx tsc --noEmit  # exit 0
```

### 브라우저 테스트 (사용자 수행 필요)
1. `npm run dev` 또는 dev server 재시작 (vite.config.ts 변경 반영)
2. 페이지 로드 후 콘솔 확인:
   - `✅ FastAPI 실시간 서버 연결 성공!` (WS 연결)
   - `🔍 INFERENCE [PREDICT]: {...}` (2초 후, 이후 15초 간격)
3. AI 분석 모달 열어 비교분석/원인진단 데이터 표시 확인
4. systemStatus 색상 갱신 확인

## 알려진 한계

- **dev 전용**: vite proxy는 `npm run build` 결과물에는 없음. 프로덕션 배포 전에 다른 경로 필요
- **부하**: 15초마다 ML 추론 호출. inference-api 단일 컨테이너 부하 ↑
- **DB 저장 X**: /predict로 만든 결과는 DB에 안 들어감. 새 Alert 이력은 frontend 메모리만 유지, 새로고침 시 사라짐 (DB의 옛날 INFERENCE 이력은 `/inference/history`로 여전히 로드됨)
- **상위 진짜 해결책**: `.env.prod`의 `S3_BUCKET_NAME`을 `raw-data`로 수정 (인프라 1줄 수정) → batch 정상화 → DB 저장 + 모든 경로 제대로 작동. 이건 사용자 결정 사항.

## 변경 파일 (frontend만)

- [frontend/vite.config.ts](../frontend/vite.config.ts) — `/predict` proxy 1줄 추가
- [frontend/src/app/hooks/useDashboardSocket.ts](../frontend/src/app/hooks/useDashboardSocket.ts) — 헬퍼 함수 추가 + INFERENCE 처리 통합 + /predict 폴링 useEffect 추가

인프라 0 변경 ✅
