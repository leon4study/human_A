import { memo } from "react";
import Panel from "../common/Panel";
import "../../styles/kpipanel.css";
import type { KpiItem } from "../../types/dashboard";

interface KpiPanelProps {
  items: KpiItem[];
}

function KpiPanel({ items }: KpiPanelProps) {
  const smallItems = items.filter((item) => item.size === "small");
  const largeItems = items.filter((item) => item.size === "large");

  if (smallItems.length === 0 && largeItems.length === 0) {
    return (
      <Panel title="KPI 현황">
        <div className="kpi-layout">데이터가 없습니다.</div>
      </Panel>
    );
  }

  return (
    <Panel title="KPI 현황">
      <div className="kpi-layout">
        {smallItems.length > 0 && (
          <div className="kpi-row">
            {smallItems.map((item) => (
              <div key={item.id} className="kpi-item">
                <div
                  className={`kpi-gauge kpi-gauge--small kpi-gauge--${item.color}`}
                  style={{ ["--percent" as string]: item.value }}
                >
                  <div className="kpi-gauge__inner">
                    <strong className="kpi-gauge__value">{item.value}%</strong>
                  </div>
                </div>
                <span className="kpi-gauge__label">{item.label}</span>
              </div>
            ))}
          </div>
        )}

        {largeItems.map((item) => (
          <div key={item.id} className="kpi-item kpi-item--large">
            <div
              className={`kpi-gauge kpi-gauge--large kpi-gauge--${item.color}`}
              style={{ ["--percent" as string]: item.value }}
            >
              <div className="kpi-gauge__inner">
                <strong className="kpi-gauge__value">{item.value}%</strong>
              </div>
            </div>
            <span className="kpi-gauge__label">{item.label}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

export default memo(KpiPanel);
