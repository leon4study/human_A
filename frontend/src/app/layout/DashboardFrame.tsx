import "../styles/dashboard.css";
import CurrentTime from "../components/common/CurrentTime";
import KpiPanel from "../components/side/KpiPanel";
import AlertHistoryPanel from "../components/side/AlertHistoryPanel";
import ZoneStatusPanel from "../components/side/ZoneStatusPanel";
import EnvironmentPanel from "../components/side/EnvironmentPanel";
import CtpStatusPanel from "../components/side/CtpStatusPanel";
import CenterPlaceholder from "../components/center/CenterPlaceholder";
import type { SystemStatus } from "../components/common/SystemStatus";
import { systemStatusMap } from "../components/common/SystemStatus";

function DashboardFrame() {
    const systemStatus: SystemStatus = "warning"; // "normal" | "warning" | "danger"
    const currentStatus = systemStatusMap[systemStatus];

  return (
    <div className="dashboard">
      {/* 상단 바 */}
      <header className="dashboard__header">
        {/* 상단 좌측 바 */}
        <div className="dashboard__header-left">
            <div className="dashboard__title-wrap">
                <div className="dashboard__title">스마트팜 배양액 공급 시스템</div>

                <div className={`dashboard__system-status ${currentStatus.className}`}>
                    <span className="dashboard__system-icon">{currentStatus.icon}</span>
                    <span className="dashboard__system-text">{currentStatus.text}</span>
                </div>
            </div>
        </div>

        {/* 상단 중앙 바 */}
        <footer className="dashboard__header-center">
            <button className="dashboard__top-device-button is-active">1호기</button>
            <button className="dashboard__top-device-button">2호기</button>
            <button className="dashboard__top-device-button">3호기</button>
        </footer>

        {/* 상단 우측 바 */}
        <div className="dashboard__header-right">
          <button className="dashboard__ai-button">AI 분석결과 페이지 버튼</button>
          <div className="dashboard__time">
            <CurrentTime />
          </div>
        </div>
      </header>

      {/* 본문 전체 */}
      <main className="dashboard__body">

        {/* 좌측 패널 영역 */}
        <aside className="dashboard__left-panels">
          <KpiPanel />
          <AlertHistoryPanel />
          <ZoneStatusPanel />
        </aside>

        {/* 중앙 영역 */}

          <CenterPlaceholder />


        {/* 우측 패널 영역 */}
        <aside className="dashboard__right-panels">
          <EnvironmentPanel />
          <CtpStatusPanel />
        </aside>
      </main>

    </div>
  );
}

export default DashboardFrame;