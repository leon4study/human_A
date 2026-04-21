import type {
  AlertItem,
  CtpVisualizationMetric,
  EnvironmentItem,
  InferencePayload,
  RawSensorPayload,
} from "../types/dashboard";
import type { SystemStatus } from "../components/common/SystemStatus";

// 환경정보 id → 백엔드 컬럼
const ENVIRONMENT_COLUMN_MAP: Record<string, keyof RawSensorPayload> = {
  light: "light_ppfd_umol_m2_s",
  temp: "air_temp_c",
  humidity: "relative_humidity_pct",
  co2: "co2_ppm",
};

// CTP 카드/시각화 id → 백엔드 컬럼
const CTP_COLUMN_MAP: Record<string, keyof RawSensorPayload> = {
  "pump-discharge-flow": "flow_rate_l_min",
  "pump-discharge-pressure": "discharge_pressure_kpa",
  ph: "mix_ph",
  "motor-current": "motor_current_a",
};

// 설비 탱크 id → 백엔드 컬럼
export const TANK_COLUMN_MAP: Record<string, keyof RawSensorPayload> = {
  rawWaterTank: "raw_tank_level_pct",
  tankA: "tank_a_level_pct",
  tankB: "tank_b_level_pct",
  tankPH: "acid_tank_level_pct",
};

function pickNumber(raw: RawSensorPayload, key: keyof RawSensorPayload): number | undefined {
  const value = raw[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

export function mapEnvironment(
  raw: RawSensorPayload,
  prev: EnvironmentItem[],
): EnvironmentItem[] {
  return prev.map((item) => {
    const column = ENVIRONMENT_COLUMN_MAP[item.id];
    if (!column) return item;
    const value = pickNumber(raw, column);
    return value === undefined ? item : { ...item, value };
  });
}

export function mapCtpCurrentValues(
  raw: RawSensorPayload,
  prev: CtpVisualizationMetric[],
): CtpVisualizationMetric[] {
  return prev.map((metric) => {
    const column = CTP_COLUMN_MAP[metric.id];
    if (!column) return metric;
    const value = pickNumber(raw, column);
    return value === undefined ? metric : { ...metric, value };
  });
}

export interface TankLevels {
  rawTankLevel?: number;
  tankALevel?: number;
  tankBLevel?: number;
  acidTankLevel?: number;
}

export function mapTankLevels(raw: RawSensorPayload): TankLevels {
  return {
    rawTankLevel: pickNumber(raw, "raw_tank_level_pct"),
    tankALevel: pickNumber(raw, "tank_a_level_pct"),
    tankBLevel: pickNumber(raw, "tank_b_level_pct"),
    acidTankLevel: pickNumber(raw, "acid_tank_level_pct"),
  };
}

// CTP 시각화: 1시간 단위 MAX 집계 버퍼 (메트릭당 최대 12개 버킷)
const HOUR_MS = 60 * 60 * 1000;
const MAX_BUCKETS = 12;

export interface HourlyBucket {
  hourStart: number;
  max: number;
}

export type CtpTrendBuffers = Record<string, HourlyBucket[]>;

function parseTimestamp(value: string | undefined): number {
  if (!value) return Date.now();
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? Date.now() : parsed;
}

export function updateCtpTrendBuffers(
  buffers: CtpTrendBuffers,
  raw: RawSensorPayload,
  metrics: CtpVisualizationMetric[],
): CtpTrendBuffers {
  const ts = parseTimestamp(raw.timestamp);
  const hourStart = Math.floor(ts / HOUR_MS) * HOUR_MS;
  const next: CtpTrendBuffers = { ...buffers };

  for (const metric of metrics) {
    const column = CTP_COLUMN_MAP[metric.id];
    if (!column) continue;
    const value = pickNumber(raw, column);
    if (value === undefined) continue;

    const existing = next[metric.id] ?? [];
    const last = existing[existing.length - 1];

    if (last && last.hourStart === hourStart) {
      const updated = value > last.max ? { hourStart, max: value } : last;
      next[metric.id] = [...existing.slice(0, -1), updated];
    } else {
      const appended = [...existing, { hourStart, max: value }];
      next[metric.id] = appended.slice(-MAX_BUCKETS);
    }
  }

  return next;
}

export function applyBuffersToTrend(
  metrics: CtpVisualizationMetric[],
  buffers: CtpTrendBuffers,
): CtpVisualizationMetric[] {
  return metrics.map((metric) => {
    const buckets = buffers[metric.id];
    if (!buckets || buckets.length === 0) return metric;
    return { ...metric, trend: buckets.map((b) => b.max) };
  });
}

// INFERENCE → Alert/SystemStatus 매핑
const LEVEL_MAP: Record<string, string> = {
  caution: "CAUTION",
  warning: "WARNING",
  danger: "CRITICAL",
  critical: "CRITICAL",
};

export function mapInferenceLevel(level: string | undefined): string {
  if (!level) return "CAUTION";
  return LEVEL_MAP[level.toLowerCase()] ?? "CAUTION";
}

export function mapInferenceToSystemStatus(
  level: string | undefined,
): SystemStatus | undefined {
  if (!level) return undefined;
  const normalized = level.toLowerCase();
  if (normalized === "normal") return "normal";
  if (normalized === "warning" || normalized === "caution") return "warning";
  if (normalized === "danger" || normalized === "critical") return "danger";
  return undefined;
}

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}

export function mapInferenceToAlert(payload: InferencePayload): AlertItem | null {
  if (!payload.action_required) return null;

  const tsMs = parseTimestamp(payload.timestamp);
  const date = new Date(tsMs);
  const dateStr = `${date.getFullYear()}.${pad2(date.getMonth() + 1)}.${pad2(date.getDate())}`;
  const timeStr = `${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`;

  return {
    id: `alert-${tsMs}-${payload.sensor_id ?? "unknown"}`,
    date: dateStr,
    time: timeStr,
    equipment: payload.sensor_id ?? "알 수 없음",
    cause: payload.overall_status ?? "이상 감지",
    level: mapInferenceLevel(payload.overall_alarm_level),
  };
}
