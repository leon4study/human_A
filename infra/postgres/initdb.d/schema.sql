-- 1. 센서 마스터 정보 (기존과 동일)
CREATE TABLE IF NOT EXISTS sensors (
    sensor_id VARCHAR(50) PRIMARY KEY, 
    location VARCHAR(100) NOT NULL,
    sensor_type VARCHAR(50) NOT NULL, 
    created_at TIMESTAMP DEFAULT NOW()
);

-- 2. 통합 추론 결과 이력 (수정됨)
CREATE TABLE IF NOT EXISTS inference_history (
    id SERIAL PRIMARY KEY,
    sensor_id VARCHAR(50) REFERENCES sensors(sensor_id),
    
    -- [엔지니어링 포인트] 전체 시스템 상태 요약
    -- 대시보드에서 '전체 상태가 Error인 것만' 필터링할 때 성능을 위해 컬럼으로 유지합니다.
    overall_level INTEGER NOT NULL,      -- 0: Normal, 1: Caution, 2: Warning, 3: Error
    overall_status VARCHAR(50),          -- 'Normal 🟢', 'Error 🔴' 등
    
    -- [핵심] 분석 데이터 전체 (JSONB)
    -- 분석가가 준 domain_reports(각 모델별 점수, RCA) 전체를 통째로 저장합니다.
    -- 모델이 2개에서 10개로 늘어나도 이 컬럼 하나면 충분합니다.
    inference_result JSONB NOT NULL,     
    
    -- 조치 권고 사항
    action_required TEXT, 
    
    -- 시점 정보
    data_timestamp TIMESTAMP WITH TIME ZONE NOT NULL, 
    created_at TIMESTAMP DEFAULT NOW()
);

-- 인덱스: 최신 알람 및 시계열 조회 최적화
-- JSONB 내부의 특정 모델 점수를 인덱싱하고 싶다면 추후 GIN 인덱스 추가 가능
CREATE INDEX idx_inference_history_status ON inference_history (overall_level DESC, data_timestamp DESC);
CREATE INDEX idx_inference_history_sid ON inference_history (sensor_id, data_timestamp DESC);

-- 초기 기초 데이터 (실제 센서 ID와 일치시킴)
INSERT INTO sensors (sensor_id, location, sensor_type) 
VALUES ('SF-ZONE-01-MAIN', 'Greenhouse-A', 'smart_emitter_complex')
ON CONFLICT (sensor_id) DO NOTHING;