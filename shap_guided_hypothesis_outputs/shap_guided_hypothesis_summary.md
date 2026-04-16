# SHAP-Guided Hypothesis Testing Summary

- 입력 파일: `human_A\src\selected_smartfarm.csv`
- 유의수준: `0.05`

## SHAP 앵커
| 가설 | 통계 기법 | 메인 변수 | 보조/Robust 피처 | SHAP 근거 |
| --- | --- | --- | --- | --- |
| H1 관로/팁 막힘 | Granger | zone1_resistance -> zone1_moisture_response_pct | filter_delta_p_kpa, flow_drop_rate, zone1_flow_l_min | zone1_resistance 4/8 Robust |
| H2 채널링/미세 누수 | Event-window CCF | mix_flow_l_min -> abs(Δdrain_ec_ds_m) | zone1_substrate_ec_ds_m, zone1_substrate_moisture_pct | drain_ec_ds_m 2/8 Robust |
| H3 펌프 노후화/기계 열화 | Welch T-test + Mann-Whitney | wire_to_water_efficiency | motor_current_a, bearing_vibration_rms_mm_s, motor_temperature_c | motor_temperature_c 4/8 Robust |

## H1
| hypothesis | x | y | lag_10m | lag_minutes | p_value | significant |
| --- | --- | --- | --- | --- | --- | --- |
| H1_original | zone1_resistance | zone1_moisture_response_pct | 6 | 60 | 1.2681133531888351e-117 | True |
| H1_alternative | filter_delta_p_kpa | flow_drop_rate | 1 | 10 | 0.0 | True |

## H2
| 점검/통계 | 값 | 비판적 리뷰 |
| --- | --- | --- |
| 이벤트 구조 | 90개, 하루 1회, 시작시각 mode 05:51 | event index와 운영일이 같은 축 |
| onset 규칙 민감도 | 1-hit 실패율 0.222 / 2-hit 실패율 0.356 | 같은 데이터라도 규칙을 엄격하게 하면 실패율이 크게 바뀜 |
| 전체 CCF peak | 58분 / corr=-0.038 | corr 절대값이 작으면 강한 증거가 아님 |
| 초기 vs 후기 CCF peak | 42분 -> 45분 | 관측 lag 비교 MW p=0.195 |
| 최종 판정 | 탐색적 분석 유지 | 2-hit 실패율이 30%를 넘으면 confirmatory claim 금지 |

## H3
| 구간 | wire_to_water_efficiency 평균 | motor_current_a 평균 | bearing_vibration_rms_mm_s 평균 | motor_temperature_c 평균 |
| --- | --- | --- | --- | --- |
| 초기 7일 | 0.05190255242751799 | 5.417983953033269 | 1.3134964774951077 | 42.17862015655578 |
| 후기 7일 | 0.023938712894863053 | 8.919769080234834 | 3.698191976516634 | 49.60039667318983 |

| 비교 방식 | Welch p-value | Mann-Whitney p-value | 비판적 리뷰 |
| --- | --- | --- | --- |
| 초기 7일 vs 후기 7일 proxy 비교 | 7.936050552468155e-13 | 0.0005827505827505828 | cleaning_event_flag가 없어 세척 전후 실험이 아니라 시간 proxy 비교 |

## 제한해서 말할 점
- H1은 파생변수 구조가 있어 유의성을 곧바로 물리 인과로 번역하면 안 됩니다.
- H2는 2-hit onset 실패율이 `0.356`라 탐색적 분석으로만 유지합니다.
- H3는 세척 전후 실험이 아니라 초기 7일 vs 후기 7일 proxy 비교입니다.