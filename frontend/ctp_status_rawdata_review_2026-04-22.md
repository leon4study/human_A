# CTP 상태 Raw Data 리뷰

작성일: 2026-04-22

## 결론

`frontend/INFERENCE_API.md` 기준으로 CTP 상태 카드에 바로 넣기 좋은 로우데이터는 아래 4개가 가장 안전하다.

1. `flow_rate_l_min`
2. `discharge_pressure_kpa`
3. `mix_ph`
4. `pump_rpm`

현재 프론트는 CTP 카드에서 `motor_current_a`도 사용하고 있지만, `INFERENCE_API.md`의 요청 예시/Raw 센서 표/`raw_inputs` 설명에는 이 값이 보장되어 있지 않다. 따라서 문서 기준으로는 `pump_rpm`이 더 안전한 대체 후보이다.

## 추천 우선순위

### 1안: 문서 기준으로만 고르면

- `flow_rate_l_min`: 유량 저하는 막힘/공급 이상을 가장 직관적으로 보여준다.
- `discharge_pressure_kpa`: 압력 상승/급변은 배관 저항 증가 신호로 해석하기 쉽다.
- `mix_ph`: 현재 CTP 카드와도 연결되어 있고, 제어 이탈 감시 의미가 분명하다.
- `pump_rpm`: 모터 전류보다 문서 보장성이 높고, 펌프 상태 문맥과도 잘 맞는다.

### 2안: 현행 프론트 구조를 최대한 유지하면

- `flow_rate_l_min`
- `discharge_pressure_kpa`
- `mix_ph`
- `motor_current_a`

단, 이 경우 `motor_current_a`는 `INFERENCE_API.md`에 명시 보강이 필요하다.

## 왜 이 4개가 적합한가

- `flow_rate_l_min`: 현재 CTP 매핑에서도 사용 중이며, 저하 방향 임계치 설계가 쉽다.
- `discharge_pressure_kpa`: 현재 CTP 매핑에서도 사용 중이며, 고압 상태를 경고 카드로 표현하기 좋다.
- `mix_ph`: 영양액 제어 이상을 한눈에 보여줄 수 있다.
- `pump_rpm`: `INFERENCE_API.md`의 시간·상태/파생 피처 설명과도 연결되고, 센서 존재 가능성이 높다.

## 후보지만 CTP 메인 카드에는 비추천

- `suction_pressure_kpa`: 단독 값보다 `discharge`와 조합했을 때 의미가 커서 카드 1칸을 쓰기엔 약하다.
- `motor_power_kw`: 설명력은 있지만 현장 직관성은 RPM/유량보다 약하다.
- `motor_temperature_c`: 느리게 변하는 값이라 CTP의 즉시성에는 덜 맞는다.
- `filter_pressure_in_kpa`, `filter_pressure_out_kpa`: 필터 전용 페이지/보조 카드에는 좋지만 CTP 메인 4종으로 쓰기엔 범용성이 떨어진다.

## 비판적 리뷰 결과

### 확인된 불일치

- 현재 CTP 매핑은 [frontend/src/app/utils/sensorMapping.ts](/c:/Users/human/Desktop/project/human_A/frontend/src/app/utils/sensorMapping.ts:21)에서 `motor-current -> motor_current_a`를 사용한다.
- 하지만 [frontend/INFERENCE_API.md](/c:/Users/human/Desktop/project/human_A/frontend/INFERENCE_API.md:107) 기준 Raw 센서 표에는 `motor_current_a`가 없다.
- 반대로 `pump_rpm`은 [frontend/INFERENCE_API.md](/c:/Users/human/Desktop/project/human_A/frontend/INFERENCE_API.md:109)와 시간·상태 설명, 도메인 피처 설명에 계속 등장한다.

### 해석상 주의

- CTP 상태는 "로우데이터 현재값 카드"인지, "이상징후 카드"인지 성격을 먼저 고정해야 한다.
- 지금처럼 임계치 기반 CTP 카드라면 변화량보다 현장 해석이 쉬운 원시 센서값 위주가 낫다.
- `pressure_flow_ratio`, `dp_per_flow` 같은 값은 CTP 상태보다는 CTP 시각화나 비교분석 쪽이 더 적합하다.

## 수정 메모

이번 리뷰에서 새로 정리한 내용은 아래와 같다.

- CTP 상태용 추천 raw 후보를 문서 기준으로 재선정했다.
- `motor_current_a`는 현행 프론트에는 있으나 `INFERENCE_API.md` 기준 보장되지 않는다는 점을 명시했다.
- 문서 일관성을 우선할 경우 `motor_current_a` 대신 `pump_rpm`을 쓰는 안을 제안했다.

## 최종 제안

가장 무난한 조합:

- `flow_rate_l_min`
- `discharge_pressure_kpa`
- `mix_ph`
- `pump_rpm`

프론트 기존 디자인을 덜 흔들고 싶다면:

- `motor_current_a`를 유지하되 `INFERENCE_API.md`에 해당 필드를 추가 명시한다.

## Threshold 관점 재정리

### 전제

- 현재 `/predict`에서 피처별 threshold가 내려오는 대상은 `per_feature_thresholds`에 잡힌 `scoring_features`뿐이다.
- 따라서 "CTP 카드에 넣을 값"과 "자동 threshold까지 같이 받을 수 있는 값"은 다를 수 있다.

### threshold까지 고려했을 때 우선 추천

raw 성격이 강하면서도 모델 피처와 연결되기 쉬운 값:

1. `flow_rate_l_min`
2. `pump_rpm`
3. `motor_power_kw`
4. `motor_temperature_c`

이 4개가 상대적으로 안전한 이유:

- `flow_rate_l_min`: hydraulic 쪽 actionable feature로 쓰일 가능성이 높다.
- `pump_rpm`: hydraulic/nutrient 쪽에 직접 등장한다.
- `motor_power_kw`: hydraulic 쪽에 직접 등장한다.
- `motor_temperature_c`: hydraulic/nutrient/zone_drip 쪽에 반복 등장한다.

### threshold는 좋지만 raw는 아닌 후보

- `pressure_trend_10`
- `rpm_slope`
- `wire_to_water_efficiency`

이 값들은 threshold와의 연결성은 좋지만, CTP "상태 카드"보다는 분석/시각화 영역에 더 잘 맞는다.

### threshold 연결이 약한 값

- `discharge_pressure_kpa`
- `mix_ph`
- `mix_ec_ds_m`
- `suction_pressure_kpa`
- `filter_pressure_in_kpa`
- `filter_pressure_out_kpa`

이 값들은 raw로는 유용할 수 있지만, 현재 문서 기준 자동 `per_feature_thresholds`가 바로 붙는다고 보기 어렵다.

### threshold까지 포함한 추천 조합

자동 threshold 활용까지 고려하면 CTP 상태 후보는 아래 조합이 가장 현실적이다.

- `flow_rate_l_min`
- `pump_rpm`
- `motor_power_kw`
- `motor_temperature_c`

문서 가독성과 현장 직관을 더 중시하면:

- `flow_rate_l_min`
- `discharge_pressure_kpa`
- `pump_rpm`
- `motor_temperature_c`

이 경우 `discharge_pressure_kpa`는 모델 threshold보다는 프론트의 정적 threshold로 관리하는 편이 자연스럽다.
