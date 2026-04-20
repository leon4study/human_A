# src/inference_core.py
import numpy as np


def get_alarm_status(mse_score: float, t_caut: float, t_warn: float, t_err: float):
    """MSE 점수를 바탕으로 4단계 알람 레벨과 라벨을 반환합니다."""
    if mse_score >= t_err:
        return 3, "Error 🔴"
    elif mse_score >= t_warn:
        return 2, "Warning 🟠"
    elif mse_score >= t_caut:
        return 1, "Caution 🔸"
    else:
        return 0, "Normal"


def calculate_rca(feature_errors: np.ndarray, features: list, top_n: int = 3):
    """피처별 복원 오차를 바탕으로 기여도(%) Top N 원인 분석 리포트를 생성합니다."""
    sum_err = np.sum(feature_errors) if np.sum(feature_errors) > 0 else 1e-10
    rca = sorted(
        [
            {"feature": n, "contribution": round((float(e) / sum_err) * 100, 1)}
            for n, e in zip(features, feature_errors)
        ],
        key=lambda x: x["contribution"],
        reverse=True,
    )[:top_n]
    return rca


def build_feature_details(
    act_vals: list, exp_vals: list, features: list, feature_stds: dict
):
    """프론트엔드 시계열 차트 및 3시그마 밴드를 그리기 위한 상세 데이터를 생성합니다.

    feature_stds: {feature_name: std_value} 형태의 평탄 dict (train.py 저장 포맷).
    """
    details = []
    for i, f_name in enumerate(features):
        act_val = float(act_vals[i])
        exp_val = float(exp_vals[i])

        # 저장된 std가 없으면 임시로 기대값의 5%를 1시그마로 사용
        std_val = float(feature_stds.get(f_name, exp_val * 0.05))

        details.append(
            {
                "name": f_name,
                "actual_value": round(act_val, 4),
                "expected_value": round(exp_val, 4),
                "bands": {
                    "caution_upper": round(exp_val + (std_val * 1), 4),
                    "caution_lower": round(exp_val - (std_val * 1), 4),
                    "warning_upper": round(exp_val + (std_val * 2), 4),
                    "warning_lower": round(exp_val - (std_val * 2), 4),
                    "critical_upper": round(exp_val + (std_val * 3), 4),
                    "critical_lower": round(exp_val - (std_val * 3), 4),
                },
            }
        )
    return details
