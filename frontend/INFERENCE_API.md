# 📘 추론 API 프론트엔드 연동 문서

스마트팜 예지보전 추론 서버의 요청/응답 포맷 문서입니다. 프론트엔드에서 차트·알람 UI를 만들 때 참고하세요.

---

## 1. 기본 정보

| 항목 | 값 |
|---|---|
| Base URL (로컬) | `http://127.0.0.1:9977` |
| Endpoint | `POST /predict` |
| Content-Type | `application/json` |
| Swagger (자동 문서) | `http://127.0.0.1:9977/docs` |

서버가 기동되면 `models/` 폴더 안의 `*_config.json` 파일을 자동 스캔해서 **도메인 모델(서브시스템)** 을 로드합니다. 현재 로드되는 도메인은 4개입니다.

| 도메인 코드 | 이름 (한글) | 역할 |
|---|---|---|
| `motor` | 모터 | 모터 전력·회전수 기반 구동 상태 감시 |
| `hydraulic` | 수압/유압 | 토출 압력·차압 기반 배관 상태 감시 |
| `nutrient` | 양액/수질 | 양액 EC·pH·목표 오차 감시 |
| `zone_drip` | 구역 점적 | 구역별 유량/압력/수분 반응 감시 |

---

## 2. 요청 (Request)

### 포맷
한 번의 요청으로 **모든 도메인 모델이 동시에 추론**됩니다. Body 는 "센서 이름 → 현재 값"의 **평탄한(flat) key-value JSON**입니다.

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

> ⚠️ 보내지 않은 필드는 서버에서 **0.0 으로 자동 채움** 합니다. 잘못된 알람 방지를 위해 아래 **"요청 필드 목록"**에 있는 값은 모두 채워 보내는 것을 권장합니다.

### 요청 필드 목록 (프론트에서 채워야 하는 센서/컨텍스트 값)

#### 2-1. 메타데이터

| 필드 | 타입 | 한글 이름 | 설명 |
|---|---|---|---|
| `timestamp` | string (ISO8601) | 타임스탬프 | 데이터가 발생한 시각 (없으면 서버 현재 시각) |

#### 2-2. Raw 센서값 (가장 중요 — 모델 입력 원본)

| 필드 | 타입 | 한글 이름 | 단위 | 설명 |
|---|---|---|---|---|
| `flow_rate_l_min` | number | 유량 | L/min | 펌프 메인 라인 유량 |
| `discharge_pressure_kpa` | number | 토출 압력 | kPa | 펌프 출력단 압력 |
| `suction_pressure_kpa` | number | 흡입 압력 | kPa | 펌프 입력단 압력 |
| `motor_power_kw` | number | 모터 전력 | kW | 모터 소비 전력 |
| `pump_rpm` | number | 펌프 회전수 | RPM | 펌프 분당 회전 수 |
| `motor_temperature_c` | number | 모터 온도 | °C | 모터 표면 온도 |
| `mix_ph` | number | 혼합액 pH | pH | 조제 탱크 현재 pH |
| `mix_ec_ds_m` | number | 혼합액 EC | dS/m | 조제 탱크 현재 EC |
| `mix_target_ec_ds_m` | number | 목표 EC | dS/m | 설정된 목표 EC |
| `mix_target_ph` | number | 목표 pH | pH | 설정된 목표 pH |
| `drain_ec_ds_m` | number | 배액 EC | dS/m | 배드 배액 EC |
| `air_temp_c` | number | 실내 기온 | °C | 재배실 공기 온도 |
| `relative_humidity_pct` | number | 상대 습도 | % | 재배실 상대 습도 |

#### 2-3. 시간·상태 (컨텍스트 피처)

