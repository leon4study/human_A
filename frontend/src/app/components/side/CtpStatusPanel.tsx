import Panel from "../common/Panel";
import type { CtpVisualizationMetric } from "../../types/dashboard";

interface CtpStatusPanelProps {
  metrics: CtpVisualizationMetric[];
  selectedId: string | null;
  onSelect: (metricId: string) => void;
}

function CtpStatusPanel({
  metrics,
  selectedId,
  onSelect,
}: CtpStatusPanelProps) {
  const getStatus = (
    value: number,
    caution: number,
    critical: number,
  ): "normal" | "warning" | "danger" => {
    if (value < caution) {
      return "normal";
    }

    if (value < critical) {
      return "warning";
    }

    return "danger";
  };

  return (
    <Panel title="CTP 상태">
      <div className="ctp-grid">
        {metrics.map((metric) => {
          const status = getStatus(
            metric.value,
            metric.caution,
            metric.critical,
          );

          return (
            <button
              type="button"
              key={metric.id}
              className={`ctp-card ctp-card--${status} ${
                selectedId === metric.id ? "is-selected" : ""
              }`}
              onClick={() => onSelect(metric.id)}
            >
              <span>{metric.label}</span>
              <strong>
                {metric.value} <em>{metric.unit}</em>
              </strong>
            </button>
          );
        })}
      </div>
    </Panel>
  );
}

export default CtpStatusPanel;