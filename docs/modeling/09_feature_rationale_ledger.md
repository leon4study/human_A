# 09 — 피처 근거 원장 (Feature Rationale Ledger)

도메인 파생 피처를 **"왜 만들었나"와 함께** 한 곳에 기록하는 원장입니다.

## 0. 왜 이 원장이 필요한가

이 프로젝트의 모델링 시간이 오래 걸린 핵심 이유는, 물리적으로 같이 움직이는 중복 지표를 제거하고 나면 도메인별로 남는 지표가 빈약해져서, **도메인 지식으로 새 파생 지표를 설계하고 각 지표의 근거를 쌓는 작업**이 반복됐기 때문입니다. 이 원장은 그 근거를 한 번 박아두어 재사용하게 합니다.

- 발표·면접에서 "이 지표 왜 만들었나"에 즉시 답이 됩니다.
- 새 피처를 추가할 때 기존 것과 중복·근거 누락을 막습니다.
- 구현 위치(공식이 사는 곳)와 상태(구현/제안)를 한눈에 봅니다.

## 1. 기록 원칙 (각 항목 필드)

| 필드 | 의미 |
|---|---|
| 피처명 | 코드 컬럼명 |
| 공식 | 어떤 센서를 어떻게 조합했나 |
| 물리 근거 | 왜 이 조합이 이상을 반영하나 (도메인 지식) |
| 탐지 대상 | 무엇을 잡으려는가 |
| 상태 | 구현됨 / 제안 |
| 출처 | PPT(script.txt 줄)·코드·문헌 등 근거 위치 |

원칙: **물리적 근거가 분명한 것만** 등록한다. 단순히 컬럼 수를 늘리려는 억지 조합은 넣지 않는다(근거 칸이 비면 등록 불가).

---

## 2. 기존 구현된 파생 피처 (create_modeling_features)

> 공식 원본: [preprocessing.py `create_modeling_features`](../../src/preprocessing.py)

### 2-1. Hydraulic / 막힘
| 피처 | 공식 | 물리 근거 | 탐지 | 상태 |
|---|---|---|---|---|
| `pressure_diff` | discharge − suction | 펌프가 만든 압력차 | 펌프 부하 | 구현됨 |
| `differential_pressure_kpa` | discharge − suction 계열 | 위와 동일 계열(타깃용) | 관로 부하 | 구현됨 |
| `flow_drop_rate` | (baseline − flow)/(baseline+ε), 3단 게이트 | 같은 조건 대비 유량 감소 | 막힘 | 구현됨 |
| `hydraulic_power_kw` | 압력 × 유량 환산 | 실제 수력 출력 | 효율 | 구현됨 |
| `wire_to_water_efficiency` | hydraulic_power / motor_power | 전기→수력 변환 효율 | 펌프 노후 | 구현됨 |
| `pressure_flow_ratio` | discharge / flow | 유량 대비 압력(해석용) | 막힘 경향 | 구현됨 |

### 2-2. Motor / 구동부
| 피처 | 공식 | 물리 근거 | 탐지 | 상태 |
|---|---|---|---|---|
| `rpm_stability_index` | \|rpm − rpm_mean_10\| / (rpm_mean_10+ε) | 회전 안정성 이탈 | 구동 불안정 | 구현됨 |
| `rpm_slope`, `rpm_acc` | rpm 1·2차 변화율 | 가감속 거동 | 기동/부하 변화 | 구현됨 |
| `temp_slope_c_per_s` | 온도 변화율 | 발열 추세 | 과열 진행 | 구현됨 |

### 2-3. Nutrient / 양액 (보조 지표 — voting 제외)
| 피처 | 공식 | 물리 근거 | 탐지 | 상태 |
|---|---|---|---|---|
| `pid_error_ec`, `pid_error_ph` | 측정 − 목표 | 제어 오차(목표 대비 이탈) | 배합 이상 | 구현됨 |
| `salt_accumulation_delta` | drain_ec − mix_ec 계열 | 배수가 공급보다 진하면 염류 축적 | 염류 집적 | 구현됨(일부 단계서 drop) |
| `ph_roll_mean_30`, `ph_trend_30` | pH 30분 평균·추세 | 느린 화학 변동 | 드리프트 | 구현됨 |

### 2-4. Zone_drip / 구역 배지
| 피처 | 공식 | 물리 근거 | 탐지 | 상태 |
|---|---|---|---|---|
| `zone1_resistance` | zone1_pressure / zone1_flow | 구역 관로 저항 | 노즐 막힘 | 구현됨 |
| `zone1_moisture_response_pct` | 관수 대비 수분 반응도 | 물 줬는데 반응 적으면 이상 | 노즐 막힘/센서 | 구현됨 |
| `zone1_ec_accumulation` | zone1_substrate_ec − mix_ec | 공급 대비 구역 EC 축적 | 염해 | 구현됨 |
| `supply_balance_index` | (zone1+2+3 flow) / flow_rate | 공급 균형 | 관수 편차 | 구현됨 |

### 2-5. 환경 / 컨텍스트
| 피처 | 공식 | 물리 근거 | 탐지 | 상태 |
|---|---|---|---|---|
| `calculated_vpd_kpa` | Tetens 공식(기온·습도) | 증산 압력(작물 물 수요 기저) | 환경 기저 | 구현됨 |
| `time_sin/cos`, `pump_on`, `minutes_since_startup` | 시간·운전 맥락 | 정상 패턴의 조건 | 컨텍스트(점수 제외) | 구현됨 |

---

## 3. 제안 신규 피처 (미구현)

도메인 빈약 해소 + 막힘 직격을 위한 후보. 난이도: 쉬움(원소별 계산) / 중간(윈도우 필요) / 어려움(이벤트 검출).

