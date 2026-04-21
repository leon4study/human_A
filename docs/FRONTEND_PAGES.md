# 🖥️ 프론트엔드 페이지 구성 스펙

프론트 작업자 질의 — "설비별 페이지에 뭘 그려야 하나? AI 분석 페이지엔 뭐가 들어가나? 비교분석 지표는? CTP 시각화? 타임라인 간격?" — 에 대한 답을 **현재 코드 기준**으로 정리한 문서.

실제 API 응답 스키마(필드명·타입·단위)는 [INFERENCE_API.md](./INFERENCE_API.md)에 있다. 이 문서는 **페이지 설계** 관점.

---

## 0. 서버가 인식하는 "설비(도메인)" 4개 + 필터

[src/train.py:242-270](../src/train.py#L242-L270)에서 정의된 4개 서브시스템 = 페이지 4개. 필터는 별도 AE 모델 없이 **룰 기반 페이지**로 추가 권장(§1-5).

| 도메인 코드 | 페이지명 | AE 모델 여부 |
|---|---|---|
| `motor` | 모터 | ✅ |
| `hydraulic` | 수압/유압 | ✅ |
| `nutrient` | 양액/수질 | ✅ |
| `zone_drip` | 구역 점적 | ✅ |
| (없음) | 필터 | ❌ 룰 기반 (§1-5) |

---

## 1. 설비별 페이지에 들어갈 시각화/정보

### 1-1. 🔧 Motor (모터)

**원시 센서 (시계열 차트)**
- `motor_current_a` (모터 전류)
- `motor_power_kw` (모터 전력)
- `motor_temperature_c` (모터 온도)
- `pump_rpm` (펌프 회전수)
- `bearing_vibration_rms_mm_s` (베어링 진동)
- `bearing_temperature_c` (베어링 온도)

**파생 지표 (게이지/트렌드)**
- `rpm_stability_index` — RPM이 목표 대비 얼마나 흔들리는지 (공기 유입·난류 징후). 정의: `abs(rpm - rpm_mean_10) / (rpm_mean_10 + ε)` [preprocessing.py:193-196](../src/preprocessing.py#L193-L196)
- `temp_slope_c_per_s` — 초당 모터 온도 변화율. 정의: `diff(motor_temperature_c) / dt_seconds` [preprocessing.py:184](../src/preprocessing.py#L184)
- `wire_to_water_efficiency` — 전력 → 수력 변환 효율. 정의: `hydraulic_power_kw / (motor_power_kw + ε)` [preprocessing.py:154-156](../src/preprocessing.py#L154-L156)

**3σ 밴드 차트**
→ `/predict` 응답의 `domain_reports.motor.feature_details[i].bands` 그대로 사용.

---

### 1-2. 💧 Hydraulic (수압/유압)

**원시 센서**
- `discharge_pressure_kpa` (토출 압력)
- `suction_pressure_kpa` (흡입 압력)
- `flow_rate_l_min` (메인 유량)
- `zone1_pressure_kpa`, `zone1_flow_l_min` (1구역)

**파생 지표**
- `differential_pressure_kpa = discharge − suction` (차압 추이) [preprocessing.py:85-87](../src/preprocessing.py#L85-L87)
- `pressure_flow_ratio`, `dp_per_flow` — 배관 저항·막힘/누수 조기감지 (§2-2 비교분석)
- `flow_drop_rate` — 유량 감소율 (0=정상, 1=완전막힘) [preprocessing.py:126-137](../src/preprocessing.py#L126-L137)
- `hydraulic_power_kw` — 유효 수력 동력 [preprocessing.py:148-150](../src/preprocessing.py#L148-L150)
- `zone1_resistance = zone1_pressure / zone1_flow` [preprocessing.py:312-314](../src/preprocessing.py#L312-L314)

---

### 1-3. 🧪 Nutrient (양액/수질)

**원시 센서**
- `mix_ec_ds_m`, `mix_ph` (현재 조제)
- `mix_target_ec_ds_m`, `mix_target_ph` (목표)
- `drain_ec_ds_m` (배액 EC)
- `tank_a_level_pct` (A 비료통 수위)

**파생 지표**
- `pid_error_ec = mix_ec − mix_target_ec` (제어 오차) [preprocessing.py:203](../src/preprocessing.py#L203)
- `pid_error_ph` [preprocessing.py:204](../src/preprocessing.py#L204)
- `salt_accumulation_delta = drain_ec − mix_ec` (염분 축적) [preprocessing.py:210-212](../src/preprocessing.py#L210-L212)
- `ph_instability_flag` — pH > 6.5 침전 임계 [preprocessing.py:207](../src/preprocessing.py#L207)
- `tank_a_est_hours_to_empty` — 고갈 예상시간 [preprocessing.py:265-279](../src/preprocessing.py#L265-L279)

---

### 1-4. 🌱 Zone Drip (구역 점적)

**원시 센서**
- `zone1_flow_l_min`, `zone1_pressure_kpa`
- `zone1_substrate_moisture_pct`, `zone1_substrate_ec_ds_m`

**파생 지표**
- `zone1_resistance` (배관 저항) [preprocessing.py:312-314](../src/preprocessing.py#L312-L314)
- `zone1_moisture_response_pct` (급액 후 수분 반응) [preprocessing.py:304-307](../src/preprocessing.py#L304-L307)
- `zone1_ec_accumulation = zone1_substrate_ec − mix_ec` (배지 염류 축적) [preprocessing.py:317-319](../src/preprocessing.py#L317-L319)
- `supply_balance_index = Σzone_flow / main_flow` (누수 탐지) [preprocessing.py:292-297](../src/preprocessing.py#L292-L297)

> 2구역·3구역은 [preprocessing.py:601-623](../src/preprocessing.py#L601-L623)의 `collinear_drop_list`에서 다중공선성으로 제외돼 모델 입력엔 안 들어가지만, 운영 대시보드에는 원시값 표시 가능.

---

### 1-5. 🧃 Filter (필터) — ⚠️ AE 모델 없음, 룰 기반 페이지

**결정 근거 (2026-04-21 상관분석, dabin.csv 43,200행 기준):**

| 비교 | Pearson r | 해석 |
|---|---:|---|
| `filter_pressure_in` vs `discharge_pressure` | **0.757** | 비슷하게 움직이나 중복은 아님 |
| `filter_pressure_in` vs `filter_pressure_out` | **0.994** | 완전 중복 → `filter_pressure_out` 이미 drop됨 [preprocessing.py:621](../src/preprocessing.py#L621) |
| `filter_delta_p` vs `pump_delta_p` | **0.374** | **독립 정보** — 펌프 상태 ≠ 필터 오염도 |

**핵심**: 필터 ΔP는 펌프 ΔP와 **독립적인 고장 모드**(막힘). 다만 현재 학습 데이터(`dabin.csv`)엔 필터 막힘 시나리오가 거의 없어(`filter_delta_p` CV=3.1%, `hidden_risk_stage=watch`에서도 +0.26 kPa만 상승) AE에 넣어봤자 SHAP이 "중요도 낮음"으로 판정할 확률이 높음 → **AE에 넣는 건 비용 대비 효과 낮음**.

**프론트 처리 방식 (권장)**:
- 원시 센서 차트: `filter_pressure_in_kpa`, `filter_pressure_out_kpa`
- 파생(클라이언트 계산): `filter_delta_p_kpa = filter_pressure_in − filter_pressure_out`
- 알람 규칙: 정적 임계 (예: `filter_delta_p > 15 kPa` 경고, `> 25 kPa` 위험). 실측 mean≈7.4 kPa / max≈8.34 kPa 기준에서 2배 이상 튀면 막힘 의심.

> **주의**: 현재 `/predict` 응답의 `raw_inputs` passthrough에 `filter_pressure_in/out`은 **포함되지 않음** ([inference_api.py:538-548](../src/inference_api.py#L538-L548)). 프론트에서 필터 페이지를 띄우려면 (a) API에 passthrough 추가하거나 (b) 프론트가 request 전송 시 값 자체 보관. → 본 문서 업데이트와 함께 (a) 방식으로 API 수정 예정.

---

## 2. AI 분석 페이지 구성

`/predict` 응답 한 덩어리로 아래 UI를 모두 그릴 수 있음. 실제 스키마는 [INFERENCE_API.md §4](./INFERENCE_API.md#4-응답-response).

### 2-1. 페이지 블록 매핑

| UI 블록 | 응답 키 | UI 제안 |
|---|---|---|
| **종합 알람 배너** | `overall_alarm_level` (0~3), `overall_status` | 상단 배지 — 4색 (Normal🟢 / Caution🔸 / Warning🟠 / Critical🔴) |
| **스파이크 배지** | `spike_info.{is_spike, is_startup_spike, is_anomaly_spike}` | "기동 스파이크(회색)" vs "⚡이상 스파이크(빨강)" 구분 |
| **도메인별 카드 4개** | `domain_reports.{motor|hydraulic|nutrient|zone_drip}` | 탭 or 그리드 |
| ├ MSE 게이지 | `.metrics.current_mse` vs `.global_thresholds` | 4색 게이지 (caution/warning/critical 라인 오버레이) |
| ├ **원인진단(RCA)** | `.rca_top3` = [{feature, contribution%}, …] | 도넛/바차트 Top3 |
| ├ 피처별 상태 | `.feature_details[i].{actual_value, expected_value, bands, feature_alarm}` | 피처마다 3σ 밴드 차트 + 실측점 |
| ├ 정상 기준선 | `.target_reference_profiles.{target}.{target_lines, related_feature_lines}` | "학습기간 정상 범위" 오버레이 |
| └ 모델 성능 결과 | `.metrics.{train_loss, val_loss}` | 사이드 인포 (작게) |
| **원시값 passthrough** | `raw_inputs` | 프론트 비교분석 파생 계산용 (§2-2) |

### 2-2. "비교분석" 탭 — 네가 적은 지표 6개 현황

| 지표 | 수식 | 현재 코드 위치 | 프론트 확보 경로 |
|---|---|---|---|
| `pressure_flow_ratio` | `discharge / (flow + ε)` | ✅ `extract_interpretation_features` [preprocessing.py:455-457](../src/preprocessing.py#L455-L457) | **인코딩 활용 여부 검토 중**. 현재는 해석용 스칼라. 프론트는 `raw_inputs`로 자체 계산 권장 |
| `dp_per_flow` | `(discharge − suction) / (flow + ε)` | ✅ [preprocessing.py:462-464](../src/preprocessing.py#L462-L464) | 프론트 자체 계산 (`raw_inputs` 사용) |
| `flow_per_power` (**유량 대비 전력 효율**) | `flow / (motor_power + ε)` | ✅ [preprocessing.py:476-478](../src/preprocessing.py#L476-L478) | 프론트 자체 계산 |
| `pressure_per_power` (**압력 대비 전력 효율**) | `discharge / (motor_power + ε)` | ✅ [preprocessing.py:469-471](../src/preprocessing.py#L469-L471) | 프론트 자체 계산 |
| 압력 변동성 (`std/IQR`) | `rolling_std / rolling_IQR` | ❌ **없음** | 프론트 링버퍼로 자체 계산 (§3 12h window) |
| 유량 변동성 (CV=`std/mean`) | `rolling_std / rolling_mean` | ❌ **없음** | 프론트 링버퍼로 자체 계산 |
| **온도 변화율** `temp_slope` | `diff(T) / dt_seconds` | ✅ `temp_slope_c_per_s` [preprocessing.py:184](../src/preprocessing.py#L184) | `/predict`의 `feature_details`에서 또는 프론트 자체 계산 |

> **⚠️ `pressure_flow_ratio` 정의 주의**: [preprocessing.py:225-227](../src/preprocessing.py#L225-L227)의 모델 입력용 버전은 `differential_pressure / flow`, 해석용 [preprocessing.py:455-457](../src/preprocessing.py#L455-L457)은 `discharge / flow`. 프론트 표시용은 **해석용 공식(토출/유량)** 으로 통일. 인코딩 활용(= 모델 입력으로 사용) 여부는 아직 미정 상태.

**프론트 링버퍼 필요한 2개(압력/유량 변동성) 구현 힌트**:

```ts
type RingBuffer = {
  discharge_pressure: number[];  // max size = 720 (12h @ 1min)
  flow_rate: number[];           // max size = 720
};

// 매 /predict 응답마다:
//   buf.discharge_pressure.push(raw_inputs.discharge_pressure_kpa)
//   if (buf.discharge_pressure.length > 720) buf.discharge_pressure.shift()
//
// 그리고:
//   pressure_iqr = q75 - q25 of buf.discharge_pressure
//   pressure_volatility = std(buf.discharge_pressure) / (pressure_iqr + ε)
//   flow_cv = std(buf.flow_rate) / (mean(buf.flow_rate) + ε)
```

---

## 3. 타임라인 & CTP(Critical Trouble Point) 시각화

### 3-1. 샘플링·집계 간격 현황

| 레이어 | 간격 | 근거 |
|---|---|---|
| 원시 수집 | 1분 | `dabin.csv` 스키마 |
| 학습 집계 | sliding **5분 윈도우 / 1분 슬라이드** | [preprocessing.py:574-577](../src/preprocessing.py#L574-L577) |
| 추론 배치 | **1분 간격 S3 폴링** | [inference_api.py:82-91](../src/inference_api.py#L82-L91) |
| 변동성 윈도우 (프론트) | **12시간** | 프론트 측 요구사항 |

→ 프론트 기본 X축 해상도는 **1분**. 12h 변동성은 링버퍼 720점.

### 3-2. CTP 시각화 제안

타임라인 위에:
- `overall_alarm_level ≥ 2` 시점 → **마커** 찍기 (주황/빨강)
- 클릭 시 팝업: `rca_top3` + 해당 시점 `feature_details` (실측/예측/밴드)
- `is_anomaly_spike = true`인 시점 → ⚡ 빨간 마커 별도 레이어
- `is_startup_spike = true` 시점은 회색 마커로 약하게(정상 과도 구동이라 무시 가능)

---

## 4. 변경/추가되는 데이터 정보

### 4-1. 🆕 프론트가 새로 만들어야 할 파생 (API 스키마 변경 없음)

| 컬럼명 | 공식 | 단위 | 버퍼 크기 |
|---|---|---:|---|
| `pressure_volatility` | `std(discharge_P) / (iqr(discharge_P) + ε)` | - | 12h = 720점 |
| `flow_cv` | `std(flow) / (mean(flow) + ε)` | - | 12h = 720점 |

→ 이 2개는 백엔드 스키마 변경 없이 프론트 자체 계산만으로 가능.

### 4-2. 📥 API 쪽 스키마 변경 (필터 페이지 지원)

`/predict` 응답의 `raw_inputs` 블록에 **필터 압력 2개 추가**:

```diff
 "raw_inputs": {
   "discharge_pressure_kpa": ...,
   "suction_pressure_kpa": ...,
   "flow_rate_l_min": ...,
   "motor_power_kw": ...,
   "motor_temperature_c": ...,
-  "pump_rpm": ...
+  "pump_rpm": ...,
+  "filter_pressure_in_kpa": ...,
+  "filter_pressure_out_kpa": ...
 }
```

적용 후 프론트는 `raw_inputs.filter_pressure_in_kpa - raw_inputs.filter_pressure_out_kpa`로 `filter_delta_p_kpa` 계산 가능.

### 4-3. 응답 전체 구조 요약

상세 스키마·타입·단위는 [INFERENCE_API.md §4](./INFERENCE_API.md#4-응답-response) 참조. 여기선 요약만:

```
{
  timestamp, overall_alarm_level, overall_status,
  spike_info: { is_spike, is_startup_spike, is_anomaly_spike },
  raw_inputs: { discharge_P, suction_P, flow, motor_power, motor_temp, pump_rpm,
                filter_P_in, filter_P_out },  // ← 필터 2개 추가 예정
  domain_reports: {
    motor | hydraulic | nutrient | zone_drip: {
      metrics, alarm, global_thresholds, per_feature_thresholds,
      rca_top3, feature_details, target_reference_profiles
    }
  },
  action_required
}
```

---

## 5. 프론트에 전달할 체크리스트

- [ ] 설비 페이지 4개 + 필터 페이지 1개(룰 기반) 설계
- [ ] 필터 페이지: `filter_delta_p_kpa = in − out` 클라이언트 계산, 정적 임계 (경고 15 kPa / 위험 25 kPa)
- [ ] AI 분석 페이지: `domain_reports[*]` 한 덩어리로 MSE 게이지 + RCA 도넛 + 피처 3σ 밴드 + 기준선 렌더
- [ ] 비교분석 7개 지표 중 **5개**는 `raw_inputs` 기반 프론트 자체 계산, **2개(변동성)** 는 링버퍼 720점 기반 자체 계산
- [ ] `pressure_flow_ratio`는 **토출/유량** 공식으로 통일 (해석용 정의). 인코딩 활용은 백엔드 추후 결정사항
- [ ] `flow_per_power` = 유량 대비 전력 효율, `pressure_per_power` = 압력 대비 전력 효율 (이름-수식 일치)
- [ ] 타임라인 X축 1분, 변동성 창 12h (720점 링버퍼)
- [ ] CTP 마커: `overall_alarm_level ≥ 2` + `is_anomaly_spike` 별도 레이어
- [ ] `is_startup_phase=1` 구간은 알람 억제됨 ([inference_api.py:476-480](../src/inference_api.py#L476-L480)) → UI에도 "기동 중" 배지 표시
