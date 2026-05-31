# 04 — 모델링 착수 전 게이트 체크리스트

train.py를 실행하기 전에 통과해야 하는 게이트입니다. "코드부터 작성하고 본다"를 방지하는 문서이며, 한 항목이라도 미충족이면 그 항목을 먼저 해결한 뒤 학습에 들어갑니다.

---

## 게이트 0 — 인프라 (최초 1회 구축, 이후 상시 유지)

- 시드·결정성 고정이 학습 스크립트에 적용됐다 ([01 §1](01_experiment_protocol.md), `repro.set_global_determinism`)
- 동일 코드 2회 학습 시 config가 동일하다(재현성 확인)
- 모델 저장이 타임스탬프 `runs/<run_id>/` 보존 구조다 (덮어쓰기 방지, [01 §2](01_experiment_protocol.md), `repro.snapshot_run`)
- `experiments.csv` 자동 append가 평가 스크립트에 있다 ([01 §3](01_experiment_protocol.md))
- 진단 시각화 자동 저장이 run 폴더에 연결돼 있다 ([05](05_reproducibility_implementation.md), [06](06_visualization_logging.md))

게이트 0이 갖춰지지 않으면 이후 모든 실험이 우연과 구분되지 않습니다. 최우선입니다.

---

## 게이트 1 — 문제·평가 정의 (실험 가설마다)

- 이 실험의 가설 한 줄이 작성됐다
- 운영 메트릭 목표가 정량이다 (예: FAR ≤ 5% 유지하며 recall 최대화, [02 §3](02_evaluation_design.md))
- split이 시간 순이다 (학습=과거, 평가=미래, [02 §1](02_evaluation_design.md))
- 임계치를 데이터로 선택한다면 validation/test가 분리됐다

---

## 게이트 2 — 데이터 건강성

- TRAIN 구간 정상 순도를 확인했다 (이상 잔존 꼬리 점검, [02 §2](02_evaluation_design.md))
- 파생 피처에 분모 발산·극단값이 없다 (`flow_drop_rate` 게이트 사례, [../MODELING.md](../MODELING.md))
- 희소 binary를 AE 입력 VIP에 넣지 않았다 (`is_startup_phase` 50배 폭발 교훈)
- 집계 윈도우가 이상 신호를 희석하지 않는다 ([02 §6](02_evaluation_design.md))

---

## 게이트 3 — baseline

- 단순 baseline(단일 센서 z>3 등)이 있다 ([02 §4](02_evaluation_design.md))
- AE를 baseline과 비교하는 평가가 준비됐다

---

## 게이트 4 — 실험 위생

- 이번 실험은 한 가지만 변경한다 ([01 §4](01_experiment_protocol.md))
- 평가 후 진단 시각화를 run 폴더에서 확인한다 ([06](06_visualization_logging.md))
- 평가 후 MODEL_CHANGELOG 5블록(가설 → 시도 → 관측 → 진단 → 수정) 기록을 예정한다

---

## 통과 후 — 실험 1회 절차

[01 §5](01_experiment_protocol.md)의 절차를 따릅니다.

```
가설 → 시드확인 → 한가지변경 → 학습(runs/ 보존) →
평가(experiments.csv) → 시각화 확인(run 폴더) → MODEL_CHANGELOG 기록 → 채택 또는 롤백
```

---

## 현재 프로젝트 적용 우선순위 (2026-05-31 기준)

| 순위 | 작업 | 근거 게이트 |
|---|---|---|
| 1 | 시드 전역 고정 + op_determinism (`repro.set_global_determinism`) | 게이트 0 (비결정성이 모든 실험을 무효화) |
| 2 | 타임스탬프 모델 폴더 + experiments.csv (`repro.snapshot_run`) | 게이트 0 (A-3 재발 방지) |
| 3 | 진단 시각화 자동 저장(run 폴더 연동) | 게이트 0·4 ([06](06_visualization_logging.md)) |
| 4 | NUTRIENT threshold를 percentile/PR로 전환 실험 | [03](03_threshold_methodology.md) |
| 5 | 단일센서 baseline 구축 | 게이트 3 + [../DEVELOPMENT_ROADMAP.md](../DEVELOPMENT_ROADMAP.md) §4 |
| 6 | 막힘률 baseline 대비 측정 (baseline 재사용) | [08 §2](08_domain_metrics_validation.md) + [../DEVELOPMENT_ROADMAP.md](../DEVELOPMENT_ROADMAP.md) §4 |
| 7 | Cpk 산출 (막힘 정의·규격 재사용) | [08 §3](08_domain_metrics_validation.md) |
| 8 | OEE 산출 | [08 §4](08_domain_metrics_validation.md) |

1·2·3번(인프라)이 없으면 4·5번 결과를 신뢰할 수 없습니다. 순서대로 진행합니다. 6·7·8번(도메인 운영 지표)은 5번 baseline이 선행 조건이며, 강사 제시 지표를 검증값으로 격상하는 단계입니다 ([08_domain_metrics_validation.md](08_domain_metrics_validation.md)).
