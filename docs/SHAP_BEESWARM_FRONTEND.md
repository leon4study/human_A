# SHAP Beeswarm 프론트 연동 가이드

모델 4종(motor / hydraulic / nutrient / zone_drip) 각각에 대해 SHAP beeswarm 그래프를 프론트에서 렌더링하기 위한 데이터 계약 · 렌더 방법을 정리한다.

---

## 1. 배경 — SHAP은 "정적 아티팩트"다

- SHAP 값은 **학습 시점에 1회만 계산**된다 ([src/feature_selection.py:215-225](../src/feature_selection.py#L215-L225)).
- 추론 입력이 바뀌어도 값은 달라지지 않는다 → **`/predict` 응답에 매번 실어 보낼 필요가 없다.**
- 따라서 전용 엔드포인트 `GET /shap-summary`를 하나 두고, 프론트는 **페이지 진입 시 1회만 호출 후 캐시**한다.

현재 상태:
- feature_selection 단계에서 `shap_values`, `x_background`는 계산되고 있으나
- `train.py:278`에서 `_`로 버려지고 있어 디스크에 저장되지 않음
- 이를 `models/{domain}_shap.json`으로 아티팩트화하는 것이 선결 작업

---

## 2. API 스펙

### 2-1. 엔드포인트
```
GET /shap-summary
```
- 요청 파라미터 없음
- 응답 크기: 대략 **0.5 ~ 2 MB** (4 도메인 × 2 타깃 × 200 sample × N feature × 2 float 배열). Gzip 권장.

### 2-2. 응답 JSON

```jsonc
{
  "motor": {
    "targets": {
      "motor_current_a": {
        "features":       ["pressure_trend_10", "pump_on", "time_sin", "..."],
        "mean_abs_shap":  [0.421, 0.318, 0.244, "..."],
        "feature_order":  ["pressure_trend_10", "pump_on", "time_sin", "..."],
        "shap_values":    [[ 0.12, -0.08, 0.03, "..."], ["..."]],
        "feature_values": [[ 1.23,  0.00, 0.88, "..."], ["..."]]
      },
      "rpm_stability_index": { /* 동일 구조 */ }
    },
    "n_samples":   200,
    "n_features":  40,
    "computed_at": "2026-04-16T01:29:07Z"
  },
  "hydraulic": { "...": "..." },
  "nutrient":  { "...": "..." },
  "zone_drip": { "...": "..." }
}
```

### 2-3. 필드 설명

| 필드 | shape / type | 역할 |
|---|---|---|
| `features` | `string[N]` | 피처 이름 — 2D 배열의 **열 순서 정의**. 모든 2D 배열이 이 순서를 따름. |
| `mean_abs_shap` | `float[N]` | `\|SHAP\|.mean(axis=0)` — 전역 중요도(바 그래프) |
| `feature_order` | `string[N]` | `mean_abs_shap` 내림차순으로 정렬된 피처 이름 — **beeswarm Y축 top→bottom** |
| `shap_values` | `float[S][N]` | **X축** — 점 하나 = 1 sample의 SHAP value (부호 유지) |
| `feature_values` | `float[S][N]` | **색상** — 점 하나의 raw 센서 값. 피처별 min/max 정규화 후 파랑(Low)↔빨강(High)으로 매핑 |
| `n_samples` (S) | int | K-Means 압축 배경 샘플 수 (현재 200) |
| `n_features` (N) | int | 해당 타깃의 SHAP 입력 피처 수 |
| `computed_at` | ISO8601 | 모델 재학습 시 갱신 |

**S는 도메인·타깃별로 같다** (K-Means 클러스터 수 = 200).
**N은 타깃마다 다를 수 있다** (타깃에 따라 leakage 방지 drop 컬럼이 다르기 때문, [feature_selection.py:206-207](../src/feature_selection.py#L206-L207)).

### 2-4. 타깃 리스트 (도메인 × 타깃)

| 도메인 | 타깃 1 | 타깃 2 |
|---|---|---|
| motor | `motor_current_a` | `rpm_stability_index` |
| hydraulic | `zone1_resistance` | `differential_pressure_kpa` |
| nutrient | `pid_error_ec` | `salt_accumulation_delta` |
| zone_drip | `zone1_moisture_response_pct` | `zone1_ec_accumulation` |

→ **도메인당 beeswarm 2개** 또는 프론트에서 드롭다운으로 선택.

---

## 3. 프론트 렌더링 가이드

### 3-1. 기본 알고리즘 (beeswarm)

```
for each target:
    Y축  = feature_order            (top N개만 표시, 나머지는 "Sum of X other features"로 합침)
    for each feature f in feature_order[:top_n]:
        for each sample s in [0..S):
            x = shap_values[s][feature_index(f)]
            y = f 의 y-row (jitter로 세로 분산)
            color = colorMap(feature_values[s][feature_index(f)], f의 min~max 범위)
            draw dot (x, y, color)
    draw vertical line at x=0
```

### 3-2. Y축 정렬 규칙
- `feature_order`를 그대로 사용 (mean |SHAP| desc 이미 정렬됨)
- Top-K(예: 10) 표시 후 나머지는 합계 바 `Sum of (N-K) other features`로 표시
  - 해당 행의 dot들은 `shap_values[s][remaining_features].sum(axis=1)` 으로 합산

### 3-3. 색상 매핑
- 피처마다 스케일이 다르므로 **열 단위 정규화** 필수:
  ```js
  const col = feature_values.map(row => row[fIdx]);
  const min = Math.min(...col), max = Math.max(...col);
  const norm = (v) => (v - min) / (max - min);  // [0, 1]
  const color = d3.interpolateRdBu(1 - norm(v));  // 0=blue(low), 1=red(high)
  ```
- NaN/undefined 방어: 모두 같은 값이면 보라색 고정(회색 대체 가능)

### 3-4. X축
- 대칭: `xMax = max(|shap_values|)` 사용, `[-xMax, xMax]` 범위 + 0에 세로 기준선
- 라벨: `"SHAP value (impact on model output)"`
- 도메인 타깃별로 스케일이 매우 다르므로 **타깃마다 독립 x축 사용** 권장 (4개 shared axis 쓰면 작은 타깃이 찌그러짐)

### 3-5. 점 렌더링 (jitter)
- 같은 feature row 안에서 y 좌표 겹침 방지:
  - **histogram binning**: x를 20~40개 bin으로 나눠 같은 bin에 속한 점들은 위아래로 쌓기 (원본 `shap.summary_plot` 방식)
  - 또는 **random jitter**: `y + uniform(-0.4, 0.4)` (간단)
- 점 크기: 4~6 px, 알파: 0.5~0.7

### 3-6. 추천 라이브러리

| 선택지 | 장점 | 단점 |
|---|---|---|
| **Plotly.js** (`scattergl`) | WebGL 렌더링, 200 sample × 10 feature = 2K 점 여유, 호버 툴팁 기본 제공 | 번들 크기 큼 |
| **ECharts** | scatter 커스텀 렌더 강력, beeswarm 예제 공식 있음 | jitter는 수동 계산 필요 |
| **D3.js (raw)** | 완전 커스터마이즈 | 구현 공수 큼 |
| **visx (airbnb)** | React 친화, 가볍게 조합 가능 | 문서 엷음 |

**권장**: Plotly `scattergl` + 수동 y-jitter. 3-5의 histogram binning은 `d3-array` `bin()` 하나만 조합하면 충분.

---

## 4. 프론트 구현 체크리스트

- [ ] 페이지 mount 시 `GET /shap-summary` 1회 호출 → 전역 state에 캐시
- [ ] 도메인 선택 탭 4개 (motor / hydraulic / nutrient / zone_drip)
- [ ] 각 탭 안에 타깃 드롭다운 or 두 차트 동시 표시
- [ ] Beeswarm 컴포넌트 props: `{ features, feature_order, shap_values, feature_values, topK = 10 }`
- [ ] 색상 legend: "Feature value Low → High" (파랑 → 빨강) 세로 바
- [ ] 호버 툴팁: `"{feature}: {raw_value} (SHAP={shap_value:+.3f})"`
- [ ] `n_samples ≤ 200`이면 전체 점 표시, 넘어가면 uniform subsample로 UI FPS 보전

---

## 5. 백엔드 작업 (승인 대기)

현재 SHAP 값이 디스크에 없으므로 다음 순서로 저장 → 서빙한다.

### 5-1. `train.py` 수정
- `run_feature_selection_experiment` 반환값의 `shap_vals_dict`, `X_bg_dict`를 `_`로 버리지 말고 수신 ([train.py:278](../src/train.py#L278))
- 각 도메인별로 `models/{domain}_shap.json` 저장:
  ```python
  shap_payload = {
      "targets": {
          target_name: {
              "features":       list(X_bg.columns),
              "mean_abs_shap":  np.abs(sv).mean(axis=0).tolist(),
              "feature_order":  <sorted by mean_abs_shap desc>,
              "shap_values":    sv.tolist(),
              "feature_values": X_bg.values.tolist(),
          }
          for target_name, sv in shap_vals_dict.items()
          for X_bg in [X_bg_dict[target_name]]
      },
      "n_samples":   200,
      "n_features":  <per-target>,
      "computed_at": datetime.utcnow().isoformat() + "Z",
  }
  json.dump(shap_payload, open(f"models/{domain}_shap.json", "w"))
  ```

### 5-2. `inference_api.py` 수정
- 서버 시작 시(`lifespan` 혹은 모듈 상단) 4개 `{domain}_shap.json` 로드 → 메모리에 dict로 보관
- 새 라우터:
  ```python
  @app.get("/shap-summary")
  def shap_summary():
      return SHAP_CACHE   # 시작 시 로드해둔 dict 그대로 반환
  ```

### 5-3. 변경 없음
- `/predict` 응답은 손대지 않는다 (payload 크기 · 의미 불일치 이유)
- `models/{domain}_config.json`에도 SHAP을 넣지 않는다 (config는 작게 유지)

---

## 6. Q&A

**Q. 매 `/predict`에 왜 같이 안 보내나?**
A. 입력이 변해도 SHAP은 변하지 않는다. 매 예측마다 ~2MB 중복 전송 + 프론트의 차트 리렌더 트리거 낭비.

**Q. 도메인당 타깃이 2개인데 하나만 보여도 되나?**
A. 가능. `mean_abs_shap`이 더 큰 쪽을 디폴트로 띄우거나, UI에서 토글. 둘 다 보여주면 "어떤 고장 모드가 어떤 피처를 쓰는지" 비교가 쉬움.

**Q. 재학습 후 자동 갱신되나?**
A. `train.py` 돌 때마다 `{domain}_shap.json`이 덮어쓰기된다. 프론트는 `computed_at` 필드로 캐시 무효화 판단 가능.

**Q. Top-K feature만 보내서 payload 줄이면?**
A. 가능. 200 sample × Top 10 feature로 고정 자르면 도메인당 ~20KB 수준. 단, "Sum of other features" 바는 계산 못 함. 필요 시 응답에 `top_k_mode: true` 플래그 추가해 조건부 처리.
