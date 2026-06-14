"""
ph_trend_clip_sim.py — ph_trend_30 스케일 외삽(artifact)을 '클리핑'으로 고치면
trim 없이도 FP가 잡히고 + 진짜 검출은 안 깎이는지 오프라인으로 시뮬레이션한다.

[배경] ph_trend_30은 학습 범위가 매우 좁은데(MinMax [-0.00228, 0.00239]) held-out 꼬리값이
그 범위를 벗어나 스케일값이 3.9까지 외삽된다(ph_trend_scale_diagnosis.py 확인). 그 한 피처의
복원오차가 폭발해 nutrient 헛알람(FP)의 99%를 만든다. Phase P는 이를 trim(상위1 제외)으로 가렸다.

[이 시뮬의 질문]
  Q1. 스케일값을 [0,1]로 '클리핑'하면(= 학습 도메인 안으로 강제, 재학습 불필요) ph_trend 폭발이
      사라지나? (스케일 최대·복원오차)
  Q2. 그러면 trim 없이도 nutrient FP가 잡히나? (정상 윈도우 점수 분포)
  Q3. 클리핑이 '진짜 신호'까지 깎지는 않나? (nutrient 막힘 구간 점수 — 검출 유지 확인)
      ※ 클리핑은 양날: 진짜 고장이 피처를 [0,1] 밖으로 밀어도 잘리므로 검출이 떨어질 수 있다.
         그래서 FP뿐 아니라 검출도 반드시 같이 본다.

[비교 변형] (점수 = scoring 피처 복원오차 집계)
  A. 현재(trim=1, clip 없음)   — 출고 상태
  B. trim 없음, clip 없음       — 망가진 baseline(FP 문제 재현)
  C. trim 없음, clip            — 제안 수정(클리핑이 trim을 대체하나?)
  D. trim=1 + clip              — 둘 다(보수적)

판정은 임계값 의존을 피하려 '정상 P99.5 vs 막힘 중앙값'의 분리도로 본다.
정상 P99.5(운영점) << 막힘 중앙값이면 = 낮은 FP + 검출 유지.

실행:
    python fault_injection/ph_trend_clip_sim.py
"""
import os
import sys
import json

import joblib
import numpy as np
import pandas as pd
import tensorflow as tf

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT, "src"))

from operating_point_eval import startup_mask_of, FAULTY_CSV, MODELS_DIR          # noqa: E402
from preprocessing import step1_prepare_window_data                              # noqa: E402
from inference_core import reconstruction_score                                   # noqa: E402

DOM = "nutrient"
PH = "ph_trend_30"


def score_of(sq, smask, trim):
    """scoring 피처 제곱오차에서 trim 적용한 윈도우 점수(N,) — inference_core와 동일 집계."""
    return reconstruction_score(sq, smask, trim_top=trim)


