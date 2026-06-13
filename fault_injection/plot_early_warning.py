"""
plot_early_warning.py — 막힘 에피소드별 '전조가 어느 단계(주의/경고/치명)까지, 얼마나 일찍'
잡히는지를 lead-time 표 + 그래프로 보여준다.

[답하는 질문]
"전조를 미리 잡아 '경고(Warning)' 수준까지 값이 나오나?" → 각 막힘 에피소드에서 책임 도메인의
이상점수가 고장 시점 전에 caution(주의)·warning(경고)·critical(치명) 임계선을 언제 넘는지(=각
단계 lead-time)를 잰다. warning 도달 lead가 양수면 '경고를 사전에 띄운다'는 뜻.

[그래프] 에피소드마다: 책임 도메인 이상점수 곡선 + 임계 3선(주의/경고/치명) + 고장 진행 구간 음영
+ 고장 시점 세로선. x축 = 고장까지 남은 시간(h). 점수가 고장 전에 선들을 넘어 올라가는 게 보이면
'전조를 사전에 잡는다'의 직접 증거다.

[책임 도메인] voting 도메인(nutrient 제외) 중 그 구간에서 점수/임계 비가 가장 큰(=가장 세게 반응한)
도메인을 그 막힘의 책임 도메인으로 본다.

실행:
    cd fault_injection && python plot_early_warning.py
"""
import os
import sys

import numpy as np
import pandas as pd

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT, "src"))

from evaluate_test_metrics import run_inference                         # noqa: E402
from operating_point_eval import window, FAULTY_CSV, EXCLUDE_FROM_OVERALL  # noqa: E402

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
# 한글 라벨용 폰트(맥OS). 없으면 기본 폰트로 폴백(라벨이 깨질 수 있으나 그래프는 정상).
for _f in ("AppleGothic", "Apple SD Gothic Neo", "NanumGothic"):
    try:
        plt.rcParams["font.family"] = _f
        break
    except Exception:
        continue
plt.rcParams["axes.unicode_minus"] = False

OUT_PNG = os.path.join(PROJECT, "data", "evaluation_outputs", "early_warning_episodes.png")


def build_episodes(fr):
    """fault_id별 [시작·고장시점·유형] (고장시점 있는 막힘만)."""
    eps = []
    for fid in sorted(int(x) for x in fr.loc[fr["fault_id"] >= 0, "fault_id"].unique()):
        sub = fr[fr["fault_id"] == fid]
        ft = pd.to_datetime(sub["failure_time"], errors="coerce").dropna()
        if len(ft):
            mode = str(sub["fault_mode"].dropna().iloc[0]) if "fault_mode" in sub else "?"
            eps.append({"fid": fid, "start": sub.index.min(),
                        "failure": ft.iloc[0], "mode": mode})
    return eps


