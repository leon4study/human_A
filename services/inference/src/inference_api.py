# 로컬 실행 명령어 예시
# python -m uvicorn inference_api:app --reload (개발/테스트용)
# python -m uvicorn inference_api:app --host 0.0.0.0 --port 8000 (배포/실전용)

import os
import json
import glob
import joblib
import datetime
import numpy as np
import pandas as pd
import tensorflow as tf
import sqlalchemy as sa
import boto3
from io import BytesIO
from fastapi import FastAPI, Body, HTTPException
from typing import Dict, Any, List
from logger import get_logger
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler

# =====================================================================
# 환경 변수 로드 (.env.local 또는 배포 환경 변수)
# =====================================================================
ENV = os.getenv("ENV", "local")
if ENV == "local":
    candidate_env_paths = [
        "../../../.env.local",
        "/Users/jun/GitStudy/human_A/.env.local",
    ]
    loaded = False
    for env_path in candidate_env_paths:
        if os.path.exists(env_path):
            load_dotenv(env_path)
            logger.info(f"Loaded environment from {env_path}")
            loaded = True
            break
    if not loaded:
        logger.warning(f"Missing env file; tried: {candidate_env_paths}")
else:
    logger.info(f"Using deployed environment: {ENV}")

# DB 설정
DB_URL = os.getenv("AI_DATABASE_URL", "postgresql://farmer:plant_rich@localhost:5432/smartfarm")
engine = sa.create_engine(DB_URL)

# S3 설정
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:9000")
S3_ACCESS_KEY = os.getenv("MINIO_ROOT_USER", "admin")
S3_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", "password123")
BUCKET_NAME = "raw-data"
s3 = boto3.client('s3',
                  endpoint_url=S3_ENDPOINT,
                  aws_access_key_id=S3_ACCESS_KEY,
                  aws_secret_access_key=S3_SECRET_KEY,
                  region_name='us-east-1')

# 모델 관리 변수
MODELS_DATA = {}


def _set_db_status(available: bool, error: Exception | None = None) -> None:
    DB_STATUS["available"] = available
    DB_STATUS["last_checked_at"] = datetime.datetime.now().isoformat()
    DB_STATUS["last_error"] = None if error is None else str(error)
    DB_STATUS["url"] = _mask_db_url(DB_URL)

# =====================================================================
# 2. 핵심 비즈니스 로직 (추론 및 결과 전파)
# =====================================================================
def process_inference_and_save(data: Dict[str, Any]):
    """실시간 혹은 백엔드로부터 전달받은 배치 데이터를 모델별 추론 후 DB 저장 및 백엔드 전송"""
    print(f"[RAW] 추론 입력 수신 | {json.dumps(data, ensure_ascii=False, default=str)}")
    if not MODELS_DATA:
        print("⚠️ 로드된 모델이 없어 추론을 건너뜁니다.")
        return {"error": "no models loaded"}

