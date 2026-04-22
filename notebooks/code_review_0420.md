# Critical Code Review — model_middle_0420.ipynb
> 검토 일자: 2026-04-20  
> 검토 범위: 전체 노트북 셀 + `src/preprocessing.py`, `src/feature_selection.py`

---

## 요약

| 등급 | 건수 | 내용 |
|------|------|------|
| 🔴 CRASH | 3 | 실행 시 즉시 에러 발생 |
| 🟠 WRONG | 4 | 실행은 되지만 결과가 잘못됨 |
| 🟡 ARCH  | 3 | 모델 성능에 직접 영향을 주는 구조적 결함 |

---

## 🔴 CRASH — 실행하면 즉시 죽는 버그

### Bug #1 — `__file__` 은 노트북에 없다 (Cell 27, 31)

**문제**  
`Cell 27 (save_experiment_to_csv)` 와 `Cell 31 (train_and_save_model)` 이 모두:
```python
current_dir = os.path.dirname(os.path.abspath(__file__))
```
를 사용한다. `__file__` 은 `.py` 스크립트에만 존재하는 변수다.  
Jupyter에서 실행하면 → `NameError: name '__file__' is not defined`

**수정**  
하드코딩된 `project_root` 로 교체:
```python
# 수정 전
current_dir = os.path.dirname(os.path.abspath(__file__))
save_dir = os.path.join(os.path.dirname(current_dir), "models")

# 수정 후
save_dir = os.path.join("/Users/jun/GitStudy/human_A", "models")
```
> ✅ **Fix #1, #2 적용 완료**

---

### Bug #2 — `rpm_stability_index` 는 `df_clean` 에 없다 (Cell 15, 32)

**문제**  
`subsystem_targets["motor"]` 에서 `rpm_stability_index` 를 SHAP 타겟으로 지정:
```python
"rpm_stability_index": ["pump_rpm"],
```
하지만 Cell 15의 `create_modeling_features` 는 `model_cols` 필터링을 통해
`df_model` 을 반환하는데, `rpm_stability_index` 가 `model_cols` 에 없었다.

결과: 윈도우 집계 → `df_clean` → `y = df["rpm_stability_index"]` → **KeyError**

**수정**  
Cell 15의 `model_cols` 에 추가:
```python
"rpm_slope",
"rpm_acc",
"rpm_stability_index",   # ← 추가
```
> ✅ **Fix #6 적용 완료**

---

### Bug #3 (기존 수정 확인) — `preprocessing.py` 빈 문자열 KeyError

**문제 (이미 수정됨)**  
`src/preprocessing.py` 109번 줄:
```python
df_feat['pump_on'] = df_feat[""]   # ← KeyError: ''
```

**수정 완료 (이전 세션)**  
해당 줄 삭제. `pump_on` 은 raw CSV에 이미 존재.

---

## 🟠 WRONG — 실행은 되지만 결과가 틀린 버그

### Bug #4 — Cell 32 에서 `df_agg` 가 사실은 `df_interpret` 다

**문제**  
`run_feature_selection_experiment` 의 반환 시그니처:
```python
return robust_features, X_train_ae, df_interpret, shap_results
```
Cell 32 에서 이를 받는 코드:
```python
robust_features, X_train_ae, df_agg, _ = run_feature_selection_experiment(...)
```
`df_agg` 라고 불렀지만 실제 내용은 `df_interpret` (해석용 피처 DataFrame).

이후 VIP 주입 로직:
```python
if col not in X_train_ae.columns and col in df_agg.columns:
    time_features = df_agg[missing_vips]
```
`df_interpret` 에는 `time_sin`, `time_cos` 가 없으므로 VIP 주입이 **항상 무음으로 스킵**된다.

**수정**  
변수명을 `df_interpret_result` 로 교체:
```python
robust_features, X_train_ae, df_interpret_result, _ = run_feature_selection_experiment(...)
```
> ✅ **Fix #3 적용 완료**  
> ⚠️ 단, `df_interpret_result` 에 `time_sin`/`time_cos` 를 포함시키려면 Cell 20의  
> `extract_interpretation_features` 함수에 해당 컬럼 복사 로직을 추가해야 한다.

---

### Bug #5 — `pressure_flow_ratio` 공식이 두 셀에서 다르다

**문제**  
같은 컬럼 이름, 다른 공식:
```python
# Cell 15 extract_interpretation_features
df_interpret["pressure_flow_ratio"] = (discharge - suction) / (flow + eps)   # 차압 / 유량

# Cell 20 extract_interpretation_features
df_interpret["pressure_flow_ratio"] = discharge / (flow + eps)                 # 토출압 / 유량
```
Cell 20이 마지막으로 실행되므로 Cell 15 정의는 묻힌다.  
어느 쪽 공식이 맞는지 의도를 확인하고 하나로 통일해야 한다.