| 필드 | 타입 | 한글 이름 | 설명 |
|---|---|---|---|
| `time_sin` | number | 시간(사인) | 하루 주기 sin 인코딩, 범위 [-1, 1] |
| `time_cos` | number | 시간(코사인) | 하루 주기 cos 인코딩, 범위 [-1, 1] |
| `pump_on` | 0\|1 | 펌프 가동 여부 | 0=정지, 1=가동 |
| `pump_start_event` | 0\|1 | 펌프 기동 이벤트 | 이번 tick 기동 시작 순간 1 |
| `pump_stop_event` | 0\|1 | 펌프 정지 이벤트 | 이번 tick 정지 순간 1 |
| `minutes_since_startup` | int | 기동 후 경과분 | 펌프 켜진 후 지난 분 수 |
| `minutes_since_shutdown` | int | 정지 후 경과분 | 펌프 꺼진 후 지난 분 수 |
| `is_startup_phase` | 0\|1 | 기동 직후 5분 여부 | **1일 때 알람이 강제로 Normal로 묵임** |
| `is_off_phase` | 0\|1 | 정지 직후 5분 여부 | 꺼진 직후 과도 구간 표시 |

#### 2-4. 파생 지표 (없어도 되지만 있으면 정확도 ↑)

| 필드 | 타입 | 한글 이름 | 설명 |
|---|---|---|---|
| `pressure_roll_mean_10` | number | 압력 10분 이동평균 | `discharge_pressure_kpa`의 10분 롤링 평균 |
| `pressure_trend_10` | number | 압력 10분 트렌드 | 위 이동평균의 1차 차분 |
| `pressure_flow_ratio` | number | 압력/유량 비율 | 배관 저항 지표 |

#### 2-5. 스파이크 플래그 (전처리 단계에서 이미 계산된 값을 그대로 passthrough)

| 필드 | 타입 | 한글 이름 | 설명 |
|---|---|---|---|
| `is_spike` | bool | 스파이크 발생 | 압력/RPM 급변 발생 여부 |
| `is_startup_spike` | bool | 기동 스파이크 | 기동 직후의 정상 스파이크 |
| `is_anomaly_spike` | bool | 이상 스파이크 | 기동 구간 밖의 비정상 스파이크 |

---

## 3. 응답 (Response)

### 최상위 구조

```json
{
  "timestamp": "2026-04-21T10:30:00",
  "overall_alarm_level": 2,
  "overall_status": "Warning 🟠",
  "spike_info": { ... },
  "domain_reports": { ... },
  "action_required": "System check recommended"
}
```

| 필드 | 타입 | 한글 이름 | 설명 |
|---|---|---|---|
| `timestamp` | string | 타임스탬프 | 요청의 timestamp 그대로 echo |
| `overall_alarm_level` | 0~3 | 전체 알람 레벨 | 4개 도메인 중 가장 심각한 레벨 |
| `overall_status` | string | 전체 상태 라벨 | 아래 "알람 레벨 표" 참조 |
| `spike_info` | object | 스파이크 정보 | 요청의 `is_spike*` 값 passthrough |
| `domain_reports` | object | 도메인별 리포트 | key = 도메인 코드 (motor 등) |
| `action_required` | string | 권장 조치 | `"Optimal"` 또는 `"System check recommended"` |

### 알람 레벨 표

| level | label | 한글 이름 | UI 색상 권장 |
|---|---|---|---|
| 0 | `Normal` / `Normal 🟢` | 정상 | 녹색 |
| 1 | `Caution 🔸` | 주의 | 노란색 |
| 2 | `Warning 🟠` | 경고 | 주황색 |
| 3 | `Critical 🔴` | 위험 | 빨간색 |

> 기동 직후 5분간은 `Normal (startup gated)` 라벨로 알람이 자동 억제됩니다.

### 3-1. `spike_info` 구조

```json
{
  "is_spike": false,
  "is_startup_spike": false,
  "is_anomaly_spike": false
}
```
요청의 `is_spike*` 값을 그대로 내려줍니다. UI에 "⚡ 이상 스파이크 감지" 같은 배지를 띄울 때 사용하세요.

### 3-2. `domain_reports[도메인코드]` 구조

도메인 코드는 `motor`, `hydraulic`, `nutrient`, `zone_drip` 입니다. 각 도메인마다 동일한 스키마의 리포트가 들어 있습니다.