def initialize_db_engine() -> None:
    global engine

    try:
        for sys_name, assets in MODELS_DATA.items():
            conf = assets["config"]
            feats = conf["features"]
            
            # 1) 데이터 전처리 (누락 시 0.0 보간)
            input_vals = [float(data.get(f, 0.0)) for f in feats]
            scaled = assets["scaler"].transform(pd.DataFrame([input_vals], columns=feats))
            
            # 2) 모델 추론 (MSE 계산)
            pred = assets["model"].predict(scaled, verbose=0)
            mse = float(np.mean(np.power(scaled - pred, 2)))

            # 3) 알람 레벨 판별
            lvl, lbl = 0, "Normal"
            if mse >= conf["threshold_error"]: lvl, lbl = 3, "Error 🔴"
            elif mse >= conf["threshold_warning"]: lvl, lbl = 2, "Warning 🟠"
            elif mse >= conf["threshold_caution"]: lvl, lbl = 1, "Caution 🔸"

            # 4) 원인 분석 (RCA)
            feat_errors = np.power(scaled - pred, 2)[0]
            err_sum = np.sum(feat_errors) if np.sum(feat_errors) > 0 else 1e-10
            rca = sorted([
                {"feature": n, "contribution": round((float(e)/err_sum)*100, 1)}
                for n, e in zip(feats, feat_errors)
            ], key=lambda x: x["contribution"], reverse=True)[:3]

            domain_reports[sys_name] = {
                "score": round(mse, 6),
                "alarm": {"level": lvl, "label": lbl},
                "rca": rca
            }
            print(f"[INFERENCE] {sys_name.upper()} | score={round(mse,6)} | alarm={lbl} | rca={rca}")


        print(f"[INFERENCE] 최종 결과 | overall_level={max_level} | status={final_status} | {json.dumps(domain_reports, ensure_ascii=False)}")

        # 6) DB 저장
        with engine.connect() as conn:
            query = sa.text("""
                INSERT INTO inference_history (
                    sensor_id, overall_level, overall_status,
                    inference_result, action_required, data_timestamp
                ) VALUES (:sid, :lvl, :status, :res, :act, :ts)
            """)
            conn.execute(query, {
                "sid": payload["sensor_id"], "lvl": payload["overall_alarm_level"],
                "status": payload["overall_status"], "res": json.dumps(payload["domain_reports"]),
                "act": payload["action_required"], "ts": payload["timestamp"]
            })
            conn.commit()

        return payload

    except Exception as e:
        _update_batch_status(False, e)
        logger.error("❌ [BATCH] 실패: %s", e, exc_info=True)


# =====================================================================
# 3. 추론 배치 (1분마다 S3 최신 데이터 → 추론 → DB 저장)
# =====================================================================
def run_inference_batch():
    try:
        print(f"🔬 [추론 배치] S3 최신 파일 탐색 중...")
        response = s3.list_objects_v2(Bucket=BUCKET_NAME)
        if 'Contents' not in response:
            print("⚠️ [추론 배치] S3 버킷이 비어있음, 스킵")
            return

        csv_files = [f for f in response['Contents'] if f['Key'].endswith('.csv')]
        if not csv_files:
            return

        latest_file = sorted(csv_files, key=lambda x: x['LastModified'], reverse=True)[0]
        obj = s3.get_object(Bucket=BUCKET_NAME, Key=latest_file['Key'])
        df = pd.read_csv(BytesIO(obj['Body'].read()))

        if not df.empty:
            avg_record = df.mean(numeric_only=True).to_dict()
            avg_record["timestamp"] = latest_file['LastModified'].isoformat()
            print(f"🚀 [추론 배치] 추론 시작 | 파일={latest_file['Key']}")
            process_inference_and_save(avg_record)
    except Exception as e:
        print(f"❌ [추론 배치 Error] {e}")

# =====================================================================
# 4. FastAPI Lifespan 및 서버 설정
# =====================================================================
MODELS_DATA = {}


# 경로 설정 (src/inference_api.py 기준 상위 models 폴더)
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
save_dir = os.path.join(project_root, "models")

# 🌟 [방법 1 적용] models 폴더를 뒤져서 config 파일 자동 찾기
logger.info("⏳ Loading Multi-Domain Models & Configs...")

# models 폴더 안에 있는 모든 '_config.json' 파일의 경로를 리스트로 가져옵니다.
config_files = glob.glob(os.path.join(save_dir, "*_config.json"))

# 파일명에서 앞부분(도메인 이름)만 쏙 빼서 SYSTEMS 리스트를 자동으로 만듭니다.
# 예: ".../models/motor_config.json" -> "motor"
SYSTEMS = [os.path.basename(f).replace("_config.json", "") for f in config_files]

if not SYSTEMS:
    logger.warning("⚠️ models 폴더에 학습된 모델(config)이 하나도 없습니다!")
else:
    logger.info(f"🔍 감지된 도메인 모델들: {SYSTEMS}")

