# src/inference_core.py
import numpy as np

from ko_labels import ko_alarm, ko_feature


def get_alarm_status(mse_score: float, t_caut: float, t_warn: float, t_crit: float):
    """MSE 점수를 바탕으로 4단계 알람 레벨과 라벨을 반환합니다."""
    if mse_score >= t_crit:
        return 3, "Critical 🔴"
    elif mse_score >= t_warn:
        return 2, "Warning 🟠"
    elif mse_score >= t_caut:
        return 1, "Caution 🔸"
    else:
        return 0, "Normal"


# 알람 점수(MSE)와 RCA 양쪽에서 제외할 "컨텍스트/상태" 피처.
# - 시간·상태·이벤트 피처는 현장 조치 대상이 아니며,
#   복원 오차가 커도 알람/원인 리포트로 띄워봐야 운영자가 할 수 있는 게 없음.
# - train.py 의 threshold 계산과 inference_api.py 의 실시간 MSE 계산이
#   이 단일 소스를 공유해야 "알람 근거 == 설명"이 일치한다.
# preprocessing.py의 time_cols + phase_cols 규약과 동일.
DEFAULT_CONTEXT_FEATURES = frozenset(
    {
        # 시간 인코딩 (cyclical / counter)
        "time_sin",
        "time_cos",
        "minute_of_day",
        # 펌프 상태 / 엣지 이벤트
        "pump_on",
        "pump_start_event",
        "pump_stop_event",
        # 기동/정지 경과시간 카운터
        "minutes_since_startup",
        "minutes_since_shutdown",
        # phase flag
        "is_startup_phase",
        "is_off_phase",
        # 운영 이벤트 플래그
        "cleaning_event_flag",
        # pH 2차 파생 플래그 (실제 원인은 mix_ph)
        "ph_instability_flag",
    }
)


def actionable_feature_mask(features, exclude=None) -> np.ndarray:
    """주어진 피처 리스트에서 '액션 가능한' 실센서 피처 위치의 boolean 마스크를 반환.

    DEFAULT_CONTEXT_FEATURES에 속한 피처는 False, 나머지는 True.
    모두 제외되는 극단 케이스는 호출자가 폴백 처리해야 한다 (all False 가능).
    """
    blocked = DEFAULT_CONTEXT_FEATURES if exclude is None else set(exclude)
    return np.array([f not in blocked for f in features], dtype=bool)


def calculate_rca(
    feature_errors: np.ndarray,
    features: list,
    top_n: int = 3,
    exclude_features=None,
):
    """피처별 복원 오차를 바탕으로 기여도(%) Top N 원인 분석 리포트를 생성합니다.

    exclude_features가 None이면 DEFAULT_CONTEXT_FEATURES를 사용해 시간·상태·이벤트
    피처를 제외합니다. 제외 후 남는 피처가 없으면(극단 케이스) 필터 없이 원본으로
    폴백합니다.
    """
    exclude = (
        DEFAULT_CONTEXT_FEATURES if exclude_features is None else set(exclude_features)
    )
    pairs = [
        (n, float(e)) for n, e in zip(features, feature_errors) if n not in exclude
    ]
    if not pairs:
        pairs = [(n, float(e)) for n, e in zip(features, feature_errors)]

    sum_err = sum(e for _, e in pairs)
    if sum_err <= 0:
        sum_err = 1e-10

    rca = sorted(
        [
            {
                "feature": n,
                "한글명": ko_feature(n),
                "contribution": round((e / sum_err) * 100, 1),
            }
            for n, e in pairs
        ],
        key=lambda x: x["contribution"],
        reverse=True,
    )[:]
    return rca


