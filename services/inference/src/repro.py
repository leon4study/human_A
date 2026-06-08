# ==============================================================================
# repro.py — 모델 실험 재현성(Reproducibility) & 실험 추적(Tracking) 유틸
# ==============================================================================
#
# [왜 이 파일이 생겼나]
#   과거 A-3 실험(.claude/MODEL_CHANGELOG.md)에서 `random_state=42`를 걸어뒀는데도
#   train.py를 재학습할 때마다 결과(F1·threshold·선택 피처)가 달라지는 "비결정성"이
#   관측됐다. 그 결과 (1) 무엇이 진짜 개선이고 무엇이 운(seed luck)인지 구분 불가,
#   (2) 좋았던 모델(F1 0.503)을 재학습이 덮어써서 영구 소실, 두 사고가 났다.
#
#   이 모듈은 그 두 문제를 구조적으로 막는다:
#     1) set_global_determinism()  → 모든 난수원(특히 TensorFlow)을 한 번에 고정
#     2) new_run_id() + snapshot_run() → 학습 결과물을 절대 덮어쓰지 않고 타임스탬프로 적재
#     3) get_git_sha()             → "이 모델이 어떤 코드에서 나왔나"를 영구 기록(출처 추적)
#
#   방법론 배경은 docs/modeling/01_experiment_protocol.md,
#   개념 설명은 docs/modeling/05_reproducibility_implementation.md 참조.
# ==============================================================================

import os
import csv
import glob
import json
import random
import shutil
import subprocess
import sys
from datetime import datetime


# ------------------------------------------------------------------------------
# 1. 전역 결정성(Determinism) 고정
# ------------------------------------------------------------------------------
def set_global_determinism(seed: int = 42, logger=None) -> None:
    """
    프로세스 안의 '모든' 난수 발생원을 같은 시드로 묶어, 동일 코드+동일 데이터면
    학습 결과가 비트 단위로 같아지도록 만든다.

    [왜 난수원이 여러 개인가]
      파이썬 한 번 학습에는 서로 다른 난수 엔진이 동시에 돈다. 하나만 고정하면
      나머지가 흔들려서 결과가 매번 달라진다. 그래서 4곳을 전부 잡아야 한다:

        (a) PYTHONHASHSEED  : 파이썬 set/dict의 해시 순서. 이번 비결정성의 '진짜' 원인.
                              피처 목록을 set으로 다루는 코드(다중공선성 드롭, robust
                              voting의 교집합/합집합)가 있어, 순서가 바뀌면 어느 컬럼을
                              드롭/선택하는지가 매 실행 달라져 파이프라인 전체가 흔들린다.
        (b) random          : 파이썬 표준 random 모듈.
        (c) numpy           : 샘플링·셔플 등 수치 연산 난수 (X.sample 등).
        (d) tensorflow      : AE 가중치 초기화·학습. 시드가 없으면 다른 초기값에서 출발한다.

    [PYTHONHASHSEED는 왜 re-exec가 필요한가]
      이 환경변수는 파이썬 인터프리터가 '시작되기 전'에 환경에 있어야 효과가 있다.
      이미 실행 중인 프로세스에서 os.environ["PYTHONHASHSEED"]=... 로 대입해도
      현재 프로세스의 해시 무작위화(sys.flags.hash_randomization)는 바뀌지 않는다.
      따라서 미설정 상태면 환경변수를 박은 뒤 동일 인자로 프로세스를 재실행(os.execv)해
      해시 순서를 고정한다. (2026-06-01 재현성 테스트로 이 함정을 발견·수정)

    [enable_op_determinism()이 따로 필요한 이유]
      tf.random.set_seed()는 '난수 자체'만 고정한다. 하지만 GPU/멀티스레드에서는
      덧셈 같은 연산의 '누적 순서'가 실행마다 달라져(부동소수점은 순서에 민감)
      미세하게 다른 값이 나올 수 있다. enable_op_determinism()은 이 연산 순서까지
      고정한다. 대신 일부 연산이 느려지거나 미지원이라 에러가 날 수 있어 try/except로 감싼다.

    Returns:
        None. (부수효과: 전역 시드 설정. PYTHONHASHSEED 미설정 시 프로세스 재실행)
    """
    # (a) 파이썬 해시 시드 — 런타임 대입은 효과가 없으므로, 미설정이면 환경변수를 박고
    #     프로세스를 재실행한다. 재실행 후에는 이 분기를 건너뛰고 아래 시드 고정으로 진행.
    if os.environ.get("PYTHONHASHSEED") != str(seed):
        os.environ["PYTHONHASHSEED"] = str(seed)
        _log(logger, "info",
             f"PYTHONHASHSEED 미고정 감지 → {seed}로 설정 후 프로세스 재실행"
             f"(set/dict 순서 고정, 재현성 확보)")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # (b) 파이썬 표준 random
    random.seed(seed)

    # (c) numpy — import를 함수 안에서 하는 이유: 이 모듈을 가볍게 유지하고,
    #     numpy/tf가 없는 환경에서도 모듈 자체는 import되게 하기 위함.
    import numpy as np
    np.random.seed(seed)

    # (d) tensorflow — 비결정성의 직접 원인. set_seed로 가중치 초기화/드롭아웃/셔플 난수를 고정.
    import tensorflow as tf
    tf.random.set_seed(seed)

    # 연산 순서까지 결정적으로. TF 2.8+ 에서 제공. 미지원/구버전이면 경고만 남기고 계속.
    op_det = False
    try:
        tf.config.experimental.enable_op_determinism()
        op_det = True
    except Exception as e:  # 구버전 TF 또는 미지원 연산
        _log(logger, "warning",
             f"enable_op_determinism() 미적용(TF 버전 또는 연산 미지원 가능): {e}")

    _log(logger, "info",
         f"전역 결정성 고정 완료 (seed={seed}, op_determinism={op_det}). "
         f"같은 코드와 데이터면 학습 결과가 동일해야 하며, config 2회 비교로 검증한다.")


