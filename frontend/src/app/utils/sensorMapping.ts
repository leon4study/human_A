import type {
  AlertItem,
  CtpVisualizationMetric,
  EnvironmentItem,
  InferenceDomainReport,
  InferencePayload,
  InferenceRcaItem,
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

// 배열 내용이 모두 같으면 true (참조만 다른 경우를 감지)
function numberArraysEqual(a: number[], b: number[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

export function mapEnvironment(
  raw: RawSensorPayload,
  prev: EnvironmentItem[],
): EnvironmentItem[] {
  let changed = false;
  const next = prev.map((item) => {
    const column = ENVIRONMENT_COLUMN_MAP[item.id];
    if (!column) return item;
    const value = pickNumber(raw, column);
    if (value === undefined || value === item.value) return item;
    changed = true;
    return { ...item, value };
  });
  // 값이 하나도 안 바뀌었다면 기존 배열 참조 그대로 반환 (불필요한 리렌더 방지)
  return changed ? next : prev;
}

export function mapCtpCurrentValues(
  raw: RawSensorPayload,
  prev: CtpVisualizationMetric[],
): CtpVisualizationMetric[] {
  let changed = false;
  const next = prev.map((metric) => {
    const column = CTP_COLUMN_MAP[metric.id];
    if (!column) return metric;
    const value = pickNumber(raw, column);
    if (value === undefined || value === metric.value) return metric;
    changed = true;
    return { ...metric, value };
  });
  return changed ? next : prev;
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
  let changed = false;
  const next = metrics.map((metric) => {
    const buckets = buffers[metric.id];
    if (!buckets || buckets.length === 0) return metric;
    const newTrend = buckets.map((b) => b.max);
    // trend 내용이 동일하면 기존 metric 참조 유지 → 리렌더 생략
    if (numberArraysEqual(metric.trend, newTrend)) return metric;
    changed = true;
    return { ...metric, trend: newTrend };
  });
  return changed ? next : metrics;
}

// INFERENCE overall_alarm_level 상수 (schema.sql 기준)
export const LEVEL_NORMAL = 0;
export const LEVEL_CAUTION = 1;
export const LEVEL_WARNING = 2;
export const LEVEL_ERROR = 3;

// 숫자 레벨 → Alert 테이블 표시 문자열
//   예상 외의 값이 오면 런타임 에러로 드러내 스키마 변경/데이터 오염을 즉시 감지한다.
export function levelToAlertLabel(level: number): string {
  switch (level) {
    case LEVEL_CAUTION:
      return "CAUTION";
    case LEVEL_WARNING:
      return "WARNING";
    case LEVEL_ERROR:
      return "CRITICAL";
    default:
      throw new Error(`Unexpected overall_alarm_level: ${level}`);
  }
}

// 10분 윈도우 기반 systemStatus 집계
export interface AlarmEvent {
  ts: number;
  level: number; // overall_alarm_level (0~3)
}

export const SYSTEM_STATUS_WINDOW_MS = 10 * 60 * 1000;

// 10분 윈도우 내 이벤트를 보고 systemStatus 판정
//   - Error(3) 1건 이상 → "danger"
//   - Caution(1) / Warning(2) 1건 이상 → "warning"
//   - 전부 Normal(0) 이거나 이벤트 없음 → "normal"
export function computeSystemStatus(
  events: AlarmEvent[],
  now: number,
): SystemStatus {
  let hasError = false;
  let hasAbnormal = false;

  for (const event of events) {
    if (now - event.ts > SYSTEM_STATUS_WINDOW_MS) continue;
    if (event.level === LEVEL_ERROR) {
      hasError = true;
      break;
    }
    if (event.level > LEVEL_NORMAL) hasAbnormal = true;
  }

  if (hasError) return "danger";
  if (hasAbnormal) return "warning";
  return "normal";
}

// 10분 이전 이벤트 제거
export function pruneAlarmEvents(
  events: AlarmEvent[],
  now: number,
): AlarmEvent[] {
  return events.filter((e) => now - e.ts <= SYSTEM_STATUS_WINDOW_MS);
}

export function parseTimestampToMs(value: string): number {
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) {
    throw new Error(`Invalid timestamp: ${value}`);
  }
  return parsed;
}

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}

// 도메인 코드 → 유형 한글명
const TYPE_LABEL_MAP: Record<string, string> = {
  motor: "모터",
  hydraulic: "수압/유압",
  nutrient: "양액/수질",
  zone_drip: "구역 점적",
};

// 피처 영문 키 → 원인 한글명
const FEATURE_LABEL_MAP: Record<string, string> = {
  discharge_pressure_kpa: "토출 압력 이상",
  pressure_roll_mean_10: "압력 10분 이동평균 이상",
  pressure_trend_10: "압력 10분 트렌드 이상",
  pressure_flow_ratio: "압력/유량 비율 이상",
  air_temp_c: "실내 기온 이상",
  motor_temperature_c: "모터 온도 상승 영향",
};

// rca_top3가 모두 제외 피처일 때 fallback으로 사용할 도메인별 대표 피처
const DOMAIN_FEATURE_MAP: Record<string, string[]> = {
  motor: ["discharge_pressure_kpa"],
  hydraulic: ["pressure_roll_mean_10", "pressure_trend_10"],
  nutrient: ["air_temp_c", "motor_temperature_c"],
  zone_drip: ["pressure_flow_ratio", "motor_temperature_c"],
};

// 원인 추출에서 제외할 컨텍스트 피처
const EXCLUDED_CAUSE_FEATURES = new Set(["time_sin", "time_cos"]);

// rca_top3에서 첫 "실제 원인이 될 수 있는" 피처를 선택
//  1순위: rca_top3에서 EXCLUDED 제외한 최상위 contribution
//  2순위: DOMAIN_FEATURE_MAP[domain][0]
function resolveCauseFeature(
  domain: string,
  rca: InferenceRcaItem[] | undefined,
): string | null {
  const picked = rca?.find((r) => !EXCLUDED_CAUSE_FEATURES.has(r.feature));
  if (picked) return picked.feature;
  return DOMAIN_FEATURE_MAP[domain]?.[0] ?? null;
}

// INFERENCE → AlertItem[] (도메인 단위로 1건씩)
//  - Normal(0) 도메인은 이력에 남기지 않음
//  - type: 도메인 한글명 (TYPE_LABEL_MAP)
//  - cause: rca_top3 기반 원인 피처의 한글명 (FEATURE_LABEL_MAP)
//  - level: 도메인별 alarm.level → CAUTION/WARNING/CRITICAL
export function mapInferenceToAlerts(payload: InferencePayload): AlertItem[] {
  const reports = payload.domain_reports ?? {};
  const tsMs = parseTimestampToMs(payload.timestamp);
  const date = new Date(tsMs);
  const dateStr = `${date.getFullYear()}.${pad2(date.getMonth() + 1)}.${pad2(date.getDate())}`;
  const timeStr = `${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`;

  const alerts: AlertItem[] = [];

  for (const [domain, report] of Object.entries(reports) as [
    string,
    InferenceDomainReport,
  ][]) {
    const level = report.alarm?.level;
    if (typeof level !== "number" || level === LEVEL_NORMAL) continue;

    const typeLabel = TYPE_LABEL_MAP[domain] ?? domain;
    const causeFeature = resolveCauseFeature(domain, report.rca_top3);
    const causeLabel = causeFeature
      ? (FEATURE_LABEL_MAP[causeFeature] ?? causeFeature)
      : "이상 감지";

    alerts.push({
      id: `alert-${tsMs}-${domain}`,
      date: dateStr,
      time: timeStr,
      type: typeLabel,
      cause: causeLabel,
      level: levelToAlertLabel(level),
    });
  }

  return alerts;
}
