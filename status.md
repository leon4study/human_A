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

## 정본 모델 (2026-06-06, run `..205644..retrain-fix-iso`, DOMAIN_ISOLATION=1 + 진동 fix)
- **regime band 활성**(threshold_startup 4도메인) + **motor 진동 fix**(Phase H) + **도메인 격리**(Phase I).
- 측정도구가 잡은 약점 2개 수정 후 재측정 — coupling_validate로 attribution 확인:
  - bearing_wear: zone_drip 오탐 → **motor만**(격리로 motor_temp 누설 제거).
  - suction: motor 놓침(0.08) → **hydraulic+motor**(진동 fix로 검출 회복).
- lead-time 6/6·**35.9h**·기동 FAR 0.0%·정상 FAR 1.4%. 막힘률 baseline·AE 둘 다 0%.
- **정직한 포트폴리오 발화**: "막힘률 10→2%"(미지지) 대신 **"단일센서 baseline과 동일 검출(6/6)하며 오탐 FAR 5%→1.4%(~3.6배↓), 평균 35.9h 전 사전감지."**

## 바로 다음 할 일 (우선순위)
1. **포트폴리오 정직화** — "F1 0.95"·"막힘률 10→2%"를 위 검증 발화(FAR 3.6배↓ / 35.9h 사전감지 / 진짜고장 vs 센서글리치 집중도 판별)로 교체. docs + jun_portfolio.
2. (선택) iso ON/OFF 정량 F1 비교(evaluate_test_metrics) — 현재는 coupling_validate 검출지도로만 확인.
3. hydraulic·nutrient 누락 센서(`hydraulic_power_kw`·`filter_delta_p_kpa`·`mix_temp_c`)도 같은 model_cols 점검.
4. 격리 잔여: zone_drip union의 pressure_diff·flow_diff·rpm_stability_index(타 도메인 mandatory 아니라 미포착) 검토.

## 열린 이슈
- **포트 불일치**: README §5(inference 9977/backend 8000/frontend 5173) ↔ docker-compose(8000/8080/frontend 없음). 사용자 확인 후 한쪽으로 정합.
- 문서↔코드: "F1 0.95"(MODELING §6, DEVELOPMENT_ROADMAP §0) ↔ 엄격 eval ~0.50. 재학습·로드맵 검증으로 정본 확정 예정.
- MODELING §3-3 SENSOR_MANDATORY zone_drip 표가 구버전(현재 feature_engineering와 불일치) — 내용 동기화 필요.

## 미푸시
`feat/sensor-fault-control`의 이번 라운드 커밋 전부. 나중에 한 번에 푸시 예정.