"""
PPT용 모델 출력 시각화 — 한 함수로 두 장짜리 그림 생성.

사용:
    from plot_model_outputs import plot_model_outputs

    result = plot_model_outputs(
        models_dir="/Users/jun/GitStudy/human_A/models",
        csv_path="/Users/jun/GitStudy/human_A/data/generated_data_from_dabin_0420.csv",
    )

출력:
    Figure 1 — 좌: EDA 정상 vs 이상 flow 단계 패턴, 우: SHAP Top 5 (4 도메인 합산)
    Figure 2 — 좌: Global Feature Importance, 우: 도메인별 F1 (anomaly_label 있을 때만)

라벨 컬럼(anomaly_label)이 CSV에 없으면 Figure 2 의 F1 패널은 자동으로 생략된다.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from typing import Optional

import joblib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_THIS_DIR, ".."))
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from preprocessing import step1_prepare_window_data  # noqa: E402


DEFAULT_DETECTION_NAMES = {
    "motor":     "모터 과전류·베어링 이상 탐지",
    "hydraulic": "배관 막힘·누수 탐지",
    "nutrient":  "양액 EC 제어 이상 탐지",
    "zone_drip": "점적핀 막힘 탐지",
}


def _load_models(models_dir: str) -> dict:
    """models_dir 에서 *_config.json 쌍을 모두 로드해 dict로 반환."""
    import tensorflow as tf

    out = {}
    for cfg_path in sorted(glob.glob(os.path.join(models_dir, "*_config.json"))):
        dom = os.path.basename(cfg_path).replace("_config.json", "")
        model_p = os.path.join(models_dir, f"{dom}_model.keras")
        scaler_p = os.path.join(models_dir, f"{dom}_scaler.pkl")
        if not (os.path.exists(model_p) and os.path.exists(scaler_p)):
            print(f"⚠ {dom}: model/scaler 누락 — 스킵")
            continue
        out[dom] = {
            "model":  tf.keras.models.load_model(model_p, compile=False),
            "scaler": joblib.load(scaler_p),
            "config": json.load(open(cfg_path, "r", encoding="utf-8")),
        }
    return out


def _align_features(df_agg: pd.DataFrame, features: list) -> np.ndarray:
    """학습 피처 순서대로 정렬, 누락 피처는 0으로 채움."""
    X = pd.DataFrame(index=df_agg.index, columns=features, dtype=float)
    for f in features:
        X[f] = df_agg[f].astype(float).values if f in df_agg.columns else 0.0
    return X.values


def _compute_shap_scores(
    models_data: dict,
    df_agg: pd.DataFrame,
    n_background: int,
    n_explain: int,
    seed: int = 42,
) -> dict:
    """4 도메인 SHAP mean|·| → 도메인 내 max 정규화 → 피처별 합산 반환."""
    import shap
    import tensorflow as tf

    rng = np.random.default_rng(seed)
    feat_score: dict = {}

    for dom, data in models_data.items():
        model  = data["model"]
        scaler = data["scaler"]
        features = data["config"]["features"]

        X_scaled = scaler.transform(_align_features(df_agg, features)).astype("float32")
        n = X_scaled.shape[0]
        bg  = X_scaled[rng.choice(n, size=min(n_background, n), replace=False)]
        exp = X_scaled[rng.choice(n, size=min(n_explain,    n), replace=False)]

        # AE 출력 → MSE 스칼라 래퍼 (SHAP 은 "이상 점수 기여도" 로 해석)
        inp   = tf.keras.Input(shape=(X_scaled.shape[1],), dtype="float32")
        recon = model(inp, training=False)
        mse_out = tf.keras.layers.Lambda(
            lambda xs: tf.reduce_mean(tf.square(xs[0] - xs[1]), axis=1, keepdims=True),
            output_shape=(1,),
        )([inp, recon])
        mse_model = tf.keras.Model(inp, mse_out)

        try:
            sv = shap.GradientExplainer(mse_model, bg).shap_values(exp)
            if isinstance(sv, list):
                sv = sv[0]
            sv = np.asarray(sv)
            if sv.ndim == 3 and sv.shape[-1] == 1:
                sv = np.squeeze(sv, axis=-1)
        except Exception as e:
            print(f"  ↳ [{dom}] GradientExplainer 실패({type(e).__name__}) → KernelExplainer fallback")
            def _f_mse(x, _m=model):
                r = _m.predict(np.asarray(x, dtype=np.float32), verbose=0)
                return np.mean((x - r) ** 2, axis=1)
            sv = np.asarray(
                shap.KernelExplainer(_f_mse, bg).shap_values(exp[:60], nsamples=60)
            )

        mean_abs = np.abs(sv).mean(axis=0)
        denom = max(float(mean_abs.max()), 1e-12)
        for f, v in zip(features, mean_abs / denom):
            feat_score[f] = feat_score.get(f, 0.0) + float(v)

    return feat_score


def _compute_global_importance(
    models_data: dict,
    df_agg: pd.DataFrame,
    eval_mask: np.ndarray,
) -> dict:
    """eval 구간에서 피처별 재구성 오차 평균 → 도메인 내 정규화 → 합산."""
    global_score: dict = {}
    for data in models_data.values():
        model, scaler = data["model"], data["scaler"]
        features = data["config"]["features"]

        X_scaled = scaler.transform(_align_features(df_agg, features)).astype("float32")
        X_eval = X_scaled[eval_mask]
        if len(X_eval) == 0:
            continue
        recon = model.predict(X_eval, batch_size=512, verbose=0)
        per_feat_err = np.mean((X_eval - recon) ** 2, axis=0)

        denom = max(float(per_feat_err.max()), 1e-12)
        for f, v in zip(features, per_feat_err / denom):
            global_score[f] = global_score.get(f, 0.0) + float(v)
    return global_score


def _compute_domain_f1(
    models_data: dict,
    df_agg: pd.DataFrame,
    eval_mask: np.ndarray,
    y_true: np.ndarray,
) -> dict:
    """도메인별 alarm_level >= 1 기준 F1 계산 (y_true 있을 때만)."""
    from sklearn.metrics import f1_score

    from inference_core import get_alarm_status  # 실제 inference와 동일한 판정

    out = {}
    yt = y_true[eval_mask]
    for dom, data in models_data.items():
        model, scaler = data["model"], data["scaler"]
        cfg = data["config"]
        features = cfg["features"]
        t_caut = float(cfg["threshold_caution"])
        t_warn = float(cfg["threshold_warning"])
        t_crit = float(cfg.get("threshold_critical", cfg.get("threshold_error")))

        X_scaled = scaler.transform(_align_features(df_agg, features)).astype("float32")
        recon = model.predict(X_scaled, batch_size=512, verbose=0)
        mse = np.mean((X_scaled - recon) ** 2, axis=1)
        levels = np.array(
            [get_alarm_status(float(m), t_caut, t_warn, t_crit)[0] for m in mse]
        )
        yp = (levels[eval_mask] >= 1).astype(int)
        out[dom] = float(f1_score(yt, yp, zero_division=0))
    return out


def _setup_korean_font() -> None:
    """플랫폼별 한글 폰트 자동 선택. 없으면 기본 폰트 유지."""
    import platform
    sysname = platform.system()
    candidates = {
        "Darwin":  ["AppleGothic", "Apple SD Gothic Neo"],
        "Windows": ["Malgun Gothic"],
        "Linux":   ["NanumGothic", "DejaVu Sans"],
    }.get(sysname, ["DejaVu Sans"])

    from matplotlib import font_manager
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for f in candidates:
        if f in installed:
            plt.rcParams["font.family"] = f
            break
    plt.rcParams["axes.unicode_minus"] = False


def plot_model_outputs(
    models_dir: str,
    csv_path: str,
    train_range: tuple = ("2026-03-01", "2026-03-31"),
    eval_range: tuple = ("2026-04-01", "2026-05-31"),
    window_method: str = "sliding",
    n_background: int = 60,
    n_explain: int = 150,
    flow_col: str = "flow_rate_l_min",
    detection_names: Optional[dict] = None,
    top_k: int = 5,
    show: bool = True,
) -> dict:
    """학습된 AE 모델 + CSV 로부터 PPT 용 두 장짜리 그림을 생성한다.

    Parameters
    ----------
    models_dir : str
        `{domain}_model.keras`, `_scaler.pkl`, `_config.json` 가 들어있는 폴더.
    csv_path : str
        timestamp 컬럼을 가진 원시 1분 센서 CSV.
    train_range, eval_range : (str, str)
        학습/평가 구간 경계 (ISO 날짜).
    window_method : "sliding" | "tumbling"
        preprocessing.step1_prepare_window_data 의 집계 방식.
    n_background, n_explain : int
        SHAP baseline / explain 샘플 수. 값 작으면 빠르지만 변동성 커짐.
    flow_col : str
        Figure 1 좌측에 쓸 flow 센서 컬럼명.
    detection_names : dict[str, str] | None
        도메인 → 한글 탐지 시나리오명. None 이면 기본값 사용.
    top_k : int
        Top Feature 바 개수.
    show : bool
        True 면 plt.show() 호출. False 면 figure 객체만 반환.

    Returns
    -------
    dict { fig1, fig2, shap_scores, global_scores, f1_scores, df_agg }
    """
    detection_names = detection_names or DEFAULT_DETECTION_NAMES
    _setup_korean_font()

    # `~/foo` 같은 홈 디렉터리 축약 경로 지원
    models_dir = os.path.expanduser(models_dir)
    csv_path   = os.path.expanduser(csv_path)

    # ── 1) 데이터 로드 + 전처리 ────────────────────────────────────────────
    print(f"📂 CSV 로드: {csv_path}")
    df_raw = pd.read_csv(csv_path)
    df_raw["timestamp"] = pd.to_datetime(df_raw["timestamp"])
    df_raw = df_raw.set_index("timestamp")

    target_cols = ["anomaly_label", "composite_z_score", "cleaning_event_flag"]
    target_cols = [c for c in target_cols if c in df_raw.columns]
    df_agg, _ = step1_prepare_window_data(
        df_raw, window_method=window_method, target_cols=target_cols or None
    )
    df_agg = df_agg.dropna()
    print(f"집계 완료: {df_agg.shape}")

    # ── 2) 모델 로드 ───────────────────────────────────────────────────────
    print(f"📦 모델 로드: {models_dir}")
    models_data = _load_models(models_dir)
    if not models_data:
        raise RuntimeError(f"models_dir 에 유효한 모델 아티팩트가 없음: {models_dir}")
    print(f"도메인 로드 완료: {list(models_data.keys())}")

    # ── 3) 구간 마스크 ─────────────────────────────────────────────────────
    idx = df_agg.index
    mask_train = (idx >= pd.Timestamp(train_range[0])) & (idx <= pd.Timestamp(train_range[1]))
    mask_eval  = (idx >= pd.Timestamp(eval_range[0]))  & (idx <= pd.Timestamp(eval_range[1]))

    # ── 4) Figure 1: EDA 단계 패턴 + SHAP Top K ──────────────────────────
    if flow_col not in df_agg.columns:
        raise KeyError(f"{flow_col} 이 df_agg 에 없음 (CSV 컬럼 확인 필요)")

    train_mean_flow = float(df_agg.loc[mask_train, flow_col].mean())
    eval_slice = df_agg.loc[mask_eval, [flow_col]].copy()
    if len(eval_slice) == 0:
        raise RuntimeError(f"eval_range {eval_range} 에 해당하는 데이터가 없음")
    eval_slice["bucket"] = pd.qcut(np.arange(len(eval_slice)), 5, labels=["T2","T3","T4","T5","T6"])
    eval_means = eval_slice.groupby("bucket", observed=True)[flow_col].mean().reindex(["T2","T3","T4","T5","T6"])

    x_axis = ["T1","T2","T3","T4","T5","T6"]
    normal_line   = [train_mean_flow] * 6
    clogging_line = [train_mean_flow] + eval_means.tolist()

    print("🔬 SHAP 계산 중...")
    shap_scores = _compute_shap_scores(models_data, df_agg, n_background, n_explain)
    top_shap = sorted(shap_scores.items(), key=lambda kv: -kv[1])[:top_k][::-1]
    shap_names  = [k for k, _ in top_shap]
    shap_values = [v for _, v in top_shap]

    fig1, (ax1l, ax1r) = plt.subplots(1, 2, figsize=(13, 4.3))
    ax1l.plot(x_axis, normal_line,   "o--", color="#888",   lw=1.5, ms=7, label="Normal Flow")
    ax1l.plot(x_axis, clogging_line, "o-",  color="#c92a2a", lw=2.5, ms=8, label="Clogging Flow")
    ax1l.set_title("📈 EDA: 정상 vs 이상 패턴 분석", fontsize=12, fontweight="bold")
    ax1l.set_ylabel(flow_col)
    ax1l.legend(loc="lower left", fontsize=9)
    ax1l.grid(True, alpha=0.3)

    ax1r.barh(shap_names, shap_values, color="#2b8a3e", alpha=0.9)
    ax1r.set_title(f"🌳 SHAP: 변수 기여도 Top {top_k} ({len(models_data)} 도메인 합산)",
                   fontsize=12, fontweight="bold")
    ax1r.set_xlabel("Normalized Mean |SHAP| (도메인 내 max=1 정규화 후 합산)")
    ax1r.grid(True, axis="x", alpha=0.3)
    for i, v in enumerate(shap_values):
        ax1r.text(v, i, f" {v:.3f}", va="center", fontsize=8)
    fig1.suptitle("EDA 및 SHAP 기반 핵심 인자 분석", fontsize=14, fontweight="bold", y=1.02)
    fig1.tight_layout()

    drop_pct = (clogging_line[-1] - train_mean_flow) / (train_mean_flow + 1e-12) * 100
    print(f"\n[Figure 1 요약]")
    print(f"  · flow 변화: {drop_pct:+.1f}% (T1 → T6)")
    print(f"  · SHAP Top{top_k}: {[k for k,_ in top_shap[::-1]]}")

    # ── 5) Figure 2: Global Feature Importance + 도메인별 F1 ──────────────
    print("🔬 Global feature importance 계산 중...")
    global_scores = _compute_global_importance(models_data, df_agg, mask_eval.values)
    top_global = sorted(global_scores.items(), key=lambda kv: -kv[1])[:top_k][::-1]
    g_names  = [k for k, _ in top_global]
    g_values = [v for _, v in top_global]

    # F1 계산 (label 있을 때만)
    f1_scores = {}
    has_label = "anomaly_label" in df_agg.columns
    if has_label:
        print("🔬 도메인별 F1 계산 중...")
        y_true = df_agg["anomaly_label"].astype(int).values
        f1_scores = _compute_domain_f1(models_data, df_agg, mask_eval.values, y_true)

    if has_label and f1_scores:
        fig2, (ax2l, ax2r) = plt.subplots(1, 2, figsize=(13, 4.6))
    else:
        fig2, ax2l = plt.subplots(1, 1, figsize=(7, 4.6))
        ax2r = None

    ax2l.barh(g_names, g_values, color="#3b5bdb", alpha=0.9)
    ax2l.set_title("🌳 전역 변수 중요도 (Global Feature Importance)",
                   fontsize=12, fontweight="bold")
    ax2l.set_xlabel(f"Normalized Importance ({len(models_data)} 도메인 합산)")
    ax2l.grid(True, axis="x", alpha=0.3)
    for i, v in enumerate(g_values):
        ax2l.text(v, i, f" {v:.3f}", va="center", fontsize=8)

    if ax2r is not None:
        det_rows = [(detection_names.get(d, d), f1, d) for d, f1 in f1_scores.items()]
        det_rows.sort(key=lambda r: r[1])
        ax2r.barh([r[0] for r in det_rows], [r[1] for r in det_rows],
                  color="#2b8a3e", alpha=0.9)
        ax2r.set_title("🔎 개별 이상 탐지 사례 (도메인별 F1)",
                       fontsize=12, fontweight="bold")
        ax2r.set_xlabel("Detection F1 (Caution 기준, eval 구간)")
        ax2r.set_xlim(0, 1.05)
        ax2r.grid(True, axis="x", alpha=0.3)
        for i, (_, v, _) in enumerate(det_rows):
            ax2r.text(v, i, f" {v:.3f}", va="center", fontsize=8)
        fig2.suptitle("XAI 기반 탐지 근거 시각화 (SHAP + F1)",
                      fontsize=14, fontweight="bold", y=1.02)
    else:
        fig2.suptitle("XAI 기반 탐지 근거 시각화 (SHAP) — anomaly_label 없음",
                      fontsize=14, fontweight="bold", y=1.02)
        print("\nℹ️  CSV 에 anomaly_label 이 없어 F1 패널은 생략됨. "
              "라벨 포함된 data/generated_test_data_0420.csv 로 다시 호출하면 F1 도 나옴.")
    fig2.tight_layout()

    print(f"\n[Figure 2 요약]")
    print(f"  · Global Top{top_k}: {[k for k,_ in top_global[::-1]]}")
    if f1_scores:
        best = max(f1_scores.items(), key=lambda kv: kv[1])
        print(f"  · 최고 F1: {best[0]} = {best[1]:.3f}")

    if show:
        plt.show()

    return {
        "fig1": fig1,
        "fig2": fig2,
        "shap_scores":   shap_scores,
        "global_scores": global_scores,
        "f1_scores":     f1_scores,
        "df_agg":        df_agg,
    }


if __name__ == "__main__":
    # CLI 사용 예:
    #   python plot_model_outputs.py <models_dir> <csv_path>
    if len(sys.argv) < 3:
        print("usage: python plot_model_outputs.py <models_dir> <csv_path>")
        sys.exit(1)
    plot_model_outputs(sys.argv[1], sys.argv[2])
