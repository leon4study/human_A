# 01 — 실험 프로토콜 (재현성 · 추적 · 실험 단위)

모든 모델 실험이 지켜야 하는 최소 규칙입니다. 이 규칙(프로토콜)을 갖추기 전에는 어떤 성능 비교도 믿지 않습니다. 배경: A-3 사례(같은 코드인데 결과가 매번 달라지는 비결정성 탓에, 좋았던 모델을 영영 잃은 일)는 바로 이 규칙이 없어서 벌어졌습니다 ([../../.claude/MODEL_CHANGELOG.md](../../.claude/MODEL_CHANGELOG.md) A-3).

---

## 1. 재현성 고정 (최우선 — 없으면 나머지가 무의미)

`train.py`는 `random_state=42`(난수 시드 고정)를 줬는데도 재학습할 때마다 결과가 달랐습니다. 2026-06-01 재현성 테스트로 진짜 원인을 찾았습니다: **파이썬 해시 무작위화(PYTHONHASHSEED를 고정하지 않음)** 였습니다. 이것이 고정되지 않으면 set·dict(집합·사전)의 내부 순서가 실행할 때마다 달라집니다. 그 결과, 서로 겹치는 변수를 걸러내는 단계(다중공선성 제거)와 여러 타깃에서 공통으로 중요한 피처를 뽑는 단계(robust voting)가 매번 다른 컬럼을 골랐습니다. 결정적으로 이 환경변수는 파이썬이 시작되기 전에 설정돼야 효과가 있습니다. 그래서 프로그램이 도는 도중에 값을 넣어도 소용없고, 안 잡혀 있으면 프로세스를 다시 시작(re-exec)해야 합니다. TensorFlow의 시드(신경망 초기 가중치)도 함께 잡아야 하지만, 핵심 원인은 해시였습니다. 상세는 [.claude/MODEL_CHANGELOG.md](../../.claude/MODEL_CHANGELOG.md) Phase D.

모든 학습 스크립트의 최상단에서 다음을 고정합니다.

```python
import os, random
import numpy as np
import tensorflow as tf

SEED = 42
os.environ["PYTHONHASHSEED"] = str(SEED)
random.seed(SEED)
np.random.seed(SEED)
tf.random.set_seed(SEED)
tf.config.experimental.enable_op_determinism()   # TF 2.8+ : 연산 순서까지 결정적으로
```

이 프로젝트에서는 위 로직을 [../../src/repro.py](../../src/repro.py)의 `set_global_determinism()`으로 모듈화했습니다. 상세 구현은 [05](05_reproducibility_implementation.md)를 참조하십시오.

추가 규칙
- sklearn RandomForest / LightGBM: `random_state`를 반드시 지정합니다. sklearn RandomForest는 `random_state`가 지정되면 `n_jobs`와 무관하게 재현됩니다. 일부 라이브러리는 연산 수준 병렬에서 비결정적일 수 있으므로, 의심되면 해당 연산을 먼저 격리해 확인합니다.
- 검증 방법: 동일 코드·동일 데이터로 2회 학습한 뒤 config의 thresholds·feature 목록이 동일한지 확인합니다. 다르면 재현성이 확보되지 않은 상태입니다.

원칙: 재현성이 확보되기 전의 "성능 개선"은 보고하지 않습니다. 우연(seed luck)과 구분할 수 없기 때문입니다.

---

## 2. 덮어쓰지 않는 저장 (A-3 재발 방지)

`models/`는 `.gitignore` 대상이라 git이 보호하지 않으며, `train.py`는 같은 경로에 덮어씁니다. 그 결과 좋았던 모델이 한 번의 재학습으로 사라질 수 있습니다.

원칙: 모델 아티팩트는 덮어쓰지 않고 타임스탬프 폴더로 누적합니다.

