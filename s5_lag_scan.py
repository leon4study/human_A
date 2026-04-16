from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.outliers_influence import variance_inflation_factor


# S5는 아직 DW가 낮은 타깃만 다시 봅니다.
DEFAULT_S5_TARGETS = [
    "motor_current_a",
    "wire_to_water_efficiency",
    "mix_ph",
    "mix_ec_ds_m",
]

# 1분 간격 데이터이므로 lag 숫자는 그대로 분 단위로 읽으면 됩니다.
DEFAULT_LAG_STEPS = [1, 3, 5, 10]

# family 이름은 CSV에도 그대로 남으므로, 노트북에서 variant 문자열을 읽을 때 재사용합니다.
DEFAULT_FAMILY_ORDER = [
    "s5_base",
    "s5_predlag_only",
    "s5_current_plus_predlag",
    "s5_current_plus_targetlag",
    "s5_current_plus_predlag_targetlag",
]

VERDICT_PRIORITY = {
    "강한 후보": 0,
    "동학 후보(계수 해석 주의)": 1,
    "부분 개선": 2,
    "조건 미달": 3,
    "비권장": 4,
    "기준 모델": 5,
}


def compute_vif_table(X: pd.DataFrame) -> Dict[str, float]:
    """설명변수별 VIF를 계산합니다."""
    if X.shape[1] == 0:
        return {}
    if X.shape[1] == 1:
        return {X.columns[0]: 1.0}

    values = X.astype(float).values
    return {
        column: float(variance_inflation_factor(values, idx))
        for idx, column in enumerate(X.columns)
    }


def build_quality_flags(r2: float, dw: float, max_vif: float) -> str:
    """적합 결과를 한 줄 경고 문구로 요약합니다."""
    flags: List[str] = []
    if dw < 1.0:
        flags.append("잔차 자기상관 심함")
    elif dw < 1.5:
        flags.append("잔차 자기상관 주의")

    if max_vif > 30:
        flags.append("다중공선성 매우 큼")
    elif max_vif > 10:
        flags.append("다중공선성 큼")

    if r2 > 0.95 and dw < 0.5:
        flags.append("추세 또는 상태전이 주도 적합 의심")

    return " | ".join(flags) if flags else "특이 경고 없음"


def build_target_note(target: str, target_notes: Optional[Dict[str, str]] = None) -> str:
    """타깃별 해석 메모를 반환합니다."""
    target_notes = target_notes or {}
    return target_notes.get(target, "물리적 연결과 운전 정책 영향을 함께 확인해야 합니다.")


def build_s5_design(
    df: pd.DataFrame,
    target: str,
    predictors: Sequence[str],
    family: str,
    lag_steps: int,
) -> Tuple[pd.DataFrame, List[str]]:
    """S5 family 정의에 맞는 설계행렬을 만듭니다."""
    design = pd.DataFrame(index=df.index)
    design[target] = df[target]
    x_cols: List[str] = []

    if family in {"s5_base", "s5_current_plus_predlag", "s5_current_plus_targetlag", "s5_current_plus_predlag_targetlag"}:
        for col in predictors:
            design[col] = df[col]
            x_cols.append(col)

    if family in {"s5_predlag_only", "s5_current_plus_predlag", "s5_current_plus_predlag_targetlag"}:
        for col in predictors:
            lag_col = f"{col}_lag_{lag_steps}"
            design[lag_col] = df[col].shift(lag_steps)
            x_cols.append(lag_col)

    if family in {"s5_current_plus_targetlag", "s5_current_plus_predlag_targetlag"}:
        target_lag_col = f"{target}_lag_{lag_steps}"
        design[target_lag_col] = df[target].shift(lag_steps)
        x_cols.append(target_lag_col)

    return design.dropna(), x_cols


def fit_ols_from_design(
    design: pd.DataFrame,
    target: str,
    x_cols: Sequence[str],
    tag: str,
    sample_scope: str,
    target_notes: Optional[Dict[str, str]] = None,
    hac_lags: int = 20,
) -> Optional[Dict[str, object]]:
    """이미 만든 설계행렬로 HAC OLS를 적합합니다."""
    if len(design) < 100:
        return None

    X = sm.add_constant(design[list(x_cols)], has_constant="add")
    res = sm.OLS(design[target], X).fit(cov_type="HAC", cov_kwds={"maxlags": hac_lags})
    dw = sm.stats.stattools.durbin_watson(res.resid)
    jb_stat, jb_p, _, _ = sm.stats.stattools.jarque_bera(res.resid)
    vif = compute_vif_table(design[list(x_cols)])
    max_vif = float(max(vif.values())) if vif else np.nan

    return {
        "target": target,
        "variant": tag,
        "sample_scope": sample_scope,
        "cov_type": f"HAC(maxlags={hac_lags})",
        "N": int(res.nobs),
        "R2": float(res.rsquared),
        "AdjR2": float(res.rsquared_adj),
        "AIC": float(res.aic),
        "BIC": float(res.bic),
        "DW": float(dw),
        "JB_p": float(jb_p),
        "JB_stat": float(jb_stat),
        "max_vif": max_vif,
        "quality_flags": build_quality_flags(float(res.rsquared), float(dw), max_vif),
        "target_note": build_target_note(target, target_notes),
        "predictors": list(x_cols),
        "coef": {key: float(value) for key, value in res.params.drop("const", errors="ignore").items()},
        "pvals": {key: float(value) for key, value in res.pvalues.drop("const", errors="ignore").items()},
        "vif": vif,
    }


