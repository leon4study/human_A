import { memo } from "react";
import Panel from "../common/Panel";
import type { CtpVisualizationMetric } from "../../types/dashboard";

interface CtpVisualizationPanelProps {
  selectedMetric: CtpVisualizationMetric | null;
}

interface ChartPoint {
  x: number;
  y: number;
  value: number;
}

interface Segment {
  polygonPoints: string;
  linePath: string;
}

function formatTickLabel(timestamp: number, index: number, total: number): string {
  const date = new Date(timestamp);
  const hour = String(date.getHours()).padStart(2, "0");
  const minute = String(date.getMinutes()).padStart(2, "0");

  // 라벨을 전부 찍으면 너무 촘촘해지기 때문에 일부만 표시
  if (total > 8 && index % Math.ceil(total / 6) !== 0 && index !== total - 1) {
    return "";
  }

  return `${hour}:${minute}`;
}

function buildCriticalSegments(
  points: ChartPoint[],
  criticalSeries: number[],
  direction: "high" | "low",
  chartHeight: number,
  normalizeY: (value: number) => number,
): Segment[] {
  const segments: Segment[] = [];

  // high 모드는 아래쪽을 채우고,
  // low 모드는 위쪽을 채워서 초과 영역을 보이게 한다
  const fillBaseY = direction === "low" ? 0 : chartHeight;

  const isExceeded = (value: number, critical: number) =>
    direction === "low" ? value < critical : value > critical;

  for (let i = 0; i < points.length - 1; i += 1) {
    const start = points[i];
    const end = points[i + 1];
    const startCritical = criticalSeries[i] ?? criticalSeries[criticalSeries.length - 1];
    const endCritical = criticalSeries[i + 1] ?? startCritical;
    const startExceeded = isExceeded(start.value, startCritical);
    const endExceeded = isExceeded(end.value, endCritical);

    // 두 점 모두 정상 범위면 채울 필요가 없다
    if (!startExceeded && !endExceeded) continue;

    // 두 점이 모두 critical을 넘은 구간은 그대로 사각형처럼 채움
    if (startExceeded && endExceeded) {
      segments.push({
        polygonPoints: `${start.x},${fillBaseY} ${start.x},${start.y} ${end.x},${end.y} ${end.x},${fillBaseY}`,
        linePath: `M ${start.x} ${start.y} L ${end.x} ${end.y}`,
      });
      continue;
    }

    // 한 점만 초과한 경우는 threshold와 만나는 교차점을 계산해서
    // 초과 구간만 정확히 채움
    const numerator = startCritical - start.value;
    const denominator = end.value - start.value;
    const ratio = denominator === 0 ? 0 : numerator / denominator;
    const clampedRatio = Math.min(1, Math.max(0, ratio));
    const crossX = start.x + (end.x - start.x) * clampedRatio;
    const crossCritical = startCritical + (endCritical - startCritical) * clampedRatio;
    const crossY = normalizeY(crossCritical);

    if (startExceeded && !endExceeded) {
      segments.push({
        polygonPoints: `${start.x},${fillBaseY} ${start.x},${start.y} ${crossX},${crossY} ${crossX},${fillBaseY}`,
        linePath: `M ${start.x} ${start.y} L ${crossX} ${crossY}`,
      });
      continue;
    }

    segments.push({
      polygonPoints: `${crossX},${fillBaseY} ${crossX},${crossY} ${end.x},${end.y} ${end.x},${fillBaseY}`,
      linePath: `M ${crossX} ${crossY} L ${end.x} ${end.y}`,
    });
  }

  return segments;
}

function linePathFromSeries(series: number[], chartWidth: number, normalizeY: (value: number) => number): string {
  if (series.length === 0) return "";

  // threshold도 시점마다 바뀔 수 있으므로 고정선이 아니라 path로 그린다
  return series
    .map((value, index) => {
      const x = series.length === 1 ? 0 : (index / (series.length - 1)) * chartWidth;
      const y = normalizeY(value);
      return `${index === 0 ? "M" : "L"} ${x} ${y}`;
    })
    .join(" ");
}

