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

## 3. 데이터 품질 게이트 (목적 재정의 — 2026-06-07)

**중요 교정**: 게이트의 목적은 "상관을 0으로 낮추기"가 **아니다**. 물리적으로 엮인 센서(같은 펌프가
미는 흡입·토출)는 엮인 채로 두고, 인위적 완전상관(데이터 생성식이 한 변수로만 만들어 생긴 ~1.00)만
없앤다. 고장 구분력은 상관을 죽여서가 아니라 **§7 관계 판별 피처**로 확보한다.

따라서 게이트는 두 조건을 본다.
1. **인위적 완전상관 없음**: 동어반복(파생=입력의 함수)이 아닌 raw 센서 쌍의 |corr| ≤ **0.85**
   (전처리 다중공선성 필터 컷과 동일 — 통상 0.8~0.9를 강한 상관으로 보는 통념과도 일치).
   단, **물리적으로 타당한 상관은 억지로 0까지 끌어내리지 않는다**(과교정 금지).
2. **도메인별 직교 판별피처 ≥ 3개**: 각 AE가 다른 센서와 중복이 아닌, 고장을 구분하는 피처를
   최소 3개 갖는다(§7). 컬럼을 노이즈로 늘리는 게 아니라 관계 피처로 채운다.

- 천장(0.85)을 넘으면 artifact로 실패 → 해당 센서에 **진짜 독립 물리**가 있으면 고유성분으로 분해,
  아니면 그대로 두고 한쪽을 관계 피처로 대체.
- **쌍별 물리 목표**(참고용 — 천장보다 여유 있게, 0으로 만들지 말 것):

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
---

## 7. 관계 판별 피처 카탈로그 (고장 구분력의 진짜 레버)

원칙: 고장 신호는 raw 센서보다 **센서 간 관계**에 있다. 평소 함께 움직이던 값들이 특정 고장에서
어긋나는(diverge) 그 패턴을 피처로 만든다. 이 피처들은 (a) 물리적 고장 메커니즘을 직격하고,
(b) 운전점에 무관하게 정규화돼 있으며, (c) 원 센서와 직교 정보라 다중공선성 필터를 통과한다.

데이터가 현실화(센서별 독립 성분)되면 이 피처들이 비로소 **판별력**을 갖는다. 예: 진동에 독립 베어링
마모 성분이 생겼으므로 `vibration_per_load`(진동/부하)가 상수가 아니라 베어링 상태를 드러낸다.

| 도메인 | 피처 | 공식 | 잡는 고장 | 상태 |
|---|---|---|---|---|
| hydraulic | `system_resistance` | discharge_pressure / flow² | 하류 막힘(운전점 무관) | 구현됨 |
| hydraulic | `specific_energy` | motor_power / flow | 막힘·노후(단위유량당 전력↑) | 구현됨 |
| hydraulic | `pressure_divergence` | discharge − suction (정상 대비) | 흡입 막힘(둘이 벌어짐) | **신규** |
| hydraulic | `flow_demand_residual` | actual_flow − 기대유량(VPD·광량 기반) | "이 날씨면 이만큼 나가야" 대비 부족 | **신규** |
| motor | `vibration_per_load` | bearing_vibration / motor_power | 베어링 마모(부하 무관 진동↑) | **신규(데이터 현실화로 의미 생김)** |
| motor | `bearing_thermal_margin` | bearing_temp − motor_temp | 베어링 과열(공통 환경 제거) | 구현됨 |
| motor | `load_per_speed` | motor_current / pump_rpm | 과부하·기계 마찰 | 구현됨 |
| nutrient | `leaching_ratio` | drain_ec / mix_ec | 염류 축적(배액>공급, 공공데이터 근거) | **신규(drain_ec 독립화로 의미 생김)** |
| nutrient | `ec_control_error` | mix_ec − mix_target_ec | 도징·배합 오류 | **신규** |
| zone_drip | `zone_ec_variance`/`zone_moisture_variance` | std(zone1/2/3) | 국부 노즐 막힘(구역 편차) | 구현됨 |
| zone_drip | `irrigation_response_eff` | Δmoisture / zone_flow | 노즐 막힘(물 줘도 수분 안 오름) | **신규** |
| zone_drip | `substrate_ec_accum_rate` | d(zone1_substrate_ec)/dt | 염해 진행 | 구현됨 |

신규 우선순위: `vibration_per_load`(베어링·공동현상 직격, 데이터 현실화 효과 검증), `leaching_ratio`,
`flow_demand_residual`, `pressure_divergence`. 구현 위치: [preprocessing.py create_modeling_features](../../src/preprocessing.py).
각 피처는 09 원장에 근거와 함께 기록([09](09_feature_rationale_ledger.md)).

