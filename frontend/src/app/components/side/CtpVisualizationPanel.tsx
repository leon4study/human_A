import Panel from "../common/Panel";
import type { CtpMetric } from "../../types/dashboard";

// CTP 시각화 패널의 props 인터페이스
interface CtpVisualizationPanelProps {
  selectedMetric: CtpMetric | null;
}

// 그래프 좌표 타입
interface ChartPoint {
  x: number;
  y: number;
  value: number;
}

// critical을 넘는 구간 정보를 담는 인터페이스
interface CriticalSegment {
  polygonPoints: string;
  linePath: string;
}

// CTP 시각화 패널 컴포넌트
function CtpVisualizationPanel({
  selectedMetric,
}: CtpVisualizationPanelProps) {
  const chartWidth = 100;
  const chartHeight = 180;

  if (!selectedMetric) {
    return (
      <Panel title="CTP 시각화">
        {/* 컨테이너 공간 유지용 */}
        <div className="ctp-visualization ctp-visualization--empty">
          <div className="ctp-visualization__placeholder"></div>
        </div>
      </Panel>
    );
  }

  // 그래프 데이터 값 
  const values = selectedMetric.trend;

  // 그래프 Y축 최소값 계산 (critical 기준으로 여유 있게)
  const minValue =
    Math.min(
      ...values,
      selectedMetric.w1,
      selectedMetric.w2,
      selectedMetric.critical
    ) * 0.9;

  // 그래프 Y축 최대값 계산 (critical 기준으로 여유 있게)
  const maxValue =
    Math.max(
      ...values,
      selectedMetric.w1,
      selectedMetric.w2,
      selectedMetric.critical
    ) * 1.1;

  // x축 좌표 변환 함수 (index를 0~chartWidth 범위로 변환)
  const normalizeX = (index: number) => {
    if (values.length === 1) {
      return 0;
    }
    return (index / (values.length - 1)) * chartWidth;
  };

  // y축 좌표 변환 함수 (값을 min-max 범위에 맞춰 0~chartHeight 범위로 변환)
  const normalizeY = (value: number) => {
    return chartHeight - ((value - minValue) / (maxValue - minValue)) * chartHeight;
  };

  // 실제 좌표 배열 생성
  const points: ChartPoint[] = values.map((value, index) => ({
    x: normalizeX(index),
    y: normalizeY(value),
    value,
  }));

  // 전체 선 path 생성 (critical 초과 여부와 관계없이 전체 라인)
  const linePath = points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`)
    .join(" ");

  const w1Y = normalizeY(selectedMetric.w1);
  const w2Y = normalizeY(selectedMetric.w2);
  const criticalY = normalizeY(selectedMetric.critical);

  // critical 초과 여부 판단 함수
  const isCriticalExceeded = (value: number) => {
    if (selectedMetric.direction === "high") {
      return value > selectedMetric.critical;
    }
    return value < selectedMetric.critical;
  };

  // critical 선과 교차하는 지점 계산 함수
  const getCrossPoint = (start: ChartPoint, end: ChartPoint) => {
    const valueGap = end.value - start.value;

    if (valueGap === 0) {
      return {
        x: start.x,
        y: criticalY,
      };
    }

    const ratio = (selectedMetric.critical - start.value) / valueGap;

    return {
      x: start.x + (end.x - start.x) * ratio,
      y: criticalY,
    };
  };

  // critical 구간 저장 배열 (low면 위쪽(0)부터 채움, high면 아래쪽(chartHeight)부터 채움)
  const fillBaseY = selectedMetric.direction === "low" ? 0 : chartHeight;

  const criticalSegments: CriticalSegment[] = [];

  for (let i = 0; i < points.length - 1; i += 1) {
    const start = points[i];
    const end = points[i + 1];

    const startExceeded = isCriticalExceeded(start.value);
    const endExceeded = isCriticalExceeded(end.value);

    if (!startExceeded && !endExceeded) {
      continue;
    }

    // 둘 다 critical 초과/미만인 구간
    if (startExceeded && endExceeded) {
      criticalSegments.push({
        polygonPoints: `${start.x},${fillBaseY} ${start.x},${start.y} ${end.x},${end.y} ${end.x},${fillBaseY}`,
        linePath: `M ${start.x} ${start.y} L ${end.x} ${end.y}`,
      });
      continue;
    }

    // 시작점만 critical 초과/미만
    if (startExceeded && !endExceeded) {
      const cross = getCrossPoint(start, end);

      criticalSegments.push({
        polygonPoints: `${start.x},${fillBaseY} ${start.x},${start.y} ${cross.x},${criticalY} ${cross.x},${fillBaseY}`,
        linePath: `M ${start.x} ${start.y} L ${cross.x} ${criticalY}`,
      });
      continue;
    }

    // 끝점만 critical 초과/미만
    if (!startExceeded && endExceeded) {
      const cross = getCrossPoint(start, end);

      criticalSegments.push({
        polygonPoints: `${cross.x},${fillBaseY} ${cross.x},${criticalY} ${end.x},${end.y} ${end.x},${fillBaseY}`,
        linePath: `M ${cross.x} ${criticalY} L ${end.x} ${end.y}`,
      });
    }
  }

  const patternId = `ctp-critical-pattern-${selectedMetric.id}`;

  return (
    <Panel title="CTP 시각화">
      <div className="ctp-visualization">
        <div className="ctp-visualization__head">
          <div className="ctp-visualization__title">{selectedMetric.label}</div>
          {/* <div className="ctp-visualization__value">
            현재값:{" "}
            <strong>
              {selectedMetric.value} {selectedMetric.unit}
            </strong>
          </div> */}
        </div>

        <div className="ctp-chart">
          <div
            className="ctp-chart__line-label ctp-chart__line-label--w1"
            style={{ top: `${w1Y - 10}px` }}
          >
            W1
          </div>

          <div
            className="ctp-chart__line-label ctp-chart__line-label--w2"
            style={{ top: `${w2Y - 10}px` }}
          >
            W2
          </div>

          <div
            className="ctp-chart__line-label ctp-chart__line-label--critical"
            style={{ top: `${criticalY - 10}px` }}
          >
            Critical
          </div>

          <div
            className="ctp-chart__threshold ctp-chart__threshold--w1"
            style={{ top: `${w1Y}px` }}
          />
          <div
            className="ctp-chart__threshold ctp-chart__threshold--w2"
            style={{ top: `${w2Y}px` }}
          />
          <div
            className="ctp-chart__threshold ctp-chart__threshold--critical"
            style={{ top: `${criticalY}px` }}
          />

          <svg
            className="ctp-chart__svg"
            viewBox={`0 0 ${chartWidth} ${chartHeight}`}
            preserveAspectRatio="none"
          >
            <defs>
              <pattern
                id={patternId}
                width="6"
                height="6"
                patternUnits="userSpaceOnUse"
                patternTransform="rotate(25)"
              >
                <line
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="6"
                  className="ctp-chart__critical-pattern-line"
                />
              </pattern>
            </defs>

            {/* 전체 기본 라인 */}
            <path d={linePath} className="ctp-chart__path" />

            {/* critical 초과/미만 영역 */}
            {criticalSegments.map((segment, index) => (
              <g key={`${selectedMetric.id}-critical-${index}`}>
                <polygon
                  points={segment.polygonPoints}
                  className="ctp-chart__critical-fill"
                />
                <polygon
                  points={segment.polygonPoints}
                  fill={`url(#${patternId})`}
                />
                <path
                  d={segment.linePath}
                  className="ctp-chart__path ctp-chart__path--critical"
                />
              </g>
            ))}
          </svg>
        </div>

        <div
          className="ctp-chart__xlabels"
          style={{
            gridTemplateColumns: `repeat(${values.length}, 1fr)`,
          }}
        >
          {values.map((_, index) => (
            <span key={index}>T{index + 1}</span>
          ))}
        </div>
      </div>
    </Panel>
  );
}

export default CtpVisualizationPanel;