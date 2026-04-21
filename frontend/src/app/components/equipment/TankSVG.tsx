import { memo } from "react";
import { motion } from "framer-motion";

interface TankSVGProps {
  fillLevel: number; // 0-100
  color?: string;
  label?: string;
  width?: number;
  height?: number;
}

// 값 갱신 시 부드럽게 전환되도록 하는 공통 transition
const LIQUID_TRANSITION = { duration: 0.6, ease: "easeOut" } as const;

function TankSVGImpl({ fillLevel, color = '#3b82f6', label, width = 100, height = 140 }: TankSVGProps) {
  const fillHeight = (fillLevel / 100) * 100;
  const liquidSurfaceY = 120 - fillHeight;
  const percentageTextY = Math.min(112, Math.max(34, liquidSurfaceY + 14));
  
  return (
    <svg width={width} height={height} viewBox="0 0 100 140" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        {/* 금속 질감 그라데이션 */}
        <linearGradient id={`tankMetalGradient-${label}`} x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#0f172a" />
          <stop offset="20%" stopColor="#334155" />
          <stop offset="50%" stopColor="#475569" />
          <stop offset="80%" stopColor="#334155" />
          <stop offset="100%" stopColor="#0f172a" />
        </linearGradient>
        
        {/* 액체 그라데이션 */}
        <linearGradient id={`liquidGradient-${label}`} x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor={color} stopOpacity="0.5" />
          <stop offset="30%" stopColor={color} stopOpacity="0.9" />
          <stop offset="70%" stopColor={color} stopOpacity="0.9" />
          <stop offset="100%" stopColor={color} stopOpacity="0.5" />
        </linearGradient>
        
        {/* 액체 표면 반짝임 */}
        <radialGradient id={`surfaceShine-${label}`}>
          <stop offset="0%" stopColor="white" stopOpacity="0.6" />
          <stop offset="50%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0.1" />
        </radialGradient>
        
        {/* 그림자 */}
        <filter id={`shadow-${label}`}>
          <feDropShadow dx="2" dy="2" stdDeviation="3" floodOpacity="0.5"/>
        </filter>
        
        {/* 내부 그림자 */}
        <filter id={`innerShadow-${label}`}>
          <feGaussianBlur in="SourceAlpha" stdDeviation="2"/>
          <feOffset dx="0" dy="2" result="offsetblur"/>
          <feComponentTransfer>
            <feFuncA type="linear" slope="0.5"/>
          </feComponentTransfer>
          <feMerge>
            <feMergeNode/>
            <feMergeNode in="SourceGraphic"/>
          </feMerge>
        </filter>
      </defs>
      
      {/* 탱크 그림자 */}
      <ellipse cx="50" cy="125" rx="38" ry="5" fill="black" opacity="0.3"/>
      
      {/* 탱크 상단 타원 - 3D 효과 */}
      <ellipse cx="50" cy="20" rx="36" ry="8" fill="#1e293b" stroke="#475569" strokeWidth="1"/>
      <ellipse cx="50" cy="20" rx="35" ry="7.5" fill="url(#tankMetalGradient-rawWater)" stroke="#64748b" strokeWidth="1.5"/>
      
      {/* 탱크 몸통 */}
      <rect x="14" y="20" width="72" height="100" fill={`url(#tankMetalGradient-${label})`} stroke="#64748b" strokeWidth="2"/>
      
      {/* 내부 어두운 영역 */}
      <rect x="16" y="22" width="68" height="96" fill="#0f172a" opacity="0.6"/>
      
      {/* 액체 */}
      {fillLevel > 0 && (
        <>
          <motion.rect
            x="16"
            width="68"
            fill={`url(#liquidGradient-${label})`}
            opacity="0.95"
            initial={false}
            animate={{ y: 120 - fillHeight, height: fillHeight }}
            transition={LIQUID_TRANSITION}
          />

          {/* 액체 내부 하이라이트 */}
          <motion.rect
            x="18"
            width="8"
            fill="white"
            opacity="0.15"
            initial={false}
            animate={{
              y: 122 - fillHeight,
              height: Math.max(0, fillHeight - 4),
            }}
            transition={LIQUID_TRANSITION}
          />

          {/* 액체 표면 타원 */}
          <motion.ellipse
            cx="50"
            rx="34"
            ry="6"
            fill={`url(#surfaceShine-${label})`}
            initial={false}
            animate={{ cy: liquidSurfaceY }}
            transition={LIQUID_TRANSITION}
          />

          {/* 표면 애니메이션 */}
          <motion.ellipse
            cx="50"
            rx="34"
            ry="5"
            fill={color}
            opacity="0.4"
            initial={false}
            animate={{ cy: liquidSurfaceY }}
            transition={LIQUID_TRANSITION}
          >
            <animate
              attributeName="opacity"
              values="0.3;0.5;0.3"
              dur="3s"
              repeatCount="indefinite"
            />
          </motion.ellipse>

          <motion.text
            x="50"
            fill="white"
            fontSize="16"
            fontWeight="800"
            textAnchor="middle"
            dominantBaseline="middle"
            stroke="rgba(0, 0, 0, 0.45)"
            strokeWidth="0.6"
            paintOrder="stroke"
            initial={false}
            animate={{ y: percentageTextY }}
            transition={LIQUID_TRANSITION}
          >
            {`${Math.round(fillLevel)}%`}
          </motion.text>
        </>
      )}
      
      {/* 탱크 하단 타원 - 3D 효과 */}
      <ellipse cx="50" cy="120" rx="36" ry="8" fill="#0f172a" stroke="#475569" strokeWidth="1"/>
      <ellipse cx="50" cy="120" rx="35" ry="7.5" fill="#1e293b" stroke="#64748b" strokeWidth="1.5"/>
      
      {/* 측면 강조 하이라이트 */}
      <rect x="16" y="25" width="5" height="90" fill="white" opacity="0.15"/>
      <rect x="78" y="25" width="6" height="90" fill="black" opacity="0.1"/>
      
      {/* 중앙 하이라이트 */}
      <rect x="48" y="25" width="4" height="90" fill="white" opacity="0.08"/>
      
      
      {/* 게이지 눈금 */}
      {[0, 25, 50, 75, 100].map((level) => (
        <g key={level}>
          <text 
            x="85" 
            y={122 - level} 
            fill="#94a3b8" 
            fontSize="5" 
            textAnchor="end"
          >
            {level}
          </text>
        </g>
      ))}
      
      {/* 배출 밸브 */}
      <g>
        <circle cx="50" cy="128" r="5" fill="#334155" stroke="#64748b" strokeWidth="1.5"/>
        <circle cx="50" cy="128" r="3.5" fill="#94a3b8"/>
        <rect x="48" y="128" width="4" height="10" fill="#475569" stroke="#64748b" strokeWidth="1"/>
        <rect x="46" y="136" width="8" height="3" rx="1" fill="#64748b"/>
      </g>
      
      {/* 배관 연결구 */}
      <g>
        <rect x="8" y="116" width="8" height="6" fill="#334155" stroke="#64748b" strokeWidth="1"/>
        <circle cx="91" cy="119" r="3" fill="#475569" stroke="#64748b" strokeWidth="1"/>
      </g>
      
      {/* 상단 안전 밸브 */}
      <g>
        <rect x="48" y="14" width="4" height="8" fill="#334155" stroke="#64748b" strokeWidth="1"/>
        <circle cx="50" cy="12" r="3" fill="#94a3b8" stroke="#64748b" strokeWidth="1"/>
      </g>
      
      {/* 리벳/볼트 디테일 */}
      {[30, 60, 90].map((y) => (
        <g key={y}>
          <circle cx="14" cy={y} r="1.5" fill="#94a3b8" stroke="#475569" strokeWidth="0.5"/>
          <circle cx="86" cy={y} r="1.5" fill="#94a3b8" stroke="#475569" strokeWidth="0.5"/>
        </g>
      ))}
    </svg>
  );
}

// fillLevel이 같은 탱크는 리렌더 스킵 (5개 탱크 중 1개만 변해도 나머지 4개 재렌더 방지)
export const TankSVG = memo(TankSVGImpl);
