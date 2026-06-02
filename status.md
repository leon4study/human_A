# STATUS — 현재 상태 대시보드

> 한눈 보기용. 상세 이력은 [SESSION_LOG.md](SESSION_LOG.md), 방법론은 [docs/modeling/](docs/modeling/), 실험 서사는 [.claude/MODEL_CHANGELOG.md](.claude/MODEL_CHANGELOG.md).
> 최종 갱신: 2026-06-01

## 프로젝트
4도메인(motor / hydraulic / nutrient / zone_drip) AutoEncoder 예지보전. 정상 패턴 학습 + 복원오차로 이상 판정 + 6σ 3단계 알람 + SHAP RCA.

## 현재 단계
모델 성능 작업 — 재현성 확보 완료. 빈약한 도메인(zone_drip)·피처 보강 진행 중.
- 브랜치: `Jun` (origin/Jun보다 1 커밋 앞섬, 미커밋 변경 다수)
- 마지막 검증 run: `2026-06-01_153334__5de0f9e__repro-b`

## 작동 확인된 것
- **재현성 확보** — PYTHONHASHSEED re-exec 수정 후 `train.py` 2회 config 4도메인 모두 동일 확인. 이제 성능 변화를 우연과 구분 가능.
- run 보존본(`models/runs/<run_id>`) + `LATEST_RUN.txt` — 덮어쓰기 방지
- `logs/experiment_board.csv` 누적(run_id·git_sha) — 스키마 변경 안전장치 포함
- 진단 시각화 자동 저장(`src/viz.py`) — figures/ + contact sheet, train·eval 연동

## 열린 이슈 (우선순위)
1. [후속 튜닝] FAR 컨트롤 — skew-fix overall F1 0.481 달성했으나 cutoff≥1 FAR 14%(zone_drip 주도, 평가라벨이 펌프막힘 기준이라 배지탐지가 FP로 계수되는 영향 혼재). 운영점 cutoff≥2(FAR 2.4%)·percentile 레벨·zone 전용 보정은 후속. ([03](docs/modeling/03_threshold_methodology.md))
2. [관찰] SENSOR_MANDATORY 일부 누락(데이터에 없는 컬럼) — hydraulic(`hydraulic_power_kw`, `filter_delta_p_kpa`), motor(bearing 2종), nutrient(`mix_temp_c`). 필요 시 파생으로 대체 검토.
3. [트랙] 피처 자료조사 — 얇은 도메인 보강을 위해 논문 기반 파생 피처 추가([09 원장](docs/modeling/09_feature_rationale_ledger.md)에 근거와 함께 누적). 합성 47센서 조합 한도 내에서.

## 문서↔코드 불일치 점검 목록 (별도 정리 필요, 면접 대비)
- "4도메인 F1 0.95" ↔ 실제 eval overall F1 0.48 / 도메인별 0.05~0.47
- "Optuna 20 trials 최적화"(MODELING.md) ↔ active train.py는 고정 구조(Optuna는 tmp_train.py에만)

## 최근 완료
- **domain-cleanup 성공 (2026-06-02, run `..190819..domain-cleanup`)** — supply_balance_index를 zone_drip→hydraulic 이동(유량 본질). zone_drip 순수 "구역 배지 상태"화 → precision 0.51→0.66, **overall F1 0.481→0.504**, FAR 14%→11%. 도메인 분할기준 문서 [DOMAIN_DESIGN.md](docs/DOMAIN_DESIGN.md) 신설. "토양"→"배지" 용어 정정. 상세 [MODEL_CHANGELOG Phase G](.claude/MODEL_CHANGELOG.md).
- **skew-fix (2026-06-02, run `..180438..skew-fix`)** — dynamic threshold 수렴. skew-adaptive(skew>8 percentile, else sigma) + 기동마스크 버그 수정(`pump_on==1 AND minutes≤5`). overall F1 **0.481**(전 실험 최고), hydraulic 회복(P0.99/F1 0.47/FAR0.001), zone_drip 유지(F1 0.46/R0.38). 상세 [MODEL_CHANGELOG Phase F](.claude/MODEL_CHANGELOG.md). CODE_MAP([docs/CODE_MAP.md](docs/CODE_MAP.md)) 신설.
- **feature-v2 (2026-06-02)** — zone_drip 배지 복원 + 피처 1차 배치 7개. zone_drip 퇴화 회복, hydraulic 막힘 피처 robust 선정. 상세 [Phase E](.claude/MODEL_CHANGELOG.md).
- **EC/pH 처리 = 보조 지표(Path B)** — "EC/pH 학습 제외"는 코드와 모순(nutrient가 raw EC/pH 사용)이라, "직접 신호라 포함하되 nutrient 전용 도메인으로 분리, 종합 voting 제외(보조)"로 재정리. 근거: `EXCLUDE_FROM_OVERALL={"nutrient"}`가 이미 보조 취급. 관련 문서·포트폴리오 발화 9곳 수정 완료. 코드 변경 없음.

## 바로 다음 할 일
1. [09 §5] 피처 1차 배치 + zone-soil 복원을 한 실험(`PHASE=feature-v2`)으로 구현 → 학습
2. 진단 그림으로 zone_drip 빈약 해소 확인 + 타 도메인 config 회귀 없는지 점검
3. 그다음 percentile threshold 실험

## 미커밋 변경 (다음 커밋 대상)
- `src/repro.py` — CSV 스키마 안전장치 + PYTHONHASHSEED re-exec
- `src/preprocessing.py`, `src/feature_engineering.py` — zone_drip 배지 센서 복원 (services 동기화 완료)
- `logs/experiment_board.csv` 정리(legacy 분리)
- 문서: README·docs(ANALYSIS·PROJECT_BRIEF·docs/README)·포트폴리오 발화 EC/pH 재정리, `docs/modeling/09` 신설, `status.md`·`handoff.md`
