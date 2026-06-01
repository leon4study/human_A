# 05 — 재현성·추적 구현 (repro.py)

[01 실험 프로토콜](01_experiment_protocol.md)의 원칙을 코드로 구현한 모듈이 [../../src/repro.py](../../src/repro.py)입니다. 이 문서는 처음 도입되는 개념과 사용·검증 방법을 설명합니다.

---

## 1. 왜 이 모듈이 생겼는가

A-3 실험에서 `random_state=42`를 설정했음에도 재학습 결과가 매번 달랐고(비결정성), 그 결과 좋았던 모델(F1 0.503)을 재학습이 덮어써 영구 소실했습니다. repro.py는 이 두 문제를 구조적으로 차단합니다.

| 함수 | 역할 |
|---|---|
| `set_global_determinism(seed)` | 모든 난수원(특히 TensorFlow)을 고정해 재학습이 같은 결과를 내도록 함 |
| `get_git_sha()` | 이 모델이 어떤 코드(commit)에서 나왔는지 출처 기록 |
| `new_run_id(phase, git_sha)` | 학습 1회를 식별하는 타임스탬프 이름 생성 |
| `snapshot_run(models_dir, run_id, meta)` | 학습 결과를 `models/runs/<run_id>/`에 보존(덮어쓰기 방지) |
| `append_experiment_row(csv_path, row)` | 학습 결과를 CSV에 누적(정량 비교용) |

---

## 2. 처음 도입하는 개념

### 2-1. 결정성(Determinism)과 난수원이 여러 개인 이유

파이썬 한 번의 학습에는 서로 다른 난수 엔진이 동시에 동작합니다. 하나만 고정하면 나머지가 흔들려 결과가 달라집니다. 그래서 네 곳을 모두 고정합니다.

| 난수원 | 무엇을 흔드는가 |
|---|---|
| `PYTHONHASHSEED` | set/dict의 해시 순서. **이번 비결정성의 진범.** 다중공선성 드롭·robust voting이 set 순서에 의존 |
| `random` | 파이썬 표준 random |
| `numpy` | 샘플링·셔플 등 수치 연산 난수 |
| `tensorflow` | AE 가중치 초기화·드롭아웃·셔플 |

2026-06-01 재현성 테스트에서 2회 실행의 config가 4도메인 전부 달랐고, set 순서가 실행마다 바뀌는 것을 확인해 진범이 해시 무작위화임을 규명했습니다. feature_selection의 RandomForest·KMeans는 `random_state`로 재현 가능하지만, 그 위 set 순서가 흔들리고 있었습니다.

### 2-2. PYTHONHASHSEED는 왜 re-exec가 필요한가

`os.environ["PYTHONHASHSEED"]=...`를 실행 중에 대입해도 현재 인터프리터의 해시 무작위화는 바뀌지 않습니다. 이 값은 파이썬이 시작되기 전에 환경에 있어야 합니다. 그래서 `set_global_determinism`은 미설정 시 환경변수를 박고 `os.execv`로 프로세스를 재실행해 해시 순서를 고정합니다. (초기 구현은 런타임 대입만 해서 무효였고, 재현성 테스트가 이 함정을 잡았습니다.)

### 2-3. enable_op_determinism()이 별도로 필요한 이유

`tf.random.set_seed()`는 난수 자체만 고정합니다. 그러나 GPU·멀티스레드에서는 덧셈 같은 연산의 누적 순서가 실행마다 달라질 수 있고(부동소수점은 순서에 민감), 그 결과 미세하게 다른 값이 나옵니다. `enable_op_determinism()`은 이 연산 순서까지 고정합니다. 일부 연산은 느려지거나 미지원이라 예외가 발생할 수 있어 try/except로 감싸고, 미적용 시 경고만 남기고 진행합니다(TF 2.8 이상에서 제공).

### 2-4. 코드 출처 추적(provenance)과 git SHA

수개월 뒤 "이 run의 결과가 좋았는데 그때 코드가 무엇이었는가"를 추적하려면 메트릭만으로는 부족합니다. commit SHA를 모델 폴더에 기록해 두면 `git checkout <sha>`로 그 시점 코드를 정확히 되살릴 수 있습니다. git이 없거나 repo가 아니면 `nogit`을 반환해 학습을 막지 않습니다.

### 2-5. 라이브 폴더와 보존본 스냅샷의 분리

inference_api는 기동 시 `models/` 폴더를 직접 스캔해 모델을 로드합니다(서빙 계약). 저장 위치를 `runs/` 아래로 옮기면 서빙이 깨집니다. 그래서 두 위치로 분리합니다.

| 위치 | 성격 |
|---|---|
| `models/` (라이브) | 항상 최신 — 서빙이 읽는 곳, 계약 불변 |
| `models/runs/<run_id>/` (보존본) | 학습 시점 보존 — 절대 덮어쓰지 않음 |

심링크(latest symlink) 대신 복사 스냅샷과 포인터 파일(`LATEST_RUN.txt`)을 사용합니다. 심링크는 서빙이 의도치 않은 폴더를 가리킬 위험이 있어, 서빙은 그대로 두고 보존본만 추가하는 방식이 안전합니다.

### 2-6. run_id로 실험을 묶는 이유

`run_id`는 `<시각>__<git_sha>__<phase>` 형식입니다(예: `2026-05-31_142210__41c58ea__baseline`). 한 번의 학습(4개 도메인)이 하나의 run_id로 묶이므로, experiments.csv·보존본·시각화가 모두 같은 키로 연결됩니다. `phase`는 환경변수로 실험 라벨을 줄 수 있어 코드 수정 없이 구분됩니다.

```
PHASE=percentile-thr python src/train.py
```

---

## 3. train.py 연동 지점

| 위치 | 호출 |
|---|---|
| 메인 블록 시작 (모델 생성 이전) | `set_global_determinism(seed=42)` |
| 메인 블록 시작 | `git_sha = get_git_sha()`, `run_id = new_run_id(git_sha=git_sha)` |
| 도메인 학습 호출 | `train_and_save_model(..., run_id=run_id, git_sha=git_sha)` |
| 도메인별 결과 기록 | `save_experiment_to_csv(..., run_id, git_sha)` → `append_experiment_row` |
| 4개 도메인 학습 종료 후 | `snapshot_run(models_dir, run_id, meta=...)` |

---

## 4. 검증 방법

1. 재현성: 동일 데이터로 `python src/train.py`를 2회 실행한 뒤 두 `*_config.json`의 thresholds·features가 동일한지 비교합니다. 다르면 비결정성이 남아 있는 것이며, 어느 연산이 결정성을 깨는지 격리해 확인합니다.
2. 보존본: 학습 후 `models/runs/<run_id>/`에 4개 도메인 아티팩트와 `run_meta.json`이 생성됐는지 확인합니다.
3. 포인터: `models/LATEST_RUN.txt`가 최신 run_id를 가리키는지 확인합니다.
4. 리더보드: `logs/experiment_board.csv`에 run_id·git_sha 컬럼과 함께 도메인별 행이 누적됐는지 확인합니다.

---

## 5. 한계와 후속 과제

- `enable_op_determinism()`이 미지원인 환경에서는 미세한 비결정성이 남을 수 있습니다. 그 경우 검증(4-1)이 통과하지 못하므로, TF 버전 확인 또는 해당 연산 격리가 필요합니다.
- 분류 성능(P/R/F1/FAR) 기록은 evaluate_test_metrics.py가 같은 run_id로 별도 append하도록 연동해야 완성됩니다(미구현).
- 진단 시각화 자동 저장은 [06](06_visualization_logging.md)에서 다룹니다.
