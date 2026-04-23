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

// 화면에서 쓰는 환경정보 id를 RAW payload 컬럼명에 연결
const ENVIRONMENT_COLUMN_MAP: Record<string, keyof RawSensorPayload> = {
  light: "light_ppfd_umol_m2_s",
  temp: "air_temp_c",
  humidity: "relative_humidity_pct",
  co2: "co2_ppm",
};

// CTP 카드와 시각화가 어떤 RAW 값을 읽어야 하는지 고정
const CTP_COLUMN_MAP: Record<string, keyof RawSensorPayload> = {
  "pump-discharge-flow": "flow_rate_l_min",
  "pump-discharge-pressure": "discharge_pressure_kpa",
  "motor-temperature": "motor_temperature_c",
  "motor-power": "motor_power_kw",
};

// 설비 SVG/패널에 표시용 탱크 수위 컬럼 매핑
export const TANK_COLUMN_MAP: Record<string, keyof RawSensorPayload> = {
  rawWaterTank: "raw_tank_level_pct",
  tankA: "tank_a_level_pct",
  tankB: "tank_b_level_pct",
  tankPH: "acid_tank_level_pct",
};

function pickNumber(raw: RawSensorPayload, key: keyof RawSensorPayload): number | undefined {
  // 숫자가 아니면 화면 계산에 섞지 않도록 제외
  const value = raw[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function numberArraysEqual(a: number[], b: number[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

// RAW 환경값을 기존 카드 배열에 덮어씀
export function mapEnvironment(
  raw: RawSensorPayload,
  prev: EnvironmentItem[],
): EnvironmentItem[] {
  let changed = false;

  const next = prev.map((item) => {
    const column = ENVIRONMENT_COLUMN_MAP[item.id];
    if (!column) return item;

    const value = pickNumber(raw, column);

    // 값이 없으면 기존 표시 유지
    if (value === undefined) return item;

    // 값이 같으면 기존 객체 유지
    if (value === item.value) return item;

    changed = true;
    return { ...item, value };
  });

  // 실제 변경 있을 때만 새 배열 반영
  return changed ? next : prev;
}

// RAW 수신 시 CTP 카드/그래프의 현재값 반영
export function mapCtpCurrentValues(
  raw: RawSensorPayload,
  prev: CtpVisualizationMetric[],
): CtpVisualizationMetric[] {
  let changed = false;

  const next = prev.map((metric) => {
    const column = CTP_COLUMN_MAP[metric.id];
    if (!column) return metric;

    const value = pickNumber(raw, column);

    // 값이 없거나 그대로면 기존 metric 유지
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
  // 설비 탱크 수위는 센서 payload에서 직접 추출
  return {
    rawTankLevel: pickNumber(raw, "raw_tank_level_pct"),
    tankALevel: pickNumber(raw, "tank_a_level_pct"),
    tankBLevel: pickNumber(raw, "tank_b_level_pct"),
    acidTankLevel: pickNumber(raw, "acid_tank_level_pct"),
  };
}

// CTP 시각화는 10분 버킷 72칸으로 12시간 유지
const TEN_MINUTES_MS = 10 * 60 * 1000;
const MAX_BUCKETS = 72;

export interface CtpTimeBucket {
  bucketStart: number;
  value: number;
}

export type CtpTrendBuffers = Record<string, CtpTimeBucket[]>;

function parseTimestamp(value: string | undefined): number {
  // timestamp가 없거나 잘못 들어와도 그래프는 현재 시각 기준으로 유지
  if (!value) return Date.now();
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? Date.now() : parsed;
}

// 같은 10분 구간이면 마지막 값만 최신값으로 교체
// 구간이 바뀌면 새 점 추가
export function updateCtpTrendBuffers(
  buffers: CtpTrendBuffers,
  raw: RawSensorPayload,
  metrics: CtpVisualizationMetric[],
): CtpTrendBuffers {
  const ts = parseTimestamp(raw.timestamp);
  const bucketStart = Math.floor(ts / TEN_MINUTES_MS) * TEN_MINUTES_MS;
  const next: CtpTrendBuffers = { ...buffers };

  for (const metric of metrics) {
    const column = CTP_COLUMN_MAP[metric.id];
    if (!column) continue;

    const value = pickNumber(raw, column);
    if (value === undefined) continue;

    const existing = next[metric.id] ?? [];
    const last = existing[existing.length - 1];

    if (last && last.bucketStart === bucketStart) {
      next[metric.id] = [...existing.slice(0, -1), { bucketStart, value }];
    } else {
      const appended = [...existing, { bucketStart, value }];
      next[metric.id] = appended.slice(-MAX_BUCKETS);
    }
  }

  return next;
}

function fillSeries(length: number, value: number | undefined): number[] | undefined {
  // threshold 시계열이 아직 없으면 현재 기준값으로 길이만 맞춤
  if (typeof value !== "number" || !Number.isFinite(value)) return undefined;
  return Array.from({ length }, () => value);
}

// 버퍼에 모인 시계열을 실제 CTP metric 구조에 다시 주입
export function applyBuffersToTrend(
  metrics: CtpVisualizationMetric[],
  buffers: CtpTrendBuffers,
): CtpVisualizationMetric[] {
  let changed = false;

  const next = metrics.map((metric) => {
    const buckets = buffers[metric.id];
    if (!buckets || buckets.length === 0) return metric;

    const newTrend = buckets.map((bucket) => bucket.value);
    const newTimestamps = buckets.map((bucket) => bucket.bucketStart);
    const trendChanged = !numberArraysEqual(metric.trend, newTrend);
    const timestampsChanged = !numberArraysEqual(metric.timestamps ?? [], newTimestamps);

    const nextMetric: CtpVisualizationMetric = {
      ...metric,
      trend: newTrend,
      timestamps: newTimestamps,
      cautionTrend:
        metric.cautionTrend && metric.cautionTrend.length === newTrend.length
          ? metric.cautionTrend
          : fillSeries(newTrend.length, metric.caution),
      warningTrend:
        metric.warningTrend && metric.warningTrend.length === newTrend.length
          ? metric.warningTrend
          : fillSeries(newTrend.length, metric.warning),
      criticalTrend:
        metric.criticalTrend && metric.criticalTrend.length === newTrend.length
          ? metric.criticalTrend
          : fillSeries(newTrend.length, metric.critical),
      cautionLowerTrend:
        metric.cautionLowerTrend && metric.cautionLowerTrend.length === newTrend.length
          ? metric.cautionLowerTrend
          : fillSeries(newTrend.length, metric.cautionLower),
      warningLowerTrend:
        metric.warningLowerTrend && metric.warningLowerTrend.length === newTrend.length
          ? metric.warningLowerTrend
          : fillSeries(newTrend.length, metric.warningLower),
      criticalLowerTrend:
        metric.criticalLowerTrend && metric.criticalLowerTrend.length === newTrend.length
          ? metric.criticalLowerTrend
          : fillSeries(newTrend.length, metric.criticalLower),
    };

    if (!trendChanged && !timestampsChanged) return metric;
    changed = true;
    return nextMetric;
  });

  return changed ? next : metrics;
}

// overall_alarm_level 숫자를 화면 상태 계산에 사용
export const LEVEL_NORMAL = 0;
export const LEVEL_CAUTION = 1;
export const LEVEL_WARNING = 2;
export const LEVEL_ERROR = 3;

export function levelToAlertLabel(level: number): string {
  switch (level) {
    case LEVEL_CAUTION:
      return "CAUTION";
    case LEVEL_WARNING:
      return "WARNING";
    case LEVEL_ERROR:
      return "CRITICAL";
    default:
      return "NORMAL";
  }
}

export interface AlarmEvent {
  ts: number;
  level: number;
}

export const SYSTEM_STATUS_WINDOW_MS = 10 * 60 * 1000;

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

export function pruneAlarmEvents(
  events: AlarmEvent[],
  now: number,
): AlarmEvent[] {
  return events.filter((event) => now - event.ts <= SYSTEM_STATUS_WINDOW_MS);
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

// 도메인 코드 → 화면 표시 유형명
const TYPE_LABEL_MAP: Record<string, string> = {
  motor: "모터",
  hydraulic: "수압/유압",
  nutrient: "양액/수질",
  zone_drip: "구역 점적",
};

// 원인 컬럼 → 화면 표시 한글명
const FEATURE_LABEL_MAP: Record<string, string> = {
  flow_rate_l_min: "메인 라인 유량 이상",
  discharge_pressure_kpa: "토출 압력 이상",
  suction_pressure_kpa: "흡입 압력 이상",
  motor_current_a: "모터 전류 이상",
  motor_power_kw: "모터 전력 이상",
  motor_temperature_c: "모터 온도 이상",
  bearing_vibration_rms_mm_s: "베어링 진동 이상",
  bearing_temperature_c: "베어링 온도 이상",
  mix_ec_ds_m: "혼합EC 이상",
  mix_ph: "조제 현재 pH 이상",
  drain_ec_ds_m: "배액 EC 이상",
  zone1_substrate_moisture_pct: "구역 배지 수분 이상",
  zone1_substrate_ec_ds_m: "구역 배지 EC 이상",
  air_temp_c: "실내 기온 이상",
};

// 시간 컨텍스트 피처는 alert 원인에서 제외
const EXCLUDED_CAUSE_FEATURES = new Set(["time_sin", "time_cos", "pump_on", "minutes_since_startup"]);

function resolveCauseFeature(report: InferenceDomainReport): string | null {
  // rca 또는 rca_top3 중 실제 있는 쪽 사용
  const rcaList: InferenceRcaItem[] =
    Array.isArray(report.rca) && report.rca.length > 0
      ? report.rca
      : Array.isArray(report.rca_top3) && report.rca_top3.length > 0
        ? report.rca_top3
        : [];

  const picked = rcaList.find((item) => !EXCLUDED_CAUSE_FEATURES.has(item.feature));
  if (picked) return picked.feature;

  return null;
}

// inference payload를 Alert 패널에 바로 쓰는 구조로 변환
export function mapInferenceToAlerts(payload: InferencePayload): AlertItem[] {
  const reports = payload.domain_reports ?? {};
  const parsedTs = Date.parse(payload.timestamp);
  const safeTs = Number.isNaN(parsedTs) ? Date.now() : parsedTs;
  const date = new Date(safeTs);

  const dateStr = `${date.getFullYear()}.${pad2(date.getMonth() + 1)}.${pad2(date.getDate())}`;
  const timeStr = `${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`;

  const alerts: AlertItem[] = [];

  for (const [domain, report] of Object.entries(reports)) {
    const level = report.alarm?.level;

    // 정상 도메인은 이력에 넣지 않음
    if (typeof level !== "number" || level === LEVEL_NORMAL) continue;

    const typeLabel = report.도메인명 ?? TYPE_LABEL_MAP[domain] ?? domain;
    const causeFeature = resolveCauseFeature(report);
    const causeLabel = causeFeature
      ? (FEATURE_LABEL_MAP[causeFeature] ?? causeFeature)
      : "이상 감지";

    alerts.push({
      id: `alert-${safeTs}-${domain}`,
      date: dateStr,
      time: timeStr,
      type: typeLabel,
      cause: causeLabel,
      level: levelToAlertLabel(level),
    });
  }

  return alerts;
}
