# 4. 6시그마 3단계 알람 + skew-adaptive 임계값

Date: 2026-05-31

## Status

Accepted

## Context

AutoEncoder의 재구성 오차(MSE)를 정상/이상으로 가르는 경계가 필요하다. 두 가지 어려움이 있다.

1. 단계의 강약: 막힘은 갑자기 터지기보다 점진적으로 진행되므로, 단일 컷오프보다 경고 단계가
   있어야 운영자가 사전 대응할 수 있다.
2. 분포의 비대칭: AE 오차 분포는 한쪽으로 길게 치우친(skewed) 경우가 많다. 이때 평균±Nσ는
   정상을 이상으로 잘못 가른다. σ는 정규분포를 가정하기 때문이다.

## Decision

- 3단계 알람을 둔다: 정상 / 주의(Caution) / 경고(Warning) / 위험(Error)을 2σ·3σ·6σ 계열의
  다단계 경계로 구성한다.
- 임계값 산출은 skew-adaptive로 한다: 왜도(skew)가 임계(약 8)를 넘으면 백분위수(percentile)
  기반, 그 이하이면 시그마 기반을 쓴다(`THRESHOLD_METHOD=auto`).
- 기동 직후 과도 구간은 정상 스파이크이므로 임계값 산출과 알람 판정에서 게이트한다
  (학습 시 기동 행 마스킹, 추론·평가 시 `is_startup_phase` 게이트).

## Consequences

- 비대칭 분포에서도 경계가 안정적으로 잡힌다.
- 기동 게이트는 운영(추론)뿐 아니라 평가 경로에도 동일하게 적용해야 한다. 평가에만 빠지면
  기동 스파이크가 매 기동마다 오탐을 내 지표를 왜곡한다(2026-06-02 발견·수정: 기동 윈도우
  FAR 100%→0%, lead-time 36.1h→29.9h로 정직화).
- 임계값 방법론 상세는 [modeling/03_threshold_methodology.md](../modeling/03_threshold_methodology.md),
  실험 변천은 [.claude/MODEL_CHANGELOG.md](../../.claude/MODEL_CHANGELOG.md) 참조.
