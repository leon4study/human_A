# SESSION_LOG — 인수인계 기록

> 목적: 세션이 바뀌어도 맥락 손실 없이 작업을 이어가기 위한 단일 인수인계 파일.
> 규칙: 코드·문서를 수정할 때마다 이 파일을 함께 업데이트한다. 세션 종료 직전 "재개 지점" 섹션을 반드시 최신화한다.

최종 갱신: 2026-04-21 (target_reference_profiles — df_reference 원천 버그 수정)

---

## 1. 달성한 작업 (최근 세션)

### 데이터 생성 파이프라인
- `src/data_gen_dabin.py`: 시드(`DABIN_SEED`)와 출력 경로(`DABIN_OUT_PATH`)를 환경변수로 오버라이드 가능하게 수정 → 학습용 CSV 건드리지 않고 테스트 CSV 재생성 가능.
- `src/data_gen_test.py` 신규: 시드 43으로 라벨 포함 테스트 데이터 생성. 핵심 4개 센서(discharge_pressure_kpa, flow_rate_l_min, motor_current_a, bearing_vibration_rms_mm_s)의 per-minute-of-day baseline 대비 composite z-score 평균 ≥ 2σ → `anomaly_label=1`. 청소 이벤트 구간은 강제 `label=0`.

### 추론 파이프라인 정합성 패치
- `src/client_simulator.py`: API URL 포트 8000 → **9977** (로컬 uvicorn과 Docker inference-api 8000 충돌 회피). CSV 경로를 `generated_data_from_dabin_0420.csv`로 교체.
- `src/inference_api.py`: `feature_stats` → **`feature_stds`** 키로 통일 (train.py 저장 포맷과 일치).
- `src/inference_core.py`: `build_feature_details` 시그니처를 평탄 dict (`{name: std_value}`)로 맞춤. 없을 때만 기대값 5% fallback.
- `src/preprocessing.py`: 슬라이딩/텀블링 양쪽에서 `anomaly_label`, `composite_z_score`, `cleaning_event_flag`를 rolling max로 passthrough.

### Phase A — 운전 모드 VIP 주입 (기동 스파이크 오탐 감소)
- **발견**: `preprocessing.py`가 이미 `pump_on`, `minutes_since_startup`, `is_startup_phase`, `is_off_phase`를 생성·집계·passthrough함. AE 입력까지 들어가지 못하던 것이 원인.
- `src/feature_engineering.py` **신규**: `MODE_FEATURES`·`VIP_FEATURES` 상수 + `inject_vip_features()` 헬퍼 정의. Scaler 앞단 변환만 두어 Tier 3 (LSTM-AE) 전환 시 그대로 재사용.
- `src/train.py` 수정: VIP 주입 블록을 `inject_vip_features(X_train_ae, df_interpret_result, VIP_FEATURES)` 한 줄로 교체.
- **변경 없음**: `preprocessing.py`, `client_simulator.py`, `inference_api.py`, `inference_core.py` (이미 모드 피처 passthrough + config-driven feature lookup 덕에 자동 반영됨).

### Phase A 1차 실험 실패 → MODE_FEATURES 축소 (2026-04-20)
- **1차 MODE_FEATURES**: `pump_on`, `minutes_since_startup`, `is_startup_phase`, `is_off_phase` (4개)
- **결과**: 기동 구간에서 NUTRIENT/ZONE_DRIP 도메인이 Critical로 더 심하게 오탐. RCA 99.7%가 `is_startup_phase` 단일 피처. MSE가 이전 0.003 → 0.144로 50배 폭발.
- **원인**: `is_startup_phase`는 0.7%만 `=1`인 극단적 희소 binary. AE는 다수(0)에 맞춰 학습 → 추론 시 `=1` 들어오면 복원 오차 ≈1로 폭발 → 다른 피처 오차(0.001~0.01)의 100배 지배 → MSE/RCA 독점.
- **수정**: `MODE_FEATURES`에서 `is_startup_phase`(희소 독성), `is_off_phase`(pump_on과 중복) 제거. `pump_on`(50:50 안전) + `minutes_since_startup`(연속값, 맥락의 핵심) 2개만 유지. 경고 주석 추가.
- **제거 피처는 주석 처리로 보관**: `is_startup_phase`와 `is_off_phase`를 코드 내 주석 블록으로 남기고 각각의 **재활성화 조건**(sample_weight/oversampling, 정지 모드 세분화 등)을 명시. 향후 실험에서 조건이 충족되면 한 줄 주석 해제로 복귀 가능.

