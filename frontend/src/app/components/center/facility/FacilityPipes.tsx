import { pipePalette } from './facilityData';
import type { PipeTone } from './facilityTypes';

// 배관 선을 그리는 컴포넌트
export function PipeRun({
  d,   // SVG 경로 문자열
  tone,   // 배관 종류
  width = 0.8,   // 본체 두께
  flowWidth = 0.3,   // 안쪽 흐름 두께
  duration = '1.8s',   // 애니메이션 속도
  reverseFlow = false,   // 흐름 방향 반전 여부
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
      {/* 배관 바깥 테두리 */}
      <path d={d} fill="none" stroke={palette.shell} strokeWidth={width + 0.3} strokeLinecap="round" strokeLinejoin="round" />

      {/* 배관 본체 */}
      <path d={d} fill="none" stroke={palette.body} strokeWidth={width} strokeLinecap="round" strokeLinejoin="round" />

      {/* 안쪽 흐름 애니메이션 */}
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
          to={reverseFlow ? '28' : '-28'}
          dur={duration}
          repeatCount="indefinite"
        />
      </path>

      {/* 약한 빛 번짐 */}
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

// 배관 연결점(조인트)을 그리는 컴포넌트
export function PipeJoint({
  x,   // x 좌표
  y,   // y 좌표
  tone = 'steel',   // 기본 배관 종류
  size = 0.12,   // 조인트 크기
}: {
  x: number;
  y: number;
  tone?: PipeTone;
  size?: number;
}) {
  const palette = pipePalette[tone];

  return (
    <g>
      {/* 바깥 원 */}
      <circle cx={x} cy={y} r={size + 0.08} fill={palette.shell} />

      {/* 본체 원 */}
      <circle cx={x} cy={y} r={size} fill={palette.body} stroke="#94a3b8" strokeWidth="0.1" />

      {/* 하이라이트 */}
      <circle cx={x - 0.08} cy={y - 0.08} r={size * 0.35} fill={palette.glow} opacity="0.45" />
    </g>
  );
}