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

const DISPLAY_POINTS = 12;

function sampleSeries(series: number[] | undefined, target = DISPLAY_POINTS): number[] {
  if (!Array.isArray(series) || series.length === 0) return [];
  if (series.length === target) return [...series];

  const result: number[] = [];
  for (let index = 0; index < target; index += 1) {
    const sourceIndex = Math.round((index / Math.max(target - 1, 1)) * (series.length - 1));
    result.push(series[sourceIndex] ?? Number.NaN);
  }
  return result;
}

function buildThresholdLine(value: number | undefined, length: number): number[] {
  if (typeof value !== "number" || !Number.isFinite(value) || length <= 0) return [];
  return Array.from({ length }, () => value);
}

function buildCriticalSegments(
  points: ChartPoint[],
  criticalSeries: number[],
  direction: "high" | "low",
  chartHeight: number,
  normalizeY: (value: number) => number,
): Segment[] {
  const segments: Segment[] = [];
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

    if (!startExceeded && !endExceeded) continue;

    if (startExceeded && endExceeded) {
      segments.push({
        polygonPoints: `${start.x},${fillBaseY} ${start.x},${start.y} ${end.x},${end.y} ${end.x},${fillBaseY}`,
        linePath: `M ${start.x} ${start.y} L ${end.x} ${end.y}`,
      });
      continue;
    }

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

  return series
    .map((value, index) => {
      const x = series.length === 1 ? 0 : (index / (series.length - 1)) * chartWidth;
      const y = normalizeY(value);
      return `${index === 0 ? "M" : "L"} ${x} ${y}`;
    })
    .join(" ");
}

function isFiniteSeries(series?: number[]) {
  return Array.isArray(series) && series.some((value) => Number.isFinite(value));
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

  const values = sampleSeries(selectedMetric.trend, DISPLAY_POINTS);

  if (values.length === 0) {
    return (
      <Panel title="CTP 시각화">
        <div className="ctp-visualization ctp-visualization--empty">
          <div className="ctp-visualization__placeholder">표시할 데이터 없음</div>
        </div>
      </Panel>
    );
  }

  const cautionSeries = buildThresholdLine(selectedMetric.caution, values.length);
  const warningSeries = buildThresholdLine(selectedMetric.warning, values.length);
  const criticalSeries = buildThresholdLine(selectedMetric.critical, values.length);
  const cautionLowerSeries = buildThresholdLine(selectedMetric.cautionLower, values.length);
  const warningLowerSeries = buildThresholdLine(selectedMetric.warningLower, values.length);
  const criticalLowerSeries = buildThresholdLine(selectedMetric.criticalLower, values.length);

  const rangeCandidates = [
    ...values,
    ...cautionSeries,
    ...warningSeries,
    ...criticalSeries,
    ...cautionLowerSeries,
    ...warningLowerSeries,
    ...criticalLowerSeries,
  ].filter((value) => Number.isFinite(value));

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

  const hasCriticalSeries = isFiniteSeries(criticalSeries);
  const criticalSegments = hasCriticalSeries
    ? buildCriticalSegments(points, criticalSeries, selectedMetric.direction, chartHeight, normalizeY)
    : [];

  const patternId = `ctp-critical-pattern-${selectedMetric.id}`;
  const showRange = selectedMetric.thresholdMode === "range";

  return (
    <Panel title="CTP 시각화">
      <div className="ctp-visualization">
        <div className="ctp-visualization__head">
          <div className="ctp-visualization__title">{selectedMetric.label}</div>
        </div>

        <div className="ctp-chart">
          <svg className="ctp-chart__svg" viewBox={`0 0 ${chartWidth} ${chartHeight}`} preserveAspectRatio="none">
            {/* 패턴 정의: 대각선 줄무늬(빗금패턴)로 위험 구간 강조 */}
            <defs>
              <pattern id={patternId} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(25)">
                <line x1="0" y1="0" x2="0" y2="6" className="ctp-chart__critical-pattern-line" />
              </pattern>
            </defs>
            
            {/* 상한선 */}
            {isFiniteSeries(cautionSeries) && (
              <path d={linePathFromSeries(cautionSeries, chartWidth, normalizeY)} className="ctp-chart__threshold-path ctp-chart__threshold-path--caution" />
            )}
            {isFiniteSeries(warningSeries) && (
              <path d={linePathFromSeries(warningSeries, chartWidth, normalizeY)} className="ctp-chart__threshold-path ctp-chart__threshold-path--warning" />
            )}
            {isFiniteSeries(criticalSeries) && (
              <path d={linePathFromSeries(criticalSeries, chartWidth, normalizeY)} className="ctp-chart__threshold-path ctp-chart__threshold-path--critical" />
            )}

            {/* 하한선 */}
            {showRange && isFiniteSeries(cautionLowerSeries) && (
              <path d={linePathFromSeries(cautionLowerSeries, chartWidth, normalizeY)} className="ctp-chart__threshold-path ctp-chart__threshold-path--caution" style={{ opacity: 0.55 }} />
            )}
            {showRange && isFiniteSeries(warningLowerSeries) && (
              <path d={linePathFromSeries(warningLowerSeries, chartWidth, normalizeY)} className="ctp-chart__threshold-path ctp-chart__threshold-path--warning" style={{ opacity: 0.55 }} />
            )}
            {showRange && isFiniteSeries(criticalLowerSeries) && (
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
            <span key={index}>{`t${index + 1}`}</span>
          ))}
        </div>
      </div>
    </Panel>
  );
}

export default memo(CtpVisualizationPanel);
