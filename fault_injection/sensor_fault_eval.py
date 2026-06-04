"""
sensor_fault_eval.py — 센서고장(단일) vs 진짜고장(다중) 판별 실험.

docs/modeling/10 §6. 강사 원칙을 데이터로 검증한다:
  "모든 값이 함께 요동치면 진짜 고장, 센서 하나만 튀면 센서 문제."

정상 데이터로 학습한 AutoEncoder는 단일 센서가 크게 튀어도 off-manifold라 총 MSE가 올라가
알람이 뜰 수 있다. 따라서 '총 MSE' 만으로는 진짜고장과 센서글리치를 구분하지 못한다.
구분은 per-feature 재구성 오차의 '퍼짐'으로 한다.

지표(윈도우별):
  - total MSE       : 알람이 뜨는가(임계값 대비).
  - concentration   : max_f e_f / sum_f e_f. 1에 가까울수록 한 피처에 오차가 집중(센서 문제).
  - n_active        : 정상대비 per-feature 오차가 큰 피처 수. 적으면 국소(센서), 많으면 광범위(진짜).

대비군:
  - clean   : 고장 없음(대조 기준).
  - sensor  : 단일 센서(discharge_pressure_kpa)에 drift/spike/stuck.
  - clog    : faulty_testset_v1 의 실제 하류 막힘(다중 센서 동반).

실행:
    cd fault_injection && python sensor_fault_eval.py
"""
import os
import sys
import glob
import json

import joblib
import numpy as np
import pandas as pd
import tensorflow as tf

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(PROJECT, "src")
sys.path.insert(0, SRC)

from preprocessing import step1_prepare_window_data          # noqa: E402
from sensor_faults import apply_sensor_fault                 # noqa: E402

MODELS_DIR = os.path.join(PROJECT, "services", "inference", "models")
CLEAN_CSV = os.path.join(PROJECT, "data", "generated_data_from_dabin_0420.csv")
FAULTY_CSV = os.path.join(PROJECT, "data", "faulty_testset_v1.csv")

DOMAIN = "hydraulic"                 # 실제 막힘 대비군이 있는 도메인
TARGET_SENSOR = "discharge_pressure_kpa"   # 단일 센서 결함 타깃
BASELINE_ROWS = 43200               # 월1(정상) 30일
FAULT_START = 20000                 # 결함 주입 시작 행(데이터 중반, 단일 지점)
FAULT_LEN = 1440                    # 24시간 지속(10분 윈도우 ~144개)


def load_domain(dom):
    """도메인 모델/스케일러/피처/임계값 로드."""
    cfg = json.load(open(os.path.join(MODELS_DIR, f"{dom}_config.json"), encoding="utf-8"))
    model = tf.keras.models.load_model(os.path.join(MODELS_DIR, f"{dom}_model.keras"))
    scaler = joblib.load(os.path.join(MODELS_DIR, f"{dom}_scaler.pkl"))
    thr = float(cfg["threshold_caution"])
    return model, scaler, cfg["features"], thr


def per_feature_error(df_agg, model, scaler, features):
    """스케일 공간의 per-feature 제곱오차 행렬 (N, F) 와 total MSE (N,) 반환."""
    X = pd.DataFrame(index=df_agg.index, columns=features, dtype=float)
    for f in features:
        X[f] = df_agg[f].astype(float).values if f in df_agg.columns else 0.0
    Xs = scaler.transform(X)
    preds = model.predict(Xs, batch_size=512, verbose=0)
    err = (Xs - preds) ** 2          # (N, F)
    mse = err.mean(axis=1)           # (N,)
    return err, mse


def window(df_raw):
    """raw → 10분 tumbling 집계(anomaly_label 보존)."""
    da, _ = step1_prepare_window_data(
        df_raw, window_method="tumbling", target_cols=["anomaly_label"]
    )
    return da.dropna()


def make_scenario(clean_raw, mode):
    """clean 복사본에 단일 센서 결함 1건 주입 + anomaly_label 부여."""
    faulty, lab = apply_sensor_fault(
        clean_raw, TARGET_SENSOR, mode, start_idx=FAULT_START, length=FAULT_LEN, magnitude=6.0
    )
    faulty = faulty.copy()
    faulty["anomaly_label"] = lab["anomaly_label"].to_numpy()
    return faulty


