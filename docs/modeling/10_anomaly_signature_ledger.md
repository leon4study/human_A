# 10 — 이상 시그니처 원장 (Anomaly Signature Ledger)

실제 현장에서 설비가 고장 났을 때, 각 센서에 **어떤 이상이 / 얼마나 크게 / 어떤 흐름으로** 나타나는지를 근거와 함께 정리한 문서입니다. 이 프로젝트가 "이 내용이 맞다"고 믿고 따르는 단일 기준입니다(SSOT — Single Source of Truth, 같은 사실을 여러 곳에 흩어 적지 않고 한 곳에만 두는 원칙). 데이터를 만드는 생성기가 이상값을 집어넣을 때 바로 이 문서의 내용을 따릅니다.

> 관련: 정상 범위·컬럼 정의는 [../COLUMNS_REFERENCE.md](../COLUMNS_REFERENCE.md), 도메인 구분은 [../DOMAIN_DESIGN.md](../DOMAIN_DESIGN.md), 파생 피처 근거는 [09](09_feature_rationale_ledger.md).

## 0. 왜 이 문서가 필요한가

지금 평가에 쓰는 이상 데이터는 생성기가 인위적으로 만든 것입니다. 구체적으로는 여러 센서의 표준화 점수를 평균낸 값(composite z-score — 각 센서가 평소보다 얼마나 벗어났는지를 합쳐 본 지표)이 2.0 이상인 지점을 이상으로 표시했습니다. 그래서 이 이상값들은 **실제 물리적 고장이 보이는 모습(시그니처)과는 다를 수 있습니다.** 따라서 지금의 F1 점수(엄격하게 평가하면 약 0.50)는 "우리가 만든 이상"을 얼마나 잘 맞히는지를 보여줄 뿐, 실제 현장에서의 탐지력을 보장하지는 않습니다. (F1은 빠뜨리지 않고 잡는 정도와 헛알람을 내지 않는 정도를 함께 반영한 0~1 사이의 탐지 성능 점수입니다.)

목표는 다음과 같습니다. **실제 고장이 났을 때 센서에 나타나는 현상을 근거(논문·센서 벤더의 벤치마크 값) 기반으로 정의하고 목록으로 만든 뒤, 그 모습 그대로 데이터에 집어넣는 것**입니다. 그래야 (1) 평가가 실제 의미를 갖고, (2) AE(오토인코더 — 정상 데이터만 학습해 그와 다른 패턴을 이상으로 찾아내는 모델)가 진짜 고장을 잡아내는지 검증할 수 있습니다.

## 1. 핵심 설계 원칙 — 상관된 다중 센서 편차

> 강사 제시 원칙: **진짜 고장이면 여러 값이 함께 요동친다. 한 값만 튀면 센서 하나의 문제를 의심하는 게 합리적이다.**

이 원칙을 이상값을 집어넣는 로직의 바탕에 둡니다.

- **실제 고장(real fault)** = 원인-결과로 엮인 **여러 센서가 동시에, 서로 맞물려** 함께 벗어나는 경우입니다. 예를 들어 하류(말단)가 막히면 유량↓·토출압↑·system_resistance↑가 같은 시점에 함께 나타납니다(전류는 약한 보조 신호입니다. §3-1 참조). 여러 센서를 함께 보는 AE는 이렇게 "여러 값이 함께 틀어지는" 모습을, 학습해 둔 정상 패턴(manifold — 정상 데이터가 모여 있는 영역)에서 크게 벗어난 것으로 보고 강하게 잡아냅니다.
- **센서 자체 이상(sensor fault)** = **센서 한 개만** 벗어나고(값이 서서히 밀리는 드리프트, 한 값에 멈추는 스턱, 잠깐 튀는 스파이크) 나머지는 정상인 경우입니다. 이때는 한 개 항목의 오차만 커서 AE가 약하게 반응합니다. 그래서 진짜 고장과 구분됩니다.

→ 따라서 데이터 생성기는 이 둘을 **서로 다른 라벨로, 서로 다른 방식으로** 만들어야 합니다. 실제 고장은 여러 센서를 함께(상관되게) 흔들고, 센서 이상은 한 개만 흔듭니다.

### 1-2. 고장은 "정적 이상"이 아니라 "열화 트라젝토리 → 고장 이벤트"

예지보전(고장을 미리 예측해 대비하는 정비)의 핵심은 고장 그 자체가 아니라 **고장으로 가는 누적 과정을 미리 잡아내는 것**입니다. 그래서 이상을 한 순간의 점이 아니라 **2단계 흐름(궤적)**으로 집어넣고 평가합니다.

```
정상  →  [열화 누적 구간(degradation ramp)]  →  고장 이벤트(failure: 트립/완전막힘/정지)
          ↑ 사전 예측 포인트 — 여기서 알람이 떠야 가치 (고장 전)
```