**수정 방향**  
`dp_per_flow` (차압/유량) 와 `pressure_flow_ratio` (토출압/유량) 을 구분하는 Cell 20 방식이 더 명시적이므로 Cell 15 정의를 Cell 20과 맞추거나 제거.

---

### Bug #6 — 함수 섀도잉: 두 셀에서 같은 함수를 정의

**문제**  
| 함수 | 정의 위치 |
|------|-----------|
| `create_modeling_features` | Cell 10 (단일 df 반환) / Cell 15 (tuple 반환) |
| `extract_interpretation_features` | Cell 15 / Cell 20 |

마지막에 실행된 셀이 이전 정의를 덮어씀.  
셀 실행 순서가 바뀌면 반환 타입이 달라져 즉시 크래시 또는 조용한 버그 발생.

**수정 방향**  
- Cell 10과 Cell 15 중 하나를 선택해 나머지를 삭제 (현재는 Cell 15가 '최신' 버전)
- Cell 15와 Cell 20의 `extract_interpretation_features` 도 동일하게 정리

---

### Bug #7 — `fillna(method='bfill')` deprecated (Cell 22)

**문제**  
```python
df_clean.fillna(method='bfill', inplace=True)   # pandas 2.0+ FutureWarning → ValueError
```

**수정**  
```python
df_clean.bfill(inplace=True)
```
> ✅ **Fix #5 적용 완료**

---

## 🟡 ARCH — 모델 품질에 직접 영향을 주는 구조적 결함

### Bug #8 — AutoEncoder 병목 크기가 중간 레이어보다 크다 (Cell 30)

**문제**  
```python
bottleneck_size = max(4, input_dim // 2)
```
예) `input_dim = 36` 이면 `bottleneck_size = 18`

실제 네트워크 구조:
```
Input(36) → Dense(32) → Dense(16) → Dense(18) ← 병목이 이전 레이어(16)보다 크다!
           → Dense(16) → Dense(32) → Output(36)
```
병목(18) > 이전 레이어(16) → 정보가 압축되지 않고 오히려 팽창.  
AutoEncoder 의 핵심인 "압축 → 재구성" 구조가 깨짐.  
이상 탐지 성능이 크게 저하될 수 있다.

**수정**  
```python
# 수정 전
bottleneck_size = max(4, input_dim // 2)

# 수정 후
bottleneck_size = max(4, input_dim // 4)
```
> ✅ **Fix #4 적용 완료**

---

### Bug #9 — K-Means n_clusters 퇴화 (Cell 23)

**문제**  
```python
n_clusters = min(300, len(X))
```
만약 `len(X) < 300` 이면, `n_clusters = len(X)` →  
클러스터 수 = 데이터 수 → 각 포인트가 자기 자신이 군집 중심 → 의미 없는 압축.

**수정**  
```python
n_clusters = min(300, max(20, len(X) // 10))
```
최소 20개, 최대 데이터의 10% or 300개 중 작은 값으로 제한.

---

### Bug #10 — EDA용 데이터와 학습용 데이터가 다르다 (Cell 5 vs Cell 32)

**문제**  
```python
# Cell 5 (EDA)
pd.read_csv("...refined_smoother_m2_m3.csv")

# Cell 32 (학습)
pd.read_csv("...clog_focus_v2_stronger_1min.csv")
```
두 파일의 컬럼 스키마가 다를 수 있다.  
Cell 7~8의 `.info()`, `.describe()` 결과가 실제 학습 데이터를 반영하지 않음.  
`target_dict` 에 있는 컬럼이 학습 파일에 없으면 런타임 KeyError 가능.

**수정 방향**  
Cell 5를 Cell 32와 같은 학습 파일로 통일하거나, EDA 섹션과 학습 섹션을 명확히 분리.

---

## 1차 리뷰 수정 적용 요약

| Fix # | 대상 | 내용 | 상태 |
|-------|------|------|------|
| #1 | Cell 31 | `__file__` → hardcoded path | ✅ 완료 |
| #2 | Cell 27 | `__file__` → hardcoded path | ✅ 완료 |
| #3 | Cell 32 | `df_agg` → `df_interpret_result` 명칭 교정 | ✅ 완료 |
| #4 | Cell 30 | bottleneck `input_dim // 2` → `input_dim // 4` | ✅ 완료 |
| #5 | Cell 22 | `fillna(method='bfill')` → `.bfill()` | ✅ 완료 |
| #6 | Cell 15 | `rpm_stability_index` model_cols 추가 | ✅ 완료 |
| — | Bug #5 | `pressure_flow_ratio` 공식 통일 | ⚠️ 수동 판단 필요 |
| — | Bug #6 | 중복 함수 정의 정리 | ⚠️ 수동 정리 필요 |
| — | Bug #9 | n_clusters 퇴화 방지 | ⚠️ 적용 전 데이터 크기 확인 후 결정 |
| — | Bug #10 | 데이터 파일 통일 | ⚠️ 수동 판단 필요 |

