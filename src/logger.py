# src/logger.py
import os
import logging
import csv
from datetime import datetime


def get_logger(module_name="SmartFarm"):
    """
    프로젝트 어디서든 이 함수를 부르면 똑같은 설정의 로거를 반환합니다.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    log_dir = os.path.join(project_root, "logs", "system")
    os.makedirs(log_dir, exist_ok=True)

    # 매일 날짜별로 로그 파일 생성 (예: system_20231027.log)
    timestamp = datetime.now().strftime("%Y%m%d")
    log_file = os.path.join(log_dir, f"system_{timestamp}.log")

    logger = logging.getLogger(module_name)

    # 이미 핸들러가 추가되어 있다면 중복 추가 방지 (루프 돌 때 로그가 여러 번 찍히는 것 방지)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )

        # 1. 터미널 출력용
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

        # 2. 파일 저장용
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def save_experiment_to_csv(model_name, mse_mean, t_caut, t_warn, t_cri):
    """
    리더보드(CSV)에 실험 결과를 누적 저장합니다.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    csv_path = os.path.join(project_root, "logs", "experiment_board.csv")

    # logs 폴더가 없을 경우 대비
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    file_exists = os.path.isfile(csv_path)

    with open(csv_path, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(
                [
                    "Date",
                    "Domain",
                    "Mean_MSE",
                    "Threshold_Caution",
                    "Threshold_Warning",
                    "Threshold_Error",
                ]
            )

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        writer.writerow(
            [
                current_time,
                model_name,
                round(mse_mean, 6),
                round(t_caut, 6),
                round(t_warn, 6),
                round(t_cri, 6),
            ]
        )