- **열화 누적 구간**: 물때(scale)·생물막(biofilm)·마모가 쌓이면서, 서로 맞물린 여러 센서가 **서서히** 틀어지는 완만한 상승 구간(ramp)입니다. 강사 원칙("여러 값이 함께 요동친다")이 여기서 **진행 중인 형태**로 나타납니다. **바로 이 구간을 잡는 것이 목표입니다.**
- **고장 이벤트**: 누적이 한계에 닿은 뒤의 결과입니다(보호 회로가 멈추는 트립, 완전히 멈추는 shutoff, 정지). 이 시점은 이미 늦어서 예측 가치가 없습니다(라벨을 붙이고 검증할 때의 기준점으로만 씁니다).
- **성공 지표 = lead time(여유 시간)**: 한 순간의 정답 여부를 따지는 point-F1이 아니라, "**고장이 난 시점보다 얼마나 일찍 알람을 띄웠는가**"입니다. 포트폴리오에서도 "F1 0.x"라는 숫자보다 "평균 N시간 전에 미리 감지"가 예지보전의 진짜 가치입니다.
- 갑자기 터지는 급성 고장(예: 메인 밸브가 닫혀 유량이 급격히 끊기고 전류가 뚝 떨어지는 경우)은 완만한 상승 없이 계단처럼(step) 오므로, **별도 모드**로 구분합니다.

## 2. 기록 양식 (각 고장 모드 1행)

| 필드 | 의미 |
|---|---|
| 고장 모드 | 무엇이 고장났나 (예: 점적 노즐 막힘) |
| 영향 센서 | 어느 센서들이 함께 움직이나 (다중 = real fault) |
| 방향 | 각 센서 ↑/↓ |
| 크기(Δ) | 정상 대비 변화량/비율 (벤더 정상범위 기준) |
| 동역학 | 속도(급성/만성), 주기, 사이클, 강도 프로파일 |
| 출처 | 논문·벤더 스펙·벤치마크 (필수, 없으면 "추정"으로 표기) |

원칙: **출처가 없는 값은 "추정"이라고 분명히 표시합니다.** 추정값과 근거가 있는 값을 섞어 적지 않습니다(정직하게 구분하기 위해서입니다).

## 3. 도메인별 고장 모드 목록 (연구 아젠다 — 값은 §2 양식으로 채움)

> 아래는 앞으로 채워 넣을 항목들의 뼈대(skeleton) 목록입니다. 각 항목의 "영향 센서·크기·동역학·출처"는 자료조사 단계(웹·논문·센서 벤더 자료)에서 채웁니다.

### 3-1. hydraulic (막힘·누수 — 프로젝트 핵심) — 자료조사 완료(2026-06-02)

**중요: "막힘"은 한 종류가 아닙니다.** 어디가 막혔느냐에 따라 여러 센서에 나타나는 모습(시그니처)이 다릅니다. 특히 **하류(말단의 점적·노즐) 막힘에서는 전류가 오히려 ↓ 내려갑니다.** 펌프 특성 곡선상 작동점이 유량이 거의 없는 쪽(shutoff)으로 이동하는데, 유량↓·양정(물을 밀어 올리는 높이)↑이 되면서 펌프가 실제로 쓰는 동력(brake power)이 줄기 때문입니다. 반대로 전류가 ↑ 올라가는 경우는 **임펠러(회전 날개) 막힘**으로 효율이 떨어졌을 때입니다 [S1][S6]. 이 구분이 현실적인 이상 주입의 핵심입니다.

**정상 기준값 (표준·벤더·논문)**
- 점적 관수 정상 입구 압력 약 **2 bar**(=200 kPa), 정상 유량 안정값 예시 **2.8 m³/h**. 압력 경보 밴드 저 **0.6 bar** / 고 **2.5 bar**, 균일 분배 최소 **1 bar** [S3].
- 점적 막힘의 ISO 정의: **실제 유량 < 설계 유량의 75%** [S4].
- 펌프 진동(ISO 10816-3/-7, 비회전부 RMS 10~1000 Hz): Zone A ≤ **1.4 mm/s**(우수) / B ≤ **2.8**(장기 허용) / C ≤ **4.5**(점검) / 정지 권고 **> 7.1 mm/s** [S2].
- 흡입측 막힘 시 흡입 게이지 비정상 고진공 **-68 ~ -85 kPa**(>20~25 inHg) [S1].

**막힘 3종 — 다중 센서 시그니처**

| 고장 모드 | discharge_pressure | flow_rate | suction_pressure | motor_power/current | vibration | system_resistance(P/flow²) | 동역학 | 출처 |
|---|---|---|---|---|---|---|---|---|
| **하류(점적/노즐) 막힘** | ↑ (shutoff 접근) | ↓ (<75% 설계) | 정상 | **↓~보합**(곡선상 저유량) | 보통(심하면 cavitation시 ↑) | **↑↑(가장 직접)** | 만성: scale·biofilm 누적(일~주, 점진) / 급성: 이물질(분 단위) | [S1][S3][S4][S6] |
| **임펠러 막힘**(이물질) | 변동(↓ 가능) | ↓ | 정상~약↓ | **↑**(효율 손실·기계 부하) | **↑**(불평형) | ↑ | 급성~아급성 | [S1][S5] |
| **흡입측 막힘/스트레이너** | ↓ | ↓ | **고진공(-68~-85 kPa)** | ↓ | ↑(cavitation 시) | — | 급성~만성 | [S1] |