def main():
    cfg = json.load(open(os.path.join(MODELS_DIR, f"{DOM}_config.json"), encoding="utf-8"))
    model = tf.keras.models.load_model(os.path.join(MODELS_DIR, f"{DOM}_model.keras"))
    scaler = joblib.load(os.path.join(MODELS_DIR, f"{DOM}_scaler.pkl"))
    features = cfg["features"]
    caution = float(cfg["threshold_caution"])
    ph_idx = features.index(PH)
    scoring = cfg.get("scoring_features") or features
    smask = np.array([f in set(scoring) for f in features], dtype=bool)

    # held-out v2 → tumbling 윈도우.
    # window()는 anomaly_label만 실어 fault_mode가 누락된다(검출 측정 불가). 그래서
    # 'nutrient 고장 플래그'를 숫자(nut_flag)로 만들어 target_cols로 같이 집계한다.
    fr = pd.read_csv(FAULTY_CSV); fr["timestamp"] = pd.to_datetime(fr["timestamp"])
    fr = fr.set_index("timestamp")
    fr["nut_flag"] = fr["fault_mode"].astype(str).str.contains("nutrient").astype(float)
    da, _ = step1_prepare_window_data(
        fr, window_method="tumbling", target_cols=["anomaly_label", "nut_flag"]
    )
    da = da.dropna()
    X = pd.DataFrame(index=da.index, columns=features, dtype=float)
    for f in features:
        X[f] = da[f].astype(float).values if f in da.columns else 0.0
    Xs = scaler.transform(X)
    Xs_clip = np.clip(Xs, 0.0, 1.0)          # 학습 도메인 [0,1]로 강제(외삽 차단)

    # 마스크: 정상(비기동) vs nutrient 막힘 구간(윈도우 평균 nut_flag>0 = 그 윈도우에 nutrient 고장 포함)
    y = (da["anomaly_label"].to_numpy() > 0.5).astype(int)
    su = startup_mask_of(da)
    normal = (y == 0) & (~su)
    nut_fault = (y == 1) & (da["nut_flag"].to_numpy() > 0.0)

    # 두 입력(clip 전/후)으로 추론 → 제곱오차
    def predict_sq(Xin):
        pred = model.predict(Xin, batch_size=512, verbose=0)
        return (Xin - pred) ** 2
    sq_raw = predict_sq(Xs)
    sq_clip = predict_sq(Xs_clip)

    # ── Q1. ph_trend 스케일·복원오차: clip 전/후 ────────────────────────────────────
    print("=== Q1. ph_trend 스케일/복원오차 (clip 전 → 후) ===")
    print(f"  스케일값 최대(정상): {Xs[normal, ph_idx].max():.3f} → {Xs_clip[normal, ph_idx].max():.3f}")
    print(f"  ph 복원오차 P99(정상): {np.percentile(sq_raw[normal, ph_idx], 99):.4f} "
          f"→ {np.percentile(sq_clip[normal, ph_idx], 99):.4f}")
    print(f"  ph 복원오차 최대(정상): {sq_raw[normal, ph_idx].max():.4f} "
          f"→ {sq_clip[normal, ph_idx].max():.4f}")

    # ── Q2·Q3. 점수 분리도: 변형별 정상 P99.5(운영점) vs nutrient 막힘 중앙값 ─────────
    print("\n=== Q2·Q3. nutrient 점수 분리도 (정상 P99.5=운영점 vs 막힘 중앙값) ===")
    print(f"  caution 임계(참고)={caution:.5f},  정상 {int(normal.sum())} / nutrient막힘 {int(nut_fault.sum())} 윈도우\n")
    print(f"  {'변형':<22}{'정상P99.5':>11}{'정상최대':>11}{'막힘중앙':>11}{'FP율@caution':>13}{'검출율@caution':>14}")
    variants = [
        ("A 현재(trim1,no-clip)", sq_raw, 1),
        ("B no-trim,no-clip",      sq_raw, 0),
        ("C no-trim,CLIP",         sq_clip, 0),
        ("D trim1+CLIP",           sq_clip, 1),
    ]
    for name, sq, trim in variants:
        s = score_of(sq, smask, trim)
        n_p995 = float(np.percentile(s[normal], 99.5)) if normal.any() else float("nan")
        n_max = float(s[normal].max()) if normal.any() else float("nan")
        f_med = float(np.median(s[nut_fault])) if nut_fault.any() else float("nan")
        fp = float((s[normal] >= caution).mean()) if normal.any() else float("nan")
        det = float((s[nut_fault] >= caution).mean()) if nut_fault.any() else float("nan")
        print(f"  {name:<22}{n_p995:>11.5f}{n_max:>11.5f}{f_med:>11.5f}{fp:>12.1%}{det:>14.1%}")

    print("\n해석:")
    print("  - Q1: clip 후 스케일 최대가 1.0로, ph 복원오차 폭발이 줄면 → 외삽 artifact가 클리핑으로 제거됨.")
    print("  - Q2: C(no-trim,CLIP)의 정상 P99.5/FP율이 A(현재)와 비슷하면 → 클리핑이 trim을 대체 가능.")
    print("  - Q3: C의 막힘 중앙값/검출율이 A와 비슷하면 → 클리핑이 진짜 신호를 안 깎음(검출 유지).")
    print("        C의 막힘 중앙값/검출이 크게 떨어지면 → 클리핑이 진짜도 깎음(검출 손실) → 클리핑 부적합.")


if __name__ == "__main__":
    main()