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
  flowing = true,
  flowColor,
  bodyColor,
  shellColor,
}: {
  d: string;
  tone: PipeTone;
  width?: number;
  flowWidth?: number;
  duration?: string;
  reverseFlow?: boolean;
  /** false이면 흐름 점선과 애니메이션을 렌더하지 않음 (밸브 잠김 등) */
  flowing?: boolean;
  /** 흐름 점선 색을 override (탱크 액체 색상 등). 미지정 시 tone 기본값 사용. */
  flowColor?: string;
  /** 파이프 본체 색 override — 회색 톤으로 주면 내부 액체 흐름이 돋보임 */
  bodyColor?: string;
  /** 파이프 외곽(shell) 색 override */
  shellColor?: string;
}) {
  const palette = pipePalette[tone];
  const flowStroke = flowColor ?? palette.flow;
  const bodyStroke = bodyColor ?? palette.body;
  const shellStroke = shellColor ?? palette.shell;

  return (
    <g>
      {/* 배관 외곽 */}
      <path
        d={d}
        fill="none"
        stroke={shellStroke}
        strokeWidth={width + 0.3}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* 배관 본체 */}
      <path
        d={d}
        fill="none"
        stroke={bodyStroke}
        strokeWidth={width}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* 흐름감을 주는 점선 애니메이션 (flowing일 때만) */}
      {flowing && (
        <path
          d={d}
          fill="none"
          stroke={flowStroke}
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
      )}
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

// 파이프 라인에 박힌 타원형 밸브 (핸들 없이 심플하게)
//  - 열림: 초록 코어 + 느린 펄스
//  - 잠김: 빨간 코어 + 정적
export function SmallValve({
  x,
  y,
  isOpen = true,
  size = 0.8,
}: {
  x: number;
  y: number;
  isOpen?: boolean;
  size?: number;
}) {
  const coreFill = isOpen ? "#22c55e" : "#ef4444";
  const coreStroke = isOpen ? "#16a34a" : "#b91c1c";

  // 수직 파이프 위이므로 세로로 긴 타원이 자연스러움
  const rx = size * 0.85;
  const ry = size * 1.25;

  return (
    <g>
      {/* 외곽 섀도우 */}
      <ellipse
        cx={x}
        cy={y}
        rx={rx + 0.12}
        ry={ry + 0.12}
        fill="#020617"
      />
      {/* 메탈 바디 */}
      <ellipse
        cx={x}
        cy={y}
        rx={rx}
        ry={ry}
        fill="#334155"
        stroke="#94a3b8"
        strokeWidth="0.12"
      />
      {/* 상태 코어 */}
      <ellipse
        cx={x}
        cy={y}
        rx={rx * 0.55}
        ry={ry * 0.6}
        fill={coreFill}
        stroke={coreStroke}
        strokeWidth="0.1"
      />
      {/* 윗면 하이라이트 */}
      <ellipse
        cx={x - rx * 0.25}
        cy={y - ry * 0.4}
        rx={rx * 0.3}
        ry={ry * 0.22}
        fill="white"
        opacity="0.35"
      />
    </g>
  );
}