→ **공통점(강사 원칙)**: 어떤 막힘이든 **유량↓와 함께, 그에 맞물린 압력·저항·진동 변화가 동시에** 나타납니다. 만약 센서 한 개(예: 압력 게이지)만 변한다면 고장이 아니라 **센서 자체의 이상**을 의심합니다(§3-5).

**흐름(트라젝토리, §1-2)**: 막힘은 한 순간의 이상이 아니라 **서서히 나빠지는 구간(열화 ramp) → 고장** 순서로 집어넣습니다.
- 누적 구간(며칠~몇 주에 걸쳐 물때·생물막이 쌓이는 동안): `flow_rate_l_min`(유량)이 서서히↓(설계값의 100%에서 점점 줄어 75%에 접근), `discharge_pressure_kpa`(토출압)가 서서히↑, `system_resistance`(시스템 저항)가↑↑(가장 먼저·가장 강하게 반응), `pressure_flow_ratio`가↑, `flow_drop_rate`가 1에 접근합니다. (임펠러형 막힘이라면 `motor_current_a`(전류)와 `bearing_vibration_rms_mm_s`(진동)도 함께↑.) — **바로 이 구간이 탐지 대상이자 lead-time(여유 시간) 측정 대상입니다.**
- 고장 이벤트(끝점): 유량이 75% 미만(ISO 막힘 기준)에 도달하거나 보호 회로가 멈추는(트립) 시점입니다. 라벨을 붙일 때의 기준점입니다.
- 별도의 급성 모드: 메인 밸브가 닫히면 몇 분 안에 계단처럼(step) 유량이 급감하고 전류가 뚝 떨어집니다(서서히 나빠지는 구간 없이).

### 3-1b. 누수·밸브·필터·캐비테이션 (자료조사 예정)
- 누수 (leak) — 압력↓·유량 불균형(`supply_balance_index`<1)
- 밸브 이상 — 구역별 압력/유량 편차
- 필터 오염 — `filter_delta_p`↑ (정상 7~8, 경고>15, 위험>25 kPa, COLUMNS_REFERENCE 기준)
- 캐비테이션 — 흡입압↓·진동↑·소음(고주파)

### 3-2. motor (구동부)
- 베어링 마모 — 진동↑·베어링온도↑·전류 미세↑ (다중)
- 권선 절연 열화 — 전류·온도↑·효율↓
- 과부하 — 전류·전력·온도↑, RPM 불안정

### 3-3. nutrient (양액 화학)
- A/B 배합 비율 오류 — EC 이탈·pid_error_ec↑·탱크 소모 불균형
- EC/pH 센서 드리프트 — **단일 센서** 천천히 이탈 (= sensor fault 사례)
- 염류 축적 — drain_ec↑·salt_accumulation↑

**농학·화학 교차관계 연구 아젠다 (미조사 — 다음 데이터 현실화 단계, 2026-06-07 추가)**
현재 EC/pH는 setpoint+노이즈 수준이라 화학적 충실성이 낮다. 아래 표준 농학 관계를 자료조사해 데이터에
반영하면 nutrient/zone_drip 도메인이 의미를 갖는다(공공데이터 딸기 ppm·EC·pH 범위와 결합).
- **나트륨(Na) 축적**: Na⁺↑ → EC↑ + 삼투 스트레스(수분 있어도 흡수↓) + K·Ca 흡수 길항 + Cl 독성. 순환식 → 배액 축적, `leaching_ratio`↑.
- **pH ↔ 양분 가용성**: pH가 이온 용해도 결정(고pH→Fe·P 결핍, 저pH→Mn 독성). 딸기 적정 5.5~6.5.
- **pH ↔ 기온/수온**: 수온↑ → 미생물 활성·CO₂ 용해 변화 → pH 드리프트.
- **습도 ↔ VPD ↔ 증산 ↔ 병해**: 고습→저VPD→증산↓→양분흡수↓+결로/잿빛곰팡이. 저습→고VPD→수분 스트레스.
- **EC ↔ 삼투 ↔ 수분흡수**: 고EC → 삼투 스트레스로 수분과 흡수가 디커플(수분 정상인데 흡수↓).
- **이온 균형(N·P·K·Ca·Mg)**: K-Ca-Mg 길항. 공공데이터 ppm 범위 기준.
→ 출처: 자료조사로 채움(논문·원예 표준). 진행은 baseline 확정 후 별도 단계.

**데이터 현실화 설계 v6 — 검증 공식 + 인코딩 (2026-06-07; C1·C2·C5 구현됨, C3·C4 후속)**
baseline·motor FAR이 확정됐으므로(Phase J~L) 이제 nutrient/zone_drip의 화학적 충실성을 올린다.
아래는 표준 공식과 data_gen 인코딩 스펙이다. 한 번의 data_gen 개정 + 재학습 1회로 묶는다(열지연 포함).

