from pathlib import Path
from textwrap import dedent
import json


SRC = Path(__file__).with_name("Hypothesis_Testing.ipynb")
DST = Path(__file__).with_name("SHAP_Guided_Hypothesis_Testing.ipynb")


def lines(text: str):
    return dedent(text).lstrip("\n").splitlines(keepends=True)


def md_cell(text: str):
    return {"cell_type": "markdown", "metadata": {}, "source": lines(text)}


def code_cell(text: str):
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": lines(text),
    }


nb = json.loads(SRC.read_text(encoding="utf-8"))
cells = nb["cells"]

cells[0]["source"] = lines(
    """
    # SHAP-Guided Hypothesis Testing

    기존 `Hypothesis_Testing.ipynb`를 뼈대로 두고,
    `shap_pipeline.ipynb`에서 반복적으로 살아남은 Robust 피처를 앞단 근거로 붙인 발표용 노트북입니다.

    이번 버전의 원칙은 두 가지입니다.
    1. SHAP에서 반복적으로 살아남은 피처만 가설의 주연·조연으로 올립니다.
    2. 첫 결과를 그대로 믿지 않고, 각 검정마다 허점과 민감도를 먼저 점검합니다.

    ## 이번 노트북의 3개 가설

    ### H1. 관로/팁 막힘
    - 메인 변수: `zone1_resistance`
    - 보조 변수: `filter_delta_p_kpa`, `flow_drop_rate`, `zone1_flow_l_min`
    - 검정 기법: **Granger Causality Test**

    ### H2. 채널링/미세 누수
    - 메인 변수: `drain_ec_ds_m`
    - 보조 변수: `zone1_substrate_ec_ds_m`, `zone1_substrate_moisture_pct`
    - 검정 기법: **Event-window CCF**
    - 주의: CCF를 그대로 믿기 전에 onset 규칙 민감도와 이벤트 구조를 먼저 비판적으로 점검합니다.

    ### H3. 펌프 노후화/기계 열화
    - 메인 변수: `wire_to_water_efficiency`
    - 보조 변수: `motor_current_a`, `bearing_vibration_rms_mm_s`, `motor_temperature_c`
    - 검정 기법: **Welch T-test + Mann-Whitney U**
    """
)

cells[1]["source"] = lines(
    """
    ## 0. 공통 함수 준비

    기존 가설검정 노트북의 계산 함수를 그대로 재사용하되,
    아래 셀 끝에서 SHAP/Robust 피처 앵커와 H2 CCF용 보조 함수를 추가로 덧붙입니다.
    """
)

cells[2]["source"] = [
    line
    for line in cells[2]["source"]
    if 'if __name__ == "__main__":' not in line and "main()" not in line
]

