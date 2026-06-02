# 10 — 이상 시그니처 원장 (Anomaly Signature Ledger)

실제 현업에서 설비 고장이 생겼을 때 **각 센서에 어떤 이상이, 얼마나, 어떤 동역학으로 나타나는가**를 근거와 함께 정리하는 SSOT입니다. 데이터 생성기의 이상 주입 로직이 이 문서를 따릅니다.

> 관련: 정상 범위·컬럼 정의는 [../COLUMNS_REFERENCE.md](../COLUMNS_REFERENCE.md), 도메인 구분은 [../DOMAIN_DESIGN.md](../DOMAIN_DESIGN.md), 파생 피처 근거는 [09](09_feature_rationale_ledger.md).

## 0. 왜 이 문서가 필요한가

현재 평가셋의 이상은 데이터 생성기가 만든 합성 이상(composite z-score ≥ 2.0)이라, **실제 물리 고장의 시그니처와 다를 수 있다**. 그래서 지금의 F1(엄격 평가 약 0.50)은 "우리가 만든 이상"에 대한 점수일 뿐, 실제 현장 탐지력의 보증이 아니다.

목표: **실제 고장 시 센서에 나타나는 현상을 근거(논문·벤더 벤치마크) 기반으로 정의·리스트업하고, 그 시그니처대로 데이터에 주입**한다. 그래야 (1) 평가가 의미를 갖고, (2) AE가 진짜 고장을 잡는지 검증 가능하다.

## 1. 핵심 설계 원칙 — 상관된 다중 센서 편차

> 강사 제시 원칙: **진짜 고장이면 여러 값이 함께 요동친다. 한 값만 튀면 센서 하나의 문제를 의심하는 게 합리적이다.**

이 원칙을 주입 로직의 근저에 둔다.

- **실제 고장(real fault)** = 인과로 엮인 **여러 센서가 동시·상관되게** 편차. 예: 하류 막힘 → 유량↓·토출압↑·system_resistance↑가 같은 시점에(전류는 약한 보조 신호, §3-1 참조). 다변량 AE는 이 "함께 틀어짐"을 manifold 이탈로 강하게 잡는다.
- **센서 자체 이상(sensor fault)** = **단일 센서만** 편차(드리프트·스턱·스파이크), 나머지는 정상. AE는 단일 피처 오차만 커서 약하게 반응 → 진짜 고장과 구분.

→ 데이터 생성기는 이 둘을 **다른 라벨/다른 주입 방식**으로 생성해야 한다. real fault는 상관 주입, sensor fault는 단일 주입.

### 1-2. 고장은 "정적 이상"이 아니라 "열화 트라젝토리 → 고장 이벤트"

예지보전의 핵심은 고장 그 자체가 아니라 **고장으로 가는 누적 과정을 미리 잡는 것**이다. 그래서 이상은 한 점이 아니라 **2단계 궤적**으로 주입·평가한다.

```
정상  →  [열화 누적 구간(degradation ramp)]  →  고장 이벤트(failure: 트립/완전막힘/정지)
          ↑ 사전 예측 포인트 — 여기서 알람이 떠야 가치 (고장 전)
```

- **열화 누적 구간**: scale·biofilm·마모가 쌓이며 상관된 다중 센서가 **서서히** 틀어지는 ramp. 강사 원칙("여러 값이 함께 요동")이 여기서 **진행형**으로 나타난다. **이 구간이 탐지 목표.**
- **고장 이벤트**: 임계 누적 후의 결과(보호 트립·shutoff·정지). 이미 늦음 — 예측 가치 없음(라벨링·검증의 기준점일 뿐).
- **성공 지표 = lead time**: 단순 point-F1이 아니라 "**고장 시점 대비 얼마나 일찍 알람을 띄웠나**". 포트폴리오에서도 "F1 0.x"보다 "평균 N시간 전 사전 감지"가 예지보전의 진짜 가치.
- 급성 고장(예: 메인 밸브 닫힘에 의한 급격 shutoff·전류 급강하)은 ramp 없이 step으로 오는 **별도 모드**로 구분한다.

## 2. 기록 양식 (각 고장 모드 1행)