- C1. **Na 축적 상태변수 (순환식 질량수지)** — 신규 컬럼 `na_accumulation_mmol_l`.
  닫힌 순환계에서 Na는 식물이 물을 Na보다 빨리 흡수해 배액에 농축된다. 단순 질량수지:
  `Na[t] = Na[t-1] + (유입 Na − 흡수 Na)/부피`. 흡수≈0(딸기 Na 거의 비흡수)로 두면 단조 증가.
  딸기 임계 1.5 mmol/L(35 ppm) 초과 시 염 스트레스 플래그. 정상 운전엔 주기적 배액교체로 리셋.
  → Na↑가 `mix_ec_ds_m`(+0.1 dS/m per mmol 근사)·`drain_ec_ds_m`·`leaching_ratio`를 함께 끌어올림.
- C2. **EC → 삼투 → 수분·흡수 디커플** — 신규 컬럼 `osmotic_potential_mpa`.
  `Ψ_osm(MPa) = -0.036 × mix_ec_ds_m`(Handbook 60). 고EC면 수분이 있어도 흡수가 막힌다 →
  `uptake_efficiency = clip(1 − k·max(0, EC − EC_opt), …)`. 이게 "수분 정상인데 흡수↓"를 만든다.
- C3. **pH ↔ 수온 드리프트** — `mix_ph`에 수온 의존 항. 수온↑ → CO2 용해↓·미생물 활성↑ → pH 소폭 상승.
  선형 근사 `pH += a·(mix_temp_c − T_ref)`(a≈0.01~0.02/°C, 자료 추가조사). 딸기 적정 5.5~6.5 밴드.
- C4. **습도 ↔ VPD ↔ 증산** — VPD는 Tetens(§8 기보유)로 산출, `transpiration_demand` 정련.
  고습→저VPD→증산↓→양분흡수↓(C2 흡수효율과 결합). 저습→고VPD→수분 스트레스.
- C5. **열적 관성 (motor_temp·rpm jitter 근본)** — `motor_temperature_c`를 1차 지연으로.
  현재 백색노이즈를 온도 본체에 직접 더해(관성 부재) 분단위 jitter가 큼(Phase L 원인). 개정:
  `target = air_temp + 13·pump_on + ar1; T = target.ewm(alpha=1/τ).mean()`(τ≈10~20분) `+ 측정노이즈(얇게)`.
  물리 온도가 매끄러워져 원시 슬로프도 자연 정제(robust 슬로프와 상호보완).

검증 게이트: 개정 후 독립성 게이트 통과 + 각 관계가 의도 방향으로 움직이는지(예: Na↑→EC↑→osmotic↓→
uptake↓) coupling_validate류로 확인. 출처: EC-삼투 US Salinity Lab Handbook 60, Na 임계 원예 표준(딸기
<1.5 mmol/L). 상세 공식·계수는 구현 시 §8(검증 공식)과 12 설계문서에 동기.

### 3-4. zone_drip (구역 배지)
- 노즐 막힘 — 해당 구역 수분 반응 지연·구역 간 편차↑
- 관수 불균일 — zone_moisture_variance↑
- 배지 염해 — substrate_ec↑·축적속도↑

### 3-5. 단일 센서 이상 (대조군 — sensor fault) — 실험 완료(2026-06-04)

단일 센서에만 결함을 주입해(상관 없음), AE가 진짜 고장(다중 센서 동반)과 이를 구분하는지 검증한다.

- 구현: [fault_injection/sensor_faults.py](../../fault_injection/sensor_faults.py)(drift·spike·stuck 단일 컬럼 주입),
  [fault_injection/sensor_fault_eval.py](../../fault_injection/sensor_fault_eval.py)(판별 지표 계산).
- 모드: drift(캘리브레이션 누적 오프셋), spike(지속 급변), stuck(고착 flatline). 각 1개 센서만.
- 타깃: hydraulic 도메인, `discharge_pressure_kpa` 단일 센서. 대비군은 §3-1 실제 막힘(다중 센서) `faulty_testset_v1`.

판별 지표(윈도우별, 스케일 공간 per-feature 제곱오차 행렬에서 산출):
- `total MSE` — 알람 발생 여부(임계값 대비).
- `concentration` = max_f e_f / Σ_f e_f. 1에 가까울수록 한 피처에 오차 집중(센서 문제), 균등(~1/F)에 가까울수록 광범위(진짜 고장).
- `n_active` — 정상 대비(피처별 mean+3σ) 오차가 큰 피처 수.

실험 결과(F=13, caution 임계값 0.00077):

| 시나리오 | 알람률 | 집중도 | 활성피처 |
|---|---|---|---|
| clean(대조) | 0.01 | 0.49 | 0.1 |
| sensor:drift (단일) | 0.99 | 0.88 | 8.4 |
| sensor:spike (단일) | 1.00 | 0.92 | 11.4 |
| sensor:stuck (단일) | 0.51 | 0.49 | 5.4 |
| clog(진짜·다중) | 0.69 | 0.45 | 4.4 |

