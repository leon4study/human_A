# 📊 ANALYSIS — 데이터 분석 및 인사이트

이 문서는 **데이터 출처 → EDA → 도메인 정의 → SHAP 인사이트** 순서로 프로젝트의 데이터 분석 흐름을 정리합니다.
- 양액·점적관수·CNL 핀·딸기 재배 환경 등 **도메인 배경지식**: [DOMAIN_KNOWLEDGE.md](DOMAIN_KNOWLEDGE.md)
- **모델 학습 파이프라인**: [MODELING.md](MODELING.md)
- **컬럼 단위 정의**: [COLUMNS_REFERENCE.md](COLUMNS_REFERENCE.md)

---

## 1. 데이터 출처

### 1-1. 기초 자료 — AI-hub 딸기 재배환경 센서 데이터
- 기초 데이터: **㈜우성미디어서비스 — 딸기 재배환경 센서 데이터** (AI-hub)
- 활용 항목: 내부 온도, 습도, CO₂, 광량, 양액 EC, 양액 pH, 배지 EC 등
- 활용 방식: 평균값과 편차를 추출 → 실제 딸기 농가 환경의 통계적 분포를 모방한 가상 데이터 생성의 기준치로 사용

### 1-2. 가상 데이터 합성 (data_gen)
양액펌프·펌프 부하·관로 압력 등 우리 프로젝트가 필요로 하는 **물리/유압 데이터는 AI-hub 데이터셋에 존재하지 않습니다.** 따라서 다음 절차로 합성:

1. 자료조사 기반으로 **45개 변수** 선정 (센서 + 물리량)
2. 1분 단위 raw 데이터를 **3개월 분량** 생성
3. 변수 간 상관관계를 도메인 지식 기반으로 반영 (예: 점적 노즐 막힘률 → 차압 상승 → 유량 감소 → 펌프 부하 증가)
4. 정상/이상 시나리오를 분리해 라벨링

> 관련 코드: [services/inference/src/data_gen_jun.py](../services/inference/src/data_gen_jun.py), [data_gen_dabin.py](../services/inference/src/data_gen_dabin.py), [data_gen_test.py](../services/inference/src/data_gen_test.py)

### 1-3. 화학 센서(EC/pH) 학습 배제 결정
**왜 배제했나** — EC/pH는 화학 센서 특성상 양액에 상시 노출되어 다음 문제가 잦습니다:
- 미생물막(biofilm) 형성으로 인한 오감지
- 스케일(석회·염류 침전)에 의한 측정값 왜곡
- 잦은 보정·교체 필요 → 현장 신뢰도 ↓

→ **현실 반영도 측면에서 신뢰성 있는 결과를 위해, 가상 데이터 자체에는 EC/pH 값이 포함되어 있어도 학습 입력 피처에서는 제외**했습니다. 실제 학습은 압력·유량·전류·온도·진동·RPM 등 **물리 센서**에 집중합니다.

