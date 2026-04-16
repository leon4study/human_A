import Panel from "../common/Panel";
import type { AlertItem } from "../../types/dashboard";

interface AlertHistoryPanelProps {
  items: AlertItem[];
}

function AlertHistoryPanel({ items }: AlertHistoryPanelProps) {
  return (
    <Panel title="Alert 이력">
      <div className="alert-table">
        <div className="alert-table__head">
          <span>시간</span>
          <span>장비</span>
          <span>원인</span>
          <span>위험도</span>
        </div>

        <div className="alert-table__body">
          {items.map((item) => (
            <div className="alert-table__row" key={item.id}>
              <span>{item.time}</span>
              <span>{item.equipment}</span>
              <span>{item.cause}</span>
              <span>{item.level}</span>
            </div>
          ))}
        </div>
      </div>
    </Panel>
  );
}

export default AlertHistoryPanel;