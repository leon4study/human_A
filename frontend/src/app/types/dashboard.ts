// 환경 정보 
export interface EnvironmentItem {
  id: string;
  label: string;
  value: number | string;
  unit: string;
}

// CTP 상태 카드용 타입
export interface CtpStatusItem {
  id: string;
  label: string;
  value: number;
  unit: string;
  status: "normal" | "warning" | "danger";
}

// CTP 시각화용 타입
export interface CtpVisualizationMetric {
  id: string;
  label: string;
  value: number;
  unit: string;
  direction: "high" | "low";
  caution: number;
  warning: number;
  critical: number;
  trend: number[];
}

// KPI 현황
export interface KpiItem {
  id: string;
  label: string;
  value: number;
  color: "green" | "orange" | "blue";
  size: "small" | "large";
}

// Alert 이력
export interface AlertItem {
  id: string;
  date: string;
  time: string;
  equipment: string;
  cause: string;
  level: string;
}

// 구역별 막힘 상태
export interface ZoneItem {
  id: string;
  label: string;
  blockageRate: number;
}

// 구역별 막힘 원인 Top 3
export interface ZoneCauseItem {
  id: string;
  zoneId: string;
  equipment: string;
  cause: string;
  count: number;
}

// 대시보드 소켓 메시지 타입
export interface DashboardSocketPayload {
  systemStatus?: "normal" | "warning" | "danger";
  environment?: EnvironmentItem[];
  ctpStatusItems?: CtpStatusItem[];
  ctpVisualizationMetrics?: CtpVisualizationMetric[];
  kpiItems?: KpiItem[];
  alertItems?: AlertItem[];
  zoneItems?: ZoneItem[];
}

// 백엔드에서 MQTT로 들어오는 원시 센서 페이로드
export interface RawSensorPayload {
  timestamp?: string;
  light_ppfd_umol_m2_s?: number;
  air_temp_c?: number;
  relative_humidity_pct?: number;
  co2_ppm?: number;
  raw_tank_level_pct?: number;
  raw_water_temp_c?: number;
  pump_rpm?: number;
  flow_rate_l_min?: number;
  suction_pressure_kpa?: number;
  discharge_pressure_kpa?: number;
  motor_current_a?: number;
  motor_power_kw?: number;
  bearing_vibration_rms_mm_s?: number;
  motor_temperature_c?: number;
  bearing_temperature_c?: number;
  filter_pressure_in_kpa?: number;
  filter_pressure_out_kpa?: number;
  turbidity_ntu?: number;
  mix_target_ec_ds_m?: number;
  mix_ec_ds_m?: number;
  mix_target_ph?: number;
  mix_ph?: number;
  mix_temp_c?: number;
  mix_flow_l_min?: number;
  dosing_acid_ml_min?: number;
  drain_ec_ds_m?: number;
  tank_a_level_pct?: number;
  tank_b_level_pct?: number;
  acid_tank_level_pct?: number;
  zone1_flow_l_min?: number;
  zone1_pressure_kpa?: number;
  zone1_substrate_moisture_pct?: number;
  zone1_substrate_ec_ds_m?: number;
  zone1_substrate_ph?: number;
  zone2_flow_l_min?: number;
  zone2_pressure_kpa?: number;
  zone2_substrate_moisture_pct?: number;
  zone2_substrate_ec_ds_m?: number;
  zone2_substrate_ph?: number;
  zone3_flow_l_min?: number;
  zone3_pressure_kpa?: number;
  zone3_substrate_moisture_pct?: number;
  zone3_substrate_ec_ds_m?: number;
  zone3_substrate_ph?: number;
  [key: string]: unknown;
}

// 백엔드 INFERENCE 배치 페이로드
export interface InferencePayload {
  sensor_id?: string;
  overall_alarm_level?: string;
  overall_status?: string;
  domain_reports?: unknown;
  action_required?: boolean;
  timestamp?: string;
  [key: string]: unknown;
}

// 백엔드 → 프론트 웹소켓 메시지
export interface BackendRawMessage {
  type: "RAW";
  payload: RawSensorPayload;
}

export interface BackendInferenceMessage {
  type: "INFERENCE";
  payload: InferencePayload;
}

// 대시보드 소켓 메시지 타입
export interface DashboardSocketMessage {
  type: "dashboard_init" | "dashboard_update";
  payload: DashboardSocketPayload;
}

export type AnySocketMessage =
  | DashboardSocketMessage
  | BackendRawMessage
  | BackendInferenceMessage;