```
models/
  motor_model.keras  motor_config.json  ...   # 라이브 폴더: 서빙(inference_api)이 읽는 곳
  LATEST_RUN.txt                                # 최신 run_id 포인터
  runs/
    2026-05-31_142210__41c58ea__baseline/       # 학습 시점 보존본 (변경 금지)
      motor_model.keras  ...  run_meta.json
    2026-05-31_153044__41c58ea__percentile-thr/
      ...
```

- 서빙 계약을 깨지 않기 위해 라이브 폴더(`models/`)에는 그대로 저장하고, **추가로** `models/runs/<run_id>/`에 보존본을 복사합니다.
- `run_meta.json`에 git commit SHA를 기록해 "이 모델이 어떤 코드에서 나왔는지"를 영구 보존합니다.
- 규모가 커지면 MLflow 또는 Weights & Biases로 승격합니다. 현재 규모에는 타임스탬프 폴더로 충분합니다.

이 프로젝트에서는 `repro.snapshot_run()`이 이 역할을 수행합니다 ([05](05_reproducibility_implementation.md)). 기존 절대 규칙(MODEL_CHANGELOG #6)은 "재학습 전 백업"이지만, 백업보다 "덮어쓰지 않는 저장 구조"가 더 근본적입니다. 백업은 잊으면 끝이지만 구조는 잊히지 않습니다.

---

## 3. 실험 비교표는 수작업으로 만들지 않는다

MODEL_CHANGELOG의 표는 변천 서사 기록용으로는 적합하지만, 다수 실험을 정렬·필터로 비교하기에는 부적합합니다. 자동 누적되는 CSV가 별도로 필요합니다.

`logs/experiment_board.csv` (평가·학습 스크립트가 매회 한 줄씩 append)

```
run_id, git_sha, date, domain, mean_mse, threshold_caution, threshold_warning, threshold_critical
```

- 매 학습 결과가 한 줄씩 쌓이면 "FAR이 가장 낮았던 run", "phase별 성능 추이"를 즉시 비교할 수 있습니다.
- MODEL_CHANGELOG(경위)와 experiments.csv(정량)가 짝을 이룹니다. 한쪽만으로는 부족합니다.
- 분류 성능(P/R/F1/FAR — 정밀도·재현율·그 둘의 조화 평균·오탐률)은 정답표(라벨)가 있어야 잴 수 있습니다. 그래서 train.py가 아니라 evaluate_test_metrics.py가 같은 run_id로 따로 기록합니다. train 쪽 CSV에는 학습 산출물(MSE·threshold)만 기록합니다.

---

## 4. 한 번에 한 변수만 변경한다

A 평가에서 "NUTRIENT 점검과 mean+max 집계를 각각 독립 실험으로 분리해 기여도를 측정"하기로 한 결정이 정확히 이 원칙입니다.

- 두 변경을 동시에 적용하면 어느 쪽이 성능을 움직였는지 구분할 수 없습니다.
- 한 실험 = 한 가설 = 한 변경. `run_id`의 phase 라벨과 notes에 그 한 가지를 기록합니다.
- 예외: 변경들이 논리적으로 분리 불가능할 때만 묶고, 그 사실을 명시합니다.

---

## 5. 실험 1회의 표준 절차

```
1. 가설 한 줄 작성              (예: nutrient threshold를 percentile로 바꾸면 FAR 감소, recall 유지)
2. 시드 고정 확인               (1절)
3. 한 가지만 변경               (4절)
4. 학습 실행 → 라이브 저장 + runs/ 보존본 (2절)
5. 평가 → experiments.csv append (3절)
6. MODEL_CHANGELOG에 5블록 기록  (가설 → 시도 → 관측 → 진단 → 수정)
7. 개선이면 채택, 아니면 보존본만 남기고 롤백
```

---

## 6. 무거운 학습은 사용자가 직접 실행

`python src/train.py` 등 메모리·연산 집약 작업은 자동 실행하지 않고 먼저 확인합니다. (사용자 환경 리소스 보호 — 프로젝트 운영 규칙)