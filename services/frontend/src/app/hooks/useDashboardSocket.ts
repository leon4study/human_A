import { useEffect, useRef, useState } from "react";
import type {
  AlertItem,
  AnySocketMessage,
  CtpVisualizationMetric,
  EnvironmentItem,
  InferenceDomainReport,
  InferencePayload,
  KpiItem,
  RawSensorPayload,
  ZoneItem,
} from "../types/dashboard";
import { environmentData } from "../data/environmentData";
import { ctpVisualizationData } from "../data/ctpVisualizationData";
import { kpiData } from "../data/kpiData";
import { alertData } from "../data/alertData";
import { zoneData } from "../data/zoneData";
import type { SystemStatus } from "../components/common/SystemStatus";
import type { SensorData } from "../components/center/facility/model/facility.types";
import { initialSensorData } from "../components/center/facility/model/facility.status";
import {
  applyBuffersToTrend,
  computeSystemStatus,
  mapCtpCurrentValues,
  mapEnvironment,
  mapInferenceToAlerts,
  mapTankLevels,
  parseTimestampToMs,
  pruneAlarmEvents,
  updateCtpTrendBuffers,
  type AlarmEvent,
  type CtpTrendBuffers,
} from "../utils/sensorMapping";

export interface ChartBuffer {
  ts: number[];
  pressure: number[];
  suction: number[];
  flow: number[];
  motor_power: number[];
  motor_current: number[];
  motor_temp: number[];
  pump_rpm: number[];
  bearing_vib: number[];
  filter_in: number[];
  filter_out: number[];
  mix_ec: number[];
  mix_target_ec: number[];
  mix_ph: number[];
  mix_target_ph: number[];
  drain_ec: number[];
  zone1_moisture: number[];
  zone1_flow: number[];
  zone1_ec: number[];
  zone2_moisture: number[];
  zone2_ec: number[];
  zone3_moisture: number[];
  zone3_ec: number[];
}

// 설비 상세/모달에 보여주는 짧은 비교 그래프는 최근 20개까지만 유지
const CHART_MAX = 20;
// 비교분석용 장기 버퍼는 최근 12시간(1분 기준 720개)을 기준으로 설정
const LONG_BUF_MAX = 720;
const MIN_SAMPLES_FOR_STATS = 30;
const EPS_LONG = 1e-6;
const TEN_MINUTES_MS = 10 * 60 * 1000;

export interface ComparativeMetrics {
  pressureVolatility: number | null;
  flowCv: number | null;
  samples: number;
}

interface DashboardSocketState {
  systemStatus: SystemStatus;
  environment: EnvironmentItem[];
  ctpVisualizationMetrics: CtpVisualizationMetric[];
  kpiItems: KpiItem[];
  alertItems: AlertItem[];
  zoneItems: ZoneItem[];
  sensorData: SensorData;
  rawSensorPayload: RawSensorPayload | null;
  latestInference: InferencePayload | null;
  chartSnapshot: ChartBuffer | null;
  comparativeMetrics: ComparativeMetrics;
  socketStatus: "connecting" | "open" | "closed" | "error";
}

const SOCKET_URL = "ws://127.0.0.1:8080/ws/smart-farm";
// Alert 이력 초기 로드는 최대 50개만 요청
// 추후 날짜 선택 로그 조회가 필요하면 query string만 확장해서 붙일 수 있게 유지
const HISTORY_URL = "/inference/history?limit=50";
const ALERT_MAX = 50;
const STATUS_RECOMPUTE_INTERVAL_MS = 60 * 1000;
const PREDICT_URL = "/predict";
const PREDICT_INTERVAL_MS = 15 * 1000;

type ThresholdSnapshot = {
  thresholdMode: CtpVisualizationMetric["thresholdMode"];
  caution: number;
  warning: number;
  critical: number;
  cautionLower?: number;
  warningLower?: number;
  criticalLower?: number;
  thresholdSource?: string;
};

type ThresholdBucket = {
  bucketStart: number;
  snapshot: ThresholdSnapshot;
};

type ThresholdHistoryBuffers = Record<string, ThresholdBucket[]>;

function computeStd(arr: number[]): number {
  // 변동성 지표 계산에 쓰는 표준편차
  if (arr.length < 2) return NaN;
  const m = arr.reduce((a, b) => a + b, 0) / arr.length;
  const variance = arr.reduce((s, v) => s + (v - m) ** 2, 0) / arr.length;
  return Math.sqrt(variance);
}

function computeIqr(arr: number[]): number {
  // pressure_volatility 계산에 쓰는 IQR(Q3-Q1)
  if (arr.length < 4) return NaN;
  const sorted = [...arr].sort((a, b) => a - b);
  const q1 = sorted[Math.floor(sorted.length * 0.25)];
  const q3 = sorted[Math.floor(sorted.length * 0.75)];
  return q3 - q1;
}

function computeMean(arr: number[]): number {
  if (arr.length === 0) return NaN;
  return arr.reduce((a, b) => a + b, 0) / arr.length;
}

