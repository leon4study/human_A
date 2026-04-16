import { useEffect, useState } from "react";
import type {
  AlertItem,
  CtpMetric,
  DashboardSocketMessage,
  EnvironmentItem,
  KpiItem,
  ZoneItem,
} from "../types/dashboard";
import { environmentData } from "../data/environmentData";
import { ctpData } from "../data/ctpData";
import { kpiData } from "../data/kpiData";
import { alertData } from "../data/alertData";
import { zoneData } from "../data/zoneData";
import type { SystemStatus } from "../components/common/SystemStatus";

interface DashboardSocketState {
  systemStatus: SystemStatus;
  environment: EnvironmentItem[];
  ctpMetrics: CtpMetric[];
  kpiItems: KpiItem[];
  alertItems: AlertItem[];
  zoneItems: ZoneItem[];
  socketStatus: "connecting" | "open" | "closed" | "error";
}

const SOCKET_URL = "ws://localhost:8080/ws/dashboard";

function useDashboardSocket(): DashboardSocketState {
  const [systemStatus, setSystemStatus] = useState<SystemStatus>("warning");
  const [environment, setEnvironment] = useState<EnvironmentItem[]>(environmentData);
  const [ctpMetrics, setCtpMetrics] = useState<CtpMetric[]>(ctpData);
  const [kpiItems, setKpiItems] = useState<KpiItem[]>(kpiData);
  const [alertItems, setAlertItems] = useState<AlertItem[]>(alertData);
  const [zoneItems, setZoneItems] = useState<ZoneItem[]>(zoneData);
  const [socketStatus, setSocketStatus] = useState<"connecting" | "open" | "closed" | "error">("connecting");

  useEffect(() => {
    const socket = new WebSocket(SOCKET_URL);

    socket.onopen = () => {
      setSocketStatus("open");
    };

    socket.onmessage = (event) => {
      try {
        const message: DashboardSocketMessage = JSON.parse(event.data);
        const payload = message.payload;

        if (payload.systemStatus) {
          setSystemStatus(payload.systemStatus);
        }

        if (payload.environment) {
          setEnvironment(payload.environment);
        }

        if (payload.ctpMetrics) {
          setCtpMetrics(payload.ctpMetrics);
        }

        if (payload.kpiItems) {
          setKpiItems(payload.kpiItems);
        }

        if (payload.alertItems) {
          setAlertItems(payload.alertItems);
        }

        if (payload.zoneItems) {
          setZoneItems(payload.zoneItems);
        }

      } catch (error) {
        console.error("웹소켓 메시지 파싱 실패:", error);
      }
    };

    socket.onerror = () => {
      setSocketStatus("error");
    };

    socket.onclose = () => {
      setSocketStatus("closed");
    };

    return () => {
      socket.close();
    };
  }, []);

  return {
    systemStatus,
    environment,
    ctpMetrics,
    kpiItems,
    alertItems,
    zoneItems,
    socketStatus,
  };
}

export default useDashboardSocket;