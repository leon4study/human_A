# CODE_MAP — 코드 지도 (함수별 역할 · 파이프라인 순서)

이 문서는 `src/`의 함수들이 **무엇을 하고, 어떤 순서로 데이터를 넘기는지**를 한눈에 보는 지도입니다. "이 함수 고치면 어디에 영향 가나"를 빠르게 파악하는 용도입니다.

> 같은 코드가 `services/inference/src/`에도 동기화되어 있습니다(서빙용 사본). 수정 시 두 트리를 함께 갱신합니다.
> 모델링 방법론은 [modeling/](modeling/), 파이프라인 개념 설명은 [MODELING.md](MODELING.md) 참조.

---

## 0. 전체 흐름 한 장

```
[데이터 생성]           [전처리]                 [피처 선택]              [학습]                    [산출물]
data_gen_jun.py    →   preprocessing.py     →   feature_selection.py  →  train.py            →   models/{도메인}.keras
data_gen_dabin.py      step1_prepare_           run_feature_selection_   train_and_save_model      {도메인}_config.json
data_gen_test.py        window_data             experiment               ├ build_autoencoder       {도메인}_scaler.pkl
(라벨 포함 평가셋)       ├ create_modeling_       ├ run_shap_ensemble       ├ (임계치 산정)           {도메인}_shap.json
                         features                │  └ get_shap_importance_ ├ inject_vip_features     models/runs/<run_id>/
                        ├ aggregate_time_         │     scalable           └ save_model_artifacts     (보존본+figures)
                         window                  └ step3_4_select_
                        └ step2_clean_drop_          features_and_finalize
                          collinear_dynamic
                                                                              ↓ (학습된 모델 사용)
                                          ┌──────────────────────────────────┴───────────────────────┐
                                   [서빙]                                                       [평가]
                            inference_api.py                                          evaluate_test_metrics.py
                            run_inference_pipeline                                     main → run_inference → compute_metrics
                            └ inference_core.* (알람·RCA·밴드)                          (anomaly_label 대비 F1/FAR)

[횡단] repro.py(재현성·추적)  viz.py(진단 그림)  logger.py  ko_labels.py(한글화)  math_utils.py  utils.py
```

---

## 1. 데이터 생성 (`data_gen_*.py`)

합성 raw 데이터(45+ 센서 × 1분 × 3개월)를 만든다. 실측 데이터에 펌프·유압이 없어 자체 생성.