try:
    for sys_name in SYSTEMS:
        # 각 시스템별 파일 로드
        model_path = os.path.join(save_dir, f"{sys_name}_model.keras")
        scaler_path = os.path.join(save_dir, f"{sys_name}_scaler.pkl")
        config_path = os.path.join(save_dir, f"{sys_name}_config.json")

        # # 3가지 아티팩트(모델, 스케일러, 설정) 중 하나라도 없으면 스킵
        if not all(os.path.exists(p) for p in [model_path, scaler_path, config_path]):
            logger.warning(
                f"⚠️ {sys_name.upper()} 모델 파일 일부가 누락되었습니다. 스킵합니다."
            )
            continue

        MODELS_DATA[sys_name] = {
            "model": tf.keras.models.load_model(model_path),
            "scaler": joblib.load(scaler_path),
            "config": json.load(open(config_path, "r")),
        }
    logger.info(f"✅ {len(MODELS_DATA)}개의 서브 시스템 모델 로드 완료!")

except Exception as e:
    logger.error(f"❌ 초기화 중 치명적 에러 발생: {e}")


# =====================================================================
# 2. 실시간 다중 도메인 추론 파이프라인 (/predict + 배치 공용)
# =====================================================================
def run_inference_pipeline(
    realtime_data: Dict[str, Any],
    trigger_source: str = "external-request",
) -> Dict[str, Any]:
    if not MODELS_DATA:
        logger.error("❌ 추론 요청이 들어왔으나 로드된 모델이 없습니다.")
        raise HTTPException(status_code=503, detail="사용 가능한 모델이 없습니다.")

    sensor_id = str(realtime_data.get("sensor_id", DEFAULT_SENSOR_ID))
    logger.info(
        "📥 [PIPELINE] inference 요청 수신 source=%s sensor_id=%s timestamp=%s input_keys=%d",
        trigger_source,
        sensor_id,
        realtime_data.get("timestamp"),
        len(realtime_data),
    )

    final_results = {}
    total_alarm_level = 0
    overall_status = "Normal 🟢"

    try:
        for sys_name, data in MODELS_DATA.items():
            model = data["model"]
            scaler = data["scaler"]
            config = data["config"]
            features = config["features"]
            t_caut, t_warn, t_err = (
                config["threshold_caution"],
                config["threshold_warning"],
                config["threshold_critical"],
            )

            # 1. 데이터 추출 및 추론
            input_values = [float(realtime_data.get(f, 0.0)) for f in features]
            missing = [f for f in features if f not in realtime_data]
            if missing:
                logger.warning(
                    "⚠️  [PIPELINE] domain=%s 입력에 없는 feature=%d 개 → 0.0 대체 samples=%s",
                    sys_name,
                    len(missing),
                    missing[:5],
                )
            raw_df = pd.DataFrame([input_values], columns=features)

            scaled_array = scaler.transform(raw_df)
            pred_array = model.predict(scaled_array, verbose=0)

            # 🌟 알람 근거 == 설명 일치:
            # train.py가 threshold 계산에 쓴 것과 동일한 피처 셋으로 MSE를 낸다.
            # config에 "scoring_features"가 있으면 그것을, 없으면(구버전 모델)
            # DEFAULT_CONTEXT_FEATURES로 동적 계산해 폴백.
            sq_err = np.power(scaled_array - pred_array, 2)[0]
            scoring_features = config.get("scoring_features")
            if scoring_features:
                scoring_mask = np.array(
                    [f in set(scoring_features) for f in features], dtype=bool
                )
            else:
                scoring_mask = actionable_feature_mask(features)
            if scoring_mask.sum() == 0:
                scoring_mask = np.ones(len(features), dtype=bool)
            mse_score = float(np.mean(sq_err[scoring_mask]))

            # 2. [함수 사용] 알람 레벨 판정
            alarm_level, label = get_alarm_status(mse_score, t_caut, t_warn, t_err)
            logger.info(
                "🔬 [PIPELINE] domain=%s mse=%.6f thresholds(c/w/e)=%.6f/%.6f/%.6f → level=%s label=%s",
                sys_name,
                mse_score,
                t_caut,
                t_warn,
                t_err,
                alarm_level,
                label,
            )

            # 2-1. 기동 직후 5분은 정상 스파이크 → 알람 억제(운영 모드 gating)
            if int(realtime_data.get("is_startup_phase", 0)) == 1:
                logger.info(
                    "🔄 [PIPELINE] domain=%s is_startup_phase=1 → 알람 억제", sys_name
                )
                alarm_level, label = 0, "Normal (startup gated)"

            # 3. [함수 사용] RCA(원인 분석) 계산
            rca = calculate_rca(sq_err, features, top_n=3)

            # 4. [함수 사용] 프론트엔드 차트용 상세 데이터(시그마 밴드 등) 생성
            pred_raw_array = scaler.inverse_transform(pred_array)[
                0
            ]  # 1차원 리스트로 축소
            # train.py는 "feature_stds"(평탄 dict: name→std값)로 저장하므로
            # 기존 config와 호환되게 같은 키로 읽는다.
            feature_stds = config.get("feature_stds", {})
            # 🔬 피처별 threshold가 있으면 feature_details에 포함
            per_feature_thresholds = config.get("per_feature_thresholds", None)
            feature_details = build_feature_details(
                input_values,
                pred_raw_array,
                features,
                feature_stds,
                scaled_errors=sq_err,
                per_feature_thresholds=per_feature_thresholds,
            )
            # 5. 결과 조립
            final_results[sys_name] = {
                "metrics": {
                    "current_mse": round(mse_score, 6),
                    "train_loss": config.get("train_loss", "N/A"),
                    "val_loss": config.get("val_loss", "N/A"),
                },
                "alarm": {"level": alarm_level, "label": label},
                "global_thresholds": {
                    "caution": round(t_caut, 6),
                    "warning": round(t_warn, 6),
                    "critical": round(t_err, 6),
                },
                "per_feature_thresholds": config.get("per_feature_thresholds", {}),
                "rca_top3": rca,
                "feature_details": feature_details,
                "target_reference_profiles": config.get(
                    "target_reference_profiles", {}
                ),
            }

            # 전체 알람 수위 갱신 (가장 심각한 쪽 기준)
            if alarm_level > total_alarm_level:
                total_alarm_level = alarm_level
                overall_status = label

    print(f"⏰ 총 {len(MODELS_DATA)}개 모델 로드됨. 배치 스케줄러 가동 중...")
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_inference_batch, 'interval', minutes=1)
    scheduler.start()
    yield
    scheduler.shutdown()
    print("🛑 시스템 종료")


