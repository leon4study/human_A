import Panel from "../common/Panel";
import type { CtpMetric } from "../../types/dashboard";

interface CtpStatusPanelProps {
  metrics: CtpMetric[];
  selectedId: string | null;
  onSelect: (metric: CtpMetric) => void;
}

function CtpStatusPanel({
  metrics,
  selectedId,
  onSelect,
}: CtpStatusPanelProps) {
  return (
    <Panel title="CTP 상태">
      <div className="ctp-grid">
        {metrics.map((item) => (
          <button
            type="button"
            key={item.id}
            className={`ctp-card ctp-card--${item.level} ${
              selectedId === item.id ? "is-selected" : ""
            }`}
            onClick={() => onSelect(item)}
          >
            <span>{item.label}</span>
            <strong>
              {item.value} <em>{item.unit}</em>
            </strong>
          </button>
        ))}
      </div>
    </Panel>
  );
}

export default CtpStatusPanel;