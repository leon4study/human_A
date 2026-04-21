"""
테스트 CSV(`anomaly_label` 포함)로 학습된 AE 모델의 FN/FP를 정량 측정.

실행:
    cd /Users/jun/GitStudy/human_A/src
    python evaluate_test_metrics.py

출력:
    - 콘솔: 구간별(학습/평가) × cutoff별(level≥1/≥2/≥3) × 도메인별 precision/recall/F1
    - CSV: ../data/evaluation_outputs/ 에 혼동행렬 · FN/FP 타임스탬프 저장
"""
from __future__ import annotations

import glob
import json
import os
import sys

import joblib
import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score

from preprocessing import step1_prepare_window_data
from inference_core import get_alarm_status

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_CSV = os.path.join(PROJECT_ROOT, "data", "generated_test_data_0420.csv")
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
OUT_DIR = os.path.join(PROJECT_ROOT, "data", "evaluation_outputs")

TRAIN_RANGE = ("2026-03-01", "2026-03-31")
EVAL_RANGE = ("2026-04-01", "2026-05-31")

LEVEL_CUTOFFS = [1, 2, 3]  # 각각 "Caution 이상 = 이상", "Warning 이상", "Critical 이상"

# A-2: nutrient 도메인은 타겟(mix_ec 등)과 최종 학습 피처(time/pump_rpm/motor_temp)가 어긋나
# 5월 정지 시간대에 FP를 독점 발생시킴 (547/581 = 94%).
# A-3(feature_selection 재검토)로 근본 수정 전까지 overall voting에서 제외.
EXCLUDE_FROM_OVERALL = {"nutrient"}


