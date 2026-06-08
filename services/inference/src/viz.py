# ==============================================================================
# viz.py — 모델 진단 시각화 자동 저장
# ==============================================================================
#
# [왜 이 파일이 생겼나]
#   성능 지표(F1·FAR)가 좋아도, "원하는 구간(실제 이상)에서 AE가 동작하고
#   원하지 않는 구간(정상·기동 스파이크)에서 동작하지 않는다"는 사실이 그래프로
#   보여야 비로소 모델이 의도대로 작동한다고 말할 수 있다. 따라서 이미지 저장은
#   평가의 일부다. 다만 조정할 옵션이 많아 이미지가 폭증하므로, 모든 그래프를
#   실험 식별자(run_id) 폴더에 결정적 파일명으로 자동 저장해 관리 부담을 없앤다.
#   배경·설계: docs/modeling/06_visualization_logging.md
#
# [이 모듈이 그리는 진단 그래프가 답하는 질문]
#   1. 각 threshold가 MSE 시계열에 올바로 적용됐는가.
#      특히 의도된 펌프 기동 스파이크가 threshold 산정을 부풀리지 않았는가
#      (기동 구간을 음영으로 표시 + "기동 제외 시 threshold"를 점선으로 병기해 비교).
#   2. MSE 분포가 한쪽으로 몰렸는가(정규분포 가정 위반 여부 — percentile 전환 근거).
#   3. 우리가 지정한 이상 구간부터 문제가 드러나는가(모델이 이상탐지 역할을 하는가).
#
# [의존성·실행]
#   matplotlib만 사용한다. 헤드리스에서도 동작하도록 Agg 백엔드를 강제하고,
#   화면 출력(plt.show) 대신 파일로 저장(savefig)한다. 대량 렌더는 무거운 작업이므로
#   학습/평가 스크립트 안에서 호출되며, 그 스크립트는 사용자가 직접 실행한다.
# ==============================================================================

import os
import matplotlib

matplotlib.use("Agg")  # 디스플레이 없는 환경에서도 저장되도록 (창을 띄우지 않음)
import matplotlib.pyplot as plt
import numpy as np


# 색상 팔레트 — 단계별로 일관되게 (히스토그램/시계열 공통)
_C_BASE = "#4C78A8"     # MSE 본선
_C_MEAN = "#7F7F7F"     # 평균
_C_CAUT = "#F1C40F"     # 주의(2σ)
_C_WARN = "#E67E22"     # 경고(3σ)
_C_CRIT = "#C0392B"     # 심각(6σ)
_C_STARTUP = "#95A5A6"  # 기동 구간 음영
_C_ANOM = "#C0392B"     # 이상 라벨 음영


def _sigma_thresholds(values, sigma_levels=(2, 3, 6)):
    """평균 + kσ 임계치를 dict로 반환. config 산정식과 동일(중복 의존 회피용 인라인)."""
    mu = float(np.mean(values))
    sd = float(np.std(values))
    c, w, cr = sigma_levels
    return {
        "mean": mu,
        "caution": mu + c * sd,
        "warning": mu + w * sd,
        "critical": mu + cr * sd,
    }


def _shade_spans(ax, mask, color, label):
    """
    bool 마스크(시간순)에서 True가 '연속'된 구간을 찾아 axvspan으로 음영 처리한다.
    여러 구간이 있어도 범례에는 한 번만 표시한다.

    [왜 구간 단위인가] 기동/이상은 점이 아니라 '구간'이다. 점으로 찍으면 가려져
    보이지 않으므로, 시작~끝을 띠로 칠해 "이 시간대"임을 한눈에 보이게 한다.
    """
    if mask is None:
        return
    mask = np.asarray(mask).astype(bool)
    if mask.sum() == 0:
        return
    # 연속 True 구간의 경계 탐지
    edges = np.diff(mask.astype(int))
    starts = list(np.where(edges == 1)[0] + 1)
    ends = list(np.where(edges == -1)[0] + 1)
    if mask[0]:
        starts = [0] + starts
    if mask[-1]:
        ends = ends + [len(mask)]
    first = True
    for s, e in zip(starts, ends):
        ax.axvspan(s, e, color=color, alpha=0.18, lw=0,
                   label=(label if first else None))
        first = False