cells[2]["source"] += lines(
    """

    BASE_NOTEBOOK_DIR = Path("human_A") if Path("human_A").exists() else Path(".")
    OUT_DIR = BASE_NOTEBOOK_DIR / "shap_guided_hypothesis_outputs"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    ROBUST_IMG_CANDIDATES = [
        Path("output_m") / "robust_per_target.png",
        Path("..") / "output_m" / "robust_per_target.png",
    ]
    SHAP_IMG_CANDIDATES = [
        Path("output_m") / "shap_top10.png",
        Path("..") / "output_m" / "shap_top10.png",
    ]

    ROBUST_FEATURE_TABLE = [
        {"feature": "zone1_resistance", "votes": "4/8", "representative_class": "PUMP_DEGRADATION", "use_in_notebook": "H1 메인 신호"},
        {"feature": "filter_delta_p_kpa", "votes": "2/8", "representative_class": "TIP_CLOG", "use_in_notebook": "H1 보조축"},
        {"feature": "zone1_flow_l_min", "votes": "3/8", "representative_class": "FLOW_DROP", "use_in_notebook": "H1/H2 보조 해석"},
        {"feature": "drain_ec_ds_m", "votes": "2/8", "representative_class": "RPM_INSTABILITY", "use_in_notebook": "H2 메인 반응 신호"},
        {"feature": "zone1_substrate_ec_ds_m", "votes": "2/8", "representative_class": "FLOW_DROP", "use_in_notebook": "H2 보조 zone 신호"},
        {"feature": "zone1_substrate_moisture_pct", "votes": "2/8", "representative_class": "FLOW_DROP", "use_in_notebook": "H2 보조 zone 신호"},
        {"feature": "motor_current_a", "votes": "2/8", "representative_class": "FILTER_CLOG", "use_in_notebook": "H3 보조 지표"},
        {"feature": "bearing_vibration_rms_mm_s", "votes": "3/8", "representative_class": "FILTER_CLOG", "use_in_notebook": "H3 보조 지표"},
        {"feature": "motor_temperature_c", "votes": "4/8", "representative_class": "TIP_CLOG", "use_in_notebook": "H3 보조 지표"},
    ]

    HYPOTHESIS_FEATURE_MAP = [
        {"가설": "H1 관로/팁 막힘", "통계 기법": "Granger", "메인 변수": "zone1_resistance -> zone1_moisture_response_pct", "보조/Robust 피처": "filter_delta_p_kpa, flow_drop_rate, zone1_flow_l_min", "SHAP 근거": "zone1_resistance 4/8 Robust"},
        {"가설": "H2 채널링/미세 누수", "통계 기법": "Event-window CCF", "메인 변수": "mix_flow_l_min -> abs(Δdrain_ec_ds_m)", "보조/Robust 피처": "zone1_substrate_ec_ds_m, zone1_substrate_moisture_pct", "SHAP 근거": "drain_ec_ds_m 2/8 Robust"},
        {"가설": "H3 펌프 노후화/기계 열화", "통계 기법": "Welch T-test + Mann-Whitney", "메인 변수": "wire_to_water_efficiency", "보조/Robust 피처": "motor_current_a, bearing_vibration_rms_mm_s, motor_temperature_c", "SHAP 근거": "motor_temperature_c 4/8 Robust"},
    ]

    def build_shap_anchor_tables():
        return pd.DataFrame(HYPOTHESIS_FEATURE_MAP), pd.DataFrame(ROBUST_FEATURE_TABLE)


    def resolve_optional_path(paths):
        for path in paths:
            if path.exists():
                return path
        return None


    def format_p_value(value):
        if pd.isna(value):
            return "NA"
        value = float(value)
        if value <= 0:
            return "< 1e-300"
        if value < 1e-4:
            return f"{value:.2e}"
        if value < 0.01:
            return f"{value:.4f}"
        return f"{value:.3f}"


    def build_event_lag_table_with_hits(df_raw, abs_diff_signal, threshold, consecutive_hits):
        on_mask = get_on_mask(df_raw)
        starts = find_isolated_event_starts(on_mask)
        rows = []
        for event_idx, ts in enumerate(starts, start=1):
            onset_ts = first_consecutive_hit(
                signal=abs_diff_signal,
                start_ts=ts,
                threshold=threshold,
                max_lag_minutes=MAX_RESPONSE_LAG_MINUTES,
                consecutive_hits=consecutive_hits,
            )
            observed = onset_ts is not None
            lag_minutes = (onset_ts - ts).total_seconds() / 60 if observed else MAX_RESPONSE_LAG_MINUTES
            rows.append(
                {
                    "event_index": event_idx,
                    "event_start": ts,
                    "lag_minutes": float(lag_minutes),
                    "event_observed": int(observed),
                }
            )
        return pd.DataFrame(rows)


    def get_ccf_peak(curve):
        valid = curve.dropna(subset=["mean_corr"])
        if valid.empty:
            return {"lag_minutes": None, "mean_corr": None}
        peak_row = valid.loc[valid["mean_corr"].abs().idxmax()]
        return {"lag_minutes": int(peak_row["lag_minutes"]), "mean_corr": float(peak_row["mean_corr"])}


    def run_h2_shap_guided(df_raw, phase0_result):
        on_mask = get_on_mask(df_raw)
        isolated_starts = phase0_result["isolated_starts"]
        drain_abs_diff = phase0_result["drain_abs_diff"]
        threshold = phase0_result["threshold_info"]["threshold_mad"]

        one_hit_lag_table = build_event_lag_table_with_hits(df_raw, drain_abs_diff, threshold, consecutive_hits=1)
        two_hit_lag_table = build_event_lag_table_with_hits(df_raw, drain_abs_diff, threshold, consecutive_hits=2)
        one_hit_failure_rate = float(1 - one_hit_lag_table["event_observed"].mean())
        two_hit_failure_rate = float(1 - two_hit_lag_table["event_observed"].mean())

        split_point = int(np.ceil(len(isolated_starts) / 2))
        early_starts = isolated_starts[:split_point]
        late_starts = isolated_starts[split_point:]
        ccf_curve, ccf_peak = auxiliary_event_ccf(df_raw, isolated_starts, drain_abs_diff, max_lag_minutes=MAX_RESPONSE_LAG_MINUTES)
        early_curve, early_peak = auxiliary_event_ccf(df_raw, early_starts, drain_abs_diff, max_lag_minutes=MAX_RESPONSE_LAG_MINUTES)
        late_curve, late_peak = auxiliary_event_ccf(df_raw, late_starts, drain_abs_diff, max_lag_minutes=MAX_RESPONSE_LAG_MINUTES)

        observed_lags = two_hit_lag_table.loc[two_hit_lag_table["event_observed"] == 1].copy()
        observed_lags["group"] = np.where(observed_lags["event_index"] <= split_point, "초기 절반", "후기 절반")
        early_obs = observed_lags.loc[observed_lags["group"] == "초기 절반", "lag_minutes"]
        late_obs = observed_lags.loc[observed_lags["group"] == "후기 절반", "lag_minutes"]
        if len(early_obs) > 0 and len(late_obs) > 0:
            lag_mw = mannwhitneyu(early_obs, late_obs, alternative="two-sided")
            lag_mw_p = float(lag_mw.pvalue)
        else:
            lag_mw_p = np.nan

        start_time_mode = isolated_starts.to_series().dt.strftime("%H:%M").mode().iloc[0]
        starts_per_day_mode = pd.Series(isolated_starts.date).value_counts().mode().iloc[0]

        summary = pd.DataFrame(
            [
                {"점검/통계": "이벤트 구조", "값": f"{len(isolated_starts)}개, 하루 {starts_per_day_mode}회, 시작시각 mode {start_time_mode}", "비판적 리뷰": "event index와 운영일이 같은 축"},
                {"점검/통계": "onset 규칙 민감도", "값": f"1-hit 실패율 {one_hit_failure_rate:.3f} / 2-hit 실패율 {two_hit_failure_rate:.3f}", "비판적 리뷰": "같은 데이터라도 규칙을 엄격하게 하면 실패율이 크게 바뀜"},
                {"점검/통계": "전체 CCF peak", "값": f"{ccf_peak['lag_minutes']}분 / corr={ccf_peak['mean_corr']:.3f}" if ccf_peak["lag_minutes"] is not None else "NA", "비판적 리뷰": "corr 절대값이 작으면 강한 증거가 아님"},
                {"점검/통계": "초기 vs 후기 CCF peak", "값": f"{early_peak['lag_minutes']}분 -> {late_peak['lag_minutes']}분" if early_peak["lag_minutes"] is not None and late_peak["lag_minutes"] is not None else "NA", "비판적 리뷰": f"관측 lag 비교 MW p={format_p_value(lag_mw_p)}"},
                {"점검/통계": "최종 판정", "값": "탐색적 분석 유지" if two_hit_failure_rate > 0.30 else "제한적 해석 가능", "비판적 리뷰": "2-hit 실패율이 30%를 넘으면 confirmatory claim 금지"},
            ]
        )

        plt.figure(figsize=(9, 4))
        sns.lineplot(data=ccf_curve.assign(group="전체"), x="lag_minutes", y="mean_corr", label="전체", marker="o")
        sns.lineplot(data=early_curve.assign(group="초기"), x="lag_minutes", y="mean_corr", label="초기 절반", marker="o")
        sns.lineplot(data=late_curve.assign(group="후기"), x="lag_minutes", y="mean_corr", label="후기 절반", marker="o")
        plt.axhline(0, color="black", linestyle="--", linewidth=1)
        plt.title("H2 Event-window CCF: mix_flow vs |Δdrain_ec|")
        plt.xlabel("lag (minutes)")
        plt.ylabel("mean correlation")
        plt.tight_layout()
        plt.savefig(OUT_DIR / "h2_event_window_ccf.png", dpi=150, bbox_inches="tight")
        plt.close()

        note_md = "\\n".join(
            [
                "### H2 발표 포인트",
                f"- `drain_ec_ds_m` hold 중앙값은 `{exact_hold_run_quantiles(df_raw['drain_ec_ds_m']).loc[0.5]:.1f}분`이고 이벤트 수는 `{len(isolated_starts)}`개입니다.",
                f"- 하지만 onset 실패율이 `1-hit {one_hit_failure_rate:.3f}`에서 `2-hit {two_hit_failure_rate:.3f}`로 크게 뛰어 규칙 민감도가 큽니다.",
                f"- 전체 CCF peak는 `{ccf_peak['lag_minutes']}분 / corr={ccf_peak['mean_corr']:.3f}` 수준이라 강한 정합성 신호라고 보기 어렵습니다.",
                "- 따라서 H2는 채널링/미세 누수의 확증적 검정이 아니라 탐색적 패턴 분석으로만 유지합니다.",
            ]
        )

        return {
            "summary": summary,
            "zone_support": phase0_result["zone_summary"],
            "note_md": note_md,
            "one_hit_failure_rate": one_hit_failure_rate,
            "two_hit_failure_rate": two_hit_failure_rate,
            "ccf_peak": ccf_peak,
            "lag_mw_p": lag_mw_p,
        }


    def write_shap_guided_summary(csv_path, phase0_result, h1_result, h2_result, h3_result):
        lines = [
            "# SHAP-Guided Hypothesis Testing Summary",
            "",
            f"- 입력 파일: `{csv_path}`",
            f"- 유의수준: `{ALPHA}`",
            "",
            "## SHAP 앵커",
            dataframe_to_simple_markdown(pd.DataFrame(HYPOTHESIS_FEATURE_MAP)),
            "",
            "## H1",
            dataframe_to_simple_markdown(h1_result["summary"]),
            "",
            "## H2",
            dataframe_to_simple_markdown(h2_result["summary"]),
            "",
            "## H3",
            dataframe_to_simple_markdown(h3_result["group_present"]),
            "",
            dataframe_to_simple_markdown(h3_result["test_present"]),
            "",
            "## 제한해서 말할 점",
            "- H1은 파생변수 구조가 있어 유의성을 곧바로 물리 인과로 번역하면 안 됩니다.",
            f"- H2는 2-hit onset 실패율이 `{h2_result['two_hit_failure_rate']:.3f}`라 탐색적 분석으로만 유지합니다.",
            "- H3는 세척 전후 실험이 아니라 초기 7일 vs 후기 7일 proxy 비교입니다.",
        ]
        (OUT_DIR / "shap_guided_hypothesis_summary.md").write_text("\\n".join(lines), encoding="utf-8-sig")


    def run_h3_shap_guided(df_feat):
        active = df_feat.loc[df_feat["pump_on_proxy"] == 1].copy()
        active["date"] = active.index.date
        daily_mean = active.groupby("date")[["wire_to_water_efficiency", "motor_current_a", "bearing_vibration_rms_mm_s", "motor_temperature_c"]].mean()
        daily_mean["day_idx"] = np.arange(len(daily_mean))

        group_a = daily_mean.head(WEEK_DAYS).copy()
        group_b = daily_mean.tail(WEEK_DAYS).copy()

        welch = ttest_ind(group_a["wire_to_water_efficiency"], group_b["wire_to_water_efficiency"], equal_var=False)
        mw = mannwhitneyu(group_a["wire_to_water_efficiency"], group_b["wire_to_water_efficiency"], alternative="two-sided")

        trend_present = pd.DataFrame(
            [
                {"지표": "wire_to_water_efficiency", "운영일과의 상관": float(np.corrcoef(daily_mean["day_idx"], daily_mean["wire_to_water_efficiency"])[0, 1])},
                {"지표": "motor_current_a", "운영일과의 상관": float(np.corrcoef(daily_mean["day_idx"], daily_mean["motor_current_a"])[0, 1])},
                {"지표": "bearing_vibration_rms_mm_s", "운영일과의 상관": float(np.corrcoef(daily_mean["day_idx"], daily_mean["bearing_vibration_rms_mm_s"])[0, 1])},
                {"지표": "motor_temperature_c", "운영일과의 상관": float(np.corrcoef(daily_mean["day_idx"], daily_mean["motor_temperature_c"])[0, 1])},
            ]
        )

        group_present = pd.DataFrame(
            [
                {
                    "구간": "초기 7일",
                    "wire_to_water_efficiency 평균": float(group_a["wire_to_water_efficiency"].mean()),
                    "motor_current_a 평균": float(group_a["motor_current_a"].mean()),
                    "bearing_vibration_rms_mm_s 평균": float(group_a["bearing_vibration_rms_mm_s"].mean()),
                    "motor_temperature_c 평균": float(group_a["motor_temperature_c"].mean()),
                },
                {
                    "구간": "후기 7일",
                    "wire_to_water_efficiency 평균": float(group_b["wire_to_water_efficiency"].mean()),
                    "motor_current_a 평균": float(group_b["motor_current_a"].mean()),
                    "bearing_vibration_rms_mm_s 평균": float(group_b["bearing_vibration_rms_mm_s"].mean()),
                    "motor_temperature_c 평균": float(group_b["motor_temperature_c"].mean()),
                },
            ]
        )

        test_present = pd.DataFrame(
            [
                {
                    "비교 방식": "초기 7일 vs 후기 7일 proxy 비교",
                    "Welch p-value": float(welch.pvalue),
                    "Mann-Whitney p-value": float(mw.pvalue),
                    "비판적 리뷰": "cleaning_event_flag가 없어 세척 전후 실험이 아니라 시간 proxy 비교",
                }
            ]
        )

        plot_df = pd.concat([group_a.assign(group="초기 7일"), group_b.assign(group="후기 7일")]).reset_index(names="date")
        plt.figure(figsize=(8, 4))
        sns.boxplot(data=plot_df, x="group", y="wire_to_water_efficiency")
        plt.title("H3: wire_to_water_efficiency 비교")
        plt.tight_layout()
        plt.savefig(OUT_DIR / "h3_ttest.png", dpi=150, bbox_inches="tight")
        plt.close()

        return {
            "trend_present": trend_present,
            "group_present": group_present,
            "test_present": test_present,
            "test_summary": pd.DataFrame([{"welch_t_p_value": float(welch.pvalue), "mann_whitney_p_value": float(mw.pvalue)}]),
        }
    """
)