검증: 단순 상관 낮추기가 아니라 — 주입한 각 고장(fault_signatures)에서 해당 관계 피처가 실제로
튀는지(coupling_validate에 per-feature 반응 확인)로 "판별력"을 검증한다.

---

## 8. 검증된 공식·출처 (자료조사 — 우리가 지어내지 않고 표준/문헌 인용)

데이터 물리(Layer 2 결합)와 §7 관계 피처는 아래 검증된 공식에 근거한다. 공모전 공공데이터·문헌 근거.

### 8-1. 펌프 수력 (hydraulic)
- **시스템 곡선**: `H_system = H_static + K·Q²` (난류에서 마찰손실 ∝ 유량²). 막힘이 진행되면 K(저항계수)↑.
  → `system_resistance = discharge_pressure / flow²`가 곧 K의 대용지표. 운전점 무관하게 막힘을 직격.
- **상사법칙(affinity laws, 임펠러경 고정)**: `Q ∝ N`, `H ∝ N²`, `P ∝ N³` (N=회전수).
  → rpm–유량–압력–전력 결합의 물리적 근거. **단, 전면 도입 보류(2026-06-07)**: 실측상 이 펌프는
    **정속 운전**(rpm 1740~1796, ±1.5%)이라 속도가 거의 안 변해 affinity 스케일링 효과가 미미하다
    (affinity는 VFD 가변속에서 핵심). 대신 **막힘→작동점 이동**(유량↓+압력↑, 시스템 곡선에서 K↑)이
    활성 메커니즘이며 `system_resistance`가 직접 포착한다. 함의 효율 η≈11%로 스케일 일관
    (Q·ΔP/60000 ≈ 0.25kW vs motor 2.2kW). 면접 답: "정속 펌프라 affinity 생략, 막힘은 시스템 곡선(K↑)으로".
- **비에너지(specific energy)**: `SEC[kWh/m³] = (H·g·ρ)/(3.6e6·η)` (η=펌프 효율). 단위 유량당 에너지.
  → `specific_energy`(= motor_power/flow)는 SEC에 비례. 막힘·노후 시 상승.
- 출처: [PDHonline M125 Pump Parameters & Affinity Laws](https://www.pdhonline.com/courses/m125/m125content.pdf),
  [Pump Systems Academy — Affinity Laws](https://home.pumpsystemsacademy.com/blog/pump-affinity-laws),
  [ScienceDirect — Affinity Law overview](https://www.sciencedirect.com/topics/engineering/affinity-law).

### 8-2. 환경·증산 (irrigation demand)
- **VPD(수증기압 결손)**: `VPD = SVP − SVP·RH/100`,  `SVP[kPa] = 0.6108·exp(17.27·T/(T+237.3))` (Tetens, 0~50℃서 0.1% 정확).
- **증산 ∝ VPD**(광량 동반): VPD가 식물 증산=물·양분 수요의 주동인. 광량·VPD가 높을수록 관수 수요↑.
  → `flow_demand_residual = actual_flow − 기대유량(VPD·광량 기반)`. "이 환경이면 이만큼 나가야"의 기준.
- 출처: [Andrews Forest (OSU) — Dewpoint & VPD equations](https://andrewsforest.oregonstate.edu/sites/default/files/lter/data/studies/ms01/dewpt_vpd_calculations.pdf),
  [Omnicalculator — VPD](https://www.omnicalculator.com/biology/vapor-pressure-deficit). 권장 VPD 0.5~1.2 kPa는 공공데이터(딸기)와 일치.

### 8-3. 모터·베어링 (motor)
- **ISO 10816 진동 존**(이미 [10 §3-1 S2]): A≤1.4 / B≤2.8 / C≤4.5 / 정지>7.1 mm/s. 베어링 마모 시 RMS↑.
- 베어링 마모는 부하와 무관한 독립 과정 → `vibration_per_load = vibration/power`가 부하 정규화 진동으로 마모만 분리.
- (심화: 베어링 결함주파수 BPFO/BPFI는 주파수영역 — 현재 RMS 기반이라 후속.)

### 8-4. 양액 (nutrient)
- **배액률·leaching**: 배액 EC > 공급 EC = 염류 축적, < = 양분 부족(공공데이터 명시). 배액률 20~30% 정상.
  → `leaching_ratio = drain_ec / mix_ec` > 1 누적 = 염류 축적 신호.

> 구현 시 각 §7 피처의 09 원장 행 '출처' 칸에 위 링크를 박는다.
