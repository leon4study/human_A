interface SprayAnimationProps {
  x: number;
  y: number;
  isActive: boolean;
}

export function SprayAnimation({ x, y, isActive }: SprayAnimationProps) {
  if (!isActive) return null;

  return (
    <g>
      {/* 좌우로 물방울 스프레이 효과 */}
      {/* 왼쪽으로 뿌려지는 물방울 */}
      {Array.from({ length: 5 }).map((_, i) => {
        const offsetY = i * 5;
        const offsetX = -4 - i * 1.5;
        const delay = i * 0.15;
        
        return (
          <g key={`left-${i}`}>
            <circle
              cx={x}
              cy={y + offsetY}
              r="0.2"
              fill="#3b82f6"
              opacity="0"
            >
              <animate
                attributeName="cx"
                from={x}
                to={x + offsetX}
                dur="1.2s"
                begin={`${delay}s`}
                repeatCount="indefinite"
              />
              <animate
                attributeName="cy"
                from={y + offsetY}
                to={y + offsetY + 3}
                dur="1.2s"
                begin={`${delay}s`}
                repeatCount="indefinite"
              />
              <animate
                attributeName="opacity"
                from="0.9"
                to="0"
                dur="1.2s"
                begin={`${delay}s`}
                repeatCount="indefinite"
              />
            </circle>
          </g>
        );
      })}
      
      {/* 오른쪽으로 뿌려지는 물방울 */}
      {Array.from({ length: 5 }).map((_, i) => {
        const offsetY = i * 5;
        const offsetX = 4 + i * 1.5;
        const delay = i * 0.15;
        
        return (
          <g key={`right-${i}`}>
            <circle
              cx={x}
              cy={y + offsetY}
              r="0.2"
              fill="#60a5fa"
              opacity="0"
            >
              <animate
                attributeName="cx"
                from={x}
                to={x + offsetX}
                dur="1.2s"
                begin={`${delay}s`}
                repeatCount="indefinite"
              />
              <animate
                attributeName="cy"
                from={y + offsetY}
                to={y + offsetY + 3}
                dur="1.2s"
                begin={`${delay}s`}
                repeatCount="indefinite"
              />
              <animate
                attributeName="opacity"
                from="0.9"
                to="0"
                dur="1.2s"
                begin={`${delay}s`}
                repeatCount="indefinite"
              />
            </circle>
          </g>
        );
      })}
    </g>
  );
}