| 필드 | 의미 |
|---|---|
| 고장 모드 | 무엇이 고장났나 (예: 점적 노즐 막힘) |
| 영향 센서 | 어느 센서들이 함께 움직이나 (다중 = real fault) |
| 방향 | 각 센서 ↑/↓ |
| 크기(Δ) | 정상 대비 변화량/비율 (벤더 정상범위 기준) |
| 동역학 | 속도(급성/만성), 주기, 사이클, 강도 프로파일 |
| 출처 | 논문·벤더 스펙·벤치마크 (필수, 없으면 "추정"으로 표기) |

원칙: **출처 없는 값은 "추정"으로 명시**한다. 추정과 근거값을 섞지 않는다(정직성).

## 3. 도메인별 고장 모드 목록 (연구 아젠다 — 값은 §2 양식으로 채움)

> 아래는 채울 대상 목록(skeleton)이다. 각 항목의 영향 센서·크기·동역학·출처는 자료조사 단계(웹·논문·벤더)에서 채운다.

### 3-1. hydraulic (막힘·누수 — 프로젝트 핵심) — 자료조사 완료(2026-06-02)

**중요: "막힘"은 한 종류가 아니다.** 어디가 막히느냐에 따라 다중 센서 시그니처가 다르다. 특히 **하류(점적/노즐) 막힘은 전류가 오히려 ↓**(펌프 곡선상 shutoff 쪽으로 이동, 유량↓·양정↑이라 brake power↓), 전류↑는 **임펠러 막힘**(효율 손실)일 때다 [S1][S6]. 이 구분이 현실적 주입의 핵심.

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

→ **공통점(강사 원칙)**: 어느 막힘이든 **유량↓ + 그에 상관된 압력·저항·진동 변화가 동시에** 나타난다. 단일 센서(예: 압력 게이지)만 변하면 **센서 이상**을 의심(§3-5).

**트라젝토리 (§1-2)**: 막힘은 정적 이상이 아니라 **열화 ramp → 고장**으로 주입한다.
- 누적 구간(며칠~주, scale·biofilm): `flow_rate_l_min` 서서히↓(설계의 100%→…→75% 접근), `discharge_pressure_kpa` 서서히↑, `system_resistance`↑↑(가장 먼저·강하게), `pressure_flow_ratio`↑, `flow_drop_rate`→1 접근. (임펠러형은 `motor_current_a`/`bearing_vibration_rms_mm_s` 동반↑) — **이 구간이 탐지·lead-time 측정 대상.**
- 고장 이벤트(끝점): 유량 <75%(ISO 막힘 기준) 도달 또는 보호 트립 시점. 라벨의 기준점.
- 별도 급성 모드: 메인 밸브 닫힘 → 분 단위 step으로 유량 급감·전류 급강하(ramp 없음).

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

### 3-4. zone_drip (구역 배지)
- 노즐 막힘 — 해당 구역 수분 반응 지연·구역 간 편차↑
- 관수 불균일 — zone_moisture_variance↑
- 배지 염해 — substrate_ec↑·축적속도↑

### 3-5. 단일 센서 이상 (대조군 — sensor fault)
- 드리프트 (slow drift), 스턱(stuck-at), 스파이크(spike), 노이즈 증가 — 각 1개 센서만.

## 4. 데이터 생성기 연동 (구현 위치)

- 주입 지점: [data_gen_jun.py `simulate_degradation`](../../src/data_gen_jun.py), [data_gen_dabin.py](../../src/data_gen_dabin.py).
- **공통 잠재 고장강도 s(t) (0→1 ramp)**: 고장 1건마다 누적 강도 s(t)가 시작 시점부터 끝(고장)까지 0→1로 서서히 증가(scale/biofilm은 며칠~주, sigmoid/선형). 각 영향 센서의 Δ = s(t) × (해당 센서의 §3 시그니처 크기·방향). → 한 잠재 변수가 여러 센서를 **상관되게** 끌어 강사 원칙을 구현.
- **고장 이벤트**: s(t)가 임계(예: 유량 75%↓ 도달)에 닿는 시점을 failure로 마킹.
- sensor fault(대조군): s(t) 없이 **단일 센서에만** 드리프트/스파이크 주입(상관 없음).
- 라벨: `anomaly_label`은 누적 구간 + 고장 구간 모두 1, 별도로 `degradation_severity`(=s(t))·`failure_time`·`fault_mode`·`sensor_fault_flag`를 함께 저장해 lead-time·real/sensor 분리 평가 가능.

