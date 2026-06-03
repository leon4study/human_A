# 2. 이상 탐지에 AutoEncoder를 쓴다

Date: 2026-04-23

## Status

Accepted

## Context

양액펌프 막힘·과부하를 사전에 감지해야 한다. 후보는 세 가지였다.

- 단일 센서 임계값(rule): 구현은 쉽지만, 정상 범위가 외부 환경·작물 상태·기동 여부에 따라
  계속 변해 고정 임계값으로는 오탐/미탐이 많다.
- 지도학습 분류기: 고장 라벨이 충분해야 하는데, 실제 고장 데이터가 거의 없다(정상 운전이 대부분).
- 비지도 재구성 기반(AutoEncoder): 정상 데이터만으로 "정상의 형상"을 학습하고, 재구성 오차가
  큰 입력을 이상으로 본다.

## Decision

정상 데이터로 학습하는 AutoEncoder를 주 모델로 채택한다. 재구성 오차(MSE)를 이상 점수로 쓴다.

## Consequences

- 고장 라벨 없이 학습할 수 있어, 라벨 부족 문제를 우회한다.
- 정상 운전의 다변량 상관(여러 센서가 함께 움직이는 패턴)을 학습하므로, 단일 임계값이 놓치는
  "값들이 함께 요동치는 진짜 고장"을 포착한다(강사 원칙: 다중 센서 동반 변동 = 실제 고장,
  단일 값만 튐 = 센서 문제).
- 모델 비교(AE vs IsolationForest vs One-Class SVM)는
  [notebooks/03_evaluation/model_comparison_jun.ipynb](../../notebooks/03_evaluation/model_comparison_jun.ipynb)에 기록.
- 임계값(정상/이상 경계) 설정이 별도 과제가 된다 → ADR 0004.
- 고장 데이터가 없으므로 검증은 현실적 고장 주입 + lead-time으로 한다
  ([modeling/10_anomaly_signature_ledger.md](../modeling/10_anomaly_signature_ledger.md)).