핵심 발견(정직):
1. **총 MSE/알람만으로는 구분 불가.** 단일 센서 drift·spike가 오히려 진짜 막힘(0.69)보다 알람을 더 자주 띄운다(0.99~1.00). 정상으로 학습한 AE는 단일 센서가 크게 벗어나도 off-manifold라 반응하기 때문. 강사 원칙의 우려가 데이터로 확인됨.
2. **집중도(concentration)가 판별 신호.** 단일 센서 drift·spike는 0.88~0.92로 한 피처에 집중되고, 다중 동반인 막힘은 0.45로 퍼진다. "한 값만 튐=센서 문제 / 여러 값 동반=진짜 고장"을 정량화한다.
3. **한계.** ① `n_active`는 판별자로 부적합 — 큰 spike는 AE 재구성을 전반적으로 교란해 활성 피처가 오히려 늘어난다(11.4 > 막힘 4.4). 따라서 집중도를 주 지표로 쓴다. ② `stuck`(고착)은 집중도 0.49로 애매하다 — flatline이 파생(trend) 피처로 퍼져 신호가 약하다. 고착형 센서 결함은 이 방법으로 깔끔히 분리되지 않는다(별도 규칙: 분산 0 검출 등 보완 필요).

운영 함의: 도메인 알람이 떴을 때 그 윈도우의 집중도를 함께 보면, 정비팀이 "설비 고장 점검" 대 "센서 점검"을 1차 분기할 수 있다.

주의: 본 실험은 현재 서빙 모델(`services/inference/models/`, 2026-04-22 학습)로 수행했다. 이후 피처 엔지니어링·zone_drip 토양센서 복원이 반영 안 된 구버전이므로, 재학습 후 수치는 갱신될 수 있다(아래 §6).

### 3-6. 영향 모델 일반화 + baseline 검출 지도 (Phase 1, 2026-06-05)

고장을 '근본 원인 → s(t) → 가중치로 다중 센서/도메인 전파'의 **영향 프로파일**로 일반화했다
([fault_signatures.py](../../fault_injection/fault_signatures.py)). 방향 패턴은 물리 결합 생성기
`data_gen_jun`의 clog 계수에서, 절대 크기·일부 방향 보정(예: 하류 막힘 전류는 펌프곡선상 ~flat/↓,
jun의 ↑를 보정)은 §3 자료조사에서 가져왔다. 위치 라이브러리 4종:

- `hydraulic_clog_downstream` — 광역(4도메인 전파): 유량↓·토출압↑ 축 + 진동·drain_ec·turbidity 동반.
- `motor_bearing_wear` — motor 국소: 진동↑↑·베어링온도↑·마찰전류↑. 수력 라인 거의 불변(대비군).
- `hydraulic_suction_blockage` — 흡입측: 고진공+유량↓+**토출압↓**(하류와 반대)+공동 진동↑.
- `nutrient_imbalance` — nutrient 국소: EC·pH 드리프트.

검증([coupling_validate.py](../../fault_injection/coupling_validate.py)): 데이터 레벨 ripple이 각
위치의 `propagates_to`와 일치 — 위치를 바꾸면 의도한 센서 집합이 가중치대로 움직인다(강사 원칙 구현 확인).

현재 6/2 모델(`PROJECT_ROOT/models`) baseline 검출 지도 — 고장 구간 도메인별 알람률(≥Caution):

| 고장 | hydraulic | motor | nutrient | zone_drip | 기대 |
|---|---|---|---|---|---|
| clog_downstream | 0.97 | 0.70 | 0.87 | 0.86 | 4도메인(광역) |
| bearing_wear | 0.00 | 0.98 | 0.00 | **0.98** | motor만 |
| suction_blockage | 0.98 | **0.08** | 0.55 | 0.64 | hydraulic+motor |
| nutrient_imbalance | 0.00 | 0.00 | 0.98 | 0.00 | nutrient만 |

드러난 약점(Phase 2 타깃):
1. **zone_drip이 motor 베어링 고장에 오탐(0.98)** — zone_drip 피처에 `motor_temperature_c`가 들어가
   경계 누설. 베어링이 motor_temp를 +6.5% 올리자 zone_drip AE가 반응. 도메인 경계 정리 필요.
2. **motor가 흡입 막힘의 진동(+45%)을 놓침(0.08)** — motor 진동 민감도 부족. `vibration_per_load`(§3-4) 검토.
3. nutrient가 수력 고장에 부분 오탐(clog 0.87/suction 0.55) — 단 nutrient는 voting 제외라 영향 제한.

clog가 4도메인 모두 켜는 것은 오탐이 아니라 **실제 광역 전파(정상)**. 문제는 국소 고장(bearing·suction)이
엉뚱한 도메인을 켜는 것. 이 baseline이 Phase 2(피처·경계 정리)·Phase 3(재학습) 변경을 재는 고정 기준이다.