def plot_threshold_diagnosis(mse_scores, thresholds, model_name, save_path,
                             startup_mask=None, anomaly_mask=None,
                             sigma_levels=(2, 3, 6), boundary_index=None,
                             boundary_label="train/eval", show_excl_startup=True):
    """
    도메인 1개의 핵심 진단 그래프(분포 + 시계열)를 한 장으로 저장한다.

    Args:
        mse_scores   : (N,) 시간순 복원오차(MSE) 배열.
        thresholds   : config에 저장된 실제 임계치 dict(mean/caution/warning/critical).
                       전체 학습 샘플 기준으로 산정된 '운영에 쓰이는' 값.
        model_name   : 도메인 이름(파일/제목용).
        save_path    : 저장할 png 경로.
        startup_mask : (N,) bool. 펌프 기동 구간 표시 + '기동 제외 시 threshold' 비교용.
        anomaly_mask : (N,) bool. 지정된 이상 구간 표시(평가 단계에서 anomaly_label로 전달).
        sigma_levels : 보조 threshold 계산용 σ 레벨(기본 2/3/6).
        boundary_index : 시계열에 세로선을 그을 위치(예: 학습/평가 경계 = 평가 시작 인덱스).
                         월1(정상 학습 구간)과 월2~3(이상 구간)의 경계를 표시해
                         "학습은 여기까지, 이후부터 이상이 드러나는가"를 보이게 한다.
        boundary_label : 그 세로선의 범례 라벨.
        show_excl_startup : '기동 제외 시 임계치' 점선 표시 여부. 학습 단계(정상 데이터)에서만
                            의미가 있으므로 평가 단계에서는 False로 끈다.

    [그래프 구성]
      왼쪽(분포): MSE 히스토그램(log y) + 실제 임계 3선 + 평균.
                  분포가 한쪽으로 길게 몰렸는지(꼬리)를 보고 percentile 전환 근거를 확인.
      오른쪽(시계열): MSE 라인 + 임계 3선(가로).
                  - 기동 구간(회색)·이상 구간(빨강) 음영.
                  - startup_mask가 있으면 '기동 제외 시 임계치'를 점선으로 병기 →
                    실제 임계선과 점선의 간격이 크면, 기동 스파이크가 threshold를
                    부풀리고 있다는 직접 증거.
                  - 이상 음영 위에서 MSE가 임계선을 넘으면 이상탐지가 동작하는 것.
    """
    mse_scores = np.asarray(mse_scores, dtype=float)
    t_mean = thresholds.get("mean")
    t_caut = thresholds["caution"]
    t_warn = thresholds["warning"]
    t_crit = thresholds["critical"]

    fig, (ax_hist, ax_ts) = plt.subplots(1, 2, figsize=(15, 5))

    # ----- 왼쪽: 분포 -----
    ax_hist.hist(mse_scores, bins=100, color=_C_BASE, alpha=0.75, edgecolor="white")
    ax_hist.set_yscale("log")
    if t_mean is not None:
        ax_hist.axvline(t_mean, color=_C_MEAN, linestyle=":", lw=1.2, label=f"Mean={t_mean:.4g}")
    ax_hist.axvline(t_caut, color=_C_CAUT, lw=1.8, label=f"Caution={t_caut:.4g}")
    ax_hist.axvline(t_warn, color=_C_WARN, lw=1.8, label=f"Warning={t_warn:.4g}")
    ax_hist.axvline(t_crit, color=_C_CRIT, lw=1.8, label=f"Critical={t_crit:.4g}")
    # 분포 쏠림(skew)을 수치로 주석 — 오른쪽으로 길수록 양수
    skew = _safe_skew(mse_scores)
    ax_hist.set_xlabel("Reconstruction MSE")
    ax_hist.set_ylabel("Count (log)")
    ax_hist.set_title(f"[{model_name.upper()}] MSE distribution (skew={skew:.2f})")
    ax_hist.legend(loc="upper right", fontsize=9)
    ax_hist.grid(True, alpha=0.3)

    # ----- 오른쪽: 시계열 -----
    ax_ts.plot(mse_scores, color=_C_BASE, lw=0.6, alpha=0.85)
    # 음영(구간) 먼저 깔고 그 위에 임계선
    _shade_spans(ax_ts, startup_mask, _C_STARTUP, "startup")
    _shade_spans(ax_ts, anomaly_mask, _C_ANOM, "anomaly")
    ax_ts.axhline(t_caut, color=_C_CAUT, lw=1.5, linestyle="--", label="Caution")
    ax_ts.axhline(t_warn, color=_C_WARN, lw=1.5, linestyle="--", label="Warning")
    ax_ts.axhline(t_crit, color=_C_CRIT, lw=1.5, linestyle="--", label="Critical")

    # '기동 제외 시 임계치' 병기 — 기동 스파이크가 threshold를 부풀렸는지 직접 비교.
    #   학습 단계(정상 데이터)에서만 의미가 있다. 평가 데이터는 이상값이 섞여 있어
    #   이 보조선이 이상값까지 반영하므로 show_excl_startup=False로 끈다.
    if show_excl_startup and startup_mask is not None:
        keep = ~np.asarray(startup_mask).astype(bool)
        if keep.sum() > 1:
            alt = _sigma_thresholds(mse_scores[keep], sigma_levels)
            ax_ts.axhline(alt["caution"], color=_C_CAUT, lw=1.0, linestyle=":",
                          alpha=0.9, label="Caution (excl. startup)")
            ax_ts.axhline(alt["critical"], color=_C_CRIT, lw=1.0, linestyle=":",
                          alpha=0.9, label="Critical (excl. startup)")

    # 학습/평가 경계(또는 임의 구간 경계) 세로선
    if boundary_index is not None:
        ax_ts.axvline(boundary_index, color="#2C3E50", lw=1.4, linestyle="-.",
                      alpha=0.9, label=boundary_label)

    ax_ts.set_xlabel("Sample index (time order)")
    ax_ts.set_ylabel("Reconstruction MSE")
    ax_ts.set_title(f"[{model_name.upper()}] MSE timeline & thresholds")
    ax_ts.legend(loc="upper right", fontsize=8, ncol=2)
    ax_ts.grid(True, alpha=0.3)

    fig.suptitle(f"AutoEncoder threshold diagnosis — {model_name}", fontsize=13, y=1.02)
    fig.tight_layout()
    _savefig(fig, save_path)
    return save_path


