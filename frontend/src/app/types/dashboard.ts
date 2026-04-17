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

// 대시보드 소켓 메시지 타입
export interface DashboardSocketMessage {
  type: "dashboard_init" | "dashboard_update";
  payload: DashboardSocketPayload;
}