Phase 2 #1 구현(2026-06-05): 위 약점 1(경계 누설)의 원인은 SHAP 피처 선택이 '전체 센서 풀'에서
골라 zone_drip이 motor_temperature_c 등 타 도메인 센서를 spurious 선택한 것이다. 환경변수
`DOMAIN_ISOLATION=1`이면 각 도메인 피처 선택에서 '다른 도메인의 핵심 센서(SENSOR_MANDATORY)'를
후보에서 제외한다([train.py](../../src/train.py)·[feature_selection.py](../../src/feature_selection.py)).
기본 OFF(동작 불변). A-3(피처 선택 변경이 전 도메인 F1 붕괴) 위험 지대라, 재학습 시 ON/OFF를
coupling_validate로 비교해 회귀 없는지 확인한 뒤 도입한다.

약점 2(motor 진동 못 봄)의 진짜 원인은 민감도가 아니라 **진동 센서 자체가 model_cols 누락으로 잘려
motor 피처에 없던 것**이었다(Phase H). model_cols에 추가해 수정.

수정 후 재측정(2026-06-06, `DOMAIN_ISOLATION=1` + 진동 fix, run `..205644..retrain-fix-iso`):

| 고장 | 수정 전(버그) | 수정 후 | 기대 |
|---|---|---|---|
| bearing_wear | motor + **zone_drip 오탐** | **motor만** | motor만 |
| suction_blockage | hydraulic+nutrient+zone (**motor 놓침 0.08**) | **hydraulic+motor** | hydraulic+motor |

두 수정이 각각 예측대로 동작 확인 — 진동 fix로 motor가 흡입 진동 검출 회복, 격리로 zone_drip의
motor_temp 누설 오탐 제거(zone_drip 피처에서 motor_temperature_c 사라짐). lead-time 29.9h→35.9h,
기동 FAR 0%, 정상 FAR 1.4%. 상세: MODEL_CHANGELOG Phase H·I.

캐노니컬 데이터 전환 후 재측정(2026-06-07, dabin→jun v5 정상셋, `DOMAIN_ISOLATION=1`,
run `..110219..`): 이 baseline부터는 **jun 정상셋**(공공앵커+독립 AR(1), 인위적 ~1.0 상관 제거)
위에서 잰다. 검출 지도(고장 구간 도메인별 알람률 ≥Caution):

| 고장 | hydraulic | motor | nutrient | zone_drip | 기대 | root |
|---|---|---|---|---|---|---|
| clog_downstream | 1.00 | 0.86 | 0.36 | 0.00 | 광역 | O |
| bearing_wear | **0.43** | 0.93 | 0.14 | 0.00 | motor만 | O |
| suction_blockage | 1.00 | 0.86 | 0.14 | 0.00 | hydraulic+motor | O |
| nutrient_imbalance | 0.29 | **0.86** | 1.00 | 0.00 | nutrient만 | O |

4 root 모두 검출(O)하나 Phase I의 깨끗함이 일부 후퇴 — bearing_wear에 hydraulic 0.43 오탐 재등장,
nutrient_imbalance에 motor 0.86 오탐. 이는 **motor 도메인의 과발화**와 같은 뿌리다:

- **FAR 회귀**: AE overall 정상 FAR 6.5%(> baseline 3.2%, > 5% 목표). 도메인 분해 — motor **6.3%(주범)**,
  hydraulic 2.7%, nutrient 1.1%, zone_drip 1.1%. Phase I(dabin)는 1.4%였다.
- 검출 자체는 유지: clog 6/6, 막힘률 0%, AE lead-time 47.5h(같은 데이터 baseline 45.5h).
  단 lead-time은 dabin 35.9h와 직접 비교 불가(에피소드 배치가 다른 데이터셋).
- 집중도 판별 비재현: clog 0.65 > sensor drift/spike 0.40(역전). dabin의 '단일 0.88~0.92 vs 다중 0.45'가
  jun에서 깨짐 — hydraulic 피처 축소(F=15) + 단일 드리프트가 파생피처로 퍼진 탓. 판별식은 피처구성 의존적.

진단: 데이터 현실성이 오르며 생긴 현실적 노이즈가 motor 재구성오차 분포를 넓혀 sigma threshold가
6.3% FAR을 낸다. motor에 강제주입된 노이즈성 비율피처(vibration_per_load·temp_slope_c_per_s) 1차 용의자.
다음 회차: motor FAR을 5%↓로 되돌리는 수정(threshold percentile화 또는 노이즈피처 정리) 후 재측정해
Phase I 대비 회복 확인. 상세: MODEL_CHANGELOG Phase J.

조건부 마스크 수정 후 재측정(2026-06-07, run `..205502..`): 자유 파생피처 pressure_diff·flow_diff가
어느 도메인 mandatory에도 없어 SHAP이 엉뚱한 도메인에 배정 → motor 등 채점을 오염시킨 게 FAR
상승·attribution 오탐의 공통 뿌리였다. 이들을 '입력 유지 + 채점 제외'(조건부 마스크,
[feature_engineering.foreign_scoring_features](../../src/feature_engineering.py))하니 둘 다 풀렸다.

