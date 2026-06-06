# STATUS — 현재 상태 대시보드

> 프로젝트 진행을 한눈에 보는 공용 대시보드. "지금 어디까지 됐고 다음이 무엇인가"는 여기만 보면 된다.
> 상세 이력 → [SESSION_LOG.md](SESSION_LOG.md) · 방법론 → [docs/modeling/](docs/modeling/) · 실험 서사 → [.claude/MODEL_CHANGELOG.md](.claude/MODEL_CHANGELOG.md) · 앞으로의 계획 → [docs/DEVELOPMENT_ROADMAP.md](docs/DEVELOPMENT_ROADMAP.md)
> 최종 갱신: 2026-06-06

## 프로젝트
4도메인(motor / hydraulic / nutrient / zone_drip) AutoEncoder 예지보전. 정상 패턴 학습 + 복원오차로 이상 판정 + 6σ 3단계 알람 + SHAP RCA.

## 브랜치·모델 현황
- 작업 브랜치: **`feat/sensor-fault-control`** (이번 라운드 작업 다수, **미푸시**).
- 원격: `feat/fault-injection-eval`(옛 `Jun` 리네임, 푸시됨), `main`.
- 모델 위치 두 곳(주의): **`PROJECT_ROOT/models`(6/2, zone_drip 19피처 복원본 — 학습·평가가 읽음)** vs `services/inference/models`(4/22 구버전 — 서빙). 재학습 후 동기화 필요. ([modeling/11 §6](docs/modeling/11_retrain_checklist.md))

## 작동 확인된 것 (검증됨)
- 재현성(PYTHONHASHSEED re-exec), run 보존본 + experiments.csv, 진단 시각화 자동저장.
- **현실적 고장 주입 프레임** — [fault_injection/](fault_injection/): 영향모델(위치별 cross-domain 전파) + faulty testset + **lead-time 평가(사전감지 6/6, 평균 29.9h)**.
- **기동 게이트 정직화** — 평가 경로도 운영처럼 기동 게이트(기동 FAR 100%→0%, lead-time 정직화).
- **센서고장 대조군** — 총 MSE로는 진짜고장/센서글리치 구분 불가, per-feature 집중도가 판별자(단일 0.88~0.92 vs 다중 0.45). ([modeling/10 §3-5](docs/modeling/10_anomaly_signature_ledger.md))
- **Phase 1 측정도구** — `coupling_validate.py` baseline 검출지도(약점 발견: zone_drip이 motor고장 오탐, motor가 suction 진동 놓침).
- 문서 가독성 재작성(어려운 docs 18개, 사실 보존 검증).

## 코드 됨 / 재학습 후 활성 (Phase 3 대기)
- **기동 regime band** (`STARTUP_MODE=gate|regime`, 기본 regime) — 통째게이트 대신 기동전용 band. 재학습으로 `threshold_startup` 생성돼야 실활성. ([modeling/03 §4-2](docs/modeling/03_threshold_methodology.md))
- **도메인 격리** (`DOMAIN_ISOLATION=1`, 기본 OFF) — 피처선택에서 타 도메인 핵심센서 제외(zone_drip의 motor_temp 누설 차단). 재학습 ON/OFF를 coupling_validate로 비교. ([modeling/10 §3-6](docs/modeling/10_anomaly_signature_ledger.md))

## 바로 다음 할 일 (우선순위)
1. **Phase 3 재학습**(사용자 직접) — `DOMAIN_ISOLATION` ON/OFF + 기동 band 생성. 끝나면 `coupling_validate`·`leadtime_eval`로 재측정(attribution). 체크리스트: [modeling/11](docs/modeling/11_retrain_checklist.md).
2. **로드맵 §4 운영지표** — 단일센서 baseline 구축 → AE 대비 **막힘률** 측정(지표 쓰되 근거 만들기). [DEVELOPMENT_ROADMAP §4](docs/DEVELOPMENT_ROADMAP.md) + [modeling/08](docs/modeling/08_domain_metrics_validation.md). 이어서 Cpk·OEE.
3. Phase 2 #2 — motor 진동 민감도(`vibration_per_load`).
4. 포트폴리오 정직화 — "F1 0.95"를 재학습 후 검증 수치로 교체.

## 열린 이슈
- **포트 불일치**: README §5(inference 9977/backend 8000/frontend 5173) ↔ docker-compose(8000/8080/frontend 없음). 사용자 확인 후 한쪽으로 정합.
- 문서↔코드: "F1 0.95"(MODELING §6, DEVELOPMENT_ROADMAP §0) ↔ 엄격 eval ~0.50. 재학습·로드맵 검증으로 정본 확정 예정.
- MODELING §3-3 SENSOR_MANDATORY zone_drip 표가 구버전(현재 feature_engineering와 불일치) — 내용 동기화 필요.

## 미푸시
`feat/sensor-fault-control`의 이번 라운드 커밋 전부. 나중에 한 번에 푸시 예정.