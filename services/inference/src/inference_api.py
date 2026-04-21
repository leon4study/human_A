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
from apscheduler.schedulers.background import BackgroundScheduler

# 분리해둔 추론 함수들 불러오기
from inference_core import (
    actionable_feature_mask,
    build_feature_details,
    calculate_rca,
    get_alarm_status
)
from preprocessing import step1_prepare_window_data


app = FastAPI(title="SmartFarm Multi-Domain 예지보전 API")
logger = get_logger("API")


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

DB_URL = os.getenv(
    "AI_DATABASE_URL",
    "postgresql://farmer:plant_rich@localhost:5432/smartfarm",
)
DEFAULT_SENSOR_ID = os.getenv("AI_SENSOR_ID", "SF-ZONE-01-MAIN")
engine = None
DB_STATUS = {
    "available": False,
    "last_checked_at": None,
    "last_error": None,
    "url": None,
}
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:9000")
S3_ACCESS_KEY = os.getenv("MINIO_ROOT_USER", "admin")
S3_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", "password123")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "raw-data")
S3_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
s3 = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
    region_name=S3_REGION,
)
scheduler = None
BATCH_STATUS = {
    "enabled": True,
    "interval_minutes": 1,
    "last_run_at": None,
    "last_success_at": None,
    "last_error": None,
    "last_source_key": None,
    "last_processed_etag": None,
    "last_rows_read": 0,
}


# =====================================================================
# DB 연결/상태 관리
# =====================================================================
def _mask_db_url(db_url: str) -> str:
    try:
        return str(sa.engine.make_url(db_url).render_as_string(hide_password=True))
    except Exception:
        return "<invalid-db-url>"


def _set_db_status(available: bool, error: Exception | None = None) -> None:
    DB_STATUS["available"] = available
    DB_STATUS["last_checked_at"] = datetime.datetime.now().isoformat()
    DB_STATUS["last_error"] = None if error is None else str(error)
    DB_STATUS["url"] = _mask_db_url(DB_URL)


def initialize_db_engine() -> None:
    global engine

    try:
        candidate = sa.create_engine(DB_URL, pool_pre_ping=True)
        with candidate.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
        engine = candidate
        _set_db_status(True)
        logger.info("Inference DB engine initialized and connection verified")
    except Exception as e:
        engine = None
        _set_db_status(False, e)
        logger.error(f"Failed to initialize inference DB engine: {e}", exc_info=True)


initialize_db_engine()


def save_inference_history(sensor_id: str, payload: Dict[str, Any]) -> None:
    """Persist one inference response into inference_history when DB is available."""
    if engine is None:
        logger.warning(
            "DB engine is unavailable before insert; attempting reconnect once"
        )
        initialize_db_engine()
        if engine is None:
            logger.error(
                "Skip inference_history insert because DB engine is unavailable"
            )
            return

    try:
        with engine.begin() as conn:
            query = sa.text(
                """
                INSERT INTO inference_history (
                    sensor_id, overall_level, overall_status,
                    inference_result, action_required, data_timestamp
                ) VALUES (:sid, :lvl, :status, :res, :act, :ts)
                """
            )
            conn.execute(
                query,
                {
                    "sid": sensor_id,
                    "lvl": payload["overall_alarm_level"],
                    "status": payload["overall_status"],
                    "res": json.dumps(
                        payload["domain_reports"],
                        ensure_ascii=False,
                        default=str,
                    ),
                    "act": payload["action_required"],
                    "ts": payload["timestamp"],
                },
            )
        _set_db_status(True)
        logger.info(
            "Saved inference_history row sensor_id=%s overall_level=%s timestamp=%s",
            sensor_id,
            payload["overall_alarm_level"],
            payload["timestamp"],
        )
    except Exception as e:
        _set_db_status(False, e)
        logger.error(
            "Failed to save inference_history sensor_id=%s timestamp=%s: %s",
            sensor_id,
            payload.get("timestamp"),
            e,
            exc_info=True,
        )


# =====================================================================
# S3 배치 폴링
# =====================================================================
def _update_batch_status(success: bool, error: Exception | None = None) -> None:
    BATCH_STATUS["last_run_at"] = datetime.datetime.now().isoformat()
    if success:
        BATCH_STATUS["last_success_at"] = BATCH_STATUS["last_run_at"]
        BATCH_STATUS["last_error"] = None
    elif error is not None:
        BATCH_STATUS["last_error"] = str(error)


