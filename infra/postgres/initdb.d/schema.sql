-- 1. 센서 마스터 정보
CREATE TABLE IF NOT EXISTS sensors (
    sensor_id VARCHAR(50) PRIMARY KEY, 
    location VARCHAR(100) NOT NULL,
    sensor_type VARCHAR(50) NOT NULL, -- 예: 'smart_emitter_complex'
    created_at TIMESTAMP DEFAULT NOW()
);

-- 2. 추론 결과 이력 (분석 결과 전용)
CREATE TABLE IF NOT EXISTS inference_history (
    id SERIAL PRIMARY KEY,
    sensor_id VARCHAR(50) REFERENCES sensors(sensor_id),
    
    -- Score 정보 (MSE 등)
    mse_score FLOAT NOT NULL,
    log_mse_score FLOAT,
    
    -- Alarm 상태
    alarm_level INTEGER NOT NULL,     -- 0: Normal, 1: Caution, 2: Warning, 3: Error
    alarm_label VARCHAR(20),          -- 'Normal', 'Warning' 등
    is_anomaly BOOLEAN DEFAULT FALSE,
    
    -- RCA 및 조치 권고 (유연한 확장을 위해 JSONB 사용)
    -- [Portfolio Point] 단순 텍스트가 아닌 JSONB를 사용하여 향후 RCA 분석 쿼리 최적화 고려
    rca_report JSONB,                 -- Top 3 원인 분석 리포트
    action_required TEXT,             -- 조치 사항 내용
    
    -- 분석 기준점 (Thresholds) - 당시의 기준치를 기록하여 추후 모델 튜닝 참고
    threshold_values JSONB,           -- {caution: 0.1, warning: 0.2, ...}
    
    -- 시점 정보
    data_timestamp TIMESTAMP NOT NULL, -- 분석에 사용된 데이터의 시점 (Raw Data 기준)
    created_at TIMESTAMP DEFAULT NOW() -- DB에 저장된 시점
);

-- 인덱스: 최신 알람 발생 현황을 빠르게 조회하기 위함
CREATE INDEX idx_inference_history_alarm ON inference_history (alarm_level DESC, data_timestamp DESC);

-- 초기 기초 데이터
INSERT INTO sensors (sensor_id, location, sensor_type) 
VALUES ('SF-ZONE-01-MAIN', 'Greenhouse-A', 'drip_irrigation_system');