function makeEmptyChartBuffer(): ChartBuffer {
  // RAW가 아직 안 들어왔을 때도 차트 구조는 유지
  return {
    ts: [], pressure: [], suction: [], flow: [], motor_power: [],
    motor_current: [], motor_temp: [], pump_rpm: [], bearing_vib: [],
    filter_in: [], filter_out: [],
    mix_ec: [], mix_target_ec: [], mix_ph: [], mix_target_ph: [], drain_ec: [],
    zone1_moisture: [], zone1_flow: [], zone1_ec: [],
    zone2_moisture: [], zone2_ec: [],
    zone3_moisture: [], zone3_ec: [],
  };
}

function snapChartBuffer(b: ChartBuffer): ChartBuffer {
  return {
    ts: [...b.ts], pressure: [...b.pressure], suction: [...b.suction],
    flow: [...b.flow], motor_power: [...b.motor_power], motor_current: [...b.motor_current],
    motor_temp: [...b.motor_temp], pump_rpm: [...b.pump_rpm], bearing_vib: [...b.bearing_vib],
    filter_in: [...b.filter_in], filter_out: [...b.filter_out],
    mix_ec: [...b.mix_ec], mix_target_ec: [...b.mix_target_ec],
    mix_ph: [...b.mix_ph], mix_target_ph: [...b.mix_target_ph],
    drain_ec: [...b.drain_ec], zone1_moisture: [...b.zone1_moisture], zone1_flow: [...b.zone1_flow], zone1_ec: [...b.zone1_ec],
    zone2_moisture: [...b.zone2_moisture], zone2_ec: [...b.zone2_ec],
    zone3_moisture: [...b.zone3_moisture], zone3_ec: [...b.zone3_ec],
  };
}

// /predict 응답과 웹소켓 inference 응답을 같은 형태로 맞춤
function mapPredictResponseToInferencePayload(
  resp: Record<string, unknown>,
  fallbackTs: string,
): InferencePayload {
  const reports: Record<string, InferenceDomainReport> = {};
  const src = (resp?.domain_reports ?? {}) as Record<string, Record<string, unknown>>;
  for (const [domain, raw] of Object.entries(src)) {
    const r = raw ?? {};
    const rcaTop3 = r.rca_top3;
    const rcaPlain = r.rca;
    reports[domain] = {
      alarm: (r.alarm as InferenceDomainReport["alarm"]) ?? { level: 0, label: "Normal" },
      rca: Array.isArray(rcaTop3)
        ? (rcaTop3 as InferenceDomainReport["rca"])
        : Array.isArray(rcaPlain)
          ? (rcaPlain as InferenceDomainReport["rca"])
          : [],
      score: (r.metrics as { current_mse?: number } | undefined)?.current_mse,
      metrics: r.metrics,
      global_thresholds: r.global_thresholds,
      feature_details: r.feature_details,
      target_reference_profiles: r.target_reference_profiles,
    };
  }
  return normalizeInferenceRecord({
    timestamp: (resp?.timestamp as string) ?? fallbackTs,
    overall_alarm_level: (resp?.overall_alarm_level as number) ?? 0,
    overall_status: (resp?.overall_status as string) ?? null,
    spike_info: resp?.spike_info as InferencePayload["spike_info"],
    action_required: (resp?.action_required as string) ?? null,
    domain_reports: reports,
  });
}


function normalizeRawPayload(payload: unknown): RawSensorPayload | null {
  // payload.sensor_data 형태와 payload 직접 전달 형태를 같이 수용
  if (!payload || typeof payload !== "object") return null;

  const maybeWrapped = payload as { sensor_data?: RawSensorPayload };
  if (maybeWrapped.sensor_data && typeof maybeWrapped.sensor_data === "object") {
    return maybeWrapped.sensor_data;
  }

  return payload as RawSensorPayload;
}

function normalizeInferencePayload(payload: unknown): InferencePayload | null {
  // inference도 sensor_data 래핑 여부를 먼저 확인
  if (!payload || typeof payload !== "object") return null;

  const maybeWrapped = payload as { sensor_data?: InferencePayload };
  if (maybeWrapped.sensor_data && typeof maybeWrapped.sensor_data === "object") {
    return maybeWrapped.sensor_data;
  }

  return normalizeInferenceRecord(payload as InferencePayload);
}

function normalizeInferenceRecord(payload: InferencePayload): InferencePayload {
  // 최종 응답은 domain_reports 안에 metadata와 실제 domain_reports가 한 번 더 들어온다
  const root = (payload.domain_reports ?? {}) as Record<string, unknown>;
  const nested = root.domain_reports as Record<string, InferenceDomainReport> | undefined;

  if (!nested || typeof nested !== "object") {
    return payload;
  }

  return {
    ...payload,
    overall_alarm_level:
      typeof root.overall_alarm_level === "number" ? root.overall_alarm_level : payload.overall_alarm_level,
    overall_status:
      typeof root.overall_status === "string" ? root.overall_status : payload.overall_status,
    action_required:
      typeof root.action_required === "string" ? root.action_required : payload.action_required,
    spike_info:
      (root.spike_info as InferencePayload["spike_info"]) ?? payload.spike_info,
    timestamp:
      typeof root.timestamp === "string" ? root.timestamp : payload.timestamp,
    domain_reports: nested,
  };
}