# ------------------------------------------------------------------------------
# 2. 코드 출처(provenance) 추적 — git commit SHA
# ------------------------------------------------------------------------------
def get_git_sha(short: bool = True) -> str:
    """
    현재 체크아웃된 git 커밋 해시를 반환한다. "이 모델이 정확히 어떤 코드에서
    나왔나"를 모델 폴더에 박아두기 위함(출처 추적). git이 없거나 repo가 아니면
    'nogit'을 반환해 학습을 막지 않는다.

    [왜 필요한가]
      6개월 뒤 "이 run의 결과가 좋았는데 그때 코드가 뭐였지?"를 추적하려면
      메트릭만으론 부족하다. commit SHA가 있으면 `git checkout <sha>`로 그 시점
      코드를 정확히 되살릴 수 있다.
    """
    args = ["git", "rev-parse", "--short", "HEAD"] if short else ["git", "rev-parse", "HEAD"]
    try:
        sha = subprocess.check_output(args, stderr=subprocess.DEVNULL).decode().strip()
        return sha or "nogit"
    except Exception:
        return "nogit"


# ------------------------------------------------------------------------------
# 3. 실험 식별자(run_id) 생성
# ------------------------------------------------------------------------------
def new_run_id(phase: str = None, git_sha: str = None) -> str:
    """
    한 번의 전체 학습(4도메인)을 식별하는 고유 이름을 만든다.
    형식: '<YYYY-MM-DD_HHMMSS>__<git_sha>__<phase>'
      예: '2026-05-31_142210__41c58ea__baseline'

    [phase 인자]
      이번 실험이 무엇을 바꾼 회차인지 한 단어로 태깅(예: 'percentile-thr',
      'mean-max-agg'). 환경변수 PHASE로도 받을 수 있어 코드 수정 없이 라벨링 가능.
      → 나중에 models/runs/ 폴더 이름만 봐도 어떤 실험인지 식별된다.
    """
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    phase = phase or os.environ.get("PHASE", "run")
    git_sha = git_sha or get_git_sha()
    # 폴더명에 안전하도록 공백/슬래시 제거
    safe_phase = "".join(c if c.isalnum() or c in "-_" else "-" for c in phase)
    return f"{ts}__{git_sha}__{safe_phase}"