---

# 2차 Critical Code Review — model_middle_0420.ipynb
> 검토 일자: 2026-04-20 (2차)  
> 검토 범위: Cell 18, 20, 21, 22, 24, 25, 26, 32 (파이프라인 개편 후 전체)

---

## 요약

| 등급 | 건수 | 내용 |
|------|------|------|
| 🔴 CRASH | 2 | 실행 시 즉시 에러 발생 |
| 🟠 WRONG | 4 | 실행은 되지만 결과가 잘못됨 |
| 🟡 ARCH  | 3 | 모델 성능에 직접 영향을 주는 구조적 결함 |

---

## 🔴 CRASH — 실행하면 즉시 죽는 버그

### Bug #11 — Tumbling 브랜치에 `df_agg` 정의 누락 (Cell 18)

**문제**  
`aggregate_time_window` 함수에서 `window_method == "tumbling"` 분기가:
```python
df.resample(window_size).agg(agg_dict)   # 결과를 df_agg 에 저장하지 않음
```
반환값이 버려지고 `df_agg` 는 미정의 상태 → `return df_agg, df_interpret` 에서 `NameError`.

**수정**  
```python
# 수정 전
df.resample(window_size).agg(agg_dict)

# 수정 후
df_agg = df.resample(window_size).agg(agg_dict)
```
> ✅ **Fix #7 적용 완료**

---

### Bug #12 — `phase_cols` 가 불완전해 KeyError 또는 silent drop (Cell 18)

**문제**  
`aggregate_time_window` 의 `phase_cols` 리스트가:
```python
phase_cols = ["pump_on", "minutes_since_startup", "is_startup_phase"]
```
로만 정의되어 있었음. `pump_start_event`, `pump_stop_event`, `minutes_since_shutdown`, `is_off_phase` 가 누락.  
해당 컬럼들이 원본 df 에 있어도 집계 결과에서 조용히 사라짐.

**수정**  
```python
phase_cols = [
    "pump_on", "minutes_since_startup", "is_startup_phase",
    "pump_start_event", "pump_stop_event", "minutes_since_shutdown", "is_off_phase"
]
```
각 컬럼 접근 시 `if col in df.columns` 가드 추가.  
> ✅ **Fix #8 적용 완료**

---

## 🟠 WRONG — 실행은 되지만 결과가 틀린 버그

### Bug #13 — `time_sin`/`time_cos` 가 `df_interpret` 에 없어 VIP 주입이 항상 스킵 (Cell 20)

**문제**  
Cell 32 의 VIP 보완 로직:
```python
if col not in X_train_ae.columns and col in df_interpret_result.columns:
    time_features = df_interpret_result[missing_vips]
```
`df_interpret` 에 `time_sin`, `time_cos` 가 없으면 조건이 항상 False → 주입 무음 스킵.  
`extract_interpretation_features` 가 이 컬럼들을 복사하지 않았던 것이 원인.

**수정**  
`extract_interpretation_features` 상단에 추가:
```python
for col in ["time_sin", "time_cos"]:
    if col in df_agg.columns:
        df_interpret[col] = df_agg[col]
```
> ✅ **Fix #9 적용 완료**

---

### Bug #14 — `robust_features` 가 빈 리스트일 때 빈 DataFrame으로 조용히 진행 (Cell 25)

**문제**  
SHAP 앙상블 투표 결과 모든 피처가 단일 타겟에서만 선택되면 `robust_features = []`.  
`df_clean[[]]` → 빈 DataFrame → AutoEncoder 학습 시 `input_dim = 0` → Keras 에러 또는 무의미한 모델.

**수정**  
```python
selected = ensemble_lists["robust"] if ensemble_lists["robust"] else ensemble_lists["union"]
if not selected:
    raise ValueError("SHAP 앙상블 결과 선택 피처가 0개입니다. target_dict 또는 top_ratio 를 확인하세요.")
X_train_ae = df_clean[selected].copy()
```
> ✅ **Fix #10 적용 완료**

---

### Bug #15 — `zone_drip` 두 번째 타겟이 `zone1_resistance` 로 중복 (Cell 32)

**문제**  
```python
"zone_drip": {
    "zone1_moisture_response_pct": [...],
    "zone1_resistance": [...],   # ← hydraulic 도메인과 중복, 의미도 불명확
}
```
`zone1_resistance` 는 이미 hydraulic 도메인에서 선정한 타겟과 겹쳤고,  
zone_drip 도메인의 핵심 지표인 EC 누적은 빠져 있었음.