def build_feature_details(
    act_vals: list,
    exp_vals: list,
    features: list,
    feature_stds: dict,
    scaled_errors: "np.ndarray" = None,
    per_feature_thresholds: dict = None,
):
    """프론트엔드 시계열 차트 및 3시그마 밴드를 그리기 위한 상세 데이터를 생성합니다.

    feature_stds: {feature_name: std_value} 형태의 평탄 dict (train.py 저장 포맷).
    scaled_errors: (F,) 배열, 각 피처의 현재 스케일 공간 제곱오차 (선택사항).
    per_feature_thresholds: {feature_name: {caution/warning/critical}} dict (선택사항).
    """
    details = []
    for i, f_name in enumerate(features):
        act_val = float(act_vals[i])
        exp_val = float(exp_vals[i])

        # 저장된 std가 없으면 임시로 기대값의 5%를 1시그마로 사용
        std_val = float(feature_stds.get(f_name, exp_val * 0.05))

        entry = {
            "name": f_name,
            "한글명": ko_feature(f_name),
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

        # 🔬 피처별 threshold 및 현재 오차 추가 (선택사항)
        if scaled_errors is not None and per_feature_thresholds is not None:
            if f_name in per_feature_thresholds:
                entry["scaled_error"] = round(float(scaled_errors[i]), 8)
                entry["feature_thresholds"] = per_feature_thresholds[f_name]

                # 피처별 alarm level 판정 (도메인과 동일한 로직)
                err = float(scaled_errors[i])
                t_caut = per_feature_thresholds[f_name]["caution"]
                t_warn = per_feature_thresholds[f_name]["warning"]
                t_crit = per_feature_thresholds[f_name]["critical"]
                f_alarm_level, f_alarm_label = get_alarm_status(
                    err, t_caut, t_warn, t_crit
                )
                entry["feature_alarm"] = {
                    "level": f_alarm_level,
                    "label": f_alarm_label,
                    "한글": ko_alarm(f_alarm_label),
                }

        details.append(entry)
    return details


def build_sigma_reference_line(series) -> dict:
    """단일 시계열에 대해 평균 기준 sigma 라인을 계산합니다."""
    mean_val = float(series.mean())
    std_val = max(float(series.std()), 1e-6)

    return {
        "normal": round(mean_val, 4),
        "caution": {
            "lower": round(mean_val - (std_val * 1), 4),
            "upper": round(mean_val + (std_val * 1), 4),
        },
        "warning": {
            "lower": round(mean_val - (std_val * 2), 4),
            "upper": round(mean_val + (std_val * 2), 4),
        },
        "critical": {
            "lower": round(mean_val - (std_val * 3), 4),
            "upper": round(mean_val + (std_val * 3), 4),
        },
        "std": round(std_val, 4),
        "training_min": round(float(series.min()), 4),
        "training_max": round(float(series.max()), 4),
    }


def build_target_reference_profiles(df: "pd.DataFrame", target_dict: dict) -> dict:
    """타겟 기준 정상 샘플을 골라 관련 변수들의 sigma 라인을 계산합니다.

    규칙:
    - target 자체의 평균 ± 1σ 를 정상 구간(caution band)으로 사용
    - 그 정상 구간에 포함되는 행만 normal_subset 으로 간주
    - related features 는 normal_subset 위에서 mean ± 1/2/3σ 라인을 계산
    """
    profiles = {}

    for target_name, related_features in target_dict.items():
        if target_name not in df.columns:
            continue

        target_series = df[target_name].dropna()
        if target_series.empty:
            continue

        target_lines = build_sigma_reference_line(target_series)
        normal_mask = (df[target_name] >= target_lines["caution"]["lower"]) & (
            df[target_name] <= target_lines["caution"]["upper"]
        )
        normal_subset = df.loc[normal_mask]

        if normal_subset.empty:
            normal_subset = df

        related_profiles = {}
        for feature_name in related_features:
            if feature_name not in normal_subset.columns:
                continue
            feature_series = normal_subset[feature_name].dropna()
            if feature_series.empty:
                continue
            line = build_sigma_reference_line(feature_series)
            line["한글명"] = ko_feature(feature_name)
            related_profiles[feature_name] = line

        profiles[target_name] = {
            "한글명": ko_feature(target_name),
            "target_threshold_basis": "target_caution_band_1sigma",
            "target_lines": target_lines,
            "normal_sample_count": int(len(normal_subset)),
            "related_feature_lines": related_profiles,
        }

    return profiles
