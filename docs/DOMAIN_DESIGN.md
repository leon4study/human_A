# DOMAIN_DESIGN — 4개 도메인 분할 기준과 컬럼 매핑

이 문서는 **농장을 왜 4개 도메인으로 나눴고(분할 기준), 각 도메인이 어떤 컬럼을 왜 가지는지**를 정리합니다. 컬럼 전체 사전은 [COLUMNS_REFERENCE.md](COLUMNS_REFERENCE.md)(카테고리별), 모델링 파이프라인은 [MODELING.md](MODELING.md), 피처 근거는 [modeling/09](modeling/09_feature_rationale_ledger.md)를 참조하십시오.

> 코드 출처: 도메인별 입력은 [feature_engineering.py `SENSOR_MANDATORY`](../src/feature_engineering.py), SHAP 타깃은 [train.py `subsystem_targets`](../src/train.py).

---

## 0. 분할 기준 — 흐름 경로의 단계 × 고장 유형

농장을 단일 모델로 보지 않고 4개로 나눈 이유: 한 영역의 노이즈가 다른 영역의 판정을 흐리지 않게, 그리고 운영자가 "어느 단계에서 무슨 문제인지" 바로 알 수 있게 하기 위함입니다.

분할의 축은 **펌프 양액 시스템의 흐름 경로 단계**이며, 각 단계는 **서로 다른 고장 유형 + 인과적으로 함께 움직이는 센서군**을 가집니다.

```
[조제]          [동력]          [가압·전달]        [말단 — 배지]
양액 화학   →   펌프 구동부  →   압력·유량 전달  →   구역 뿌리 환경
nutrient        motor            hydraulic           zone_drip
(EC/pH)        (전기·기계)      (막힘·누수)         (배지 수분·EC)
```

각 도메인이 좋은 묶음인 이유는 두 가지를 동시에 만족하기 때문입니다.
1. **인과적 공동 변동**: 같은 도메인 센서는 물리적으로 함께 움직인다(전류↑→발열·진동↑ / 막힘→압력↑·유량↓).
2. **고장 유형 분리**: 도메인마다 잡으려는 고장이 다르다(기계 마모 ≠ 배관 막힘 ≠ 화학 이탈 ≠ 노즐 막힘).

---

## 1. motor — 구동부 (펌프 동력원)

- **정의**: 펌프를 돌리는 모터·베어링의 전기·기계 건전성.
- **고장 유형**: 베어링 마모, 모터 과부하, 권선 절연 열화.
- **SHAP 타깃**: `motor_current_a`, `rpm_stability_index`
- **입력 컬럼 (SENSOR_MANDATORY)**

| 컬럼 | 종류 | 의미 |
|---|---|---|
| `motor_power_kw` / `motor_current_a`(타깃) | Raw | 모터 소비 전력·전류 |
| `motor_temperature_c` / `bearing_temperature_c` | Raw | 모터·베어링 온도 |
| `bearing_vibration_rms_mm_s` | Raw | 베어링 진동 |
| `pump_rpm` / `rpm_slope` | Raw/파생 | 회전수·변화율 |
| `wire_to_water_efficiency` | 파생 | 전기→수력 변환 효율 |
| `temp_slope_c_per_s` | 파생 | 온도 변화율(과부하 징후) |
| `bearing_thermal_margin` | 파생 | 베어링−모터 온도차(윤활 불량) |
| `load_per_speed` | 파생 | 전류/RPM(기계적 마찰) |

- **왜 한 묶음**: 전기 부하가 오르면 전류·전력이 오르고 발열·진동으로 이어진다. 기계 마모는 RPM 불안정·진동으로 나타난다. 모두 "모터가 얼마나 무리하나"의 같은 인과 사슬.

---

## 2. hydraulic — 가압·전달 (압력·유량)

- **정의**: 펌프가 만든 압력·유량이 배관으로 전달되는 과정의 건전성.
- **고장 유형**: 배관 막힘, 누수, 밸브 이상, 필터 오염.
- **SHAP 타깃**: `zone1_resistance`, `differential_pressure_kpa`
- **입력 컬럼 (SENSOR_MANDATORY)**

| 컬럼 | 종류 | 의미 |
|---|---|---|
| `flow_rate_l_min` | Raw | 메인 유량 |
| `discharge_pressure_kpa` / `suction_pressure_kpa` | Raw | 토출·흡입 압력 |
| `flow_drop_rate` | 파생 | 유량 하락률(막힘) |
| `pressure_flow_ratio` / `system_resistance` | 파생 | 배관 저항(막힘 직격) |
| `hydraulic_power_kw` / `specific_energy` | 파생 | 수력 동력·단위유량당 전력 |
| `filter_delta_p_kpa` | 파생 | 필터 차압 |
| `pressure_trend_10` / `flow_trend_10` | 파생 | 압력·유량 추세 |
| `supply_balance_index` | 파생 | 구역 유량 합/메인 유량 = 유량 균형(누수 탐지) |

- **왜 한 묶음**: 압력과 유량은 하나의 유체계다. 막히면 압력↑·유량↓이 동시에 일어난다. `supply_balance_index`는 유량 균형 지표라(2026-06-02 zone_drip에서 이동) 유량 도메인인 hydraulic에 속한다.

