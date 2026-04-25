# 🧠 MODELING — 모델링 파이프라인

이 문서는 **전처리 → 피처 선택 → AE 학습 → 임계치 → 평가** 의 모델링 파이프라인을 코드 기준으로 정리합니다.
- 데이터 분석 인사이트: [ANALYSIS.md](ANALYSIS.md)
- 도메인 배경지식 (양액·CNL 핀·기동 spike 메커니즘): [DOMAIN_KNOWLEDGE.md](DOMAIN_KNOWLEDGE.md)
- 실패 학습·진행 중 문제·다음 단계: [PROJECT_BRIEF.md](PROJECT_BRIEF.md)
- 컬럼 정의: [COLUMNS_REFERENCE.md](COLUMNS_REFERENCE.md)
- 추론 API 스펙: [INFERENCE_API.md](INFERENCE_API.md)

---

## 0. 모델 선정 근거 — 왜 AutoEncoder인가

| 후보 | 장단점 | 채택 여부 |
|---|---|---|
| 지도학습 분류 | 고장 라벨 거의 없음 + 미래 고장 유형 열거 불가 | ❌ |
| One-Class SVM, Isolation Forest, GMM | 비지도 가능하지만 40+ 차원 비선형 데이터에 한계 | ❌ |
| **AutoEncoder** | 정상 manifold만 학습 + 복원 오차로 이상 판정 + 피처별 분해 가능(RCA 자연스러움) | ✅ |

**핵심 아이디어**: Encoder가 입력 X를 저차원 latent code h로 압축하고, Decoder가 X′로 복원. 학습 목표는 X ≈ X′. **병목(bottleneck)이 정상 manifold만 남도록 강제**하므로, 이상 입력은 manifold에서 벗어나 복원 오차가 크게 튐.

## 1. 파이프라인 전체 구조

```
data_gen (45 raw cols, 1min)
   │
   ▼  [STEP 1-2] 도메인 파생 + 슬라이딩 윈도우 집계
preprocessing.py
   │
   ▼  [STEP 3] 결측 보간 + 다중공선성(0.85) 제거 + Whitelist 보호
df_clean
   │
   ▼  [STEP 4] 정상 학습 구간 추출 (cleaning/anomaly 제거, startup 유지)
   │
   ├── target별 SHAP 상위 25% → robust(≥2 타깃 공통) [feature_selection.py]
   │
   ├── ∪ VIP_FEATURES (time + mode) [feature_engineering.py]
   ├── ∪ SENSOR_MANDATORY[domain]   [feature_engineering.py]
   │
   ▼  [STEP 5] MinMax [0,1] 정규화
X_train_ae  (도메인별)
   │
   ▼  AutoEncoder 학습 + 6-Sigma 임계치 [train.py]
models/{domain}.h5 + {domain}_config.json + {domain}_scaler.pkl
```

