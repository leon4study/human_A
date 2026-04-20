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

## 수정 적용 요약

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