def summarize(name, err, mse, thr, fault_mask, active_thr):
    """결함 구간 윈도우의 판별 지표 집계."""
    e = err[fault_mask]
    m = mse[fault_mask]
    if len(m) == 0:
        return None
    fired = (m >= thr).mean()
    conc = (e.max(axis=1) / (e.sum(axis=1) + 1e-12)).mean()
    n_active = (e > active_thr).sum(axis=1).mean()
    return {
        "scenario": name, "n_win": len(m), "alarm_rate": fired,
        "mse_mean": m.mean(), "concentration": conc, "n_active": n_active,
    }


def main():
    print(f"도메인={DOMAIN}, 단일센서 타깃={TARGET_SENSOR}\n")
    model, scaler, features, thr = load_domain(DOMAIN)
    F = len(features)

    # 1) clean baseline (대조 기준 + per-feature 정상 오차 분포)
    clean_raw = pd.read_csv(CLEAN_CSV, nrows=BASELINE_ROWS)
    clean_raw["timestamp"] = pd.to_datetime(clean_raw["timestamp"])
    clean_raw = clean_raw.set_index("timestamp")
    clean_raw["anomaly_label"] = 0

    da_clean = window(clean_raw)
    err_clean, mse_clean = per_feature_error(da_clean, model, scaler, features)
    # per-feature 정상 밴드: 피처별 mean+3*std → 이를 넘으면 'active'
    active_thr = err_clean.mean(axis=0) + 3.0 * err_clean.std(axis=0)

    # clean에서의 결함 구간(주입 안 했지만 같은 시간대) = 대조군
    fault_win_clean = da_clean["anomaly_label"].to_numpy() > 0 if "anomaly_label" in da_clean else None

    rows = []
    # clean 자체를 대조로(같은 시간대 윈도우 전체)
    rows.append(summarize("clean(대조)", err_clean, mse_clean,
                          thr, np.ones(len(mse_clean), dtype=bool), active_thr))

    # 2) 센서고장 3종
    for mode in ("drift", "spike", "stuck"):
        raw = make_scenario(clean_raw.drop(columns=["anomaly_label"]).copy(), mode)
        da = window(raw)
        err, mse = per_feature_error(da, model, scaler, features)
        fmask = da["anomaly_label"].to_numpy() > 0
        rows.append(summarize(f"sensor:{mode}", err, mse, thr, fmask, active_thr))

    # 3) 진짜 막힘(다중 센서) — faulty_testset_v1
    fr = pd.read_csv(FAULTY_CSV)
    fr["timestamp"] = pd.to_datetime(fr["timestamp"])
    fr = fr.set_index("timestamp")
    da_f = window(fr)
    err_f, mse_f = per_feature_error(da_f, model, scaler, features)
    fmask_f = da_f["anomaly_label"].to_numpy() > 0
    rows.append(summarize("clog(진짜·다중)", err_f, mse_f, thr, fmask_f, active_thr))

    # 4) 출력
    rows = [r for r in rows if r]
    print(f"피처 수 F={F}, caution 임계값={thr:.5f}\n")
    print(f"  {'시나리오':<16}{'윈도우':>6}{'알람률':>8}{'MSE평균':>11}{'집중도':>8}{'활성피처':>9}")
    for r in rows:
        print(f"  {r['scenario']:<16}{r['n_win']:>6}{r['alarm_rate']:>8.2f}"
              f"{r['mse_mean']:>11.5f}{r['concentration']:>8.2f}{r['n_active']:>9.1f}")

    print("\n해석:")
    print("  - 집중도 1에 가까움 + 활성피처 적음 → 단일 센서 문제(국소).")
    print(f"  - 집중도 낮음(~{1.0/F:.2f}=균등) + 활성피처 많음 → 진짜 고장(광범위 동반 변동).")
    print("  - 총 MSE/알람만 보면 둘 다 뜰 수 있으나, 집중도·활성피처가 둘을 가른다.")


if __name__ == "__main__":
    main()