# ------------------------------------------------------------------------------
# 4. 학습 결과물 불변 스냅샷(snapshot) — 덮어쓰기 방지
# ------------------------------------------------------------------------------
def snapshot_run(models_dir: str, run_id: str, meta: dict = None, logger=None) -> str:
    """
    방금 models_dir(서빙용 라이브 폴더)에 저장된 모델 아티팩트 일습을
    models_dir/runs/<run_id>/ 로 '복사'해 불변 스냅샷으로 남긴다.

    [설계 의도 — 왜 '복사'인가, 왜 라이브 폴더를 안 건드리나]
      inference_api.py는 기동 시 models/ 폴더를 직접 스캔해 모델을 로드한다
      (서빙 계약). 저장 위치를 runs/ 밑으로 옮기면 서빙이 깨진다. 그래서:
        - 라이브 폴더(models/)        : 항상 '최신' — 서빙이 읽는 곳 (계약 불변)
        - 스냅샷(models/runs/<run_id>): 학습 시점의 보존본 — 절대 덮어쓰지 않음
      이렇게 하면 A-3처럼 좋은 모델이 다음 재학습에 사라지는 일이 없다.
      (doc의 'latest symlink' 방식 대신 복사 스냅샷을 쓴 이유: 심링크는 서빙이
       엉뚱한 폴더를 가리킬 위험이 있어, 서빙은 그대로 두고 백업만 추가하는 게 안전.)

    복사 대상: models_dir 바로 아래의 파일들(*.keras, *.pkl, *.json 등).
               하위 폴더(runs/ 자신)는 제외해 무한 복사를 막는다.

    또한 run_meta.json(출처·시드·메타)과 models/LATEST_RUN.txt(최신 run_id 포인터)를 남긴다.

    Returns:
        생성된 스냅샷 폴더 절대경로.
    """
    runs_root = os.path.join(models_dir, "runs")
    run_dir = os.path.join(runs_root, run_id)
    os.makedirs(run_dir, exist_ok=True)

    # models_dir 바로 아래 '파일'만 복사 (runs/ 같은 하위 폴더는 건너뜀)
    copied = 0
    for path in glob.glob(os.path.join(models_dir, "*")):
        if os.path.isfile(path):
            shutil.copy2(path, os.path.join(run_dir, os.path.basename(path)))
            copied += 1

    # 출처·재현 정보 기록
    run_meta = {
        "run_id": run_id,
        "git_sha": get_git_sha(),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "models_dir": os.path.abspath(models_dir),
        "files_copied": copied,
    }
    if meta:
        run_meta.update(meta)  # 도메인별 threshold 요약 등 호출측이 넘긴 정보 병합
    with open(os.path.join(run_dir, "run_meta.json"), "w", encoding="utf-8") as f:
        json.dump(run_meta, f, indent=2, ensure_ascii=False)

    # 최신 run을 가리키는 포인터 파일 (심링크 대신 — 크로스플랫폼·서빙 안전)
    with open(os.path.join(models_dir, "LATEST_RUN.txt"), "w", encoding="utf-8") as f:
        f.write(run_id + "\n")

    _log(logger, "info",
         f"run 스냅샷 저장 완료: {run_dir} (파일 {copied}개). "
         f"라이브(models/)는 서빙용으로 유지하고, 이 폴더는 변경하지 않는 보존본이다.")
    return run_dir