### 3-1. Zone_drip (최우선 — 현재 가장 빈약)
| 피처 | 공식 | 물리 근거 | 탐지 | 난이도 | 출처 |
|---|---|---|---|---|---|
| `zone_ec_variance` | std(zone1/2/3 substrate_ec) | 한 라인만 막히면 구역 간 EC 편차↑. 펌프와 무관한 고유 정보 | 국부 막힘 | 쉬움 | PPT:474 |
| `zone_moisture_variance` | std(zone1/2/3 moisture) | 관수 불균일 시 구역별 수분 벌어짐 | 관수 편차 | 쉬움 | PPT:474 |
| `substrate_ec_accum_rate` | d(zone1_substrate_ec)/dt | 염류 집적 속도 | 염해 진행 | 쉬움 | — |
| `irrigation_response_eff` | Δmoisture / zone1_flow | 같은 물에 수분 안 오르면 누수/막힘 | 노즐 막힘 | 중간 | — |
| `moisture_lag_time` | valve_on → 수분 반응까지 지연 | 막히면 반응 지연↑ | 노즐 막힘(직접) | 어려움 | PPT:473 |

> 비고: zone2/3 raw 센서는 `model_cols` 필터 이전 단계엔 살아 있으므로 variance 계산 가능. 개별 zone 압력/유량은 단일 펌프 연동(공선성)이라 제외하되, 편차(variance)는 고유 정보라 살릴 가치.

### 3-2. Hydraulic (막힘 직격)
| 피처 | 공식 | 물리 근거 | 탐지 | 난이도 | 출처 |
|---|---|---|---|---|---|
| `system_resistance` | discharge_pressure / flow_rate² | 펌프 시스템 곡선. 막히면 같은 유량에 압력 급증 | 관로 막힘(직접) | 쉬움 | PPT:487 |
| `specific_energy` | motor_power / flow_rate | 단위 유량당 전력. 막히면 같은 물에 전력↑ | 막힘·노후 | 쉬움 | PPT:488 |
| `filter_clog_index` | filter_pressure_in − filter_pressure_out | 필터 차압 직접 지표 | 필터 막힘 | 쉬움 | — |

> `filter_pressure_out`은 현재 collinearity에서 drop됨. filter_clog_index를 쓰려면 차압 계산 후 원본을 drop하는 순서로 보존 필요.

### 3-3. 환경 보정 (양방향 강력)
| 피처 | 공식 | 물리 근거 | 탐지 | 난이도 | 출처 |
|---|---|---|---|---|---|
| `transpiration_demand` | VPD × light_ppfd | 작물 물 수요 proxy | 기저 수요 | 쉬움 | PPT:500-501 |
| `demand_residual` | actual_flow − 기대유량(demand 기반) | "이 날씨면 이만큼 나가야 하는데 왜 안 나가나" | 막힘/과관수 | 중간 | PPT:501 |

### 3-4. Motor
| 피처 | 공식 | 물리 근거 | 탐지 | 난이도 | 출처 |
|---|---|---|---|---|---|
| `vibration_per_load` | bearing_vibration / motor_power | 부하 정규화 진동. 마모는 부하 무관 진동↑ | 베어링 마모 | 쉬움 | — |
| `bearing_thermal_margin` | bearing_temp − motor_temp | 베어링이 더 뜨거우면 윤활 불량 | 베어링 과열 | 쉬움 | — |
| `load_per_speed` | motor_current / pump_rpm | 같은 RPM에 전류↑ = 기계적 마찰 | 과부하·막힘 | 쉬움 | — |

### 3-5. Nutrient (보조)
| 피처 | 공식 | 물리 근거 | 탐지 | 난이도 | 출처 |
|---|---|---|---|---|---|
| `ab_tank_imbalance` | d(tank_a)/dt ÷ d(tank_b)/dt | A/B액 소모 비율 어긋남 | 배합 비율 오류 | 중간 | PPT |
| `leaching_ratio` | drain_ec / mix_ec | 배수 EC가 공급보다 높으면 염류 축적 | 염류 집적 | 쉬움 | — |

---

## 4. 구현 위치와 주의

새 피처를 실제로 살리려면 다음을 함께 손봐야 한다(zone-soil 복원 사례와 동일 패턴, [05](05_reproducibility_implementation.md)·[06](06_visualization_logging.md) 참조):

1. **공식 추가** — [preprocessing.py `create_modeling_features`](../../src/preprocessing.py)에서 계산.
2. **`model_cols` 등록** — 집계 화이트리스트에 넣어야 df_agg까지 살아남음(누락 시 zone_drip 사례처럼 조용히 잘림).
3. **공선성 보호** — 펌프와 중복 안 되는 고유 정보면 collinearity whitelist에 추가.
4. **도메인 배정** — `feature_engineering.SENSOR_MANDATORY[domain]` 또는 SHAP 타깃으로 해당 도메인에 들어가게.
5. **leak 주의** — 어떤 피처가 도메인 타깃에서 파생되면 leak_cols로 SHAP 후보에서 제외(타깃 예측에 자기 자신 금지). AE 입력으로는 MANDATORY 주입 가능.
6. **검증** — 재학습 후 해당 도메인 진단 그림이 살아나는지 + 타 도메인 config 회귀 없는지([04 체크리스트](04_modeling_kickoff_checklist.md)).

## 5. 권장 1차 구현 배치

난이도 "쉬움" + 빈약 도메인 우선:
- zone_drip: `zone_ec_variance`, `zone_moisture_variance`, `substrate_ec_accum_rate`
- hydraulic: `system_resistance`, `specific_energy`
- motor: `bearing_thermal_margin`, `load_per_speed`

zone-soil 복원분과 묶어 한 실험(`PHASE=feature-v2`)으로 학습→진단 그림으로 빈약 해소를 확인한다.
