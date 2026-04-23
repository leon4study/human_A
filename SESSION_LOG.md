# SESSION_LOG

## 2026-04-21 — 프론트 연동 스펙 정리 (FRONTEND_PAGES.md 신설 · 필터 페이지 결정 · raw_inputs 확장)

### ✅ 달성 (Accomplished)

1. **필터 페이지 처리 방침 결정** (dabin.csv 43,200행 상관분석 근거):
   - `filter_pressure_in` vs `discharge_pressure`: r=**0.757** (비슷하지만 중복은 아님)
   - `filter_pressure_in` vs `filter_pressure_out`: r=**0.994** → out 측은 이미 [preprocessing.py:621](src/preprocessing.py#L621)에서 drop됨
   - **`filter_delta_p` vs `pump_delta_p`: r=0.374** → **독립 정보** (펌프 상태 ≠ 필터 오염도)
   - 하지만 dabin.csv엔 필터 막힘 시나리오 거의 없음 (`filter_delta_p` CV=3.1%, `hidden_risk_stage=watch`에서도 +0.26 kPa만)
   - **결정**: 필터 페이지는 **AE 모델 없이 룰 기반**으로 운영 (경고 Δp>15 kPa, 위험 Δp>25 kPa)

2. **`docs/FRONTEND_PAGES.md` 신설**: 프론트 작업자 질의(설비별 페이지 구성·AI 분석 페이지 내용·비교분석 7지표·CTP 시각화·타임라인 간격·데이터 정보)에 코드 기반 답변. 4개 AE 도메인(motor/hydraulic/nutrient/zone_drip) + 필터 룰 페이지.

3. **`docs/INFERENCE_API.md` 업데이트**:
   - §4-3 `raw_inputs`에 `filter_pressure_in_kpa`, `filter_pressure_out_kpa` 추가 문서화
   - §7-1 한글 라벨 정정 (`flow_per_power` = 유량 대비 전력 효율, `pressure_per_power` = 압력 대비 전력 효율 — 사용자 네이밍 규칙 준수)
   - §7-1 `pressure_flow_ratio_discharge` → `pressure_flow_ratio`로 단순화 (해석용 공식 = 토출/유량 으로 프론트 통일)
   - §7-4 신설: 필터 페이지 룰 기반 가이드 (`filter_delta_p_kpa` 계산법·임계)
   - §8-2 업데이트: `pressure_flow_ratio` 인코딩 활용 여부 검토 중임을 명시
   - §3-3, §10 용어집에 필터 관련 키 추가

4. **`inference_api.py` raw_inputs passthrough 확장** (src/ + services/inference/src/ 두 파일 모두):
   - `raw_input_keys`에 `filter_pressure_in_kpa`, `filter_pressure_out_kpa` 2개 추가
   - 요청 body에 존재하는 키만 담는 기존 안전장치 유지
   - AE 모델 config는 건드리지 않음 (filter는 모델 입력 아님, 프론트 파생용)

### ⏳ 남은 과제 (Pending)

1. **프론트 작업자에게 `docs/FRONTEND_PAGES.md` + `docs/INFERENCE_API.md` 전달** → 설비 페이지 4개(motor/hydraulic/nutrient/zone_drip) + 필터 룰 페이지 + AI 분석 페이지 UI 구현
2. **`client_simulator.py` 점검**: filter 2개 키가 POST body에 포함되는지 확인 (없으면 `raw_inputs`에서 누락됨)
3. **`pressure_flow_ratio` 인코딩 결정**: 모델 입력으로 쓸지/해석용만 둘지 결정 필요. 쓸 경우 [preprocessing.py:225-227](src/preprocessing.py#L225-L227)·[preprocessing.py:455-457](src/preprocessing.py#L455-L457) 두 공식 중 하나로 통일
4. **`pressure_volatility` / `flow_cv` 12h 파생**: 프론트 링버퍼 720점으로 자체 계산하도록 합의(백엔드엔 없음)
5. **재학습 대기 건 (이전 세션)**: `python src/train.py` 사용자 실행 필요

### 🔒 절대 규칙 (Absolutes)

- 필터는 **AE에 넣지 않는다** (학습 데이터에 막힘 시나리오 부재). `collinear_drop_list`의 `filter_pressure_out_kpa` 제외 유지
- `raw_inputs`는 **passthrough 채널**. 추가해도 모델 config/학습과 무관해야 함
- `pressure_flow_ratio` 공식은 당분간 프론트=해석용(`discharge/flow`), 모델=공식 미정. 재학습 전엔 둘 다 유지
- `flow_per_power` = 유량/전력, `pressure_per_power` = 압력/전력. 수식-라벨 일치 유지

### 🔄 재개 지점 (Resume Point)

1. `curl -X POST http://127.0.0.1:9977/predict ... ` 응답의 `raw_inputs`에 `filter_pressure_in_kpa` 키가 있는지 확인 (요청에 포함해서 보냈을 때)
2. 프론트팀과 `docs/FRONTEND_PAGES.md` §5 체크리스트 확인
3. `pressure_flow_ratio` 인코딩 방향 결정 필요 — 결정되면 preprocessing.py에서 두 공식 통일

---

## 2026-04-21 — inference_api에 데이터 저장 로직 이식 (inference_api2.py → inference_api.py)

### ✅ 달성 (Accomplished)

1. **`~/Downloads/inference_api2.py`의 저장 로직을 `src/inference_api.py`로 그대로 이식** (총 571 lines)
   - 추가된 import: `sqlalchemy`, `boto3`, `BytesIO`, `dotenv`, `apscheduler.BackgroundScheduler`, `preprocessing.step1_prepare_window_data`
   - `.env.local` 로딩 블록 (ENV=local 일 때 `../../../.env.local` 로드)
   - DB 설정: `DB_URL`, `DEFAULT_SENSOR_ID`(=`SF-ZONE-01-MAIN`), `engine`, `DB_STATUS`
   - S3/MinIO 설정: `S3_ENDPOINT`, `BATCH_STATUS`
   - 신규 함수: `_mask_db_url`, `_set_db_status`, `initialize_db_engine`, `save_inference_history`, `_update_batch_status`, `_build_batch_payload_from_dataframe`, `run_inference_batch`
   - `/predict` 본체를 `run_inference_pipeline(realtime_data, trigger_source)`로 리팩터 → `/predict`와 배치가 동일 파이프라인 공유
   - `@app.on_event("startup")` → APScheduler 1분 주기 배치 + DB 엔진 초기화
   - `/health` 엔드포인트 신설 (DB/배치 상태 반환)
   - 포트는 **9977 유지** (inference_api2.py의 8000 채택 안 함)

2. **기존 로직은 전부 보존**:
   - `scoring_features` 기반 MSE 계산
   - `is_startup_phase` 게이팅
   - `per_feature_thresholds` passthrough
   - `feature_details`의 `scaled_error` / `feature_thresholds` / `feature_alarm`
   - `target_reference_profiles`, `spike_info`, `raw_inputs` 블록
   - 응답 구조 변경 없음 (프론트 계약 유지)

3. **미채택 (의도적 제외)**: `get_alarm_status_with_consecutive_delay`, `MSE_HISTORY deque`, `hourly_thresholds`, `threshold_hard_ceiling`, `rca_report` flat format — 응답 구조/알람 동작을 바꾸므로 요청 범위 밖

### ⏳ 남은 과제 (Pending)

1. **의존성 설치 확인**: analyzer conda env에 `sqlalchemy`, `boto3`, `python-dotenv`, `apscheduler` 설치 필요
2. **DB 테이블 존재 확인**: PostgreSQL에 `inference_history` 테이블이 있어야 저장 성공 (없으면 `save_inference_history`는 로그만 남기고 skip)
3. **`.env.local` 파일 배치**: `/Users/jun/GitStudy/.env.local` 위치에 DB/S3 자격 필요 (DB_URL, S3_ENDPOINT, MinIO 키)
4. **서버 재기동 필요**: 기존 uvicorn 프로세스 종료 후 `python -m uvicorn inference_api:app --reload` 재실행
5. **배치 스케줄러 실 동작 검증**: MinIO 버킷에 창(window) 파일이 쌓이면 1분마다 `run_inference_batch`가 폴링해서 `run_inference_pipeline` 호출하는지 관찰

### 🔒 절대 규칙 (Absolutes)

- `run_inference_pipeline`은 `/predict`와 배치가 공유하는 단일 진입점 — 응답 페이로드 변경 시 두 호출자 모두에 동일하게 반영돼야 함
- `save_inference_history` 실패는 추론 결과 반환을 막지 않는다 (try/except로 격리) — 저장 이슈가 사용자 요청에 영향 주면 안 됨
- 포트/환경 변수는 프로젝트 기존 설정 우선 (9977, `.env.local` 경로 등)

### 🔄 재개 지점 (Resume Point)

1. 서버 재기동 후 `curl http://127.0.0.1:9977/health` → `{"db": {...}, "batch": {...}}` 반환 확인
2. `curl -X POST http://127.0.0.1:9977/predict -H "Content-Type: application/json" -d @<sample>.json` 응답 구조 불변 확인 (raw_inputs, domain_reports 등)
3. PostgreSQL `inference_history` 테이블에 해당 요청 row 저장됐는지 확인

---

## 2026-04-21 — inference_api `/predict` 응답에 `raw_inputs` 추가

### ✅ 달성 (Accomplished)

1. **inference_api.py** `response_payload`에 `raw_inputs` 블록 신설 ([src/inference_api.py:190](src/inference_api.py#L190) 근처)
   - 요청 body에서 6개 키를 passthrough: `discharge_pressure_kpa`, `suction_pressure_kpa`, `flow_rate_l_min`, `motor_power_kw`, `motor_temperature_c`, `pump_rpm`
   - 요청에 **존재하는 키만** 담음 (없는 값을 0.0으로 위장하지 않음 → 프론트가 "센서 미보고"와 "실제 0"을 구분 가능)
   - 목적: 프론트에서 `pressure_flow_ratio`, `dp_per_flow`, `flow_per_power`, `pressure_volatility` 등 파생변수를 만들 수 있게 원시값 노출

### ⏳ 남은 과제 (Pending)

1. **문서 통합 완료** (2026-04-21): `docs/INFERENCE_API_RESPONSE.md` 삭제, [docs/INFERENCE_API.md](docs/INFERENCE_API.md) 하나로 §0–§12 구조 재정리. §4-3 `raw_inputs`, §7 프론트 파생변수 가이드, §8 preprocessing.py 중복 맵, §9 파생변수 위치 구조 신설.
2. **프론트 작업**: `raw_inputs.discharge_pressure_kpa`를 링버퍼에 쌓아 `pressure_volatility`(std/IQR), `flow_volatility`(CV), `temp_slope` 계산 로직 구현. §7-2/§7-3 설계 참고.
3. **⚠️ preprocessing.py 이름 충돌 정리**: `pressure_flow_ratio`가 line 225(모델용, `differential/flow`)와 line 455(해석용, `discharge/flow`) 두 곳에서 **다른 공식으로 같은 이름** 사용 중. 이름 분리 또는 공식 통일 결정 필요.
4. **(선택) 응답에 `computed_ratios` 블록 추가**: preprocessing의 해석용 4개 비율(`pressure_flow_ratio`, `dp_per_flow`, `flow_per_power`, `pressure_per_power`)을 서버가 단일시점 계산해서 응답에 포함 — 프론트 로직 단순화. 사용자 승인 대기.
5. **재학습 대기 건 (이전 세션)**: per-feature threshold 반영 모델 재학습 — `python src/train.py` 사용자 실행 필요

### 🔒 절대 규칙 (Absolutes)

- `raw_inputs`는 **모델 입력이 아닌 passthrough 채널**. 여기에 값을 추가해도 모델 config/학습 파이프라인과 무관해야 한다.
- 키 추가 시 반드시 `if k in realtime_data` 필터 유지 — 요청에 없던 키를 0.0으로 채워넣으면 프론트가 잘못된 파생값을 계산하게 된다.
- 프론트 파생변수는 분모에 ε(1e-6) 추가해 0-division 방지.

### 🔄 재개 지점 (Resume Point)

재시작 시 `curl http://127.0.0.1:8000/predict ...` 응답 최상위에 `raw_inputs` 키가 존재하는지 확인. 예시:

```json
{
  "timestamp": "...",
  "overall_alarm_level": 0,
  "raw_inputs": {
    "discharge_pressure_kpa": 310.5,
    "flow_rate_l_min": 18.5,
    ...
  },
  "domain_reports": {...}
}
```

---

## 이전 세션 — Per-Feature Threshold Implementation

### ✅ 달성

1. **train.py**: per-feature threshold 계산 로직 추가 (열별 σ 컷, config에 `per_feature_thresholds` 저장)
2. **inference_core.py**: `build_feature_details`에 `scaled_errors`/`per_feature_thresholds` 인자 추가 → `scaled_error`/`feature_thresholds`/`feature_alarm` 출력
3. **inference_api.py**: 도메인 보고서에 `per_feature_thresholds` passthrough 및 `build_feature_details` 호출에 인자 전달

### ⏳ 남은 과제

- **재학습 필수**: `python src/train.py` — 기존 모델에는 `per_feature_thresholds` 필드가 없음 (graceful fallback 중)

### 🔒 절대 규칙

- `per_feature_thresholds` 계산은 도메인 MSE와 동일 σ 정책(2/3/6σ)
- 컨텍스트 피처(`is_startup_phase`, `pump_on` 등)는 threshold 대상 제외 (scoring_mask 준수)
- inference_core와 train.py의 feature 제외 기준 일치 유지

### 🔄 재개 지점

재학습 후 `domain_reports[system].feature_details[i]`에 `scaled_error`/`feature_thresholds`/`feature_alarm` 세 필드와 `domain_reports[system].per_feature_thresholds` 전체 매핑 확인.
