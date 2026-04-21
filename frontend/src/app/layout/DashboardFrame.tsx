import { useMemo, useState } from "react";
import "../styles/tailwind.css";
import "../styles/dashboard.css";
import CurrentTime from "../components/common/CurrentTime";
import KpiPanel from "../components/side/KpiPanel";
import AlertHistoryPanel from "../components/side/AlertHistoryPanel";
import ZoneStatusPanel from "../components/side/ZoneStatusPanel";
import EnvironmentPanel from "../components/side/EnvironmentPanel";
import CtpStatusPanel from "../components/side/CtpStatusPanel";
import CtpVisualizationPanel from "../components/side/CtpVisualizationPanel";
import CenterPlaceholder from "../components/center/CenterPlaceholder";
import { systemStatusMap } from "../components/common/SystemStatus";
import useDashboardSocket from "../hooks/useDashboardSocket";
import ZoneCauseTopPanel from "../components/side/ZoneCauseTopPanel";
import EquipmentModal from "../components/detail/EquipmentModal";
import AiAnalysisModal from "../components/detail/AiAnalysisModal";
import type { Equipment } from "../components/center/facility/model/facility.types";

function DashboardFrame() {
  const {
    systemStatus,
    environment,
    ctpVisualizationMetrics,
    kpiItems,
    alertItems,
    zoneItems,
    sensorData,
  } = useDashboardSocket();

  const currentStatus = systemStatusMap[systemStatus];

  // 현재 선택된 CTP 항목 id
  const [selectedMetricId, setSelectedMetricId] = useState<string | null>(null);

  // 현재 선택된 구역 id
  const [selectedZoneId, setSelectedZoneId] = useState<string>(
    zoneItems[0]?.id ?? "",
  );

  // 현재 팝업으로 띄울 장비 정보
  const [selectedEquipment, setSelectedEquipment] = useState<Equipment | null>(
    null,
  );

  // AI 분석 팝업 열림 여부
  const [isAiModalOpen, setIsAiModalOpen] = useState(false);

  // 시각화에서 사용할 선택 항목 찾기
  const selectedMetric = useMemo(() => {
    if (!selectedMetricId) {
      return null;
    }

    return (
      ctpVisualizationMetrics.find((item) => item.id === selectedMetricId) ??
      null
    );
  }, [selectedMetricId, ctpVisualizationMetrics]);

  return (
    <div className="dashboard">
      {/* 전체 배경 레이어 */}
      <div className="dashboard__bg"></div>

      {/* UI 오버레이 레이어 */}
      <div className="dashboard__overlay">
        {/* 상단 바 */}
        <header className="dashboard__header">
          {/* 상단 좌측 바 */}
          <div className="dashboard__header-left">
            <div className="dashboard__title-wrap">
              <div className="dashboard__title">
                스마트팜 배양액 공급 시스템
              </div>

              <div
                className={`dashboard__system-status ${currentStatus.className}`}
              >
                <span className="dashboard__system-icon">
                  {currentStatus.icon}
                </span>
                <span className="dashboard__system-text">
                  {currentStatus.text}
                </span>
              </div>
            </div>
          </div>

          {/* 상단 중앙 바 */}
          <footer className="dashboard__header-center">
            <button className="dashboard__top-device-button is-active">
              1호기
            </button>
            <button className="dashboard__top-device-button">2호기</button>
            <button className="dashboard__top-device-button">3호기</button>
          </footer>

          {/* 상단 우측 바 */}
          <div className="dashboard__header-right">
            <button
              className="dashboard__ai-button"
              onClick={() => setIsAiModalOpen(true)}
            >
              AI 분석결과 페이지 버튼
            </button>
            <div className="dashboard__time">
              <CurrentTime />
            </div>
          </div>
        </header>

        {/* 본문 전체 */}
        <main className="dashboard__body">
          {/* 좌측 패널 영역 */}
          <aside className="dashboard__left-panels">
            <KpiPanel items={kpiItems} />
            <ZoneStatusPanel
              zoneItems={zoneItems}
              selectedZoneId={selectedZoneId}
              onSelectZone={setSelectedZoneId}
            />
            <ZoneCauseTopPanel
              selectedZoneId={selectedZoneId}
              zoneItems={zoneItems}
            />
          </aside>

          {/* 중앙 묶음 영역 */}
          <div className="dashboard__center-wrap">
            {/* 여기로 중앙 구조도를 옮겨야 클릭이 됩니다 */}
            <CenterPlaceholder
              onEquipmentSelect={setSelectedEquipment}
              sensorData={sensorData}
            />

            <div className="dashboard__center-spacer"></div>

            {/* 중앙 하단 영역 */}
            <div className="dashboard__bottom-panel">
              <AlertHistoryPanel items={alertItems} />
            </div>
          </div>

          {/* 우측 패널 영역 */}
          <aside className="dashboard__right-panels">
            <EnvironmentPanel items={environment} />
            <CtpStatusPanel
              metrics={ctpVisualizationMetrics}
              selectedId={selectedMetricId}
              onSelect={setSelectedMetricId}
            />
            <CtpVisualizationPanel selectedMetric={selectedMetric} />
          </aside>
        </main>

        {/* 하단 효과용 */}
        <div className="dashboard__bottom-fade"></div>
      </div>

      {/* 장비 상세 팝업 */}
      <EquipmentModal
        equipment={selectedEquipment}
        onClose={() => setSelectedEquipment(null)}
      />

      {/* AI 분석 결과 팝업 */}
      <AiAnalysisModal
        open={isAiModalOpen}
        onClose={() => setIsAiModalOpen(false)}
      />
    </div>
  );
}

export default DashboardFrame;
