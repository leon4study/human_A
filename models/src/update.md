client_simulator.py에서 API로 보내기 직전에 로그로 출력하게 만들었습니다. (보내지는 데이터 값 보기위해서)
logger.info(f"📤 전송 데이터: {payload}")   <-- 한 줄 추가

flow_baseline_l_min <-- 최근 60분 유량 이동평균이 데이터로는 넘어가고 있는 상태지만 쓰지않아서 표에선 삭제 했습니다.

표 작성 했을 때, 참고한 것은
1. 센서 데이터 값 -> row 데이터
2. 실시간 분석 요청 전송 -> client_simulator에 logger을 추가해 보내지는 데이터 값을 추가했습니다.
3. AI 이상감지 결과 전송 -> uvicorn inference_api에서 FAST API를 통해 json 값을 따와 작성했습니다.
4. AI 원인 결과 전송 -> uvicorn inference_api에서 FAST API를 통해 json 값을 따와 작성했습니다.