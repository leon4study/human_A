# 07 — 학습 실행 런북 (train.py 사전 체크리스트)

`python src/train.py`를 실행하기 전에 맞춰야 할 것과, 매 실행을 기록하는 양식입니다. 학습을 돌릴 때마다 이 문서의 1~2절을 확인하고 4절 표에 한 줄 남깁니다.

---

## 1. 사전 체크리스트 (실행 전 반드시 확인)

### 1-1. 현재 모델 백업 (이번이 가장 중요)

`train.py`는 라이브 폴더 `models/`에 도메인 모델을 덮어씁니다. 보존본(`models/runs/<run_id>/`)은 학습이 끝난 뒤 그 run의 결과를 복사하므로, **직전까지 쓰던 모델은 보존되지 않은 채 덮어쓰입니다.**

2026-05-31 기준 `models/runs/`가 비어 있습니다. 즉 현재 `models/`의 4도메인 모델(2026-04-24자)은 아직 어떤 보존본에도 없습니다. 학습을 처음 돌리면 이 모델들은 사라집니다.

실행 전 1회 백업합니다.

```bash
cd /Users/jun/GitStudy/human_A
cp -r models "models_backup_pre_repro_$(date +%Y%m%d_%H%M)"
```

(이후 실행부터는 `snapshot_run`이 매 run을 `models/runs/`에 자동 보존하므로 이 수동 백업은 불필요합니다. A-3 모델 영구 소실 사고의 재발 방지 장치입니다.)

### 1-2. conda 환경 (학습 의존성 확인)

학습에 필요한 외부 패키지: `tensorflow`, `scikit-learn`, `shap`, `joblib`, `pandas`, `numpy`, `matplotlib`.

사용하는 환경에서 아래로 한 번에 확인합니다.

```bash
conda activate <학습용_env>   # 예: leo4study (현재 의존성 충족 확인됨) 또는 analyzer
python - <<'PY'
for m in ["tensorflow","sklearn","shap","joblib","pandas","numpy","matplotlib"]:
    try:
        mod=__import__(m); print("OK ", m, getattr(mod,"__version__","?"))
    except Exception as e:
        print("MISSING", m, e)
PY
```

하나라도 MISSING이면 그 패키지를 설치한 뒤 진행합니다. matplotlib가 없으면 학습은 되지만 진단 그래프가 생략됩니다([06](06_visualization_logging.md)).

### 1-3. 입력 데이터 경로

`train.py`는 다음 절대경로 파일을 읽습니다(현재 하드코딩).

```
data/generated_data_from_dabin_0420.csv
```

존재 확인:

```bash
ls -la /Users/jun/GitStudy/human_A/data/generated_data_from_dabin_0420.csv
```

다른 데이터로 학습하려면 [train.py](../../src/train.py)의 `data_filename`을 수정합니다. 평가용 라벨 데이터(`generated_test_data_0420.csv`)와는 별개입니다.

### 1-4. 실험 라벨(PHASE) 설정 — 권장

이번 학습이 무엇을 바꾼 회차인지 한 단어로 라벨링합니다. `run_id`와 보존본 폴더명, experiments.csv에 함께 기록됩니다([05](05_reproducibility_implementation.md)).

```bash
export PHASE=baseline-repro     # 예: 재현성 인프라 적용 첫 기준선
```

설정하지 않으면 기본값 `run`이 들어갑니다. 의미 있는 실험일수록 라벨을 붙입니다(예: `percentile-thr`, `mean-max-agg`).

---

## 2. 실행 명령

```bash
cd /Users/jun/GitStudy/human_A
export PHASE=baseline-repro
python src/train.py
```

`python src/train.py`는 프로젝트 루트에서 실행해도 됩니다. 스크립트 디렉터리(`src/`)가 자동으로 모듈 경로에 들어가 flat import가 동작합니다.

### 2-1. 재현성 검증 (첫 도입 시 1회)

같은 데이터로 2회 학습한 뒤 config가 동일한지 비교합니다. 동일해야 결정성이 확보된 것입니다([01 §1](01_experiment_protocol.md)).

```bash
python src/train.py            # 1회차
cp models/motor_config.json /tmp/cfg_run1.json
python src/train.py            # 2회차
diff /tmp/cfg_run1.json models/motor_config.json && echo "재현성 OK" || echo "비결정성 남음 → 연산 격리 필요"
```

(2회차도 보존본을 별도 run 폴더에 남기므로 1회차 결과는 사라지지 않습니다.)

---

## 3. 실행 후 확인

- `models/LATEST_RUN.txt` 가 방금 run_id를 가리키는가
- `models/runs/<run_id>/` 에 4도메인 아티팩트 + `run_meta.json` 이 있는가
- `models/runs/<run_id>/figures/` 에 도메인별 `__mse_diagnosis.png`, `__loss_curve.png`, `_contact_sheet.png` 가 있는가
- `logs/experiment_board.csv` 에 run_id·git_sha 포함 도메인별 행이 누적됐는가
- 콘솔 로그에 "전역 결정성 고정 완료", "run 스냅샷 저장 완료" 가 보이는가

이어서 평가까지 보려면([06](06_visualization_logging.md)):

```bash
python src/evaluate_test_metrics.py    # 같은 run 폴더 figures/에 eval 타임라인 합류
```

---

## 4. 실행 기록 양식 (매 실행 한 줄)

| 날짜 | PHASE | run_id(요약) | 변경한 한 가지 | 결과 요약(F1/FAR 또는 관찰) | 채택? |
|---|---|---|---|---|---|
| 2026-05-31 | baseline-repro | (첫 실행) | 재현성 인프라 적용 | (기록) | |
| | | | | | |

상세 서사(가설 → 시도 → 관측 → 진단 → 수정)는 [.claude/MODEL_CHANGELOG.md](../../.claude/MODEL_CHANGELOG.md)에, 정량 수치는 `logs/experiment_board.csv`에 누적합니다. 이 표는 한눈에 보는 색인입니다.

---

## 5. 자주 막히는 지점

| 증상 | 원인 / 해결 |
|---|---|
| `ModuleNotFoundError: repro/viz` | `python src/train.py`를 프로젝트 루트 또는 `src/`에서 실행. 다른 경로면 모듈 경로 누락 |
| 진단 그래프가 안 생김 | matplotlib 미설치. 학습은 정상 완료되며 그래프만 생략(1-2 확인) |
| 재현성 검증에서 config가 다름 | 결정성 미확보. TF GPU/연산 비결정 의심 → [05 §5](05_reproducibility_implementation.md) |
| 이전 모델이 사라졌다 | 1-1 백업을 건너뜀. 이후부터는 `models/runs/`에 자동 보존됨 |