| 함수 | 위치 | 역할 |
|---|---|---|
| `generate_smartfarm_final_v5` | [data_gen_jun.py:167](../src/data_gen_jun.py#L167) | 스마트팜 전체 시계열 합성의 메인 |
| `simulate_environment` / `generate_schedules` | [data_gen_jun.py:14](../src/data_gen_jun.py#L14) | 기온·습도·광량 등 환경, 관수 스케줄 생성 |
| `simulate_degradation` / `simulate_zone_data` | [data_gen_jun.py:67](../src/data_gen_jun.py#L67) | 막힘·열화 진행, 구역별 토양 데이터 |
| `smoothstep` / `baseline` | [data_gen_dabin.py:62](../src/data_gen_dabin.py#L62) | drift 램프 함수·정상 baseline (월2~3 이상 주입) |
| (스크립트) `data_gen_test.py` | [data_gen_test.py](../src/data_gen_test.py) | 다른 seed로 평가셋 생성 + composite z-score로 `anomaly_label` 부여 |

---

## 2. 전처리 (`preprocessing.py`)

raw 1분 데이터 → 도메인 파생 피처 → 윈도우 집계 → 정제. **진입점은 `step1_prepare_window_data`.**

| 순서 | 함수 | 위치 | 역할 |
|---|---|---|---|
| 진입 | `step1_prepare_window_data` | [preprocessing.py:616](../src/preprocessing.py#L616) | 아래 1·2를 묶어 호출하는 래퍼. `target_cols`로 보존할 컬럼 지정 |
| 1 | `create_modeling_features` | [preprocessing.py:40](../src/preprocessing.py#L40) | 원시 센서 → 도메인 파생(차압·유량하락률·수력효율·zone·신규 피처 등) 생성 후 `model_cols` 화이트리스트로 필터. **반환 (df_model, df_interpret)** |
| 2 | `aggregate_time_window` | [preprocessing.py:407](../src/preprocessing.py#L407) | 슬라이딩(5분)/텀블링(10분) 윈도우 집계. 센서=mean, 상태/시간=last/max |
| 3 | `step2_clean_and_drop_collinear_dynamic` | [preprocessing.py:694](../src/preprocessing.py#L694) | 결측 보간 + 상관 0.85↑ 중복 동적 제거(whitelist 보호). **권장 버전** |
| (구) | `step2_clean_and_drop_collinear` | [preprocessing.py:646](../src/preprocessing.py#L646) | 수동 drop 리스트 버전(레거시) |
| 해석용 | `extract_interpretation_features` | [preprocessing.py:492](../src/preprocessing.py#L492) | 프론트 해석/모니터링용 파생(raw 센서명 유지) |
| 학습구간 | `extract_normal_training_data` | [preprocessing.py:750](../src/preprocessing.py#L750) | 세척·이상 스파이크 제거(기동 유지)로 정상 학습 구간 추출 |
| 보조 | `filter_active_periods` | [preprocessing.py:20](../src/preprocessing.py#L20) | 밸브 on 등 활성 구간 필터 |

> 핵심 게이트: `model_cols`(create_modeling_features 내부)에 없는 컬럼은 집계 전에 잘린다. 새 피처를 살리려면 여기 등록 필수.

---

## 3. 피처 선택 (`feature_selection.py` + `feature_engineering.py`)

도메인별로 AE 입력 피처를 결정. SHAP robust 선택 + VIP/필수센서 강제 주입.

| 순서 | 함수 | 위치 | 역할 |
|---|---|---|---|
| 진입 | `run_feature_selection_experiment` | [feature_selection.py:321](../src/feature_selection.py#L321) | 전처리→SHAP→피처 확정을 묶는 도메인별 실험 래퍼. train.py가 호출 |
| 1 | `run_shap_ensemble` | [feature_selection.py:189](../src/feature_selection.py#L189) | 도메인 타깃들에 대해 SHAP 중요도 계산, robust(≥2 타깃 공통) 선정 |
| 1-1 | `get_shap_importance_scalable` | [feature_selection.py:117](../src/feature_selection.py#L117) | RF 학습 + KMeans 배경 압축 + TreeExplainer SHAP (대용량용). `random_state=42` |
| (대안) | `get_shap_importance` / `_kmeans` | [feature_selection.py:21](../src/feature_selection.py#L21) | SHAP 계산 소규모/구버전 |
| 2 | `step3_4_select_features_and_finalize` | [feature_selection.py:277](../src/feature_selection.py#L277) | robust ∪ VIP ∪ 필수센서로 최종 X_train_ae 확정 |
| 주입 | `inject_vip_features` | [feature_engineering.py:102](../src/feature_engineering.py#L102) | VIP/필수센서를 df에서 X_train_ae에 강제 주입 |
| 상수 | `SENSOR_MANDATORY` / `VIP_FEATURES` / `MODE_FEATURES` | [feature_engineering.py](../src/feature_engineering.py) | 도메인별 필수 센서, 시간·운전 맥락 VIP 목록 |

---

## 4. 학습 (`train.py` + 보조)

도메인별 AE 학습 + 임계치 산정 + 아티팩트 저장. **메인 블록이 4개 도메인을 순회.**

| 순서 | 함수/단계 | 위치 | 역할 |
|---|---|---|---|
| 진입 | `train_and_save_model` | [train.py:93](../src/train.py#L93) | 한 도메인의 스케일링→AE학습→임계치→config→저장 전 과정 |
| 1 | `build_autoencoder` | [model_builder.py:6](../src/model_builder.py#L6) | 32→16→bottleneck 대칭 AE 생성(고정 구조, Optuna 미적용) |
| 2 | `actionable_feature_mask` | [inference_core.py:49](../src/inference_core.py#L49) | MSE 점수에서 컨텍스트 피처 제외(알람 근거=설명 일치) |
| 3 | (임계치) `calculate_sigma_thresholds` | [math_utils.py:5](../src/math_utils.py#L5) | μ+2σ/3σ/6σ. train.py가 skew에 따라 percentile과 자동 선택 |
| 4 | `build_target_reference_profiles` | [inference_core.py:185](../src/inference_core.py#L185) | 프론트용 타깃-관련변수 기준선 |
| 5 | `save_model_artifacts` | [utils.py:7](../src/utils.py#L7) | .keras + scaler.pkl + config.json 저장 |
| 6 | 진단 그림 | viz.* (아래 8) | figures/에 MSE 진단·loss curve 저장 |
| 기록 | `save_experiment_to_csv` | [train.py:56](../src/train.py#L56) | 실험 리더보드 누적(repro.append_experiment_row로 위임). *logger.py:43의 동명 함수는 레거시* |

---

## 5. 재현성·추적 (`repro.py`) — 횡단

train.py가 학습 전체를 감싸는 인프라. 상세: [modeling/05](modeling/05_reproducibility_implementation.md).

| 함수 | 위치 | 역할 |
|---|---|---|
| `set_global_determinism` | [repro.py:34](../src/repro.py#L34) | 전역 시드 + PYTHONHASHSEED re-exec(비결정성 차단) |
| `get_git_sha` / `new_run_id` | [repro.py:105](../src/repro.py#L105) | 코드 출처·실험 식별자 생성 |
| `snapshot_run` | [repro.py:149](../src/repro.py#L149) | models/runs/<run_id>/에 보존본 복사 + LATEST_RUN.txt |
| `latest_run_dir` | [repro.py:208](../src/repro.py#L208) | LATEST_RUN.txt로 최신 run 폴더 조회(평가 그림 합류용) |
| `append_experiment_row` | [repro.py:231](../src/repro.py#L231) | experiments.csv 누적(스키마 변경 안전장치 포함) |

---

## 6. 추론·서빙 (`inference_api.py` + `inference_core.py`)

학습된 모델을 FastAPI로 서빙. `/predict`와 배치가 `run_inference_pipeline` 단일 진입점 공유.

| 함수 | 위치 | 역할 |
|---|---|---|
| `run_inference_pipeline` | [inference_api.py:414](../src/inference_api.py#L414) | 실시간 1건 → 4도메인 추론 → 알람·RCA·밴드 응답 조립(핵심) |
| `predict_multi_domain` / `health_check` | [inference_api.py:663](../src/inference_api.py#L663) | `/predict`·`/health` 엔드포인트 |
| `run_inference_batch` / `_build_batch_payload_from_dataframe` | [inference_api.py:258](../src/inference_api.py#L258) | APScheduler 1분 배치 추론 |
| `save_inference_history` / `initialize_db_engine` | [inference_api.py:131](../src/inference_api.py#L131) | 추론 결과 DB(PostgreSQL) 저장 |
| `startup_scheduler` / `shutdown_scheduler` | [inference_api.py:680](../src/inference_api.py#L680) | 기동 시 배치 스케줄러·DB 초기화 |

### 6-1. 추론 핵심 로직 (`inference_core.py`)
| 함수 | 위치 | 역할 |
|---|---|---|
| `get_alarm_status` | [inference_core.py:7](../src/inference_core.py#L7) | MSE vs 임계치 → 3단계 알람 레벨 |
| `calculate_rca` | [inference_core.py:59](../src/inference_core.py#L59) | 피처별 복원오차 → 원인 Top-N(컨텍스트 제외·재정규화) |
| `build_feature_details` | [inference_core.py:99](../src/inference_core.py#L99) | 피처별 실제값·기대값·밴드·feature_alarm |
| `build_sigma_reference_line` / `build_target_reference_profiles` | [inference_core.py:160](../src/inference_core.py#L160) | 프론트 시각화용 기준선·프로파일 |
| `actionable_feature_mask` / `DEFAULT_CONTEXT_FEATURES` | [inference_core.py:49](../src/inference_core.py#L49) | 점수/설명에서 제외할 컨텍스트 피처 단일 소스 |

---

## 7. 평가 (`evaluate_test_metrics.py`)

라벨 포함 평가셋으로 F1/FAR 측정.

| 순서 | 함수 | 위치 | 역할 |
|---|---|---|---|
| 진입 | `main` | [evaluate_test_metrics.py:133](../src/evaluate_test_metrics.py#L133) | 평가셋 로드→집계→추론→구간×cutoff×도메인 메트릭 + 진단 그림 |
| 1 | `run_inference` | [evaluate_test_metrics.py:52](../src/evaluate_test_metrics.py#L52) | 도메인별 배치 추론(level·score·임계치맵 반환) |
| 2 | `compute_metrics` | [evaluate_test_metrics.py:111](../src/evaluate_test_metrics.py#L111) | confusion matrix → P/R/F1/FAR |

---

## 8. 진단 시각화 (`viz.py`) — 횡단

train·evaluate가 호출. 상세: [modeling/06](modeling/06_visualization_logging.md).

| 함수 | 위치 | 역할 |
|---|---|---|
| `plot_threshold_diagnosis` | [viz.py:85](../src/viz.py#L85) | MSE 분포(skew)+시계열(임계치·기동/이상 음영·경계선) 한 장 |
| `plot_loss_curve` | [viz.py:180](../src/viz.py#L180) | train/val loss 곡선 |
| `build_contact_sheet` | [viz.py:205](../src/viz.py#L205) | run의 모든 그림을 한 장 대조표로 |
| `_shade_spans` / `_safe_skew` / `_sigma_thresholds` | [viz.py:44](../src/viz.py#L44) | 내부 헬퍼(구간 음영·skew·보조 임계치) |

---

## 9. 유틸리티

| 함수 | 위치 | 역할 |
|---|---|---|
| `calculate_sigma_thresholds` / `calculate_topdown_sigma_thresholds` | [math_utils.py:5](../src/math_utils.py#L5) | σ 임계치 산정 |
| `save_model_artifacts` | [utils.py:7](../src/utils.py#L7) | 모델 3종 저장 |
| `get_logger` | [logger.py:8](../src/logger.py#L8) | 공통 로거 |
| `ko_feature` / `ko_alarm` / `ko_domain` | [ko_labels.py:138](../src/ko_labels.py#L138) | 피처·알람·도메인 한글 라벨(프론트/리포트) |
| `run_simulation` | [client_simulator.py:31](../src/client_simulator.py#L31) | /predict로 시계열 던져 눈대중 검증 |

---

## 10. 파일 한눈 요약

| 파일 | 한 줄 |
|---|---|
| `data_gen_*.py` | 합성 raw 데이터·라벨 평가셋 생성 |
| `preprocessing.py` | 파생 피처 + 윈도우 집계 + 정제 (model_cols 게이트) |
| `feature_selection.py` | SHAP robust 선택 |
| `feature_engineering.py` | VIP·필수센서 주입 상수·헬퍼 |
| `model_builder.py` | AE 구조(고정) |
| `train.py` | 도메인별 학습·임계치·저장 메인 |
| `repro.py` | 재현성·run 스냅샷·실험 기록 |
| `viz.py` | 진단 그림 |
| `inference_api.py` | FastAPI 서빙·배치·DB |
| `inference_core.py` | 알람·RCA·밴드 계산 |
| `evaluate_test_metrics.py` | 라벨 기반 F1/FAR 평가 |
| `math_utils.py`·`utils.py`·`logger.py`·`ko_labels.py` | 임계치·저장·로깅·한글화 유틸 |
