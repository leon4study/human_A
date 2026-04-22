interface SprayAnimationProps {
  x: number;
  y: number;
  isActive: boolean;
}

export function SprayAnimation({ x, y, isActive }: SprayAnimationProps) {
  if (!isActive) return null;

  return (
    <g>
      {Array.from({ length: 5 }).map((_, i) => {
        const offsetY = i * 5;
        const offsetX = -4 - i * 1.5;
        const delay = i * 0.15;

        return (
          <circle key={`left-${i}`} cx={x} cy={y + offsetY} r="0.2" fill="#3b82f6" opacity="0">
            <animateTransform
              attributeName="transform"
              type="translate"
              from="0 0"
              to={`${offsetX} 3`}
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
        );
      })}

      {Array.from({ length: 5 }).map((_, i) => {
        const offsetY = i * 5;
        const offsetX = 4 + i * 1.5;
        const delay = i * 0.15;

        return (
          <circle key={`right-${i}`} cx={x} cy={y + offsetY} r="0.2" fill="#60a5fa" opacity="0">
            <animateTransform
              attributeName="transform"
              type="translate"
              from="0 0"
              to={`${offsetX} 3`}
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
        );
      })}
    </g>
  );
}