# ------------------------------------------------------------------------------
# 4-b. 최신 run 폴더 조회 — 평가 산출물을 학습과 같은 run에 합류시키기 위함
# ------------------------------------------------------------------------------
def latest_run_dir(models_dir: str) -> str:
    """
    models/LATEST_RUN.txt가 가리키는 최신 run의 보존본 폴더 경로를 반환한다.
    포인터가 없거나 폴더가 실재하지 않으면 None을 반환한다.

    [용도]
      evaluate_test_metrics.py는 라이브 models/ 폴더의 모델로 추론하는데, 그 모델을
      만든 run이 LATEST_RUN.txt에 적혀 있다. 이를 읽어 평가 그래프를 그 run의
      figures/ 에 합류시키면, 한 모델의 학습 그래프와 평가 그래프가 같은 run_id
      폴더에 모인다. (docs/modeling/06_visualization_logging.md)
    """
    pointer = os.path.join(models_dir, "LATEST_RUN.txt")
    if not os.path.isfile(pointer):
        return None
    with open(pointer, "r", encoding="utf-8") as f:
        run_id = f.read().strip()
    run_dir = os.path.join(models_dir, "runs", run_id)
    return run_dir if os.path.isdir(run_dir) else None


# ------------------------------------------------------------------------------
# 5. 학습 실험 리더보드 CSV 누적 (run_id·git_sha 포함)
# ------------------------------------------------------------------------------
def append_experiment_row(csv_path: str, row: dict, logger=None) -> None:
    """
    학습 1회(도메인 1개)의 결과를 한 줄로 experiments CSV에 '누적' 저장한다.
    (덮어쓰지 않고 append. 헤더는 파일이 없을 때 한 번만 기록.)

    [왜 손으로 표를 안 그리고 CSV인가]
      MODEL_CHANGELOG의 표는 '서사'(왜 이렇게 됐나)용으론 훌륭하지만, 수십 회
      실험을 정렬·필터로 비교하기엔 부적합하다. 이 CSV가 '얼마나'(정량)를 맡는다.
      run_id로 묶이므로 같은 run의 4개 도메인이 한 묶음으로 추적된다.

    [P/R/F1/FAR이 여기 없는 이유]
      train.py는 라벨 평가를 하지 않는다(정상 데이터만 학습). 분류 성능 지표는
      evaluate_test_metrics.py가 같은 run_id를 키로 별도 append한다. 여기 train
      보드에는 학습 산물(MSE·threshold)만 정직하게 남긴다.

    Args:
        row: dict. 키가 곧 CSV 컬럼이 된다. (예: run_id, git_sha, domain, ...)
    """
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    fieldnames = list(row.keys())
    header = ",".join(fieldnames)

    # 스키마 변경 안전장치:
    #   기존 파일의 헤더가 지금 쓰려는 컬럼과 다르면(예: 옛 6열 → 새 8열),
    #   헤더 없이 덧붙이면 열이 어긋난다. 이 경우 기존 파일을 .legacy.csv로 보존하고
    #   새 스키마로 새로 시작한다. (옛 데이터 손실 없이 자동 이행)
    write_header = True
    if os.path.isfile(csv_path):
        with open(csv_path, "r", encoding="utf-8") as f:
            existing_header = f.readline().strip()
        if existing_header == header:
            write_header = False
        else:
            stem = csv_path[:-4] if csv_path.endswith(".csv") else csv_path
            legacy = f"{stem}.legacy.csv"
            n = 1
            while os.path.exists(legacy):
                legacy = f"{stem}.legacy{n}.csv"
                n += 1
            os.rename(csv_path, legacy)
            _log(logger, "warning",
                 f"experiments CSV 스키마 변경 감지 → 기존 파일을 "
                 f"{os.path.basename(legacy)}로 보존하고 새 스키마로 시작")

    with open(csv_path, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow(row)
    _log(logger, "info", f"실험 기록 누적: {csv_path} ({row.get('domain', '?')})")


# ------------------------------------------------------------------------------
# 내부 헬퍼 — logger가 있으면 그쪽으로, 없으면 print로 폴백
# ------------------------------------------------------------------------------
def _log(logger, level: str, msg: str) -> None:
    if logger is not None:
        getattr(logger, level, logger.info)(msg)
    else:
        print(msg)