function CtpVisualizationPanel({ selectedMetric }: CtpVisualizationPanelProps) {
  const chartWidth = 100;
  const chartHeight = 180;

  if (!selectedMetric) {
    return (
      <Panel title="CTP 시각화">
        <div className="ctp-visualization ctp-visualization--empty">
          <div className="ctp-visualization__placeholder">시각화 할 CTP를 선택해주세요.</div>
        </div>
      </Panel>
    );
  }

  const values = selectedMetric.trend;
  const timestamps = selectedMetric.timestamps ?? [];

  // 실제 시계열이 아직 없으면 빈 상태 표시
  if (values.length === 0) {
    return (
      <Panel title="CTP 시각화">
        <div className="ctp-visualization ctp-visualization--empty">
          <div className="ctp-visualization__placeholder">표시할 12시간 데이터 없음</div>
        </div>
      </Panel>
    );
  }

  // threshold 시계열이 없으면 현재 threshold를 길이에 맞춰 임시로 채움
  const cautionSeries = selectedMetric.cautionTrend ?? Array.from({ length: values.length }, () => selectedMetric.caution);
  const warningSeries = selectedMetric.warningTrend ?? Array.from({ length: values.length }, () => selectedMetric.warning);
  const criticalSeries = selectedMetric.criticalTrend ?? Array.from({ length: values.length }, () => selectedMetric.critical);
  const cautionLowerSeries = selectedMetric.cautionLowerTrend ?? [];
  const warningLowerSeries = selectedMetric.warningLowerTrend ?? [];
  const criticalLowerSeries = selectedMetric.criticalLowerTrend ?? [];

  const rangeCandidates = [
    ...values,
    ...cautionSeries,
    ...warningSeries,
    ...criticalSeries,
    ...cautionLowerSeries,
    ...warningLowerSeries,
    ...criticalLowerSeries,
  ].filter((value) => Number.isFinite(value));

  // 유효 숫자가 하나도 없으면 그래프 대신 빈 상태 표시
  if (rangeCandidates.length === 0) {
    return (
      <Panel title="CTP 시각화">
        <div className="ctp-visualization ctp-visualization--empty">
          <div className="ctp-visualization__placeholder">표시할 유효 데이터 없음</div>
        </div>
      </Panel>
    );
  }

  const minValue = Math.min(...rangeCandidates) * 0.95;
  const maxValue = Math.max(...rangeCandidates) * 1.05;

  const normalizeX = (index: number) => {
    if (values.length === 1) return 0;
    return (index / (values.length - 1)) * chartWidth;
  };

  const normalizeY = (value: number) => {
    if (maxValue === minValue) return chartHeight / 2;
    return chartHeight - ((value - minValue) / (maxValue - minValue)) * chartHeight;
  };

  const points: ChartPoint[] = values.map((value, index) => ({
    x: normalizeX(index),
    y: normalizeY(value),
    value,
  }));

  const linePath = points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`)
    .join(" ");

  // 카드 옆 라벨 위치는 현재 threshold 값 기준으로 설정
  const cautionY = normalizeY(selectedMetric.caution);
  const warningY = normalizeY(selectedMetric.warning);
  const criticalY = normalizeY(selectedMetric.critical);

  // critical을 넘은 구간만 따로 채우기 위해 segment를 미리 계산
  const criticalSegments = buildCriticalSegments(
    points,
    criticalSeries,
    selectedMetric.direction,
    chartHeight,
    normalizeY,
  );

  const patternId = `ctp-critical-pattern-${selectedMetric.id}`;

  // range 모드는 upper/lower threshold를 둘 다 그려야 한다
  const showRange = selectedMetric.thresholdMode === "range";

  return (
    <Panel title="CTP 시각화">
      <div className="ctp-visualization">
        <div className="ctp-visualization__head">
          <div className="ctp-visualization__title">{selectedMetric.label}</div>
        </div>

        <div className="ctp-chart">
          <div className="ctp-chart__line-label ctp-chart__line-label--caution" style={{ top: `${cautionY - 10}px` }}>
            Caution
          </div>
          <div className="ctp-chart__line-label ctp-chart__line-label--warning" style={{ top: `${warningY - 10}px` }}>
            Warning
          </div>
          <div className="ctp-chart__line-label ctp-chart__line-label--critical" style={{ top: `${criticalY - 10}px` }}>
            Critical
          </div>

          <div className="ctp-chart__threshold ctp-chart__threshold--caution" style={{ top: `${cautionY}px` }} />
          <div className="ctp-chart__threshold ctp-chart__threshold--warning" style={{ top: `${warningY}px` }} />
          <div className="ctp-chart__threshold ctp-chart__threshold--critical" style={{ top: `${criticalY}px` }} />

          {showRange && selectedMetric.cautionLower !== undefined && (
            <div className="ctp-chart__threshold ctp-chart__threshold--caution" style={{ top: `${normalizeY(selectedMetric.cautionLower)}px`, opacity: 0.55 }} />
          )}
          {showRange && selectedMetric.warningLower !== undefined && (
            <div className="ctp-chart__threshold ctp-chart__threshold--warning" style={{ top: `${normalizeY(selectedMetric.warningLower)}px`, opacity: 0.55 }} />
          )}
          {showRange && selectedMetric.criticalLower !== undefined && (
            <div className="ctp-chart__threshold ctp-chart__threshold--critical" style={{ top: `${normalizeY(selectedMetric.criticalLower)}px`, opacity: 0.55 }} />
          )}

          <svg className="ctp-chart__svg" viewBox={`0 0 ${chartWidth} ${chartHeight}`} preserveAspectRatio="none">
            <defs>
              <pattern id={patternId} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(25)">
                <line x1="0" y1="0" x2="0" y2="6" className="ctp-chart__critical-pattern-line" />
              </pattern>
            </defs>

            {cautionSeries.length > 0 && (
              <path d={linePathFromSeries(cautionSeries, chartWidth, normalizeY)} className="ctp-chart__threshold-path ctp-chart__threshold-path--caution" />
            )}
            {warningSeries.length > 0 && (
              <path d={linePathFromSeries(warningSeries, chartWidth, normalizeY)} className="ctp-chart__threshold-path ctp-chart__threshold-path--warning" />
            )}
            {criticalSeries.length > 0 && (
              <path d={linePathFromSeries(criticalSeries, chartWidth, normalizeY)} className="ctp-chart__threshold-path ctp-chart__threshold-path--critical" />
            )}

            {showRange && cautionLowerSeries.length > 0 && (
              <path d={linePathFromSeries(cautionLowerSeries, chartWidth, normalizeY)} className="ctp-chart__threshold-path ctp-chart__threshold-path--caution" style={{ opacity: 0.55 }} />
            )}
            {showRange && warningLowerSeries.length > 0 && (
              <path d={linePathFromSeries(warningLowerSeries, chartWidth, normalizeY)} className="ctp-chart__threshold-path ctp-chart__threshold-path--warning" style={{ opacity: 0.55 }} />
            )}
            {showRange && criticalLowerSeries.length > 0 && (
              <path d={linePathFromSeries(criticalLowerSeries, chartWidth, normalizeY)} className="ctp-chart__threshold-path ctp-chart__threshold-path--critical" style={{ opacity: 0.55 }} />
            )}

            <path d={linePath} className="ctp-chart__path" />

            {criticalSegments.map((segment, index) => (
              <g key={`${selectedMetric.id}-critical-${index}`}>
                <polygon points={segment.polygonPoints} className="ctp-chart__critical-fill" />
                <polygon points={segment.polygonPoints} fill={`url(#${patternId})`} />
                <path d={segment.linePath} className="ctp-chart__path ctp-chart__path--critical" />
              </g>
            ))}
          </svg>
        </div>

        <div className="ctp-chart__xlabels" style={{ gridTemplateColumns: `repeat(${values.length}, 1fr)` }}>
          {values.map((_, index) => (
            <span key={index}>{timestamps[index] ? formatTickLabel(timestamps[index], index, values.length) : `T${index + 1}`}</span>
          ))}
        </div>
      </div>
    </Panel>
  );
}

// 선택된 metric이 바뀔 때만 다시 그리게 해서 SVG 재렌더를 축소
export default memo(CtpVisualizationPanel);