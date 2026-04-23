// 환경정보 카드에 바로 표시하는 값 타입
export interface EnvironmentItem {
  id: string;
  label: string;
  value: number | string;
  unit: string;
}

// CTP 상태 카드 한 칸에 표시용 값 타입
export interface CtpStatusItem {
  id: string;
  label: string;
  value: number;
  unit: string;
  status: "normal" | "warning" | "danger";
}

export type CtpThresholdMode = "high" | "low" | "range";

// CTP 시각화는 현재값 + trend + threshold series를 같이 포함 필요
// threshold가 바뀌어도 alert 이력과 섞이지 않게 화면용 데이터만 따로 저장
export interface CtpVisualizationMetric {
  id: string;
  label: string;
  value: number;
  unit: string;
  // direction은 기존 단방향 기준이다
  // high: 높아질수록 위험 / low: 낮아질수록 위험
  direction: "high" | "low";
  // range는 upper/lower를 둘 다 보는 값에 사용
  thresholdMode?: CtpThresholdMode;
  caution: number;
  warning: number;
  critical: number;
  cautionLower?: number;
  warningLower?: number;
  criticalLower?: number;
  // trend는 CTP 시각화에 그릴 값 시계열이다
  trend: number[];
  // timestamps는 trend 각 점의 실제 시각이다
  timestamps?: number[];
  // threshold도 시간에 따라 바뀔 수 있어서 series로 따로 들고 간다
  cautionTrend?: number[];
  warningTrend?: number[];
  criticalTrend?: number[];
  cautionLowerTrend?: number[];
  warningLowerTrend?: number[];
  criticalLowerTrend?: number[];
  // thresholdSource를 보면 이 값이 inference payload 어디서 왔는지 추적할 수 존재
  thresholdSource?: string;
  thresholdUpdatedAt?: number;
}

// KPI 현황
export interface KpiItem {
  id: string;
  label: string;
  value: number;
  color: "green" | "orange" | "blue";
  size: "small" | "large";
}

// Alert 패널 한 줄에 표시용 데이터 타입
// type / cause / level은 inference 결과에서 꺼내서 화면용 문자열로 바꾼 값이다
export interface AlertItem {
  id: string;
  date: string;
  time: string;
  type: string;
  cause: string;
  level: string;
}

// 구역별 막힘 상태 카드/차트용 타입
export interface ZoneItem {
  id: string;
  label: string;
  blockageRate: number;
}

// 구역별 원인 Top3 차트용 타입
export interface ZoneCauseItem {
  id: string;
  zoneId: string;
  equipment: string;
  cause: string;
  count: number;
}

export interface InferenceHistoryRow {
  sensor_id?: string;
  overall_alarm_level?: number;
  overall_status?: string | null;
  action_required?: string | null;
  timestamp?: string | null;
  data_timestamp?: string | null;
  domain_reports?: Record<string, InferenceDomainReport>;
  inference_result?: Record<string, InferenceDomainReport>;
}

// 프론트가 받아서 바로 화면에 넣는 대시보드 메시지 타입
export interface DashboardSocketPayload {
  systemStatus?: "normal" | "warning" | "danger";
  environment?: EnvironmentItem[];
  ctpStatusItems?: CtpStatusItem[];
  ctpVisualizationMetrics?: CtpVisualizationMetric[];
  kpiItems?: KpiItem[];
  alertItems?: AlertItem[];
  zoneItems?: ZoneItem[];
}

// RAW는 장비/센서에서 들어오는 원본 데이터다
// 프론트는 이 값을 바로 카드에 쓰거나 파생 계산의 재료로 사용
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

// INFERENCE는 모델이 계산한 결과 묶음이다
// alert, threshold, RCA 같은 값은 RAW가 아니라 여기서 읽음
export interface InferenceRcaItem {
  feature: string;
  contribution: number;
}

export interface InferenceDomainAlarm {
  level: number; // 0=Normal, 1=Caution, 2=Warning, 3=Critical
  label: string;
  한글?: string;
}

export interface InferenceDomainReport {
  score?: number;
  alarm: InferenceDomainAlarm;
  rca?: InferenceRcaItem[];
  rca_top3?: InferenceRcaItem[];
  metrics?: unknown;
  global_thresholds?: unknown;
  feature_details?: unknown;
  target_reference_profiles?: unknown;
  도메인명?: string;
}

export interface SpikeInfo {
  is_spike?: boolean;
  is_startup_spike?: boolean;
  is_anomaly_spike?: boolean;
}

// 웹소켓 inference와 /predict 응답을 프론트에서 같은 형태로 다루기 위한 타입
export interface InferencePayload {
  sensor_id?: string;
  overall_alarm_level: number;
  overall_status: string | null;
  spike_info?: SpikeInfo;
  domain_reports: Record<string, InferenceDomainReport>;
  action_required: string | null;
  timestamp: string;
}

// 웹소켓으로 들어올 수 있는 메시지 종류
export interface BackendRawMessage {
  type: "RAW";
  payload: RawSensorPayload;
}

export interface BackendInferenceMessage {
  type: "INFERENCE";
  payload: InferencePayload;
}

// 프론트가 받아서 바로 화면에 넣는 대시보드 메시지 타입
export interface DashboardSocketMessage {
  type: "dashboard_init" | "dashboard_update";
  payload: DashboardSocketPayload;
}

export type AnySocketMessage =
  | DashboardSocketMessage
  | BackendRawMessage
  | BackendInferenceMessage;