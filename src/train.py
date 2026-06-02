# train.py 는 1분단위의 데이터를 학습시켜야 성능이 우수함.

import os
import json
import numpy as np
import pandas as pd
import tensorflow as tf
import time
from datetime import datetime
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input, Dense, Dropout
from tensorflow.keras.callbacks import EarlyStopping
from sklearn.preprocessing import MinMaxScaler


# 우리가 만들어둔 '메인 셰프(파이프라인 매니저)' 모듈 불러오기
from feature_engineering import SENSOR_MANDATORY, VIP_FEATURES, inject_vip_features
from feature_selection import run_feature_selection_experiment
from inference_core import actionable_feature_mask, build_target_reference_profiles
from logger import get_logger
from math_utils import calculate_sigma_thresholds
from model_builder import build_autoencoder
from utils import save_model_artifacts

# [재현성/추적 인프라] — repro.py (docs/modeling/05_reproducibility_implementation.md)
#   set_global_determinism : 모든 난수원(특히 TF)을 고정해 재학습이 같은 결과를 내게 함
#   get_git_sha            : 이 모델이 어떤 코드(commit)에서 나왔는지 출처 기록
#   new_run_id             : 이번 학습 1회를 식별하는 타임스탬프 이름
#   snapshot_run           : 학습 결과를 models/runs/<run_id>/에 불변 박제(덮어쓰기 방지)
#   append_experiment_row  : 학습 결과를 experiments CSV에 누적(손표 대신 정량 비교용)
from repro import (
    set_global_determinism,
    get_git_sha,
    new_run_id,
    snapshot_run,
    append_experiment_row,
)

# [진단 시각화] — viz.py (docs/modeling/06_visualization_logging.md)
#   matplotlib가 없는 환경에서도 학습 자체는 진행되도록 import 실패를 흡수한다.
#   (시각화는 평가의 일부지만, 라이브러리 부재가 학습을 막아서는 안 됨)
try:
    from viz import plot_threshold_diagnosis, plot_loss_curve, build_contact_sheet
    _VIZ_AVAILABLE = True
except Exception as _viz_err:  # matplotlib 미설치 등
    _VIZ_AVAILABLE = False
    _VIZ_IMPORT_ERROR = _viz_err

# 로거 생성
logger = get_logger("TRAIN")


