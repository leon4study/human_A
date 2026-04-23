interface ValveSVGProps {
  isOpen: boolean;
  size?: number;
}

export function ValveSVG({ isOpen, size = 30 }: ValveSVGProps) {
  // 밸브 잠김 상태는 빨강으로 통일
  const color = isOpen ? '#3b82f6' : '#ef4444';

  return (
    <svg width={size} height={size} viewBox="0 0 30 30" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id="valveBodyGradient">
          <stop offset="0%" stopColor="#475569" />
          <stop offset="50%" stopColor="#334155" />
          <stop offset="100%" stopColor="#0f172a" />
        </radialGradient>
      </defs>

      {/* 밸브 외부 링 */}
      <circle cx="15" cy="15" r="13.5" fill="url(#metalRingGradient)" stroke="#64748b" strokeWidth="2" />

      {/* 밸브 본체 */}
      <circle cx="15" cy="15" r="11" fill="url(#valveBodyGradient)" stroke="#64748b" strokeWidth="1.5" />

      {/* 내부 하우징 */}
      <circle cx="15" cy="15" r="9" fill="#0f172a" stroke="#475569" strokeWidth="1" />

      {/* 상태 표시 */}
      {isOpen ? (
        <g>
          <circle cx="15" cy="15" r="6" fill={color} opacity="0.3" />
          <circle cx="15" cy="15" r="5" fill={color} opacity="0.7" />
          {/* 흐름 화살표 — 정적 */}
          <path
            d="M 15 12 L 15 18 M 12 15 L 15 18 L 18 15"
            stroke="white"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity="0.9"
          />
        </g>
      ) : (
        <g>
          <rect x="12" y="10" width="6" height="10" rx="1" fill={color} opacity="0.9" stroke="#7f1d1d" strokeWidth="0.7" />
          <rect x="13" y="11" width="4" height="8" fill="#1e293b" />
          <path d="M 12 12 L 18 18 M 18 12 L 12 18" stroke="#ef4444" strokeWidth="1.5" strokeLinecap="round" opacity="0.6" />
        </g>
      )}

      {/* 핸들 샤프트 */}
      <rect x="13" y="2" width="4" height="9" rx="1" fill="url(#metalRingGradient)" stroke="#64748b" strokeWidth="1" />
      <rect x="13.5" y="3" width="1" height="7" fill="white" opacity="0.3" />

      {/* 핸들 */}
      <ellipse cx="15" cy="3" rx="4" ry="2.5" fill="#94a3b8" stroke="#64748b" strokeWidth="1" />
      <ellipse cx="15" cy="2.5" rx="3.5" ry="2" fill="#cbd5e1" />
      <ellipse cx="14" cy="2" rx="1.5" ry="0.8" fill="white" opacity="0.6" />

      {/* 상태 표시등 — 정적 */}
      <circle cx="23" cy="8" r="2.5" fill="#0f172a" stroke="#64748b" strokeWidth="1" />
      <circle cx="23" cy="8" r="1.8" fill={isOpen ? '#22c55e' : '#ef4444'} stroke="#475569" strokeWidth="0.3" />
      {isOpen && <circle cx="23" cy="8" r="1" fill="white" opacity="0.6" />}

      {/* 배관 연결 플랜지 */}
      <rect x="1" y="12" width="5" height="6" rx="1" fill="#334155" stroke="#64748b" strokeWidth="0.8" />
      <circle cx="3" cy="15" r="0.8" fill="#94a3b8" />
      <rect x="24" y="12" width="5" height="6" rx="1" fill="#334155" stroke="#64748b" strokeWidth="0.8" />
      <circle cx="27" cy="15" r="0.8" fill="#94a3b8" />

      {/* 볼트 디테일 */}
      {[[7, 7], [23, 7], [7, 23], [23, 23]].map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r="1" fill="#94a3b8" stroke="#64748b" strokeWidth="0.5" />
      ))}
    </svg>
  );
}
