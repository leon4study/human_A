import os
import sys
import time
import requests
import pandas as pd
from logger import get_logger

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from preprocessing import step1_prepare_window_data

logger = get_logger("SIMULATOR")

API_URL = "http://127.0.0.1:9977/predict"

# 4개 도메인(motor, hydraulic, nutrient, zone_drip) 전체 타겟 컬럼
# step1_prepare_window_data의 extra_cols로 전달 → model_cols 필터에서 살아남음
ALL_TARGET_COLS = [
    "motor_current_a",
    "rpm_stability_index",  # motor
    "zone1_resistance",
    "differential_pressure_kpa",  # hydraulic
    "pid_error_ec",
    "salt_accumulation_delta",  # nutrient
    "zone1_moisture_response_pct",
    "zone1_ec_accumulation",  # zone_drip
]

SPIKE_COLS = ["is_spike", "is_startup_spike", "is_anomaly_spike"]


def run_simulation():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    data_path = os.path.join(
        project_root,
        "data",
        "generated_data_from_dabin_0420.csv",
    )

    logger.info(f"📂 CSV 데이터 로딩 중... ({data_path})")
    df_raw = pd.read_csv(data_path)
    df_raw["timestamp"] = pd.to_datetime(df_raw["timestamp"])
    df_raw = df_raw.set_index("timestamp")

    logger.info("⚙️ 슬라이딩 윈도우 피처 엔지니어링 적용 중 (학습과 동일한 전처리)...")
    df_agg, df_interpret = step1_prepare_window_data(
        df_raw, window_method="sliding", target_cols=ALL_TARGET_COLS
    )

    # 스파이크 탐지 컬럼을 df_agg에 병합 (API 응답용 passthrough)
    for col in SPIKE_COLS:
        if col in df_interpret.columns:
            df_agg[col] = df_interpret[col]

    logger.info(
        f"✅ 전처리 완료! 총 {len(df_agg)}개의 슬라이딩 윈도우 데이터 준비 완료."
    )
    logger.info("🚀 API 서버로 실시간 추론 요청 시뮬레이션을 시작합니다!\n" + "=" * 60)

    for current_time, row in df_agg.iterrows():
        payload = row.to_dict()
        payload["timestamp"] = str(current_time)

        try:
            response = requests.post(API_URL, json=payload)

            if response.status_code == 200:
                result = response.json()
                overall_lvl = result["overall_alarm_level"]
                spike_info = result.get("spike_info", {})

                # 스파이크 유형 접두사 (기동 스파이크는 정상 범주)
                spike_tag = ""
                if spike_info.get("is_anomaly_spike"):
                    spike_tag = " ⚡[이상 스파이크]"
                elif spike_info.get("is_startup_spike"):
                    spike_tag = " 🔄[기동 스파이크-정상]"

                if overall_lvl == 0:
                    logger.info(
                        f"[{current_time}] 🟢 통합 상태: Normal (4개 도메인 정상){spike_tag}"
                    )
                else:
                    print(
                        f"\n🚨 [이상 진단 리포트] 발생 시점: {current_time}{spike_tag}"
                    )

                    # 4개 도메인 순회
                    for sys_name, report in result["domain_reports"].items():
                        if report["alarm"]["level"] > 0:
                            score = report["metrics"]["current_mse"]
                            t_caut = report["global_thresholds"]["caution"]
                            t_warn = report["global_thresholds"]["warning"]
                            t_err = report["global_thresholds"]["critical"]
                            rca = report["rca_top3"]

                            print(
                                f"  👉 [{sys_name.upper()} 도메인] 상태: {report['alarm']['label']}"
                            )
                            print(f"     ▶ 현재 Score (MSE): {score:.6f}")
                            print(
                                f"     ▶ 🔸 Caution(2σ): {t_caut:.6f} | 🟠 Warning(3σ): {t_warn:.6f} | 🔴 Critical(6σ): {t_err:.6f}"
                            )
                            print(f"     ▶ 🔍 주요 이상 원인 센서 (RCA):")
                            for i, item in enumerate(rca):
                                print(
                                    f"       * Top {i+1}: {item['feature']} ({item['contribution']}% 기여)"
                                )
                            if len(rca) > 0:
                                print(
                                    f"     ▶ 🛠️ Action Required: Inspect [{rca[0]['feature']}]"
                                )
                            print("  " + "-" * 50)

                    print("=" * 60 + "\n")

            else:
                logger.error(
                    f"[{current_time}] ❌ API 에러 ({response.status_code}): {response.text}"
                )

        except requests.exceptions.ConnectionError:
            logger.error(
                "❌ API 서버에 연결할 수 없습니다. uvicorn 서버가 켜져 있는지 확인하세요!"
            )
            break
        time.sleep(0.03)

    logger.info("🎉 모든 데이터 시뮬레이션 전송이 완료되었습니다!")


if __name__ == "__main__":
    run_simulation()