```json
"motor": {
  "metrics": {
    "current_mse": 0.000345,
    "train_loss": [...],
    "val_loss": [...]
  },
  "alarm": {
    "level": 1,
    "label": "Caution 🔸"
  },
  "global_thresholds": {
    "caution":  0.000777,
    "warning":  0.001039,
    "critical": 0.001827
  },
  "rca_top3": [
    { "feature": "discharge_pressure_kpa", "contribution": 78.3 },
    { "feature": "time_sin",                "contribution": 12.4 },
    { "feature": "time_cos",                "contribution":  9.3 }
  ],
  "feature_details": [
    {
      "name": "discharge_pressure_kpa",
      "actual_value":  310.5,
      "expected_value": 305.1,
      "bands": {
        "caution_upper":  408.4, "caution_lower":  201.8,
        "warning_upper":  511.7, "warning_lower":   98.5,
        "critical_upper": 615.0, "critical_lower":  -4.8
      }
    }
  ]
}
```

#### 3-2-1. `metrics`

| 필드 | 타입 | 한글 이름 | 설명 |
|---|---|---|---|
| `current_mse` | number | 현재 MSE | 이번 추론의 복원 오차 (알람 판정 근거) |
| `train_loss` | number[] \| "N/A" | 학습 손실 | 학습 시 epoch별 loss (참고용) |
| `val_loss` | number[] \| "N/A" | 검증 손실 | 학습 시 epoch별 val_loss (참고용) |

#### 3-2-2. `alarm`

| 필드 | 타입 | 한글 이름 | 설명 |
|---|---|---|---|
| `level` | 0~3 | 알람 레벨 | 위 "알람 레벨 표" 참고 |
| `label` | string | 알람 라벨 | 한글 매핑은 위 표 참고 |

#### 3-2-3. `global_thresholds`

| 필드 | 타입 | 한글 이름 | 설명 |
|---|---|---|---|
| `caution` | number | 주의 임계값 | MSE 이 값 넘으면 Caution |
| `warning` | number | 경고 임계값 | MSE 이 값 넘으면 Warning |
| `critical` | number | 위험 임계값 | MSE 이 값 넘으면 Critical |

UI 게이지/바 그릴 때 `current_mse`와 함께 구간 라인으로 표시하면 좋습니다.

#### 3-2-4. `rca_top3` (원인 분석 Top 3)

| 필드 | 타입 | 한글 이름 | 설명 |
|---|---|---|---|
| `feature` | string | 피처명 | 이상 기여도가 높은 피처 이름 (영문 키) |
| `contribution` | number | 기여도(%) | 전체 오차 중 이 피처가 차지하는 % |

> 시간/상태 피처(`time_sin`, `pump_on` 등)는 원인 분석에서 **자동 제외**되고 실제 액션 가능한 센서 피처만 올라옵니다.

#### 3-2-5. `feature_details` (차트용 시계열/밴드 데이터)

배열의 각 원소는 한 피처의 상세 정보입니다.

| 필드 | 타입 | 한글 이름 | 설명 |
|---|---|---|---|
| `name` | string | 피처명 | 영문 키 (아래 "도메인별 피처" 표에서 한글명 매핑) |
| `actual_value` | number | 실제 값 | 지금 들어온 센서 실측치 |
| `expected_value` | number | 예측 값 | AE가 "정상이라면 이랬을 것"이라고 복원한 값 |
| `bands.caution_upper/lower` | number | 1시그마 상/하한 | 주의 밴드 |
| `bands.warning_upper/lower` | number | 2시그마 상/하한 | 경고 밴드 |
| `bands.critical_upper/lower` | number | 3시그마 상/하한 | 위험 밴드 |

UI에서 정상 기대값(라인) + 1/2/3시그마 밴드(반투명 영역) + 실측값(점) 조합으로 그리면 직관적입니다.

---

## 4. 도메인별 피처 한글 매핑

`feature_details[].name` 및 `rca_top3[].feature` 에 등장하는 영문 키를 한글로 어떻게 표시할지 아래 표로 매핑하세요.

### 4-1. motor (모터)

