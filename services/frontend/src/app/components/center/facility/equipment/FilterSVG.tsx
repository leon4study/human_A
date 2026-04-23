interface FilterSVGProps {
  width?: number;
  height?: number;
}

export function FilterSVG({ width = 70, height = 90 }: FilterSVGProps) {
  return (
    <svg width={width} height={height} viewBox="0 0 70 90" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        {/* 금속 본체 그라데이션 */}
        <linearGradient id="filterBodyGradient" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#0f172a" />
          <stop offset="25%" stopColor="#334155" />
          <stop offset="50%" stopColor="#475569" />
          <stop offset="75%" stopColor="#334155" />
          <stop offset="100%" stopColor="#0f172a" />
        </linearGradient>
        
        {/* 필터 메쉬 패턴 - 육각형 */}
        <pattern id="filterMesh" x="0" y="0" width="6" height="6" patternUnits="userSpaceOnUse">
          <path d="M 3,0 L 6,1.5 L 6,4.5 L 3,6 L 0,4.5 L 0,1.5 Z" fill="none" stroke="#64748b" strokeWidth="0.5" opacity="0.4"/>
          <circle cx="3" cy="3" r="0.5" fill="#3b82f6" opacity="0.3"/>
        </pattern>
        
        {/* 압력 게이지 그라데이션 */}
        <radialGradient id="gaugeGradient">
          <stop offset="0%" stopColor="#1e3a8a" />
          <stop offset="70%" stopColor="#0f172a" />
          <stop offset="100%" stopColor="#000000" />
        </radialGradient>
        
        {/* 그림자 */}
        <filter id="filterShadow">
          <feDropShadow dx="1" dy="2" stdDeviation="2" floodOpacity="0.4"/>
        </filter>
      </defs>
      
      {/* 필터 그림자 */}
      <ellipse cx="35" cy="85" rx="27" ry="4" fill="black" opacity="0.3"/>
      
      {/* 필터 상단 캡 - 3D 효과 */}
      <ellipse cx="35" cy="15" rx="26" ry="7" fill="#0f172a" stroke="#475569" strokeWidth="1"/>
      <ellipse cx="35" cy="15" rx="25" ry="6" fill="#334155" stroke="#64748b" strokeWidth="1.5"/>
      <ellipse cx="35" cy="15" rx="25" ry="5" fill="url(#filterBodyGradient)" opacity="0.8"/>
      
      {/* 필터 본체 */}
      <rect x="10" y="15" width="50" height="60" rx="6" fill="url(#filterBodyGradient)" stroke="#64748b" strokeWidth="2" filter="url(#filterShadow)"/>
      
      {/* 본체 내부 어두운 영역 */}
      <rect x="12" y="17" width="46" height="56" rx="5" fill="#0f172a" opacity="0.5"/>
      
      {/* 필터 카트리지 */}
      <rect x="15" y="22" width="40" height="48" rx="4" fill="#1e293b" stroke="#475569" strokeWidth="1.5"/>
      
      {/* 필터 메쉬 영역 */}
      <rect x="17" y="25" width="36" height="42" rx="3" fill="url(#filterMesh)" stroke="#475569" strokeWidth="1"/>
      
      {/* 메쉬 프레임 */}
      <rect x="17" y="25" width="36" height="6" fill="#334155" opacity="0.7"/>
      <rect x="17" y="61" width="36" height="6" fill="#334155" opacity="0.7"/>
      
      {/* 입구 파이프 */}
      <g>
        <rect x="-5" y="33" width="20" height="8" fill="#1e293b" stroke="#64748b" strokeWidth="1.5"/>
        <rect x="-4" y="34" width="18" height="6" fill="#334155"/>
        <circle cx="-5" cy="37" r="4" fill="#334155" stroke="#64748b" strokeWidth="1.5"/>
        <circle cx="-5" cy="37" r="2.5" fill="#0f172a"/>
        {/* 파이프 하이라이트 */}
        <rect x="-3" y="34" width="2" height="6" fill="white" opacity="0.2"/>
      </g>
      
      {/* 출구 파이프 */}
      <g>
        <rect x="55" y="33" width="20" height="8" fill="#1e293b" stroke="#64748b" strokeWidth="1.5"/>
        <rect x="56" y="34" width="18" height="6" fill="#334155"/>
        <circle cx="75" cy="37" r="4" fill="#334155" stroke="#64748b" strokeWidth="1.5"/>
        <circle cx="75" cy="37" r="2.5" fill="#0f172a"/>
        {/* 파이프 하이라이트 */}
        <rect x="56" y="34" width="2" height="6" fill="white" opacity="0.2"/>
      </g>
      
      {/* 필터 하단 캡 - 3D 효과 */}
      <ellipse cx="35" cy="75" rx="26" ry="7" fill="#0f172a" stroke="#475569" strokeWidth="1"/>
      <ellipse cx="35" cy="75" rx="25" ry="6" fill="#1e293b" stroke="#64748b" strokeWidth="1.5"/>
      
      {/* 드레인 밸브 */}
      <g>
        <rect x="31" y="75" width="8" height="12" rx="1" fill="#475569" stroke="#64748b" strokeWidth="1"/>
        <rect x="32" y="76" width="6" height="10" fill="#334155"/>
        <circle cx="35" cy="89" r="5" fill="#334155" stroke="#64748b" strokeWidth="1.5"/>
        <circle cx="35" cy="89" r="3.5" fill="#94a3b8"/>
        <line x1="33" y1="89" x2="37" y2="89" stroke="#64748b" strokeWidth="1.5" strokeLinecap="round"/>
      </g>
      
      {/* 압력 게이지 */}
      <g>
        <circle cx="55" cy="20" r="9" fill="url(#gaugeGradient)" stroke="#64748b" strokeWidth="2"/>
        <circle cx="55" cy="20" r="7.5" fill="#0f172a" stroke="#475569" strokeWidth="1"/>
        
        {/* 게이지 눈금 */}
        {[0, 45, 90, 135, 180].map((angle) => {
          const rad = ((angle - 90) * Math.PI) / 180;
          const x1 = 55 + 6 * Math.cos(rad);
          const y1 = 20 + 6 * Math.sin(rad);
          const x2 = 55 + 7 * Math.cos(rad);
          const y2 = 20 + 7 * Math.sin(rad);
          return (
            <line key={angle} x1={x1} y1={y1} x2={x2} y2={y2} stroke="#64748b" strokeWidth="0.5"/>
          );
        })}
        
        {/* 게이지 바늘 */}
        <line x1="55" y1="20" x2="59" y2="17" stroke="#3b82f6" strokeWidth="1.5" strokeLinecap="round">
          <animateTransform
            attributeName="transform"
            attributeType="XML"
            type="rotate"
            from="0 55 20"
            to="10 55 20"
            dur="3s"
            repeatCount="indefinite"
          />
        </line>
        
        {/* 게이지 중심점 */}
        <circle cx="55" cy="20" r="1.5" fill="#3b82f6"/>
      </g>
      
      {/* 측면 하이라이트 */}
      <rect x="12" y="20" width="4" height="50" fill="white" opacity="0.15"/>
      <rect x="54" y="20" width="4" height="50" fill="black" opacity="0.4"/>
      
      {/* 리벳 디테일 */}
      {[25, 45, 65].map((y) => (
        <g key={y}>
          <circle cx="10" cy={y} r="1.5" fill="#94a3b8" stroke="#475569" strokeWidth="0.5"/>
          <circle cx="60" cy={y} r="1.5" fill="#94a3b8" stroke="#475569" strokeWidth="0.5"/>
        </g>
      ))}
      
      {/* 상단 볼트 */}
      {[20, 30, 40, 50].map((x) => (
        <circle key={x} cx={x} cy="15" r="1.5" fill="#94a3b8" stroke="#64748b" strokeWidth="0.5"/>
      ))}
      
      {/* 경고 라벨 */}
      <rect x="22" y="70" width="26" height="4" rx="1" fill="#f59e0b" opacity="0.3" stroke="#f59e0b" strokeWidth="0.5"/>
    </svg>
  );
}
