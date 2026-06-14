# 14. RCA(근본 원인 분석)와 고장 격리 — 무엇이고, 왜 손보는가

> 이 문서는 두 가지를 풀어 설명한다. (1) RCA란 무엇이며 이 프로젝트에서 어떤 일을 하는가,
> (2) 지금 RCA를 손보려는 궁극 목적과 그 계획. 관련: 점수 산출은 [13. 복원점수와 FP 진단](13_reconstruction_score_and_fp_diagnosis.md),
> 임계 방법론은 [03. 임계 방법론](03_threshold_methodology.md), 이상 시그니처(글리치 vs 진짜)는
> [10. 이상 시그니처 원장](10_anomaly_signature_ledger.md).

---

## 1. RCA란 무엇인가

**RCA(Root Cause Analysis, 근본 원인 분석)** 는 알람이 울렸을 때 "왜 울렸나, 무엇이 원인인가"까지
짚어 주는 기능이다.

비유하면 병원이 "열이 납니다(=알람)"에서 멈추지 않고 "폐렴이고 오른쪽 폐가 원인입니다(=RCA)"까지
진단하는 것과 같다. 그래야 의사(정비원)가 어디를 치료(점검)할지 안다.

이 시스템의 가치 주장은 baseline(단순 z-score 임계)과의 대비에서 나온다.

| | 알람이 답하는 것 | RCA가 답하는 것 |
|---|---|---|
| baseline(z>3) | "어딘가 이상하다" | (없음) |
| **AE + RCA** | "이상하다" | **"어느 도메인의 어느 신호가, 왜"** |

즉 RCA는 이 프로젝트의 핵심 차별점이다. "오탐(FAR)을 낮추면서 + 원인 도메인을 짚는다"가
포트폴리오 발화의 골격이다.

---

## 2. 이 프로젝트의 RCA는 2층 구조

### 2-1. 도메인 층 — "어느 도메인이 이상한가"

4개 도메인(motor / hydraulic / nutrient / zone_drip)이 각자 독립 인코더로 자기 신호를 복원하고,
도메인별 이상점수를 낸다. overall 알람은 도메인 점수의 voting(최댓값)으로 정한다. "어느 도메인이
가장 세게 반응했나"가 1차 원인 도메인이다.

이 층은 이미 검증되어 정확하다. held-out v2에서 유형별 귀인이 4/4 적중한다(clog→hydraulic,
bearing→motor, suction→hydraulic, nutrient→nutrient). 근거: [verify_attribution.py](../../fault_injection/verify_attribution.py),
[attribution_matrix.py](../../fault_injection/attribution_matrix.py).

### 2-2. 피처 층 — "그 도메인 안에서 어느 신호가 원인인가"