@app.post("/predict")
def predict_multi_domain(realtime_data: Dict[str, Any] = Body(...)):
    return run_inference_pipeline(realtime_data, trigger_source="external-request")


@app.on_event("startup")
def startup_scheduler() -> None:
    global scheduler

    if scheduler is not None:
        return

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_inference_batch,
        "interval",
        minutes=BATCH_STATUS["interval_minutes"],
        id="inference_s3_batch",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info(
        "Started scheduled inference batch interval=%s minute(s)",
        BATCH_STATUS["interval_minutes"],
    )


@app.on_event("shutdown")
def shutdown_scheduler() -> None:
    global scheduler

    if scheduler is None:
        return

    scheduler.shutdown(wait=False)
    scheduler = None
    logger.info("Stopped scheduled inference batch")


@app.get("/health")
def health_check():
    return {
        "status": "ok" if MODELS_DATA else "degraded",
        "models_loaded": list(MODELS_DATA.keys()),
        "db": DB_STATUS,
        "batch": BATCH_STATUS,
        "trigger_mode": "external-request-plus-scheduled-batch",
    }


if __name__ == "__main__":
    import uvicorn

    logger.info("🌐 Uvicorn 웹 서버를 시작합니다... (http://127.0.0.1:8000/docs)")
    uvicorn.run("inference_api:app", host="0.0.0.0", port=8000, reload=True)

# 압력 대비 전력 효율 : pressure_per_power = discharge_pressure / (motor_power + ε)
