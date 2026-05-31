# 07 — 도메인 운영 지표 검증 (막힘률 · Cpk · OEE)

현재 진행 중인 모델 성능 작업(게이트 0 인프라 → NUTRIENT threshold → 단일센서 baseline)이 끝난 뒤 이어서 수행할 검증 작업입니다. 강사가 기획·경력기술 단계에서 제시한 제조 표준 지표([../DEVELOPMENT_ROADMAP.md](../DEVELOPMENT_ROADMAP.md) §3·§4)를 실제로 측정해 포트폴리오 강점으로 격상하는 단계입니다.

핵심은 효과 크기(막힘률 10→2% 등)의 절대값이 아니라, **도메인이 인정하는 평가 지표를 정의하고 그에 맞춘 테스트를 수행했다는 사실**입니다. 따라서 이 문서는 각 지표의 정의·측정 절차·효과 책정 기준에 집중합니다.

---

## 1. 선행 조건 (이것이 끝나야 착수)

| 선행 | 근거 |
|---|---|
| 단일센서 baseline 구축 완료 | [02 §4](02_evaluation_design.md), [04 게이트 3](04_modeling_kickoff_checklist.md). 막힘률은 baseline 대비 비교가 핵심이라 baseline 없이는 측정 불가 |
| AE 평가 파이프라인(experiments.csv) 동작 | [01 §3](01_experiment_protocol.md). 막힘률·Cpk를 실험 단위로 기록 |
| 막힘 사건의 조작적 정의 확정 | 아래 2절. 모든 지표가 이 정의를 공유 |

선행이 갖춰지기 전에는 이 지표들이 "측정"이 아니라 "추정"에 머뭅니다.

---

## 2. 막힘률 (1순위 — 임팩트 최대, baseline 재사용)

### 정의
```
막힘률(%) = 막힘 사건 수 / 전체 운전 사이클(또는 시간) × 100
```

### 막힘 사건의 조작적 정의 (먼저 고정)
- 현재 합성 데이터 기준의 막힘 정의(예: 4센서 composite z-score ≥ 2.0)를 그대로 사용할지 확정합니다. 코드 근거(`data_gen` 계열)를 명시합니다.
- **사건 카운팅 단위**: 연속된 이상 프레임을 하나의 막힘 "사건"으로 병합합니다(chattering 방지). episode 시작·종료 규칙(예: ON 임계 진입 → OFF 임계 이탈)을 명시해야 사건 수가 일관됩니다.

### 측정 절차
1. 동일한 EVAL 시나리오(시간 순 split, [02 §1](02_evaluation_design.md))에 두 정책을 각각 적용합니다.
   - 정책 A: 단일 센서 임계값 baseline
   - 정책 B: AE 시스템(현재 모델)
2. 각 정책의 막힘 사건 수를 episode 단위로 집계해 막힘률을 산출합니다.
3. 효과 = 상대 감소율. 예: 10% → 2%는 80% 감소.

### 산출물
- baseline vs AE 막힘률 비교표 → experiments.csv 기록
- 동기화: [../DEVELOPMENT_ROADMAP.md](../DEVELOPMENT_ROADMAP.md) §4, P-002 supersede 행

### 테스트 점검
- split이 시간 순인가(학습=과거, 평가=미래)
- 두 정책에 동일 시나리오·동일 episode 정의를 적용했는가
- 막힘 사건 카운팅이 chattering으로 부풀려지지 않았는가

---

## 3. Cpk 공정능력지수 (2순위 — 막힘 정의·규격 확정 후)

막힘률에서 정한 품질특성·규격을 재사용하므로 막힘률 다음에 둡니다.

### 정의
```
Cpk = min[ (USL − μ) / 3σ , (μ − LSL) / 3σ ]
```
Cp(산포만 반영)와 달리 공정 평균의 치우침까지 반영합니다.

### 측정 절차
1. **품질특성(CTQ) 선정**: 막힘은 유량 저하이므로 정상 운전 시 토출 유량(L/min) 또는 유량편차를 CTQ로 둡니다. "무엇을 재는가"를 먼저 고정합니다.
2. **규격 한계(LSL/USL) 명시**: 장비 사양 기반 허용 범위를 명시합니다. 합성 데이터인 경우 시뮬레이션 사양 가정을 출처와 함께 적습니다(현재 출처 표기 0 → 반드시 보강).
3. **σ 추정**: 관리상태(in-control) 데이터에서 단기 within-subgroup σ = R̄/d₂를 사용합니다(Cpk 관례). overall σ와 구분합니다.
4. **정규성 확인**: Shapiro 등으로 확인하고, 비정규면 변환 또는 비정규 Cpk를 사용합니다.
5. **산출 코드 추가**: `evaluate_test_metrics.py`에 USL·LSL·μ·σ·n 입력 → Cpk 함수. 샘플 크기를 명시합니다.

