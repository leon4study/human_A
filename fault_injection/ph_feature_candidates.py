"""
ph_feature_candidates.py — ph_trend_30(diff) 대신 넣을 'pH 불안정성' 후보 피처가 얌전한지(외삽
안 터지는지) 비교한다. 나쁜 피처를 또 넣는 실수를 막으려 꼬리·외삽을 먼저 본다.

[후보] mix_ph(레벨)·pid_error_ph(설정점 편차)는 이미 얌전하다(첨도 -1.3, 스케일 0.96). 추가로
'pH가 흔들린다'를 잡고 싶을 때:
  - ph_trend_30  : 현재(=rolling 평균의 diff). 문제아(첨도 135, 스케일 4.18).
  - ph_std_30    : mix_ph의 30창 표준편차. '얼마나 흔들리나'(diff보다 안정적이어야).
  - ph_range_30  : mix_ph 30창 (최대-최소). 변동폭.
  - ph_abs_dev   : |mix_ph - mix_target_ph|. 설정점에서 얼마나 벗어났나(레벨편차).

[판정] 첨도 낮음 + 스케일위치(P99.9)가 1 근처/이하 = 외삽 안 터짐 = 좋은 후보.

실행:
    python fault_injection/ph_feature_candidates.py
"""
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import kurtosis

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT, "src"))

from preprocessing import step1_prepare_window_data  # noqa: E402

TRAIN_CSV = os.path.join(PROJECT, "data", "smartfarm_normal_train_v5.csv")
HOLD_CSV = os.path.join(PROJECT, "data", "faulty_testset_v2.csv")


def windowed(csv, nrows=None):
    df = pd.read_csv(csv, nrows=nrows); df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp")
    if "anomaly_label" not in df:
        df["anomaly_label"] = 0
    da, _ = step1_prepare_window_data(df, window_method="tumbling", target_cols=["anomaly_label"])
    return da.dropna()


def add_candidates(da):
    """윈도우된 mix_ph로 후보 불안정성 피처 계산(빠른 viability 체크용)."""
    out = pd.DataFrame(index=da.index)
    out["ph_trend_30"] = da["ph_trend_30"] if "ph_trend_30" in da else da["mix_ph"].diff().fillna(0)
    out["ph_std_30"] = da["mix_ph"].rolling(30, min_periods=1).std().fillna(0)
    out["ph_range_30"] = (da["mix_ph"].rolling(30, min_periods=1).max()
                          - da["mix_ph"].rolling(30, min_periods=1).min()).fillna(0)
    if "mix_target_ph" in da:
        out["ph_abs_dev"] = (da["mix_ph"] - da["mix_target_ph"]).abs()
    out["pid_error_ph"] = da["pid_error_ph"] if "pid_error_ph" in da else 0.0
    return out


def main():
    tr = add_candidates(windowed(TRAIN_CSV))
    ho_da = windowed(HOLD_CSV)
    ho = add_candidates(ho_da)
    normal = (ho_da["anomaly_label"].to_numpy() <= 0.5)   # 정상 윈도우만(외삽은 정상서 봐야 FP 원인)

    print("=== pH 불안정성 후보 피처 꼬리/외삽 (held-out 정상 vs 학습) ===")
    print(f"  {'피처':<16}{'학습max':>11}{'held max':>11}{'held/학습':>10}{'첨도':>9}{'스케일P99.9':>12}  판정")
    for c in tr.columns:
        if c not in ho:
            continue
        tv, hv = tr[c].to_numpy(), ho[c].to_numpy()[normal]
        tmin, tmax = np.min(tv), np.max(tv)
        span = (tmax - tmin) if tmax > tmin else 1e-12
        scaled_p999 = float(np.percentile(np.abs((hv - tmin) / span), 99.9))
        kurt = float(kurtosis(hv))
        ratio = float(np.max(np.abs(hv)) / (abs(tmax) + 1e-12))
        ok = "좋음(얌전)" if (kurt < 5 and scaled_p999 < 1.5) else "나쁨(외삽)"
        print(f"  {c:<16}{tmax:>11.4f}{np.max(hv):>11.4f}{ratio:>10.2f}{kurt:>9.1f}{scaled_p999:>12.2f}  {ok}")

    print("\n해석:")
    print("  - '좋음': 첨도<5 + 스케일P99.9<1.5 → 외삽 안 터짐 → ph_trend_30 대체 후보로 적합.")
    print("  - ph_std_30/ph_range_30이 좋으면: diff 대신 '변동성'으로 pH 불안정을 얌전하게 잡을 수 있음.")
    print("  - 전부 mix_ph·pid_error_ph로 충분하면(Q2 검출 유지): 굳이 추가 안 하고 제거만 해도 됨.")


if __name__ == "__main__":
    main()