### 검증
- 4개 수정 파일 `py_compile` 통과 (Phase A 포함 `src/feature_engineering.py`, `src/train.py` 추가 통과).
- uvicorn 기동 + client_simulator 실행 시 기동 스파이크 구간에서 MOTOR/HYDRAULIC 도메인이 Error/Warning으로 오탐하는 현상 관찰 (Phase A 효과는 **재학습 후** 재측정 필요).

### 테스트 CSV 기반 정량 평가 (FN/FP) — 2026-04-20
- `src/evaluate_test_metrics.py` 신규: `generated_test_data_0420.csv`(anomaly_label 포함) 로드 → 10min tumbling 집계 → 4개 도메인 AE 추론 → TRAIN/EVAL/ALL × cutoff{1,2,3} × overall/도메인별 precision/recall/F1/FAR 산출, FN/FP 타임스탬프 CSV 저장.
- **에러 1 (수정 완료)**: `❌ df_agg에 anomaly_label 없음` — `preprocessing.create_modeling_features()`의 model_cols 화이트리스트 필터([preprocessing.py:344-345](../src/preprocessing.py#L344-L345))가 aggregate 전에 anomaly_label을 drop. **수정**: `step1_prepare_window_data(..., target_cols=["anomaly_label","composite_z_score","cleaning_event_flag"])`로 호출해 [preprocessing.py:343](../src/preprocessing.py#L343) extra_cols 경로로 보존 강제.
- **에러 2 (수정 완료)**: Jupyter에서 `ModuleNotFoundError: No module named 'preprocessing'` — `NB_DIR = os.path.abspath(".")`가 커널 cwd를 반환해 `SRC_DIR = NB_DIR/src`가 `notebooks/src`로 조립(존재하지 않음). **수정**: 절대경로 `PROJECT_ROOT="/Users/jun/GitStudy/human_A"` + `SRC_DIR=PROJECT_ROOT/src`로 하드코딩. DATA_CSV도 `os.path.join(NB_DIR,"data","/abs/path")` 버그(3번째 인자가 절대경로면 앞 인자 무시) 함께 정리.
- **첫 실행 결과**: EVAL 구간 Overall(cutoff≥1) P=0.64/R=0.37/F1=0.47/FAR=10.1%. **MOTOR 단일 도메인만 쓸만함**(P=0.994/R=0.358/F1=0.527/FAR=0.001), **NUTRIENT가 FP 독점**(FP 581 중 547건=94%, precision 0.15). Critical(≥3) recall 2%로 임계값이 매우 타이트.

### A-2 적용: NUTRIENT voting 제외 (2026-04-20)
- [evaluate_test_metrics.py](../src/evaluate_test_metrics.py)에 `EXCLUDE_FROM_OVERALL = {"nutrient"}` 추가. overall 레벨 계산에서 nutrient 제외 + 비교용 `overall_alarm_level_with_nutrient` 병행 저장.
- **결과**: EVAL Overall(cutoff≥1) FAR 10.1%→4.4% (−56%), Precision 0.636→0.800 (+16%p), Recall 0.367 유지. **Recall 무변화 = nutrient가 단독으로 잡은 진짜 이상은 0건**. 즉 nutrient는 noise만 기여하던 상태.
- cutoff≥2: FAR 5.9%→1.6%, P 0.62→0.86.

### Phase B — MSE 점수·RCA 컨텍스트 피처 분리 + startup gating (2026-04-20)
- **문제**: client_simulator 리포트에서 MOTOR Caution 알람의 RCA Top1/2가 `time_cos(58.1%)`, `time_sin(41.6%)` — 액션 불가능한 시간 인코딩이 "원인"으로 올라옴. 실센서 `flow_rate_l_min`은 뒤로 밀림. 알람이 떠도 현장 조치 대상 없음.
- **근본 원인**: `inference_api.py:107`의 `mse_score`는 **전체 피처 평균**. time_sin/time_cos/minutes_since_startup 복원 오차가 크면 실센서 정상이어도 threshold 초과. RCA도 같은 feature_errors 배열을 정렬만 해서 시간 피처가 Top.
- **수정 1 — RCA 리포팅 필터**: [src/inference_core.py](../src/inference_core.py)에 `DEFAULT_CONTEXT_FEATURES` (12개: time_sin/cos, minute_of_day, pump_on, pump_start/stop_event, minutes_since_startup/shutdown, is_startup/off_phase, cleaning_event_flag, ph_instability_flag) + `actionable_feature_mask(features)` 헬퍼 추가. `calculate_rca`가 default로 이 12개 제외 후 남은 피처들끼리 % 재정규화.
- **수정 2 — MSE 점수 동일 제외**: [src/train.py](../src/train.py) `train_and_save_model`이 `actionable_feature_mask` 적용한 sq_err로 `mse_scores` 계산 → threshold도 같은 피처 셋 기반. config에 `scoring_features` 저장해 추론 시 동일 재현.
- **수정 3 — inference 일치**: [src/inference_api.py](../src/inference_api.py)가 config의 `scoring_features` (없으면 mask) 로 `mse_score` 계산. 알람 판정과 RCA가 같은 피처 셋 위에서 돌도록 정합.
- **수정 4 — startup gating**: `realtime_data["is_startup_phase"] == 1`이면 alarm_level=0, label="Normal (startup gated)"로 강제. 기동 직후 5분 정상 스파이크를 알람에서 제거.
- **수정 5 — 노트북 동기화**: [notebooks/model_middle_0420.ipynb](../notebooks/model_middle_0420.ipynb)의 `train_and_save_model`도 동일 패치. 별도 plot 셀에서 도메인별 reconstruction error 분포 + 6σ threshold 시각화 가능하도록 `return mse_scores, thresholds`로 변경 + `all_results` dict 수집 + plot 셀 추가.
- **검증**: 3개 파일 ast.parse 통과. 합성 피처 리스트로 `calculate_rca` 테스트 → time_cos/time_sin/pump_on 제외되고 flow_rate_l_min(71.4%)/suction_pressure_kpa(28.6%)만 남음.
- **주의**: `scoring_features` 키는 신규이므로 **재학습 필수**. 구버전 모델은 scoring_features 부재 시 동적 mask로 폴백하나, threshold는 옛 scale(전체 피처 평균)로 저장돼 있어 알람이 비정상적으로 안 뜰 수 있음.

### target_reference_profiles — df_reference 원천 버그 수정 (2026-04-21)
- **배경**: 직전에 모델별 target 중심 정상선(normal/caution/warning/critical) 계산 로직을 `src/inference_core.py:build_target_reference_profiles`에 추가하고 train에서 config에 저장하도록 함. Codex 코드 리뷰 결과 **치명적 버그** 발견.
- **문제**: `run_feature_selection_experiment`가 반환하던 `df_interpret`는 파생 지표(pressure_flow_ratio, dp_per_flow, zone1_resistance 등) 전용 DF이고, motor_current_a / motor_power_kw / mix_ec_ds_m 같은 **raw 센서 타겟·관련 컬럼이 들어있지 않음**(`src/preprocessing.py:extract_interpretation_features`). 결과적으로 `build_target_reference_profiles`의 `if target_name not in df.columns: continue`에 걸려 거의 모든 타겟이 skip → 저장되는 profile이 빈 `{}`였음.
- **수정 1**: [src/feature_selection.py:run_feature_selection_experiment](../src/feature_selection.py)의 반환을 `(robust_features, X_train_ae, df_interpret, shap_results, df_agg)`로 확장. `df_agg`는 raw 센서 컬럼명이 그대로 살아있는 윈도우 집계본(aggregate_time_window mean)이라 기준선 소스로 적합.
- **수정 2**: [src/train.py](../src/train.py) — 반환값 unpack 확장 + `df_reference=df_agg`로 교체. `df_interpret_result`는 그대로 `inject_vip_features` 호출에 유지(그쪽은 시간/페이즈 플래그 passthrough 필요).
- **수정 3 (서비스 사본 동기화)**: [services/inference/src/feature_selection.py](../services/inference/src/feature_selection.py) 반환 시그니처 동일 확장, [services/inference/src/train.py](../services/inference/src/train.py)도 unpack·df_reference 동일 교체.
- **수정 4 (target_dict drift 정리)**: services 사본의 motor target_dict에 `bearing_vibration_rms_mm_s`가 빠져 있어 src와 불일치 → 추가. (services에는 zone_drip 도메인 자체가 없음, 이는 배포 범위 차이로 일단 유지.)
- **검증**: 5개 파일 `python3 -m py_compile` 통과.
- **영향 및 재개 지점**: 이 수정은 **재학습 후** 새 config에 들어가는 `target_reference_profiles`를 실제 값으로 채우기 위한 선행 패치. 재학습 전 `cp -r models models_backup_$(date +%Y%m%d_%H%M)` 필수(절대 규칙).

### A-3 시도 실패 → 롤백 (2026-04-20)
- **가설**: `train.py`의 nutrient target_dict가 파생 target(pid_error_ec, salt_accumulation_delta)으로 설정돼, 그 leak_cols에 mix_ec/drain_ec가 들어가 SHAP 후보에서 원천 배제됨. raw 센서(mix_ec_ds_m, mix_ph, drain_ec_ds_m) target으로 재편하면 영양액 피처가 feature_selection에 들어올 것.
- **시도**: target_dict를 raw 센서로 교체 + 파생 컬럼 leak_cols에 전수 명시.
- **결과**: **전체 도메인 악화**. EVAL Overall(no_nutrient) F1 0.503→0.136, motor F1 0.527→0.106 (변경 안 한 도메인도 붕괴), zone_drip 완전 붕괴. 학습 구간 FP 450건(이전 0).
- **롤백**: target_dict 원복 후 재학습 → **완전 복구 실패**. F1 0.377까지만 회복, motor 여전히 P 0.994→0.601. 피처 수조차 첫 A-2와 다르게 뽑힘(motor robust 3→2, nutrient 4→3).
- **발견**: `random_state=42`가 걸려 있음에도 `train.py` **재학습이 비결정적**. 원인 미규명.
- **자산 손실**: 첫 A-2 모델 아티팩트(`models/*.keras|pkl|json`)는 `/models` gitignore로 git 추적 대상이 아니라서 재학습이 덮어씀 → 영구 소실. Time Machine/Trash에도 없음.
- **유지된 개선**: `evaluate_test_metrics.py`의 extra_cols 패치, nutrient 제외 voting, with/without 비교 기능은 모두 유용하므로 보존.

---

## 2. 남은 과제 (우선순위)

### P0 — 기동 스파이크 오탐 감소 (Phase A 3차까지 완료, 재학습 검증 대기)
- **Phase A 1차**: ❌ 실패 — 희소 binary `is_startup_phase` 독성으로 MSE 50배 폭발.
- **Phase A 2차**: 🟡 부분 성공 — 2개 도메인(NUTRIENT/ZONE_DRIP)은 Normal 복귀, MOTOR만 여전히 `flow_drop_rate` 99.9% RCA로 Critical.
- **Phase A 3차**: ✅ 코드 수정 완료 — `preprocessing.py`의 `flow_drop_rate` 공식에 pump_on + baseline + clip 3단 게이트 추가. pump_on 블록을 공식 앞으로 이동. 분포 검증 완료 (min -7.3e7 → 0.0, 기동 구간 전부 0).
  - 다음 액션: **재학습** (`python src/train.py`) 후 `client_simulator.py` 실행해 MOTOR 오탐 해결 여부 확인.
- **Phase B (Tier 1 확장, 보류)**: Phase A로 부족할 때만 진행 — `feature_engineering.py`에 `fit_diurnal_baseline` / `transform_diurnal_residual` 추가 → baseline pkl을 artifact로 저장/로드.
- **Tier 3 (LSTM-AE, 보류)**: Phase A/B로도 부족할 때만 `model_builder.py`에 `build_lstm_autoencoder` 추가하고 sequence reshape 삽입. `feature_engineering.py`의 VIP 로직은 그대로 재사용.

### P1 — 검증 루틴
- API 재기동 후 `feature_details.bands`가 실제 std 기반으로 그려지는지 확인 (5% fallback이 아닌 실 std 반영).
- `data_gen_test.py` 실행 → 라벨 분포 확인 (anomaly 비율이 합리적 범위인지).
- End-to-end: `train.py` → uvicorn 9977 → `client_simulator.py` → 정상 전처리 흐름 재확인.

### P2 — 운영/배포 일관성
- `services/inference/src/` (Docker 배포 사본)은 **의도적 stale**. 본 리포 수정이 배포에 반영되려면 Docker 이미지 재빌드 필요. 동기화 시점은 별도 결정.

---

## 3. AI가 배운 절대 규칙

- **SESSION_LOG.md 인수인계**: 수정 시마다 이 파일을 갱신하고, 세션 종료 전 "재개 지점"을 최신화한다. (`.claude/claude_context.txt` 규칙)
- **포트 정책**: 로컬 개발 uvicorn은 **9977**, Docker `inference-api`는 8000을 사용한다. 두 포트는 절대 섞지 않는다.
- **의도적 orphan 보존**: 사용자가 이름을 바꿔 빼놓은 로직(예: `extract_normal_training_data`)은 자동 주입하지 않는다. "A에서 A'로 만들며 A를 남겨둔" 케이스가 있으므로.
- **Docker 배포 사본 비동기**: `services/inference/src/`는 본 리포 `src/`와 자동 동기화하지 않는다.
- **feature_stds 포맷**: `{feature_name: std_value}` 평탄 dict. train.py가 저장, inference_api/core가 그대로 로드.
- **희소 binary 금지**: `MODE_FEATURES` 같은 AE 입력 VIP 리스트에는 분포가 치우친 binary(전체의 5% 이하 `=1`)를 절대 넣지 않는다. AE가 다수 클래스에만 맞춰 학습해 추론 시 소수 클래스가 MSE를 독점. 맥락은 **연속값 피처**로 전달한다.
- **파생 공식 분모 발산 금지**: `(A - B) / (B + eps)` 형태의 파생 공식은 B가 0에 근접하는 구간이 있으면 반드시 게이트를 걸 것. `eps`는 0-division 방지용이지 수치 안정화 도구가 아님. 게이트 없이 두면 학습 데이터에 수천만 단위 극단값이 섞여 Scaler를 왜곡하고 AE를 붕괴시킴. (2026-04-20 `flow_drop_rate` 버그 사례.)
- **재학습 전 `models/` 백업 필수**: `/models`는 `.gitignore`로 git 추적 대상이 아니며 `train.py`가 재학습 시 덮어씀. 현재 `train.py`는 `random_state=42`가 있음에도 **비결정적**이어서 같은 코드/데이터로 돌려도 같은 모델이 안 나옴. 실험 전 `cp -r models/ models_backup_$(date +%Y%m%d_%H%M)/` 식으로 스냅샷 후 진행. (2026-04-20 A-3 실험 시 첫 A-2 모델 영구 소실 사례.)
- **한글 기본**: 로그·문서·커밋 메시지는 한국어로 작성.
- **PDF/PPT 추출**: `memory/reference_doc_extraction.md`의 지침을 따른다.

---

## 4. 다음 세션 재개 지점

**이어갈 작업**: `models/` 백업 후 `python src/train.py` 재학습 → 생성된 `models/*_config.json`에 `target_reference_profiles`가 실제 값(target_lines, related_feature_lines)으로 채워졌는지 확인 → uvicorn 9977 + client_simulator로 `/predict` 응답의 `domain_reports.<sys>.target_reference_profiles`에 값이 내려오는지 검증. 이후 Phase B 재학습 검증(RCA 실센서화 + startup gating) 및 train.py 비결정성 감사로 이어감.

**현재 운영 상태**:
- `train.py`: 원래 target_dict (A-2 상태 코드).
- `evaluate_test_metrics.py`: extra_cols 패치 + `EXCLUDE_FROM_OVERALL={"nutrient"}` + with/without 비교. 유지.
- `models/`: 롤백 재학습 결과. EVAL F1(no_nutrient)=0.377. 첫 A-2 수치(F1=0.503)는 재현 불가.

**첫 액션**:
1. **재학습 전 백업 규칙 도입** — `scripts/backup_models.sh` 또는 `cp -r models/ models_backup_$(date +%Y%m%d_%H%M)/`를 train.py 상단 또는 운영 절차에 넣기.
2. **비결정성 원인 감사** — `feature_selection.py`의 `n_jobs=-1`(RF 병렬), `shap.TreeExplainer`, `KMeans` 랜덤성, numpy/tf global seed 미설정 여부 확인. 재현 가능한 pipeline 만들기.
3. **NUTRIENT 대안 3가지 중 선택**:
   - (a) `top_ratio`를 0.25→0.4로 상향 (robust voting 완화)
   - (b) `df_interpret`에 mix_ec/mix_ph/drain_ec/zone_substrate_ec 패스스루 추가 + `NUTRIENT_VIP` 정의 + nutrient 학습 루프에서 강제 주입
   - (c) robust voting 대신 도메인별 명시 피처 리스트로 전환
4. **mean+max 집계**(별도 실험) — recall 37%→50%+ 목표. preprocessing.py의 sensor_cols 집계에 max 파생 추가.

**A-3 실패 기록** (참고용):
- raw 센서 target 재편안 실패. 이유: 3개 target 간 상호 leak로 공통 프록시(time/motor/pump)만 robust 통과, 영양액 raw 피처는 각자 다른 target에서만 중요해 voting 탈락. 더 심각한 문제는 **변경 안 한 motor/zone_drip까지 전부 악화** = 재학습 비결정성 유출. 첫 A-2 모델 영구 소실.

**현재 브랜치**: `Jun` (main에서 분기)
**미커밋 변경**: `docker-compose.yaml`, `services/frontend/package-lock.json`, `src/inference_api.py`, `src/train.py`, `src/preprocessing.py`, `src/inference_core.py`, `src/client_simulator.py`, `src/feature_selection.py`, `services/inference/src/feature_selection.py`, `services/inference/src/train.py`, `services/inference/src/inference_api.py`, `docs/INFERENCE_API.md`, `ppt/*.pptx` / 삭제: `src/data_gen_ver2.py` / 신규: `src/data_gen_dabin.py`, `src/data_gen_jun.py`, `src/data_gen_test.py`, `src/feature_engineering.py`, `.claude/SESSION_LOG.md`

**관련 파일 바로가기** (`.claude/SESSION_LOG.md` 기준 상대 경로):
- [../src/train.py](../src/train.py)
- [../src/feature_engineering.py](../src/feature_engineering.py)
- [../src/preprocessing.py](../src/preprocessing.py)
- [../src/inference_api.py](../src/inference_api.py)
- [../src/inference_core.py](../src/inference_core.py)
- [../src/client_simulator.py](../src/client_simulator.py)
- [../src/data_gen_test.py](../src/data_gen_test.py)
- [../src/math_utils.py](../src/math_utils.py)
