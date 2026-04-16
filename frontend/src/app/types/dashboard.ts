export interface EnvironmentItem {
  id: string;
  label: string;
  value: number | string;
  unit: string;
}

export interface CtpMetric {
  id: string;
  label: string;
  value: number;
  unit: string;
  level: "normal" | "warning" | "danger";
  direction: "high" | "low";
  w1: number;
  w2: number;
  critical: number;  // 고장 기준
  trend: number[];
}

export interface KpiItem {
  id: string;
  label: string;
  value: number;
  color: "green" | "orange" | "blue";
  size: "small" | "large";
}

export interface AlertItem {
  id: string;
  time: string;
  equipment: string;
  cause: string;
  level: string;
}

export interface ZoneItem {
  id: string;
  label: string;
  blockageRate: number;
}

export interface ZoneCauseItem {
  id: string;
  zoneId: string;
  equipment: string;
  cause: string;
  count: number;
}

export interface DashboardSocketPayload {
  systemStatus?: "normal" | "warning" | "danger";
  environment?: EnvironmentItem[];
  ctpMetrics?: CtpMetric[];
  kpiItems?: KpiItem[];
  alertItems?: AlertItem[];
  zoneItems?: ZoneItem[];
}

export interface DashboardSocketMessage {
  type: "dashboard_init" | "dashboard_update";
  payload: DashboardSocketPayload;
}