→ **이 파이프라인을 4개 도메인(motor, hydraulic, nutrient, zone_drip)에 대해 독립 반복** ([train.py:273](../services/inference/src/train.py#L273) for 루프).

## 2. 전처리 5단계 — preprocessing.py

> 전체 코드: [services/inference/src/preprocessing.py](../services/inference/src/preprocessing.py)

### STEP 1 — 도메인 기반 파생 피처 생성 + 운전 상태 보정
원시 센서값을 그대로 넣지 않고, 설비 물리·작물 환경을 반영한 파생 피처로 변환합니다.

**핵심 파생 피처** ([preprocessing.py:40-349](../services/inference/src/preprocessing.py#L40-L349) `create_modeling_features`):
- 압력차 `pressure_diff = discharge - suction`
- 유량 하락률 `flow_drop_rate` — **3단 게이트**(`pump_on`, `min baseline`, `[0,1] clipping`)로 분모 발산 차단. *과거 학습 데이터 0.5% 샘플이 수천만 단위 극단값으로 튀어 MinMaxScaler 왜곡 → AE MSE 폭발한 사례에서 도출* ([PROJECT_BRIEF.md §4-3](PROJECT_BRIEF.md))
- 수력 동력 `hydraulic_power_kw`
- RPM 안정성 `rpm_stability_index = |rpm - rpm_mean_10| / (rpm_mean_10 + ε)`
- 모터 효율 `wire_to_water_efficiency = hydraulic_power / motor_power`
- VPD `calculated_vpd_kpa` (Tetens 공식)
- 구역 저항 `zone1_resistance = zone1_pressure / zone1_flow`

**운전 모드 컨텍스트** — 기동 전환 구간을 명시적으로 추적:
- `pump_on` (펌프 ON/OFF)
- `minutes_since_startup`
- `is_startup_phase` (기동 직후 5분)
- `pump_start_event`

→ 이게 있어야 AE가 "정상 기동 overshoot"를 이상으로 오판하지 않습니다.

### STEP 2 — 시계열 윈도우 집계 + Context 보존
1분 단위 시계열을 슬라이딩 윈도우로 집계해 순간 노이즈를 줄입니다.

| 항목 | 값 |
|---|---|
| 윈도우 크기 | **5분** (sliding) 또는 10분 (tumbling) |
| 스텝 | **1분** |
| 센서값 집계 | `mean` |
| **상태/플래그/시간** | **`last` 또는 `max`** (절대 평균 X) |

> 코드: [preprocessing.py:358-432](../services/inference/src/preprocessing.py#L358-L432) `aggregate_time_window`

**평균이 아닌 last/max를 쓰는 이유**:
- 시간 (`time_sin/time_cos`)·기동 상태(`pump_on`)·이벤트 플래그(`cleaning_event_flag`)를 평균내면 "기동 전환" 같은 결정적 컨텍스트가 사라짐
- 평가용 라벨(`anomaly_label`)도 윈도우 내 `max`로 유지

### STEP 3 — 결측 보간 + 다중공선성 제거
- 결측: **선형 보간 + backward fill** (시계열 특성 고려)
- 무한대 값: 0 또는 NaN 처리 후 보간
- **상관계수 0.85 이상** 중복 변수 동적 제거 ([preprocessing.py:645](../services/inference/src/preprocessing.py#L645) `step2_clean_and_drop_collinear_dynamic`)

**Whitelist 보호** — 다음 핵심 피처는 상관성과 무관하게 보존:
```python
calculated_vpd_kpa, mix_ec_ds_m, mix_ph, air_temp_c
discharge_pressure_kpa, flow_rate_l_min, motor_power_kw, pump_rpm,
motor_temperature_c, time_sin, time_cos
pump_on, pump_start_event, is_startup_phase, minutes_since_startup
pressure_diff, rpm_slope, rpm_acc
zone1_substrate_moisture_pct, daily_light_integral_mol_m2_d
```

### STEP 4 — 정상 학습 구간만 선별 ⭐
**가장 차별화되는 단계.** AE가 정상 패턴만 안정적으로 복원하도록 학습 데이터를 필터링.

| 신호 | 처리 | 이유 |
|---|---|---|
| `cleaning_event_flag == 1` | **제거** | 양액 세척·산처리 이벤트는 비정상 운영 |
| `is_anomaly_spike == 1` | **제거** | 외부 비정상 스파이크 |
| `is_startup_spike == 1` | **유지** | 정상 과도 응답 (매일 아침 기동) |

> 코드: [preprocessing.py:443-561](../services/inference/src/preprocessing.py#L443-L561) `extract_interpretation_features`

**IQR 꼬리 절단을 일부러 사용하지 않은 이유** — 잘라내면 정상 기동 overshoot까지 이상으로 학습돼 매일 아침 알람이 폭주.

### STEP 5 — 정규화 (MinMax [0,1])
유량·압력·전류·온도 등 단위가 다른 센서·파생 피처를 **MinMax Scaling으로 [0, 1] 구간 정렬**.

```python
scaler = MinMaxScaler()
X_scaled = scaler.fit_transform(X_train_ae)
```

→ 재구성 손실이 특정 고단위 피처(예: kPa)에 과도하게 집중되는 현상 방지.

## 3. 피처 선택 — feature_selection.py

도메인별로 어떤 피처를 AE 입력에 넣을지 결정.

```
df_agg (원본+파생)
   │
   ▼  [step2 corr > 0.85 drop] (Whitelist 보호)
df_clean (예: ~24col)
   │
   ▼  타깃별 SHAP 상위 25% = 6개씩 추출
   ▼  robust = (≥2 타깃 공통) — 더 적음
robust ∪ VIP_FEATURES ∪ SENSOR_MANDATORY[domain]
   │
   ▼
X_train_ae  ← AE 입력
```

### 3-1. SHAP 기반 robust 선택
도메인별로 정의된 **타깃 변수**(예: motor의 `motor_current_a`, `rpm_stability_index`)에 대해 LightGBM으로 SHAP 값 계산 → 타깃별 상위 25% 피처 → **2개 이상 타깃에 공통으로 잡힌 피처만 robust로 채택**.

> 도메인별 타깃 정의: [train.py:242-270](../services/inference/src/train.py#L242-L270) `subsystem_targets`
> SHAP 계산: [feature_selection.py:117-185](../services/inference/src/feature_selection.py#L117-L185) `get_shap_importance_scalable`

### 3-2. VIP_FEATURES — 강제 주입 (시간/상태 컨텍스트)
SHAP 선택에서 빠져도 다음 피처는 항상 입력에 주입:

```python
VIP_FEATURES = ["time_sin", "time_cos"] + MODE_FEATURES
# MODE_FEATURES = ["pump_on", "pump_start_event", "minutes_since_startup", ...]
```

> [feature_engineering.py:39](../services/inference/src/feature_engineering.py#L39)

**이유**: AE가 "기동 스파이크는 정상 루틴"임을 학습하려면 시간·상태 정보가 필수. 매일 아침 CNL 핀 Cracking Pressure 돌파로 발생하는 압력 spike의 물리적 메커니즘은 [DOMAIN_KNOWLEDGE.md §3](DOMAIN_KNOWLEDGE.md) 참조.

**⚠️ 희소 binary 금지 규칙** — `is_startup_phase`(0.7%만 `=1`)를 AE 입력에 직접 넣으면 **MSE 50배 폭발**. 운전 맥락은 *연속값* `minutes_since_startup`로 전달. 재활성화 조건은 [feature_engineering.py:24-36](../services/inference/src/feature_engineering.py#L24-L36) 주석 참조. 실패 사례: [PROJECT_BRIEF.md §4-1](PROJECT_BRIEF.md).

### 3-3. SENSOR_MANDATORY — 도메인별 필수 센서
SHAP robust selection이 0~소수만 뽑아도 실제 센서가 AE 입력에 포함되도록 보장:

| 도메인 | 필수 센서 |
|---|---|
| `motor` | `motor_power_kw`, `motor_temperature_c`, `bearing_vibration_rms_mm_s`, `bearing_temperature_c`, `wire_to_water_efficiency`, `pump_rpm`, `rpm_slope`, `temp_slope_c_per_s` |
| `hydraulic` | `flow_rate_l_min`, `discharge_pressure_kpa`, `suction_pressure_kpa`, `flow_drop_rate`, `pressure_flow_ratio`, `hydraulic_power_kw`, `filter_delta_p_kpa`, `pressure_trend_10`, `flow_trend_10` |
| `nutrient` | `mix_ph`, `mix_ec_ds_m`, `mix_target_ec_ds_m`, `drain_ec_ds_m`, `pid_error_ph`, `mix_temp_c`, `ph_trend_30` |
| `zone_drip` | `zone1_flow_l_min`, `zone1_pressure_kpa`, `zone1_substrate_moisture_pct`, `zone1_substrate_ec_ds_m`, `supply_balance_index` |

> [feature_engineering.py:50-88](../services/inference/src/feature_engineering.py#L50-L88) `SENSOR_MANDATORY`

**규칙**:
- 각 도메인 *타깃 컬럼*은 leakage 방지로 입력에서 제외
- zone 2·3은 preprocessing에서 drop → zone1만 사용
- 파생이 원본보다 신호 대 잡음비 좋을 때는 파생 우선 (예: `rpm_slope` > `pump_rpm`)

## 4. AE 아키텍처 — model_builder.py

> 전체 코드: [services/inference/src/model_builder.py](../services/inference/src/model_builder.py)

```
Input(input_dim)
   │
Dense(32, relu) ─ Dropout(0.1)
   │
Dense(16, relu)
   │
Dense(bottleneck, relu)            # bottleneck = max(4, input_dim // 4)
   │
Dense(16, relu)
   │
Dense(32, relu)
   │
Dense(input_dim, sigmoid)          # 출력
```

**설계 의도**:
- **8로 바로 짓누르지 않고 32 → 16 → bottleneck으로 서서히 압축** — 시간/상태/센서 간 복잡한 비선형 관계 학습 용량 확보
- Bottleneck `max(4, input_dim/4)` — 최소 4 보장으로 과도한 정보 손실 방지
- Dropout 0.1 — 과적합 방지 (얕은 단계에만)
- 출력 sigmoid — 입력이 MinMax [0,1]이므로 매칭

| 항목 | 값 |
|---|---|
| Optimizer | Adam |
| Loss | MSE |
| Epochs | 100 (max) |
| Batch size | 64 |
| Validation split | 20% |
| EarlyStopping | `patience=10`, `restore_best_weights=True` (val_loss 기준) |
| 하이퍼파라미터 튜닝 | **Optuna 20 trials**로 8개 하이퍼파라미터 최적화 |

> 학습 설정: [train.py:81-94](../services/inference/src/train.py#L81-L94)

**학습 결과** — 약 **20 epoch 이내에 Loss 안정 수렴**, Train/Validation Loss 곡선이 거의 겹쳐 과적합 없이 일반화 확보. EarlyStopping이 자동으로 학습 종료, 최적 가중치만 저장.

## 5. 임계치 — 6시그마 3단계 알람

학습 후 정상 데이터의 MSE 분포에서 σ 기반 임계치를 산출. **상위 몇 σ로 통일**해서 도메인별 공정한 비교가 가능하게 합니다.

### 5-1. 도메인별 임계치 (3단계)

| 단계 | 기준 | 의미 |
|---|---|---|
| 🟡 Caution (주의) | μ + **2σ** | 운영자 모니터링 강화 |
| 🟠 Warning (경고) | μ + **3σ** | 정비 일정 사전 조율 |
| 🔴 Critical (치명) | μ + **6σ** | 즉시 점검·출동 |

```python
thresholds = calculate_sigma_thresholds(mse_scores, sigma_levels=(2, 3, 6))
```

> [train.py:134](../services/inference/src/train.py#L134), [math_utils.py](../services/inference/src/math_utils.py)

### 5-2. Scoring features — 컨텍스트 분리 ⭐
MSE 계산 시 **시간·상태 컨텍스트 피처는 제외**하고 실센서 피처만으로 점수를 냅니다.

```python
scoring_mask = actionable_feature_mask(feature_cols)
mse_scores = np.mean(sq_err[:, scoring_mask], axis=1)
```

→ **이유**: RCA 설명 기준과 알람 판정 기준을 일치시키기 위함. 시간 피처가 "이상의 원인"으로 잡히면 사용자가 해석 불가.

> [train.py:101-119](../services/inference/src/train.py#L101-L119), [inference_core.DEFAULT_CONTEXT_FEATURES](../services/inference/src/inference_core.py)

### 5-3. 피처별 threshold (per-feature)
도메인 전체 MSE와 별도로, **각 피처마다 독립 임계치**도 계산해 RCA에서 "어느 센서가 얼마나 튀었는지" 정량 판단:

```python
for fname in feature_cols:
    col_err = sq_err[:, j]
    per_feature_thresholds[fname] = {
        "mean": μ, "std": σ,
        "caution":  μ + 2σ,
        "warning":  μ + 3σ,
        "critical": μ + 6σ,
    }
```

### 5-4. 알람 격상 룰
**"N분 이상 연속 임계 초과"** 규칙으로 헛출동 인건비 절감. (예: warning 단계에서 N분 이상 지속 → critical 격상)

### 5-5. 🚧 알람 사양 변경 예정 (강사님 피드백 반영)
| 항목 | 현재 | 목표 |
|---|---|---|
| 시그마 레벨 | (2σ, 3σ, 6σ) | **(1σ, 2σ, 3σ)** |
| 디바운싱 | "N분 이상 연속" 단순 룰 | **도메인별 연속 N회 디바운싱** (Caution 3회 / Warning 5회 / Critical 7회 초안) |
| 적용 상태 | 미구현 | 진행 중 ([PROJECT_BRIEF.md §5-4](PROJECT_BRIEF.md)) |

→ 이 변경의 핵심은 **민감도(Recall) ↑** + **스파이크성 노이즈를 디바운싱으로 차단**.

## 6. 평가 — F1 score

### 6-1. 평가 지표
도메인별 모델 성능을 **시나리오 데이터**(정상/이상 라벨링)에 대한 confusion matrix 기반 F1 스코어로 평가.

| 지표 | 정의 | 의미 |
|---|---|---|
| 정밀도 (Precision) | TP / (TP + FP) | 모델이 이상이라 예측한 것 중 실제 이상인 비율 → **모델 신뢰성** |
| 재현율 (Recall) | TP / (TP + FN) | 실제 이상 중 모델이 잡아낸 비율 → **모델 완전성** |
| **F1 Score** | 2 · P · R / (P + R) | Precision과 Recall의 조화평균 |

### 6-2. 결과
**4개 도메인 모두 F1 ≥ 0.95** 달성. 데이터 불균형(정상 >> 이상)에서 Accuracy 한계를 보완하는 핵심 지표.

> 평가 코드: [services/inference/src/evaluate_test_metrics.py](../services/inference/src/evaluate_test_metrics.py)

### 6-3. nutrient 도메인 운영 예외
EC 기반 nutrient 도메인은 화학 센서 신뢰도 이슈와 일부 실험에서 다른 도메인 성능을 끌어내리는 결과를 보여 (`motor F1 0.527→0.106` 사례, [train.py:260-262](../services/inference/src/train.py#L260-L262) 주석), **현재 overall voting에서 제외하는 운영**으로 운용:

```python
EXCLUDE_FROM_OVERALL = {"nutrient"}  # evaluate_test_metrics.py:41
```

해당 도메인 모델 자체는 학습·서빙되며, 단지 종합 점수 산출에서만 제외.

**정량 근거** — EVAL 구간 전체 FP **581건 중 547건(94%)이 nutrient에서 발생**. 단독으로 잡은 진짜 이상은 **0건**. 근본 수정 후보 3안은 [PROJECT_BRIEF.md §5-1](PROJECT_BRIEF.md) 참조.

## 7. 산출 아티팩트

도메인별로 [services/inference/models/](../services/inference/models/) 또는 루트 [models/](../models/) 폴더에 다음 3종 파일 저장:

| 파일 | 내용 |
|---|---|
| `{domain}.h5` | Keras AE 모델 가중치 |
| `{domain}_scaler.pkl` | MinMaxScaler (입력 정규화) |
| `{domain}_config.json` | 메타데이터 (features, scoring_features, thresholds, target_reference_profiles, train/val loss curves) |

**inference_api.py 기동 시** 이 폴더를 자동 스캔해 4개 도메인 모델을 로드 ([INFERENCE_API.md §1](INFERENCE_API.md)).

## 8. 모델 실험 변천사

전체 실험 이력(가설 → 시도 → 관측 → 진단 → 수정)은 [.claude/MODEL_CHANGELOG.md](../.claude/MODEL_CHANGELOG.md)에 5블록 형식으로 누적 기록.

세션별 진행 상황·인수인계는 [SESSION_LOG.md](../SESSION_LOG.md).

## 9. 알려진 이슈 / 향후 개선

| 항목 | 현황 / 상태 |
|---|---|
| **NUTRIENT 오탐 독점** ⚠️ | EVAL FP 94%가 nutrient → overall voting 제외 운영. 근본 수정 3안 검토 중 ([PROJECT_BRIEF.md §5-1](PROJECT_BRIEF.md)) |
| **train.py 비결정성** ⚠️ | `random_state=42`에도 재학습마다 다른 모델. RF `n_jobs=-1`·SHAP·KMeans 랜덤성 의심. seed 전역 고정 + `n_jobs=1` 실험 예정 |
| **모델 아티팩트 소실 리스크** ⚠️ | `/models`가 `.gitignore` + 재학습이 덮어씀 → 재학습 전 `models_phaseX_YYYY-MM-DD/` 형태 스냅샷 규칙 수립 |
| **알람 사양 (1,2,3) σ + 디바운싱** | §5-5 참조. 미구현 |
| Tier 3 LSTM-AE 전환 | 검토 중 (VIP_FEATURES는 그대로 재사용 가능하게 설계됨) |
| `temp_slope_c_per_s` 등 기여도 0 변수 제거 | SHAP 분석 결과 반영 ([ANALYSIS.md §4-1 HYDRAULIC](ANALYSIS.md)) |
| nutrient 도메인 raw 센서 target 재편 | A-3 롤백 (2026-04-20) — 원인 미규명, A-2 상태 유지 중 |
| 집계 방식 확장 (mean + max 병행) | recall 향상 실험 예정 (목표 F1 0.5+) |
| Edge AI 경량화 | 향후 발전 방향 |