def _build_batch_payload_from_dataframe(
    df_raw: pd.DataFrame,
    source_key: str,
    source_timestamp: str,
) -> Dict[str, Any] | None:
    logger.info(
        "🧱 [BATCH] payload 빌드 시작 key=%s shape=%s columns=%s",
        source_key,
        df_raw.shape,
        list(df_raw.columns)[:10] + (["..."] if len(df_raw.columns) > 10 else []),
    )
    if df_raw.empty:
        logger.warning("🧱 [BATCH] 빈 데이터프레임 — payload=None")
        return None

    if "timestamp" in df_raw.columns:
        try:
            prepared_raw = df_raw.copy()
            prepared_raw["timestamp"] = pd.to_datetime(prepared_raw["timestamp"])
            prepared_raw = prepared_raw.sort_values("timestamp").set_index("timestamp")
            logger.info(
                "🧱 [BATCH] timestamp 정렬 완료 range=%s ~ %s rows=%d",
                prepared_raw.index.min(),
                prepared_raw.index.max(),
                len(prepared_raw),
            )
            df_window, _ = step1_prepare_window_data(
                prepared_raw, window_method="tumbling"
            )
            logger.info(
                "🧱 [BATCH] tumbling 집계 완료 window_shape=%s", df_window.shape
            )
            if not df_window.empty:
                payload = df_window.iloc[-1].to_dict()
                payload["timestamp"] = source_timestamp
                logger.info(
                    "🧱 [BATCH] 마지막 window 선택 payload_keys=%d sample_keys=%s",
                    len(payload),
                    list(payload.keys())[:8],
                )
                return payload
        except Exception as e:
            logger.warning(
                "🧱 [BATCH] Batch preprocessing failed for key=%s; falling back to numeric mean: %s",
                source_key,
                e,
            )

    numeric_payload = df_raw.mean(numeric_only=True).to_dict()
    if not numeric_payload:
        logger.warning("🧱 [BATCH] numeric fallback도 비어있음 — payload=None")
        return None
    numeric_payload["timestamp"] = source_timestamp
    logger.info(
        "🧱 [BATCH] numeric mean fallback 사용 keys=%d", len(numeric_payload)
    )
    return numeric_payload


def run_inference_batch() -> None:
    BATCH_STATUS["last_run_at"] = datetime.datetime.now().isoformat()
    logger.info("========================================================")
    logger.info("🚀 [BATCH] 시작 at=%s", BATCH_STATUS["last_run_at"])

    try:
        logger.info(
            "🔍 [BATCH] S3 polling bucket=%s endpoint=%s",
            S3_BUCKET_NAME,
            S3_ENDPOINT,
        )
        response = s3.list_objects_v2(Bucket=S3_BUCKET_NAME)
        contents = response.get("Contents", [])
        csv_files = [item for item in contents if item["Key"].endswith(".csv")]
        logger.info(
            "🔍 [BATCH] 총 객체=%d, CSV=%d", len(contents), len(csv_files)
        )

        if not csv_files:
            _update_batch_status(True)
            logger.info("⚪ [BATCH] CSV 없음 — 종료")
            return

        latest_file = max(csv_files, key=lambda item: item["LastModified"])
        latest_etag = latest_file.get("ETag")
        logger.info(
            "📄 [BATCH] latest key=%s last_modified=%s size=%s etag=%s",
            latest_file["Key"],
            latest_file["LastModified"],
            latest_file.get("Size"),
            latest_etag,
        )

        if (
            latest_file["Key"] == BATCH_STATUS["last_source_key"]
            and latest_etag == BATCH_STATUS["last_processed_etag"]
        ):
            _update_batch_status(True)
            logger.info(
                "⏭️  [BATCH] 이미 처리한 파일 — skip key=%s", latest_file["Key"]
            )
            return

        logger.info("⬇️  [BATCH] S3 get_object 다운로드 시작 key=%s", latest_file["Key"])
        obj = s3.get_object(Bucket=S3_BUCKET_NAME, Key=latest_file["Key"])
        df_raw = pd.read_csv(BytesIO(obj["Body"].read()))
        BATCH_STATUS["last_rows_read"] = int(len(df_raw))
        logger.info(
            "⬇️  [BATCH] CSV 로드 완료 rows=%d cols=%d", len(df_raw), df_raw.shape[1]
        )

        source_timestamp = latest_file["LastModified"].isoformat()
        payload = _build_batch_payload_from_dataframe(
            df_raw=df_raw,
            source_key=latest_file["Key"],
            source_timestamp=source_timestamp,
        )
        if payload is None:
            _update_batch_status(True)
            logger.warning(
                "⚠️  [BATCH] payload 생성 실패 — skip key=%s", latest_file["Key"]
            )
            return

        logger.info(
            "🤖 [BATCH] 추론 파이프라인 호출 key=%s rows=%s payload_timestamp=%s",
            latest_file["Key"],
            len(df_raw),
            payload.get("timestamp"),
        )
        result = run_inference_pipeline(payload, trigger_source="scheduled-batch")
        logger.info(
            "✅ [BATCH] 추론 완료 overall_level=%s status=%s action=%s",
            result.get("overall_alarm_level"),
            result.get("overall_status"),
            result.get("action_required"),
        )
        BATCH_STATUS["last_source_key"] = latest_file["Key"]
        BATCH_STATUS["last_processed_etag"] = latest_etag
        _update_batch_status(True)
        logger.info("🏁 [BATCH] 종료 (성공) key=%s", latest_file["Key"])

    except Exception as e:
        _update_batch_status(False, e)
        logger.error("❌ [BATCH] 실패: %s", e, exc_info=True)


