import { memo } from "react";
import Panel from "../common/Panel";
import type { CtpVisualizationMetric } from "../../types/dashboard";

interface CtpStatusPanelProps {
  metrics: CtpVisualizationMetric[];
  selectedId: string | null;
  onSelect: (metricId: string) => void;
}

function hasFiniteThreshold(value: number | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

// 카드 색을 정할 때는 thresholdMode 우선 적용,
// direction 값 fallback 사용
function getMetricStatus(metric: CtpVisualizationMetric): "normal" | "warning" | "danger" {
  const mode = metric.thresholdMode ?? metric.direction;

  // threshold 미수신 상태, 중립 유지
  if (!Number.isFinite(metric.value)) return "normal";

  // range 모드, 상한/하한 동시 판정
  // EC, 전류처럼 너무 높아도 문제고 너무 낮아도 문제인 경우에 사용
  if (mode === "range") {
    const value = metric.value;
    const cautionLower = metric.cautionLower;
    const criticalLower = metric.criticalLower;

    // 상하한 threshold가 모두 준비되어야 판정
    if (
      !hasFiniteThreshold(metric.caution) ||
      !hasFiniteThreshold(metric.critical) ||
      !hasFiniteThreshold(cautionLower) ||
      !hasFiniteThreshold(criticalLower)
    ) {
      return "normal";
    }

    // critical 범위 이탈 시 danger
    const isCritical = value >= metric.critical || value <= criticalLower;
    if (isCritical) return "danger";

    // caution 범위 이탈 시 warning
    const isWarning = value >= metric.caution || value <= cautionLower;
    return isWarning ? "warning" : "normal";
  }

  // low 모드, 값 하락 시 위험
  // 유량처럼 떨어질수록 이상으로 보는 항목이 여기 유입
  if (mode === "low") {
    if (metric.value >= metric.caution) return "normal";
    if (metric.value >= metric.critical) return "warning";
    return "danger";
  }

  // 기본 high 모드
  // 값이 높아질수록 위험해지는 압력 같은 항목이 이 기준을 사용
  if (metric.value < metric.caution) return "normal";
  if (metric.value < metric.critical) return "warning";
  return "danger";
}

// 카드에 보여주는 숫자는 항목별로 자릿수를 다르게 맞춤
function formatMetricValue(metric: CtpVisualizationMetric) {
  // 값 미수신 시 --- 표시
  // 미수신 상태 바로 인지
  if (!Number.isFinite(metric.value)) return "---";

  // 전력, 정밀도 확보를 위해 2자리 표시
  if (metric.unit === "kW") return metric.value.toFixed(2);

  // 나머지 값은 카드 가독성을 위해 소수점 1자리로 맞춤
  return metric.value.toFixed(1);
}

function CtpStatusPanel({
  metrics,
  selectedId,
  onSelect,
}: CtpStatusPanelProps) {
  return (
    <Panel title="CTP 상태">
      <div className="ctp-grid">
        {metrics.map((metric) => {
          // 현재 값 기준 카드 상태 결정
          const status = getMetricStatus(metric);

          return (
            <button
              type="button"
              key={metric.id}
              // 선택된 카드인지 여부와 상태색을 같이 class에 반영
              className={`ctp-card ctp-card--${status} ${
                selectedId === metric.id ? "is-selected" : ""
              }`}
              // 카드를 누르면 아래 CTP 시각화 그래프가 이 metric 기준으로 변경
              onClick={() => onSelect(metric.id)}
            >
              <span>{metric.label}</span>
              <strong>
                {formatMetricValue(metric)} <em className="ctp-card__unit">{metric.unit}</em>
              </strong>
            </button>
          );
        })}
      </div>
    </Panel>
  );
}

// CTP 카드 배열은 값이 바뀔 때만 다시 그리도록 memo로 적용
export default memo(CtpStatusPanel);