도메인이 정해지면, 그 안에서 어떤 센서/피처가 이상을 끌어올렸는지를 per-feature 복원오차로
순위 매겨 Top-3로 보여 준다. 구현은 [`calculate_rca`](../../src/inference_core.py#L82).

```
contribution(피처 f) = 복원오차(f) / Σ 복원오차  × 100 (%)
```

즉 "이 알람의 총 오차에서 그 피처가 차지한 비율"을 raw(절대오차) 기준으로 매긴다. **바로 이 층에
결함이 있다(4절).**

---

## 3. RCA와 헷갈리기 쉬운 두 메커니즘 — 역할이 다르다

RCA를 손볼 때 "이러면 SHAP이나 다른 게 무의미해지지 않나"라는 의문이 자연스럽다. 셋은 서로 다른
질문에 답하므로 중복이 아니다.

| 메커니즘 | 답하는 질문 | 시점 | 단위 |
|---|---|---|---|
| **SHAP** (`*_shap.json`) | 이 도메인에서 어느 피처가 (학습상) **중요**한가 | 학습 | 전역(global) |
| **RCA** (`calculate_rca`) | 이 알람에서 어느 피처가 (지금) **원인**인가 (Top-3) | 서빙 | 사건별 |
| **n_active**(제안) | 이 알람이 **몇 개 신호**에 걸쳐 있나(글리치/진짜) | 서빙 | 사건별 |

- SHAP = "어느 피처가 중요한가"(피처 선택의 근거, 리포트 주석). 전역·학습 단계라 RCA와 축이 다르다.
- RCA = "어느 피처가 원인인가"(Top-3 순위).
- n_active = "몇 개 신호인가"(광범위도 → 한 개면 글리치 의심, 여럿이면 진짜).

→ n_active는 SHAP을 대체하지 않는다(전역 중요도 vs 사건별 광범위도). RCA와는 데이터(per-feature
오차)를 공유하지만 "어느 것"과 "몇 개"로 질문이 다르며, n_active는 RCA가 이미 쓰는 데이터에서
파생되는 요약일 뿐 별도 메커니즘이 아니다.

---

## 4. 지금 발견한 문제 — 피처 층 RCA의 결함 2개

### 4-1. raw 편향 — 원래 시끄러운 피처가 원인으로 늘 찍힌다

RCA는 raw 절대오차 비율로 순위를 매긴다([`calculate_rca`](../../src/inference_core.py#L109)).
그런데 피처마다 "평소 복원오차"의 크기가 다르다. 예: nutrient에서 ph_trend_30의 정상 상한(μ+2σ)은
0.020으로 넓고, pid_error_ec는 0.005로 좁다(`per_feature_thresholds`). 즉 ph_trend는 원래 잘 튀는
신호라, 진짜 원인이 아니어도 raw % 상위를 차지하기 쉽다.

이는 다변량 공정 모니터링(MSPC)에서 잘 알려진 문제다. Alcala & Qin(Automatica 2009)은 전통적
기여도 plot이 "고장이 정상 변수의 기여도로 번지고(smear), 고장이 없어도 변수마다 기여도가
불균등해" 오진을 부른다고 지적한다. 우리 RCA의 raw 편향이 정확히 이 현상이다.

### 4-2. 점수와 RCA의 모순 — 점수는 잘랐는데 RCA는 원인이라 한다

Phase P에서 nutrient 점수는 trimmed-mean으로 상위 1개 오차(보통 ph_trend의 OOD 스파이크)를
**잘라내고** 계산한다([`reconstruction_score`](../../src/inference_core.py#L59),
[inference_api.py:476](../../src/inference_api.py#L476)). 그런데 RCA는 trim하지 않은 raw 오차를
쓴다([inference_api.py:517](../../src/inference_api.py#L517) `calculate_rca(sq_err, ...)`).

결과적으로 nutrient 알람이 (다른 신호 때문에) 울렸을 때, 점수는 "ph_trend는 잘라서 무시했다"는데
RCA는 "ph_trend가 원인 60%"라고 보고하는 모순이 생긴다. 정비원이 RCA를 믿고 ph_trend 센서로
달려가지만 실제 원인은 다른 신호인 상황이 가능하다.

---

## 5. 궁극 목적 — "왜"를 신뢰할 수 있게 만든다

이 작업의 궁극 목적은 새 기능을 더하는 것이 아니라 **RCA가 가리키는 원인이 실제 원인과 일치하고,
점수(알람 판단)와 RCA(설명)가 같은 말을 하게 만드는 것**이다. 정비원이 RCA를 믿고 행동할 수 있어야
"원인까지 짚는다"는 가치 주장이 성립한다.

부수적으로, 같은 per-feature 정규화에서 "한 신호만 튀었나(글리치 의심) vs 여럿이 함께 움직였나
(진짜)"를 알려주는 글리치 플래그(n_active)가 공짜로 파생된다. 이는 강사 원칙("한 센서만 튀면
글리치, 여럿 함께면 진짜")의 운영 버전이다. 단 이는 부차적이며, 측정으로 가치가 확인될 때만 만든다.

설계 원칙(앞선 논의에서 합의): **알람은 억제하지 않는다.** 단일 신호 이상도 알람은 울리되, 글리치
의심은 "억제"가 아니라 "플래그(확인하라)"로 표시한다. 양액(pH/EC) 문제는 펌프와 독립적으로 식물을
빠르게(비가역) 죽일 수 있어, 단일 도메인 이상도 알람 가치가 충분하다.

---

## 6. 스코프 분리 — 과투자를 막는다

"지금 RCA가 과한 건 아닌가"라는 우려는 타당하다. 그래서 작업을 3단계로 분리하고, 명백한 것만
확정으로, 나머지는 측정으로 게이트를 건다.

| 스코프 | 내용 | 정당성 | 결정 |
|---|---|---|---|
| **최소** | RCA를 점수와 동일하게 trim(잘린 피처는 RCA에서도 제외) | 명백한 모순(4-2) 제거. 싸고 확실 | **항상 한다** |
| **중간** | RCA 순위를 정규화 기여도로(자기 정상 대비) | raw 편향(4-1) 제거 | 측정 통과 시 |
| **풀** | n_active를 서빙 응답에 노출(글리치 플래그) | 부차층 폴리시·포폴 talking point | 측정 강하게 통과 시만 |

---

## 7. 계획 — 측정 우선·게이트형

```
P0 측정   sensor_fault_eval로 raw 집중도 vs 정규화 n_active의 분리도 측정 (코드변경 0, 위험 0)
          └─ 게이트: 정규화가 라벨된 글리치(단일센서) / 진짜(다중센서)를 가르는가?
P1 최소   RCA를 점수와 동일 trim → 모순 제거 (게이트 무관, 항상)
P2 중간   게이트 통과 시: RCA 정규화 기여도 (편향 제거)
P3 풀     게이트 강하게 통과 시만: n_active 서빙 노출
P4 기록   본 문서 갱신 + MODEL_CHANGELOG(Phase Q) + SESSION_LOG, src/ ↔ services/inference/ 동기화
```

각 단계가 앞 단계 측정에 종속되므로 과투자가 자동으로 방지된다.

---

## 8. 예측 효과와 위험

- **분리도가 좋으면**: RCA가 진짜 원인을 가리킨다(ph_trend 고정 탈출). 점수와 RCA가 일관된다.
  글리치/진짜 triage가 가능해진다. 포트폴리오: "MSPC 기여도 분석(RBC 계열)을 적용해 고장을 격리".
- **분리도가 약하면**: "우리 피처로는 글리치/진짜 구분이 어렵다"는 정직한 null 결과(crest_factor
  사례와 동일한 절제). 풀 스코프는 만들지 않고 최소(모순 제거)만 적용한다.
- **위험**: 거의 없다. **재학습 불필요**(기존 `per_feature_thresholds` 재사용), P0는 코드 변경이 없다.

---

## 9. 문헌 근거

- Alcala & Qin, "Reconstruction-based contribution for process monitoring," *Automatica* 45(7),
  2009 — RBC(재구성 기반 기여도). raw 기여도의 번짐(smearing)·불균등 편향 문제와 그 해법.
- Miller et al. 1998 / Westerhuis et al. 2000 — 기여도 plot(contribution plots)의 고전.
- "Autoencoder based Anomaly Detection and Explained Fault Localization," PHM Society 2022
  (arXiv:2210.08011) — AE per-feature 복원오차로 영향 신호를 localize, normalized 기여.

---

## 부록. 코드 위치

- 피처 층 RCA: [`calculate_rca`](../../src/inference_core.py#L82) — 현재 raw 기여 %.
- 점수(trim): [`reconstruction_score`](../../src/inference_core.py#L59), 호출 [inference_api.py:476](../../src/inference_api.py#L476).
- RCA 호출(현재 raw·untrimmed): [inference_api.py:517](../../src/inference_api.py#L517).
- 도메인 귀인 검증: [verify_attribution.py](../../fault_injection/verify_attribution.py), [attribution_matrix.py](../../fault_injection/attribution_matrix.py).
- per-feature 정상 밴드: 각 도메인 config의 `per_feature_thresholds`.
- 글리치/진짜 판별자(집중도·n_active) 기존 구현: [sensor_fault_eval.py](../../fault_injection/sensor_fault_eval.py), [10. 이상 시그니처 원장](10_anomaly_signature_ledger.md).