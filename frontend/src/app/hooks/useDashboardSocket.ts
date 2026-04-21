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

interface DashboardSocketState {
  systemStatus: SystemStatus;
  environment: EnvironmentItem[];
  ctpVisualizationMetrics: CtpVisualizationMetric[];
  kpiItems: KpiItem[];
  alertItems: AlertItem[];
  zoneItems: ZoneItem[];
  sensorData: SensorData;
  socketStatus: "connecting" | "open" | "closed" | "error";
}

const SOCKET_URL = "ws://localhost:8080/ws/smart-farm";
const HISTORY_URL = "http://localhost:8080/inference/history?limit=200";
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
  const [socketStatus, setSocketStatus] =
    useState<"connecting" | "open" | "closed" | "error">("connecting");

  // CTP 1시간 MAX 집계 버퍼 (메트릭당 최대 12개)
  const trendBuffersRef = useRef<CtpTrendBuffers>({});

  // 최근 10분 INFERENCE 이상 이벤트 버퍼 (systemStatus 집계용)
  const alarmEventsRef = useRef<AlarmEvent[]>([]);

  // 버퍼 기반으로 systemStatus 재계산
  const recomputeSystemStatus = () => {
    const now = Date.now();
    alarmEventsRef.current = pruneAlarmEvents(alarmEventsRef.current, now);
    setSystemStatus(computeSystemStatus(alarmEventsRef.current, now));
  };

  const handleRawPayload = (raw: RawSensorPayload) => {
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
          // [DEBUG] 원시 센서 데이터 수신 확인용 (확정되면 제거)
          // console.log("📡 [RAW데이터]", message.payload);
          handleRawPayload(message.payload);
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
    socketStatus,
  };
}

export default useDashboardSocket;
