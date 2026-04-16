# Hypothesis Testing Summary

- 입력 파일: `human_A\src\selected_smartfarm.csv`
- 유의수준: `0.05`

## Phase 0
- drain_ec median hold 길이: `1.0분`
- isolated event 수: `90`
- MAD threshold: `0.004448`
- drain lag 검출 실패율: `0.356`
- H2 메인 게이트 판정: `탐색적 분석으로 강등`

## H1 Granger
| hypothesis | x | y | lag_10m | lag_minutes | p_value | significant |
| --- | --- | --- | --- | --- | --- | --- |
| H1_original | zone1_resistance | zone1_moisture_response_pct | 6 | 60 | 1.2681133531888351e-117 | True |
| H1_alternative | filter_delta_p_kpa | flow_drop_rate | 1 | 10 | 0.0 | True |

## H2 Event-based lag
- Cox hazard ratio (10 event 증가당): `0.9850`
- Cox p-value: `0.763963`
- 우측 경계(60분) 검출 비율: `0.000`
- 보조 CCF peak lag: `58`분
- 보조 CCF peak corr: `-0.03750384305057365`

### Zone reproducibility
| signal | threshold | events | failure_rate | pass_gate |
| --- | --- | --- | --- | --- |
| zone1_substrate_moisture_pct | 0.0889560000000139 | 90 | 0.12222222222222223 | True |
| zone2_substrate_moisture_pct | 0.08450819999999266 | 90 | 0.21111111111111114 | True |
| zone3_substrate_moisture_pct | 0.08450819999999266 | 90 | 0.18888888888888888 | True |
| zone1_substrate_ec_ds_m | 0.00444779999999951 | 90 | 0.24444444444444446 | True |
| zone2_substrate_ec_ds_m | 0.00444779999999951 | 90 | 0.3555555555555555 | False |
| zone3_substrate_ec_ds_m | 0.00444779999999951 | 90 | 0.5 | False |

## H3 T-test / Mann-Whitney
- 비교 모드: `time_proxy_first7_vs_last7`
- Welch t-test p-value: `7.93605e-13`
- Mann-Whitney p-value: `0.000582751`

## 해석 제한
- H2는 clogging의 직접 인과 증명이 아니라 repeated-event response lag 패턴 분석입니다.
- 현재 고정 onset 규칙(2분 연속 초과)을 적용하면 H2 메인 실패율이 30%를 넘어, 확증적 검정보다 탐색적 분석으로 보는 편이 안전합니다.
- 이 데이터에서는 운영 일수와 이벤트 수가 사실상 같은 축이어서 달력 시간 효과와 반복 운영 효과를 분리할 수 없습니다.
- H3는 cleaning_event_flag가 없으면 세척 전후가 아니라 time-based proxy 비교로만 해석해야 합니다.