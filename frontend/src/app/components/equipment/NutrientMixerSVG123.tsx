interface NutrientMixerSVGProps {
  width?: number;
  height?: number;
}

// 양액 자동공급기(혼합기) 신규 디자인
//  - 상단 헤더 + LED 인디케이터
//  - 중앙 믹싱 챔버 (회전 블레이드)
//  - 하단 EC/pH 게이지
//  - 우측 측면에 5개 입력 포트 (각 탱크 피드 파이프가 꽂히는 자리)
//  - 하단 중앙 출력 포트 (재배 구역 메인 라인 연결)
export function NutrientMixerSVG({
  width = 130,
  height = 160,
}: NutrientMixerSVGProps) {
  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 130 160"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <linearGradient id="nutMixerBody" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#0f172a" />
          <stop offset="20%" stopColor="#334155" />
          <stop offset="50%" stopColor="#475569" />
          <stop offset="80%" stopColor="#334155" />
          <stop offset="100%" stopColor="#0f172a" />
        </linearGradient>

        <linearGradient id="nutMixerHeader" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#1e293b" />
          <stop offset="100%" stopColor="#0f172a" />
        </linearGradient>

        <radialGradient id="rotorGlow">
          <stop offset="0%" stopColor="#fbbf24" stopOpacity="0.55" />
          <stop offset="60%" stopColor="#fb923c" stopOpacity="0.25" />
          <stop offset="100%" stopColor="#fb923c" stopOpacity="0" />
        </radialGradient>

        <filter id="nutMixerShadow">
          <feDropShadow dx="2" dy="3" stdDeviation="3" floodOpacity="0.5" />
        </filter>
      </defs>

      {/* 바닥 그림자 */}
      <ellipse cx="65" cy="152" rx="48" ry="4" fill="black" opacity="0.3" />

      {/* 본체 */}
      <rect
        x="14"
        y="20"
        width="100"
        height="120"
        rx="6"
        fill="url(#nutMixerBody)"
        stroke="#94a3b8"
        strokeWidth="1.4"
        filter="url(#nutMixerShadow)"
      />

      {/* 상단 헤더 */}
      <rect
        x="14"
        y="20"
        width="100"
        height="18"
        rx="6"
        fill="url(#nutMixerHeader)"
      />
      <rect x="14" y="32" width="100" height="6" fill="#0f172a" />
      <text
        x="64"
        y="32"
        textAnchor="middle"
        fill="#e2e8f0"
        fontSize="9"
        fontWeight="700"
        letterSpacing="1"
      >
        NUTRIENT MIXER
      </text>

      {/* LED 인디케이터 */}
      <circle cx="22" cy="29" r="1.8" fill="#4ade80" />
      <circle cx="22" cy="29" r="1.8" fill="#4ade80" opacity="0.5">
        <animate
          attributeName="r"
          values="1.8;2.6;1.8"
          dur="1.6s"
          repeatCount="indefinite"
        />
        <animate
          attributeName="opacity"
          values="0.5;0;0.5"
          dur="1.6s"
          repeatCount="indefinite"
        />
      </circle>
      <circle cx="106" cy="29" r="1.8" fill="#fbbf24" />

      {/* 중앙 믹싱 챔버 */}
      <circle cx="64" cy="78" r="26" fill="#0f172a" stroke="#475569" strokeWidth="1.4" />
      <circle cx="64" cy="78" r="24" fill="url(#rotorGlow)" />

      {/* 회전 블레이드 (SMIL 애니메이션) */}
      <g transform="translate(64 78)">
        <g>
          <rect x="-16" y="-1.8" width="32" height="3.6" rx="1.8" fill="#fbbf24" />
          <rect x="-1.8" y="-16" width="3.6" height="32" rx="1.8" fill="#fbbf24" />
          <animateTransform
            attributeName="transform"
            type="rotate"
            from="0"
            to="360"
            dur="4s"
            repeatCount="indefinite"
          />
        </g>
        {/* 중앙 허브 */}
        <circle cx="0" cy="0" r="3.5" fill="#fef3c7" />
        <circle cx="0" cy="0" r="2" fill="#fbbf24" />
      </g>

      {/* 하단 게이지 영역 - EC */}
      <rect
        x="22"
        y="114"
        width="38"
        height="14"
        rx="1.5"
        fill="#0f172a"
        stroke="#475569"
        strokeWidth="0.6"
      />
      <text x="25" y="121" fill="#94a3b8" fontSize="5" fontWeight="700">
        EC
      </text>
      <rect x="25" y="123" width="32" height="3" rx="1" fill="#1e293b" />
      <rect x="25" y="123" width="22" height="3" rx="1" fill="#4ade80" />

      {/* 하단 게이지 영역 - pH */}
      <rect
        x="68"
        y="114"
        width="38"
        height="14"
        rx="1.5"
        fill="#0f172a"
        stroke="#475569"
        strokeWidth="0.6"
      />
      <text x="71" y="121" fill="#94a3b8" fontSize="5" fontWeight="700">
        pH
      </text>
      <rect x="71" y="123" width="32" height="3" rx="1" fill="#1e293b" />
      <rect x="71" y="123" width="18" height="3" rx="1" fill="#60a5fa" />

      {/* 우측 입력 포트 5개 */}
      {[0, 1, 2, 3, 4].map((i) => {
        const y = 50 + i * 12;
        return (
          <g key={`in-port-${i}`}>
            {/* 포트 플랜지 */}
            <rect
              x="110"
              y={y - 3.2}
              width="9"
              height="6.4"
              rx="0.6"
              fill="#334155"
              stroke="#94a3b8"
              strokeWidth="0.4"
            />
            {/* 포트 내부 */}
            <circle cx="117" cy={y} r="2" fill="#020617" />
            <circle
              cx="117"
              cy={y}
              r="2"
              fill="none"
              stroke="#64748b"
              strokeWidth="0.5"
            />
            {/* 포트 번호 */}
            <text
              x="100"
              y={y + 1.5}
              textAnchor="middle"
              fill="#94a3b8"
              fontSize="4"
              fontWeight="700"
            >
              P{i + 1}
            </text>
          </g>
        );
      })}

      {/* 좌측 고정 볼트 디테일 */}
      {[26, 46, 66, 86, 106].map((x) => (
        <circle
          key={`bolt-top-${x}`}
          cx={x}
          cy="23.5"
          r="0.9"
          fill="#94a3b8"
          stroke="#1e293b"
          strokeWidth="0.2"
        />
      ))}

      {/* 하단 출력 포트 */}
      <rect
        x="56"
        y="138"
        width="16"
        height="4"
        rx="0.8"
        fill="#334155"
        stroke="#94a3b8"
        strokeWidth="0.5"
      />
      <rect
        x="60"
        y="142"
        width="8"
        height="8"
        fill="#475569"
        stroke="#94a3b8"
        strokeWidth="0.5"
      />
      <circle cx="64" cy="146" r="2.2" fill="#fb923c" />
      <circle cx="64" cy="146" r="2.2" fill="#fb923c" opacity="0.5">
        <animate
          attributeName="r"
          values="2.2;3;2.2"
          dur="1.8s"
          repeatCount="indefinite"
        />
        <animate
          attributeName="opacity"
          values="0.5;0;0.5"
          dur="1.8s"
          repeatCount="indefinite"
        />
      </circle>
    </svg>
  );
}
