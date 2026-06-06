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

## 재학습 1회 완료 (2026-06-06, run `..144921..retrain-regime`, DOMAIN_ISOLATION=0)
- 기동 band(threshold_startup) 4도메인 생성 → regime 활성. 정본 측정: lead-time 6/6·29.9h·정상 FAR 1.0%·**기동 FAR 0.0%**(regime 정상). 막힘률 baseline·AE 둘 다 0%, AE 우위는 FAR 5%→1%.
- **버그 발견·수정(Phase H)**: motor가 `bearing_vibration_rms_mm_s`·`bearing_temperature_c`를 못 봄(model_cols 누락, zone_drip 토양센서와 동일 버그) → 진동기반 고장 깜깜이. preprocessing.model_cols에 추가함. **재학습 1회 더 필요**(motor에 진동 반영).
- coupling_validate: zone_drip이 motor 베어링 고장에 여전히 오탐(isolation OFF) → `DOMAIN_ISOLATION=1` 재학습으로 검증 예정.

## 바로 다음 할 일 (우선순위)
1. **재학습 다시**(사용자) — 위 motor 진동 fix 반영. 가능하면 `DOMAIN_ISOLATION=1`도 한 번 → zone_drip 누설·motor 진동 둘 다 검증. 이후 `coupling_validate`로 attribution.
2. **로드맵 §4 운영지표** — 막힘률 측정 도구 완성([baseline_blockage_eval.py](fault_injection/baseline_blockage_eval.py)). 발화는 "막힘률 10→2%"가 아니라 **"동일 검출에서 FAR 5%→1%"**로 정직화 필요(또는 iso-FAR·미묘막힘 추가). [modeling/08 §2](docs/modeling/08_domain_metrics_validation.md).
3. 포트폴리오 정직화 — "F1 0.95"를 검증 수치로 교체.
4. hydraulic·nutrient 누락 센서(`hydraulic_power_kw`·`filter_delta_p_kpa`·`mix_temp_c`)도 같은 점검.

## 열린 이슈
- **포트 불일치**: README §5(inference 9977/backend 8000/frontend 5173) ↔ docker-compose(8000/8080/frontend 없음). 사용자 확인 후 한쪽으로 정합.
- 문서↔코드: "F1 0.95"(MODELING §6, DEVELOPMENT_ROADMAP §0) ↔ 엄격 eval ~0.50. 재학습·로드맵 검증으로 정본 확정 예정.
- MODELING §3-3 SENSOR_MANDATORY zone_drip 표가 구버전(현재 feature_engineering와 불일치) — 내용 동기화 필요.

## 미푸시
`feat/sensor-fault-control`의 이번 라운드 커밋 전부. 나중에 한 번에 푸시 예정.