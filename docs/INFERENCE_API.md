# 📘 추론 API 프론트엔드 연동 문서

스마트팜 예지보전 추론 서버의 요청/응답 포맷 + 파생변수/분석 가이드 통합 문서.
프론트엔드 차트·알람 UI, 파생변수 계산, preprocessing.py와의 중복 점검까지 한 파일로 정리했다.

---

## 0. 문서 범위

이 문서 하나에 다음이 모두 들어있음:
1. API 엔드포인트 · 요청 포맷 · 응답 포맷 (스키마)
2. 응답의 모든 필드 의미 · 타입 · 단위
3. 프론트엔드에서 만들 수 있는 파생변수 목록 + 수식
4. [src/preprocessing.py](../src/preprocessing.py)의 파생변수와 중복·충돌 지점
5. 파생변수가 어떻게 도메인별 모델에 분배되는지
6. 한글 라벨 매핑 · 에러 응답 · 연동 체크리스트

---

## 1. 기본 정보

| 항목 | 값 |
|---|---|
| Base URL (로컬) | `http://127.0.0.1:9977` (또는 개발 중이면 `http://127.0.0.1:8000`) |
| Endpoint | `POST /predict` |
| Content-Type | `application/json` |
| Swagger (자동 문서) | `{Base URL}/docs` |
| 관련 소스 | [src/inference_api.py](../src/inference_api.py), [src/inference_core.py](../src/inference_core.py) |

서버 기동 시 [models/](../models/) 폴더 안의 `*_config.json` 파일을 자동 스캔해서 **도메인 모델(서브시스템)** 을 로드한다. 현재 로드되는 도메인은 4개.

| 도메인 코드 | 이름 (한글) | 역할 |
|---|---|---|
| `motor` | 모터 | 모터 전력·회전수 기반 구동 상태 감시 |
| `hydraulic` | 수압/유압 | 토출 압력·차압 기반 배관 상태 감시 |
| `nutrient` | 양액/수질 | 양액 EC·pH·목표 오차 감시 |
| `zone_drip` | 구역 점적 | 구역별 유량/압력/수분 반응 감시 |

---

## 2. 데이터 흐름 개요

```
┌────────────────┐   flat JSON    ┌───────────────────┐   JSON    ┌─────────────┐
│ Client/Simulator │ ───────────▶ │ /predict           │ ────────▶ │ Frontend    │
│  (센서값 + 시점)  │   raw sensors │ inference_api.py   │           │ (차트/알람)  │
└────────────────┘                │  · 4개 도메인 추론 │           └─────────────┘
                                  │  · MSE → alarm     │
                                  │  · RCA Top3        │
                                  │  · σ-band 계산     │
                                  └───────────────────┘
```

- **Client**는 보통 [src/client_simulator.py](../src/client_simulator.py)처럼 CSV 한 행을 `to_dict()`로 payload화해서 POST.
- 서버는 **stateless** — 한 요청 = 한 시점. 시계열 버퍼가 없으므로 std/IQR/기울기 같은 **시간창 파생**은 서버가 직접 만들지 못함.

---

## 3. 요청 (Request)

### 3-1. 요청 포맷

한 번의 요청으로 **모든 도메인 모델이 동시에 추론**된다. Body는 "센서 이름 → 현재 값"의 **평탄한(flat) key-value JSON**.

```http
POST /predict HTTP/1.1
Content-Type: application/json

{
  "timestamp": "2026-04-21T10:30:00",
  "flow_rate_l_min": 45.2,
  "discharge_pressure_kpa": 310.5,
  "suction_pressure_kpa": 95.1,
  "motor_power_kw": 2.45,
  "pump_rpm": 1780,
  "motor_temperature_c": 52.3,
  "mix_ph": 6.1,
  "mix_ec_ds_m": 2.1,
  "mix_target_ec_ds_m": 2.0,
  "mix_target_ph": 6.0,
  "drain_ec_ds_m": 2.4,
  "air_temp_c": 24.1,
  "relative_humidity_pct": 62.0,
  "time_sin": 0.707,
  "time_cos": 0.707,
  "pump_on": 1,
  "is_startup_phase": 0,
  "is_off_phase": 0,
  "pressure_roll_mean_10": 305.2,
  "pressure_trend_10": 0.4,
  "pressure_flow_ratio": 6.87,
  "is_spike": false,
  "is_startup_spike": false,
  "is_anomaly_spike": false
}
```

