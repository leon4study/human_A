import { memo } from "react";
import Panel from "../common/Panel";
import type { AlertItem } from "../../types/dashboard";

interface AlertHistoryPanelProps {
  items: AlertItem[];
}

// 위험도 값에 따라 클래스명 반환
function getAlertLevelClass(level: string) {
  if (level === "CAUTION") {
    return "alert-level alert-level--yellow";
  }

  if (level === "WARNING") {
    return "alert-level alert-level--orange";
  }

  if (level === "CRITICAL") {
    return "alert-level alert-level--red";
  }

  return "alert-level";
}

function AlertHistoryPanel({ items }: AlertHistoryPanelProps) {
  return (
    <Panel title="Alert 이력">
      <div className="alert-table">
        <div className="alert-table__head">
          <span>날짜</span>
          <span>시간</span>
          <span>유형</span>
          <span>원인</span>
          <span>위험도</span>
        </div>

        <div className="alert-table__body">
          {items.map((item) => (
            <div className="alert-table__row" key={item.id}>
              <span>{item.date}</span>
              <span>{item.time}</span>
              <span>{item.type}</span>
              <span>{item.cause}</span>
              <span className={getAlertLevelClass(item.level)}>
                {item.level}
              </span>
            </div>
          ))}
        </div>
      </div>
    </Panel>
  );
}

export default memo(AlertHistoryPanel);
