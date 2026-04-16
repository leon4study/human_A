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
    data_path = os.path.join(project_root, "data", "smartfarm_nutrient_pump_rawdata_3months_clog_focus_v2_stronger.csv")

    logger.info(f"📂 CSV 데이터 로딩 중... ({data_path})")
    df_raw = pd.read_csv(data_path)

    # 1. timestamp를 datetime으로 변환하고 인덱스로 설정
    df_raw["timestamp"] = pd.to_datetime(df_raw["timestamp"])
    df_raw = df_raw.set_index("timestamp")

    # 🌟 2. 핵심 로직: 1분 단위 데이터를 '10분(10T)' 단위로 묶어서 평균(mean) 계산!
    logger.info("⏱️ 1분 단위 데이터를 10분 단위 평균 데이터로 집계(Resampling) 합니다...")
    df_10min = df_raw.resample("10min").mean().dropna()
    logger.info(f"✅ 집계 완료! 총 {len(df_10min)}개의 10분 단위 추론 데이터가 준비되었습니다.")

    logger.info("🚀 API 서버로 실시간 추론 요청 시뮬레이션을 시작합니다!\n" + "="*60)

    # 3. 10분 단위로 묶인 데이터를 한 줄씩 API 서버로 전송
    for current_time, row in df_10min.iterrows():
        # Pandas Series(한 줄)를 딕셔너리로 변환
        payload = row.to_dict()
        # API에서 쓸 수 있게 타임스탬프를 문자열로 추가
        payload["timestamp"] = str(current_time)

        try:
            # 🌟 API 서버에 POST 요청 쏘기!
            response = requests.post(API_URL, json=payload)
            
            if response.status_code == 200:
                result = response.json()
                status = result["overall_status"]
                
                # 시각적으로 상태 확인 (정상 🟢, 주의 🔸, 경고 🟠, 에러 🔴)
                if result["overall_alarm_level"] == 0:
                    logger.info(f"[{current_time}] API 응답: {status}")
                else:
                    # 이상 징후가 있을 때는 눈에 띄게 출력!
                    logger.warning(f"[{current_time}] 🚨 API 응답: {status} (Level {result['overall_alarm_level']})")
                    
                    # 어떤 도메인에서 무슨 센서가 문제인지 RCA 리포트 간략히 출력
                    for sys, report in result["domain_reports"].items():
                        if report["alarm"]["level"] > 0:
                            rca_top1 = report["rca"][0]
                            logger.warning(f"   -> [원인 분석] {sys.upper()} 도메인 '{rca_top1['feature']}' 이상 (기여도: {rca_top1['contribution']}%)")
            else:
                logger.error(f"[{current_time}] ❌ API 에러 ({response.status_code}): {response.text}")

        except requests.exceptions.ConnectionError:
            logger.error("❌ API 서버에 연결할 수 없습니다. uvicorn 서버가 켜져 있는지 확인하세요!")
            break

        # 터미널 창에 너무 빨리 지나가면 보기 힘드니, 0.1초씩 쉬면서 쏩니다 (실제 10분 = 시뮬레이션 0.1초)
        time.sleep(0.1)

    logger.info("🎉 모든 데이터 시뮬레이션 전송이 완료되었습니다!")

if __name__ == "__main__":
    run_simulation()