(*nutrient 도메인의 `pid_error_ec`, `salt_accumulation_delta`는 raw EC가 아닌 *오차/축적* 형태의 파생 지표라 별도 취급. 운영상으로도 [evaluate_test_metrics.py:41](../services/inference/src/evaluate_test_metrics.py#L41)에서 `EXCLUDE_FROM_OVERALL = {"nutrient"}`로 voting 제외 — **이유: EVAL FP 581건 중 547건(94%)이 nutrient에서 발생, 단독으로 잡은 진짜 이상은 0건**. [PROJECT_BRIEF.md §5-1](PROJECT_BRIEF.md) 참조.*)

## 2. EDA 결과 요약

### 2-1. 결측치·이상치
- 1분 단위 시계열의 자연스러운 결측은 선형 보간 + backward fill로 복구 ([MODELING.md §3](MODELING.md))
- IQR 꼬리 절단을 **의도적으로 사용하지 않음** — 매일 아침 정상 기동(startup) overshoot까지 이상으로 학습되어 알람이 폭주하기 때문 (물리적 메커니즘은 [DOMAIN_KNOWLEDGE.md §3](DOMAIN_KNOWLEDGE.md))

### 2-2. "막힘" 정의
**막힘 = 점적 노즐·관로의 점진적 폐쇄 현상** 으로, 다음과 같이 데이터에 발현:

| 단계 | 관측되는 변화 |
|---|---|
| 초기 | 차압(`differential_pressure_kpa`) 미세 상승, 유량 미세 감소 (-1~3%) |
| 중기 | 유량이 **계단식으로 감소** (스크립트 기준 약 **-2.9% 단위**), 시간이 갈수록 정상 대비 차이가 점점 벌어짐 |
| 후기 | 펌프 RPM·전류·온도 동반 상승, 모터 과부하 신호 |

→ **유량 감소율이 가장 빨리 잡히는 1차 신호**, 모터 측 변화는 후행 지표입니다.

> 막힘의 화학·생물·물리적 원인과 발현 흐름의 자세한 설명: [DOMAIN_KNOWLEDGE.md §2](DOMAIN_KNOWLEDGE.md)

### 2-3. 정상 시나리오 vs 이상 시나리오 비교
정상/이상 라벨 시나리오에서 도메인 핵심 변수의 분포 차이를 확인 → 4개 도메인 분리 학습이 단일 모델보다 신호 대 잡음비가 좋다는 근거 확보.

> 관련 노트북:
> - [notebooks/EDA.ipynb](../notebooks/EDA.ipynb), [EDA_2.ipynb](../notebooks/EDA_2.ipynb), [EDA_jun.ipynb](../notebooks/EDA_jun.ipynb)
> - [notebooks/dabin_EDA_jun.ipynb](../notebooks/dabin_EDA_jun.ipynb)
> - [notebooks/Hypothesis_Testing.ipynb](../notebooks/Hypothesis_Testing.ipynb) — 정상/이상 평균 차이 통계 검정
> - [notebooks/data_filtering.ipynb](../notebooks/data_filtering.ipynb) — 필터 막힘 룰 검증

## 3. 4개 도메인 정의

농장을 단일 모델로 보지 않고 **4개 도메인으로 분리한 이유** — 외부 환경(광량·기온)과 작물 상태에 따라 정상 범위가 계속 변하기 때문에, 단일 임계값으로는 이상 판단이 불가능합니다. 도메인별로 *동적 정상 상태*를 학습하는 Health Index를 생성합니다.

### 3-1. 🔧 MOTOR — 모터/구동부
**관심사** — 펌프 모터의 에너지 소비, 회전 안정성, 베어링 상태
**핵심 입력** — `motor_current_a`, `motor_power_kw`, `motor_temperature_c`, `pump_rpm`, `bearing_vibration_rms_mm_s`, `wire_to_water_efficiency`
**탐지 이상** — 베어링 마모 / 과부하 / 권선 절연 열화 / 임펠러 손상
**현장 영향** — 모터 진동·과열로 돌발 정지 시 *전체 관수 중단* (수 시간 이상) → 재배사 전체 작물 동시 수분 미공급

### 3-2. 💧 HYDRAULIC — 수력/유량
**관심사** — 관로 압력차, 유량, 시스템 곡선 이탈
**핵심 입력** — `flow_rate_l_min`, `discharge_pressure_kpa`, `suction_pressure_kpa`, `differential_pressure_kpa`, `filter_delta_p_kpa`
**탐지 이상** — 배관 막힘 / 누수 / 밸브 이상
**현장 영향** — 특정 구역에 급수 편차 → 부족 구역 시들음, 과잉 구역 뿌리 부패 / 펌프 캐비테이션으로 임펠러 손상

### 3-3. 🧪 NUTRIENT — 양액/수질
**관심사** — 양액 조성의 PID 제어 오차, 염류 축적 추이
**핵심 입력** — `pid_error_ec`, `pid_error_ph`, `salt_accumulation_delta`, `mix_target_ec_ds_m` (raw EC/pH는 학습 배제 — §1-3)
**탐지 이상** — A/B액 투입 비율 오류 / EC 센서 드리프트 / 양액펌프 막힘 / 원수 공급 불량
**현장 영향** — 잘못된 농도 → 염류 장해(뿌리 끝 갈변·흡수 장애) → 엽소 → 수율 저하·비료 낭비

### 3-4. 🌱 ZONE_DRIP — 구역 점적
**관심사** — 구역별 관수 응답·배지 환경
**핵심 입력** — `zone1_flow_l_min`, `zone1_pressure_kpa`, `zone1_substrate_moisture_pct`, `zone1_substrate_ec_ds_m`, `zone1_resistance`, `supply_balance_index`
**탐지 이상** — 점적 노즐 막힘·빠짐 / 배지 염류 축적 / 드리퍼 유량 불균일 / 배수 불량
**현장 영향** — 구역별 관수 편차 확대 → 일부 구역만 뿌리 염해 또는 시들음 → 재배사 내 품질 불균일

> 도메인별 입력 피처 정의: [services/inference/src/feature_engineering.py:50-88](../services/inference/src/feature_engineering.py#L50-L88) (`SENSOR_MANDATORY`)
> 도메인별 SHAP 타깃: [services/inference/src/train.py:242-270](../services/inference/src/train.py#L242-L270)

### 3-5. 필터 막힘 — 룰 기반 (AE 미사용)
필터 차압(`filter_delta_p_kpa`) 단일 변수의 신호 대 잡음비가 약하고(상관계수 r=0.37), 학습 데이터에 명확한 막힘 사례가 부족해 **별도 AE를 만들지 않고 프론트 룰 기반 페이지로 운영**합니다. (참고: [FRONTEND_PAGES.md §1-5](FRONTEND_PAGES.md))

## 4. SHAP 기반 인사이트

[SHAP](https://github.com/shap/shap)으로 4개 도메인 AE의 재구성 오차에 가장 크게 기여하는 피처를 분석했습니다. 분석 결과는 RCA(근본 원인 분석)의 근거로 사용되며, 프론트엔드에서 beeswarm으로 시각화됩니다 ([SHAP_BEESWARM_FRONTEND.md](SHAP_BEESWARM_FRONTEND.md)).

### 4-1. 도메인별 핵심 발견

#### 🔧 MOTOR — 에너지 소비 및 유량 안정성
- **Energy Driver**: `motor_power_kw`, `motor_current_a` 가 높을 때 → 강한 이상 신호 (과부하)
- **Flow Signal**: `flow_rate_l_min` 이 *낮을 때* SHAP 값 상승 → 저유량 상태가 이상 신호
- **Secondary**: `rpm_stability_index` 불안정 → 오차 증가
- **추천 파생변수**: `Power / Flow Rate` (단위 유량당 소모 전력) — 펌프 효율 저하(노즐 막힘) 더 민감하게 포착

#### 🧪 NUTRIENT — 양액 밸런스 및 축적
- **Accumulation Driver**: `salt_accumulation_delta` 클 때 → 양액 공급 불균형 핵심 지표
- **Environmental Baseline**: `daily_light_integral` (DLI) 낮을 때 → 광량 부족 시 비정상 양액 흡수 패턴
- **Operational**: `raw_tank_level_pct` 낮을 때 → 모델이 민감하게 반응
- **추천 파생변수**: `DLI-EC Ratio` — 빛 대비 양액 흡수율로 식물 활성도 추적

#### 🌱 ZONE_DRIP — 구역 관수 및 토양 환경
- **Core Driver**: `zone1_ec_accumulation` → SHAP 값이 압도적으로 길게 뻗음 (염류 집적이 결정적 단서)
- **Hydraulic Response**: `zone1_moisture_response_pct` 높을 때 → 과관수 또는 센서 오작동
- **Energy/Light**: `daily_light_integral` 낮을 때 → 오차 발생 가능성 ↑
- **추천 파생변수**: `Moisture Lag Time` — 관수 시작부터 토양 수분 반응까지의 지연 시간 (드립 노즐 막힘 직접 감지)

#### 💧 HYDRAULIC — 유압 및 관로 부하
- **압도적 1순위**: `differential_pressure_kpa` 가 높을 때 → SHAP 가장 길게 뻗음 (관로 막힘·밸브 이상으로 인한 압력 급증)
- **Power Correlation**: `motor_power_kw` 동반 상승 → 펌프가 부하를 이기려 과하게 일하는 상태
- **Flow Inverse**: `flow_rate_l_min` 이 *낮을 때* SHAP 양수 → "**압력↑ + 유량↓**" 의 전형적 폐쇄(Clogging) 신호 학습됨
- **기여도 낮음**: `temp_slope_c_per_s` (0 부근에 밀집 — 모델 경량화 시 제외 후보)

### 4-2. 종합 패턴 — 모델이 학습한 핵심 로직

1. **"압력↑ + 유량↓" 동시 발생을 가장 확실한 이상 신호로 간주** → 노즐·필터 막힘 탐지에 최적화
2. **에너지 소비(Power)는 확증 편향 도구** → 단순 전력 상승보다, *압력 상승·유량 저하가 동반된 상태에서의 전력 상승*에 훨씬 민감
3. **환경 데이터(DLI·온도)는 기저 상태 설정** → "이 정도 광량이면 이만큼 양액이 나가야 하는데 왜 안 나가지?" 같은 *상대적 편차* 판단 배경
4. **센서 우선순위** — Critical: 차압·전력·구역별 EC/수분 / Low: 온도 변화율

### 4-3. 막힘 사건 1건 RCA 정량 검증
특정 막힘 이벤트 1건을 Local SHAP 분석한 결과:
- 누수/유량 관련 feature의 급격한 감소가 **AE 이상 점수 상승의 82%를 차지**
- Global SHAP 결과(좌측)와 일관성 정량적으로 입증

→ **모델 전체에서 유량(Flow Rate)이 가장 결정적 역할, 압력·전류가 그 뒤를 따르는** 우선순위 확정.

### 4-4. EDA × SHAP 교차 검증 — 막힘 연쇄 흐름
EDA에서 본 "유량 계단식 감소(-2.9%)" 와 SHAP의 "유량/압력/모터 신호 우선순위" 가 다음 **실제 고장 연쇄 흐름**과 일치:

```
양액펌프 노즐/관로 막힘
   → 펌프 과부하
      → 모터 전류↑·온도↑
         → 작물에 도달하는 양액 감소
            → 배지 수분 부족 → 작물 스트레스
```

→ AI가 단순한 블랙박스가 아니라 **물리적으로 설명 가능한 근거로 이상을 잡고 있음**을 검증.

---

## 5. 노트북 가이드

| 노트북 | 내용 |
|---|---|
| [notebooks/EDA.ipynb](../notebooks/EDA.ipynb), [EDA_2.ipynb](../notebooks/EDA_2.ipynb), [EDA_jun.ipynb](../notebooks/EDA_jun.ipynb) | 기초 분포·결측·이상치·시계열 패턴 |
| [notebooks/dabin_EDA_jun.ipynb](../notebooks/dabin_EDA_jun.ipynb) | dabin 데이터 도메인별 EDA |
| [notebooks/Hypothesis_Testing.ipynb](../notebooks/Hypothesis_Testing.ipynb) | 정상/이상 분포 차이 통계 검정 |
| [notebooks/data_filtering.ipynb](../notebooks/data_filtering.ipynb) | 필터 막힘 룰 검증 |
| [notebooks/modeling_jun.ipynb](../notebooks/modeling_jun.ipynb), [modeling_stronger_jun.ipynb](../notebooks/modeling_stronger_jun.ipynb) | 초기 모델링 실험 |
| [notebooks/model_middle_0420.ipynb](../notebooks/model_middle_0420.ipynb), [model_middle_0423.ipynb](../notebooks/model_middle_0423.ipynb) | 중간 모델 실험 (날짜별) |
| [notebooks/model_comparison_jun.ipynb](../notebooks/model_comparison_jun.ipynb) | 모델 변형별 성능 비교 |
| [notebooks/eval_f1.ipynb](../notebooks/eval_f1.ipynb) | F1 평가 |
| [notebooks/client_metrics_dashboard.ipynb](../notebooks/client_metrics_dashboard.ipynb) | 클라이언트 메트릭 대시보드 시안 |

> **모델 실험 변천사**(가설→시도→관측→진단→수정)는 [.claude/MODEL_CHANGELOG.md](../.claude/MODEL_CHANGELOG.md)에 누적 기록.