## 5. 검증 (주입 후 무엇을 확인하나)

- **lead-time(핵심)**: 각 고장 이벤트에 대해 AE 알람이 **failure_time보다 얼마나 일찍** 떴나. 평균 lead-time + 사전 감지율(고장 전 1건 이상 알람 비율).
- AE가 **real fault(다중 상관 ramp)**에는 누적 구간에서 점점 강해지며 일찍 반응하는가(recall↑).
- AE가 **sensor fault(단일 센서)**에는 덜 반응하는가(오탐 적음) — 원칙 성립 확인.
- 도메인별 진단 그림에서 ramp 구간이 임계선을 점진적으로 넘는지([06](06_visualization_logging.md)).
- 통과 시 그때의 lead-time·F1이 "실제 고장 사전 감지력"의 정직한 지표 → portfolio reframe(A)에 사용.
- 이게 성립하면 그때의 F1이 "실제 고장 탐지력"의 정직한 지표가 된다 → 포트폴리오 숫자 reframe(A).

## 6. 진행 단계

1. 본 원장 프레임 확정(이 문서).
2. **자료조사로 값 채우기** — 도메인별로 영향 센서·Δ·동역학·출처. 웹/논문/벤더 벤치마크 필수. hydraulic 막힘(핵심)부터.
3. 데이터 생성기에 상관 주입 구현 + sensor fault 대조군.
4. 재학습·평가 + 검증(§5). 통과 시 portfolio 숫자 reframe(A).

## 7. 출처 (Sources)

자료조사로 채운 값의 근거. 출처 없는 값은 본문에서 "추정"으로 표기한다.

- [S1] 원심펌프 막힘·저유량 진단 — [SpringPump Centrifugal Pump Troubleshooting](https://springpump.com/centrifugal-pump-troubleshooting/), [UNITEC: Low Flow/No Discharge Diagnostic Guide](https://www.unitecd.com/centrifugal-pump-low-flow-no-discharge-a-diagnostic-troubleshooting-guide-for-maintenance-engineers/)
- [S2] 펌프 진동 한계 (ISO 10816-3/-7) — [ISO 10816-3 Zones A/B/C/D mm/s (Vibromera)](https://vibromera.eu/glossary/iso-10816-3/), [ISO 10816-3 Severity Table (DSP Analytic)](https://dspanalytic.com/en/vibrations/understanding-the-iso-10816-3-vibration-severity-table/), [Europump Pump Vibration Guidelines](https://www.europump.net/files/Publications/Guides/Guidelines%200n%20Pump%20Vibration%20First%20edition%20Final%20July%202013.pdf)
- [S3] 점적 관수 정상 압력·유량·경보 밴드 — [Implementation of a WSN for drip irrigation management (Scientific Reports / PMC12019383)](https://pmc.ncbi.nlm.nih.gov/articles/PMC12019383/)
- [S4] 점적 막힘 ISO 정의(유량 <75% 설계) — [Emitter hydraulic performance & clogging (PMC10973410)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10973410/)
- [S5] 임펠러 막힘 진동·전류 진단 — [Clogged impeller diagnosis using vibration and motor current analysis (ResearchGate 330663300)](https://www.researchgate.net/publication/330663300_Clogged_impeller_diagnosis_in_the_centrifugal_pump_using_the_vibration_and_motor_current_analysis), [Inlet pipe blockage level identification by deep learning (ScienceDirect S0263224121010654)](https://www.sciencedirect.com/science/article/abs/pii/S0263224121010654)
- [S6] 펌프 곡선·throttle 시 전력/전류 거동 — [Centrifugal Pump Performance Curve (BBP Pump)](https://bbppump.com/centrifugal-pump-performance-curve-explained/), [Pump current under low-head (StreamPumps)](https://www.streampumps.com/pump-knowledge/pump-low-head-knowledge.html)

> 다음 회차: §3-1b(누수·밸브·필터·캐비테이션) → §3-2 motor(베어링 ISO 10816 + MCSA) → §3-3 nutrient → §3-4 zone_drip → §3-5 단일센서 대조군 순으로 자료조사 확장.