cells[7:7] = [
    md_cell(
        """
        ## 3. SHAP/Robust 피처 앵커

        여기서는 `shap_pipeline.ipynb`에서 이미 뽑아 둔 Robust 피처를 기준으로
        이번 발표용 3개 가설이 왜 선택되었는지 먼저 고정합니다.
        """
    ),
    code_cell(
        """
        hypothesis_feature_df, robust_feature_df = build_shap_anchor_tables()
        robust_img_path = resolve_optional_path(ROBUST_IMG_CANDIDATES)
        shap_img_path = resolve_optional_path(SHAP_IMG_CANDIDATES)

        display(hypothesis_feature_df)
        display(robust_feature_df)
        if robust_img_path is not None:
            display(Image(filename=str(robust_img_path)))
        if shap_img_path is not None:
            display(Image(filename=str(shap_img_path)))
        """
    ),
]

cells[9]["source"] = lines(
    """
    ## 4. H2를 하기 전 비판적 점검

    H2는 CCF를 바로 해석하면 안 됩니다.
    먼저 다음을 확인합니다.

    1. `drain_ec_ds_m` 유효 갱신 주기
    2. isolated event 수
    3. MAD 기반 threshold
    4. onset 규칙 민감도
    5. zone 보조 신호 가용성
    """
)