**수정**  
```python
"zone_drip": {
    "zone1_moisture_response_pct": ["zone1_substrate_moisture_pct"],
    "zone1_ec_accumulation": ["zone1_substrate_ec_ds_m", "mix_ec_ds_m"],
}
```
> ✅ **Fix #11 적용 완료**

---

### Bug #16 — `run_shap_ensemble` 의 `all_features` 변수 사용 안 됨 (Cell 24)

**문제**  
```python
all_features = df.columns.tolist()   # 이후 한 번도 참조되지 않는 죽은 코드
```
실행 오류는 아니지만 코드 리더를 혼란에 빠뜨리고 "이 변수로 필터링하는 게 맞나?" 라는 오해 유발.

**수정**  
해당 줄 삭제.  
> ✅ **Fix #12 적용 완료**

---

## 🟡 ARCH — 모델 품질에 직접 영향을 주는 구조적 결함

### Bug #17 — `pressure_flow_ratio` 공식이 Cell 20 에서도 불명확 (Cell 20)

**문제**  
Cell 20 `extract_interpretation_features`:
```python
df_interpret["pressure_flow_ratio"] = discharge / (flow + eps)   # 토출압/유량
```
물리적으로 의미 있는 값은 **차압(differential pressure) / 유량** 이지, 토출압/유량이 아님.  
차압은 `discharge - suction` 으로 계산 가능하며 `pressure_diff` 컬럼이 이미 존재.

**수정 방향**  
```python
# 추천: dp_per_flow (차압/유량) 로 변수명 변경 + 공식 수정
df_interpret["dp_per_flow"] = (discharge - suction) / (flow + eps)
```
또는 두 개를 구분해서 유지:
```python
df_interpret["dp_per_flow"] = (discharge - suction) / (flow + eps)    # 수력 저항 지표
df_interpret["pressure_flow_ratio"] = discharge / (flow + eps)          # 토출 효율 지표
```
> ⚠️ **수동 판단 필요** — 물리적 의도 확인 후 공식 통일

---

### Bug #18 — 구버전 `step2_clean_and_drop_collinear` 가 잔존 (Cell 22)

**문제**  
`step2_clean_and_drop_collinear_dynamic` 로 교체한 이후에도 구버전 함수가 셀 내에 그대로 남아 있음.  
셀 실행 순서가 달라지거나 누군가 구버전을 임포트하면 whitelist/protected_cols 없이 동작.

**수정 방향**  
Cell 22 에서 구버전 함수 정의 블록 삭제, `step2_clean_and_drop_collinear_dynamic` 만 유지.  
> ⚠️ **수동 정리 필요**

---

### Bug #19 — MSE 이상 탐지 임계값이 학습 데이터로만 산출 (Cell 32~33)

**문제**  
```python
threshold = np.percentile(train_mse, 95)
```
학습 데이터의 MSE 분포로 임계값을 정하면 정상 구간이 과적합된 기준이 만들어짐.  
실제 운영 중 발생하는 미세 이상은 학습 데이터 MSE 범위 안에 있어 탐지 불가.

**수정 방향**  
학습 셋과 분리된 **정상 검증 셋(holdout)** 의 MSE 분포로 임계값 산출:
```python
# 학습 80% / 검증 20% 분리 후
val_mse = compute_reconstruction_error(model, X_val)
threshold = np.percentile(val_mse, 95)
```
> ⚠️ **수동 판단 필요** — 데이터셋 분리 전략 결정 후 적용

---

## 2차 리뷰 수정 적용 요약

| Fix # | 대상 | 내용 | 상태 |
|-------|------|------|------|
| #7  | Cell 18 | Tumbling 브랜치 `df_agg =` 누락 추가 | ✅ 완료 |
| #8  | Cell 18 | `phase_cols` 확장 + 컬럼 존재 가드 | ✅ 완료 |
| #9  | Cell 20 | `time_sin`/`time_cos` → `df_interpret` 복사 추가 | ✅ 완료 |
| #10 | Cell 25 | `robust_features` 빈 경우 union fallback + ValueError | ✅ 완료 |
| #11 | Cell 32 | `zone_drip` 2번째 타겟 → `zone1_ec_accumulation` | ✅ 완료 |
| #12 | Cell 24 | 미사용 `all_features` 변수 삭제 | ✅ 완료 |
| —   | Bug #17 | `pressure_flow_ratio` 공식 통일 | ⚠️ 수동 판단 필요 |
| —   | Bug #18 | 구버전 `step2_clean_and_drop_collinear` 삭제 | ⚠️ 수동 정리 필요 |
| —   | Bug #19 | MSE 임계값을 holdout 검증 셋 기준으로 재산출 | ⚠️ 데이터 분리 전략 결정 후 적용 |
