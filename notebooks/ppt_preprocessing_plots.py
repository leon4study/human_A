"""
PPT 슬라이드 `데이터 전처리 및 도메인 기반 보정 로직` 용 플롯 생성 스크립트.

데이터:  data/generated_data_from_dabin_0420.csv  (90일, 1분 단위)
모델:    models/*.keras + *_scaler.pkl  (motor / hydraulic / nutrient / zone_drip)

실행:   python notebooks/ppt_preprocessing_plots.py
결과:   notebooks/ppt_plots/  에 PNG 4장 저장
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from preprocessing import (  # noqa: E402
    filter_active_periods,
    create_modeling_features,
    step1_prepare_window_data,
    step2_clean_and_drop_collinear_dynamic,
)

DATA_PATH = ROOT / "data" / "generated_data_from_dabin_0420.csv"
MODELS_DIR = ROOT / "models"
OUT_DIR = ROOT / "notebooks" / "ppt_plots"
OUT_DIR.mkdir(exist_ok=True, parents=True)

plt.rcParams["font.family"] = "AppleGothic"
plt.rcParams["axes.unicode_minus"] = False
sns.set_style("whitegrid")


def load_data() -> pd.DataFrame:
    print(f"[1/5] 데이터 로드: {DATA_PATH}")
    df = pd.read_csv(DATA_PATH, encoding="utf-8-sig")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()

    # lights_on / pump_on / valve_on 컬럼이 없으면 휴리스틱으로 생성
    if "lights_on" not in df.columns:
        df["lights_on"] = ((df.index.hour >= 6) & (df.index.hour < 20)).astype(int)
    if "pump_on" not in df.columns:
        df["pump_on"] = (df["flow_rate_l_min"] > 0.1).astype(int)
    for z in (1, 2, 3):
        col = f"zone{z}_valve_on"
        if col not in df.columns:
            df[col] = (df[f"zone{z}_flow_l_min"] > 0.05).astype(int)
    return df


# ─────────────────────────────────────────────────────────────────
# STEP 01 — 유효 구간 필터링 & flow_drop_rate 도메인 보정 전/후
# ─────────────────────────────────────────────────────────────────
def plot_step01(df_raw: pd.DataFrame) -> None:
    print("[2/5] STEP 01 플롯: 유효 구간 필터링 + flow_drop_rate 보정")

    # 3일치만 뽑아서 시각화 (가독성)
    sample = df_raw.loc[df_raw.index[0] : df_raw.index[0] + pd.Timedelta(days=3)]
    filtered = filter_active_periods(sample)

    fig, axes = plt.subplots(2, 1, figsize=(12, 6), sharex=False)

    # (a) 원본 유량 vs 유효 구간만 마킹
    ax = axes[0]
    ax.plot(sample.index, sample["flow_rate_l_min"],
            color="#bbbbbb", linewidth=0.8, label="원본 (야간·대기 포함)")
    ax.plot(filtered.index, filtered["flow_rate_l_min"],
            color="#2F6FEB", linewidth=1.0, label="유효 구간만 (lights_on ∧ active)")
    ax.set_title("(a) 유효 구간 필터링: 야간/대기 시간 제거로 노이즈 절감")
    ax.set_ylabel("flow_rate (L/min)")
    ax.legend(loc="upper right")

    # (b) flow_drop_rate 3단계 게이트 전/후
    df_feat, _ = create_modeling_features(sample)
    # 보정 없는 naive 계산 (버그 재현용)
    eps = 1e-6
    naive = (
        (df_feat["flow_baseline_l_min"] - df_feat["flow_rate_l_min"])
        / (df_feat["flow_baseline_l_min"] + eps)
    ).replace([np.inf, -np.inf], np.nan)

    ax = axes[1]
    ax.plot(df_feat.index, naive,
            color="#E55B5B", linewidth=0.7, alpha=0.7,
            label="Naive (분모 발산 → 수천만 단위 튐)")
    ax.plot(df_feat.index, df_feat["flow_drop_rate"],
            color="#2FB56C", linewidth=1.2,
            label="3단계 게이트 보정: [0,1] 클리핑")
    ax.set_ylim(-0.2, 1.2)
    ax.set_title("(b) flow_drop_rate 도메인 보정 전/후 (Phase A 3차 버그픽스)")
    ax.set_ylabel("flow_drop_rate")
    ax.legend(loc="upper right")

    fig.tight_layout()
    out = OUT_DIR / "step01_noise_filter.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"      → 저장: {out}")


# ─────────────────────────────────────────────────────────────────
# STEP 02 — 다중공선성 제거 전/후 상관 히트맵
# ─────────────────────────────────────────────────────────────────
def plot_step02(df_raw: pd.DataFrame) -> pd.DataFrame:
    print("[3/5] STEP 02 플롯: 다중공선성 제거 전/후")

    # 연산 줄이려고 첫 14일만 사용
    sample = df_raw.loc[df_raw.index[0] : df_raw.index[0] + pd.Timedelta(days=14)]
    df_agg, _ = step1_prepare_window_data(sample, window_method="tumbling")

    before_cols = df_agg.select_dtypes(include=[np.number]).columns.tolist()
    df_clean = step2_clean_and_drop_collinear_dynamic(df_agg, corr_threshold=0.85)
    after_cols = df_clean.select_dtypes(include=[np.number]).columns.tolist()

    corr_before = df_agg[before_cols].corr().abs()
    corr_after = df_clean[after_cols].corr().abs()

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    sns.heatmap(corr_before, cmap="rocket_r", vmin=0, vmax=1,
                ax=axes[0], cbar=False, xticklabels=False, yticklabels=False)
    axes[0].set_title(f"(a) 제거 전: {len(before_cols)} features\n"
                      f"상관계수 > 0.85 쌍 다수")

    sns.heatmap(corr_after, cmap="rocket_r", vmin=0, vmax=1,
                ax=axes[1], cbar=True, xticklabels=False, yticklabels=False)
    axes[1].set_title(f"(b) 제거 후: {len(after_cols)} features\n"
                      f"동적 제거 + whitelist 보호")

    fig.suptitle("상관계수 0.85 임계 동적 다중공선성 제거", y=1.02, fontsize=13)
    fig.tight_layout()
    out = OUT_DIR / "step02_collinearity.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"      → 저장: {out}  (before={len(before_cols)}, after={len(after_cols)})")
    return df_clean


# ─────────────────────────────────────────────────────────────────
# STEP 03 — MinMax 정규화 전/후 분포 (저장된 scaler 사용)
# ─────────────────────────────────────────────────────────────────
def plot_step03(df_raw: pd.DataFrame) -> None:
    print("[4/5] STEP 03 플롯: MinMax 정규화 전/후 분포")

    # 각 도메인 scaler를 하나씩 로드해 domain별 대표 피처 하나씩 시각화
    domains = ["motor", "hydraulic", "nutrient", "zone_drip"]

    fig, axes = plt.subplots(2, 4, figsize=(16, 7))
    for i, domain in enumerate(domains):
        scaler_path = MODELS_DIR / f"{domain}_scaler.pkl"
        config_path = MODELS_DIR / f"{domain}_config.json"
        if not scaler_path.exists() or not config_path.exists():
            print(f"      ! {domain}: scaler/config 없음, 스킵")
            continue

        scaler = joblib.load(scaler_path)
        # scaler가 기억하는 feature 이름 (sklearn 1.x)
        feat_names = list(getattr(scaler, "feature_names_in_", []))
        if not feat_names:
            continue

        # raw에서 가진 공통 컬럼만 가져오기
        avail = [c for c in feat_names if c in df_raw.columns]
        if not avail:
            print(f"      ! {domain}: 원본 CSV에 매칭 피처 없음, 스킵")
            continue

        # 각 도메인 대표 피처 1개를 일부러 골라서 보여주기
        picker = {
            "motor": "motor_power_kw",
            "hydraulic": "discharge_pressure_kpa",
            "nutrient": "mix_ec_ds_m",
            "zone_drip": "zone1_flow_l_min",
        }
        target = picker.get(domain) if picker.get(domain) in avail else avail[0]

        raw_vals = df_raw[target].dropna().values
        # scaler.transform은 전체 feature 필요 → target 컬럼의 min/max만 수동 MinMax
        idx = feat_names.index(target)
        lo = scaler.data_min_[idx]
        hi = scaler.data_max_[idx]
        scaled = np.clip((raw_vals - lo) / (hi - lo + 1e-12), 0, 1)

        ax_top = axes[0, i]
        ax_bot = axes[1, i]
        ax_top.hist(raw_vals, bins=60, color="#E59D5B", alpha=0.85)
        ax_top.set_title(f"{domain}\n{target} (원본)")
        ax_top.set_xlabel("")

        ax_bot.hist(scaled, bins=60, color="#2F6FEB", alpha=0.85)
        ax_bot.set_title(f"{target} (MinMax [0,1])")
        ax_bot.set_xlim(-0.02, 1.02)

    fig.suptitle("STEP 03: MinMax [0, 1] 정규화 (저장된 scaler 아티팩트 사용)",
                 y=1.00, fontsize=13)
    fig.tight_layout()
    out = OUT_DIR / "step03_minmax.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"      → 저장: {out}")


# ─────────────────────────────────────────────────────────────────
# 요약 — 파이프라인 피처 수 감소 흐름
# ─────────────────────────────────────────────────────────────────
def plot_summary(df_raw: pd.DataFrame) -> None:
    print("[5/5] 요약 플롯: 파이프라인 단계별 피처 수 감소")

    sample = df_raw.loc[df_raw.index[0] : df_raw.index[0] + pd.Timedelta(days=7)]

    n_raw = len(df_raw.select_dtypes(include=[np.number]).columns)
    df_feat, _ = create_modeling_features(sample)
    n_feat = len(df_feat.select_dtypes(include=[np.number]).columns)
    df_agg, _ = step1_prepare_window_data(sample, window_method="tumbling")
    n_agg = len(df_agg.select_dtypes(include=[np.number]).columns)
    df_clean = step2_clean_and_drop_collinear_dynamic(df_agg, corr_threshold=0.85)
    n_clean = len(df_clean.select_dtypes(include=[np.number]).columns)

    stages = ["원본 센서", "+ 도메인 파생", "+ 윈도우 집계", "다중공선성 제거 후"]
    counts = [n_raw, n_feat, n_agg, n_clean]
    colors = ["#9AA5B1", "#E59D5B", "#F2C94C", "#2FB56C"]

    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(stages, counts, color=colors, edgecolor="black", linewidth=0.6)
    for b, c in zip(bars, counts):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 1,
                str(c), ha="center", fontsize=12, fontweight="bold")
    ax.set_ylabel("피처 수")
    ax.set_title("전처리 파이프라인 단계별 피처 수 흐름")
    fig.tight_layout()
    out = OUT_DIR / "summary_feature_counts.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"      → 저장: {out}  ({stages} = {counts})")


def main() -> None:
    df_raw = load_data()
    print(f"      shape={df_raw.shape}, range={df_raw.index.min()} ~ {df_raw.index.max()}")

    plot_step01(df_raw)
    plot_step02(df_raw)
    plot_step03(df_raw)
    plot_summary(df_raw)

    print(f"\n✅ 완료! PPT 삽입용 PNG 4장: {OUT_DIR}")


if __name__ == "__main__":
    main()
