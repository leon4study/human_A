import type { PipeTone } from "../model/facility.types";

// 배관 종류별 시각 스타일 팔레트
const pipePalette: Record<
  PipeTone,
  { shell: string; body: string; flow: string; glow: string }
> = {
  water: {
    shell: "#020617",
    body: "#1d4ed8",
    flow: "#60a5fa",
    glow: "#bfdbfe",
  },
  nutrient: {
    shell: "#1c1917",
    body: "#9a3412",
    flow: "#fb923c",
    glow: "#fed7aa",
  },
  steel: {
    shell: "#0f172a",
    body: "#475569",
    flow: "#cbd5e1",
    glow: "#e2e8f0",
  },
};

export function PipeRun({
  d,
  tone,
  width = 0.8,
  flowWidth = 0.3,
  duration = "1.8s",
  reverseFlow = false,
}: {
  d: string;
  tone: PipeTone;
  width?: number;
  flowWidth?: number;
  duration?: string;
  reverseFlow?: boolean;
}) {
  const palette = pipePalette[tone];

  return (
    <g>
      {/* 배관 외곽 */}
      <path
        d={d}
        fill="none"
        stroke={palette.shell}
        strokeWidth={width + 0.3}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* 배관 본체 */}
      <path
        d={d}
        fill="none"
        stroke={palette.body}
        strokeWidth={width}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* 흐름감을 주는 점선 애니메이션 */}
      <path
        d={d}
        fill="none"
        stroke={palette.flow}
        strokeWidth={flowWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeDasharray="10 18"
      >
        <animate
          attributeName="stroke-dashoffset"
          from="0"
          to={reverseFlow ? "28" : "-28"}
          dur={duration}
          repeatCount="indefinite"
        />
      </path>
      {/* 약한 글로우 오버레이 */}
      <path
        d={d}
        fill="none"
        stroke={palette.glow}
        strokeWidth="0.1"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.08"
      />
    </g>
  );
}

export function PipeJoint({
  x,
  y,
  tone = "steel",
  size = 0.12,
}: {
  x: number;
  y: number;
  tone?: PipeTone;
  size?: number;
}) {
  const palette = pipePalette[tone];

  return (
    <g>
      {/* 조인트 외곽 */}
      <circle cx={x} cy={y} r={size + 0.08} fill={palette.shell} />
      {/* 조인트 본체 */}
      <circle
        cx={x}
        cy={y}
        r={size}
        fill={palette.body}
        stroke="#94a3b8"
        strokeWidth="0.1"
      />
      {/* 조인트 하이라이트 */}
      <circle
        cx={x - 0.08}
        cy={y - 0.08}
        r={size * 0.35}
        fill={palette.glow}
        opacity="0.45"
      />
    </g>
  );
}
