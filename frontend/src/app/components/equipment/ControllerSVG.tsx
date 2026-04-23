interface ControllerSVGProps {
  width?: number;
  height?: number;
}

export function ControllerSVG({ width = 120, height = 150 }: ControllerSVGProps) {
  return (
    <svg width={width} height={height} viewBox="0 0 120 150" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        {/* 컨트롤러 본체 그라데이션 */}
        <linearGradient id="controllerBodyGradient" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#0f172a" />
          <stop offset="40%" stopColor="#1e293b" />
          <stop offset="60%" stopColor="#334155" />
          <stop offset="100%" stopColor="#0f172a" />
        </linearGradient>
        
        {/* 버튼 그라데이션 */}
        <radialGradient id="buttonGradient">
          <stop offset="0%" stopColor="#334155" />
          <stop offset="70%" stopColor="#1e293b" />
          <stop offset="100%" stopColor="#0f172a" />
        </radialGradient>
        
      </defs>
      
      {/* 컨트롤러 메인 박스 */}
      <rect 
        x="10" 
        y="10" 
        width="100" 
        height="130" 
        rx="8" 
        fill="url(#controllerBodyGradient)" 
        stroke="#64748b" 
        strokeWidth="2.5"
        filter="url(#controllerShadow)"
      />
      
      
      {/* 상단 스크린 베젤 */}
      <rect 
        x="18" 
        y="18" 
        width="84" 
        height="54" 
        rx="5" 
        fill="#0f172a" 
        stroke="#475569" 
        strokeWidth="2"
      />
      
      {/* 스크린 */}
      <rect 
        x="20" 
        y="20" 
        width="80" 
        height="50" 
        rx="4" 
        fill="url(#screenGradient)" 
        stroke="#1e40af" 
        strokeWidth="1"
      />
      
      {/* 스크린 내용 배경 그리드 */}
      <g opacity="0.2">
        {[0, 1, 2, 3, 4].map((i) => (
          <line 
            key={`h-${i}`}
            x1="22" 
            y1={22 + i * 11} 
            x2="98" 
            y2={22 + i * 11} 
            stroke="#3b82f6" 
            strokeWidth="0.3"
          />
        ))}
        {[0, 1, 2, 3, 4, 5, 6].map((i) => (
          <line 
            key={`v-${i}`}
            x1={22 + i * 11} 
            y1="22" 
            x2={22 + i * 11} 
            y2="68" 
            stroke="#3b82f6" 
            strokeWidth="0.3"
          />
        ))}
      </g>
      
      {/* 스크린 내용 - pH/EC 표시 */}
      <g fontFamily="monospace">
        <text x="28" y="36" fill="#3b82f6" fontSize="11" fontWeight="bold">pH</text>
        <text x="70" y="36" fill="#3b82f6" fontSize="12" fontWeight="bold">6.2</text>
        
        <text x="28" y="50" fill="#22c55e" fontSize="11" fontWeight="bold">EC</text>
        <text x="70" y="50" fill="#22c55e" fontSize="12" fontWeight="bold">1.5</text>
        
        <text x="28" y="64" fill="#f59e0b" fontSize="11" fontWeight="bold">TEMP</text>
        <text x="70" y="64" fill="#f59e0b" fontSize="12" fontWeight="bold">22°C</text>
      </g>
      
      
      
      {/* 제어 버튼 영역 배경 */}
      <rect 
        x="18" 
        y="76" 
        width="84" 
        height="30" 
        rx="4" 
        fill="#0f172a" 
        opacity="0.5"
      />
      
      {/* 제어 버튼들 */}
      <g>
        {/* pH 조절 버튼 */}
        <rect 
          x="24" 
          y="80" 
          width="35" 
          height="22" 
          rx="4" 
          fill="url(#buttonGradient)" 
          stroke="#3b82f6" 
          strokeWidth="2"
        />
        <rect 
          x="25" 
          y="81" 
          width="33" 
          height="3" 
          rx="1"
          fill="white" 
          opacity="0.2"
        />
        <text 
          x="41.5" 
          y="94" 
          fill="#3b82f6" 
          fontSize="10" 
          fontWeight="bold"
          textAnchor="middle"
        >
          pH
        </text>
        {/* 버튼 마크 */}
        <circle cx="28" cy="91" r="1.5" fill="#3b82f6" opacity="0.6"/>
        
        {/* EC 조절 버튼 */}
        <rect 
          x="63" 
          y="80" 
          width="35" 
          height="22" 
          rx="4" 
          fill="url(#buttonGradient)" 
          stroke="#22c55e" 
          strokeWidth="2"
        />
        <rect 
          x="64" 
          y="81" 
          width="33" 
          height="3" 
          rx="1"
          fill="white" 
          opacity="0.2"
        />
        <text 
          x="80.5" 
          y="94" 
          fill="#22c55e" 
          fontSize="10" 
          fontWeight="bold"
          textAnchor="middle"
        >
          EC
        </text>
        {/* 버튼 마크 */}
        <circle cx="67" cy="91" r="1.5" fill="#22c55e" opacity="0.6"/>
      </g>
      
      {/* 상태 LED 패널 */}
      <rect 
        x="18" 
        y="110" 
        width="84" 
        height="24" 
        rx="3" 
        fill="#0f172a" 
        stroke="#334155" 
        strokeWidth="1"
      />
      
      {/* 상태 LED */}
      <g filter="url(#ledGlow)">
        {/* 전원 LED */}
        <circle cx="30" cy="122" r="4.5" fill="#0f172a" stroke="#475569" strokeWidth="1"/>
        <circle cx="30" cy="122" r="3.5" fill="#22c55e">
          <animate 
            attributeName="opacity" 
            values="1;0.4;1" 
            dur="2s" 
            repeatCount="indefinite"
          />
        </circle>
        <circle cx="28.5" cy="120.5" r="1.5" fill="white" opacity="0.7"/>
        <text x="40" y="125" fill="#94a3b8" fontSize="9" fontWeight="bold">전원</text>
        
        {/* 운전 LED */}
        <circle cx="65" cy="122" r="4.5" fill="#0f172a" stroke="#475569" strokeWidth="1"/>
        <circle cx="65" cy="122" r="3.5" fill="#3b82f6">
          <animate 
            attributeName="opacity" 
            values="1;0.6;1" 
            dur="1.5s" 
            repeatCount="indefinite"
          />
        </circle>
        <circle cx="63.5" cy="120.5" r="1.5" fill="white" opacity="0.7"/>
        <text x="75" y="125" fill="#94a3b8" fontSize="9" fontWeight="bold">운전</text>
      </g>
      
      {/* 배관 연결구 */}
      <g>
        {/* 입구 */}
        <rect 
          x="0" 
          y="43" 
          width="15" 
          height="10" 
          rx="1"
          fill="#1e293b" 
          stroke="#64748b" 
          strokeWidth="1.5"
        />
        <rect 
          x="1" 
          y="44" 
          width="13" 
          height="8" 
          fill="#334155"
        />
        <rect 
          x="2" 
          y="45" 
          width="2" 
          height="6" 
          fill="white" 
          opacity="0.2"
        />
        <circle cx="0" cy="48" r="5" fill="#334155" stroke="#64748b" strokeWidth="1.5"/>
        <circle cx="0" cy="48" r="3" fill="#1e293b"/>
        
        {/* 출구 */}
        <rect 
          x="105" 
          y="43" 
          width="15" 
          height="10" 
          rx="1"
          fill="#1e293b" 
          stroke="#64748b" 
          strokeWidth="1.5"
        />
        <rect 
          x="106" 
          y="44" 
          width="13" 
          height="8" 
          fill="#334155"
        />
        <rect 
          x="107" 
          y="45" 
          width="2" 
          height="6" 
          fill="white" 
          opacity="0.2"
        />
        <circle cx="120" cy="48" r="5" fill="#334155" stroke="#64748b" strokeWidth="1.5"/>
        <circle cx="120" cy="48" r="3" fill="#1e293b"/>
      </g>
      
      {/* 코너 볼트 */}
      {[[16, 16], [104, 16], [16, 134], [104, 134]].map(([x, y], i) => (
        <g key={i}>
          <circle cx={x} cy={y} r="3" fill="#94a3b8" stroke="#64748b" strokeWidth="1"/>
          <circle cx={x} cy={y} r="1.5" fill="#475569"/>
        </g>
      ))}
      
      {/* 측면 하이라이트 */}
      <rect x="12" y="15" width="5" height="120" fill="white" opacity="0.12"/>
      <rect x="103" y="15" width="5" height="120" fill="black" opacity="0.4"/>
      
    </svg>
  );
}
