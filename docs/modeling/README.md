# 모델링 기획 (방법론 / 프로세스)

이 폴더는 **앞으로 모델링과 성능 검증을 어떻게 체계적으로 수행할 것인가**를 정리한 방법론·프로세스 문서입니다. 이미 구축된 파이프라인의 구조(as-built)는 [../MODELING.md](../MODELING.md)에 있으며, 이 폴더는 그 위에서 **실험·평가·임계치 산정을 수행하는 규칙**을 다룹니다.

---

## 0. 이 폴더가 필요한 이유

지금까지 모델 성능 개선은 "학습 후 결과를 눈으로 확인하고 다시 수정"하는 방식의 반복 실험으로 진행됐습니다. 이 방식의 한계가 실제로 두 차례 문제가 됐습니다 ([../../.claude/MODEL_CHANGELOG.md](../../.claude/MODEL_CHANGELOG.md)).

1. **A-3 사례** — `random_state=42`를 설정했음에도 재학습마다 결과(비결정성)가 달라, 좋았던 모델(F1 0.503)을 재학습이 덮어써 영구 소실했습니다. 무엇이 개선이고 무엇이 우연인지 구분할 수 없었습니다.
2. **NUTRIENT dynamic threshold** — 도메인별 σ 임계치가 안정적으로 산정되지 않아 오탐(FP)의 94%가 한 도메인에 집중됐습니다. "임계치가 너무 낮다"는 판단이 정량 근거 없이 직관에만 머물렀습니다.

결론은 **반복 실험을 줄이는 것이 아니라, 모든 실험을 복원·비교 가능하게 만드는 것**입니다. 숙련된 데이터 과학자와의 차이는 실험 횟수가 아니라, 모든 실험이 기록되고 재현되는지에 있습니다.

---

## 1. 핵심 원칙 네 가지

1. **재현성 우선** — 시드와 결정성을 고정하기 전에는 어떤 실험 결과도 신뢰하지 않습니다. ([01](01_experiment_protocol.md))
2. **덮어쓰지 않음** — 모델 아티팩트와 메트릭은 타임스탬프로 누적 보존합니다. 비교는 자동화합니다. ([01](01_experiment_protocol.md))
3. **평가를 모델보다 먼저 설계** — split·메트릭·baseline을 코드 작성 전에 확정합니다. ([02](02_evaluation_design.md))
4. **임계치는 방법론으로 산정** — 직관적 σ 조정이 아니라, 운영 제약을 만족하는 지점을 데이터로 선택합니다. ([03](03_threshold_methodology.md))

---

## 2. 문서 색인

| 문서 | 다루는 내용 | 핵심 질문 |
|---|---|---|
| [01_experiment_protocol.md](01_experiment_protocol.md) | 재현성·실험 추적·실험 단위 | 이 실험을 수개월 뒤 그대로 재현할 수 있는가 |
| [02_evaluation_design.md](02_evaluation_design.md) | 데이터 split·정상 순도·메트릭·baseline | 성능 향상이 실제 일반화인가, 평가 누수인가 |
| [03_threshold_methodology.md](03_threshold_methodology.md) | dynamic threshold 산정·도메인별 보정 | 이 임계치는 왜 이 값이며 운영 제약을 만족하는가 |
| [04_modeling_kickoff_checklist.md](04_modeling_kickoff_checklist.md) | 착수 전 게이트 체크리스트 | 기획이 끝났는가, 학습을 시작해도 되는가 |
| [05_reproducibility_implementation.md](05_reproducibility_implementation.md) | repro.py 구현·신규 개념 설명 | 추가된 코드가 무엇을 하고 어떻게 검증하는가 |
| [06_visualization_logging.md](06_visualization_logging.md) | 진단 시각화 자동 저장·실험별 이미지 관리 | 의도대로 동작함을 그래프로 보이고 수많은 이미지를 어떻게 정리하는가 |
| [07_training_runbook.md](07_training_runbook.md) | train.py 실행 전 체크리스트·실행 기록 양식 | 학습 돌리기 전에 무엇을 맞추고 무엇을 기록하는가 |
| [08_domain_metrics_validation.md](08_domain_metrics_validation.md) | 도메인 운영 지표(막힘률·Cpk·OEE) 정의·측정 절차·효과 책정 | baseline 완료 후 강사 제시 제조 지표를 어떻게 측정·격상하는가 |

---

## 3. 관련 문서 (역할 분리)

| 문서 | 역할 |
|---|---|
| [../MODELING.md](../MODELING.md) | 현재 구축된 파이프라인 구조 (as-built reference) |
| [.claude/MODEL_CHANGELOG.md](../../.claude/MODEL_CHANGELOG.md) | 실험 변천사 — 현재 상태에 이른 경위 |
| [../../SESSION_LOG.md](../../SESSION_LOG.md) | 세션별 진행·인수인계 (현재 상태) |
| [../DEVELOPMENT_ROADMAP.md](../DEVELOPMENT_ROADMAP.md) | 포트폴리오 강점 강화 로드맵 (MDOF·NN·Cpk·OEE) |
| [../PROJECT_BRIEF.md](../PROJECT_BRIEF.md) | 실패 학습·진행 중 문제 |

이 폴더(방법론)와 MODELING.md(구조)는 의도적으로 분리합니다. 구조 문서에 방법론을 섞으면 "현재 코드 상태"와 "앞으로의 작업 방향"이 뒤섞여 양쪽 모두 신뢰를 잃기 때문입니다.
