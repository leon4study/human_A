# 12 — 데이터 생성 현실화 설계 (공공데이터 앵커 + 센서 독립성)

이 문서는 합성 데이터 생성기를 **물리적으로 더 충실하게** 다시 설계하는 계획입니다. 목표는 두 가지입니다.
하나는 공공데이터(딸기 농가 환경)를 기준으로 운영 조건을 앵커링하는 것이고, 다른 하나는 센서마다
독립적인 거동을 부여해 인위적인 완전상관(collinearity artifact)을 없애는 것입니다.

> 배경: 현재 데이터는 거의 모든 센서를 `clog`(막힘 진행도) 한 변수의 결정적(deterministic) 함수로
> 만들어, 물리적으로 독립이어야 할 센서들이 상관계수 ~1.00이 됩니다. 그 결과 전처리의 다중공선성
> 필터(corr>0.85)가 그 센서들을 "중복"으로 제거해 도메인별 학습 피처가 빈약해집니다(2026-06-06 감사).
> 상세 진단: [10 §3-6](10_anomaly_signature_ledger.md), MODEL_CHANGELOG Phase H·I.

> 정직성 원칙: 데이터 변경은 **물리적 충실성**(연구한 범위·영향·독립성)만을 근거로 한다. 모델 점수를
> 좋게 만들려는 튜닝(순환적 데이터해킹)은 금지. 모든 결과는 "합성데이터 결과"로만 보고한다.

---

## 0. 공공데이터 앵커 (딸기 농가)

출처: 공공데이터포털 딸기 재배환경 자료([평균_딸기_환경셋팅.txt](../평균_딸기_환경셋팅.txt)). 개화·착과기 기준.

| 항목 | 범위 | 비고 |
|---|---|---|
| 온도 | 주간 20~25℃ / 야간 7~10℃ | 야간 냉각 5~8℃ |
| 습도 | 낮 60~70% / 밤 70~85% | |
| CO₂ | 800~1200 ppm | |
| VPD | 0.5~1.2 kPa | temp·humidity에서 유도 |
| 양액 EC | 1.5~1.8 dS/m (개화기) | |
| pH | 5.5~6.5 (이상 5.8~6.2) | |
| 양분 ppm | N 100~150 / P 20~40 / K 150~250 / Ca 100~150 / Mg 30~50 | |
| 관수 | 하루 5~15회 (광량 연동) | 배액률 20~30% |
| 광량 | 200~400 μmol/m²/s | 일조 10~14시간 |
| 배지 | 코코피트 | 배액 EC>공급 EC = 염류 축적 |

이 값들이 Layer 0(환경)과 Layer 1(양액 setpoint)의 기준선이 됩니다.

---

## 1. 층 구조 (각 층이 독립 분산을 더한다)

```
Layer 0  환경(공공데이터 앵커)   air_temp·humidity·CO2·PPFD·VPD — 일주기 + 독립노이즈 + 계절드리프트
   │
Layer 1  운영/제어              관수 스케줄(광량연동 5~15회)·펌프 on/off·양액 setpoint(EC/pH)+PID 잔차
   │
Layer 2  물리 센서             각 센서 = 공유드라이버 + [센서 고유 확률성분] + 측정노이즈   ← 핵심 수정
   │
Layer 3  고장 주입             clog·bearing·suction·nutrient influence 모델(이미 설계, fault_injection/)
```

핵심은 Layer 2입니다. 현재는 `센서 = f(clog)` 결정식뿐이라, 여기에 **센서 고유 성분**을 더해 독립성을 만듭니다.

---

## 2. 센서 분해 공식 (독립성의 핵심)

각 센서 s를 다음으로 구성합니다.

```
s(t) = baseline(환경·setpoint)  +  Σ_k w_k · driver_k(t)  +  u_s(t)  +  ε_s(t)
        └ 공공데이터 기준선        └ 공유 드라이버(부하·환경·고장)   └ 고유   └ 측정노이즈
                                     (researched 영향 가중치 w_k)       확률성분
```

- `driver_k`: 펌프 부하, 환경(기온), 고장강도(clog 등) 등 **여러 센서가 공유**하는 물리 동인.
- `u_s(t)`: **그 센서만의 독립 확률 과정**(AR(1) 또는 random-walk). 예: 베어링 상태, 센서 드리프트, 국소 난류.
  이 항이 없으면 같은 driver를 쓰는 센서들이 완전상관이 된다. **이 항의 분산이 상관계수를 조절한다.**
