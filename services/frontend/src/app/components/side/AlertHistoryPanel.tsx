import { memo } from "react";
import Panel from "../common/Panel";
import type { AlertItem } from "../../types/dashboard";

interface AlertHistoryPanelProps {
  items: AlertItem[];
}

function getAlertLevelClass(level: string) {
  // level 값에 맞는 색상 클래스 반환
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
          {items.length === 0 ? (
            <div className="alert-table__row">
              <span>---</span>
              <span>---</span>
              <span>표시할</span>
              <span>Alert 이력 없음</span>
              <span>---</span>
            </div>
          ) : (
            items.map((item) => (
              <div className="alert-table__row" key={item.id}>
                {/* 발생 날짜 표시 */}
                <span>{item.date}</span>

                {/* 발생 시간 표시 */}
                <span>{item.time}</span>

                {/* 도메인 유형 표시 */}
                <span>{item.type}</span>

                {/* 주요 원인 표시 */}
                <span>{item.cause}</span>

                {/* 위험도 색상 반영 */}
                <span className={getAlertLevelClass(item.level)}>{item.level}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </Panel>
  );
}

export default memo(AlertHistoryPanel);
