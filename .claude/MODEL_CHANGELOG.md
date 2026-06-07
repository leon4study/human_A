# MODEL_CHANGELOG — 모델 개발 변천사

> 목적: 모델 실험의 **가설 → 시도 → 관측 → 진단 → 수정** 사이클을 시간순으로 누적 기록.
> SESSION_LOG가 "현재 상태"라면 이 파일은 "왜 지금의 상태가 됐는가"의 서사.
> 나중에 발표·리포트·리뷰에서 그대로 인용할 수 있도록 데이터와 함께 남긴다.

---

## Phase A — 기동 스파이크 오탐 해결을 위한 운전 모드 피처 주입

### 배경

AE 기반 다중 도메인 예지보전 파이프라인 (motor / hydraulic / nutrient / zone_drip)을 구축했는데,
펌프가 **06:00에 켜지는 순간**부터 5분 구간에서 4개 도메인이 줄줄이 Error/Critical 알람을 쏟아냄.

**관찰된 실제 알람 (2026-04-20 20:26, Phase A 이전)**:

```
2026-03-01 06:00:00 🔄[기동 스파이크]
  [MOTOR]   Error 🔴     MSE 0.003814  (thr 0.001191 / 0.001573 / 0.002719)
  RCA Top1: flow_drop_rate (56.9%)
```

→ 펌프 기동은 매일 반복되는 **정상 루틴**인데 AE가 못 배우고 있음.

### 가설 (왜 AE가 기동을 못 배우나)

1. **데이터 불균형**: 기동 구간은 전체 운전 시간의 0.7% (30일 × 5분 / 30일 × 720분). MSE 최소화는 steady state에 과적합.
2. **시간 맥락 부재**: AE는 snapshot만 봄. "06:00 기동 3분차"인지 "14:00 평상시 이상"인지 구분 불가.
3. **time_sin/time_cos 해상도 부족**: 하루 주기라 "정각 전후 5분"을 sharp하게 구분 못 함.

### 설계 원칙

- **Scaler 앞단에만 변경 → Tier 3 (LSTM-AE) 이동 시 재작업 최소화**
- 피처 엔지니어링 레이어를 모델 무관하게 분리 (`feature_engineering.py` 신규)
- preprocessing.py와 inference API는 건드리지 않음 (이미 passthrough + config-driven lookup)

### 1차 시도 — 모드 피처 4개 VIP 주입 (2026-04-20 20:50경)

**발견**: `preprocessing.py`가 이미 `pump_on`, `minutes_since_startup`, `is_startup_phase`, `is_off_phase`를
생성·집계·passthrough하고 있었음. 문제는 SHAP 기반 feature_selection이 이들을 안 뽑는 경우가 많아
**AE 입력까지 못 들어간다**는 것.

**조치**:

- `src/feature_engineering.py` 신규 생성
  - `MODE_FEATURES = ["pump_on", "minutes_since_startup", "is_startup_phase", "is_off_phase"]`
  - `VIP_FEATURES = ["time_sin", "time_cos"] + MODE_FEATURES`
  - `inject_vip_features()` 헬퍼로 주입 로직 일반화
- `src/train.py`: 기존 time-only VIP 블록을 헬퍼 호출로 교체.

**1차 실험 결과 (2026-04-20 21:09, 실패)**:

```
2026-03-01 06:00:00 🔄[기동 스파이크]
  [NUTRIENT]  Critical 🔴  MSE 0.144808  (thr 0.020511 / 0.029991 / 0.058433)
  RCA Top1: is_startup_phase (98.7%)  ← 내가 심은 피처가 RCA 독점
  [ZONE_DRIP] Critical 🔴  MSE 0.167135  (thr 0.022514 / 0.033279 / 0.065574)
  RCA Top1: is_startup_phase (99.7%)
```

**관측 요점**:

- MSE가 이전(0.003 대) 대비 **약 50배 폭발**.
- 학습 임계값(thresholds)도 10배 이상 커짐 → 학습 단계에서 이미 AE가 해당 피처를 못 배우고 있었다는 증거.
- RCA가 99% 이상을 `is_startup_phase` 단일 피처에 몰아줌.

### 진단 — 희소 binary의 AE 독성

RCA 99.7%가 힌트. `is_startup_phase`의 분포를 계산해보면:

- 학습 데이터 30일 × 720분 = 21,600 샘플 중 **150개(0.7%)만 `=1`**.
- MSE 최소화 = 다수 클래스(0)에 AE 가중치 완전 쏠림 → `=0` 샘플은 완벽 재구성.
- 추론 시 `=1`이 들어오면 AE는 그대로 0으로 복원 → **재구성 오차 (1-0)² = 1** (스케일 후).
- 다른 센서 피처의 정상 오차가 0.001~0.01 수준이므로 **이 한 피처가 100배 이상 차이로 MSE 지배**.
- RCA에서 99% 기여율이 나오는 이유가 정확히 이것.

**교훈**: 희소 binary를 AE 입력 VIP에 넣으면 오히려 AE를 터뜨린다. 분포 균형이 맞는 피처만 넣을 것.

### 2차 시도 — MODE_FEATURES 축소 (2026-04-20 21:30경)

**기준**: 각 피처를 "분포의 건강도"와 "정보의 고유성" 관점에서 재평가.

| 피처                    | 분포                     | 판정    | 이유                                                                                |
| ----------------------- | ------------------------ | ------- | ----------------------------------------------------------------------------------- |
| `pump_on`               | 50:50 (12h on / 12h off) | ✅ 유지 | 균형 잡힘 → AE가 양쪽 다 학습 가능                                                  |
| `minutes_since_startup` | 연속 0~720               | ✅ 유지 | 연속값이라 희소 문제 없음. "기동 후 N분"이라는 맥락의 **핵심 정보원**               |
| `is_startup_phase`      | 0.7% 희소                | ❌ 제거 | 희소 binary → AE 독성. 정보는 `minutes_since_startup ≤ 5`로 이미 연속값 안에 포함됨 |
| `is_off_phase`          | 50% (pump_on의 역수)     | ❌ 제거 | `pump_on`과 정보 중복 (거의 1 - pump_on). 남겨도 AE에 추가 정보 없음                |

**수정**:

```python
# src/feature_engineering.py (2차)
MODE_FEATURES = [
    "pump_on",                 # 50:50 분포 → 학습 안전
    "minutes_since_startup",   # 연속값, 기동 맥락의 핵심 정보원
]
```

경고 주석도 동반 추가 (앞으로 같은 실수 방지).

**다음 단계**: 이 상태로 재학습 → 기동 구간 알람이 Normal로 떨어지는지 확인.

- 떨어지면 Phase A 2차 성공 → 스토리: "희소 binary를 걸러내는 반복을 통해 올바른 맥락 피처에 도달"
- 여전히 오탐이면 **Phase B** (diurnal baseline residual) 또는 **sample_weight**로 진행.

### 배운 원칙 (절대 규칙으로 승격)

1. **희소 binary 금지**: AE 입력 VIP 리스트에는 분포가 치우친 binary(전체 5% 이하 `=1`) 넣지 않는다.
2. **맥락은 연속값으로**: 기동 후 경과시간처럼 맥락 정보는 연속 피처로 제공. Binary는 파생(derived)일 뿐이고 원천이 연속값이면 이미 포함된 것과 동일.
3. **RCA 단일 피처 독점은 경보**: 어떤 피처가 RCA 기여도 90% 이상을 먹으면 → 분포 불균형 or 스케일 문제 의심.
4. **임계값이 10배 급등하면 학습 붕괴 신호**: thresholds 자체가 이전 실험 대비 크게 변했다면 학습 분포에 문제가 생긴 것.

---

### 3차 시도 — `flow_drop_rate` 공식 버그 픽스 (2026-04-20)

**배경**: Phase A 2차 재학습 후 NUTRIENT/ZONE_DRIP 도메인은 Normal로 내려갔으나 **MOTOR 도메인만 여전히 Critical** (MSE 0.198, RCA `flow_drop_rate` 99.9%). 1차의 `is_startup_phase`와 동일한 "한 피처가 RCA 독점" 패턴 재발.

**가설**: `flow_drop_rate`는 binary가 아니지만 희소 극단값 분포를 가질 것. 공식을 보면:

