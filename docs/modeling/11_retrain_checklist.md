# 11 — 재학습 전 설정 체크리스트 (Retrain Setup Checklist)

`src/train.py`로 4도메인 AutoEncoder를 재학습하기 직전에 한 번 훑는 운영 체크리스트.
모델링 게이트(가설·평가 정의)는 [04](04_modeling_kickoff_checklist.md), 상세 절차는
[07 training runbook](07_training_runbook.md), 재현성은 [01](01_experiment_protocol.md),
임계값 방법론은 [03](03_threshold_methodology.md)을 본다.

이번 재학습이 활성화하는 것: 현재 `src/` 피처 반영 + zone_drip 복원 유지 + **기동 regime band 생성**
(`threshold_startup`. 생성되어야 추론/평가의 `STARTUP_MODE=regime`이 실제로 동작한다. 03 §4-2).

---

## 0. 사전 점검 (pre-flight)
- [ ] 현재 작업 커밋/스태시 완료. 작업 브랜치 확인(예: `feat/sensor-fault-control`).
- [ ] 학습은 **기준이 되는(canonical) 코드 트리**인 `src/train.py`로 실행한다(모델 저장 위치가 `services/`와 다름 — §4 참고).
- [ ] Python 환경: `services/inference/requirements.txt` 설치된 venv 활성.
- [ ] 학습 산출물(모델·CSV)은 git 추적 대상이 아니다(.gitignore). 재학습이 기존 `models/`를 덮어쓴다.

## 1. 재현성 (자동 — 확인만)
- [ ] `set_global_determinism(seed=42)`가 train.py 최상단에서 `PYTHONHASHSEED`를 박고 `os.execv`로
      프로세스를 재실행한다. **수동으로 환경변수 설정 불필요.** 첫 실행에서 "재실행" 로그가 한 번 뜨는 것이 정상.
- [ ] 엄밀 검증이 필요하면 2회 실행 후 도메인별 config가 동일한지 비교(01 재현성).

## 2. 입력 데이터
- [ ] train.py가 읽는 경로는 **절대경로 하드코딩**이다(line ~435:
      `data/generated_data_from_dabin_0420.csv`). 다른 머신/경로면 이 줄을 수정한다.
- [ ] 이 CSV가 **정상 학습 데이터**(월1, 고장 미주입)인지 확인. 고장 주입본(`faulty_testset_v1.csv`)으로
      학습하면 안 된다(AE는 정상만 학습).

## 3. 임계값/기동 환경변수 (선택 — 기본값으로도 동작)

| 변수 | 기본값 | 의미 |
|---|---|---|
| `THRESHOLD_METHOD` | `auto` | skew로 sigma/percentile 자동분기. `sigma`/`percentile`로 강제 가능 |
| `SKEW_CUTOFF` | `8.0` | auto 분기 경계 |
| `PCT_CAUTION`/`WARNING`/`CRITICAL` | `95`/`99`/`99.9` | percentile 방법일 때 레벨 |
| `STARTUP_PCT_CAUTION`/`WARNING`/`CRITICAL` | `99`/`99.5`/`99.9` | **기동 band 백분위(신규)** |
| `PHASE` | (없음) | run_id 라벨(실험 구분용) |

- [ ] 특별한 실험이 아니면 **전부 기본값**으로 둔다.
- [ ] 주의: `STARTUP_MODE`(gate|regime)는 **학습이 아니라 추론/평가 시** 변수다. 학습은 항상 기동
      band를 산출한다(정상 기동 표본 ≥ 20일 때. 미만이면 생략 → 추론에서 gate 폴백).

## 4. 실행 + 기대 산출물
- [ ] 명령: `cd <repo> && python src/train.py`
- [ ] 4도메인(motor → hydraulic → nutrient → zone_drip) 순차 학습.
- [ ] 저장 위치: **`PROJECT_ROOT/models/`**(라이브) + `models/runs/<run_id>/`(불변 스냅샷) +
      `figures/` + `logs/experiment_board.csv`.
- [ ] 로그에서 도메인별 `기동 band(n=...): ...` 또는 `기동 표본 부족(...)` 메시지 확인.

## 5. 학습 후 검증 (필수)
- [ ] `threshold_startup`이 config에 생겼는지 확인(4도메인). 없으면 기동 표본 < 20.
      `python -c "import json; print(json.load(open('models/hydraulic_config.json')).get('threshold_startup'))"`
- [ ] zone_drip features에 substrate(수분/EC) 포함 유지 확인(복원 회귀 방지).
- [ ] **서빙 동기화(중요)**: `PROJECT_ROOT/models/` → `services/inference/models/` 복사.
      docker/추론 API가 읽는 곳이며 현재 2026-04-22 구버전이다. 안 하면 배포 API는 옛 모델을 계속 쓴다.
      `cp models/*.keras models/*_config.json models/*_scaler.pkl models/*_shap.json services/inference/models/`
- [ ] 평가 재실행: `fault_injection/leadtime_eval.py`(PROJECT_ROOT/models를 읽음) — lead-time 갱신.
- [ ] **디스크 정리(매 재학습)**: 새 run이 검증되면 superseded(낡은) run 스냅샷을 삭제해 용량을 아낀다.
      지표 이력은 `logs/experiment_board.csv` + MODEL_CHANGELOG에 이미 보존되므로, 모델 바이너리만
      지워도 수치는 안 사라진다. 보통 **최신 run 1개만 유지**(필요 시 known-best 1개 추가).
      `ls models/runs/` 로 확인 후 옛 폴더 `rm -rf models/runs/<old_run_id>` (서빙 라이브 `models/`는 건드리지 말 것).
- [ ] regime 실검증: 동기화 후 `STARTUP_MODE=regime python fault_injection/startup_strategy_eval.py`,
      `sensor_fault_eval.py` 재실행(두 스크립트는 현재 `services/inference/models`를 읽음 — §6 참고).
- [ ] 재현성: 2회 실행 시 config 동일.

## 6. 알려진 함정 (2026-06-04 발견)
- **모델 두 곳이 갈림.** train·`src/evaluate_test_metrics`·`leadtime_eval`은 `PROJECT_ROOT/models`(최신,
  zone_drip 복원본)를 쓰고, **서빙·`sensor_fault_eval`·`startup_strategy_eval`은
  `services/inference/models`(2026-04-22 구버전, zone_drip 6피처 퇴화)**를 읽는다. 재학습 후 반드시
  동기화(§5). 권장: 실험 스크립트 `MODELS_DIR`을 `PROJECT_ROOT/models`로 통일해 평가 일관성 확보.
- **데이터 경로 하드코딩**(절대경로) — 환경 바뀌면 깨진다.
- **기동 표본이 적다**(월1 ~30개) → band 추정이 거칠다. 더 긴 정상 데이터로 학습 시 안정화.
- **10분 mean 집계가 기동 피크를 희석**할 수 있다 → 기동 윈도우에 max/p95 피처 보강을 검토(03 §4-2).