def main():
    fr = pd.read_csv(FAULTY_CSV)
    fr["timestamp"] = pd.to_datetime(fr["timestamp"])
    fr = fr.set_index("timestamp")
    da = window(fr)

    df_pred, domains, thr_map = run_inference(da)           # serve 동일: 점수·임계·voting·기동band
    voting = [d for d in domains if d not in EXCLUDE_FROM_OVERALL]
    eps = build_episodes(fr)
    idx = da.index

    # ── 에피소드별 책임 도메인 + 단계별 lead-time ───────────────────────────────────
    rows = []
    for e in eps:
        seg = (idx >= e["start"]) & (idx <= e["failure"])
        # 책임 도메인 = 그 구간에서 점수/caution 비가 최대(가장 세게 반응)
        best_dom, best_ratio = None, -1.0
        for d in voting:
            s = df_pred[f"{d}_score"].to_numpy()
            caut = thr_map[d]["caution"]
            r = float((s[seg] / caut).max()) if seg.any() and caut > 0 else 0.0
            if r > best_ratio:
                best_dom, best_ratio = d, r
        s = df_pred[f"{best_dom}_score"].to_numpy()
        t = thr_map[best_dom]

        def lead(level_thr):
            """그 구간에서 점수가 level_thr를 처음 넘은 시점부터 고장까지 시간(h). 못 넘으면 None."""
            cross = seg & (s >= level_thr)
            if cross.any():
                return (e["failure"] - idx[cross].min()).total_seconds() / 3600.0
            return None

        rows.append({
            "fid": e["fid"], "mode": e["mode"].split("_")[0], "dom": best_dom,
            "lead_caut": lead(t["caution"]), "lead_warn": lead(t["warning"]),
            "lead_crit": lead(t["critical"]),
        })

    # ── 표 출력 ─────────────────────────────────────────────────────────────────────
    print("=== 에피소드별 단계 도달 lead-time (고장 N시간 전 그 단계 도달) ===")
    print(f"  {'#':>2} {'유형':<10}{'책임도메인':<11}{'주의lead':>9}{'경고lead':>9}{'치명lead':>9}")
    def fmt(v):
        return f"{v:.1f}h" if v is not None else "  -"
    n_warn = 0
    for r in rows:
        if r["lead_warn"] is not None:
            n_warn += 1
        print(f"  {r['fid']:>2} {r['mode']:<10}{r['dom']:<11}"
              f"{fmt(r['lead_caut']):>9}{fmt(r['lead_warn']):>9}{fmt(r['lead_crit']):>9}")
    print(f"\n  >> '경고(Warning)'를 고장 전에 도달한 막힘: {n_warn}/{len(rows)}")
    print("     (경고lead가 양수면 = 경고 수준 알람을 고장보다 그만큼 일찍 띄웠다는 뜻)")

    # ── 그래프: 에피소드마다 책임 도메인 점수 + 임계 3선 + 고장 진행 음영 ───────────────
    n = len(eps)
    ncol = 3
    nrow = int(np.ceil(n / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(ncol * 4.2, nrow * 2.8), squeeze=False)
    for k, (e, r) in enumerate(zip(eps, rows)):
        ax = axes[k // ncol][k % ncol]
        dom = r["dom"]
        s = df_pred[f"{dom}_score"].to_numpy()
        t = thr_map[dom]
        # x = 고장까지 남은 시간(h), 음수=고장 전. 시작 2h 전 ~ 고장 1h 후만 확대.
        hrs = (idx - e["failure"]).total_seconds() / 3600.0
        view = (idx >= e["start"] - pd.Timedelta(hours=2)) & (idx <= e["failure"] + pd.Timedelta(hours=1))
        ax.plot(hrs[view], s[view], color="#1f3b73", lw=1.3, label="이상점수")
        # 고장 점수가 임계의 수십~수백 배까지 치솟아 임계선이 바닥에 깔리므로 log 스케일로 본다.
        ax.set_yscale("log")
        # 임계 3선
        ax.axhline(t["caution"], color="#f0a500", ls="--", lw=0.9)
        ax.axhline(t["warning"], color="#e8590c", ls="--", lw=0.9)
        ax.axhline(t["critical"], color="#c92a2a", ls="--", lw=0.9)
        # 고장 진행 구간 음영 + 고장 시점
        ax.axvspan((e["start"] - e["failure"]).total_seconds() / 3600.0, 0,
                   color="red", alpha=0.06)
        ax.axvline(0, color="red", lw=1.0)
        ax.set_title(f"#{e['fid']} {r['mode']} ({dom}) · 경고 {fmt(r['lead_warn'])} 전",
                     fontsize=9)
        ax.set_xlabel("고장까지 남은 시간(h)", fontsize=8)
        ax.tick_params(labelsize=7)
    # 빈 칸 숨김
    for k in range(n, nrow * ncol):
        axes[k // ncol][k % ncol].axis("off")
    fig.suptitle("막힘 에피소드별 전조 감지 — 이상점수가 고장 전에 임계선(주의/경고/치명)을 넘는다",
                 fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    fig.savefig(OUT_PNG, dpi=120)
    print(f"\n[plot] 저장: {OUT_PNG}")


if __name__ == "__main__":
    main()