cells[11]["source"] = lines(
    """
    ## 5. 검정 1. Granger Causality Test

    기존 노트북의 H1 구조를 유지하되,
    SHAP에서 반복적으로 등장한 `zone1_resistance`와 `filter_delta_p_kpa`를 중심 축으로 다시 읽습니다.
    """
)

cells[13]["source"] = lines(
    """
    ## 6. 검정 2. Event-window CCF

    사용자가 원한 방법론은 CCF입니다.
    다만 이 데이터는 하루 1회 고정 공급 블록 구조라서, 펌프 on/off 스텝 자체를 그대로 CCF에 넣으면 정보량이 낮습니다.

    그래서 이번 셀은 다음 순서로 정리합니다.
    - 공급 신호 proxy: `mix_flow_l_min`
    - 반응 신호: `|Δdrain_ec_ds_m|`
    - event-window CCF 계산
    - onset 1-hit vs 2-hit 민감도와 함께 결과 해석
    """
)

cells[14]["source"] = lines(
    """
    h2_result = run_h2_shap_guided(df_raw, phase0_result)

    display(h2_result["summary"])
    display(h2_result["zone_support"])
    display(Markdown(h2_result["note_md"]))
    """
)

cells[15]["source"] = lines(
    """
    Image(filename=str(OUT_DIR / "h2_event_window_ccf.png"))
    """
)

