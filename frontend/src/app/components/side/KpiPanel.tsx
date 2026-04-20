import Panel from "../common/Panel";
import "../../styles/kpipanel.css";
import type { KpiItem } from "../../types/dashboard";

interface KpiPanelProps {
  items: KpiItem[];
}

function KpiPanel({ items }: KpiPanelProps) {
  const operationRate = items.find((item) => item.id === "operation-rate");
  const failureRate = items.find((item) => item.id === "failure-rate");
  const overallEfficiency = items.find((item) => item.id === "overall-efficiency");

  if (!operationRate || !failureRate || !overallEfficiency) {
    return (
      <Panel title="KPI 현황">
        <div className="kpi-layout">데이터가 없습니다.</div>
      </Panel>
    );
  }

  return (
    <Panel title="KPI 현황">
      <div className="kpi-layout">
        <div className="kpi-row">
          <div className="kpi-item">
            <div
              className="kpi-gauge kpi-gauge--small kpi-gauge--green"
              style={{ ["--percent" as string]: operationRate.value }}
            >
              <div className="kpi-gauge__inner">
                <strong className="kpi-gauge__value">{operationRate.value}%</strong>
              </div>
            </div>
            <span className="kpi-gauge__label">{operationRate.label}</span>
          </div>

          <div className="kpi-item">
            <div
              className="kpi-gauge kpi-gauge--small kpi-gauge--orange"
              style={{ ["--percent" as string]: failureRate.value }}
            >
              <div className="kpi-gauge__inner">
                <strong className="kpi-gauge__value">{failureRate.value}%</strong>
              </div>
            </div>
            <span className="kpi-gauge__label">{failureRate.label}</span>
          </div>
        </div>

        <div className="kpi-item kpi-item--large">
          <div
            className="kpi-gauge kpi-gauge--large kpi-gauge--blue"
            style={{ ["--percent" as string]: overallEfficiency.value }}
          >
            <div className="kpi-gauge__inner">
              <strong className="kpi-gauge__value">{overallEfficiency.value}%</strong>
            </div>
          </div>
          <span className="kpi-gauge__label">{overallEfficiency.label}</span>
        </div>
      </div>
    </Panel>
  );
}

export default KpiPanel;