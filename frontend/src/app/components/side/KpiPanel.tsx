import Panel from "../common/Panel";
import "../../styles/kpipanel.css";

function KpiPanel() {
  return (
    <Panel title="KPI 현황">
      <div className="kpi-layout">
        {/* 상단: 작은 원 2개 세트 */}
        <div className="kpi-row">
          <div className="kpi-item">
            <div
              className="kpi-gauge kpi-gauge--small kpi-gauge--green"
              style={{ ["--percent" as string]: 85 }}
            >
              <div className="kpi-gauge__inner">
                <strong className="kpi-gauge__value">85%</strong>
              </div>
            </div>
            <span className="kpi-gauge__label">가동율</span>
          </div>

          <div className="kpi-item">
            <div
              className="kpi-gauge kpi-gauge--small kpi-gauge--orange"
              style={{ ["--percent" as string]: 10 }}
            >
              <div className="kpi-gauge__inner">
                <strong className="kpi-gauge__value">10%</strong>
              </div>
            </div>
            <span className="kpi-gauge__label">고장율</span>
          </div>
        </div>

        {/* 하단: 큰 원 1개 */}
        <div className="kpi-item kpi-item--large">
          <div
            className="kpi-gauge kpi-gauge--large kpi-gauge--blue"
            style={{ ["--percent" as string]: 81 }}
          >
            <div className="kpi-gauge__inner">
              <strong className="kpi-gauge__value">81%</strong>
            </div>
          </div>
          <span className="kpi-gauge__label">설비 종합 효율</span>
        </div>
      </div>
    </Panel>
  );
}

export default KpiPanel;