def plot_loss_curve(history, model_name, save_path):
    """
    학습 곡선(train/val loss)을 저장한다. 두 곡선이 겹치면 과적합 없이 일반화가 양호.

    Args:
        history : dict 또는 keras History. {'loss': [...], 'val_loss': [...]}.
    """
    hist = history.history if hasattr(history, "history") else history
    loss = hist.get("loss", [])
    val = hist.get("val_loss", [])

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(loss, color=_C_BASE, lw=1.8, label="train loss")
    if val:
        ax.plot(val, color=_C_WARN, lw=1.8, label="val loss")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("MSE loss")
    ax.set_title(f"[{model_name.upper()}] training curve")
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    _savefig(fig, save_path)
    return save_path


def build_contact_sheet(figures_dir, out_name="_contact_sheet.png", ncols=2):
    """
    figures_dir 안의 모든 png(대조표 자신 제외)를 격자 한 장으로 모은다.
    폴더를 일일이 열지 않고 run 하나의 모든 그래프를 한 화면에서 비교하기 위함.
    """
    pngs = sorted(
        f for f in os.listdir(figures_dir)
        if f.endswith(".png") and f != out_name
    )
    if not pngs:
        return None
    nrows = (len(pngs) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 8, nrows * 4.2))
    axes = np.array(axes).reshape(-1)
    for ax in axes:
        ax.axis("off")
    for ax, name in zip(axes, pngs):
        ax.imshow(plt.imread(os.path.join(figures_dir, name)))
        ax.set_title(name, fontsize=8)
    fig.tight_layout()
    out_path = os.path.join(figures_dir, out_name)
    _savefig(fig, out_path)
    return out_path


# ------------------------------------------------------------------------------
# 내부 헬퍼
# ------------------------------------------------------------------------------
def _savefig(fig, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)  # 메모리 누수 방지(대량 렌더 시 필수)


def _safe_skew(x):
    """표준 라이브러리만으로 3차 모멘트 기반 비대칭도 근사(scipy 미사용)."""
    x = np.asarray(x, dtype=float)
    mu = x.mean()
    sd = x.std()
    if sd == 0 or len(x) < 3:
        return 0.0
    return float(np.mean(((x - mu) / sd) ** 3))