# =====================================================================
# 1. 멀티 모델 및 설정 로드 (서버 기동 시)
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

        # 6. 스파이크 정보 추출 (시뮬레이터가 전처리 후 넘겨준 값 passthrough)
        spike_info = {
            "is_spike": bool(realtime_data.get("is_spike", False)),
            "is_startup_spike": bool(realtime_data.get("is_startup_spike", False)),
            "is_anomaly_spike": bool(realtime_data.get("is_anomaly_spike", False)),
        }

        # 7. 최종 응답 페이로드
        # raw_inputs: 프론트가 파생변수(pressure_flow_ratio, dp_per_flow,
        # pressure_volatility, filter_delta_p 등) 만들 때 쓰도록 요청 원시값 passthrough.
        # filter 2개는 AE 모델엔 안 쓰지만 룰 기반 필터 페이지용으로 전달.
        raw_input_keys = [
            "discharge_pressure_kpa",
            "suction_pressure_kpa",
            "flow_rate_l_min",
            "motor_power_kw",
            "motor_temperature_c",
            "pump_rpm",
            "filter_pressure_in_kpa",
            "filter_pressure_out_kpa",
        ]
        raw_inputs = {
            k: float(realtime_data[k]) for k in raw_input_keys if k in realtime_data
        }

        response_payload = {
            "timestamp": realtime_data.get(
                "timestamp", datetime.datetime.now().isoformat()
            ),
            "overall_alarm_level": total_alarm_level,
            "overall_status": overall_status,
            "spike_info": spike_info,
            "raw_inputs": raw_inputs,
            "domain_reports": final_results,
            "action_required": (
                "System check recommended" if total_alarm_level >= 2 else "Optimal"
            ),
        }

        if total_alarm_level > 0:
            spike_tag = ""
            if spike_info["is_anomaly_spike"]:
                spike_tag = " ⚡[이상 스파이크]"
            elif spike_info["is_startup_spike"]:
                spike_tag = " 🔄[기동 스파이크]"
            logger.warning(
                f"🚨 [이상 감지] Level {total_alarm_level} ({overall_status}){spike_tag} - 타임스탬프: {response_payload['timestamp']}"
            )

        logger.info(
            "📦 [PIPELINE] 응답 조립 완료 overall_level=%s status=%s action=%s domains=%s",
            total_alarm_level,
            overall_status,
            response_payload["action_required"],
            list(final_results.keys()),
        )

        # 💾 DB persistence (inference_api2.py 에서 이식한 저장 로직)
        logger.info(
            "💾 [PIPELINE] DB 저장 시도 sensor_id=%s db_available=%s",
            sensor_id,
            DB_STATUS["available"],
        )
        save_inference_history(sensor_id, response_payload)
        if not DB_STATUS["available"]:
            logger.warning(
                "⚠️  [PIPELINE] DB 저장 미확정 상태로 응답 반환 source=%s sensor_id=%s timestamp=%s",
                trigger_source,
                sensor_id,
                response_payload["timestamp"],
            )

        return response_payload

    except Exception as e:
        # API 내부에서 파이썬 에러가 터졌을 때
        # exc_info=True 를 주면 에러가 난 몇 번째 줄인지 추적(Traceback) 정보까지 파일에 싹 다 저장됩니다.
        logger.error(f"❌ API 추론 중 내부 에러 발생: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