# ==============================================================================
# 실험 결과 기록 (리더보드 CSV)
# ==============================================================================
def save_experiment_to_csv(model_name, mse_mean, t_caut, t_warn, t_cri,
                           run_id="legacy", git_sha="nogit"):
    """
    리더보드(CSV)에 학습 결과 1줄을 누적 저장합니다.

    [run_id / git_sha 컬럼이 추가된 이유]
      예전엔 Date·Domain·MSE·threshold만 남겨서, 여러 번 학습하면 "이 줄이 어느
      실험(어느 코드)의 결과인지" 묶을 수가 없었다. run_id(이번 학습 묶음 식별자)와
      git_sha(코드 출처)를 같이 박으면, 같은 run의 4개 도메인이 한 묶음으로 추적되고
      나중에 정렬·필터로 "어느 실험이 FAR을 낮췄나"를 즉시 비교할 수 있다.
      (분류 성능 P/R/F1은 라벨 평가가 필요해 evaluate_test_metrics.py가 같은 run_id로 별도 기록)

    실제 파일 쓰기는 repro.append_experiment_row가 담당(헤더 자동 관리 + append-only).
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    csv_path = os.path.join(project_root, "logs", "experiment_board.csv")

    append_experiment_row(
        csv_path,
        {
            "run_id": run_id,
            "git_sha": git_sha,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "domain": model_name,
            "mean_mse": round(mse_mean, 6),
            "threshold_caution": round(t_caut, 6),
            "threshold_warning": round(t_warn, 6),
            "threshold_critical": round(t_cri, 6),
        },
        logger=logger,
    )


# ==============================================================================
# 🛠️ [모델 학습 및 아티팩트 저장 통합 함수]
# ==============================================================================
def train_and_save_model(X_train_ae, model_name, target_dict=None, df_reference=None,
                         run_id="legacy", git_sha="nogit", figures_dir=None):
    """
    특정 도메인(예: motor, hydraulic)의 데이터를 받아
    독립적인 AutoEncoder 모델을 학습하고 아티팩트를 저장합니다.

    run_id / git_sha
        이번 학습이 어느 실험 묶음(run_id)과 어느 코드(git_sha)에서 나왔는지를
        실험 리더보드 CSV에 함께 기록하기 위한 식별자입니다. 메인 블록에서 한 번
        생성해 4개 도메인에 동일하게 전달하므로, 같은 run의 결과가 한 묶음으로 추적됩니다.
    """
    start_time = time.time()

    logger.info(f"🚀 [{model_name.upper()}] 모델 파이프라인 시작")

    # 1. 데이터 스케일링
    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(X_train_ae)

    # 2. 모델 구조 설계 (AutoEncoder 모델 생성)
    logger.info("🧠 [Phase 5-2] 텐서플로우 AutoEncoder 모델 구조 설계...")
    autoencoder = build_autoencoder(input_dim=X_scaled.shape[1])

    # 3. 모델 학습
    logger.info("🚀 [Phase 5-3] AutoEncoder 모델 학습 시작...")
    early_stopping = EarlyStopping(
        monitor="val_loss", patience=10, restore_best_weights=True
    )

    # 시각화용 Loss 점수 저장을 위해 history 객체 수집
    history = autoencoder.fit(
        X_scaled,
        X_scaled,
        epochs=100,
        batch_size=64,
        validation_split=0.2,  # 데이터의 20%를 검증(Validation)용으로 자동 사용
        callbacks=[early_stopping],
        verbose=1,  # 딥러닝 진행바(Epoch)는 print 기반이므로 화면에만 나오고 로그엔 안 찍힙니다
    )

    # 4. 추론 및 시그마 임계값 계산 (math_utils.py 에게 외주)
    logger.info("🎯 [Phase 5-4] 이상 탐지 임계값(Threshold) 계산...")
    reconstructed = autoencoder.predict(X_scaled)
    sq_err = np.power(X_scaled - reconstructed, 2)

    # 🌟 알람 근거 == 설명 일치:
    # 시간·상태 컨텍스트 피처는 MSE 점수 계산에서 제외해, 실센서 복원 오차만으로
    # threshold를 세운다. 그래야 RCA(같은 제외 셋)와 같은 피처에 대해 판정/설명이
    # 일관된다. (inference_core.DEFAULT_CONTEXT_FEATURES 단일 소스)
    feature_cols = X_train_ae.columns.tolist()
    scoring_mask = actionable_feature_mask(feature_cols)
    if scoring_mask.sum() == 0:
        logger.warning(
            "⚠️ 모든 피처가 컨텍스트로 제외되어 scoring_mask가 비어있습니다. "
            "전체 피처로 폴백합니다."
        )
        scoring_mask = np.ones(len(feature_cols), dtype=bool)
    scoring_features = [f for f, keep in zip(feature_cols, scoring_mask) if keep]
    logger.info(
        f"  ▶ MSE scoring features: {len(scoring_features)}/{len(feature_cols)}개 "
        f"(컨텍스트 제외: {sorted(set(feature_cols) - set(scoring_features))})"
    )

    mse_scores = np.mean(sq_err[:, scoring_mask], axis=1)

    # ── 임계치 계산 — 기동(startup) 구간 제외 + 방법 선택 ──────────────────────
    # [왜] 기동 직후 transient는 MSE가 크게 튀어 σ/percentile을 부풀린다. eval에서
    #   zone_drip이 이상 구간에 반응(MSE 상승)했음에도 임계치가 너무 높아 recall이 막힌
    #   원인이 이것. 그래서 threshold는 기동 구간을 빼고 계산한다.
    #   (docs/modeling/03_threshold_methodology.md)
    startup_row_mask = np.zeros(len(mse_scores), dtype=bool)
    if "is_startup_phase" in X_train_ae.columns:
        startup_row_mask = (X_train_ae["is_startup_phase"].to_numpy() == 1)
    elif "minutes_since_startup" in X_train_ae.columns:
        # 주의: minutes_since_startup는 정지(off) 구간에서 0이다. 따라서 단순히
        #   minutes<=5 로 잡으면 '진짜 기동 5분'뿐 아니라 off 전체(데이터의 ~50%)가
        #   기동으로 잘못 분류돼 baseline이 왜곡된다(2026-06-02 평가에서 hydraulic 회귀로 발견).
        #   pump_on==1 조건을 함께 걸어 '펌프가 켜진 직후 5분'만 정확히 제외한다.
        mss = X_train_ae["minutes_since_startup"].to_numpy()
        if "pump_on" in X_train_ae.columns:
            startup_row_mask = (X_train_ae["pump_on"].to_numpy() == 1) & (mss <= 5)
        else:
            startup_row_mask = (mss <= 5)
    mse_base = mse_scores[~startup_row_mask]
    if len(mse_base) < 100:  # 기동 제외 후 표본이 너무 적으면 전체로 폴백
        mse_base = mse_scores

    # ── 임계치 산정 '방법'을 분포 비대칭도(skew)로 도메인별 자동 선택 ────────────
    #
    # [배경 — 왜 도메인마다 '방법'을 달리하나]
    #   평가(2026-06-02)에서 단일 percentile을 4개 도메인에 똑같이 적용했더니 결과가 갈렸다:
    #     - zone_drip(꼬리 긴 분포): recall 0.015 → 0.41 로 살아남  → percentile이 맞음
    #     - hydraulic(정규에 가까운 분포): recall 0.30 → 0.15 로 망가짐 → sigma가 맞음
    #   즉 "어떤 방법이 옳은가"는 그 도메인 오차 분포의 '모양'에 달려 있고, 모양은 도메인마다 다르다.
    #   그리고 이 '모양' 불일치는 percentile '레벨'(P95→P98)을 조절해도 고쳐지지 않는다.
    #   레벨은 같은 방법 안에서 threshold를 위아래로 옮길 뿐이고, hydraulic처럼 방법 자체가
    #   안 맞는 도메인은 레벨을 어디로 옮겨도 sigma만 못하다. → 그래서 '방법'을 분기한다.
    #
    # [skew(왜곡도)란 — 한 줄 정의]
    #   분포가 한쪽으로 얼마나 치우쳤는지를 재는 표준화 3차 모멘트.
    #     skew ≈ 0  : 좌우 대칭(정규에 가까움)            → μ+kσ(sigma)가 분포를 잘 기술
    #     skew >> 0 : 오른쪽 꼬리가 긴 분포(소수 극단값)   → σ가 그 극단값에 부풀려짐 → percentile이 robust
    #   AE 복원오차는 대개 오른쪽으로 치우치는데 그 '정도'가 도메인마다 다르다
    #   (관측: hydraulic ~3, zone_drip ~11, motor ~15).
    #
    # [분기 규칙]
    #   skew >  SKEW_CUTOFF → percentile (꼬리 긴 도메인: P95/99/99.9, 극단값에 안 흔들림)
    #   skew <= SKEW_CUTOFF → sigma      (정규형 도메인: μ+2σ/3σ/6σ, 모양이 맞음)
    #   둘 다 위에서 만든 mse_base(기동 제외)에서 계산한다.
    #
    # [환경변수 override — 비교 실험·튜닝용]
    #   THRESHOLD_METHOD=auto(기본) → skew로 자동 분기
    #   THRESHOLD_METHOD=sigma|percentile → 모든 도메인 강제 고정(방법 비교 실험)
    #   SKEW_CUTOFF(기본 8.0) → 자동 분기 경계. PCT_CAUTION/WARNING/CRITICAL → percentile 레벨.
    #   설계 근거: docs/modeling/03_threshold_methodology.md §4(도메인별 보정).

    # (1) 분포 왜곡도 계산 — 표준 라이브러리만(scipy 불필요), 3차 모멘트 직접 계산.
    _mu = float(np.mean(mse_base))
    _sd = float(np.std(mse_base))
    mse_skew = (
        float(np.mean(((mse_base - _mu) / _sd) ** 3))
        if _sd > 0 and len(mse_base) >= 3
        else 0.0
    )

    # (2) 방법 결정 — auto면 skew로 분기, 아니면 환경변수가 지정한 방법으로 강제.
    SKEW_CUTOFF = float(os.environ.get("SKEW_CUTOFF", "8.0"))
    method_opt = os.environ.get("THRESHOLD_METHOD", "auto").lower()
    if method_opt == "auto":
        chosen_method = "percentile" if mse_skew > SKEW_CUTOFF else "sigma"
    else:
        chosen_method = method_opt  # "sigma" 또는 "percentile" 강제

    # (3) 선택된 방법으로 3단계 임계치 산정.
    if chosen_method == "percentile":
        # P95≈정상의 상위 5%(주의)·P99≈1%(경고)·P99.9≈0.1%(치명).
        # 운영 제약(FAR)과 직결되며, 레벨은 환경변수로 미세조정 가능.
        p_caut = float(os.environ.get("PCT_CAUTION", "95.0"))
        p_warn = float(os.environ.get("PCT_WARNING", "99.0"))
        p_crit = float(os.environ.get("PCT_CRITICAL", "99.9"))
        thresholds = {
            "mean":     _mu,
            "caution":  float(np.percentile(mse_base, p_caut)),
            "warning":  float(np.percentile(mse_base, p_warn)),
            "critical": float(np.percentile(mse_base, p_crit)),
        }
    else:
        # 정규형 분포에 적합한 6시그마 3단계(μ+2σ/3σ/6σ).
        thresholds = calculate_sigma_thresholds(mse_base, sigma_levels=(2, 3, 6))

    logger.info(
        f"임계값 설정 (method={chosen_method}{' [auto]' if method_opt == 'auto' else ''}, "
        f"skew={mse_skew:.2f}, cutoff={SKEW_CUTOFF}, 기동 {int(startup_row_mask.sum())}샘플 제외)"
    )
    logger.info(f"   Caution:  {thresholds['caution']:.6f}")
    logger.info(f"   Warning:  {thresholds['warning']:.6f}")
    logger.info(f"   Critical: {thresholds['critical']:.6f}")

    # 🔬 피처별 재구성오차 시그마 컷 (스케일 공간 기준, 도메인 컷과 동일 정책 2/3/6σ)
    # 도메인 MSE는 axis=1 평균으로 F차원을 압축하지만, sq_err 자체는 (N x F) 행렬이라
    # 피처별 분포가 그대로 살아있다. 열별(axis=0)로 평균·표준편차를 내면
    # 각 센서가 "AE 재구성 대비 얼마나 튀어야 이상인지" 독립 임계치를 얻을 수 있다.
    per_feature_thresholds = {}
    for j, fname in enumerate(feature_cols):
        if not scoring_mask[j]:
            continue  # 컨텍스트 피처는 제외 (RCA/알람 근거 셋과 동일)
        col_err = sq_err[:, j]
        mu = float(col_err.mean())
        sd = float(col_err.std())
        per_feature_thresholds[fname] = {
            "mean":     round(mu, 8),
            "std":      round(sd, 8),
            "caution":  round(mu + 2 * sd, 8),
            "warning":  round(mu + 3 * sd, 8),
            "critical": round(mu + 6 * sd, 8),
        }
    logger.info(
        f"  📊 피처별 threshold 계산 완료: {len(per_feature_thresholds)}개 피처"
    )

    # 4-b. 진단 시각화 저장 (run 폴더의 figures/ 로 자동 적재)
    #   - MSE 분포(쏠림 확인) + 시계열(임계치 적용·기동 음영) 한 장
    #   - 학습 곡선(과적합 확인)
    #   기동 마스크: AE 입력에 남아 있는 운전 맥락 피처에서 도출한다. is_startup_phase가
    #   있으면 그대로 쓰고, 없으면 minutes_since_startup<=5(기동 직후 5분)로 근사한다.
    #   이 마스크가 있어야 "기동 스파이크가 threshold를 부풀렸는지"를 그래프에서 비교할 수 있다.
    #   학습 데이터는 이상 구간이 제거돼 있으므로 anomaly 음영은 평가 단계(evaluate)에서 그린다.
    if _VIZ_AVAILABLE and figures_dir is not None:
        try:
            startup_mask = None
            if "is_startup_phase" in X_train_ae.columns:
                startup_mask = (X_train_ae["is_startup_phase"].to_numpy() == 1)
            elif "minutes_since_startup" in X_train_ae.columns:
                startup_mask = (X_train_ae["minutes_since_startup"].to_numpy() <= 5)

            plot_threshold_diagnosis(
                mse_scores, thresholds, model_name,
                save_path=os.path.join(figures_dir, f"{model_name}__mse_diagnosis.png"),
                startup_mask=startup_mask,
                anomaly_mask=None,  # 학습 데이터엔 이상 라벨 없음(정상 구간만)
            )
            plot_loss_curve(
                history, model_name,
                save_path=os.path.join(figures_dir, f"{model_name}__loss_curve.png"),
            )
            logger.info(f"  진단 시각화 저장 완료: {figures_dir}")
        except Exception as e:
            # 시각화 실패가 학습/저장을 막아서는 안 된다
            logger.warning(f"  진단 시각화 저장 실패(학습은 정상 완료): {e}")
    elif not _VIZ_AVAILABLE:
        logger.warning("  matplotlib 미가용으로 진단 시각화 생략(학습은 정상 진행)")

    # 5. 프론트엔드용 메타데이터(Config) 조립

    logger.info("💾 [Phase 5-5] 서버 배포용 아티팩트(Artifacts) 저장...")
    target_reference_profiles = {}
    if target_dict and df_reference is not None:
        target_reference_profiles = build_target_reference_profiles(
            df_reference, target_dict
        )

    config = {
        "model_name": model_name,
        "features": X_train_ae.columns.tolist(),
        # threshold 계산과 동일한 피처 셋으로 추론 시에도 MSE를 내야 일관성 유지
        "scoring_features": scoring_features,
        "target_feature_map": target_dict or {},
        "threshold_caution": thresholds["caution"],
        "threshold_warning": thresholds["warning"],
        "threshold_critical": thresholds["critical"],
        # 임계치 산정 추적: 실제 적용된 방법(auto면 skew로 분기된 결과)과 그 근거 skew값.
        "threshold_method": chosen_method,
        "threshold_skew": round(mse_skew, 4),
        "per_feature_thresholds": per_feature_thresholds,
        "metrics": {
            "train_loss": [float(l) for l in history.history["loss"]],
            "val_loss": [float(l) for l in history.history["val_loss"]],
            "final_mse_mean": thresholds["mean"],
        },
        "feature_stds": X_train_ae.std().to_dict(),
        "target_reference_profiles": target_reference_profiles,
    }

    # 6. 아티팩트 저장
    current_dir = os.path.dirname(os.path.abspath(__file__))
    save_dir = os.path.join(os.path.dirname(current_dir), "models")

    save_model_artifacts(autoencoder, scaler, config, model_name, save_dir)
    logger.info(f"✅ [{model_name.upper()}] 학습 및 아티팩트 저장 완료! ({save_dir})")

    # 7. 실험 기록 및 메모리 정리
    save_experiment_to_csv(
        model_name=model_name,
        mse_mean=thresholds["mean"],
        t_caut=thresholds["caution"],
        t_warn=thresholds["warning"],
        t_cri=thresholds["critical"],
        run_id=run_id,
        git_sha=git_sha,
    )

    end_time = time.time()
    logger.info(
        f"⏱️ 모델링 소요 시간: {int((end_time - start_time) // 60)}분 {(end_time - start_time) % 60:.2f}초"
    )
    # 🌟 메모리 누수 방지: 학습 완료 후 텐서플로우 세션 정리
    tf.keras.backend.clear_session()
    return None


# ==============================================================================
# ⚔️ [메인 실행 블록]
# ==============================================================================
if __name__ == "__main__":
    total_start_time = time.time()
    logger.info("[MAIN] 다중 도메인(Multi-Domain) 예지보전 AI 파이프라인 학습 시작")

    # --------------------------------------------------------------------------
    # [재현성 고정] 어떤 학습보다 먼저 실행한다.
    #   AutoEncoder 가중치 초기화는 시드가 없으면 매번 다른 값에서 출발해 다른 모델로
    #   수렴한다. 모델을 만들기(build_autoencoder) 전에 전역 시드를 박아야, 같은 코드와
    #   같은 데이터면 같은 모델이 나온다. 이 한 줄이 "성능이 좋아졌는지, 운이 좋았는지"를
    #   구분 가능하게 만드는 전제 조건이다. (docs/modeling/01_experiment_protocol.md §1)
    # --------------------------------------------------------------------------
    set_global_determinism(seed=42, logger=logger)

    # --------------------------------------------------------------------------
    # [실험 식별자] 이번 학습 1회(4개 도메인)를 하나로 묶는 이름과 코드 출처를 만든다.
    #   - git_sha : 이 결과가 어느 커밋에서 나왔는지 → 나중에 그 시점 코드를 되살릴 수 있게.
    #   - run_id  : '시각__sha__phase' 형태. PHASE 환경변수로 실험 라벨을 줄 수 있다.
    #               예) PHASE=percentile-thr python train.py
    # --------------------------------------------------------------------------
    git_sha = get_git_sha()
    run_id = new_run_id(git_sha=git_sha)
    logger.info(f"[MAIN] run_id={run_id} (git={git_sha})")

    # 경로 하드코딩 제거 -> 동적 경로 탐색 로직 적용
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)

    # [시각화 출력 폴더] 이번 run의 보존본 폴더 아래 figures/ 에 도메인별 그래프를 모은다.
    #   같은 run_id로 모델·메트릭·이미지가 한 묶음으로 보존되어, 옵션을 바꾼 다른 run과
    #   같은 파일명으로 바로 비교된다. (docs/modeling/06_visualization_logging.md)
    run_figures_dir = os.path.join(project_root, "models", "runs", run_id, "figures")

    # /Users/... 대신 project_main_folder/data 폴더를 찾아가도록 설정
    data_filename = (
        "/Users/jun/GitStudy/human_A/data/generated_data_from_dabin_0420.csv"
    )
    data_path = os.path.join(project_root, "data", data_filename)

    logger.info(f"📂 데이터 로딩 경로: {data_path}")
    df_raw = pd.read_csv(data_path)

    # 🌟 [추가] timestamp 컬럼을 datetime 형으로 바꾸고 인덱스로 설정!
    df_raw["timestamp"] = pd.to_datetime(df_raw["timestamp"])
    df_raw = df_raw.set_index("timestamp")

    # 🌟 서브시스템별로 타겟 딕셔너리를 묶어서 정의합니다.
    # 각 도메인 성격에 맞는 타겟들을 지정해 주면 훨씬 똑똑한 피처가 뽑힙니다.
    subsystem_targets = {
        "motor": {
            "motor_current_a": [
                "motor_power_kw",
                "motor_temperature_c",
                "wire_to_water_efficiency",
                "bearing_vibration_rms_mm_s"
            ],
            "rpm_stability_index": ["pump_rpm"],
        },
        "hydraulic": {  # 수력/압력/유량 도메인
            "zone1_resistance": ["zone1_pressure_kpa", "zone1_flow_l_min"],
            "differential_pressure_kpa": [
                "discharge_pressure_kpa",
                "suction_pressure_kpa",
            ],
        },
        "nutrient": {  # 양액/수질/환경 도메인
            # A-3 롤백(2026-04-20): raw 센서 target 재편안을 시도했으나 재학습 후 전 도메인 악화
            # (motor F1 0.527→0.106, zone_drip 완전 붕괴). 원인 미규명 → A-2 상태 복구.
            # 현재는 nutrient를 evaluate의 overall voting에서 제외하는 운영(EXCLUDE_FROM_OVERALL)로 운용.
            "pid_error_ec": ["mix_ec_ds_m", "mix_target_ec_ds_m"],
            "salt_accumulation_delta": ["drain_ec_ds_m", "mix_ec_ds_m"],
        },
        "zone_drip": {  # 구역 점적 시스템 도메인
            "zone1_moisture_response_pct": ["zone1_substrate_moisture_pct"],
            "zone1_ec_accumulation": ["zone1_substrate_ec_ds_m", "mix_ec_ds_m"],
        },
    }

    # 🌟 [수정포인트 4] For 루프를 돌면서 각각 독립적인 모델을 학습시킵니다.
    for system_name, target_dict in subsystem_targets.items():
        logger.info(f"[{system_name.upper()} 도메인] 분석 파이프라인 시작")

        # 1. 도메인별 피처 셀렉션
        # df_agg: target_reference_profiles 계산용(raw 센서 이름 유지 윈도우 집계본)
        robust_features, X_train_ae, df_interpret_result, _, df_agg, shap_vals_dict, X_bg_dict = run_feature_selection_experiment(
            df_raw=df_raw, window_method="sliding", target_dict=target_dict
        )

        # VIP 피처 강제 주입: 시간 피처 + 운전 모드 피처 (기동/정지 맥락)
        # → SHAP에서 빠져도 AE가 '기동 스파이크는 정상 루틴'임을 학습할 수 있도록 보완.
        # VIP_FEATURES 정의는 feature_engineering.py (Tier 3 LSTM-AE 전환 시에도 그대로 재사용).
        X_train_ae, injected_vips = inject_vip_features(
            X_train_ae, df_interpret_result, VIP_FEATURES
        )
        if injected_vips:
            logger.info(
                f"🔗 오토인코더 입력 데이터에 VIP 피처 강제 주입: {injected_vips}"
            )

        # 도메인별 필수 센서 강제 주입 — SHAP robust selection이 0개/소수만 뽑아도
        # 실제 센서 피처가 AE 입력에 반드시 포함되도록 보장.
        # 소스는 df_agg (raw 센서 + 파생 포함한 윈도우 집계본).
        mandatory_sensors = SENSOR_MANDATORY.get(system_name, [])
        X_train_ae, injected_sensors = inject_vip_features(
            X_train_ae, df_agg, mandatory_sensors
        )
        if injected_sensors:
            logger.info(
                f"🔗 [{system_name.upper()}] 필수 센서 강제 주입: {injected_sensors}"
            )
        missing_sensors = [
            s for s in mandatory_sensors if s not in X_train_ae.columns
        ]
        if missing_sensors:
            logger.warning(
                f"⚠️  [{system_name.upper()}] SENSOR_MANDATORY에 있으나 df_agg에 없는 피처: {missing_sensors}"
            )

        # 2. 도메인별 모델 학습 및 저장 (이름을 같이 넘겨줌)
        # df_reference는 raw 센서 컬럼명이 살아있는 df_agg를 넘긴다.
        # df_interpret_result는 파생 지표(pressure_flow_ratio 등) 전용이라
        # motor_current_a 같은 타겟 raw 컬럼이 없어 기준선 계산이 전부 skip된다.
        train_and_save_model(
            X_train_ae,
            model_name=system_name,
            target_dict=target_dict,
            df_reference=df_agg,
            run_id=run_id,
            git_sha=git_sha,
            figures_dir=run_figures_dir,
        )

        # 3. SHAP 아티팩트 저장 (frontend beeswarm 렌더용)
        # 입력이 바뀌어도 값은 변하지 않는 "정적 아티팩트"라 /predict 대신 별도 json으로 서빙.
        shap_targets_payload = {}
        n_features_per_target = {}
        for target_name, sv in shap_vals_dict.items():
            X_bg = X_bg_dict[target_name]
            sv_arr = np.asarray(sv)
            mean_abs = np.abs(sv_arr).mean(axis=0)
            order_idx = np.argsort(mean_abs)[::-1]
            features_list = list(X_bg.columns)
            shap_targets_payload[target_name] = {
                "features":       features_list,
                "mean_abs_shap":  mean_abs.tolist(),
                "feature_order":  [features_list[i] for i in order_idx],
                "shap_values":    sv_arr.tolist(),
                "feature_values": X_bg.values.tolist(),
            }
            n_features_per_target[target_name] = len(features_list)

        n_samples = int(next(iter(shap_vals_dict.values())).shape[0]) if shap_vals_dict else 0
        shap_payload = {
            "targets":      shap_targets_payload,
            "n_samples":    n_samples,
            "n_features":   n_features_per_target,
            "computed_at":  datetime.utcnow().isoformat() + "Z",
        }
        shap_path = os.path.join(project_root, "models", f"{system_name}_shap.json")
        with open(shap_path, "w") as f:
            json.dump(shap_payload, f)
        logger.info(f"💾 [{system_name.upper()}] SHAP 아티팩트 저장: {shap_path}")

    # --------------------------------------------------------------------------
    # [불변 스냅샷] 4개 도메인 학습이 모두 끝난 뒤, 라이브 폴더(models/)에 쌓인
    #   아티팩트 일습을 models/runs/<run_id>/ 로 복사해 박제한다.
    #   - models/ 는 서빙(inference_api)이 직접 읽는 곳이라 그대로 둔다(계약 불변).
    #   - runs/<run_id>/ 는 이 학습 시점의 박제본으로, 다음 재학습이 덮어쓰지 않는다.
    #   과거 A-3 사고(좋은 모델이 재학습에 소실)를 구조적으로 막는 장치다.
    # --------------------------------------------------------------------------
    models_dir = os.path.join(project_root, "models")

    # 도메인별 그래프를 한 장의 대조표로 묶어 run 폴더에서 한눈에 비교 가능하게 한다.
    if _VIZ_AVAILABLE and os.path.isdir(run_figures_dir):
        try:
            sheet = build_contact_sheet(run_figures_dir)
            if sheet:
                logger.info(f"[MAIN] 진단 대조표 생성: {sheet}")
        except Exception as e:
            logger.warning(f"[MAIN] 대조표 생성 실패(학습은 정상 완료): {e}")

    snapshot_run(
        models_dir,
        run_id,
        meta={"domains": list(subsystem_targets.keys()), "seed": 42},
        logger=logger,
    )

    total_end_time = time.time()
    t_min, t_sec = divmod(total_end_time - total_start_time, 60)
    logger.info(
        "모든 서브시스템(Motor, Hydraulic, Nutrient, Zone Drip)의 모델 학습이 성공적으로 종료되었습니다."
    )
    logger.info(
        f"전체 파이프라인 구동 완료 (총 소요 시간: {int(t_min)}분 {t_sec:.2f}초)"
    )