function buildInferenceKey(payload: InferencePayload): string {
  // 동일 timestamp/상태/도메인 구성이 반복되면 한 번만 처리
  const domainKeys = Object.keys(payload.domain_reports ?? {}).sort().join(",");
  return `${payload.timestamp}|${payload.overall_alarm_level}|${payload.overall_status ?? ""}|${domainKeys}`;
}

function toFiniteNumber(value: unknown): number | undefined {
  // 숫자가 아니면 threshold 계산에 넣지 않는다
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

// 새 threshold가 실제로 바뀐 경우에만 갱신해야 해서
// 이전 snapshot과 동일한지 비교
function isSameThresholdSnapshot(
  left: ThresholdSnapshot | undefined,
  right: ThresholdSnapshot | undefined,
): boolean {
  if (!left || !right) return false;
  return (
    left.thresholdMode === right.thresholdMode &&
    left.caution === right.caution &&
    left.warning === right.warning &&
    left.critical === right.critical &&
    left.cautionLower === right.cautionLower &&
    left.warningLower === right.warningLower &&
    left.criticalLower === right.criticalLower &&
    left.thresholdSource === right.thresholdSource
  );
}

function getFeatureDetail(report: InferenceDomainReport | undefined, name: string) {
  // feature_details에서 특정 RAW 항목의 bands/threshold 정보를 조회
  const details = Array.isArray(report?.feature_details)
    ? (report?.feature_details as Array<Record<string, unknown>>)
    : [];
  return details.find((detail) => detail?.name === name);
}

// target_reference_profiles.related_feature_lines에서
// 특정 컬럼의 upper/lower 기준선을 꺼낼 때 사용
function getRelatedFeatureLines(
  report: InferenceDomainReport | undefined,
  profileName: string,
  featureName: string,
) {
  const profiles = (report?.target_reference_profiles ?? {}) as Record<string, Record<string, unknown>>;
  const profile = profiles?.[profileName];
  const related = (profile?.related_feature_lines ?? {}) as Record<string, Record<string, unknown>>;
  return related?.[featureName];
}

// motor_current_a처럼 target_lines를 바로 쓰는 항목은 여기서 읽음
function getTargetLines(
  report: InferenceDomainReport | undefined,
  profileName: string,
) {
  const profiles = (report?.target_reference_profiles ?? {}) as Record<string, Record<string, unknown>>;
  const profile = profiles?.[profileName];
  return (profile?.target_lines ?? null) as Record<string, unknown> | null;
}

// threshold는 RAW가 아니라 INFERENCE payload에서 읽음
// CTP 4개만 골라서 화면용 threshold snapshot으로 정리
function extractThresholdUpdates(payload: InferencePayload): Record<string, ThresholdSnapshot> {
  // 최종 payload는 normalizeInferenceRecord를 거친 뒤 domain_reports가 평탄화된 상태
  const reports = payload.domain_reports ?? {};

  const hydraulic = reports.hydraulic;
  const motor = reports.motor;
  const nutrient = reports.nutrient;

  const flowDetail = getFeatureDetail(hydraulic, "flow_rate_l_min");
  const flowBands = (flowDetail?.bands ?? {}) as Record<string, unknown>;

  const pressureLines = getRelatedFeatureLines(
    hydraulic,
    "differential_pressure_kpa",
    "discharge_pressure_kpa",
  );
  const pressureCaution = (pressureLines?.caution ?? {}) as Record<string, unknown>;
  const pressureWarning = (pressureLines?.warning ?? {}) as Record<string, unknown>;
  const pressureCritical = (pressureLines?.critical ?? {}) as Record<string, unknown>;

  const motorCurrentLines = getTargetLines(motor, "motor_current_a");
  const currentCaution = (motorCurrentLines?.caution ?? {}) as Record<string, unknown>;
  const currentWarning = (motorCurrentLines?.warning ?? {}) as Record<string, unknown>;
  const currentCritical = (motorCurrentLines?.critical ?? {}) as Record<string, unknown>;

  const ecLines = getRelatedFeatureLines(
    nutrient,
    "pid_error_ec",
    "mix_ec_ds_m",
  );
  const ecCaution = (ecLines?.caution ?? {}) as Record<string, unknown>;
  const ecWarning = (ecLines?.warning ?? {}) as Record<string, unknown>;
  const ecCritical = (ecLines?.critical ?? {}) as Record<string, unknown>;

  const updates: Record<string, ThresholdSnapshot> = {};

  // 유량은 low-direction 기준이라 lower 값을 현재 화면 기준선으로 사용
  const flowCaution = toFiniteNumber(flowBands.caution_lower);
  const flowWarning = toFiniteNumber(flowBands.warning_lower);
  const flowCritical = toFiniteNumber(flowBands.critical_lower);
  if (
    flowCaution !== undefined &&
    flowWarning !== undefined &&
    flowCritical !== undefined
  ) {
    updates["pump-discharge-flow"] = {
      thresholdMode: "low",
      caution: flowCaution,
      warning: flowWarning,
      critical: flowCritical,
      thresholdSource: "hydraulic.feature_details.flow_rate_l_min.bands",
    };
  }

  // 토출 압력은 높아질수록 위험하므로 upper 기준선을 사용
  const pressureUpperCaution = toFiniteNumber(pressureCaution.upper);
  const pressureUpperWarning = toFiniteNumber(pressureWarning.upper);
  const pressureUpperCritical = toFiniteNumber(pressureCritical.upper);
  if (
    pressureUpperCaution !== undefined &&
    pressureUpperWarning !== undefined &&
    pressureUpperCritical !== undefined
  ) {
    updates["pump-discharge-pressure"] = {
      thresholdMode: "high",
      caution: pressureUpperCaution,
      warning: pressureUpperWarning,
      critical: pressureUpperCritical,
      cautionLower: toFiniteNumber(pressureCaution.lower),
      warningLower: toFiniteNumber(pressureWarning.lower),
      criticalLower: toFiniteNumber(pressureCritical.lower),
      thresholdSource: "hydraulic.target_reference_profiles.differential_pressure_kpa.related_feature_lines.discharge_pressure_kpa",
    };
  }

  // 모터 전류는 upper/lower를 둘 다 보는 range 기준이다
  const currentUpperCaution = toFiniteNumber(currentCaution.upper);
  const currentUpperWarning = toFiniteNumber(currentWarning.upper);
  const currentUpperCritical = toFiniteNumber(currentCritical.upper);
  if (
    currentUpperCaution !== undefined &&
    currentUpperWarning !== undefined &&
    currentUpperCritical !== undefined
  ) {
    updates["motor-current"] = {
      thresholdMode: "range",
      caution: currentUpperCaution,
      warning: currentUpperWarning,
      critical: currentUpperCritical,
      cautionLower: toFiniteNumber(currentCaution.lower),
      warningLower: toFiniteNumber(currentWarning.lower),
      criticalLower: toFiniteNumber(currentCritical.lower),
      thresholdSource: "motor.target_reference_profiles.motor_current_a.target_lines",
    };
  }

  // EC는 독립 threshold가 아니라 pid_error_ec.related_feature_lines 기준을 빌려온다
  const ecUpperCaution = toFiniteNumber(ecCaution.upper);
  const ecUpperWarning = toFiniteNumber(ecWarning.upper);
  const ecUpperCritical = toFiniteNumber(ecCritical.upper);
  if (
    ecUpperCaution !== undefined &&
    ecUpperWarning !== undefined &&
    ecUpperCritical !== undefined
  ) {
    updates["mix-ec"] = {
      thresholdMode: "range",
      caution: ecUpperCaution,
      warning: ecUpperWarning,
      critical: ecUpperCritical,
      cautionLower: toFiniteNumber(ecCaution.lower),
      warningLower: toFiniteNumber(ecWarning.lower),
      criticalLower: toFiniteNumber(ecCritical.lower),
      thresholdSource: "nutrient.target_reference_profiles.pid_error_ec.related_feature_lines.mix_ec_ds_m",
    };
  }

  return updates;
}

// threshold는 10분마다 확인하되,
// 새 값이 실제로 바뀐 경우에만 history 버퍼에 추가한다
function updateThresholdHistoryBuffers(
  buffers: ThresholdHistoryBuffers,
  timestampMs: number,
  updates: Record<string, ThresholdSnapshot>,
): ThresholdHistoryBuffers {
  if (Object.keys(updates).length === 0) return buffers;

  const bucketStart = Math.floor(timestampMs / TEN_MINUTES_MS) * TEN_MINUTES_MS;
  const next: ThresholdHistoryBuffers = { ...buffers };

  for (const [metricId, snapshot] of Object.entries(updates)) {
    const existing = next[metricId] ?? [];
    const last = existing[existing.length - 1];

    // 같은 10분 구간에서 값이 바뀌면 마지막 snapshot만 교체
    if (last && last.bucketStart === bucketStart) {
      if (isSameThresholdSnapshot(last.snapshot, snapshot)) continue;
      next[metricId] = [...existing.slice(0, -1), { bucketStart, snapshot }];
      continue;
    }

    // 새 값이 없으면 threshold를 무조건 늘리지 않고 이전 값을 유지
    if (last && isSameThresholdSnapshot(last.snapshot, snapshot)) continue;
    next[metricId] = [...existing, { bucketStart, snapshot }].slice(-72);
  }

  return next;
}

// 특정 시각에 어떤 threshold가 유효했는지 조회
// alert 이력은 이 함수가 아니라 당시 inference 결과만 사용
function resolveSnapshotForTimestamp(
  buckets: ThresholdBucket[] | undefined,
  timestamp: number,
  fallback: ThresholdSnapshot,
): ThresholdSnapshot {
  if (!buckets || buckets.length === 0) return fallback;

  let resolved = fallback;
  for (const bucket of buckets) {
    if (bucket.bucketStart <= timestamp) {
      resolved = bucket.snapshot;
      continue;
    }
    break;
  }
  return resolved;
}

function buildFilledSeries(length: number, value: number | undefined): number[] | undefined {
  // threshold history가 아직 없을 때는 현재 기준선을 길이에 맞춰 채움
  if (typeof value !== "number" || !Number.isFinite(value)) return undefined;
  return Array.from({ length }, () => value);
}

// CTP 값 시계열에 맞춰 threshold 시계열도 같이 붙여서
// 시각화 패널이 step threshold를 그릴 수 있게 생성
function applyThresholdHistoryToMetrics(
  metrics: CtpVisualizationMetric[],
  buffers: ThresholdHistoryBuffers,
): CtpVisualizationMetric[] {
  let changed = false;

  const next = metrics.map((metric) => {
    const timestamps = metric.timestamps ?? [];
    const fallback: ThresholdSnapshot = {
      thresholdMode: metric.thresholdMode,
      caution: metric.caution,
      warning: metric.warning,
      critical: metric.critical,
      cautionLower: metric.cautionLower,
      warningLower: metric.warningLower,
      criticalLower: metric.criticalLower,
      thresholdSource: metric.thresholdSource,
    };

    const thresholdBuckets = buffers[metric.id];
    const latestSnapshot = thresholdBuckets?.[thresholdBuckets.length - 1]?.snapshot ?? fallback;

    let cautionTrend = metric.cautionTrend;
    let warningTrend = metric.warningTrend;
    let criticalTrend = metric.criticalTrend;
    let cautionLowerTrend = metric.cautionLowerTrend;
    let warningLowerTrend = metric.warningLowerTrend;
    let criticalLowerTrend = metric.criticalLowerTrend;

    // 값 시계열 timestamp가 있으면 각 시점에 유효한 threshold를 다시 계산
    if (timestamps.length > 0) {
      cautionTrend = [];
      warningTrend = [];
      criticalTrend = [];
      cautionLowerTrend = [];
      warningLowerTrend = [];
      criticalLowerTrend = [];

      for (const ts of timestamps) {
        const snapshot = resolveSnapshotForTimestamp(thresholdBuckets, ts, fallback);
        cautionTrend.push(snapshot.caution);
        warningTrend.push(snapshot.warning);
        criticalTrend.push(snapshot.critical);
        if (snapshot.cautionLower !== undefined) cautionLowerTrend.push(snapshot.cautionLower);
        if (snapshot.warningLower !== undefined) warningLowerTrend.push(snapshot.warningLower);
        if (snapshot.criticalLower !== undefined) criticalLowerTrend.push(snapshot.criticalLower);
      }

      if (cautionLowerTrend.length === 0) cautionLowerTrend = undefined;
      if (warningLowerTrend.length === 0) warningLowerTrend = undefined;
      if (criticalLowerTrend.length === 0) criticalLowerTrend = undefined;
    } else {
      // 아직 timestamp가 없으면 현재 threshold를 전체 길이에 동일하게 적용
      cautionTrend = buildFilledSeries(metric.trend.length, latestSnapshot.caution);
      warningTrend = buildFilledSeries(metric.trend.length, latestSnapshot.warning);
      criticalTrend = buildFilledSeries(metric.trend.length, latestSnapshot.critical);
      cautionLowerTrend = buildFilledSeries(metric.trend.length, latestSnapshot.cautionLower);
      warningLowerTrend = buildFilledSeries(metric.trend.length, latestSnapshot.warningLower);
      criticalLowerTrend = buildFilledSeries(metric.trend.length, latestSnapshot.criticalLower);
    }

    const nextMetric: CtpVisualizationMetric = {
      ...metric,
      thresholdMode: latestSnapshot.thresholdMode ?? metric.thresholdMode,
      caution: latestSnapshot.caution,
      warning: latestSnapshot.warning,
      critical: latestSnapshot.critical,
      cautionLower: latestSnapshot.cautionLower,
      warningLower: latestSnapshot.warningLower,
      criticalLower: latestSnapshot.criticalLower,
      thresholdSource: latestSnapshot.thresholdSource ?? metric.thresholdSource,
      thresholdUpdatedAt: thresholdBuckets?.[thresholdBuckets.length - 1]?.bucketStart ?? metric.thresholdUpdatedAt,
      cautionTrend,
      warningTrend,
      criticalTrend,
      cautionLowerTrend,
      warningLowerTrend,
      criticalLowerTrend,
    };

    const hasChanged =
      nextMetric.caution !== metric.caution ||
      nextMetric.warning !== metric.warning ||
      nextMetric.critical !== metric.critical ||
      nextMetric.cautionLower !== metric.cautionLower ||
      nextMetric.warningLower !== metric.warningLower ||
      nextMetric.criticalLower !== metric.criticalLower ||
      nextMetric.thresholdMode !== metric.thresholdMode ||
      nextMetric.thresholdSource !== metric.thresholdSource ||
      JSON.stringify(nextMetric.cautionTrend ?? []) !== JSON.stringify(metric.cautionTrend ?? []) ||
      JSON.stringify(nextMetric.warningTrend ?? []) !== JSON.stringify(metric.warningTrend ?? []) ||
      JSON.stringify(nextMetric.criticalTrend ?? []) !== JSON.stringify(metric.criticalTrend ?? []) ||
      JSON.stringify(nextMetric.cautionLowerTrend ?? []) !== JSON.stringify(metric.cautionLowerTrend ?? []) ||
      JSON.stringify(nextMetric.warningLowerTrend ?? []) !== JSON.stringify(metric.warningLowerTrend ?? []) ||
      JSON.stringify(nextMetric.criticalLowerTrend ?? []) !== JSON.stringify(metric.criticalLowerTrend ?? []);

    if (!hasChanged) return metric;
    changed = true;
    return nextMetric;
  });

  return changed ? next : metrics;
}

// 이 훅은 RAW / INFERENCE / CTP / alert / 비교분석 상태를 한 곳에서 관리
function useDashboardSocket(): DashboardSocketState {
  const [systemStatus, setSystemStatus] = useState<SystemStatus>("normal");
  const [environment, setEnvironment] = useState<EnvironmentItem[]>(environmentData);
  const [ctpVisualizationMetrics, setCtpVisualizationMetrics] =
    useState<CtpVisualizationMetric[]>(ctpVisualizationData);
  const [kpiItems, setKpiItems] = useState<KpiItem[]>(kpiData);
  const [alertItems, setAlertItems] = useState<AlertItem[]>(alertData);
  const [zoneItems, setZoneItems] = useState<ZoneItem[]>(zoneData);
  const [sensorData, setSensorData] = useState<SensorData>(initialSensorData);
  const [rawSensorPayload, setRawSensorPayload] = useState<RawSensorPayload | null>(null);
  const [latestInference, setLatestInference] = useState<InferencePayload | null>(null);
  const [chartSnapshot, setChartSnapshot] = useState<ChartBuffer | null>(null);
  const [comparativeMetrics, setComparativeMetrics] = useState<ComparativeMetrics>({
    pressureVolatility: null,
    flowCv: null,
    samples: 0,
  });
  const [socketStatus, setSocketStatus] =
    useState<"connecting" | "open" | "closed" | "error">("connecting");

  // trendBuffersRef는 CTP 값 시계열 버퍼다
  const trendBuffersRef = useRef<CtpTrendBuffers>({});
  // thresholdBuffersRef는 threshold 변경 이력을 따로 저장한다
  // 시각화는 이 버퍼를 쓰지만 alert 이력은 여기와 섞지 않는다
  const thresholdBuffersRef = useRef<ThresholdHistoryBuffers>({});
  const chartBufRef = useRef<ChartBuffer>(makeEmptyChartBuffer());
  const longBufRef = useRef<{ diffP: number[]; flow: number[] }>({
    diffP: [],
    flow: [],
  });
  const alarmEventsRef = useRef<AlarmEvent[]>([]);
  const latestRawRef = useRef<RawSensorPayload | null>(null);
  const rawDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSeenRawRef = useRef<RawSensorPayload | null>(null);
  const lastWsInferenceAtRef = useRef<number>(0);
  const lastInferenceKeyRef = useRef<string>("");

  const recomputeSystemStatus = () => {
    // 최근 10분 alarm 이벤트만 남겨서 상단 시스템 상태를 다시 계산
    const now = Date.now();
    alarmEventsRef.current = pruneAlarmEvents(alarmEventsRef.current, now);
    setSystemStatus(computeSystemStatus(alarmEventsRef.current, now));
  };

  const processInferencePayload = (payload: InferencePayload, source: string) => {
    // 최종 응답 구조를 프론트 공통 형태로 먼저 정규화
    const normalized = normalizeInferenceRecord(payload);
    const inferenceKey = buildInferenceKey(normalized);

    // 같은 inference가 WS/PREDICT 경로로 반복 유입되면 한 번만 반영
    if (lastInferenceKeyRef.current === inferenceKey) return;
    lastInferenceKeyRef.current = inferenceKey;

    // WS가 정상 수신 중이면 fallback /predict보다 WS를 우선 사용
    if (source === "WS") {
      lastWsInferenceAtRef.current = Date.now();
    }

    console.log(`🔍 INFERENCE [${source}]:`, normalized);

    // alarm 이벤트는 상단 시스템 상태 계산용으로만 사용
    // Alert 패널 데이터는 DB history API 결과만 사용
    const ts = parseTimestampToMs(normalized.timestamp);
    alarmEventsRef.current = pruneAlarmEvents(
      [...alarmEventsRef.current, { ts, level: normalized.overall_alarm_level }],
      Date.now(),
    );
    recomputeSystemStatus();

    setLatestInference(normalized);
    setChartSnapshot(snapChartBuffer(chartBufRef.current));

    // 비교분석용 장기 버퍼는 별도로 유지
    const lb = longBufRef.current;
    const samples = Math.min(lb.diffP.length, lb.flow.length);
    let pVol: number | null = null;
    let fCv: number | null = null;
    if (lb.diffP.length >= MIN_SAMPLES_FOR_STATS) {
      const s = computeStd(lb.diffP);
      const iqrVal = computeIqr(lb.diffP);
      if (Number.isFinite(s) && Number.isFinite(iqrVal) && iqrVal > 0) {
        pVol = s / (iqrVal + EPS_LONG);
      }
    }
    if (lb.flow.length >= MIN_SAMPLES_FOR_STATS) {
      const s = computeStd(lb.flow);
      const m = computeMean(lb.flow);
      if (Number.isFinite(s) && Number.isFinite(m) && m > 0) {
        fCv = s / (m + EPS_LONG);
      }
    }
    setComparativeMetrics({ pressureVolatility: pVol, flowCv: fCv, samples });

    // threshold는 새 값이 있을 때만 갱신
    // 이 단계에서 alert 이력을 다시 만들면 안 됨
    const thresholdUpdates = extractThresholdUpdates(normalized);
    if (Object.keys(thresholdUpdates).length > 0) {
      thresholdBuffersRef.current = updateThresholdHistoryBuffers(
        thresholdBuffersRef.current,
        ts,
        thresholdUpdates,
      );
      setCtpVisualizationMetrics((prev) => applyThresholdHistoryToMetrics(prev, thresholdBuffersRef.current));
    }

    // Alert 이력은 프론트에서 직접 생성하지 않음
    // DB에 저장된 history API 응답만 화면에 반영
  };

  const handleRawPayload = (raw: RawSensorPayload) => {
    // RAW는 현재값 카드, 설비 상태, 값 시계열의 재료로만 사용
    lastSeenRawRef.current = raw;
    setRawSensorPayload(raw);

    // 차트/모달에서 쓰는 짧은 최근값 버퍼를 먼저 갱신
    const b = chartBufRef.current;
    const pushN = (arr: number[], v: unknown) =>
      arr.push(typeof v === "number" && Number.isFinite(v) ? v : NaN);
    const ts = typeof raw.timestamp === "string" ? Date.parse(raw.timestamp) || Date.now() : Date.now();
    pushN(b.ts, ts);
    pushN(b.pressure, raw.discharge_pressure_kpa);
    pushN(b.suction, raw.suction_pressure_kpa);
    pushN(b.flow, raw.flow_rate_l_min);
    pushN(b.motor_power, raw.motor_power_kw);
    pushN(b.motor_current, raw.motor_current_a);
    pushN(b.motor_temp, raw.motor_temperature_c);
    pushN(b.pump_rpm, raw.pump_rpm);
    pushN(b.bearing_vib, raw.bearing_vibration_rms_mm_s);
    pushN(b.filter_in, raw.filter_pressure_in_kpa);
    pushN(b.filter_out, raw.filter_pressure_out_kpa);
    pushN(b.mix_ec, raw.mix_ec_ds_m);
    pushN(b.mix_target_ec, raw.mix_target_ec_ds_m);
    pushN(b.mix_ph, raw.mix_ph);
    pushN(b.mix_target_ph, raw.mix_target_ph);
    pushN(b.drain_ec, raw.drain_ec_ds_m);
    pushN(b.zone1_moisture, raw.zone1_substrate_moisture_pct);
    pushN(b.zone1_flow, raw.zone1_flow_l_min);
    pushN(b.zone1_ec, raw.zone1_substrate_ec_ds_m);
    pushN(b.zone2_moisture, raw.zone2_substrate_moisture_pct);
    pushN(b.zone2_ec, raw.zone2_substrate_ec_ds_m);
    pushN(b.zone3_moisture, raw.zone3_substrate_moisture_pct);
    pushN(b.zone3_ec, raw.zone3_substrate_ec_ds_m);
    (Object.values(b) as number[][]).forEach((arr) => {
      while (arr.length > CHART_MAX) arr.shift();
    });

    // 비교분석용 장기 버퍼는 별도로 유지
    const lb = longBufRef.current;
    if (
      typeof raw.discharge_pressure_kpa === "number" &&
      typeof raw.suction_pressure_kpa === "number"
    ) {
      const diffP = raw.discharge_pressure_kpa - raw.suction_pressure_kpa;
      if (Number.isFinite(diffP)) {
        lb.diffP.push(diffP);
        if (lb.diffP.length > LONG_BUF_MAX) lb.diffP.shift();
      }
    }
    if (typeof raw.flow_rate_l_min === "number" && Number.isFinite(raw.flow_rate_l_min)) {
      lb.flow.push(raw.flow_rate_l_min);
      if (lb.flow.length > LONG_BUF_MAX) lb.flow.shift();
    }

    setEnvironment((prev) => mapEnvironment(raw, prev));

    setCtpVisualizationMetrics((prev) => {
      // RAW는 현재값과 값 시계열만 바꾸고,
      // threshold는 마지막 inference 기준을 그대로 덮어씀
      const withCurrent = mapCtpCurrentValues(raw, prev);
      const nextBuffers = updateCtpTrendBuffers(trendBuffersRef.current, raw, withCurrent);
      trendBuffersRef.current = nextBuffers;
      const withTrend = applyBuffersToTrend(withCurrent, nextBuffers);
      return applyThresholdHistoryToMetrics(withTrend, thresholdBuffersRef.current);
    });

    const tankLevels = mapTankLevels(raw);
    setSensorData((prev) => ({
      ...prev,
      waterLevel: tankLevels.rawTankLevel ?? prev.waterLevel,
      tankALevel: tankLevels.tankALevel ?? prev.tankALevel,
      tankBLevel: tankLevels.tankBLevel ?? prev.tankBLevel,
      acidTankLevel: tankLevels.acidTankLevel ?? prev.acidTankLevel,
      ph: typeof raw.mix_ph === "number" ? raw.mix_ph : prev.ph,
      ec: typeof raw.mix_ec_ds_m === "number" ? raw.mix_ec_ds_m : prev.ec,
      temperature: typeof raw.mix_temp_c === "number" ? raw.mix_temp_c : prev.temperature,
      pressure:
        typeof raw.discharge_pressure_kpa === "number"
          ? raw.discharge_pressure_kpa
          : prev.pressure,
    }));
  };

  useEffect(() => {
    // 메인 웹소켓은 RAW와 INFERENCE를 같이 받는다
    const socket = new WebSocket(SOCKET_URL);
    let isCleanup = false;

    socket.onopen = () => {
      if (isCleanup) return;
      setSocketStatus("open");
      console.log("✅ FastAPI 실시간 서버 연결 성공!");
    };

    socket.onmessage = (event) => {
      try {
        const message: AnySocketMessage = JSON.parse(event.data);

        if (message.type === "RAW") {
          // RAW는 sensor_data 래핑 여부를 먼저 정규화
          const raw = normalizeRawPayload(message.payload);
          if (!raw) return;

          // RAW는 너무 자주 들어올 수 있어서 짧게 debounce 후 처리
          latestRawRef.current = raw;
          if (rawDebounceRef.current) clearTimeout(rawDebounceRef.current);
          rawDebounceRef.current = setTimeout(() => {
            if (latestRawRef.current) {
              handleRawPayload(latestRawRef.current);
              latestRawRef.current = null;
            }
          }, 150);
          return;
        }

        if (message.type === "INFERENCE") {
          // INFERENCE도 sensor_data 래핑 여부를 먼저 정규화
          const inference = normalizeInferencePayload(message.payload);
          if (!inference) return;

          // threshold / alert / 비교분석 반영
          processInferencePayload(inference, "WS");
          return;
        }

        const payload = message.payload;
        if (payload.systemStatus) setSystemStatus(payload.systemStatus);
        if (payload.environment) setEnvironment(payload.environment);
        if (payload.ctpVisualizationMetrics) setCtpVisualizationMetrics(payload.ctpVisualizationMetrics);
        if (payload.kpiItems) setKpiItems(payload.kpiItems);
        // 서버가 가공한 alertItems를 주는 경우에도 최대 50개까지만 유지
        if (payload.alertItems) setAlertItems(payload.alertItems.slice(0, ALERT_MAX));
        if (payload.zoneItems) setZoneItems(payload.zoneItems);
      } catch (error) {
        console.error("❌ 데이터 파싱 에러:", error);
      }
    };

    socket.onerror = () => {
      if (isCleanup) return;
      setSocketStatus("error");
      console.error("❌ 웹소켓 연결 에러");
    };

    socket.onclose = () => {
      if (isCleanup) return;
      setSocketStatus("closed");
      console.log("🔌 서버 연결 종료");
    };

    return () => {
      isCleanup = true;
      socket.close();
      if (rawDebounceRef.current) clearTimeout(rawDebounceRef.current);
    };
  }, []);

  useEffect(() => {
    // 초기 진입 시 과거 inference history를 읽어서 alert 패널을 먼저 채움
    let cancelled = false;

    const fireOnce = async () => {
      const raw = lastSeenRawRef.current;
      if (!raw) return;

      // 최근 WS inference가 들어왔으면 /predict fallback은 건너뜀
      if (Date.now() - lastWsInferenceAtRef.current < 30_000) return;

      try {
        const res = await fetch(PREDICT_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(raw),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (cancelled) return;

        const payload = mapPredictResponseToInferencePayload(
          data,
          raw.timestamp ?? new Date().toISOString(),
        );
        processInferencePayload(payload, "PREDICT");
      } catch (error) {
        console.error("❌ /predict 호출 실패:", error);
      }
    };

    const kickoff = setTimeout(fireOnce, 2000);
    const timer = setInterval(fireOnce, PREDICT_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearTimeout(kickoff);
      clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    // alarm 이벤트가 없어도 시스템 상태가 시간이 지나며 정상으로 주기적 재계산으로 정상 복귀 반영
    const timer = setInterval(recomputeSystemStatus, STATUS_RECOMPUTE_INTERVAL_MS);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    // Alert 이력은 DB/API history 결과만 표시
    let cancelled = false;

    (async () => {
      try {
        const res = await fetch(HISTORY_URL);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const rows = (await res.json()) as InferencePayload[];
        if (cancelled) return;

        const alerts: AlertItem[] = [];
        const seen = new Set<string>();

        for (const row of rows) {
          const normalized = normalizeInferenceRecord(row);
          for (const alert of mapInferenceToAlerts(normalized)) {
            if (seen.has(alert.id)) continue;
            seen.add(alert.id);
            alerts.push(alert);
          }
        }

        setAlertItems(alerts.slice(0, ALERT_MAX));
      } catch (error) {
        console.error("❌ Alert 이력 초기 로드 실패:", error);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  return {
    systemStatus,
    environment,
    ctpVisualizationMetrics,
    kpiItems,
    alertItems,
    zoneItems,
    sensorData,
    rawSensorPayload,
    latestInference,
    chartSnapshot,
    comparativeMetrics,
    socketStatus,
  };
}

export default useDashboardSocket;