### 기준
- 1.67 = 5σ 수준(약 0.6 ppm). 1.33 = 4σ(산업 최소 기준). 1.67은 우수 공정.
- 효과 책정: 개입 전(무개입 운전) Cpk vs 예지보전 가동 후 Cpk 비교. 사전 감지로 유량 산포가 줄면 Cpk가 상승합니다.

### 반드시 분리할 것
F1(이상탐지 분류 성능)과 Cpk(공정 산포 지표)는 수학적으로 연결되지 않는 별개 지표입니다. "F1 0.95 → Cpk 1.67 달성"처럼 한 결과로 묶으면 면접에서 측정 근거 질문에 막힙니다. Cpk는 막힘률과 한 묶음(CTQ·규격 공유)으로 설계합니다([../DEVELOPMENT_ROADMAP.md](../DEVELOPMENT_ROADMAP.md) §3-3).

---

## 4. OEE 설비종합효율 (3순위)

### 정의
```
OEE = 가용성(Availability) × 성능(Performance) × 품질(Quality)
```
| 구성요소 | 정의 | 예지보전 효과 |
|---|---|---|
| 가용성 | 실가동시간 / 계획가동시간 | 계획 외 다운타임 감소 → 상승 |
| 성능 | 실제 생산속도 / 이론 생산속도 | 막힘으로 인한 속도 저하 감소 |
| 품질 | 양품 / 총생산 | 막힘 사전 차단으로 불량 감소 |

### 측정 절차
1. 각 구성요소를 합성 시뮬레이션 로그에서 산출합니다.
2. 78% → 85%의 출처를 명시합니다(산업 평균 가정인지, 시나리오 산출인지 — 현재 출처 표기 0).
3. 개입 전후 OEE를 비교합니다.

---

## 5. RMSE · Confusion Matrix (강사 양식 Evaluation Measure 대응)

강사 양식의 "Evaluation Measure: RMSE, Confusion Matrix"는 위 운영 지표와 별개의 모델 성능 지표군입니다.

- **RMSE**: AE 복원오차, 또는 (MDOF 물리모델 도입 시) 물리 예측 대 실제 유량의 회귀 정확도.
- **Confusion Matrix**: 이상탐지 분류 결과 → Precision·Recall·F1(이미 측정됨, [02 §3](02_evaluation_design.md)).

운영 지표(막힘률·Cpk·OEE)와 모델 지표(RMSE·F1)를 같은 표에 섞지 않습니다.

---

## 6. 작업 순서 요약

```
1. 막힘률 baseline 비교 (baseline 완료 직후, AE 결과 재사용)
2. Cpk          (막힘 정의·규격을 막힘률에서 재사용)
3. OEE          (구성요소 정의 + 시뮬레이션 산출)
```
[../DEVELOPMENT_ROADMAP.md](../DEVELOPMENT_ROADMAP.md) §5 권장 순서와 동일하며, 코드 재사용이 최대가 되는 순서입니다.

---

## 7. 완료 시 동기화 (격상 반영)

각 지표 측정이 검증값으로 확정되면 아래를 함께 갱신합니다([../DEVELOPMENT_ROADMAP.md](../DEVELOPMENT_ROADMAP.md) §6).

- [ ] `../DEVELOPMENT_ROADMAP.md` §0 표 상태 갱신 (❌ → ✅)
- [ ] `../portfolio_interview_facts.md` — 검증 수치 등재
- [ ] `~/GitStudy/make_portfolio/포트폴리오_사실_검증_원칙.md` — CEDR 카탈로그 신규 행 추가(append-only)
- [ ] `~/GitStudy/make_portfolio/프로젝트이력/pump_clogging.md`(경력기술서) 및 `projects/clogging_detection/본인_기여_상세.md` 발화 격상
- [ ] `.claude/MODEL_CHANGELOG.md` — 측정 Phase 기록

---

## 8. 착수 체크리스트

- [ ] 막힘 사건 조작적 정의 + episode 시작·종료 규칙 확정
- [ ] baseline vs AE 막힘률 비교표 산출 → experiments.csv 기록
- [ ] CTQ 선정 + LSL/USL 명시(출처 포함) + within σ 추정 + 정규성 확인 + Cpk 산출 함수 추가
- [ ] OEE 3개 구성요소 정의·산출 + 78/85 출처 표기
- [ ] F1과 Cpk를 분리 서술했는지 확인
- [ ] §7 동기화 5종 갱신
