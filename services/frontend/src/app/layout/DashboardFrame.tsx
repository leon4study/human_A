import { useLayoutEffect, useMemo, useState } from "react";
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

const DESIGN_W = 1920;
const DESIGN_H = 1080;
const DESIGN_ASPECT = DESIGN_W / DESIGN_H;

/**
 * 뷰포트를 letterbox 없이 꽉 채우면서 SVG 찌그러짐·텍스트 블러 없이 스케일.
 *
 * 전략:
 * - `zoom` 을 뷰포트의 "짧은 축" 에 맞춰 결정 (vh 또는 vw 중 하나) → 내부 px 치수는
 *   그 축 기준으로 정확히 뷰포트를 채움.
 * - 대시보드의 **설계 크기** 를 반대 축 방향으로 확장 → 긴 축도 뷰포트를 꽉 채움.
 *   내부 `flex:1` 영역(center-wrap) 이 확장을 흡수하고, facility-diagram-inner 는
 *   1100px 고정이라 비율 유지.
 * - `transform:scale` 대신 `zoom` 이라 텍스트는 새 크기로 재-레이아웃 → 블러 없음.
 */
function useFitScale() {
  useLayoutEffect(() => {
    const update = () => {
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const viewportAspect = vw / vh;

      let zoom: number;
      let width: number;
      let height: number;

      if (viewportAspect >= DESIGN_ASPECT) {
        zoom = vh / DESIGN_H;
        width = vw / zoom;
        height = DESIGN_H;
      } else {
        zoom = vw / DESIGN_W;
        width = DESIGN_W;
        height = vh / zoom;
      }

      const root = document.documentElement;
      root.style.setProperty("--app-zoom", String(zoom));
      root.style.setProperty("--app-width", `${width}px`);
      root.style.setProperty("--app-height", `${height}px`);
    };

    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);
}

function DashboardFrame() {
  useFitScale();

  const {
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
  } = useDashboardSocket();

  const currentStatus = systemStatusMap[systemStatus];

  // CTP 시각화에 반영할 선택 metric id
  const [selectedMetricId, setSelectedMetricId] = useState<string | null>(null);

  // 헤더 중앙 호기 버튼 전용 선택 상태
  // 왼쪽 패널의 "호기별 상태 / 막힘 원인 Top3" 선택 상태와 분리
  const [requestedHeaderZoneId, setRequestedHeaderZoneId] = useState<string>(
    zoneItems[0]?.id ?? "",
  );

  // 왼쪽 패널 전용 선택 상태
  // 호기별 상태를 누르면 아래 막힘 원인 Top3만 같이 바뀌도록 유지
  const [requestedSideZoneId, setRequestedSideZoneId] = useState<string>(
    zoneItems[0]?.id ?? "",
  );

  // 현재 팝업으로 띄울 장비 정보
  const [selectedEquipment, setSelectedEquipment] = useState<Equipment | null>(
    null,
  );

  // AI 분석 팝업 열림 상태
  const [isAiModalOpen, setIsAiModalOpen] = useState(false);

  // 현재 선택된 CTP metric 찾기
  const selectedMetric = useMemo(() => {
    if (!selectedMetricId) {
      return null;
    }

    return (
      ctpVisualizationMetrics.find((item) => item.id === selectedMetricId) ??
      null
    );
  }, [selectedMetricId, ctpVisualizationMetrics]);

  // 헤더 버튼 선택값 보정
  // 현재 목록에 없는 id가 남아 있으면 첫 번째 호기로 맞춤
  const headerZoneId =
    zoneItems.length === 0
      ? ""
      : zoneItems.some((zone) => zone.id === requestedHeaderZoneId)
        ? requestedHeaderZoneId
        : zoneItems[0].id;

  // 왼쪽 패널 선택값 보정
  // 현재 목록에 없는 id가 남아 있으면 첫 번째 호기로 맞춤
  const sideZoneId =
    zoneItems.length === 0
      ? ""
      : zoneItems.some((zone) => zone.id === requestedSideZoneId)
        ? requestedSideZoneId
        : zoneItems[0].id;

  return (
    <div className="dashboard-fit">
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
              {zoneItems.map((zone) => (
                <button
                  key={zone.id}
                  type="button"
                  className={`dashboard__top-device-button ${headerZoneId === zone.id ? "is-active" : ""}`}
                  // 헤더 중앙 호기 버튼 선택만 반영
                  // 왼쪽 패널 선택 상태와는 분리 유지
                  onClick={() => setRequestedHeaderZoneId(zone.id)}
                >
                  {zone.label}
                </button>
              ))}
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
                selectedZoneId={sideZoneId}
                // 왼쪽 호기 선택만 아래 Top3에 연동
                onSelectZone={setRequestedSideZoneId}
              />
              <ZoneCauseTopPanel
                selectedZoneId={sideZoneId}
                zoneItems={zoneItems}
              />
            </aside>

            {/* 중앙 묶음 영역 */}
            <div className="dashboard__center-wrap">
              {/* 중앙 구조도 */}
              {/* 현재는 헤더 호기 선택을 구조도 쪽에 전달하지 않음 */}
              {/* 추후 중앙 구조도 필터가 필요하면 headerZoneId를 별도 prop으로 추가 */}
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
          sensorPayload={rawSensorPayload}
          chartSnapshot={chartSnapshot}
          onClose={() => setSelectedEquipment(null)}
        />

        {/* AI 분석 결과 팝업 */}
        <AiAnalysisModal
          open={isAiModalOpen}
          inference={latestInference}
          chartSnapshot={chartSnapshot}
          comparativeMetrics={comparativeMetrics}
          onClose={() => setIsAiModalOpen(false)}
        />
      </div>
    </div>
  );
}

export default DashboardFrame;
