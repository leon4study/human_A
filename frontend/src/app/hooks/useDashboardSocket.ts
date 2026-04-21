import { useEffect, useRef, useState } from "react";
import type {
  AlertItem,
  AnySocketMessage,
  CtpVisualizationMetric,
  EnvironmentItem,
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
  mapCtpCurrentValues,
  mapEnvironment,
  mapInferenceToAlert,
  mapInferenceToSystemStatus,
  mapTankLevels,
  updateCtpTrendBuffers,
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
const ALERT_MAX = 500;

function useDashboardSocket(): DashboardSocketState {
  const [systemStatus, setSystemStatus] = useState<SystemStatus>("danger");
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
          handleRawPayload(message.payload);
          return;
        }

        if (message.type === "INFERENCE") {
          const nextSystemStatus = mapInferenceToSystemStatus(
            message.payload.overall_alarm_level,
          );
          if (nextSystemStatus) setSystemStatus(nextSystemStatus);

          const alert = mapInferenceToAlert(message.payload);
          if (alert) {
            setAlertItems((prev) => {
              if (prev.some((item) => item.id === alert.id)) return prev;
              return [alert, ...prev].slice(0, ALERT_MAX);
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
        if (payload.alertItems) setAlertItems(payload.alertItems);
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
