"""
plot_domain_timelines.py — 4개 도메인 각각의 진단 타임라인을 held-out v2 기준으로 저장한다.

evaluate_test_metrics.py가 학습 run figures에 남기던 도메인별 진단 그림(viz.plot_threshold_diagnosis)을,
독립 held-out 평가셋(faulty_testset_v2)에 대해 동일하게 4개 도메인 전부 뽑는다. 각 그림 = 그 도메인
이상점수(MSE) 시계열 + 실제 임계 3선(주의/경고/치명) + 기동(회색)·고장(빨강) 음영. 고장 음영 위에서
점수가 임계선을 넘으면 그 도메인이 이상을 잡고 있다는 직접 증거다.

실행:
    cd fault_injection && python plot_domain_timelines.py
"""
import os
import sys

import numpy as np
import pandas as pd

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT, "src"))

from evaluate_test_metrics import run_inference                 # noqa: E402
from operating_point_eval import window, startup_mask_of, FAULTY_CSV  # noqa: E402
from viz import plot_threshold_diagnosis, build_contact_sheet   # noqa: E402

OUT_DIR = os.path.join(PROJECT, "data", "evaluation_outputs", "figures_v2")


def main():
    fr = pd.read_csv(FAULTY_CSV)
    fr["timestamp"] = pd.to_datetime(fr["timestamp"])
    fr = fr.set_index("timestamp")
    da = window(fr)

    df_pred, domains, thr_map = run_inference(da)        # serve 동일 추론 → 도메인별 점수·임계
    y_true = da["anomaly_label"].astype(int).to_numpy()
    startup = startup_mask_of(da)

    os.makedirs(OUT_DIR, exist_ok=True)
    for dom in domains:                                  # 4개 도메인 전부
        plot_threshold_diagnosis(
            df_pred[f"{dom}_score"].to_numpy(),
            thr_map[dom],
            model_name=dom,
            save_path=os.path.join(OUT_DIR, f"{dom}__v2_timeline.png"),
            startup_mask=startup,
            anomaly_mask=(y_true == 1),                  # 고장 구간(빨강 음영)
            boundary_index=None,                         # held-out 전체가 테스트라 학습/평가 경계 없음
            show_excl_startup=False,                     # 평가 단계 → 기동제외 보조선 비활성
        )
        print(f"  저장: {dom}__v2_timeline.png")

    sheet = build_contact_sheet(OUT_DIR)                 # 4장 한 장으로 모은 대조표
    print(f"\n[plot] 4개 도메인 타임라인: {OUT_DIR}")
    if sheet:
        print(f"  대조표(4개 한 장): {sheet}")


if __name__ == "__main__":
    main()