import os
import time
import requests
import pandas as pd
from logger import get_logger

# 클라이언트(데이터 쏘는 쪽) 전용 로거
logger = get_logger("SIMULATOR")

# 🌟 API 서버 주소 (Uvicorn이 켜져 있는 주소)
API_URL = "http://127.0.0.1:8000/predict"


def run_simulation():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    data_path = os.path.join(
        project_root,
        "data",
        "smartfarm_nutrient_pump_rawdata_3months_clog_focus_v2_stronger.csv",
    )

    logger.info(f"📂 CSV 데이터 로딩 중... ({data_path})")
    df_raw = pd.read_csv(data_path)

    # 1. timestamp를 datetime으로 변환하고 인덱스로 설정
    df_raw["timestamp"] = pd.to_datetime(df_raw["timestamp"])
    df_raw = df_raw.set_index("timestamp")

    # 🌟 2. 핵심 로직: 1분 단위 데이터를 '10분(10T)' 단위로 묶어서 평균(mean) 계산!
    logger.info(
        "⏱️ 1분 단위 데이터를 10분 단위 평균 데이터로 집계(Resampling) 합니다..."
    )
    df_10min = df_raw.resample("10min").mean().dropna()
    logger.info(
        f"✅ 집계 완료! 총 {len(df_10min)}개의 10분 단위 추론 데이터가 준비되었습니다."
    )

    logger.info("🚀 API 서버로 실시간 추론 요청 시뮬레이션을 시작합니다!\n" + "=" * 60)

    # 3. 10분 단위로 묶인 데이터를 한 줄씩 API 서버로 전송
    for current_time, row in df_10min.iterrows():
        # Pandas Series(한 줄)를 딕셔너리로 변환
        payload = row.to_dict()
        # API에서 쓸 수 있게 타임스탬프를 문자열로 추가
        payload["timestamp"] = str(current_time)

        try:
            logger.info(f"📤 전송 데이터: {payload}")  #client_simulator.py에서 API로 보내기 직전에 로그로 출력 (보내지는 값을 보기위함)
            # API 서버에 POST 요청 쏘기
            response = requests.post(API_URL, json=payload)

            if response.status_code == 200:
                result = response.json()
                overall_lvl = result["overall_alarm_level"]

                # 🟢 전체가 완전 정상일 때는 요약만 출력
                if overall_lvl == 0:
                    logger.info(
                        f"[{current_time}] 🟢 통합 상태: Normal (모든 도메인 정상)"
                    )

                # 🟠 하나라도 '주의' 이상이 발생하면 노트북 스타일의 상세 리포트 출력!
                else:
                    print(f"🚨 [이상 진단 리포트] 발생 시점: {current_time}")
                    # 3개의 도메인을 순회하며 각각의 상세 상태 출력
                    for sys_name, report in result["domain_reports"].items():
                        alarm_lbl = report["alarm"]["label"]
                        score = report["score"]
                        th = report["thresholds"]
                        rcas = report["rca"]

                        print(f"\n[{sys_name.upper()} 도메인]")
                        print(f"▶ 판정 결과: [{alarm_lbl}]")
                        print(f"▶ 현재 Score (MSE): {score:.6f}")
                        print(f"  🔸 주의(Caution) 기준선: {th['caution']:.6f}")
                        print(f"  🟠 경고(Warning) 기준선: {th['warning']:.6f}")
                        print(f"  🔴 에러(Error)   기준선: {th['error']:.6f}")

                        # RCA 출력
                        print("  [Root Cause Analysis - 원인 기여도]")
                        for i, cause in enumerate(rcas):
                            print(
                                f"    Top{i+1}: {cause['feature']} ({cause['contribution']}%)"
                            )

                        # 에러 발생 시 Action Required (조치 권고안) 출력
                        if report["alarm"]["level"] > 0 and len(rcas) > 0:
                            print(f"▶ Action_Required: Inspect {rcas[0]['feature']}")

                    print("-" * 60 + "\n")

            else:
                logger.error(
                    f"[{current_time}] ❌ API 에러 ({response.status_code}): {response.text}"
                )

        except requests.exceptions.ConnectionError:
            logger.error(
                "❌ API 서버에 연결할 수 없습니다. uvicorn 서버가 켜져 있는지 확인하세요!"
            )
            break

        # 시뮬레이션 속도 조절 (예: 1초 대기)
        time.sleep(7)

    logger.info("🎉 모든 데이터 시뮬레이션 전송이 완료되었습니다!")


if __name__ == "__main__":
    run_simulation()