def run_inference(df_agg: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """도메인별 배치 예측 → `{domain}_level` 컬럼 담은 DataFrame 반환."""
    config_files = glob.glob(os.path.join(MODELS_DIR, "*_config.json"))
    systems = sorted(os.path.basename(f).replace("_config.json", "") for f in config_files)

    rows = {dom: np.zeros(len(df_agg), dtype=int) for dom in systems}
    scores = {dom: np.zeros(len(df_agg), dtype=float) for dom in systems}
    loaded = []

    for dom in systems:
        model_p = os.path.join(MODELS_DIR, f"{dom}_model.keras")
        scaler_p = os.path.join(MODELS_DIR, f"{dom}_scaler.pkl")
        config_p = os.path.join(MODELS_DIR, f"{dom}_config.json")
        if not all(os.path.exists(p) for p in [model_p, scaler_p, config_p]):
            print(f"⚠️  {dom}: 아티팩트 누락 → 스킵")
            continue

        model = tf.keras.models.load_model(model_p)
        scaler = joblib.load(scaler_p)
        cfg = json.load(open(config_p, "r", encoding="utf-8"))
        features = cfg["features"]
        t_caut = float(cfg["threshold_caution"])
        t_warn = float(cfg["threshold_warning"])
        t_err = float(cfg.get("threshold_critical", cfg.get("threshold_error")))

        X = pd.DataFrame(index=df_agg.index, columns=features, dtype=float)
        for f in features:
            X[f] = df_agg[f].astype(float).values if f in df_agg.columns else 0.0

        X_scaled = scaler.transform(X)
        preds = model.predict(X_scaled, batch_size=512, verbose=0)
        mse = np.mean((X_scaled - preds) ** 2, axis=1)

        levels = np.array(
            [get_alarm_status(float(m), t_caut, t_warn, t_err)[0] for m in mse]
        )
        rows[dom] = levels
        scores[dom] = mse
        loaded.append(dom)
        print(f"✅ {dom}: N={len(df_agg)}, thr_caut={t_caut:.4f} / warn={t_warn:.4f} / err={t_err:.4f}")

    df = pd.DataFrame(index=df_agg.index)
    for dom in loaded:
        df[f"{dom}_level"] = rows[dom]
        df[f"{dom}_score"] = scores[dom]

    voting_domains = [d for d in loaded if d not in EXCLUDE_FROM_OVERALL]
    df["overall_alarm_level"] = df[[f"{d}_level" for d in voting_domains]].max(axis=1)
    if EXCLUDE_FROM_OVERALL & set(loaded):
        df["overall_alarm_level_with_nutrient"] = df[[f"{d}_level" for d in loaded]].max(axis=1)
        print(f"🚫 overall voting 제외 도메인: {sorted(EXCLUDE_FROM_OVERALL & set(loaded))}")
    return df, loaded


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, label: str) -> dict:
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    p = precision_score(y_true, y_pred, zero_division=0)
    r = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    total = len(y_true)
    pos = int(y_true.sum())
    return {
        "scope": label,
        "N": total,
        "positives": pos,
        "TP": int(tp),
        "FP": int(fp),
        "FN": int(fn),
        "TN": int(tn),
        "precision": round(p, 4),
        "recall": round(r, 4),
        "f1": round(f1, 4),
        "FAR": round(fp / max(tn + fp, 1), 4),  # False Alarm Rate
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"📂 CSV: {DATA_CSV}")
    df_raw = pd.read_csv(DATA_CSV)
    df_raw["timestamp"] = pd.to_datetime(df_raw["timestamp"])
    df_raw = df_raw.set_index("timestamp")
    print(f"1min raw: {df_raw.shape}")

    # anomaly_label / composite_z_score는 model_cols 화이트리스트에 없어서
    # create_modeling_features()에서 drop됨 → extra_cols(target_cols)로 보존 강제.
    df_agg, _ = step1_prepare_window_data(
        df_raw,
        window_method="tumbling",
        target_cols=["anomaly_label", "composite_z_score", "cleaning_event_flag"],
    )
    df_agg = df_agg.dropna()
    print(f"10min agg: {df_agg.shape}")

    if "anomaly_label" not in df_agg.columns:
        sys.exit("❌ df_agg에 anomaly_label 없음 — preprocessing passthrough 점검")

    y_true = df_agg["anomaly_label"].astype(int).values

    print("\n=== 도메인별 추론 실행 ===")
    df_pred, domains = run_inference(df_agg)

    # 평가 구간 분할
    idx = df_agg.index
    mask_train = (idx >= pd.Timestamp(TRAIN_RANGE[0])) & (idx <= pd.Timestamp(TRAIN_RANGE[1]))
    mask_eval = (idx >= pd.Timestamp(EVAL_RANGE[0])) & (idx <= pd.Timestamp(EVAL_RANGE[1]))

    print(f"\n라벨 분포 (10min 윈도우 기준)")
    print(f"  전체 anomaly 비율: {y_true.mean():.4f} ({int(y_true.sum())}/{len(y_true)})")
    print(f"  학습구간 anomaly 비율: {y_true[mask_train].mean():.4f}")
    print(f"  평가구간 anomaly 비율: {y_true[mask_eval].mean():.4f}")

    # === 구간 × cutoff × 도메인 조합 metrics ===
    metrics_rows = []
    for scope_name, mask in [("TRAIN", mask_train), ("EVAL", mask_eval), ("ALL", np.ones(len(y_true), dtype=bool))]:
        yt = y_true[mask]
        for cut in LEVEL_CUTOFFS:
            # Overall (nutrient 제외 A-2 적용)
            yp = (df_pred["overall_alarm_level"].values[mask] >= cut).astype(int)
            m = compute_metrics(yt, yp, f"{scope_name} / overall(no_nutrient) / level>={cut}")
            metrics_rows.append(m)
            # Overall (nutrient 포함, 비교용)
            if "overall_alarm_level_with_nutrient" in df_pred.columns:
                yp_w = (df_pred["overall_alarm_level_with_nutrient"].values[mask] >= cut).astype(int)
                m_w = compute_metrics(yt, yp_w, f"{scope_name} / overall(with_nutrient) / level>={cut}")
                metrics_rows.append(m_w)
            # Per-domain
            for dom in domains:
                yp_d = (df_pred[f"{dom}_level"].values[mask] >= cut).astype(int)
                m_d = compute_metrics(yt, yp_d, f"{scope_name} / {dom} / level>={cut}")
                metrics_rows.append(m_d)

    metrics_df = pd.DataFrame(metrics_rows)
    metrics_csv = os.path.join(OUT_DIR, "metrics_summary.csv")
    metrics_df.to_csv(metrics_csv, index=False, encoding="utf-8-sig")

    # === 콘솔 출력: overall만 표로 ===
    print("\n=== Overall metrics (any domain level ≥ cutoff vs anomaly_label) ===")
    overall = metrics_df[metrics_df["scope"].str.contains("overall")].copy()
    print(overall.to_string(index=False))

    # === 평가구간 도메인별 cutoff=1 메트릭 ===
    print("\n=== EVAL 구간 · 도메인별 (cutoff level>=1) ===")
    dom_table = metrics_df[
        metrics_df["scope"].str.startswith("EVAL /")
        & metrics_df["scope"].str.endswith("level>=1")
        & ~metrics_df["scope"].str.contains("overall")
    ]
    print(dom_table.to_string(index=False))

    # === FN / FP 타임스탬프 저장 (overall, cutoff=1, EVAL 기준) ===
    yp_overall = (df_pred["overall_alarm_level"].values >= 1).astype(int)
    fn_mask = mask_eval & (y_true == 1) & (yp_overall == 0)
    fp_mask = mask_eval & (y_true == 0) & (yp_overall == 1)

    fn_df = df_agg.loc[fn_mask, ["anomaly_label", "composite_z_score"]].copy()
    for dom in domains:
        fn_df[f"{dom}_level"] = df_pred.loc[fn_mask, f"{dom}_level"]
        fn_df[f"{dom}_score"] = df_pred.loc[fn_mask, f"{dom}_score"].round(6)
    fn_df.to_csv(os.path.join(OUT_DIR, "fn_eval_overall.csv"), encoding="utf-8-sig")

    fp_df = df_agg.loc[fp_mask, ["anomaly_label", "composite_z_score"]].copy()
    for dom in domains:
        fp_df[f"{dom}_level"] = df_pred.loc[fp_mask, f"{dom}_level"]
        fp_df[f"{dom}_score"] = df_pred.loc[fp_mask, f"{dom}_score"].round(6)
    fp_df.to_csv(os.path.join(OUT_DIR, "fp_eval_overall.csv"), encoding="utf-8-sig")

    print(f"\n💾 저장:")
    print(f"  - {metrics_csv}")
    print(f"  - {os.path.join(OUT_DIR, 'fn_eval_overall.csv')}  ({int(fn_mask.sum())}건)")
    print(f"  - {os.path.join(OUT_DIR, 'fp_eval_overall.csv')}  ({int(fp_mask.sum())}건)")


if __name__ == "__main__":
    main()