```python
flow_drop_rate = (baseline - flow_rate) / (baseline + eps)   # baseline = rolling(60).mean().shift(1)
```

기동 전환(06:00) 시 `baseline ≈ 0`, `flow_rate ≈ 30` → `(0-30)/1e-6 ≈ -3e7`. 분모가 `eps`에 발산.

**진단 (데이터로 확증)**:

```
전체 분포
  min: -7.30e+07
  99%:  1.00
  (중앙값 0, 하지만 0.5% 샘플이 수천만 단위 음수)

극단값 상위 10개: 전부 06:00 기동 시점
  2026-03-09 06:00:00: -7.295e+07
  2026-03-02 06:00:00: -7.288e+07
  ...
```

MinMaxScaler가 이 극단 소수에 맞춰 스케일 → 99% 샘플이 0.999 근처로 압축 → AE는 "대부분 0.999"만 학습 → 기동 극단값 들어오면 복원 불가 → MSE 폭발. 1차 `is_startup_phase`와 **구조적으로 동일한 병리**(희소 극단값 + Scaler 왜곡).

**수정** — [preprocessing.py:89-141](../src/preprocessing.py#L89-L141):

1. `pump_on` / `minutes_since_startup` 계산을 `flow_drop_rate` 위로 이동 (게이트로 사용 가능하게).
2. 공식을 3단 게이트로 재구성:
   - pump_on=0 → 0 (정지 중엔 "드롭" 정의 무의미)
   - baseline < 1.0 L/min → 0 (기동 직후 누적 부족 구간, 분모 발산 방지)
   - 최종 `[0, 1]` 클리핑 (음수 drop = surge/상승은 "유량 감소" 의미 아님)

**수정 후 검증**:
| 지표 | 수정 전 | 수정 후 |
|---|---|---|
| min | -7.30×10⁷ | 0.0 |
| 06:00~06:05 평균 | -1.19×10⁷ | 0.0 (540 샘플 전부) |
| 극단값 상위 10위치 | 전부 06:00 기동 | 전부 18:04 정지 (값=1.0, 의도된 동작) |

**교훈 (절대 규칙 #5 추가)**: 5. **파생 공식의 분모 발산 체크**: `(A - B) / (B + eps)` 형태 공식에서 B가 0에 근접하는 구간이 있다면 반드시 게이트를 걸 것. `eps`는 0-division 방지용 안전장치이지 "작은 분모의 수치 안정화" 도구가 아님.

**다음 단계**: 이 상태로 4개 도메인 재학습 → MOTOR 오탐 해결 여부 확인. 해결되면 Phase A 3차 최종 성공.

---

## Phase A 3차 재학습 후 정량 평가 (2026-04-20)

### 배경

client_simulator 눈대중 검증은 "MOTOR Critical → Caution" 정도만 보여주고 recall/FAR 수치를 못 냄.
`data_gen_test.py`가 만든 `generated_test_data_0420.csv`(anomaly_label 포함) 기반 라벨 평가 필요.

### 도구 — `src/evaluate_test_metrics.py` 신규

테스트 CSV → `step1_prepare_window_data(tumbling)` → 4도메인 AE 배치 추론 → 혼동행렬·P/R/F1/FAR 산출.
구간(TRAIN/EVAL/ALL) × cutoff(1/2/3) × overall/도메인별 격자로 결과 저장.

### 에러 1 — `anomaly_label` 유실 (수정)

**관측**: 실행 중 `❌ df_agg에 anomaly_label 없음 — preprocessing passthrough 점검`.
**진단**: `preprocessing.create_modeling_features()`가 model_cols 화이트리스트 필터([preprocessing.py:344-345](../src/preprocessing.py#L344-L345))로 비-센서 컬럼을 전부 drop. anomaly_label이 aggregate 전에 제거됨.
**수정**: `step1_prepare_window_data(..., target_cols=["anomaly_label","composite_z_score","cleaning_event_flag"])`로 호출 → [preprocessing.py:343](../src/preprocessing.py#L343) `model_cols ∪ extra_cols` 경로로 보존. `phase_agg` 사전([preprocessing.py:372,387](../src/preprocessing.py#L372))에 `"anomaly_label":"max"`가 이미 정의돼 있어 10min 윈도우 라벨은 max 집계로 자동 보존.
**교훈**: 새 컬럼을 preprocessing 통과시키려면 sensor 화이트리스트 대신 `extra_cols` 파라미터를 써야 함.

### 에러 2 — Jupyter 경로 조립 실패 (수정)

**관측**: `ModuleNotFoundError: No module named 'preprocessing'`.
**진단**: `NB_DIR = os.path.abspath(".")`가 Jupyter 커널 cwd를 반환 → `SRC_DIR = os.path.join(NB_DIR,"src")`가 `notebooks/src`로 잘못 조립. 또한 `os.path.join(NB_DIR,"data","/abs/path")` 형태는 3번째 인자가 절대경로면 앞 인자를 폐기하는 posixpath 동작 때문에 버그성.
**수정**: `PROJECT_ROOT = "/Users/jun/GitStudy/human_A"` 하드코딩 + `SRC_DIR = os.path.join(PROJECT_ROOT,"src")`.

### 평가 결과 (EVAL 2026-04-01~05-31, 8496 샘플, anomaly 비율 32.5%)

**Overall (any domain level ≥ cutoff)**:
| cutoff | P | R | F1 | FAR |
|---|---|---|---|---|
| ≥1 | 0.6355 | 0.3669 | 0.4652 | 0.1013 |
| ≥2 | 0.6205 | 0.1996 | 0.3020 | 0.0588 |
| ≥3 | 0.5500 | 0.0199 | 0.0384 | 0.0078 |

**Per-domain (cutoff ≥1)**:
| domain | P | R | F1 | FAR | 평가 |
|---|---|---|---|---|---|
| **motor** | **0.9940** | 0.3582 | **0.5266** | **0.0010** | 유일하게 실전 가능한 품질 |
| hydraulic | 0.6343 | 0.0496 | 0.0920 | 0.0138 | recall 바닥 (스파이크 희석 추정) |
| zone_drip | 0.3742 | 0.0431 | 0.0773 | 0.0347 | 낮은 기여 |
| **nutrient** | **0.1533** | 0.0359 | 0.0581 | **0.0954** | **FP 547/581(94%) 독점** |

### 진단

1. **NUTRIENT 오탐 독점**: Overall FAR 10.1% 중 거의 전부가 nutrient 탓. threshold가 학습 분포에 비해 너무 낮게 잡힌 상태로 추정. 도메인을 voting에서 뺄지, threshold 재산정할지 결정 필요.
2. **recall 63% 놓침 (cutoff=1)**: 10min 평균 집계가 스파이크형 이상을 희석. HYDRAULIC recall 5%가 가장 강한 증거.
3. **MOTOR만 신뢰 가능**: 단일 도메인 기준 P=0.994/F1=0.527. Phase A가 MOTOR에만 제대로 먹은 셈.

### 다음 단계 (사용자 합의 — "둘 다")

- **① NUTRIENT 점검**: threshold_caution/warning/critical 재산정 또는 feature_selection 재검토. 목표 overall FAR 10% → 1%대.
- **② mean+max 집계**: `preprocessing.py`에 센서 핵심 피처의 max 집계 파생 추가. 목표 overall recall 37% → 50%+.
- ①②를 **각각 독립 실험**으로 돌려 기여도 분리 측정 (한 번에 섞으면 어느 쪽이 기여했는지 구분 불가).

---

## A-2 — NUTRIENT voting 제외 (2026-04-20, 성공)

### 가설

NUTRIENT는 FP 547/581(94%)를 독점. nutrient 단독 precision 0.15로 거의 noise. voting에서 빼면 다른 도메인의 정상 신호는 유지한 채 FAR만 감소할 것.

### 조치

[evaluate_test_metrics.py](../src/evaluate_test_metrics.py)에 `EXCLUDE_FROM_OVERALL = {"nutrient"}` 추가. overall 레벨 계산 시 nutrient 제외 + 비교용 `overall_alarm_level_with_nutrient` 병행 저장.

### 결과

| 지표 (EVAL, cutoff≥1) | 수정 전 | A-2 후 | Δ      |
| --------------------- | ------- | ------ | ------ |
| Precision             | 0.636   | 0.800  | +16%p  |
| Recall                | 0.367   | 0.367  | **±0** |
| F1                    | 0.465   | 0.503  | +3.8%p |
| FAR                   | 10.13%  | 4.43%  | −56%   |
| FP                    | 581     | 254    | −327   |

**보너스 증거**: Recall 무변화 = nutrient의 TP 99건이 전부 다른 도메인도 함께 잡았던 이상. nutrient 단독 TP는 0건 → voting 제외해도 검출 손실 전무 → 도메인명·피처 불일치 진단 재확인.

---

## A-3 — NUTRIENT feature_selection 재설계 시도 (2026-04-20, 실패 → 롤백)

### 배경 (A-2 후에도 남은 근본 문제)

`models/nutrient_config.json` 최종 학습 피처: `time_cos, time_sin, motor_temperature_c, pump_rpm, pump_on, minutes_since_startup`. 영양액 관련 원본 센서가 하나도 없음 = "도메인 이름만 nutrient, 실제로는 모터/시간 감시기". A-2(voting 제외)는 증상 차단이고 근본 수정은 안 됨.

### 진단

`train.py`의 nutrient target_dict가 파생 target 구조:

```python
"pid_error_ec":          ["mix_ec_ds_m", "mix_target_ec_ds_m"],
"salt_accumulation_delta": ["drain_ec_ds_m", "mix_ec_ds_m"],
```

두 target의 leak_cols 합집합이 {mix_ec, mix_target_ec, drain_ec} 전부를 SHAP 후보 X에서 drop. 영양액 raw 센서가 feature_selection 후보에 아예 들어가지 못함. + `df_interpret`에도 mix_ec/mix_ph/drain_ec가 passthrough되지 않아 VIP 주입으로도 복구 불가.

### 가설 (C안)

target을 raw 센서(mix_ec_ds_m, mix_ph, drain_ec_ds_m)로 바꾸고, preprocessing.py에서 이 raw 센서로부터 계산되는 모든 파생(pid_error_ec/ph, salt_accumulation_delta, ph_instability_flag, ph_roll_mean_30, ph_trend_30, zone{1,2,3}\_ec_accumulation)을 leak_cols에 전수 명시하면 SHAP이 EC/pH를 선행 예측하는 피처를 자연스럽게 선택할 것.

### 시도

[train.py:206-229](../src/train.py#L206)의 nutrient target_dict 전면 교체. 3개 raw 타겟 + 각 타겟별 파생 leak_cols 명시.

### 관측 (결과)

**전체 도메인 악화**:
| EVAL overall(no_nutrient) | A-2 | C안 재학습 |
|---|---|---|
| Precision | 0.800 | 0.297 |
| Recall | 0.367 | 0.088 |
| F1 | 0.503 | 0.136 |
| FAR | 4.4% | 10.1% |

도메인별: motor F1 0.527→0.106 (**변경 안 한 도메인이 박살**), zone_drip F1 0.077→0.004 (완전 붕괴). 학습 구간 FP 450건(이전 0). nutrient 자체 precision은 0.153→0.561로 개선됐지만 다른 도메인 희생이 훨씬 큼.

또 NUTRIENT 최종 피처를 확인해도 `time_cos, motor_temperature_c, pump_rpm, time_sin, pump_on, minutes_since_startup`으로 **본질적으로 변화 없음**. 3개 raw target끼리 상호 leak라서 공통 프록시(time/motor/pump)만 robust(≥2 target) 통과, 영양액 raw 피처는 서로 다른 target에서만 중요해 voting 탈락.

### 진단 — 예상 못 한 비결정성

target_dict 원복 후 재학습(옵션 1 롤백) → **첫 A-2 상태로 복원 실패**. F1 0.377까지만 회복, motor P 0.994→0.601 여전. 피처 수조차 다르게 뽑힘(motor robust 3→2, nutrient 4→3).

`random_state=42`가 걸려 있음에도 `train.py` 파이프라인이 비결정적. 원인 미규명 (후보: RF 병렬 연산 순서, TF GPU 연산, numpy seed 미전역화, shuffle 등).

### 자산 손실

`.gitignore:295`의 `/models` 규칙으로 모델 아티팩트는 git 추적 대상이 아님. 재학습이 `models/*.keras|pkl|json`을 덮어씀 → 첫 A-2 모델(F1=0.503) 영구 소실. Time Machine·Trash·/tmp 모두 백업 없음.

### 롤백 최종 상태

- `train.py` target_dict: 원복 완료 (원본 `pid_error_ec`/`salt_accumulation_delta` target).
- `evaluate_test_metrics.py`: extra_cols 패치 + `EXCLUDE_FROM_OVERALL={"nutrient"}` + with/without 비교 기능 **전부 유지**.
- 현재 `models/`: 롤백 재학습 결과물. F1 0.377, hydraulic P=1.000/F1=0.261로 일부 개선, motor/nutrient는 악화. 첫 A-2 수치는 재현 불가.

### 배운 원칙 (절대 규칙 #6 추가)

6. **재학습 전 `models/` 백업 필수**: `/models`는 gitignore되어 있고 `train.py`는 비결정적이라 재학습이 모델을 덮어쓰면 복구 불가. 실험 전 `cp -r models/ models_backup_$(date +%Y%m%d_%H%M)/`로 스냅샷.

### 추가 숙제

- train.py 비결정성 원인 감사 (RandomForest `n_jobs=-1`, TF 연산, numpy seed 전역화 여부).
- nutrient 피처 주입 대안: (a) `top_ratio` 상향, (b) `df_interpret`에 영양액 raw 센서 passthrough + `NUTRIENT_VIP` 강제 주입, (c) robust voting 대신 union/도메인별 명시 리스트 사용.

---

## Phase B — 알람 점수와 RCA 원인 분리: 컨텍스트 피처 단일 소스 + startup gating (2026-04-20)

### 가설

Phase A에서 time/pump 컨텍스트 피처를 VIP로 AE 입력에 주입했더니, AE가 컨텍스트 의존 정상 패턴을 학습하는 이득은 얻었다.
그런데 **추론 시 MSE는 전체 피처 평균**이라, 컨텍스트 피처 하나가 복원 오차를 크게 내면 실센서가 멀쩡해도 threshold를 넘는다.
RCA도 같은 feature_errors 배열을 쓰므로 "원인 Top1: time_cos"처럼 **액션 불가능한 설명**이 나온다.
→ 운영자 입장에서 **알람이 떴는데 현장에서 볼 게 없는** 상태.

### 관측된 실제 알람 (Phase B 이전)

```
🚨 [이상 진단 리포트] 2026-03-02 06:38:00
  [MOTOR] Caution 🔸   MSE 0.000440  (thr 0.000421 / 0.000557 / 0.000966)
  RCA Top 1: time_cos (58.1% 기여)
  RCA Top 2: time_sin (41.6% 기여)
  RCA Top 3: minutes_since_startup (0.2%)
  Action Required: Inspect [time_cos]   ← 현장 조치 불가
```

### 진단

- `inference_api.py:107`: `mse_score = np.mean((scaled - pred)**2)` — 전체 피처 평균
- `inference_core.calculate_rca`: feature_errors 배열을 그대로 정렬
- 시간 피처 복원 오차가 실센서(0.0003~0.0001 수준)보다 **10~50배 큼**. 기여도 %가 시간 피처에 집중.
- 깊은 원인: AE bottleneck이 작고(input//4), 시간 피처는 하루 주기 단일 스케일 + `MinMaxScaler`로 압축된 상태라 decoder가 덜 민감하게 복원. AE capacity 문제.

### 설계 원칙

- **단일 소스**: 제외할 컨텍스트 피처 셋을 `inference_core.DEFAULT_CONTEXT_FEATURES` 한 곳에 모음. train/inference/RCA가 모두 여기서 import → 불일치 사고 원천 차단.
- **"알람 근거 == 설명"**: MSE 계산에 쓰인 피처 == RCA 대상 피처. 운영자가 "왜 알람?" 물으면 "이 피처들이 평균적으로 이상"이라고 같은 셋으로 답할 수 있어야 함.
- **컨텍스트는 입력에는 남김**: AE 학습 시엔 여전히 시간/모드 피처를 입력으로 받아 **컨텍스트 의존 정상 패턴 학습**. 단, 점수화와 설명에서만 빼기.
- **운영 모드 gating**: 기동 직후는 정상 스파이크가 구조적으로 발생 → 알람 억제가 현장 원칙.

### 조치

**1. 제외 피처 목록 정의 — [src/inference_core.py](../src/inference_core.py)**

```python
DEFAULT_CONTEXT_FEATURES = frozenset({
    "time_sin", "time_cos", "minute_of_day",
    "pump_on", "pump_start_event", "pump_stop_event",
    "minutes_since_startup", "minutes_since_shutdown",
    "is_startup_phase", "is_off_phase",
    "cleaning_event_flag",
    "ph_instability_flag",
})

def actionable_feature_mask(features, exclude=None) -> np.ndarray:
    blocked = DEFAULT_CONTEXT_FEATURES if exclude is None else set(exclude)
    return np.array([f not in blocked for f in features], dtype=bool)
```

`preprocessing.py`의 `time_cols + phase_cols` 규약과 동일 + ph_instability_flag(파생 플래그) 추가.

**2. train-time threshold 계산 분리 — [src/train.py](../src/train.py)**

- `sq_err = (X_scaled - reconstructed)^2` 계산 후, `actionable_feature_mask`로 컬럼 마스킹.
- `mse_scores = mean(sq_err[:, mask], axis=1)` → 여기서 sigma threshold 계산.
- config에 `"scoring_features": [...]` 추가해 추론 시 재현 가능하게 저장.

**3. 추론 시 동일 mask 적용 — [src/inference_api.py](../src/inference_api.py)**

```python
sq_err = np.power(scaled_array - pred_array, 2)[0]
scoring_mask = np.array([f in set(config["scoring_features"]) for f in features])
mse_score = float(np.mean(sq_err[scoring_mask]))
```

`scoring_features` 키가 없는 구버전 모델은 `actionable_feature_mask(features)`로 동적 폴백.

**4. Startup gating**

```python
if int(realtime_data.get("is_startup_phase", 0)) == 1:
    alarm_level, label = 0, "Normal (startup gated)"
```

펌프 기동 직후 5분(`preprocessing.py`가 0~5분을 `is_startup_phase=1`로 세팅)은 정상 스파이크로 간주해 알람 억제.

**5. RCA 함수는 이미 Phase B 직전 커밋에서 `DEFAULT_CONTEXT_FEATURES` 기반 필터·재정규화 적용됨.**

**6. 노트북 버전 동기화 — [notebooks/model_middle_0420.ipynb](../notebooks/model_middle_0420.ipynb)**

- `train_and_save_model`에 동일 scoring_mask 로직 주입.
- `return mse_scores, thresholds` 로 변경 → 메인 루프가 `all_results[system_name] = train_and_save_model(...)` 로 결과 수집.
- 마지막 셀에 `plot_threshold(mse_scores, thresholds, model_name)` 정의: 왼쪽 히스토그램(log y) + 오른쪽 시계열, 둘 다 Mean/Caution(2σ)/Warning(3σ)/Critical(6σ) 수직·수평선 표시.

### 검증

- `ast.parse`: `inference_core.py`, `train.py`, `inference_api.py` 3개 파일 모두 OK.
- 단위 테스트: 합성 feature_errors로 `calculate_rca` 실행
  - before (exclude 없음): `time_cos(55.7%) → time_sin(40.3%) → flow_rate(2.9%)`
  - after (기본 exclude): `flow_rate(75%) → suction_pressure(25%)` ← 실센서 중심 재정규화.

### 기대 효과

- **RCA 해석성**: 모든 알람의 원인이 실센서(suction/discharge pressure, flow*rate, motor*\* 등) 기반으로 나와 현장 점검 포인트가 명확.
- **false positive 감소**: 시간/모드 피처 복원 오차만으로 MSE가 threshold를 넘지 못함. 기동 구간은 startup gating으로 추가 억제.
- **단일 소스 안정성**: 컨텍스트 피처 리스트 변경 시 한 곳만 수정하면 train/inference/RCA 전체 반영. 불일치 사고 원천 차단.

### 주의·리스크

- **재학습 필수**: `scoring_features` 키는 신규이므로 기존 모델은 config에 없음. 구버전은 동적 mask로 폴백하나, **threshold 값 자체는 전체 피처 평균 기준으로 저장**돼 있어 새 mask와 스케일이 맞지 않음 → 알람이 거의 안 뜨는 false negative 가능. 재학습해서 config 갱신 필요.
- **재학습 전 `models/` 백업** (Phase A-3 규칙): 비결정성으로 재현 불가한 자산 손실 방지.
- **DEFAULT_CONTEXT_FEATURES 과잉 제외 위험**: 현재 12개 중 `ph_instability_flag`는 파생 플래그라 제외가 자연스럽지만, 실센서 중 하나라도 실수로 들어가면 실제 이상을 놓치게 됨. 변경 시 RCA 단위 테스트로 검증 권장.

### 남은 과제

- 재학습 후 client*simulator 실행으로 실제 RCA 출력이 time*\*에서 실센서로 이동했는지 눈으로 확인.
- startup gating을 `is_off_phase`까지 확장할지 결정 (정지 구간도 센서 값 자체가 다른 분포라 false positive 유발 가능).
- AE bottleneck 재설계 검토: 시간 피처가 reconstruction error를 키운 근본 원인이 모델 capacity라면, `build_autoencoder`의 bottleneck_size = max(4, input_dim // 4)가 적절한지 재점검.

---

## Phase C — Per-Feature Threshold 추가: 피처별 정상 범주 정밀화 (2026-04-21, 코드 완성)

### 배경 (프론트엔드 드릴다운 요청)

Phase B에서 domain-level MSE threshold로 "도메인이 이상인가"는 판정하고,
RCA로 원인 피처를 Top 3로 보여줌. 하지만 운영 대시보드에서 **"motor_current_a는 얼마나 벗어났나? 정상 범위가 뭔가?"**
질문에는 `feature_details.bands`(raw σ 밴드) 정도만 답할 수 있음.

AE는 **피처별로 재구성값을 내놓는 모델**인데, MSE는 F개 피처를 axis=1 평균으로 압축.
→ domain threshold 스칼라 하나로는 역산 불가능하지만,
→ **AE의 원본 출력(피처별 재구성오차)은 여전히 (N x F) 행렬로 살아있음**.

### 가설

피처별 재구성오차 분포(axis=0 관점)의 시그마 컷으로 **피처별 독립 threshold**를 계산하면,

- 프론트에서 "motor_current_a 현재 0.0031, threshold: caution 0.0031 warning 0.0040 critical 0.0067"처럼 표시 가능
- 각 피처가 AE의 학습 과정에서 얼마나 재구성 잘 했는지 반영 (피처별 신뢰도 자동 포함)
- RCA와 달리 **도메인 MSE 기반이라 알람 근거와 직결되고 일관성 유지**

### 설계

**단일 소스**: Caution/Warning/Critical σ 정책(2/3/6σ)은 domain threshold와 동일하게.
**정책 일관성**: `actionable_feature_mask` 동일 적용 → 컨텍스트 피처 제외.
**backward compat**: config에 `per_feature_thresholds` 없는 구모델은 inference 시 graceful fallback (None 체크).

### 조치

**1. train.py — per-feature threshold 계산 및 config 저장**

```python
per_feature_thresholds = {}
for j, fname in enumerate(feature_cols):
    if not scoring_mask[j]:
        continue  # 컨텍스트 피처 제외
    col_err = sq_err[:, j]
    mu = float(col_err.mean())
    sd = float(col_err.std())
    per_feature_thresholds[fname] = {
        "mean":     round(mu, 8),
        "std":      round(sd, 8),
        "caution":  round(mu + 2 * sd, 8),
        "warning":  round(mu + 3 * sd, 8),
        "critical": round(mu + 6 * sd, 8),
    }
```

config에 저장: `"per_feature_thresholds": per_feature_thresholds`

**2. inference_core.py — build_feature_details 확장**
함수 시그니처: `scaled_errors=None, per_feature_thresholds=None` 인자 추가.
각 feature 엔트리에:

```python
entry["scaled_error"] = round(float(scaled_errors[i]), 8)
entry["feature_thresholds"] = per_feature_thresholds[f_name]
entry["feature_alarm"] = {"level": f_alarm_level, "label": f_alarm_label}
```

**3. inference_api.py — 응답에 피처별 정보 통합**

```python
per_feature_thresholds = config.get("per_feature_thresholds", None)
feature_details = build_feature_details(
    input_values, pred_raw_array, features, feature_stds,
    scaled_errors=sq_err, per_feature_thresholds=per_feature_thresholds
)
"per_feature_thresholds": config.get("per_feature_thresholds", {}),
```

### 기대 JSON 응답 예시 (feature_details[i])

```json
{
  "name": "motor_current_a",
  "actual_value": 18.42,
  "expected_value": 14.10,
  "bands": { "caution_upper": 15.20, ... },

  "scaled_error": 0.003100,
  "feature_thresholds": {
    "mean": 0.001300,
    "std": 0.000900,
    "caution": 0.003100,
    "warning": 0.004000,
    "critical": 0.006700
  },
  "feature_alarm": { "level": 1, "label": "Caution 🔸" }
}
```

### 남은 과제 (재학습 필수)

1. **재학습**: `python src/train.py` 실행 → config에 `per_feature_thresholds` 저장
2. **검증**: client_simulator 실행 → feature_details에 신규 필드 확인
3. **정책 결정**: feature_alarm.level이 domain alarm.level과 충돌 시 voting 규칙 수립

### 주의사항

- 피처별 threshold는 **스케일 공간 기준** (raw 센서 단위 아님)
- 컨텍스트 피처는 threshold 대상 제외 (scoring_mask 준수)
- 구모델(Phase B)은 per_feature_thresholds 필드 없음 → inference는 graceful fallback

---

## Phase D — 비결정성 진범 규명: PYTHONHASHSEED와 set 순서 (2026-06-01)

### 가설
재현성 인프라(repro.set_global_determinism: numpy/random/TF 시드 + op_determinism)를 넣고 train.py 첫 실행(baseline-repro) 성공. "이제 같은 코드·데이터면 config가 동일할 것"이라 가정하고 2회차(repro-check)로 검증.

### 시도
`train.py`를 2회 실행해 run1 vs run2의 `*_config.json`을 diff.

### 관측 (재현성 테스트 실패)
4개 도메인 config 전부 다름. 단순 가중치 차이가 아니라 **피처 선택 자체가 달라짐**:
- motor 다중공선성 드롭: run1 13개 제거(25 남음) vs run2 10개 제거(28 남음)
- motor SHAP robust: run1 `[pressure_trend_10]` vs run2 `[flow_rate_l_min, pressure_trend_10]`
- zone_drip robust: run1 2개 vs run2 0개

### 진단 (데이터로 확증)
- `sys.flags.hash_randomization == 1` (해시 무작위화 ON).
- 동일 set을 두 프로세스에서 list로 출력 → 순서가 다름(`['suction_pressure_kpa', ...]` vs `['pressure_flow_ratio', ...]`).
- 즉 진범은 TF가 아니라 **Python 해시 무작위화**. preprocessing 다중공선성 드롭과 feature_selection robust voting이 set/dict 순서에 의존 → 매 실행 어느 컬럼을 드롭/선택하는지가 달라지고 전체 파이프라인이 어긋남.
- 핵심 함정: `os.environ["PYTHONHASHSEED"]="42"`를 **런타임에** 대입해도 이미 실행 중인 인터프리터의 해시 시드는 바뀌지 않는다(시작 전 환경에 있어야 함). repro 1차 구현이 이 대입만 해서 무효였다.

### 수정 — [repro.set_global_determinism](../src/repro.py)
PYTHONHASHSEED가 seed로 박혀 있지 않으면 환경변수를 설정하고 `os.execv`로 프로세스를 재실행(re-exec). 재실행 후에는 해시 시드가 고정돼 set 순서가 매 실행 동일.
- 격리 검증: 동일 스크립트 2회 실행 → set 순서 동일 확인.
- 전체 파이프라인 검증(train.py 2회 config diff)은 사용자 재실행 대기.

### 배운 원칙 (절대 규칙 #7 추가)
7. **PYTHONHASHSEED는 런타임 대입 불가**: 해시 무작위화를 끄려면 인터프리터 시작 전 환경변수로 박거나 re-exec해야 한다. set/dict 순서에 의존하는 파이프라인(피처 드롭·voting)은 이걸 안 하면 매 실행 결과가 달라진다. 재현성은 시드 4종(hash/random/numpy/TF)을 모두 잡아야 완성된다.

### 메모
- 이전 기록·문서에서 "비결정성 직접 원인 = TF(무시드)"라 적었던 것은 오진이었다. feature_selection RF/KMeans는 random_state로 재현 가능하나, 그 위 set 순서가 흔들리고 있었다. TF 시드도 필요하지만 진범은 해시였다.

---

## Phase E — 빈약 도메인 보강: zone_drip 배지 복원 + 피처 1차 배치 (2026-06-02, 성공)

### 가설
재현성 확보 후 첫 실험. (1) zone_drip이 배지 센서 0개로 학습돼 퇴화(기동 spike만 반복) → 배지 센서 복원하면 실제 신호가 생긴다. (2) 중복 제거 후 도메인이 빈약 → 물리 근거 있는 파생 피처를 추가하면 막힘 직격 신호가 강해진다. (근거: [docs/modeling/09_feature_rationale_ledger.md](../docs/modeling/09_feature_rationale_ledger.md))

### 시도 (PHASE=feature-v2)
- preprocessing `model_cols`+collinearity whitelist에 zone 배지 센서(`zone1_substrate_moisture/ec`, Raw) + 공급균형 파생지표(`supply_balance_index`, 유량) 복원. 펌프 중복인 zone 압력/유량은 제외. (supply_balance_index는 이후 Phase G에서 유량 성격이라 hydraulic으로 이동)
- 신규 파생 7개: zone(`zone_ec_variance`·`zone_moisture_variance`·`substrate_ec_accum_rate`), hydraulic(`system_resistance`·`specific_energy`), motor(`bearing_thermal_margin`·`load_per_speed`). `create_modeling_features`에 추가 + 도메인별 `SENSOR_MANDATORY` 배정.
- 스모크 테스트로 `system_resistance` 저유량 분모 발산(4.5e7) 선제 발견 → pump_on & flow≥1.0 게이트 적용(절대규칙 #5).

### 관측 (진단 그림)
- **zone_drip**: X_train_ae 피처 5~10 → **14개**(배지·변동성 피처 전부 주입). 진단 그림이 0/0.5 이분 반복(무변동)에서 연속 변동으로 회복, skew 18.69→11.28, 후반부(월3 drift)에서 baseline 상승 관측. 기동 제외 임계치와 실선 간격 10배→약 1.3배.
- **hydraulic**: `system_resistance`·`specific_energy`가 robust 교집합(6개)으로 선정. skew 3.44(최저), 타임라인이 정상 구간 평탄→월3 drift에서 깨끗하게 critical 돌파. 가장 명료한 막힘 응답.
- motor/nutrient: 회귀 없음(기존 + 신규 일부 흡수). 재현성 re-exec 정상 작동.

### 진단
빈약의 근본은 "raw 센서 부족"이 아니라 "도메인 고유 신호를 담은 파생 피처 부족"이었다. 배지 변동성·시스템 저항 같은 물리 근거 피처가 들어가자 두 도메인 모두 실제 이상 구간(월3)에 반응. zone_drip은 robust voting은 여전히 0(타깃 간 공통 예측자 부재)이나 union+MANDATORY로 충분한 입력 확보.

### 다음 단계
- 정량 확인: `evaluate_test_metrics.py`로 라벨 기반 F1/FAR + 이상 음영 타임라인(월1정상→월3이상 구조에서 검출 확인).
- threshold: skew 여전(zone 11·motor 15) → percentile/PR 전환 실험([03](../docs/modeling/03_threshold_methodology.md)).

---

## Phase F — Dynamic threshold 수렴: percentile 진단 → skew-adaptive → 기동마스크 수정 (2026-06-02)

### 가설
feature-v2 평가에서 zone_drip은 신호가 있는데(MSE가 이상 구간에 상승) σ 임계치가 너무 높아 recall 0.015로 막혔다. 임계치 산정을 바꾸면 풀릴 것.

### 시도와 관측 (3회)
1. **percentile(전 도메인, PHASE=pct-thr)**: zone_drip recall 0.015→0.41(F1 0.46)로 진단 적중. 그러나 hydraulic은 percentile이 안 맞아 F1 0.46→0.26으로 악화. overall FAR 1.7%→19%.
2. **skew-adaptive(PHASE=skew-adaptive)**: 분포 skew>8이면 percentile, 아니면 sigma로 도메인별 자동 분기 구현. 자동 라우팅은 정확(hydraulic skew 3.4→sigma, zone 8.0→percentile). 그러나 hydraulic이 더 떨어짐(F1 0.21).
3. **진단 — 기동 마스크 버그**: threshold를 "기동 제외"로 계산하는데 `minutes_since_startup<=5`가 정지(off) 구간(minutes=0)까지 잡아 데이터의 50%를 제외 → baseline 왜곡으로 hydraulic 임계치 오염. `(pump_on==1) & (minutes<=5)`로 수정(0.5%만 제외).

### 결과 (PHASE=skew-fix, 최종)
| EVAL F1 cutoff≥1 | feature-v2(σ all) | pct-thr | skew-fix |
|---|---|---|---|
| hydraulic | 0.462 | 0.261 | **0.469** (P0.99, FAR0.001) |
| zone_drip | 0.029 | 0.458 | **0.456** (R0.38) |
| overall(no_nut) | 0.455 | 0.458 | **0.481** |
overall recall 0.31→0.41, FAR(월1 클린) 1.4%, cutoff≥2 운영 시 FAR 2.4%.
- 마스크 수정 후 zone_drip skew 8.0→7.2로 떨어져 sigma로 분기됐고 그래도 F1 0.456 — 신호만 있으면 방법 무관.

### 진단 / 교훈
- 임계치 '방법'은 분포 모양(skew)에 종속이며 도메인마다 다르다 → 단일 방법 강제는 한 도메인을 희생. skew-adaptive로 best-of-both.
- 기동 제외는 반드시 `pump_on==1`과 AND. minutes_since_startup 단독은 off를 오분류(절대규칙 후보).
- percentile 레벨 조정은 '방법' 불일치를 못 고친다(hydraulic). 레벨이 아니라 방법을 분기해야 한다.

### 구현
[train.py](../src/train.py) 임계치 블록: 기동 제외(pump_on AND minutes≤5) → mse_base skew 계산 → `THRESHOLD_METHOD=auto`면 SKEW_CUTOFF(기본 8)로 sigma/percentile 분기. config에 threshold_method·threshold_skew 기록. 환경변수(SKEW_CUTOFF, PCT_*)로 튜닝.

### 남은 과제
- overall FAR(cutoff≥1) 14%는 zone_drip 주도 + 평가라벨이 펌프막힘 기준이라 배지 탐지가 FP로 계수되는 영향 혼재. 운영점(cutoff≥2)·zone 전용 보정·percentile 레벨은 후속 튜닝.

---

## Phase G — 도메인 경계 정리: supply_balance_index를 zone_drip→hydraulic 이동 (2026-06-02, 성공)

### 가설
zone_drip이 "구역 배지 상태 + 유량 균형"을 섞고 있어 이름이 애매(배지 도메인인데 supply_balance_index는 유량). supply_balance(구역합/메인 유량 = 누수 탐지)는 유량 본질이라 hydraulic 소속이 맞다. 옮기면 zone_drip이 순수 배지 상태가 되고, 유량 노이즈가 빠져 precision이 오를 것.

### 시도
`feature_engineering.SENSOR_MANDATORY`에서 supply_balance_index를 zone_drip → hydraulic으로 이동(model_cols·whitelist는 도메인 무관이라 불변). 분할 기준 문서 [docs/DOMAIN_DESIGN.md](../docs/DOMAIN_DESIGN.md) 신설.

### 관측 (PHASE=domain-cleanup, eval)
| EVAL cutoff≥1 | skew-fix | domain-cleanup |
|---|---|---|
| overall(no_nut) F1 | 0.481 | **0.504** |
| overall precision | 0.582 | **0.647** |
| overall FAR | 0.142 | **0.109** |
| zone_drip F1 / P | 0.456 / 0.515 | **0.486 / 0.656** |
| hydraulic | 0.469 | 0.469(불변) |
cutoff≥2: F1 0.268, FAR 1.8%(운영 제약 안). zone_drip skew 8.0→4.56(배지만 남아 덜 치우침)으로 sigma 분기.

### 진단 / 교훈
supply_balance(유량)가 zone_drip(배지)에 섞여 **유량 불균형에 알람을 올려 zone_drip의 FP를 늘리고 있었다**. 제 도메인으로 보내니 zone_drip precision 0.515→0.656로 상승, 전체 F1도 개선. **도메인 경계를 물리량 본질대로 맞추면 해석성뿐 아니라 성능도 오른다**(경계 정합 = 노이즈 감소). 새 피처 배정 원칙: 한 컬럼이 두 도메인에 걸치면 물리량 본질로 귀속(DOMAIN_DESIGN §6).

### 현재 수렴 상태 (threshold+feature+domain 트랙)
overall F1 0.504(시작 0.455 대비), hydraulic P0.99 주력, zone_drip 부활·정밀화(0.03→0.49), 클린-정상 FAR 1.4%. 후속 후보: FAR 컨트롤(운영점/레벨), 피처 자료조사, 모델층(Optuna).

---

## Phase H — motor 진동/베어링온도 센서 누락 발견·수정 (2026-06-06)

### 가설
재학습(`retrain-regime`)으로 현재 피처·기동 band를 반영하면 4도메인 정본 모델이 나오고, 측정 도구(lead-time·막힘률·coupling_validate)로 검증 가능하다.

### 시도
`DOMAIN_ISOLATION=0`(기본)으로 `python src/train.py` 재학습. run `2026-06-06_144921__ef0128d__retrain-regime`. 기동 band(threshold_startup) 4도메인 생성(n=540).

### 관측
- 정본 측정: lead-time 6/6·평균 29.9h·정상 FAR 1.0%·기동 FAR 0.0%(regime band 정상 동작). 막힘률은 baseline·AE 둘 다 0%(심한 막힘), AE 우위는 FAR 5%→1%.
- 학습 로그 경고: `⚠️ [MOTOR] SENSOR_MANDATORY에 있으나 df_agg에 없는 피처: ['bearing_vibration_rms_mm_s', 'bearing_temperature_c']`.
- coupling_validate: motor가 흡입 막힘의 진동(+45%)을 또 놓침(motor 알람률 0.08). zone_drip은 motor 베어링 고장에 여전히 오탐(isolation OFF라 motor_temp 누설 유지).

### 진단
raw 데이터에 `bearing_vibration_rms_mm_s`·`bearing_temperature_c`가 있는데도 `preprocessing.model_cols` 화이트리스트에 없어 집계 전에 잘렸다. zone_drip 토양센서 누락(Phase 직전)과 **동일한 버그 클래스**. 진동은 파생 생존자도 없어 motor가 '진동'을 한 피처도 못 보고 학습 → 베어링·공동현상 등 진동 기반 고장에 구조적 깜깜이.

### 수정
`model_cols`에 `bearing_vibration_rms_mm_s`·`bearing_temperature_c` 추가(상세 주석 포함). src/+services/ 동기화. 스모크 테스트로 집계 후 df_agg에 생존 확인. **재학습 1회 필요**(다음 retrain에서 motor가 진동을 보게 됨).

### 남은 과제
- motor 재학습 후 coupling_validate로 "흡입 막힘 진동 검출됨" 확인.
- zone_drip 경계 누설은 `DOMAIN_ISOLATION=1` 재학습으로 검증(별도).
- hydraulic(`hydraulic_power_kw`·`filter_delta_p_kpa`)·nutrient(`mix_temp_c`) 누락도 같은 점검 필요(status 열린이슈).

## Phase I — motor 진동 fix + 도메인 격리 재학습: attribution 확인 (2026-06-06, 성공)

### 가설
(a) motor에 진동 센서를 살리면(Phase H fix) 흡입 막힘·베어링 등 진동 기반 고장을 잡고,
(b) DOMAIN_ISOLATION=1로 타 도메인 핵심 센서를 후보에서 빼면 zone_drip의 motor_temp 누설 오탐이 사라진다.

### 시도
`DOMAIN_ISOLATION=1 PHASE=retrain-fix-iso python src/train.py`. run `2026-06-06_205644__996f8a3__retrain-fix-iso`.
격리 작동(motor 24·hydraulic 22·nutrient 27·zone_drip 29개 제외). motor 피처에 bearing_vibration_rms_mm_s·
bearing_temperature_c 주입 확인(이전 run의 "df_agg에 없음" 경고 사라짐). zone_drip 피처에서 motor_temperature_c 제거 확인.

### 관측 (coupling_validate 검출지도 — 고정 오라클로 before/after 대조)
| 고장 | 이전(regime, 버그) | 지금(fix-iso) | 기대 |
|---|---|---|---|
| clog_downstream | hydraulic+motor+nutrient+zone | hydraulic+motor+nutrient | 광역 |
| bearing_wear | motor + **zone_drip(오탐)** | **motor만** | motor만 |
| suction_blockage | hydraulic+nutrient+zone (**motor 0.08 놓침**) | **hydraulic+motor** | hydraulic+motor |
| nutrient_imbalance | nutrient | nutrient | nutrient |
- lead-time 29.9h→**35.9h**(진동 fix로 더 일찍), 기동 FAR 0.0%, 정상 FAR 1.0%→1.4%.
- 막힘률: baseline·AE 둘 다 0%(심한 막힘). AE FAR 1.4% vs baseline 5.0%(~3.6배 낮음), lead-time 35.9h vs 38.1h(근접).

### 진단 / 교훈
두 수정이 **각각 예측한 효과를 정확히** 냈다. 진동 fix → motor가 suction 진동(+45%) 검출 회복(0.08→발화),
격리 → bearing_wear의 zone_drip 오탐·suction의 nutrient/zone 오탐 제거. "측정 도구(coupling_validate)를 먼저
만들고 그 고정 오라클로 변경을 잰다"는 방법론이 결함 발견(Phase H)→수정→재측정 confirm으로 한 바퀴 돌았다.

### 수정 (확정 채택)
DOMAIN_ISOLATION=1 + 진동 fix 모델을 정본으로. 포트폴리오 발화: "막힘률 10→2%"(미지지) 대신
"단일센서 baseline과 동일 검출(6/6)하며 오탐(FAR) 5%→1.4%(~3.6배↓), 평균 35.9h 전 사전감지."

### 남은 과제
- 격리 잔여: zone_drip union에 pressure_diff·flow_diff·rpm_stability_index 잔존(타 도메인 mandatory가 아니라 격리 미포착). 필요 시 도메인 sensor 네임스페이스로 확장.
- hydraulic(`hydraulic_power_kw`·`filter_delta_p_kpa`)·nutrient(`mix_temp_c`) 누락 센서 점검(같은 model_cols 패턴).
- iso ON/OFF 정량 F1 비교는 evaluate_test_metrics로 별도(현재는 coupling_validate 검출지도로 확인).

## Phase J — 캐노니컬 데이터 전환(dabin→jun v5) 재학습: 현실성↑·motor FAR 회귀 (2026-06-07, 정직 측정)

### 가설
dabin 정상셋은 센서가 인위적으로 ~1.0 상관(suction↔discharge 등)이라 다중공선성 필터가 도메인
피처를 깎아내고 §7 관계피처도 무의미했다. 공공앵커+독립 AR(1) 성분 기반 jun 정상셋으로 바꾸면
raw 센서가 필터를 통과하고 관계피처가 자연 선택돼, 데이터 현실성과 함께 attribution·FAR이 개선될 것.

### 시도
`DOMAIN_ISOLATION=1 python src/train.py` on smartfarm_normal_train_v5.csv(129,599행·90일).
run `2026-06-07_110219__6965158`(라벨 retrain-rel-features는 PHASE 미지정 기본값). faulty_testset_v1을
jun base에서 재생성 후 측정도구 4종 + 도메인별 FAR 분해 재실행.

### 관측
- 검출(baseline_blockage): clog 6/6, 막힘률 0%, AE lead-time 47.5h vs baseline 45.5h.
  (lead-time은 dabin 35.9h와 직접 비교 불가 — 에피소드 배치가 다른 데이터셋.)
- attribution(coupling_validate): 4 root 모두 검출 O. 단 Phase I의 깨끗함이 일부 후퇴 —
  bearing_wear에 hydraulic 0.43 오탐 재등장, nutrient_imbalance에 motor 0.86 오탐.
- **FAR 회귀**: AE overall 6.5%(>baseline 3.2%, >5% 목표). 도메인별 motor **6.3%(주범)**·
  hydraulic 2.7%·nutrient 1.1%·zone_drip 1.1%. Phase I는 1.4%였음.
- 기동 band B: 정상기동 FAR 1.3%, 비정상 ≥1.2배 recall 100%(양호, 재확인).
- 집중도 판별 깨짐: clog 0.65 > sensor drift/spike 0.40(역전). dabin의 '단일 0.88~0.92 vs 다중 0.45'
  분리 재현 실패 — hydraulic F=15 축소 + 단일 드리프트가 파생피처(pressure_flow_ratio·system_resistance)로 퍼짐.
- §7 피처: vibration_per_load(motor)·transpiration_demand(hydraulic) 여전히 Step2에서 드롭 →
  SENSOR_MANDATORY 강제주입으로만 생존. leaching_ratio(nutrient)만 SHAP 합집합에 자연 포함.

### 진단 / 교훈
데이터 현실성은 올랐으나(독립 AR(1)·공공앵커), 그 현실적 노이즈가 motor 재구성오차 분포를 넓혀
sigma threshold(caut 0.0021)가 6.3% FAR을 냈다. motor에 강제주입된 노이즈성 비율피처
(vibration_per_load·temp_slope_c_per_s·bearing_thermal_margin)가 1차 용의자. §7 관계피처가
'자연 선택'되지 못하고 강제주입에 의존한 것은, 그것이 판별력이 아니라 노이즈로 작용했을 신호
(사용자 우려: 필터링되면 곱하거나 공식 변경). 집중도 판별식은 피처구성 의존적이라 데이터셋 간 일반화 안 됨.

### 수정 (다음 회차 방향 — 미확정, 사용자 결정 대기)
motor FAR을 5%↓로 되돌리는 게 선결. 후보: (i) motor threshold를 percentile(목표 FAR 직접 타게팅)로
또는 sigma 배수 상향, (ii) motor 강제주입 노이즈피처를 attribution 기여 없으면 제외, (iii) 둘 병행.
확정 전까지 포트폴리오 정직화(D)는 Phase I 수치(FAR 1.4%) 유지하되 'jun 데이터 재측정 진행 중' 단서.

### 남은 과제
- motor FAR 회귀 수정 → 재학습 → coupling_validate·baseline_blockage 재측정으로 Phase I 대비 회복 확인.
- §7 관계피처 판별력 검증 또는 재설계(C 화학·농학 트랙과 통합 검토).
- 집중도 판별을 포트폴리오에서 쓸지 재검토(jun에서 비재현).

## Phase K — 교차도메인 외래 피처 채점 제외(조건부 마스크): FAR·attribution 동시 회복 (2026-06-07, 성공)

### 가설
Phase J의 motor 과발화(FAR 6.0%·attribution 오탐)의 뿌리는, 어느 SENSOR_MANDATORY에도 없는
자유 파생피처 pressure_diff·flow_diff가 SHAP으로 motor 등에 섞여 채점을 오염시킨 것이다.
이들을 '입력 유지 + 채점 제외'(조건부 마스크)하면 FAR과 attribution 오탐이 함께 풀린다.

### 시도
(1) eval==serve 정합 선결: evaluate_test_metrics가 전체 피처로 MSE를 내던 것을 scoring_features
기반으로 수정(이게 없으면 채점 제외가 측정에 안 잡힘). (2) feature_engineering.foreign_scoring_features
(DERIVED_FEATURE_OWNER: pressure_diff·flow_diff→hydraulic, ENVIRONMENT_CONTEXT: air_temp_c) +
train.py 연동. (3) DOMAIN_ISOLATION=1 재학습 run `..205502..`. 채점 제외 로그 확인: motor
[flow_diff,pressure_diff] 11/17, nutrient [air_temp_c,pressure_diff] 9/15, zone_drip [pressure_diff] 5/10.

### 관측 (정합 eval 기준, faulty_testset 정상 윈도우)
| 지표 | Phase J(누설) | Phase K(채점제외) |
|---|---|---|
| motor FAR | 6.0% | **5.1%** |
| nutrient FAR | 2.1% | **0.9%** |
| zone_drip FAR | 2.7% | **0.3%** |
| overall FAR | 6.2% | **5.4%** |
| bearing_wear 귀인 | motor + hydraulic 0.43(오탐) | **motor만**(hydraulic 0.07) |
| nutrient_imb 귀인 | nutrient + motor 0.86(오탐) | **nutrient만**(motor 0.21) |
- 검출 유지: clog 6/6, 막힘률 0%, AE lead-time 47.3h(같은 데이터 baseline 45.5h). 4 root 모두 검출 O.

### 진단 / 교훈
자유 파생피처 누설이 **FAR 상승과 attribution 오탐의 공통 뿌리**였음이 확정됐다 — 채점에서만
빼니(입력·교차상관은 보존) 둘 다 해소. DOMAIN_ISOLATION(mandatory만 격리)의 사각지대를 조건부
마스크가 메웠다. 'eval==serve 정합'이 선결조건이었다(없으면 수정이 측정에 안 잡힘) — 측정도구가
서빙과 같은 점수식을 써야 변경을 정직하게 잰다(Phase B 컨텍스트 제외의 한 단계 위 일반화).

### 수정 (확정 채택)
조건부 마스크(foreign_scoring_features) + eval 정합을 정본으로. 포트폴리오 논거: '도메인 경계를
입력이 아니라 채점에서 지켜(조건부 AE) 헛알람·오귀인을 동시에 줄였다'(근거: Conditional Anomaly
Detection, MODELING §5-2-1).

### 남은 과제
- motor FAR 5.1%: 목표(≤5%) 경계이나 baseline(3.2%) 초과. 잔여는 유지 선택한 노이즈 슬로프
  (rpm_slope·temp_slope). 옵션: motor만 threshold percentile화(사용자 '둘 다'의 (나) 단계) — 선택 대기.
- jun 데이터는 현실적 노이즈라 dabin Phase I(FAR 1.4%) 수준 복귀는 구조적으로 어려움(정직 서술).

## Phase L — robust 슬로프(rpm_slope·temp_slope): motor FAR 회귀 종결 (2026-06-07, 성공)

### 가설
Phase K 잔여 motor FAR 5.1%의 주범은 유지 선택한 노이즈 슬로프다. 두 슬로프가 원시 1차
차분(x.diff()/dt)이라 끝점 2개만 써서 분 단위 센서 jitter를 증폭한다. 트레일링 이동평균으로
다듬은 뒤 변화율을 내면(robust 슬로프) 추세는 보존하며 노이즈만 줄여 FAR이 더 내려간다.

### 시도
preprocessing의 temp_slope_c_per_s·rpm_slope를 `x.rolling(5,min_periods=1).mean().diff()/dt`로
교체(인과적 5분 평활). 재학습 전 검증: 시간대 구조 제거 후 잔차(랜덤)노이즈 std temp -72%·rpm -55%,
60분 +6°C 과열 모사에서 평균 슬로프 보존(원시 2.53e-3≈robust 2.55e-3). 재학습 run `..212812..`.

### 관측 (정합 eval)
| 지표 | Phase K | Phase L |
|---|---|---|
| motor FAR | 5.1% | **2.7%**(baseline 3.2% 미만) |
| overall FAR | 5.4% | **4.2%** |
| 검출/막힘률 | 6/6·0% | 6/6·0% |
| lead-time | 47.3h | 45.4h(-1.9h) |
- 부수효과: 슬로프 평활로 motor 점수 분포 skew 7.42→8.30(cutoff 8.0 초과) → threshold method가
  sigma→**percentile**로 자동 전환(목표 분위 직접 타게팅). 사용자 '둘 다'의 (나)가 자동 충족된 셈.
- attribution 유지(4 root 모두 O). 단 nutrient_imbalance에서 motor 경계(~0.3) 잔존(사소).

### 진단 / 교훈
원시 1차 차분은 어떤 신호든 고주파 노이즈를 증폭한다(수학적). robust 슬로프로 잔차노이즈를
72%/55% 줄이니 motor FAR이 절반 가까이(5.1→2.7%) 떨어지고 baseline 아래로 내려갔다. 평활 대가로
lead-time 1.9h 감소(45.4h)는 허용 범위. '증상(threshold)이 아니라 원인(피처 노이즈)을 고친다'가
감지력을 거의 안 깎고 FAR을 더 낮췄다.

### 수정 (확정 채택)
robust 슬로프를 정본으로. motor FAR 회귀(Phase J 6.0%→Phase L 2.7%) 종결. 포트폴리오: 도메인
FAR 모두 baseline(3.2%) 미만(motor 2.7·hydraulic 1.9·nutrient 0.9·zone 0.3), overall 4.2%는
4개 도메인 OR이라 baseline(13센서 OR 3.2%)보다 약간 높음 — 정직 서술(이점은 도메인 귀인+lead-time).

### 남은 과제
- 데이터 현실성(근본): motor_temp가 실제 열적 관성보다 분단위 jitter가 큼(AR(1) 독립노이즈에
  thermal low-pass 부재). data_gen에 1차 열지연을 주면 원시 슬로프도 자연히 매끈 — 데이터 현실화
  트랙 후보(선택). robust 슬로프와 상호보완.
- overall 4.2% 추가 인하(예: 연속 N윈도우 디바운싱/2도메인 동시) 여부는 선택.

## Phase M — 데이터 현실화 v6: Na축적·EC삼투·열지연 (2026-06-07, 데이터 변경·측정 대기)

### 가설
baseline·motor FAR이 확정됐으니(J~L) data_gen의 화학·열 충실성을 올리면 nutrient/zone 도메인이
의미를 갖고, 슬로프 jitter의 데이터 레벨 근본도 잡힌다. 검증 공식만 사용(지어내지 않음).

### 시도 (data_gen_jun 개정, 검증공식 + 출처)
- C5 열적 관성: motor/bearing_temp를 lumped capacitance(dT/dt=(T_target−T)/τ, τ=15분) 이산 IIR(EWM)로
  평활 + 측정노이즈 분리. → motor_temp 원시 슬로프 std 2.1e-2→3.6e-3(-83%).
- C1 Na 축적: 순환식 질량수지 톱니(0.15→1.45 mmol/L, 딸기 임계 1.5 미만, 12일 교체). Na→mix/drain EC↑.
  출처 Neocleous 2017·WUR 403810. 신규 raw 컬럼 na_accumulation_mmol_l.
- C2 EC→삼투→흡수: Ψ=-0.036·EC(Handbook 60). 고EC서 흡수↓(Na>0.8서 0~35%) → 배지 수분↑·EC↑.
  신규 raw 컬럼 osmotic_potential_mpa. na/osmotic은 raw만(EC와 collinear라 model_cols 제외).
- 검증: na 톱니 임계 미만, osmotic=-0.036·EC 검산 일치, na↔mix_ec +0.89·na↔배지EC +0.44(디커플 작동),
  mix↔drain +0.26(신규 collinearity 없음), bearing↔motor 0.79→0.83(<0.85). 미러 data_gen은 dead.

### 관측 / 진단 / 수정 (측정 대기)
data_gen만 바뀜 — 효과는 사용자가 정상셋 regen(`python src/data_gen_jun.py`) + faulty_testset 재생성
+ 재학습 후 측정해야 확정. 기대: nutrient/zone가 EC-삼투-배지 패턴을 학습해 의미↑, FAR·attribution
회귀 없어야(coupling_validate로 확인). C3 pH-수온·C4 VPD는 후속.
