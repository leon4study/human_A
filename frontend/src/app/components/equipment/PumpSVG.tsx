interface PumpSVGProps {
  isActive: boolean;
  width?: number;
  height?: number;
}

export function PumpSVG({
  isActive,
  width = 80,
  height = 80,
}: PumpSVGProps) {
  const color = isActive ? "#22c55e" : "#6b7280";

  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 80 80"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        {/* 금속 본체 그라데이션 */}
        <linearGradient
          id="pumpBodyGradient"
          x1="0%"
          y1="0%"
          x2="100%"
          y2="100%"
        >
          <stop offset="0%" stopColor="#0f172a" />
          <stop offset="30%" stopColor="#334155" />
          <stop offset="70%" stopColor="#475569" />
          <stop offset="100%" stopColor="#1e293b" />
        </linearGradient>

        {/* 원형 하우징 그라데이션 */}
        <radialGradient id="housingGradient">
          <stop offset="0%" stopColor="#475569" />
          <stop offset="50%" stopColor="#334155" />
          <stop offset="100%" stopColor="#0f172a" />
        </radialGradient>

        {/* 활성화 상태 글로우 */}
        <filter id="activeGlow">
          <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
          <feMerge>
            <feMergeNode in="coloredBlur"/>
            <feMergeNode in="SourceGraphic"/>
          </feMerge>
        </filter>

        {/* 그림자 */}
        <filter id="pumpShadow">
          <feDropShadow dx="2" dy="3" stdDeviation="3" floodOpacity="0.5"/>
        </filter>
      </defs>

      {/* 펌프 그림자 */}
      <ellipse cx="42" cy="73" rx="32" ry="5" fill="black" opacity="0.3"/>

      {/* 펌프 베이스 - 3D 효과 */}
      <rect
        x="8"
        y="45"
        width="64"
        height="28"
        rx="4"
        fill="url(#pumpBodyGradient)"
        stroke="#64748b"
        strokeWidth="2"
        filter="url(#pumpShadow)"
      />

      {/* 베이스 상단 하이라이트 */}
      <rect
        x="10"
        y="46"
        width="60"
        height="3"
        rx="2"
        fill="white"
        opacity="0.15"
      />

      {/* 베이스 리벳 */}
      {[15, 30, 50, 65].map((x) => (
        <circle key={x} cx={x} cy="70" r="2" fill="#94a3b8" stroke="#64748b" strokeWidth="0.5"/>
      ))}

      {/* 펌프 본체 외부 링 */}
      <circle
        cx="40"
        cy="35"
        r="25"
        fill="url(#housingGradient)"
        stroke="#64748b"
        strokeWidth="2.5"
      />

      {/* 본체 하이라이트 */}
      <circle
        cx="40"
        cy="35"
        r="24"
        fill="none"
        stroke="white"
        strokeWidth="1"
        opacity="0.1"
      />

      {/* 임펠러 하우징 */}
      <circle
        cx="40"
        cy="35"
        r="20"
        fill="#0f172a"
        stroke="#475569"
        strokeWidth="2"
      />

      {/* 하우징 내부 링 */}
      <circle
        cx="40"
        cy="35"
        r="18"
        fill="none"
        stroke="#334155"
        strokeWidth="1"
      />

      {/* 임펠러 블레이드 */}
      {isActive && (
        <g filter="url(#activeGlow)">
          <animateTransform
            attributeName="transform"
            attributeType="XML"
            type="rotate"
            from="0 40 35"
            to="360 40 35"
            dur="1.5s"
            repeatCount="indefinite"
          />
          {[0, 60, 120, 180, 240, 300].map((angle) => {
            const rad = (angle * Math.PI) / 180;
            const x1 = 40 + 3 * Math.cos(rad);
            const y1 = 35 + 3 * Math.sin(rad);
            const x2 = 40 + 14 * Math.cos(rad);
            const y2 = 35 + 14 * Math.sin(rad);
            const cx = 40 + 10 * Math.cos(rad);
            const cy = 35 + 10 * Math.sin(rad);

            return (
              <g key={angle}>
                <path
                  d={`M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`}
                  stroke={color}
                  strokeWidth="4"
                  strokeLinecap="round"
                  fill="none"
                />
                <path
                  d={`M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`}
                  stroke="white"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  fill="none"
                  opacity="0.4"
                />
              </g>
            );
          })}
        </g>
      )}

      {!isActive && (
        <g>
          {[0, 60, 120, 180, 240, 300].map((angle) => {
            const rad = (angle * Math.PI) / 180;
            const x1 = 40 + 3 * Math.cos(rad);
            const y1 = 35 + 3 * Math.sin(rad);
            const x2 = 40 + 14 * Math.cos(rad);
            const y2 = 35 + 14 * Math.sin(rad);
            const cx = 40 + 10 * Math.cos(rad);
            const cy = 35 + 10 * Math.sin(rad);

            return (
              <path
                key={angle}
                d={`M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`}
                stroke={color}
                strokeWidth="4"
                strokeLinecap="round"
                fill="none"
                opacity="0.6"
              />
            );
          })}
        </g>
      )}

      {/* 중심축 */}
      <circle
        cx="40"
        cy="35"
        r="6"
        fill="#334155"
        stroke="#64748b"
        strokeWidth="1.5"
      />
      <circle
        cx="40"
        cy="35"
        r="4"
        fill="#475569"
      />
      <circle
        cx="38"
        cy="33"
        r="1.5"
        fill="white"
        opacity="0.4"
      />

      {/* 입구 파이프 - 3D */}
      <g>
        <rect
          x="2"
          y="28"
          width="18"
          height="10"
          rx="1"
          fill="#1e293b"
          stroke="#64748b"
          strokeWidth="1.5"
        />
        <rect
          x="3"
          y="29"
          width="16"
          height="8"
          fill="#334155"
        />
        <rect
          x="4"
          y="30"
          width="2"
          height="6"
          fill="white"
          opacity="0.2"
        />
        <circle
          cx="2"
          cy="33"
          r="5"
          fill="#334155"
          stroke="#64748b"
          strokeWidth="1.5"
        />
      </g>

      {/* 출구 파이프 - 3D */}
      <g>
        <rect
          x="60"
          y="28"
          width="18"
          height="10"
          rx="1"
          fill="#1e293b"
          stroke="#64748b"
          strokeWidth="1.5"
        />
        <rect
          x="61"
          y="29"
          width="16"
          height="8"
          fill="#334155"
        />
        <rect
          x="62"
          y="30"
          width="2"
          height="6"
          fill="white"
          opacity="0.2"
        />
        <circle
          cx="78"
          cy="33"
          r="5"
          fill="#334155"
          stroke="#64748b"
          strokeWidth="1.5"
        />
      </g>

      {/* 모터 연결부 */}
      <rect
        x="35"
        y="8"
        width="10"
        height="12"
        rx="2"
        fill="#334155"
        stroke="#64748b"
        strokeWidth="1.5"
      />

      {/* 냉각 핀 */}
      {[13, 16].map((y) => (
        <rect
          key={y}
          x="32"
          y={y}
          width="16"
          height="1.5"
          fill="#475569"
          stroke="#64748b"
          strokeWidth="0.5"
        />
      ))}

      {/* 상태 표시등 */}
      <g>
        <circle
          cx="68"
          cy="52"
          r="5"
          fill="#0f172a"
          stroke="#64748b"
          strokeWidth="1.5"
        />
        <circle
          cx="68"
          cy="52"
          r="3.5"
          fill={isActive ? color : "#374151"}
          stroke="#64748b"
          strokeWidth="0.5"
        >
          {isActive && (
            <animate
              attributeName="opacity"
              values="1;0.4;1"
              dur="1.2s"
              repeatCount="indefinite"
            />
          )}
        </circle>
        {isActive && (
          <circle
            cx="68"
            cy="52"
            r="2"
            fill="white"
            opacity="0.6"
          />
        )}
      </g>

      {/* 명판 */}
      <rect
        x="25"
        y="50"
        width="30"
        height="8"
        rx="1"
        fill="#1e293b"
        stroke="#64748b"
        strokeWidth="0.5"
        opacity="0.7"
      />

      {/* 볼트 디테일 */}
      {[[25, 20], [55, 20], [25, 50], [55, 50]].map(([x, y], i) => (
        <circle
          key={i}
          cx={x}
          cy={y}
          r="2"
          fill="#94a3b8"
          stroke="#64748b"
          strokeWidth="0.5"
        />
      ))}
    </svg>
  );
}
