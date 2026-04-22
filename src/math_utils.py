# src/math_utils.py
import numpy as np


def calculate_sigma_thresholds(mse_scores: np.ndarray, sigma_levels: tuple = (2, 4, 6)):
    """
    [옵션 A. 정석/Bottom-Up 방식]
    정상 데이터의 평균(Mean)에서 시그마를 더해 올라가는 방식입니다.
    """
    mse_mean = np.mean(mse_scores)
    mse_std = np.std(mse_scores)

    return {
        "caution": float(mse_mean + (sigma_levels[0] * mse_std)),
        "warning": float(mse_mean + (sigma_levels[1] * mse_std)),
        "critical": float(
            mse_mean + (sigma_levels[2] * mse_std)
        ),  # error -> critical 변경
        "mean": float(mse_mean),
        "std": float(mse_std),
    }


def calculate_topdown_sigma_thresholds(
    mse_scores: np.ndarray, top_sigma: int = 6, step: int = 3
):
    """
    [옵션 B. 주니어님 맞춤형/Top-Down 방식]
    최고 위험선(Critical)을 먼저 잡고, 지정한 간격(Step)만큼 시그마를 빼서 내려오는 방식입니다.
    - Critical = Mean + (top_sigma * Std)
    - Warning  = Critical - (step * Std)
    - Caution  = Warning - (step * Std)
    """
    mse_mean = np.mean(mse_scores)
    mse_std = np.std(mse_scores)

    t_cri = mse_mean + (top_sigma * mse_std)
    t_warn = t_cri - (step * mse_std)
    t_caut = t_warn - (step * mse_std)

    return {
        "caution": float(t_caut),
        "warning": float(t_warn),
        "critical": float(t_cri),
        "mean": float(mse_mean),
        "std": float(mse_std),
    }
