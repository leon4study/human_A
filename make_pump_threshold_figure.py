from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def get_analysis_home() -> Path:
    """스크립트를 어디서 실행하든 human_A 작업 폴더를 찾습니다."""
    here = Path(__file__).resolve().parent
    if (here / "src").exists():
        return here
    if (Path.cwd() / "src").exists():
        return Path.cwd()
    if (Path.cwd() / "human_A" / "src").exists():
        return Path.cwd() / "human_A"
    return here


ANALYSIS_HOME = get_analysis_home()
INPUT_PATH = ANALYSIS_HOME / "src" / "selected_smartfarm.csv"
OUTPUT_PATH = ANALYSIS_HOME / "pump_rpm_threshold_rationale.png"


def main() -> None:
    # 한국어 라벨이 깨지지 않도록 Windows 기본 글꼴을 우선 사용합니다.
    plt.rcParams["font.family"] = ["Malgun Gothic", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    df = pd.read_csv(INPUT_PATH, parse_dates=["timestamp"]).sort_values("timestamp")

    rpm_mask = df["pump_rpm"] > 100
    flow_mask = df["flow_rate_l_min"] > 1.0
    start_mask = rpm_mask.astype(int).diff().fillna(0).eq(1)

    starts = df.loc[start_mask, ["timestamp", "pump_rpm", "flow_rate_l_min"]].copy()
    flow_missed_starts = starts["flow_rate_l_min"] <= 1.0

    low_rpm = df.loc[df["pump_rpm"] <= 400, "pump_rpm"]
    gap_count = int(((df["pump_rpm"] > 10) & (df["pump_rpm"] <= 160)).sum())
    mismatch_count = int((rpm_mask & ~flow_mask).sum())

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), constrained_layout=True)

    # 왼쪽: 저회전 구간 분포를 확대해 threshold가 빈 구간 안에 있음을 보여줍니다.
    axes[0].hist(
        low_rpm,
        bins=np.arange(0, 401, 2),
        color="#9ecae1",
        edgecolor="white",
        linewidth=0.4,
    )
    axes[0].set_yscale("log")
    axes[0].axvspan(10, 160, color="#fdd0a2", alpha=0.45, label="관측 비어 있는 구간 (10~160 rpm)")
    axes[0].axvline(100, color="#d62728", linestyle="--", linewidth=2, label="선택 기준: pump_rpm > 100")
    axes[0].axvspan(
        starts["pump_rpm"].min(),
        starts["pump_rpm"].max(),
        color="#74c476",
        alpha=0.30,
        label="실제 시작 rpm 범위",
    )
    axes[0].set_xlim(0, 400)
    axes[0].set_xlabel("pump_rpm (0~400 확대)")
    axes[0].set_ylabel("행 수 (log scale)")
    axes[0].set_title("저회전 구간 분포: idle drift와 실제 시작 구간의 분리")
    axes[0].text(
        0.98,
        0.95,
        f"10~160 rpm 관측치: {gap_count}개\n시작 rpm 범위: {starts['pump_rpm'].min():.1f}~{starts['pump_rpm'].max():.1f}",
        transform=axes[0].transAxes,
        ha="right",
        va="top",
        bbox={"boxstyle": "round,pad=0.4", "facecolor": "white", "alpha": 0.9},
    )
    axes[0].legend(loc="lower right", fontsize=9)

    # 오른쪽: 시작 시점에서 rpm 기준은 잡지만 flow 기준은 놓치는 점들을 표시합니다.
    axes[1].scatter(
        starts.loc[~flow_missed_starts, "pump_rpm"],
        starts.loc[~flow_missed_starts, "flow_rate_l_min"],
        s=42,
        color="#3182bd",
        alpha=0.75,
        label="flow > 1.0인 시작 시점",
    )
    axes[1].scatter(
        starts.loc[flow_missed_starts, "pump_rpm"],
        starts.loc[flow_missed_starts, "flow_rate_l_min"],
        s=60,
        color="#d62728",
        alpha=0.95,
        label=f"flow 기준이 놓치는 시작 시점 (n={int(flow_missed_starts.sum())})",
    )
    axes[1].axvline(100, color="#d62728", linestyle="--", linewidth=2, label="pump_rpm cutoff")
    axes[1].axhline(1.0, color="#636363", linestyle=":", linewidth=2, label="flow cutoff = 1.0")
    axes[1].set_xlim(175, 186)
    axes[1].set_ylim(0.85, 2.45)
    axes[1].set_xlabel("이벤트 시작 시점의 pump_rpm")
    axes[1].set_ylabel("이벤트 시작 시점의 flow_rate_l_min")
    axes[1].set_title("유량 기준이 일부 시작 시점을 놓치는 이유")
    axes[1].text(
        0.02,
        0.95,
        f"총 시작 시점: {len(starts)}개\nrpm>100 & flow<=1.0 불일치: {mismatch_count}개",
        transform=axes[1].transAxes,
        ha="left",
        va="top",
        bbox={"boxstyle": "round,pad=0.4", "facecolor": "white", "alpha": 0.9},
    )
    axes[1].legend(loc="lower right", fontsize=9)

    fig.suptitle("`pump_rpm > 100` 기준의 시각적 근거", fontsize=15, fontweight="bold")
    fig.savefig(OUTPUT_PATH, dpi=180, bbox_inches="tight")
    plt.close(fig)

    print(f"저장 완료: {OUTPUT_PATH.resolve()}")


if __name__ == "__main__":
    main()