- `ε_s(t)`: 측정 노이즈(백색).

수학: 두 센서가 driver D를 공유하면 `corr(s1,s2) = w1·w2·Var(D) / √((w1²Var(D)+Var(u1)+Var(ε1))(...))`.
→ `Var(u)`(고유성분)를 키우면 상관이 내려간다. 이를 이용해 각 쌍을 **목표 상관**에 맞춘다.

---

## 3. 독립성 게이트 (데이터 품질 자동 검증)

생성 후 상관행렬을 검사하는 규칙. 재현성 검증처럼 **데이터에도 거는 품질 게이트**다.

- **하드 천장**: 동어반복(파생=입력의 함수)이 아닌 **raw 센서 쌍의 |corr| ≤ 0.85**(전처리 필터 컷과 동일).
  넘으면 artifact로 게이트 실패 → 해당 센서 고유성분 분산을 키워 재생성.
- **쌍별 물리 목표**(천장보다 여유 있게):

| 쌍 유형 | 예 | 목표 corr |
|---|---|---|
| 강결합(같은 펌프 구동) | flow ↔ discharge_pressure | 0.6~0.8 |
| 약결합(열원·경로 다름) | motor_temp ↔ bearing_temp | 0.4~0.7 |
| 거의 무관(기계 vs 수력/화학) | bearing_vibration ↔ discharge_pressure | 0.1~0.3 |
| 동어반복(파생) | differential_pressure = discharge − suction | 게이트 제외 |

- 구현: 생성 스크립트 끝에 `assert` 또는 리포트로 천장 위반 쌍을 출력. 위반 0이어야 통과.

---

## 4. 센서별 독립성 부여 계획 (artifact 우선)

2026-06-06 감사에서 완전상관(~1.00)으로 잘린 raw 센서부터. (동어반복 파생은 그대로 둠 — 정상 드롭.)

| 센서 | 현재(문제) | 부여할 고유 성분 |
|---|---|---|
| `bearing_vibration_rms_mm_s` | discharge_pressure와 1.00 (둘 다 clog 선형) | 베어링 상태 random-walk(마모 누적, 부하와 약결합) + 노이즈 → 압력과 0.1~0.3 |
| `bearing_temperature_c` | motor_temperature와 0.97 (둘 다 air+clog) | 베어링 마찰열의 독립 열 시정수(thermal lag) + 노이즈 → motor_temp와 0.4~0.7 |
| `suction_pressure_kpa` | discharge와 1.00 | 흡입측 inlet 변동(원수 수위·여과 저항)의 독립 성분 → discharge와 0.6~0.8 |
| `drain_ec_ds_m` | relative_humidity와 0.97 (우연 일주기) | 배지 염류 축적의 독립 누적 성분 → 습도와 무관(<0.3) |

> hydraulic_power_kw·filter_delta_p_kpa는 raw에 없는 유령 mandatory(§5). mix_temp_c는 model_cols 누락(§5).

---

## 5. 부수 정리 (이번에 함께)

- `mix_temp_c`: raw에 존재하나 model_cols 누락 → 추가(motor 진동과 동일 패턴).
- `hydraulic_power_kw`·`filter_delta_p_kpa`: raw에 없음. 파생으로 계산(flow×pressure / filter_in−out)하거나
  SENSOR_MANDATORY에서 제거. 필터는 룰기반 도메인이라 filter_delta_p는 제거 가능.

---

## 6. 진행 순서

1. (이 문서) 설계 확정.
2. `data_gen_jun` 진화 — Layer 0 공공데이터 앵커 + Layer 2 센서 고유성분 추가. 상세 주석 필수.
3. 독립성 게이트 스크립트(생성 후 corr 리포트)로 천장 위반 0 확인.
4. 센서 설명 문서 동기화: [COLUMNS_REFERENCE](../COLUMNS_REFERENCE.md)(각 센서 공식·범위·독립성), [DOMAIN_KNOWLEDGE](../DOMAIN_KNOWLEDGE.md), [10 ledger](10_anomaly_signature_ledger.md).
5. 재생성 → 재학습 → 측정도구(coupling_validate·leadtime·baseline_blockage) 전체 재실행 → 새 baseline 확정.
6. MODEL_CHANGELOG에 변천 기록(가설→시도→관측→진단→수정).

> 검증 상태 리셋 주의: 이 작업 후 Phase I까지의 모든 수치(lead-time 35.9h 등)는 새 데이터 기준으로 재측정해야 한다.