| 고장 | Phase J(누설) | Phase K(채점제외) | 기대 |
|---|---|---|---|
| clog_downstream | hydraulic+motor+nutrient | hydraulic+nutrient (motor 0.29) | 광역 |
| bearing_wear | motor + **hydraulic 0.43(오탐)** | **motor만**(hydraulic 0.07) | motor만 |
| suction_blockage | hydraulic+motor | hydraulic+motor | hydraulic+motor |
| nutrient_imbalance | nutrient + **motor 0.86(오탐)** | **nutrient만**(motor 0.21) | nutrient만 |

- FAR(정합 eval): motor 6.0→5.1%, nutrient 2.1→0.9%, zone_drip 2.7→0.3%, overall 6.2→5.4%.
- 검출 유지: clog 6/6, 막힘률 0%, lead-time 47.3h. 4 root 모두 검출 O.
- 잔여: motor 5.1%(목표 경계·baseline 3.2% 초과) — 유지 선택한 노이즈 슬로프(rpm_slope·temp_slope).
  옵션은 motor threshold percentile화. 상세: MODEL_CHANGELOG Phase K, MODELING §5-2-1.

robust 슬로프 수정 후 재측정(2026-06-07, run `..212812..`): rpm_slope·temp_slope의 원시 1차 차분이
분 단위 센서 jitter를 증폭한 게 motor 5.1% 잔여의 원인. 트레일링 이동평균 기반 robust 슬로프로 교체
(잔차노이즈 temp -72%·rpm -55%, 과열 ramp 보존)하니 **motor FAR 5.1→2.7%(baseline 3.2% 미만)**,
overall 5.4→4.2%. 검출 6/6·lead-time 45.4h 유지(robust 평활로 47.3→45.4h). 부수효과로 motor skew
8.30이 cutoff(8.0)를 넘겨 threshold가 percentile로 자동 전환. attribution 유지(4 root O, nutrient_imb의
motor만 경계 0.3 잔존). 도메인별 FAR 모두 baseline 미만(motor 2.7·hydraulic 1.9·nutrient 0.9·zone 0.3);
overall 4.2%는 4도메인 OR이라 baseline(3.2%)보다 약간 높음. 상세: MODEL_CHANGELOG Phase L.

threshold 목표-FAR 통제 후 정본화(2026-06-08, Phase N): C v6(Phase M)에서 FAR이 도메인을 옮겨다니며
재발(motor 해결→hydraulic 4.1%)한 근본은 sigma가 도메인 fit 타이트함에 FAR을 묶은 것. threshold를
percentile(정상 상위 1%=PCT_CAUTION 99)로 고정하니 per-domain FAR이 hydraulic 4.1→1.8·motor 1.5→0.5·
nutrient 0.7→0.4·zone 0.6→0.0, **overall 5.0→2.3%(baseline 3.4% 미만)** 로 통제됐다. 검출 6/6·막힘률 0%,
lead-time 47.3→43.9h(완화 비용), attribution 가장 깨끗(clog→hydraulic만 등). train.py 기본값을 percentile@99로
전환(method auto→percentile). FAR 작업(J~N) 종결. 상세: MODEL_CHANGELOG Phase N.

## 4. 데이터 생성기 연동 (구현 위치)

- 주입 지점(이상값을 집어넣는 코드 위치): [data_gen_jun.py `simulate_degradation`](../../src/data_gen_jun.py), [data_gen_dabin.py](../../src/data_gen_dabin.py).
- **공통 잠재 고장강도 s(t)**: 고장 한 건마다, 눈에 안 보이는 '고장 진행 정도'를 나타내는 값 s(t)를 둡니다. 이 값은 고장이 시작되는 시점부터 끝(고장)까지 0에서 1로 서서히 커집니다(물때·생물막은 며칠~몇 주에 걸쳐, S자 또는 직선 모양으로). 각 영향 센서의 변화량 Δ = s(t) × (그 센서의 §3 시그니처에 적힌 크기·방향)입니다. 즉 **하나의 숨은 값이 여러 센서를 서로 맞물리게(상관되게) 끌어당겨**, 강사 원칙("여러 값이 함께 요동친다")을 그대로 구현합니다.
- **고장 이벤트**: s(t)가 한계(예: 유량이 75% 아래로 떨어지는 지점)에 닿는 순간을 고장(failure)으로 표시합니다.
- 센서 이상(sensor fault, 대조군): s(t) 없이 **센서 한 개에만** 드리프트·스파이크를 넣습니다(다른 센서와 맞물리지 않게).
- 라벨: `anomaly_label`은 누적 구간과 고장 구간 모두 1로 둡니다. 여기에 더해 `degradation_severity`(=s(t))·`failure_time`·`fault_mode`·`sensor_fault_flag`를 함께 저장합니다. 그래야 lead-time(여유 시간)을 재고, 진짜 고장과 센서 이상을 나눠서 평가할 수 있습니다.

