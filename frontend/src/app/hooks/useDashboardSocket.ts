import { useEffect, useState } from "react";
import type {
  AlertItem,
  AnySocketMessage,
  CtpVisualizationMetric,
  EnvironmentItem,
  KpiItem,
  ZoneItem,
} from "../types/dashboard";
import { environmentData } from "../data/environmentData";
import { ctpVisualizationData } from "../data/ctpVisualizationData";
import { kpiData } from "../data/kpiData";
import { alertData } from "../data/alertData";
import { zoneData } from "../data/zoneData";
import type { SystemStatus } from "../components/common/SystemStatus";

interface DashboardSocketState {
  systemStatus: SystemStatus;
  environment: EnvironmentItem[];
  ctpVisualizationMetrics: CtpVisualizationMetric[];
  kpiItems: KpiItem[];
  alertItems: AlertItem[];
  zoneItems: ZoneItem[];
  socketStatus: "connecting" | "open" | "closed" | "error";
}

const SOCKET_URL = "ws://localhost:8080/ws/smart-farm";



function useDashboardSocket(): DashboardSocketState {
  const [systemStatus, setSystemStatus] = useState<SystemStatus>("danger");
  const [environment, setEnvironment] = useState<EnvironmentItem[]>(environmentData);
  const [ctpVisualizationMetrics, setCtpVisualizationMetrics] = useState<CtpVisualizationMetric[]>(ctpVisualizationData);
  const [kpiItems, setKpiItems] = useState<KpiItem[]>(kpiData);
  const [alertItems, setAlertItems] = useState<AlertItem[]>(alertData);
  const [zoneItems, setZoneItems] = useState<ZoneItem[]>(zoneData);
  const [socketStatus, setSocketStatus] = useState<"connecting" | "open" | "closed" | "error">("connecting");

  useEffect(() => {
    const socket = new WebSocket(SOCKET_URL);

    socket.onopen = () => {
      setSocketStatus("open");
      console.log("✅ FastAPI 실시간 서버 연결 성공!");
    };

    socket.onmessage = (event) => {
      try {
        const message: AnySocketMessage = JSON.parse(event.data);
        console.log("📥 받은 메시지:", message);

        if (message.type === "RAW" || message.type === "INFERENCE") {
          // TODO: 백엔드 센서 데이터 → 각 패널 상태 매핑 (추후 작업)
          return;
        }

        const payload = message.payload;

        if (payload.systemStatus) setSystemStatus(payload.systemStatus);
        if (payload.environment) setEnvironment(payload.environment);
        if (payload.ctpVisualizationMetrics) setCtpVisualizationMetrics(payload.ctpVisualizationMetrics);
        if (payload.kpiItems) setKpiItems(payload.kpiItems);
        if (payload.alertItems) setAlertItems(payload.alertItems);
        if (payload.zoneItems) setZoneItems(payload.zoneItems);
      } catch (error) {
        console.error("❌ 데이터 파싱 에러:", error);
      }
    };

    socket.onerror = () => {
      setSocketStatus("error");
      console.error("❌ 웹소켓 연결 에러");
    };

    socket.onclose = () => {
      setSocketStatus("closed");
      console.log("🔌 서버 연결 종료");
    };

    return () => {
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
    socketStatus,
  };
}

export default useDashboardSocket;