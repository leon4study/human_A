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
 *
 * 예:
 * - 2560×1080 (ultrawide): zoom=1, width=2560, height=1080 — 좌우 letterbox 없음
 * - 1920×1200 (16:10):     zoom=1, width=1920, height=1200 — 상하 letterbox 없음
 * - 3840×2160 (4K 16:9):   zoom=2, width=1920, height=1080 — 균등 확대
 * - 1280×720:              zoom=0.667, width=1920, height=1080 — 균등 축소
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
        // 16:9 보다 넓음 → 높이를 기준으로 zoom, 너비를 뷰포트에 맞게 확장
        zoom = vh / DESIGN_H;
        width = vw / zoom;
        height = DESIGN_H;
      } else {
        // 16:9 보다 좁음 (세로가 김) → 너비 기준 zoom, 높이를 확장
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

  // 현재 선택된 CTP 항목 id
  const [selectedMetricId, setSelectedMetricId] = useState<string | null>(null);

  // 현재 사용자가 선택한 구역 id (요청 값).
  // 실제 화면/자식에 넘기는 "유효한" 값은 아래 effectiveZoneId 에서 렌더 시점
  // 계산한다. zoneItems 가 바뀌면서 이 값이 목록에 없게 되면 effect 로 보정하는
  // 대신 렌더 중 fallback → cascading render 방지.
  const [requestedZoneId, setSelectedZoneId] = useState<string>(
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

  // 요청 id 가 현재 목록에 없거나 목록이 비어있으면 안전한 값으로 대체 (렌더 파생).
  const selectedZoneId =
    zoneItems.length === 0
      ? ""
      : zoneItems.some((z) => z.id === requestedZoneId)
        ? requestedZoneId
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
                className={`dashboard__top-device-button ${selectedZoneId === zone.id ? "is-active" : ""}`}
                onClick={() => setSelectedZoneId(zone.id)}
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
