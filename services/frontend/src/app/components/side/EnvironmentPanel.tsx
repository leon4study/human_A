import { memo } from "react";
import Panel from "../common/Panel";
import type { EnvironmentItem } from "../../types/dashboard";

interface EnvironmentPanelProps {
  items: EnvironmentItem[];
}

function formatEnvironmentValue(item: EnvironmentItem) {
  // 숫자가 아니면 placeholder 표시
  if (typeof item.value !== "number" || !Number.isFinite(item.value)) {
    return "---";
  }

  // 광량 / CO₂는 정수형 표시
  if (item.id === "light" || item.id === "co2") {
    return Math.round(item.value).toString();
  }

  // 온도 / 습도는 소수점 1자리 표시
  return item.value.toFixed(1);
}

function EnvironmentPanel({ items }: EnvironmentPanelProps) {
  return (
    <Panel title="환경 정보">
      <div className="panel-list">
        {items.map((item) => (
          <div className="panel-row" key={item.id}>
            {/* 환경 항목명 표시 */}
            <span>{item.label}</span>

            <strong>
              {/* 화면 표시 자릿수 반영 */}
              {formatEnvironmentValue(item)} {item.unit}
            </strong>
          </div>
        ))}
      </div>
    </Panel>
  );
}

export default memo(EnvironmentPanel);