| 피처명 | 한글 이름 | 단위 |
|---|---|---|
| `discharge_pressure_kpa` | 토출 압력 | kPa |
| `time_sin` | 시간(사인) | - |
| `time_cos` | 시간(코사인) | - |

### 4-2. hydraulic (수압/유압)

| 피처명 | 한글 이름 | 단위 |
|---|---|---|
| `pressure_roll_mean_10` | 압력 10분 이동평균 | kPa |
| `pressure_trend_10` | 압력 10분 트렌드 | kPa/min |
| `time_sin` | 시간(사인) | - |
| `time_cos` | 시간(코사인) | - |

### 4-3. nutrient (양액/수질)

| 피처명 | 한글 이름 | 단위 |
|---|---|---|
| `air_temp_c` | 실내 기온 | °C |
| `motor_temperature_c` | 모터 온도 | °C |
| `time_sin` | 시간(사인) | - |
| `time_cos` | 시간(코사인) | - |

### 4-4. zone_drip (구역 점적)

| 피처명 | 한글 이름 | 단위 |
|---|---|---|
| `time_sin` | 시간(사인) | - |
| `pressure_flow_ratio` | 압력/유량 비율 | kPa·min/L |
| `motor_temperature_c` | 모터 온도 | °C |
| `time_cos` | 시간(코사인) | - |

---

## 5. 전체 센서/피처 용어집 (한/영 대조)

요청 필드·응답 피처 외에 운영 화면에서 보여줄 수 있는 전체 센서의 한글 이름입니다.

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
| `zone1_valve_on` / `zone2_valve_on` / `zone3_valve_on` | 1/2/3구역 밸브 가동 | 0/1 |
| `zone1_flow_l_min` ~ `zone3_flow_l_min` | 1/2/3구역 유량 | L/min |
| `zone1_pressure_kpa` ~ `zone3_pressure_kpa` | 1/2/3구역 압력 | kPa |
| `zone1_substrate_moisture_pct` ~ `zone3_...` | 1/2/3구역 배지 수분 | % |
| `zone1_substrate_ec_ds_m` ~ `zone3_...` | 1/2/3구역 배지 EC | dS/m |
| `zone1_resistance` ~ `zone3_resistance` | 1/2/3구역 배관 저항 | kPa·min/L |
| `zone1_ec_accumulation` ~ `zone3_...` | 1/2/3구역 염류 축적 | dS/m |
| `zone1_moisture_response_pct` ~ `zone3_...` | 1/2/3구역 수분 반응량 | %/min |
| `supply_balance_index` | 공급 밸런스 지수 | - |
| `flow_drop_rate` | 유량 감소율 | 0~1 |
| `rpm_stability_index` | RPM 안정성 지수 | - |
| `cleaning_event_flag` | 세척 이벤트 | 0/1 |
| `lights_on` | 조명 가동 | 0/1 |

---

## 6. 에러 응답

| HTTP | 의미 | 조치 |
|---|---|---|
| 503 | 로드된 모델 없음 | 서버 기동 로그 확인 — `models/` 폴더 내 artifact 누락 가능 |
| 500 | 추론 중 서버 내부 에러 | `detail` 필드에 원인 메시지, 서버 로그 동시 확인 |

```json
// 500 예시
{ "detail": "Input has wrong dimension..." }
```

---

## 7. 프론트엔드 연동 체크리스트

- [ ] `POST /predict` 에 **평탄한 JSON** 으로 센서값을 보낸다.
- [ ] 응답의 `overall_alarm_level` 로 전체 알람 배지 색을 결정한다.
- [ ] `domain_reports[*].alarm` 으로 도메인별 카드 색을 결정한다.
- [ ] `domain_reports[*].rca_top3` 로 "의심 원인 Top3" 리스트를 띄운다.
- [ ] `domain_reports[*].feature_details` 로 각 피처의 실제값 · 예측값 · 3시그마 밴드 차트를 그린다.
- [ ] `feature.name` 을 위 **도메인별 피처 표**로 한글 라벨로 매핑해서 표시한다.
- [ ] `spike_info.is_anomaly_spike` 가 true 면 "⚡ 이상 스파이크" 배지를 강조한다.
