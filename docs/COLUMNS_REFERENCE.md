# 📚 컬럼 레퍼런스 (Raw + 파생변수)

프론트 화면에서 차트·지표 매핑할 때 참고용 전체 컬럼 사전. 설비 구분 없이 **카테고리별**로 정리.

- 관련 문서: [INFERENCE_API.md](./INFERENCE_API.md) (API 스키마·요청/응답), [FRONTEND_PAGES.md](./FRONTEND_PAGES.md) (페이지 설계)
- 데이터 소스: [data/dabin.csv](../data/) (Raw), [src/preprocessing.py](../src/preprocessing.py) (파생)

## 범례

| 아이콘 | 의미 | 위치 |
|---|---|---|
| 🟢 Raw | CSV 원시 센서 | `data/*.csv` 스키마 |
| 🔵 파생(모델) | `create_modeling_features` 산출, AE 학습 입력 후보 | [preprocessing.py:40-349](../src/preprocessing.py#L40-L349) |
| 🟡 파생(해석) | `extract_interpretation_features` 산출, 해석 전용 | [preprocessing.py:443-561](../src/preprocessing.py#L443-L561) |
| ⚪ 프론트계산 | API 응답 기반 클라이언트 계산 (백엔드엔 없음) | - |

---

## 1. 메타

| 컬럼 | 종류 | 단위 | 설명 |
|---|---|---|---|
| `timestamp` | 🟢 | ISO8601 | 측정 시각 (1분 간격) |

## 2. 환경 센서

| 컬럼 | 종류 | 단위 | 설명 |
|---|---|---|---|
| `light_ppfd_umol_m2_s` | 🟢 | μmol/m²/s | 광합성 유효 광량자속 밀도 (순간 광량) |
| `air_temp_c` | 🟢 | °C | 재배실 공기 온도 |
| `relative_humidity_pct` | 🟢 | % | 재배실 상대 습도 |
| `co2_ppm` | 🟢 | ppm | 재배실 CO₂ 농도 |
| `calculated_vpd_kpa` | 🔵 | kPa | 증기압 결손 (식물 스트레스 지표). Tetens 공식: `e_s − e_s·(RH/100)`. 권장 0.5~1.2 |
| `daily_light_integral_proxy` | 🔵 | mol/m² | 1분 단위 광량 누적 프록시 = `PPFD · Δt / 1e6` |
| `daily_light_integral_mol_m2_d` | 🔵 | mol/m²/day | 일 단위 누적 광량 (DLI). 빛 대비 배액률 비정상 상승 = 뿌리 손상·점적핀 빠짐 |

## 3. 원수/탱크 센서

| 컬럼 | 종류 | 단위 | 설명 |
|---|---|---|---|
| `raw_tank_level_pct` | 🟢 | % | 원수 탱크 수위 |
| `raw_water_temp_c` | 🟢 | °C | 원수 온도 |
| `tank_a_level_pct` | 🟢 | % | A 비료통 수위 |
| `tank_b_level_pct` | 🟢 | % | B 비료통 수위 |
| `acid_tank_level_pct` | 🟢 | % | 산 탱크 수위 |
| `raw_tank_level_change_pct_per_min` | 🔵 | %/min | 원수 탱크 분당 수위 변화율. 관수 없는데 감소=누수, 관수 중 미감소=센서 고장 |
| `tank_a_est_hours_to_empty` | 🔵 | h | A통 고갈 예상 시간 (최근 10분 소비속도 기준) |
| `tank_b_est_hours_to_empty` | 🔵 | h | B통 고갈 예상 시간 |
| `acid_tank_est_hours_to_empty` | 🔵 | h | 산 탱크 고갈 예상 시간 |

## 4. 펌프·모터 센서 (Raw)

| 컬럼 | 종류 | 단위 | 설명 |
|---|---|---|---|
| `pump_rpm` | 🟢 | RPM | 펌프 분당 회전수 |
| `flow_rate_l_min` | 🟢 | L/min | 메인 라인 유량 |
| `flow_baseline_l_min` | 🟢 | L/min | 생성기 기준 유량 (참고용, 모델엔 재계산본 사용) |
| `suction_pressure_kpa` | 🟢 | kPa | 펌프 입력단(흡입) 압력 |
| `discharge_pressure_kpa` | 🟢 | kPa | 펌프 출력단(토출) 압력 |
| `motor_current_a` | 🟢 | A | 모터 소비 전류 |
| `motor_power_kw` | 🟢 | kW | 모터 소비 전력 |
| `motor_temperature_c` | 🟢 | °C | 모터 표면 온도 |
| `bearing_vibration_rms_mm_s` | 🟢 | mm/s | 베어링 진동 RMS |
| `bearing_temperature_c` | 🟢 | °C | 베어링 온도 |

## 5. 필터 센서

| 컬럼 | 종류 | 단위 | 설명 |
|---|---|---|---|
| `filter_pressure_in_kpa` | 🟢 | kPa | 필터 입구 압력 |
| `filter_pressure_out_kpa` | 🟢 | kPa | 필터 출구 압력 |
| `turbidity_ntu` | 🟢 | NTU | 탁도 (수질) |
| `filter_delta_p_kpa` | ⚪ | kPa | **필터 차압 = in − out**. 정상 7~8, 경고 >15, 위험 >25. 필터 오염도 직접 지표 |

## 6. 양액 조제 센서

| 컬럼 | 종류 | 단위 | 설명 |
|---|---|---|---|
| `mix_target_ec_ds_m` | 🟢 | dS/m | 조제 목표 EC |
| `mix_ec_ds_m` | 🟢 | dS/m | 조제 탱크 현재 EC |
| `mix_target_ph` | 🟢 | pH | 조제 목표 pH |
| `mix_ph` | 🟢 | pH | 조제 탱크 현재 pH |
| `mix_temp_c` | 🟢 | °C | 조제 탱크 온도 |
| `mix_flow_l_min` | 🟢 | L/min | 조제 탱크 유량 |
| `dosing_acid_ml_min` | 🟢 | mL/min | 산 주입 속도 |
| `drain_ec_ds_m` | 🟢 | dS/m | 배액 EC |

## 7. 양액 파생

| 컬럼 | 종류 | 단위 | 설명 |
|---|---|---|---|
| `pid_error_ec` | 🔵 | dS/m | `mix_ec − mix_target_ec`. 지속 양수=조제 모자람, 음수=과잉 |
| `pid_error_ph` | 🔵 | pH | `mix_ph − mix_target_ph`. 산/알칼리 조제 이탈 |
| `ph_instability_flag` | 🔵 | 0/1 | `mix_ph > 6.5` 침전 임계 플래그 |
| `salt_accumulation_delta` | 🔵 | dS/m | `drain_ec − mix_ec`. 양수 지속=뿌리가 물만 빨아 염류 축적 중 |
| `ph_roll_mean_30` | 🔵 | pH | pH 30분 이동평균 |
| `ph_trend_30` | 🔵 | pH/min | pH 30분 트렌드 (1차 차분) |

## 8. 압력·유량·전력 파생

| 컬럼 | 종류 | 단위 | 설명 |
|---|---|---|---|
| `differential_pressure_kpa` | 🔵 | kPa | 차압 = `discharge − suction`. 펌프가 실제 전달한 순수 압력 에너지 |
| `pressure_diff` | 🔵 | kPa | 토출 압력 1분 변화량 (`.diff()`). 급변 스파이크 탐지 |
| `flow_diff` | 🔵 | L/min | 유량 1분 변화량 |
| `flow_drop_rate` | 🔵 | 0~1 | `(baseline − flow) / baseline`. 0=정상, 1=완전 막힘. 3단계 게이트(pump_on, baseline>1, [0,1] 클리핑) 적용 |
| `hydraulic_power_kw` | 🔵 | kW | 유효 수력 동력 = `flow·차압 / 60000` |
| `wire_to_water_efficiency` | 🔵 | - | 전기→수력 변환 효율 = `hydraulic_power / motor_power` |
| `pressure_flow_ratio` (모델용) | 🔵 | kPa·min/L | `differential_pressure / flow`. [preprocessing.py:225](../src/preprocessing.py#L225) |
| `pressure_flow_ratio` (해석용) | 🟡 | kPa·min/L | `discharge / flow`. 배관 저항 지표. **프론트 표시는 이 버전** |
| `dp_per_flow` | 🟡 | kPa·min/L | `(discharge − suction) / flow`. 에너지 대비 유량. 상승=비정상 부하 |
| `pressure_per_power` | 🟡 | kPa/kW | `discharge / motor_power`. 압력 대비 전력 효율 |
| `flow_per_power` | 🟡 | L/(min·kW) | `flow / motor_power`. 유량 대비 전력 효율 |
| `pressure_roll_mean_10` | 🔵 | kPa | 차압 10분 이동평균 |
| `pressure_trend_10` | 🔵 | kPa/min | 차압 10분 트렌드 (1차 차분) |
| `flow_roll_mean_10` | 🔵 | L/min | 유량 10분 이동평균 |
| `flow_trend_10` | 🔵 | L/min·min | 유량 10분 트렌드 |
| `pressure_volatility` | ⚪ | - | 12h 압력 변동성 = `std/IQR` (프론트 링버퍼 720점 계산) |
| `flow_cv` | ⚪ | - | 12h 유량 변동계수 = `std/mean` (프론트 링버퍼 720점 계산) |

## 9. 온도·진동·RPM 파생

| 컬럼 | 종류 | 단위 | 설명 |
|---|---|---|---|
| `temp_slope_c_per_s` | 🔵 | °C/sec | 초당 모터 온도 변화율 (`diff(T)/Δt`). 급격한 양수=과부하 징후 |
| `rpm_slope` | 🔵 | RPM/sec | RPM 초당 변화율 |
| `rpm_acc` | 🔵 | RPM/sec² | RPM 가속도 (`rpm_slope.diff()`) |
| `rpm_stability_index` | 🔵 | - | `|rpm − rpm_mean_10| / rpm_mean_10`. 공기 유입·난류 시 목표 RPM 못 유지 |

## 10. 펌프 상태·이벤트 파생

| 컬럼 | 종류 | 단위 | 설명 |
|---|---|---|---|
| `pump_on` | 🔵 | 0/1 | 동적 판정: 유량>0.1 OR rpm_std>80분위 OR rpm>70분위. 3분 max 스무딩 |
| `pump_start_event` | 🔵 | 0/1 | `pump_on` 0→1 전환 순간만 1 |
| `pump_stop_event` | 🔵 | 0/1 | `pump_on` 1→0 전환 순간만 1 |
| `minutes_since_startup` | 🔵 | min | 펌프 켜진 후 경과 분 |
| `minutes_since_shutdown` | 🔵 | min | 펌프 꺼진 후 경과 분 |
| `is_startup_phase` | 🔵 | 0/1 | 기동 직후 0~5분 구간. **1일 때 알람 강제 Normal 억제** |
| `is_off_phase` | 🔵 | 0/1 | 정지 직후 0~5분 구간 |

## 11. 시간 인코딩 파생

| 컬럼 | 종류 | 단위 | 설명 |
|---|---|---|---|
| `minute_of_day` | 🔵 | 0~1439 | 하루 중 몇 번째 분인지 |
| `time_sin` | 🔵 | -1~1 | `sin(2π · minute_of_day / 1440)` |
| `time_cos` | 🔵 | -1~1 | `cos(2π · minute_of_day / 1440)` |

## 12. 구역별 Raw (zone 1, 2, 3 각각)

| 컬럼 | 종류 | 단위 | 설명 |
|---|---|---|---|
| `zone{1,2,3}_flow_l_min` | 🟢 | L/min | 구역별 유량 |
| `zone{1,2,3}_pressure_kpa` | 🟢 | kPa | 구역별 압력 |
| `zone{1,2,3}_substrate_moisture_pct` | 🟢 | % | 구역별 배지 수분 |
| `zone{1,2,3}_substrate_ec_ds_m` | 🟢 | dS/m | 구역별 배지 EC |
| `zone{1,2,3}_substrate_ph` | 🟢 | pH | 구역별 배지 pH |

## 13. 구역별 파생

| 컬럼 | 종류 | 단위 | 설명 |
|---|---|---|---|
| `zone{1,2,3}_resistance` | 🔵 | kPa·min/L | 배관 저항 = `zone_pressure / zone_flow`. 상승=점적핀 막힘 |
| `zone{1,2,3}_moisture_response_pct` | 🔵 | %/min | 급액 후 수분 변화량 (배지 수분 `.diff()`) |
| `zone{1,2,3}_ec_accumulation` | 🔵 | dS/m | `zone_substrate_ec − mix_ec`. 양수 지속=염류 축적 |
| `supply_balance_index` | 🔵 | - | `(z1+z2+z3 flow) / main_flow`. <1 지속=메인 배관 누수 |

> ⚠️ zone 2·3은 [preprocessing.py:607-617](../src/preprocessing.py#L607-L617)에서 다중공선성으로 drop. AE 학습엔 미사용이나 **원시 모니터링 표시는 가능**

## 14. 운영 이벤트 플래그

| 컬럼 | 종류 | 단위 | 설명 |
|---|---|---|---|
| `cleaning_event_flag` | 🟢 | 0/1 | 주기적 산 세척 이벤트. **1인 윈도우는 학습 제외** |

## 15. 해석용 스파이크 탐지

| 컬럼 | 종류 | 단위 | 설명 |
|---|---|---|---|
| `is_pressure_spike` | 🟡 | 0/1 | `|pressure_diff|`이 rolling 60분 80분위 초과 |
| `is_rpm_spike` | 🟡 | 0/1 | `|rpm_slope|`이 rolling 60분 80분위 초과 |
| `is_spike` | 🟡 | 0/1 | 압력 OR RPM 스파이크 |
| `is_startup_spike` | 🟡 | 0/1 | `is_startup_phase=1`일 때의 스파이크 (**정상 과도 거동**) |
| `is_anomaly_spike` | 🟡 | 0/1 | `is_startup_phase=0`일 때의 스파이크 (**이상 징후**) |

## 16. 학습 전용 (내부/검증용 — CSV에서 제외됨)

> [data_gen_dabin.py:304-305](../services/inference/src/data_gen_dabin.py#L304-L305)에서 `hidden_*` 접두사 컬럼은 최종 CSV에서 drop. 프론트/추론 경로엔 안 들어옴.

| 컬럼 | 종류 | 설명 |
|---|---|---|
| `hidden_tip_clog_level` | (제외됨) | 점적핀 막힘 시뮬 레벨 |
| `hidden_blocked_tip_ratio` | (제외됨) | 막힌 핀 비율 |
| `hidden_risk_stage` | (제외됨) | 시뮬레이션 라벨 (normal/watch/warning/critical) |


앞서 사진을 봤다시피 물방울이 나오는 노드팁 구멍이 워낙 작다 보니, 여러 영양분이 섞이 배약액들의 결정화로 스케일링이 발생하거나, 유기물 증식, 이물질 유입으로 인해 노드 팁이 막히는 문제가 발생되기도 합니다. 이러한 문제가 발생되면 불균일한 작물 품질로 인해 전체 수확량이 줄어들수 있으며, 양액 펌프에 지속적인 부담으로 인해 설비 수명 단축, 추후 기계에 문제 발생히 막대한 복구 비용과 장시간의 다운타임이 발생할수 있는 문제가 생깁니다.

이에, 저희 프로젝트는 양액 펌프 및 센서 데이터를 수집하여 모델 학습하여, 설비 이상을 사전 감지하여 사전조치를 할수 있게 함으로써, 균등한 품질 확보 및 수확량 극대화, 설비 및 호스 정비 적기 시기를 제시하는 것이 목표입니다.


시스템 아키텍처 구성도입니다.
이 구조는 크게 두 가지 흐름으로 나누어 설명드릴 수 있습니다.
첫 번째는 실시간 흐름입니다.
MQTT로 수신한 데이터를 backend가 직접 구독하여,
별도의 저장 없이 WebSocket을 통해 프론트로 즉시 전달합니다.
두 번째는 배치 추론 흐름입니다.
수집된 데이터를 S3에 주기적으로 저장한 뒤,
AI 모델을 통해 이상 여부를 판단하고 그 결과를 DB에 저장합니다.
이후 backend가 해당 결과를 조회하여 프론트에 전달하는 구조입니다.


간단하게 아키텍처를 구성하는 주요 컴포넌트에 대해 설명드리겠습니다.
먼저, 데이터 수집 단계입니다.
센서와 서비스를 직접 연결하지 않고 MQTT 기반 Pub/Sub 구조를 적용했습니다.
이를 통해 생산자와 소비자를 분리하여, 유연한 구조를 만들었습니다.
MQTT는 Kafka와 같은 강한 메시지 큐 시스템은 아니지만,
QoS를 통해 기본적인 전달 신뢰성을 제공합니다.
이 시스템에서는 데이터 완전성보다 실시간성과 경량성을 더 중요하게 판단하여 MQTT를 선택했습니다.
다음으로 데이터 저장 단계입니다.
수집된 데이터는 메모리에 버퍼링한 뒤, 10분 단위로 배치 처리하여 S3에 저장했습니다.
이후 AI 추론 단계입니다.
실시간 처리 대신 배치 기반으로 모델을 운영하여 연산 비용을 줄이고, 안정적으로 이상 탐지를 수행하도록 구성했습니다.
마지막으로 백엔드입니다. MQTT의 실시간 데이터와 DB의 추론 결과를 통합하여, WebSocket을 통해 클라이언트에 전달하는 역할을 수행합니다. 이를 통해 프론트엔드는 하나의 채널로 모든 데이터를 받을 수 있도록 단순화했습니다.