def describe_s5_variant(variant: str) -> str:
    """variant 문자열을 한국어 설명으로 바꿉니다."""
    target, spec = variant.split("__", 1)

    if spec == "s5_base":
        return f"{target} 기준 모델: 현재 시점 설명변수만 사용"

    lag_text = spec.split("_lag")[-1]
    lag_minutes = f"{lag_text}분 시차"

    if spec.startswith("s5_predlag_only_lag"):
        return f"{target}: 설명변수의 {lag_minutes} 값만 사용"
    if spec.startswith("s5_current_plus_predlag_lag"):
        return f"{target}: 현재 설명변수 + {lag_minutes} 설명변수"
    if spec.startswith("s5_current_plus_targetlag_lag"):
        return f"{target}: 현재 설명변수 + {lag_minutes} 타깃"
    if spec.startswith("s5_current_plus_predlag_targetlag_lag"):
        return f"{target}: 현재 설명변수 + {lag_minutes} 설명변수 + {lag_minutes} 타깃"

    return variant


def judge_s5_candidate(base_row: Dict[str, float], candidate_row: Dict[str, float]) -> Tuple[float, float, float, float, str, str]:
    """같은 행 기준 base와 비교해 S5 후보를 판정합니다."""
    delta_aic = float(candidate_row["AIC"] - base_row["AIC"])
    delta_bic = float(candidate_row["BIC"] - base_row["BIC"])
    base_dw_distance = abs(float(base_row["DW"]) - 2.0)
    candidate_dw_distance = abs(float(candidate_row["DW"]) - 2.0)
    dw_improvement = base_dw_distance - candidate_dw_distance
    candidate_max_vif = float(candidate_row["max_vif"])

    if delta_aic <= -2 and candidate_dw_distance <= 0.5 and candidate_max_vif <= 10:
        verdict = "강한 후보"
        reason = "DW가 2에 충분히 가까워졌고, 같은 행 기준 AIC도 개선됐으며 VIF도 허용 범위입니다."
    elif delta_aic <= -2 and candidate_dw_distance <= 0.5:
        verdict = "동학 후보(계수 해석 주의)"
        reason = "DW와 AIC는 좋아졌지만 VIF가 커서 계수 해석은 여전히 불안정합니다."
    elif delta_aic <= -2 and dw_improvement >= 0.2:
        verdict = "부분 개선"
        reason = "AIC는 좋아지고 DW도 개선됐지만, 아직 목표 수준까지는 아닙니다."
    elif delta_aic <= 2 and dw_improvement > 0:
        verdict = "조건 미달"
        reason = "개선은 있지만 채택 기준(DW와 AIC)을 동시에 만족하지 못합니다."
    else:
        verdict = "비권장"
        reason = "DW 개선 또는 AIC 개선이 충분하지 않습니다."

    return delta_aic, delta_bic, candidate_dw_distance, dw_improvement, verdict, reason