cells[16]["source"] = lines(
    """
    ### H2 중간 해석

    여기서는 결론을 세게 말하지 않습니다.

    - H2는 CCF를 쓰더라도 event 구조와 onset 규칙에 민감합니다.
    - 따라서 채널링/미세 누수의 확증적 증명보다,
      **반복 공급 이벤트에 대한 drain 반응 패턴이 어떻게 보이는가**에 초점을 둡니다.
    - 이번 데이터에서는 H2를 **탐색적 분석**으로 유지하는 편이 안전합니다.
    """
)

cells[17]["source"] = lines(
    """
    ## 7. 검정 3. T-test / Mann-Whitney U

    기존 H3 구조를 유지하되,
    `wire_to_water_efficiency`를 중심으로 `motor_current_a`, `bearing_vibration_rms_mm_s`, `motor_temperature_c`를 함께 읽습니다.
    """
)

cells[18]["source"] = lines(
    """
    h3_result = run_h3_shap_guided(df_feat)

    display(h3_result['trend_present'])
    display(h3_result['group_present'])
    display(h3_result['test_present'])
    Image(filename=str(OUT_DIR / 'h3_ttest.png'))
    """
)

cells[19]["source"] = lines(
    """
    ## 8. 최종 요약

    마지막 셀은 SHAP 근거와 통계 검정을 한 번에 묶어 발표용 요약본으로 출력합니다.
    """
)

cells[20]["source"] = lines(
    """
    write_shap_guided_summary(csv_path, phase0_result, h1_result, h2_result, h3_result)
    summary_path = OUT_DIR / 'shap_guided_hypothesis_summary.md'
    summary_text = summary_path.read_text(encoding='utf-8-sig')
    display(Markdown(summary_text))
    print('summary saved to:', summary_path)
    """
)

for cell in cells:
    if cell["cell_type"] == "code":
        cell["execution_count"] = None
        cell["outputs"] = []
for i, cell in enumerate(cells):
    cell["id"] = f"cell-{i:02d}"

DST.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
print(DST)