---

## 3. nutrient — 양액 화학 (조제 조성) · 보조 지표

- **정의**: 조제 탱크에서 섞인 양액의 화학 조성(EC/pH) 상태.
- **고장 유형**: A/B액 배합 비율 오류, EC/pH 센서 드리프트, 염류 축적.
- **운영**: **종합 알람 voting에서 제외**(`EXCLUDE_FROM_OVERALL={"nutrient"}`). 화학 센서 신뢰도 한계로 1차 알람이 아니라 보조 모니터링 채널. 배경은 [ANALYSIS.md §1-3](ANALYSIS.md).
- **SHAP 타깃**: `pid_error_ec`, `salt_accumulation_delta`
- **입력 컬럼 (SENSOR_MANDATORY)**

| 컬럼 | 종류 | 의미 |
|---|---|---|
| `mix_ec_ds_m` / `mix_ph` | Raw | 조제 탱크 현재 EC·pH |
| `mix_target_ec_ds_m` | Raw | 조제 목표 EC |
| `drain_ec_ds_m` | Raw | 배액 EC(염류 축적 단서) |
| `mix_temp_c` | Raw | 조제 탱크 온도 |
| `pid_error_ph` | 파생 | pH 제어 오차 |
| `ph_trend_30` | 파생 | pH 30분 추세(드리프트) |

- **왜 한 묶음**: EC/pH는 화학량으로, 기계 도메인(압력·전류)과 독립 축이다. 화학 신호의 노이즈가 물리 도메인 판정을 오염시키지 않도록 별도 도메인으로 격리했다.

---

## 4. zone_drip — 구역 배지(substrate) 상태 (말단)

> 코드 키는 `zone_drip`(점적, 파급 때문에 유지)이나, 개념상 정확한 이름은 **"구역 배지 상태"**다. supply_balance_index를 hydraulic으로 보낸 뒤(2026-06-02) 순수 배지 상태 도메인이 됐다.

- **정의**: 흐름의 말단, 각 구역 뿌리의 배지(코코피트 등 재배 매질) 수분·EC 상태.
- **고장 유형**: 점적 노즐 막힘, 구역 관수 불균일, 배지 염류 축적.
- **SHAP 타깃**: `zone1_moisture_response_pct`, `zone1_ec_accumulation`
- **입력 컬럼 (SENSOR_MANDATORY)**

| 컬럼 | 종류 | 의미 |
|---|---|---|
| `zone1_substrate_moisture_pct` | Raw | 구역 배지 수분 |
| `zone1_substrate_ec_ds_m` | Raw | 구역 배지 EC |
| `zone_ec_variance` | 파생 | 구역 간 배지 EC 편차(국부 막힘) |
| `zone_moisture_variance` | 파생 | 구역 간 수분 편차(관수 불균일) |
| `substrate_ec_accum_rate` | 파생 | 배지 EC 변화율(염류 집적 속도) |

- **왜 한 묶음**: 모두 "물·양분이 뿌리에 제대로 도달했는가"의 결과 신호다. 배지 수분·EC는 펌프와 무관한 구역 고유 정보이며, 구역 간 편차(variance)는 특정 라인만 막히는 국부 이상을 잡는다.

---

## 5. 경계 사례 (도메인에 안 들어가는 것들)

| 항목 | 처리 | 이유 |
|---|---|---|
| **필터** | AE 도메인 아님 → **룰 기반 페이지** | 학습 데이터에 막힘 시나리오 부족, 단일 변수 신호 약함([modeling 메모리]). `filter_delta_p` 임계(경고 15·위험 25 kPa) |
| **zone 2·3 raw** | AE 입력에서 drop(다중공선성) | 단일 펌프 연동으로 zone1과 중복. 단, **구역 편차(variance) 계산엔 사용** |
| **펌프 압력/유량의 zone 버전** | hydraulic이 메인 라인으로 대표 | 구역별 압력/유량은 펌프와 공선성이라 개별로는 미사용 |
| **시간·운전 맥락**(time, pump_on, minutes_since_startup) | 전 도메인 공통 입력, 단 점수/RCA에서 제외 | 정상 패턴의 조건일 뿐 알람 근거 아님([inference_core](../src/inference_core.py)) |

---

## 6. 분할 평가 요약

| 도메인 | 응집도 | 비고 |
|---|---|---|
| motor | 높음 | 전기·기계 인과 사슬 명확 |
| hydraulic | 높음 | 단일 유체계. supply_balance 편입으로 유량 일원화 |
| nutrient | 높음 | 화학 독립 축. 보조 지표(voting 제외) |
| zone_drip | 높음(개선됨) | supply_balance 분리로 순수 배지 상태가 됨 |

**핵심 원칙(향후 새 피처 배정 시)**:
- 컬럼을 도메인에 넣을 때는 "이 컬럼이 어느 흐름 단계의, 어느 고장을 반영하나"로 판단한다.
- 유량·압력 계열 → hydraulic, 전기·진동·RPM → motor, EC/pH 조제 → nutrient, 배지·구역 편차 → zone_drip.
- 한 컬럼이 두 도메인에 걸치면(예: supply_balance), **물리량의 본질**(유량)로 귀속시킨다.