def run_s5_lag_scan(
    df_diff: pd.DataFrame,
    target_dictionary: Dict[str, Sequence[str]],
    target_notes: Optional[Dict[str, str]] = None,
    targets: Optional[Iterable[str]] = None,
    lag_steps: Optional[Sequence[int]] = None,
    family_order: Optional[Sequence[str]] = None,
    output_scan_path: Optional[Path] = None,
    output_summary_path: Optional[Path] = None,
    hac_lags: int = 20,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """S5 lag feature 스캔을 실행하고 전체 결과/추천 요약을 반환합니다."""
    targets = list(targets or DEFAULT_S5_TARGETS)
    lag_steps = list(lag_steps or DEFAULT_LAG_STEPS)
    family_order = list(family_order or DEFAULT_FAMILY_ORDER)
    target_notes = target_notes or {}

    rows: List[Dict[str, object]] = []

    for target in targets:
        predictors = list(target_dictionary[target])

        # full DIFF_on 기준 모델도 같은 표에 넣어 출발점을 맞춥니다.
        base_design_full, base_x_cols = build_s5_design(
            df_diff,
            target,
            predictors,
            family="s5_base",
            lag_steps=0,
        )
        base_variant = f"{target}__s5_base"
        base_result = fit_ols_from_design(
            base_design_full,
            target,
            base_x_cols,
            tag=base_variant,
            sample_scope="펌프 작동 구간 1차 차분 (현재 시점 기준 모델)",
            target_notes=target_notes,
            hac_lags=hac_lags,
        )
        if base_result is None:
            continue

        base_result.update({
            "family": "s5_base",
            "lag_minutes": 0,
            "variant_설명": describe_s5_variant(base_variant),
            "matched_base_variant": base_variant,
            "matched_base_N": base_result["N"],
            "matched_base_AIC": base_result["AIC"],
            "matched_base_BIC": base_result["BIC"],
            "matched_base_DW": base_result["DW"],
            "matched_base_max_vif": base_result["max_vif"],
            "delta_AIC_vs_matched_base": 0.0,
            "delta_BIC_vs_matched_base": 0.0,
            "dw_distance_to_2": abs(float(base_result["DW"]) - 2.0),
            "dw_improvement_vs_matched_base": 0.0,
            "n_lost_vs_full_diff": int(len(df_diff) - int(base_result["N"])),
            "판정": "기준 모델",
            "판정 이유": "S5에서 비교 기준이 되는 현재 시점 모델입니다.",
        })
        rows.append(base_result)

        matched_base_design, matched_base_x = build_s5_design(
            df_diff,
            target,
            predictors,
            family="s5_base",
            lag_steps=0,
        )

        for lag in lag_steps:
            for family in family_order[1:]:
                candidate_design, candidate_x = build_s5_design(
                    df_diff,
                    target,
                    predictors,
                    family=family,
                    lag_steps=lag,
                )
                if candidate_design.empty:
                    continue

                # lag 후보와 완전히 같은 시점만 남긴 base를 다시 적합해 AIC/BIC를 비교합니다.
                matched_base_design_aligned = matched_base_design.loc[candidate_design.index, [target] + matched_base_x].dropna()
                common_index = candidate_design.index.intersection(matched_base_design_aligned.index)
                candidate_design = candidate_design.loc[common_index]
                matched_base_design_aligned = matched_base_design_aligned.loc[common_index]

                candidate_variant = f"{target}__{family}_lag{lag}"
                candidate_result = fit_ols_from_design(
                    candidate_design,
                    target,
                    candidate_x,
                    tag=candidate_variant,
                    sample_scope=f"펌프 작동 구간 1차 차분 + {lag}분 시차 조합",
                    target_notes=target_notes,
                    hac_lags=hac_lags,
                )
                matched_base_result = fit_ols_from_design(
                    matched_base_design_aligned,
                    target,
                    matched_base_x,
                    tag=f"{target}__s5_base_matched_lag{lag}",
                    sample_scope=f"펌프 작동 구간 1차 차분 + {lag}분 시차 비교 기준",
                    target_notes=target_notes,
                    hac_lags=hac_lags,
                )

                if candidate_result is None or matched_base_result is None:
                    continue

                delta_aic, delta_bic, dw_distance, dw_improvement, verdict, reason = judge_s5_candidate(
                    matched_base_result,
                    candidate_result,
                )
                candidate_result.update({
                    "family": family,
                    "lag_minutes": lag,
                    "variant_설명": describe_s5_variant(candidate_variant),
                    "matched_base_variant": matched_base_result["variant"],
                    "matched_base_N": matched_base_result["N"],
                    "matched_base_AIC": matched_base_result["AIC"],
                    "matched_base_BIC": matched_base_result["BIC"],
                    "matched_base_DW": matched_base_result["DW"],
                    "matched_base_max_vif": matched_base_result["max_vif"],
                    "delta_AIC_vs_matched_base": delta_aic,
                    "delta_BIC_vs_matched_base": delta_bic,
                    "dw_distance_to_2": dw_distance,
                    "dw_improvement_vs_matched_base": dw_improvement,
                    "n_lost_vs_full_diff": int(len(df_diff) - int(candidate_result["N"])),
                    "판정": verdict,
                    "판정 이유": reason,
                })
                rows.append(candidate_result)

    scan = pd.DataFrame(rows)
    scan["판정_우선순위"] = scan["판정"].map(VERDICT_PRIORITY)

    summary = (
        scan.sort_values(
            ["target", "판정_우선순위", "delta_AIC_vs_matched_base", "dw_distance_to_2", "max_vif", "lag_minutes"],
            ascending=[True, True, True, True, True, True],
        )
        .groupby("target", as_index=False)
        .first()
        .sort_values("target")
        .reset_index(drop=True)
    )

    if output_scan_path is not None:
        output_scan_path.parent.mkdir(parents=True, exist_ok=True)
        scan.drop(columns=["판정_우선순위"]).to_csv(output_scan_path, index=False)

    if output_summary_path is not None:
        output_summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary.drop(columns=["판정_우선순위"]).to_csv(output_summary_path, index=False)

    return scan, summary
