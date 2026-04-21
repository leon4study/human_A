import { memo } from "react";
import Panel from "../common/Panel";
import type { EnvironmentItem } from "../../types/dashboard";

interface EnvironmentPanelProps {
  items: EnvironmentItem[];
}

function EnvironmentPanel({ items }: EnvironmentPanelProps) {
  return (
    <Panel title="환경 정보">
      <div className="panel-list">
        {items.map((item) => (
          <div className="panel-row" key={item.id}>
            <span>{item.label}</span>
            <strong>
              {item.value} {item.unit}
            </strong>
          </div>
        ))}
      </div>
    </Panel>
  );
}

export default memo(EnvironmentPanel);