> ⚠️ 보내지 않은 필드는 서버에서 **0.0으로 자동 채움** ([inference_api.py:107](../src/inference_api.py#L107)).
> 잘못된 알람 방지를 위해 아래 **"요청 필드 목록"**에 있는 값은 모두 채워 보내는 것을 권장.

---

### 3-2. 메타데이터

| 필드 | 타입 | 한글 이름 | 설명 |
|---|---|---|---|
| `timestamp` | string (ISO8601) | 타임스탬프 | 데이터가 발생한 시각 (없으면 서버 현재 시각) |

### 3-3. Raw 센서값 (가장 중요 — 모델 입력 원본)

| 필드 | 타입 | 한글 이름 | 단위 | 설명 |
|---|---|---|---|---|
| `flow_rate_l_min` | number | 유량 | L/min | 펌프 메인 라인 유량 |
| `discharge_pressure_kpa` | number | 토출 압력 | kPa | 펌프 출력단 압력 |
| `suction_pressure_kpa` | number | 흡입 압력 | kPa | 펌프 입력단 압력 |
| `motor_power_kw` | number | 모터 전력 | kW | 모터 소비 전력 |
| `pump_rpm` | number | 펌프 회전수 | RPM | 펌프 분당 회전수 |
| `motor_temperature_c` | number | 모터 온도 | °C | 모터 표면 온도 |
| `mix_ph` | number | 혼합액 pH | pH | 조제 탱크 현재 pH |
| `mix_ec_ds_m` | number | 혼합액 EC | dS/m | 조제 탱크 현재 EC |
| `mix_target_ec_ds_m` | number | 목표 EC | dS/m | 설정된 목표 EC |
| `mix_target_ph` | number | 목표 pH | pH | 설정된 목표 pH |
| `drain_ec_ds_m` | number | 배액 EC | dS/m | 배드 배액 EC |
| `air_temp_c` | number | 실내 기온 | °C | 재배실 공기 온도 |
| `relative_humidity_pct` | number | 상대 습도 | % | 재배실 상대 습도 |
| `filter_pressure_in_kpa` | number | 필터 입구 압력 | kPa | 필터 전단 압력 (필터 페이지용, 룰 기반) |
| `filter_pressure_out_kpa` | number | 필터 출구 압력 | kPa | 필터 후단 압력. 펌프 AE에는 다중공선성으로 제외됨 ([preprocessing.py:621](../src/preprocessing.py#L621)) |

### 3-4. 시간·상태 (컨텍스트 피처)

| 필드 | 타입 | 한글 이름 | 설명 |
|---|---|---|---|
| `time_sin` | number | 시간(사인) | 하루 주기 sin 인코딩, 범위 [-1, 1] |
| `time_cos` | number | 시간(코사인) | 하루 주기 cos 인코딩, 범위 [-1, 1] |
| `pump_on` | 0\|1 | 펌프 가동 여부 | 0=정지, 1=가동 |
| `pump_start_event` | 0\|1 | 펌프 기동 이벤트 | 이번 tick 기동 시작 순간 1 |
| `pump_stop_event` | 0\|1 | 펌프 정지 이벤트 | 이번 tick 정지 순간 1 |
| `minutes_since_startup` | int | 기동 후 경과분 | 펌프 켜진 후 지난 분 수 |
| `minutes_since_shutdown` | int | 정지 후 경과분 | 펌프 꺼진 후 지난 분 수 |
| `is_startup_phase` | 0\|1 | 기동 직후 5분 여부 | **1일 때 알람이 강제로 Normal로 묵임** ([inference_api.py:133-134](../src/inference_api.py#L133-L134)) |
| `is_off_phase` | 0\|1 | 정지 직후 5분 여부 | 꺼진 직후 과도 구간 표시 |

### 3-5. 파생 지표 (없어도 되지만 있으면 정확도 ↑)

| 필드 | 타입 | 한글 이름 | 설명 |
|---|---|---|---|
| `pressure_roll_mean_10` | number | 압력 10분 이동평균 | `differential_pressure_kpa`의 10분 롤링 평균 ([preprocessing.py:215-217](../src/preprocessing.py#L215-L217)) |
| `pressure_trend_10` | number | 압력 10분 트렌드 | 위 이동평균의 1차 차분 |
| `pressure_flow_ratio` | number | 압력/유량 비율 | 배관 저항 지표 — ⚠️ 공식 이슈는 §8-2 참고 |
| `wire_to_water_efficiency` | number | 전기→수력 효율 | `hydraulic_power / motor_power` |
| `rpm_slope` | number | RPM 변화율 | `diff(pump_rpm) / Δt` |
| `temp_slope_c_per_s` | number | 온도 변화율 | `diff(motor_temperature_c) / Δt` |

### 3-6. 스파이크 플래그 (전처리에서 계산된 값 passthrough)

| 필드 | 타입 | 한글 이름 | 설명 |
|---|---|---|---|
| `is_spike` | bool | 스파이크 발생 | 압력/RPM 급변 발생 여부 |
| `is_startup_spike` | bool | 기동 스파이크 | 기동 직후의 정상 스파이크 |
| `is_anomaly_spike` | bool | 이상 스파이크 | 기동 구간 밖의 비정상 스파이크 |

---

## 4. 응답 (Response)

### 4-1. 최상위 구조

> **영어/한국어 키 이중 표기 정책** (2026-04-22 적용):
> 일부 필드는 영어 키와 한국어 키를 **둘 다** 담아 보낸다. **영어 키가 정본**이며, DB 저장·로그·SHAP 로직 등 서버 내부 consumer는 영어 키만 읽는다. 한국어 키는 프론트 UI 라벨/디버깅 편의를 위한 **동일 값 별칭**이다. 프론트도 가급적 영어 키를 읽기를 권장 — 한국어 키는 UI 표시 직전 치환용으로만 사용.

```json
{
  "timestamp": "2026-04-21T10:30:00",
  "overall_alarm_level": 2,
  "알람": 2,
  "overall_status": "Warning 🟠",
  "spike_info": { ... },
  "raw_inputs": { ... },
  "센서 로우데이터": { ... },
  "domain_reports": { ... },
  "action_required": "System check recommended"
}
```

| 영어 키 (정본) | 한국어 별칭 | 타입 | 설명 |
|---|---|---|---|
| `timestamp` | — | string | 타임스탬프 — 요청의 timestamp 그대로 echo (없으면 서버시각) |
| `overall_alarm_level` | `알람` | 0~3 | 전체 알람 레벨 — 4개 도메인 중 가장 심각한 레벨. **두 키는 항상 같은 값**. |
| `overall_status` | — | string | 전체 상태 라벨 — §5 참조 |
| `spike_info` | — | object | 스파이크 정보 — 요청의 `is_spike*` passthrough |
| `raw_inputs` | `센서 로우데이터` | object | 원시값 passthrough — §4-3 참조. **두 키는 동일 object 참조**. |
| `domain_reports` | — | object | 도메인별 리포트 — key = 도메인 코드 (`motor`, `hydraulic`, `nutrient`, `zone_drip`) |
| `action_required` | — | string | 권장 조치 — `"Optimal"` 또는 `"System check recommended"` (level ≥ 2) |

### 4-2. `spike_info`

```json
"spike_info": {
  "is_spike": false,
  "is_startup_spike": false,
  "is_anomaly_spike": false
}
```

요청의 `is_spike*` 값을 그대로 echo. UI에 "⚡ 이상 스파이크 감지" 배지를 띄울 때 사용 ([inference_api.py:183-187](../src/inference_api.py#L183-L187)).

### 4-3. `raw_inputs` (프론트 파생변수 계산용 passthrough)

2026-04-21 추가. 요청 body의 원시 센서값 중 프론트 파생변수 계산에 자주 쓰이는 키만 골라 echo한다. **요청에 존재하는 키만 담긴다** — 서버가 0.0으로 위장하지 않으므로 프론트가 "센서 미보고 vs 실제 0"을 구분할 수 있다.

```json
"raw_inputs": {
  "discharge_pressure_kpa": 310.5,
  "suction_pressure_kpa": 95.1,
  "flow_rate_l_min": 45.2,
  "motor_power_kw": 2.45,
  "motor_temperature_c": 52.3,
  "pump_rpm": 1780,
  "filter_pressure_in_kpa": 152.4,
  "filter_pressure_out_kpa": 144.9
}
```

| 키 | 타입 | 단위 | 용도 |
|---|---|---|---|
| `discharge_pressure_kpa` | number | kPa | `pressure_flow_ratio`, `dp_per_flow`, `pressure_volatility` 분자/버퍼링 |
| `suction_pressure_kpa` | number | kPa | `dp_per_flow`에서 차압 계산 |
| `flow_rate_l_min` | number | L/min | 위 비율들의 분모, `flow_volatility` 버퍼링 |
| `motor_power_kw` | number | kW | `flow_per_power`, `pressure_per_power` 분모 |
| `motor_temperature_c` | number | °C | `temp_slope` 직전값 저장 후 차분 |
| `pump_rpm` | number | RPM | 필요 시 RPM 기반 파생에 사용 |
| `filter_pressure_in_kpa` | number | kPa | 필터 페이지 `filter_delta_p_kpa` 분자 (§7-4) |
| `filter_pressure_out_kpa` | number | kPa | 필터 페이지 `filter_delta_p_kpa` 분모 (§7-4) |

구현: [inference_api.py:538-550](../src/inference_api.py#L538-L550).

### 4-4. `domain_reports[도메인코드]` 구조

도메인 코드는 `motor`, `hydraulic`, `nutrient`, `zone_drip`. 각 도메인마다 동일한 스키마의 리포트가 들어 있음.

```json
"motor": {
  "도메인명": "모터",
  "metrics": {
    "current_mse": 0.000345,
    "train_loss": "N/A",
    "val_loss": "N/A"
  },
  "alarm": {
    "level": 1,
    "label": "Caution 🔸",
    "한글": "주의 🔸"
  },
  "global_thresholds": {
    "caution":  0.003418,
    "warning":  0.005013,
    "critical": 0.009800
  },
  "per_feature_thresholds": {
    "pressure_trend_10": { "caution": 0.00012, "warning": 0.00031, "critical": 0.00075 }
  },
  "rca_top3": [
    { "feature": "pressure_trend_10", "한글명": "차압 10분 트렌드", "contribution": 78.3 },
    { "feature": "motor_temperature_c", "한글명": "모터 온도", "contribution": 12.4 },
    { "feature": "flow_rate_l_min", "한글명": "메인 유량", "contribution":  9.3 }
  ],
  "feature_details": [
    {
      "name": "pressure_trend_10",
      "한글명": "차압 10분 트렌드",
      "actual_value": 0.0234,
      "expected_value": 0.0210,
      "bands": {
        "caution_upper":  0.025, "caution_lower":  0.017,
        "warning_upper":  0.029, "warning_lower":  0.013,
        "critical_upper": 0.033, "critical_lower": 0.009
      },
      "scaled_error": 0.00001234,
      "feature_thresholds": { "caution": 0.00012, "warning": 0.00031, "critical": 0.00075 },
      "feature_alarm": { "level": 1, "label": "Caution 🔸", "한글": "주의 🔸" }
    }
  ],
  "target_reference_profiles": {
    "motor_current_a": {
      "한글명": "모터 전류",
      "target_lines": { ... },
      "related_feature_lines": {
        "motor_power_kw": { "한글명": "모터 전력", ... }
      },
      ...
    }
  }
}
```

> **한국어 별칭 정책 (도메인 내부)**: `도메인명`, `한글명`(피처/타깃), `한글`(알람 라벨)은 모두 **프론트 UI 표시 전용 별칭**이다. 영문 키(`name`, `feature`, `label`)가 여전히 정본이며 프로그램 로직은 영문 키만 사용해야 한다. 매핑 소스: [src/ko_labels.py](../src/ko_labels.py) · 매핑 없는 피처는 영문 그대로 반환 (fallback).

#### 4-4-1. `metrics`

| 필드 | 타입 | 한글 이름 | 설명 |
|---|---|---|---|
| `current_mse` | number | 현재 MSE | 이번 추론의 복원 오차 (알람 판정 근거) |
| `train_loss` | number \| `"N/A"` | 학습 손실 | config에 있으면 숫자, 없으면 문자열 `"N/A"` ([inference_api.py:160](../src/inference_api.py#L160)) |
| `val_loss` | number \| `"N/A"` | 검증 손실 | 위와 동일 |

#### 4-4-2. `alarm`

| 필드 | 타입 | 한글 이름 | 설명 |
|---|---|---|---|
| `level` | 0~3 | 알람 레벨 | §5 알람 레벨 표 참고 |
| `label` | string | 알람 라벨 | §5 알람 레벨 표 참고 |

#### 4-4-3. `global_thresholds`

도메인 전체 MSE 기준 임계치. [inference_core.py:5-14](../src/inference_core.py#L5-L14)의 `get_alarm_status`가 사용.

| 필드 | 타입 | 한글 이름 | 설명 |
|---|---|---|---|
| `caution` | number | 주의 임계값 | MSE ≥ 이 값 → Caution |
| `warning` | number | 경고 임계값 | MSE ≥ 이 값 → Warning |
| `critical` | number | 위험 임계값 | MSE ≥ 이 값 → Critical |

#### 4-4-4. `per_feature_thresholds`

피처 단위의 임계치. config의 `per_feature_thresholds`를 passthrough ([inference_api.py:147, 169](../src/inference_api.py#L147)). 해당 도메인 모델이 `scoring_features`로 지정한 피처들에 대해서만 존재.

```json
"pressure_trend_10": {
  "caution":  0.00012,
  "warning":  0.00031,
  "critical": 0.00075
}
```

#### 4-4-5. `rca_top3` (원인 분석 Top 3) — [inference_core.py:57-90](../src/inference_core.py#L57-L90)

배열의 각 원소:

| 필드 | 타입 | 한글 이름 | 설명 |
|---|---|---|---|
| `feature` | string | 피처명 | 이상 기여도가 높은 피처 이름 (영문 키) |
| `contribution` | number | 기여도(%) | 전체 오차 중 이 피처가 차지하는 % |

> 시간/상태 피처(`time_sin`, `time_cos`, `pump_on`, `minutes_since_startup` 등)는 원인 분석에서 **자동 제외** ([inference_core.py:23-44](../src/inference_core.py#L23-L44) `DEFAULT_CONTEXT_FEATURES`). 액션 가능한 실센서 피처만 올라옴.

#### 4-4-6. `feature_details` (차트용 시계열/밴드 데이터) — [inference_core.py:93-149](../src/inference_core.py#L93-L149)

도메인 모델의 features 리스트에 있는 모든 피처에 대해 원소 1개씩.

| 필드 | 타입 | 한글 이름 | 설명 |
|---|---|---|---|
| `name` | string | 피처명 | 영문 키 (§6 도메인별 피처 표에서 한글 매핑) |
| `actual_value` | number | 실제 값 | 지금 들어온 센서 실측치 |
| `expected_value` | number | 예측 값 | AE가 "정상이라면 이랬을 것"이라고 복원한 값 |
| `bands.caution_upper/lower` | number | 1σ 상/하한 | 주의 밴드 (expected ± 1σ) |
| `bands.warning_upper/lower` | number | 2σ 상/하한 | 경고 밴드 (expected ± 2σ) |
| `bands.critical_upper/lower` | number | 3σ 상/하한 | 위험 밴드 (expected ± 3σ) |
| `scaled_error` | number | 스케일 오차 | (옵션) 스케일 공간 제곱오차. `per_feature_thresholds`에 있을 때만 존재 |
| `feature_thresholds` | object | 피처별 임계치 | (옵션) `{caution, warning, critical}` |
| `feature_alarm` | object | 피처별 알람 | (옵션) `{level, label}` |

UI에서 정상 기대값(라인) + 1/2/3σ 밴드(반투명 영역) + 실측값(점) 조합으로 그리면 직관적.

> `scaled_error` / `feature_thresholds` / `feature_alarm`은 **해당 피처가 `per_feature_thresholds`에 있을 때만** 포함 ([inference_core.py:130-131](../src/inference_core.py#L130-L131)). 프론트는 옵셔널 처리 필요.

#### 4-4-7. `target_reference_profiles` — [inference_core.py:177-220](../src/inference_core.py#L177-L220)

타겟 변수(예: `motor_current_a`) 기준 **정상 구간**의 관련 변수 기준선. 학습 시 계산되어 config에 박혀 있는 **정적 레퍼런스**.

```json
"motor_current_a": {
  "target_threshold_basis": "target_caution_band_1sigma",
  "target_lines": {
    "normal": 8.6,
    "caution":  { "lower": 7.9, "upper": 9.3 },
    "warning":  { "lower": 7.2, "upper": 10.0 },
    "critical": { "lower": 6.5, "upper": 10.7 },
    "std": 0.7,
    "training_min": 6.8,
    "training_max": 10.4
  },
  "normal_sample_count": 12840,
  "related_feature_lines": {
    "motor_power_kw": {
      "normal": 2.85,
      "caution":  { "lower": 2.60, "upper": 3.10 },
      "warning":  { "lower": 2.35, "upper": 3.35 },
      "critical": { "lower": 2.10, "upper": 3.60 },
      "std": 0.25,
      "training_min": 2.20,
      "training_max": 3.48
    }
  }
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `target_threshold_basis` | string | 타겟 정상 샘플 선정 기준. 현재는 `target_caution_band_1sigma` (타겟 평균 ± 1σ) |
| `target_lines` | object | 타겟 변수 자체의 `normal/caution/warning/critical` 라인 |
| `normal_sample_count` | number | 타겟 정상 구간으로 분류된 학습 샘플 수 |
| `related_feature_lines` | object | 관련 변수별 `normal/caution/warning/critical` 라인 |

프론트에서 "타겟(`motor_current_a`) 기준의 관련 변수 기준선"을 그릴 때 `target_reference_profiles.motor_current_a.related_feature_lines`를 사용. **현재 시점의 동적 밴드**는 `feature_details[].bands`를 사용.

---

## 5. 알람 레벨 표

| level | label | 한글 이름 | UI 색상 권장 |
|---|---|---|---|
| 0 | `Normal` / `Normal 🟢` | 정상 | 녹색 |
| 1 | `Caution 🔸` | 주의 | 노란색 |
| 2 | `Warning 🟠` | 경고 | 주황색 |
| 3 | `Critical 🔴` | 위험 | 빨간색 |

> 기동 직후 5분간은 `Normal (startup gated)` 라벨로 알람이 자동 억제됨 ([inference_api.py:133-134](../src/inference_api.py#L133-L134)).

---

## 6. 도메인별 피처 한글 매핑

⚠️ **이 표는 실제 `models/*_config.json`의 `features` 리스트 기준**이다. 모델이 재학습되면 리스트가 바뀔 수 있으니, 프론트는 배포 시 `feature_details[].name`을 그대로 받아 매핑 테이블로 한글화하는 방식을 권장.

### 6-1. motor (모터)

| 피처명 | 한글 이름 | 단위 |
|---|---|---|
| `pressure_trend_10` | 압력 10분 트렌드 | kPa/min |
| `time_sin` | 시간(사인) | - |
| `time_cos` | 시간(코사인) | - |
| `pump_on` | 펌프 가동 | 0/1 |
| `minutes_since_startup` | 기동 후 경과분 | 분 |

### 6-2. hydraulic (수압/유압)

| 피처명 | 한글 이름 | 단위 |
|---|---|---|
| `wire_to_water_efficiency` | 전기→수력 효율 | - |
| `flow_rate_l_min` | 메인 유량 | L/min |
| `pump_rpm` | 펌프 회전수 | RPM |
| `motor_power_kw` | 모터 전력 | kW |
| `motor_temperature_c` | 모터 온도 | °C |
| `time_sin` | 시간(사인) | - |
| `time_cos` | 시간(코사인) | - |
| `pump_on` | 펌프 가동 | 0/1 |
| `minutes_since_startup` | 기동 후 경과분 | 분 |

### 6-3. nutrient (양액/수질)

| 피처명 | 한글 이름 | 단위 |
|---|---|---|
| `pump_rpm` | 펌프 회전수 | RPM |
| `motor_temperature_c` | 모터 온도 | °C |
| `time_sin` | 시간(사인) | - |
| `time_cos` | 시간(코사인) | - |
| `pump_on` | 펌프 가동 | 0/1 |
| `minutes_since_startup` | 기동 후 경과분 | 분 |

### 6-4. zone_drip (구역 점적)

| 피처명 | 한글 이름 | 단위 |
|---|---|---|
| `rpm_slope` | RPM 변화율 | RPM/sec |
| `motor_temperature_c` | 모터 온도 | °C |
| `time_sin` | 시간(사인) | - |
| `time_cos` | 시간(코사인) | - |
| `pump_on` | 펌프 가동 | 0/1 |
| `minutes_since_startup` | 기동 후 경과분 | 분 |

> 👉 한글 매핑 룩업 테이블은 프론트에서 **단일 JSON**으로 관리하는 것을 권장 (도메인이 늘어나도 개별 분기 안 만들어도 됨).

---

## 7. 프론트 파생변수 가이드

아래 변수들은 **응답 JSON만으로 프론트에서 직접 계산 가능한 파생변수**다. ε는 0-division 방지용 작은 값(`1e-6` 권장).

### 7-1. 단일 시점으로 바로 가능 (응답 `raw_inputs` 블록만 있으면 됨)

| 파생변수 | 수식 | 의미 |
|---|---|---|
| `pressure_flow_ratio` | `raw_inputs.discharge_pressure_kpa / (raw_inputs.flow_rate_l_min + ε)` | 배관 저항 지표. **해석용 공식(토출/유량)** 으로 프론트 통일. 모델 입력용 정의는 §8-2 참고 |
| `dp_per_flow` | `(raw_inputs.discharge_pressure_kpa − raw_inputs.suction_pressure_kpa) / (raw_inputs.flow_rate_l_min + ε)` | 펌프 순수 에너지 대비 유량 |
| `flow_per_power` | `raw_inputs.flow_rate_l_min / (raw_inputs.motor_power_kw + ε)` | **유량 대비 전력 효율** (전력 당 밀어내는 유량) |
| `pressure_per_power` | `raw_inputs.discharge_pressure_kpa / (raw_inputs.motor_power_kw + ε)` | **압력 대비 전력 효율** (전력 당 유지하는 압력) |

### 7-2. 시계열 버퍼링이 필요 (프론트 링버퍼 필수)

| 파생변수 | 필요한 버퍼 | 수식 | 의미 |
|---|---|---|---|
| `pressure_volatility` | 최근 N개의 `raw_inputs.discharge_pressure_kpa` | `std(P) / (iqr(P) + ε)` | 압력 변동성 |
| `flow_volatility` (CV) | 최근 N개의 `raw_inputs.flow_rate_l_min` | `std(F) / (mean(F) + ε)` | 유량 변동계수 |
| `temp_slope` | 직전 `motor_temperature_c` + `timestamp` | `(T_now − T_prev) / Δt_seconds` | 초당 온도 기울기 |

- **N 계산**: 원하는 윈도우(초·분 단위) ÷ 샘플링 간격.
  예: 샘플링 1분, 윈도우 12시간 → N = 720.
- **IQR**: `percentile_75(P) − percentile_25(P)`.
- **temp_slope 더 안정적**: 최근 N개 `(t_i, T_i)`로 선형회귀 기울기 = `cov(t, T) / (var(t) + ε)`.

### 7-3. 프론트 최소 상태(state) 설계

```ts
type RingBuffer = {
  discharge_pressure: number[];     // max size N
  flow_rate: number[];              // max size N
  last_temp: number | null;
  last_ts: number | null;           // ms epoch
};

// 매 요청 응답 받을 때마다:
// 1) raw_inputs 로 ring buffer 푸시
// 2) 파생변수 재계산
// 3) UI 갱신
```

### 7-4. 필터 페이지 파생 (룰 기반)

필터 도메인은 **AE 모델이 없음**(학습 데이터에 막힘 시나리오 부재 — 상세는 [FRONTEND_PAGES.md §1-5](./FRONTEND_PAGES.md#1-5-🧃-filter-필터--️-ae-모델-없음-룰-기반-페이지)). 프론트에서 아래 파생을 클라이언트 계산.

| 파생변수 | 수식 | 권장 임계 |
|---|---|---|
| `filter_delta_p_kpa` | `raw_inputs.filter_pressure_in_kpa − raw_inputs.filter_pressure_out_kpa` | 경고 > 15 kPa, 위험 > 25 kPa |

> 실측 기준(dabin.csv): mean ≈ 7.4 kPa, max ≈ 8.34 kPa. 정상 대비 2배 이상 상승 = 막힘 의심.
> 펌프 차압(`differential_pressure_kpa`)과의 상관계수는 **0.374**로 독립 정보 — 필터 페이지를 별도 운영해도 정보 중복 아님.

---

## 8. preprocessing.py와의 관계

[src/preprocessing.py](../src/preprocessing.py)는 **오프라인 학습 파이프라인**용이다. 서빙 타임엔 안 돌아감. 프론트 파생변수와 이름이 겹치는 것들이 많으니 아래 맵으로 교차 확인.

### 8-1. 모델용 파생 (`create_modeling_features` → `model_cols`)

[src/preprocessing.py:324-339](../src/preprocessing.py#L324-L339)의 `model_cols`에 들어가 **실제 AE 학습 입력**이 되는 파생변수들.

| 파생변수 | 라인 | 공식 |
|---|---|---|
| `pressure_diff` | [77](../src/preprocessing.py#L77) | `discharge_pressure_kpa.diff()` |
| `differential_pressure_kpa` | [85-87](../src/preprocessing.py#L85-L87) | `discharge − suction` |
| `flow_drop_rate` | [126-137](../src/preprocessing.py#L126-L137) | `(baseline − flow) / (baseline + ε)` with gates |
| `hydraulic_power_kw` | [148-150](../src/preprocessing.py#L148-L150) | `flow × diff_pressure / 60000` |
| `wire_to_water_efficiency` | [154-156](../src/preprocessing.py#L154-L156) | `hydraulic_power / (motor_power + ε)` |
| `temp_slope_c_per_s` | [184](../src/preprocessing.py#L184) | `motor_temperature.diff() / Δt` |
| `flow_diff` | [187](../src/preprocessing.py#L187) | `flow.diff()` |
| `rpm_slope` | [188](../src/preprocessing.py#L188) | `pump_rpm.diff() / Δt` |
| `rpm_acc` | [189](../src/preprocessing.py#L189) | `rpm_slope.diff()` |
| `rpm_stability_index` | [193-196](../src/preprocessing.py#L193-L196) | `abs(rpm − rpm_mean_10) / (rpm_mean_10 + ε)` |
| `pid_error_ec` / `pid_error_ph` | [203-204](../src/preprocessing.py#L203-L204) | `current − target` |
| `salt_accumulation_delta` | [210-212](../src/preprocessing.py#L210-L212) | `drain_ec − mix_ec` |
| `pressure_roll_mean_10` | [215-217](../src/preprocessing.py#L215-L217) | `diff_pressure.rolling(10).mean()` |
| `flow_roll_mean_10` | [218-220](../src/preprocessing.py#L218-L220) | `flow.rolling(10).mean()` |
| `pressure_trend_10` | [221](../src/preprocessing.py#L221) | `pressure_roll_mean_10.diff()` |
| `flow_trend_10` | [222](../src/preprocessing.py#L222) | `flow_roll_mean_10.diff()` |
| `ph_roll_mean_30` / `ph_trend_30` | [223-224](../src/preprocessing.py#L223-L224) | pH 30분 롤링 평균/차분 |
| `pressure_flow_ratio` (⚠️) | [225-227](../src/preprocessing.py#L225-L227) | `differential_pressure / (flow + ε)` |

### 8-2. ⚠️ 이름 충돌·공식 차이 (pressure_flow_ratio)

**`pressure_flow_ratio`** 이름은 같은데 파일 내에서 **두 번 다르게 계산됨**:

| 위치 | 공식 | 쓰이는 곳 |
|---|---|---|
| [preprocessing.py:225-227](../src/preprocessing.py#L225-L227) | `differential_pressure_kpa / flow` | 모델 입력 후보 (`model_cols` 포함) |
| [preprocessing.py:455-457](../src/preprocessing.py#L455-L457) | `discharge_pressure_kpa / flow` | 해석용 (`df_interpret`) |

**현황 (2026-04-21)**: 원래는 해석/프론트용으로 만든 값이었고, 모델 입력(인코딩)으로 쓸지는 검토 중. 두 공식 중 하나로 통일 여부는 재학습 타이밍과 함께 결정될 예정.

→ **프론트 합의**: §7-1에서 `pressure_flow_ratio = discharge / flow` (해석용 공식)으로 사용. 모델 입력으로 승격될 경우 `pressure_flow_ratio_model` 등 별도 네이밍으로 구분 예정.

### 8-3. 해석용 파생 (`extract_interpretation_features` → `df_interpret`)

[src/preprocessing.py:443-561](../src/preprocessing.py#L443-L561)에서 생성. 모델 입력 아님, 학습 후 분석/모니터링 용도.

| 파생변수 | 라인 | 공식 |
|---|---|---|
| `pressure_flow_ratio` (해석판) | [455-457](../src/preprocessing.py#L455-L457) | `discharge_pressure / (flow + ε)` |
| `dp_per_flow` | [462-464](../src/preprocessing.py#L462-L464) | `(discharge − suction) / (flow + ε)` |
| `pressure_per_power` | [469-471](../src/preprocessing.py#L469-L471) | `discharge_pressure / (motor_power + ε)` |
| `flow_per_power` | [476-478](../src/preprocessing.py#L476-L478) | `flow / (motor_power + ε)` |
| `is_pressure_spike` | [532-533](../src/preprocessing.py#L532-L533) | rolling 80-percentile 기준 spike 판정 |
| `is_rpm_spike` | [540-541](../src/preprocessing.py#L540-L541) | 위와 동일, RPM 기준 |
| `is_spike` / `is_startup_spike` / `is_anomaly_spike` | [546-559](../src/preprocessing.py#L546-L559) | spike × startup 조합 |

### 8-4. 존재하지 않는 변동성 파생

다음 항목은 **현재 preprocessing.py에도 없음**. 필요하면 신규 작성 후 재학습 필요:

- `pressure_volatility` (std/IQR)
- `flow_volatility` (std/mean, CV)

---

## 9. 파생변수 위치 구조 — 카테고리별

[src/preprocessing.py](../src/preprocessing.py)는 **도메인(motor/hydraulic/...)별 분리가 아니라 센서 카테고리별**로 구성. 각 도메인 모델은 `config["features"]`로 공통 풀에서 필요한 subset만 선택.

| 섹션 | 내용 | 라인 범위 |
|---|---|---|
| 1. 압력·유량·전력 조합 | 차압, 유량 감소율, 수력동력, wire-to-water 효율, 압력/유량 비율, pump_on 감지 | [79-227](../src/preprocessing.py#L79-L227) |
| 2. 온도·진동 동특성 | `temp_slope_c_per_s`, `flow_diff`, `rpm_slope`, `rpm_acc`, `rpm_stability_index` | [180-196](../src/preprocessing.py#L180-L196) |
| 3. 양액·수질·환경 | PID 오차, pH 불안정, 염분 축적, 롤링 지표, VPD | [198-250](../src/preprocessing.py#L198-L250) |
| 4. 탱크·자원 | 탱크 수위 변화율, 고갈 예상 시간 | [252-279](../src/preprocessing.py#L252-L279) |
| 5. 구역 복합 | 공급 밸런스, 구역별 저항/수분 반응/EC 축적 | [281-319](../src/preprocessing.py#L281-L319) |
| 6. 모델용/해석용 분리 | `model_cols` 필터 + `extract_interpretation_features` 호출 | [321-349](../src/preprocessing.py#L321-L349) |

도메인 모델별 **실제 features 할당**은 `models/*_config.json`의 `features` 리스트가 단일 소스. 도메인별 feature 선택 로직은 [src/train.py](../src/train.py) / [src/feature_selection.py](../src/feature_selection.py) 참고.

---

## 10. 전체 센서/피처 용어집 (한/영 대조)

요청 필드·응답 피처 외에 운영 화면에서 보여줄 수 있는 전체 센서의 한글 이름.

| 영문 키 | 한글 이름 | 단위 |
|---|---|---|
| `flow_rate_l_min` | 메인 유량 | L/min |
| `discharge_pressure_kpa` | 토출 압력 | kPa |
| `suction_pressure_kpa` | 흡입 압력 | kPa |
| `differential_pressure_kpa` | 차압 | kPa |
| `motor_power_kw` | 모터 전력 | kW |
| `pump_rpm` | 펌프 회전수 | RPM |
| `motor_temperature_c` | 모터 온도 | °C |
| `hydraulic_power_kw` | 수력 동력 | kW |
| `wire_to_water_efficiency` | 전기→수력 효율 | - |
| `mix_ph` | 혼합액 pH | pH |
| `mix_ec_ds_m` | 혼합액 EC | dS/m |
| `mix_target_ec_ds_m` | 목표 EC | dS/m |
| `mix_target_ph` | 목표 pH | pH |
| `pid_error_ec` | EC 제어 오차 | dS/m |
| `pid_error_ph` | pH 제어 오차 | pH |
| `drain_ec_ds_m` | 배액 EC | dS/m |
| `salt_accumulation_delta` | 염분 축적량 | dS/m |
| `ph_instability_flag` | pH 불안정 플래그 | 0/1 |
| `air_temp_c` | 실내 기온 | °C |
| `relative_humidity_pct` | 상대 습도 | % |
| `calculated_vpd_kpa` | VPD (증기압 결손) | kPa |
| `light_ppfd_umol_m2_s` | 광량(PPFD) | μmol/m²/s |
| `daily_light_integral_mol_m2_d` | 일일 적산광량(DLI) | mol/m²/day |
| `raw_tank_level_pct` | 원수 탱크 수위 | % |
| `tank_a_level_pct` | A 비료통 수위 | % |
| `tank_b_level_pct` | B 비료통 수위 | % |
| `acid_tank_level_pct` | 산 탱크 수위 | % |
| `zone{1,2,3}_valve_on` | 1/2/3구역 밸브 가동 | 0/1 |
| `zone{1,2,3}_flow_l_min` | 1/2/3구역 유량 | L/min |
| `zone{1,2,3}_pressure_kpa` | 1/2/3구역 압력 | kPa |
| `zone{1,2,3}_substrate_moisture_pct` | 1/2/3구역 배지 수분 | % |
| `zone{1,2,3}_substrate_ec_ds_m` | 1/2/3구역 배지 EC | dS/m |
| `zone{1,2,3}_resistance` | 1/2/3구역 배관 저항 | kPa·min/L |
| `zone{1,2,3}_ec_accumulation` | 1/2/3구역 염류 축적 | dS/m |
| `zone{1,2,3}_moisture_response_pct` | 1/2/3구역 수분 반응량 | %/min |
| `supply_balance_index` | 공급 밸런스 지수 | - |
| `flow_drop_rate` | 유량 감소율 | 0~1 |
| `rpm_stability_index` | RPM 안정성 지수 | - |
| `cleaning_event_flag` | 세척 이벤트 | 0/1 |
| `lights_on` | 조명 가동 | 0/1 |
| `temp_slope_c_per_s` | 초당 모터 온도 변화율 | °C/sec |
| `rpm_slope` | RPM 변화율 | RPM/sec |
| `pressure_trend_10` | 압력 10분 트렌드 | kPa/min |
| `pressure_roll_mean_10` | 압력 10분 이동평균 | kPa |
| `filter_pressure_in_kpa` | 필터 입구 압력 | kPa |
| `filter_pressure_out_kpa` | 필터 출구 압력 | kPa |
| `filter_delta_p_kpa` | 필터 차압 (프론트 계산) | kPa |
| `pressure_flow_ratio` | 압력/유량 비율 (배관 저항) | kPa·min/L |
| `dp_per_flow` | 차압/유량 (펌프 에너지 효율) | kPa·min/L |
| `flow_per_power` | 유량 대비 전력 효율 | L/(min·kW) |
| `pressure_per_power` | 압력 대비 전력 효율 | kPa/kW |
| `pressure_volatility` | 압력 변동성 (std/IQR, 12h) | - |
| `flow_cv` | 유량 변동계수 (std/mean, 12h) | - |

---

## 11. 에러 응답

| HTTP | 의미 | 조치 |
|---|---|---|
| 503 | 로드된 모델 없음 | 서버 기동 로그 확인 — `models/` 폴더 내 artifact 누락 가능 |
| 500 | 추론 중 서버 내부 에러 | `detail` 필드에 원인 메시지, 서버 로그 동시 확인 |

```json
// 500 예시
{ "detail": "Input has wrong dimension..." }
```

---

## 12. 프론트엔드 연동 체크리스트

- [ ] `POST /predict`에 **평탄한 JSON**으로 센서값을 보낸다.
- [ ] 응답의 `overall_alarm_level`로 전체 알람 배지 색을 결정한다.
- [ ] `domain_reports[*].alarm`으로 도메인별 카드 색을 결정한다.
- [ ] `domain_reports[*].rca_top3`로 "의심 원인 Top3" 리스트를 띄운다.
- [ ] `domain_reports[*].feature_details`로 각 피처의 실제값 · 예측값 · 3σ 밴드 차트를 그린다.
- [ ] `feature.name`을 **§6 도메인별 피처 표**로 한글 라벨로 매핑해서 표시한다.
- [ ] `spike_info.is_anomaly_spike`가 true면 "⚡ 이상 스파이크" 배지를 강조한다.
- [ ] `raw_inputs`를 링버퍼에 쌓아 §7 파생변수 계산 및 시계열 차트에 활용한다.
- [ ] `per_feature_thresholds`가 없는 도메인의 `feature_details`엔 `scaled_error`/`feature_alarm`이 없음을 옵셔널 처리한다.
- [ ] `metrics.train_loss` / `val_loss`는 숫자 또는 `"N/A"` 둘 중 하나임을 타입 분기한다.