## 5. 검증 (주입 후 무엇을 확인하나)

- **lead-time(여유 시간, 핵심)**: 각 고장에 대해 AE 알람이 **고장 시점(failure_time)보다 얼마나 일찍** 떴는지를 봅니다. 평균 lead-time과 사전 감지율(고장 전에 알람을 한 번이라도 띄운 비율)을 함께 봅니다.
- AE가 **진짜 고장(여러 센서가 함께 서서히 틀어지는 경우)**에는 누적 구간에서 점점 강하게, 일찍 반응하는지(많이 잡아내는지, recall↑)를 봅니다.
- AE가 **sensor fault(단일 센서)**에 어떻게 반응하는가 — §3-5 실험 결과: 총 MSE/알람으로는 진짜 고장과 구분 불가(단일 센서도 알람 뜸). 구분은 per-feature **집중도**로 한다(단일=집중 0.88~0.92, 다중=퍼짐 0.45). stuck은 예외(애매).
- 도메인별 진단 그림에서 ramp 구간이 임계선을 점진적으로 넘는지([06](06_visualization_logging.md)).
- 통과 시 그때의 lead-time·F1이 "실제 고장 사전 감지력"의 정직한 지표 → portfolio reframe(A)에 사용.
- 이게 성립하면 그때의 F1이 "실제 고장 탐지력"의 정직한 지표가 된다 → 포트폴리오 숫자 reframe(A).

## 6. 진행 단계

1. 본 원장 프레임 확정(이 문서). — 완료
2. **자료조사로 값 채우기** — 도메인별로 영향 센서·Δ·동역학·출처. hydraulic 막힘부터. — hydraulic(§3-1) 완료, motor/nutrient/zone_drip 예정.
3. 데이터 생성기에 상관 주입 구현 + sensor fault 대조군. — 완료(hydraulic 막힘 주입 + §3-5 단일센서 대조군 실험).
4. **재학습 + 평가 + 검증(§5).** — 미완. 현재 평가는 구버전 서빙 모델(2026-04-22)로 수행됨. 이후 피처 변경·zone_drip 복원이 반영 안 됨 → 재학습 후 lead-time·집중도 수치 갱신 필요. 통과 시 portfolio 숫자 reframe(A).

## 7. 출처 (Sources)

자료조사로 채운 값의 근거. 출처 없는 값은 본문에서 "추정"으로 표기한다.

- [S1] 원심펌프 막힘·저유량 진단 — [SpringPump Centrifugal Pump Troubleshooting](https://springpump.com/centrifugal-pump-troubleshooting/), [UNITEC: Low Flow/No Discharge Diagnostic Guide](https://www.unitecd.com/centrifugal-pump-low-flow-no-discharge-a-diagnostic-troubleshooting-guide-for-maintenance-engineers/)
- [S2] 펌프 진동 한계 (ISO 10816-3/-7) — [ISO 10816-3 Zones A/B/C/D mm/s (Vibromera)](https://vibromera.eu/glossary/iso-10816-3/), [ISO 10816-3 Severity Table (DSP Analytic)](https://dspanalytic.com/en/vibrations/understanding-the-iso-10816-3-vibration-severity-table/), [Europump Pump Vibration Guidelines](https://www.europump.net/files/Publications/Guides/Guidelines%200n%20Pump%20Vibration%20First%20edition%20Final%20July%202013.pdf)
- [S3] 점적 관수 정상 압력·유량·경보 밴드 — [Implementation of a WSN for drip irrigation management (Scientific Reports / PMC12019383)](https://pmc.ncbi.nlm.nih.gov/articles/PMC12019383/)
- [S4] 점적 막힘 ISO 정의(유량 <75% 설계) — [Emitter hydraulic performance & clogging (PMC10973410)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10973410/)
- [S5] 임펠러 막힘 진동·전류 진단 — [Clogged impeller diagnosis using vibration and motor current analysis (ResearchGate 330663300)](https://www.researchgate.net/publication/330663300_Clogged_impeller_diagnosis_in_the_centrifugal_pump_using_the_vibration_and_motor_current_analysis), [Inlet pipe blockage level identification by deep learning (ScienceDirect S0263224121010654)](https://www.sciencedirect.com/science/article/abs/pii/S0263224121010654)
- [S6] 펌프 곡선·throttle 시 전력/전류 거동 — [Centrifugal Pump Performance Curve (BBP Pump)](https://bbppump.com/centrifugal-pump-performance-curve-explained/), [Pump current under low-head (StreamPumps)](https://www.streampumps.com/pump-knowledge/pump-low-head-knowledge.html)

> 다음 회차: §3-1b(누수·밸브·필터·캐비테이션) → §3-2 motor(베어링 ISO 10816 + MCSA) → §3-3 nutrient → §3-4 zone_drip 순으로 자료조사 확장. (§3-5 단일센서 대조군은 실험 완료.)
