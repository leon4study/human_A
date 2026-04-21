import { useEffect, useRef, useState } from "react";
import type {
  AlertItem,
  AnySocketMessage,
  CtpVisualizationMetric,
  EnvironmentItem,
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

// 차트용 링버퍼: RAW 수신마다 ref 업데이트, INFERENCE 도착 때 state 스냅샷
export interface ChartBuffer {
  ts: number[];
  pressure: number[];      // discharge_pressure_kpa
  suction: number[];       // suction_pressure_kpa
  flow: number[];          // flow_rate_l_min
  motor_power: number[];   // motor_power_kw
  motor_current: number[]; // motor_current_a
  motor_temp: number[];    // motor_temperature_c
  pump_rpm: number[];      // pump_rpm
  bearing_vib: number[];   // bearing_vibration_rms_mm_s
  mix_ph: number[];        // mix_ph
  mix_ec: number[];        // mix_ec_ds_m
  target_ph: number[];     // mix_target_ph
  target_ec: number[];     // mix_target_ec_ds_m
  zone1_moisture: number[]; // zone1_substrate_moisture_pct
  zone1_flow: number[];    // zone1_flow_l_min
}

const CHART_MAX = 20;

// 12h 비교분석용 링버퍼 (RAW 1/min 기준 720포인트)
const LONG_BUF_MAX = 720;
const MIN_SAMPLES_FOR_STATS = 30;
const EPS_LONG = 1e-6;

export interface ComparativeMetrics {
  pressureVolatility: number | null; // std(ΔP) / IQR(ΔP)
  flowCv: number | null;             // std(flow) / mean(flow)
  samples: number;
}

function computeStd(arr: number[]): number {
  if (arr.length < 2) return NaN;
  const m = arr.reduce((a, b) => a + b, 0) / arr.length;
  const variance = arr.reduce((s, v) => s + (v - m) ** 2, 0) / arr.length;
  return Math.sqrt(variance);
}

function computeIqr(arr: number[]): number {
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
  return {
    ts: [], pressure: [], suction: [], flow: [], motor_power: [],
    motor_current: [], motor_temp: [], pump_rpm: [], bearing_vib: [], mix_ph: [],
    mix_ec: [], target_ph: [], target_ec: [], zone1_moisture: [], zone1_flow: [],
  };
}

function snapChartBuffer(b: ChartBuffer): ChartBuffer {
  return {
    ts: [...b.ts], pressure: [...b.pressure], suction: [...b.suction],
    flow: [...b.flow], motor_power: [...b.motor_power], motor_current: [...b.motor_current],
    motor_temp: [...b.motor_temp], pump_rpm: [...b.pump_rpm], bearing_vib: [...b.bearing_vib],
    mix_ph: [...b.mix_ph], mix_ec: [...b.mix_ec], target_ph: [...b.target_ph],
    target_ec: [...b.target_ec], zone1_moisture: [...b.zone1_moisture], zone1_flow: [...b.zone1_flow],
  };
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

const SOCKET_URL = "ws://localhost:8080/ws/smart-farm";
const HISTORY_URL = "/inference/history?limit=200";
const ALERT_MAX = 50;  // Alert 패널에 최대 50개까지만 보여주도록 (너무 많으면 렌더링 부담)
const STATUS_RECOMPUTE_INTERVAL_MS = 60 * 1000; // 1분마다 10분 윈도우 재평가

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

  // CTP 1시간 MAX 집계 버퍼 (메트릭당 최대 12개)
  const trendBuffersRef = useRef<CtpTrendBuffers>({});

  // 차트용 링버퍼 (ref — RAW 수신마다 업데이트, 렌더 안 일으킴)
  const chartBufRef = useRef<ChartBuffer>(makeEmptyChartBuffer());

  // 12h 비교분석용 링버퍼 (ΔP / flow, 최대 720포인트)
  const longBufRef = useRef<{ diffP: number[]; flow: number[] }>({
    diffP: [],
    flow: [],
  });

  // 최근 10분 INFERENCE 이상 이벤트 버퍼 (systemStatus 집계용)
  const alarmEventsRef = useRef<AlarmEvent[]>([]);

  // RAW 메시지 디바운싱: 150ms 안에 여러 메시지가 와도 마지막 것만 처리
  const latestRawRef = useRef<RawSensorPayload | null>(null);
  const rawDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 버퍼 기반으로 systemStatus 재계산
  const recomputeSystemStatus = () => {
    const now = Date.now();
    alarmEventsRef.current = pruneAlarmEvents(alarmEventsRef.current, now);
    setSystemStatus(computeSystemStatus(alarmEventsRef.current, now));
  };

  const handleRawPayload = (raw: RawSensorPayload) => {
    setRawSensorPayload(raw);

    // 차트 링버퍼 업데이트 (렌더 없음 — ref 직접 변이)
    const b = chartBufRef.current;
    const pushN = (arr: number[], v: unknown) =>
      arr.push(typeof v === "number" && Number.isFinite(v) ? v : NaN);
    const ts =
      typeof raw.timestamp === "string"
        ? Date.parse(raw.timestamp) || Date.now()
        : Date.now();
    pushN(b.ts, ts);
    pushN(b.pressure, raw.discharge_pressure_kpa);
    pushN(b.suction, raw.suction_pressure_kpa);
    pushN(b.flow, raw.flow_rate_l_min);
    pushN(b.motor_power, raw.motor_power_kw);
    pushN(b.motor_current, raw.motor_current_a);
    pushN(b.motor_temp, raw.motor_temperature_c);
    pushN(b.pump_rpm, raw.pump_rpm);
    pushN(b.bearing_vib, raw.bearing_vibration_rms_mm_s);
    pushN(b.mix_ph, raw.mix_ph);
    pushN(b.mix_ec, raw.mix_ec_ds_m);
    pushN(b.target_ph, raw.mix_target_ph);
    pushN(b.target_ec, raw.mix_target_ec_ds_m);
    pushN(b.zone1_moisture, raw.zone1_substrate_moisture_pct);
    pushN(b.zone1_flow, raw.zone1_flow_l_min);
    // 최대 CHART_MAX 포인트 유지
    (Object.values(b) as number[][]).forEach((arr) => {
      while (arr.length > CHART_MAX) arr.shift();
    });

    // 12h 비교분석 링버퍼 push
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

    // 환경정보 / CTP 카드 현재값
    setEnvironment((prev) => mapEnvironment(raw, prev));

    setCtpVisualizationMetrics((prev) => {
      const withCurrent = mapCtpCurrentValues(raw, prev);
      const nextBuffers = updateCtpTrendBuffers(trendBuffersRef.current, raw, prev);
      trendBuffersRef.current = nextBuffers;
      return applyBuffersToTrend(withCurrent, nextBuffers);
    });

    // 설비 탱크 수위
    const tankLevels = mapTankLevels(raw);
    setSensorData((prev) => ({
      ...prev,
      waterLevel: tankLevels.rawTankLevel ?? prev.waterLevel,
      tankALevel: tankLevels.tankALevel ?? prev.tankALevel,
      tankBLevel: tankLevels.tankBLevel ?? prev.tankBLevel,
      acidTankLevel: tankLevels.acidTankLevel ?? prev.acidTankLevel,
      ph: typeof raw.mix_ph === "number" ? raw.mix_ph : prev.ph,
      ec: typeof raw.mix_ec_ds_m === "number" ? raw.mix_ec_ds_m : prev.ec,
      temperature:
        typeof raw.mix_temp_c === "number" ? raw.mix_temp_c : prev.temperature,
      pressure:
        typeof raw.discharge_pressure_kpa === "number"
          ? raw.discharge_pressure_kpa
          : prev.pressure,
    }));
  };

  useEffect(() => {
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
          // 디바운싱: 150ms 안에 오는 메시지는 마지막 것 하나만 처리
          latestRawRef.current = message.payload;
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
          // console.log("🔍 INFERENCE payload:", message.payload);
          console.log(
            "🔍 INFERENCE level:",
            message.payload.overall_alarm_level,
            "status:",
            message.payload.overall_status,
          );

          // 10분 윈도우 집계 버퍼에 이벤트 누적 → systemStatus 재계산
          //  overall_alarm_level: 0=Normal, 1=Caution, 2=Warning, 3=Error
          const ts = parseTimestampToMs(message.payload.timestamp);
          alarmEventsRef.current = pruneAlarmEvents(
            [...alarmEventsRef.current, { ts, level: message.payload.overall_alarm_level }],
            Date.now(),
          );
          recomputeSystemStatus();

          setLatestInference(message.payload);
          setChartSnapshot(snapChartBuffer(chartBufRef.current));

          // 비교분석 지표 계산 (12h 링버퍼 스냅샷)
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
          setComparativeMetrics({
            pressureVolatility: pVol,
            flowCv: fCv,
            samples,
          });

          const newAlerts = mapInferenceToAlerts(message.payload);
          if (newAlerts.length > 0) {
            setAlertItems((prev) => {
              const existingIds = new Set(prev.map((item) => item.id));
              const fresh = newAlerts.filter((a) => !existingIds.has(a.id));
              if (fresh.length === 0) return prev;
              return [...fresh, ...prev].slice(0, ALERT_MAX);
            });
          }
          return;
        }

        // dashboard_init / dashboard_update (서버 측에서 가공된 페이로드)
        const payload = message.payload;
        if (payload.systemStatus) setSystemStatus(payload.systemStatus);
        if (payload.environment) setEnvironment(payload.environment);
        if (payload.ctpVisualizationMetrics)
          setCtpVisualizationMetrics(payload.ctpVisualizationMetrics);
        if (payload.kpiItems) setKpiItems(payload.kpiItems);
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

  // 새 INFERENCE가 없어도 시간이 흐르면 오래된 이벤트가 윈도우를 벗어나므로 주기 재평가
  useEffect(() => {
    const timer = setInterval(recomputeSystemStatus, STATUS_RECOMPUTE_INTERVAL_MS);
    return () => clearInterval(timer);
  }, []);

  // 마운트 직후 DB에 쌓여 있던 추론 이력을 한 번 가져와 Alert 이력 초기화
  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const res = await fetch(HISTORY_URL);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const rows: InferencePayload[] = await res.json();
        if (cancelled) return;

        const alerts: AlertItem[] = [];
        const seen = new Set<string>();
        for (const row of rows) {
          for (const alert of mapInferenceToAlerts(row)) {
            if (seen.has(alert.id)) continue;
            seen.add(alert.id);
            alerts.push(alert);
          }
        }

        // API는 최신 순(ORDER BY created_at DESC)으로 주므로 그대로 사용
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
