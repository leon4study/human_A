interface NutrientSupplierSVGProps {
  width?: number;
  height?: number;
}

// 양액 자동공급기(공급기/컨트롤러 느낌)
//  - 상단 헤더: AUTO SUPPLIER 라벨 + LED
//  - 상단 중앙: LCD 디스플레이 (EC/pH/MODE 표시)
//  - 중앙: 5개 도징 펌프 (각 탱크에서 양액을 끌어오는 소형 펌프 시각화)
//  - 하단: 컨트롤 버튼(START/STOP) + 상태 LED 배열
//  - 우측: 5개 입력 포트 (P1~P5)
//  - 하단: 출력 포트 → 재배구역 메인 라인
export function NutrientSupplierSVG({
  width = 130,
  height = 160,
}: NutrientSupplierSVGProps) {
  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 130 160"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <linearGradient id="supplierBody" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#0f172a" />
          <stop offset="25%" stopColor="#334155" />
          <stop offset="50%" stopColor="#475569" />
          <stop offset="75%" stopColor="#334155" />
          <stop offset="100%" stopColor="#0f172a" />
        </linearGradient>

        <linearGradient id="supplierHeader" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#1e293b" />
          <stop offset="100%" stopColor="#0f172a" />
        </linearGradient>

        <linearGradient id="lcdScreen" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#052e16" />
          <stop offset="50%" stopColor="#064e3b" />
          <stop offset="100%" stopColor="#052e16" />
        </linearGradient>

        <linearGradient id="dosingPump" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#475569" />
          <stop offset="50%" stopColor="#334155" />
          <stop offset="100%" stopColor="#1e293b" />
        </linearGradient>

        <filter id="supplierShadow">
          <feDropShadow dx="2" dy="3" stdDeviation="3" floodOpacity="0.5" />
        </filter>
      </defs>

      {/* 바닥 그림자 (비활성화) */}
      {/* <ellipse cx="65" cy="152" rx="48" ry="4" fill="black" opacity="0.3" /> */}

      {/* 본체 */}
      <rect
        x="14"
        y="20"
        width="100"
        height="120"
        rx="4"
        fill="url(#supplierBody)"
        stroke="#94a3b8"
        strokeWidth="1.4"
        filter="url(#supplierShadow)"
      />

      {/* LCD 디스플레이 (헤더 공간까지 확장) */}
      <rect
        x="25"
        y="29"
        width="75"
        height="36"
        rx="1.5"
        fill="url(#lcdScreen)"
        stroke="#1e293b"
        strokeWidth="1.5"
      />
      {/* LCD 테두리 하이라이트 */}
      <rect
        x="25.5"
        y="29.5"
        width="72"
        height="36"
        rx="1"
        fill="none"
        stroke="#065f46"
        strokeWidth="0.5"
      />
      {/* 상단 전원/통신 LED (LCD 우측 상단) */}
      {/* <circle cx="92" cy="29" r="1.2" fill="#4ade80">
        <animate
          attributeName="opacity"
          values="1;0.4;1"
          dur="1.6s"
          repeatCount="indefinite"
        />
      </circle> */}
      {/* <text
        x="28"
        y="35"
        fill="#4ade80"
        fontSize="7.5"
        fontFamily="JetBrains Mono"
        fontWeight="700"
        letterSpacing="0.6"
      >
        NUTRIENT SYS
      </text> */}
      {/* 구분선 */}
      <line
        x1="28"
        y1="38"
        x2="93"
        y2="38"
        stroke="#065f46"
        strokeWidth="0.5"
      />
      <text
        x="29"
        y="43"
        fill="#4ade80"
        fontSize="12"
        fontFamily="JetBrains Mono"
        fontWeight="700"
      >
        EC 2.10
      </text>
      <text
        x="29"
        y="59"
        fill="#4ade80"
        fontSize="12"
        fontFamily="JetBrains Mono"
        fontWeight="600"
      >
        pH 6.10
      </text>
      {/* <text
        x="28"
        y="63"
        fill="#4ade80"
        fontSize="10"
        fontFamily="JetBrains Mono"
        fontWeight="600"
      >
        MODE AUTO
      </text> */}
      {/* LCD 깜빡이는 커서 */}
      <rect x="85" y="54" width="3" height="7" fill="#4ade80">
        <animate
          attributeName="opacity"
          values="1;0;1"
          dur="1s"
          repeatCount="indefinite"
        />
      </rect>

      {/* 도징 펌프 배열 라벨 */}
      <text
        x="22"
        y="74"
        fill="#94a3b8"
        fontSize="5"
        fontWeight="700"
        letterSpacing="0.8"
      >
        DOSING PUMPS
      </text>
      {/* 구분선 */}
      <line
        x1="22"
        y1="76"
        x2="100"
        y2="76"
        stroke="#334155"
        strokeWidth="0.6"
      />

      {/* 도징 펌프 5개 */}
      {[0, 1, 2, 3, 4].map((i) => {
        const cx = 28 + i * 13;
        const statusColor = ["#fbbf24", "#fbbf24", "#fbbf24", "#64748b", "#64748b"][i];
        return (
          <g key={`pump-${i}`}>
            {/* 펌프 섀시 */}
            <rect
              x={cx - 4.5}
              y={80}
              width={9}
              height={18}
              rx={1}
              fill="url(#dosingPump)"
              stroke="#64748b"
              strokeWidth="0.5"
            />
            {/* 펌프 헤드(회전 모터) */}
            <circle
              cx={cx}
              cy={85.5}
              r={3}
              fill="#1e293b"
              stroke="#cbd5e1"
              strokeWidth="0.4"
            />
            {/* 펌프 중앙 허브 */}
            <circle cx={cx} cy={85.5} r={0.8} fill="#94a3b8" />
            {/* 펌프 튜브 */}
            <rect
              x={cx - 2.5}
              y={90}
              width={5}
              height={5}
              fill="#1e293b"
              stroke="#475569"
              strokeWidth="0.4"
            />
            {/* 상태 LED */}
            <circle cx={cx} cy={96.3} r={0.7} fill={statusColor} />
            {/* 펌프 라벨 */}
            <text
              x={cx}
              y={103}
              textAnchor="middle"
              fill="#cbd5e1"
              fontSize="3.8"
              fontWeight="700"
            >
              P{i + 1}
            </text>
          </g>
        );
      })}

      {/* 컨트롤 영역 구분선 */}
      <line
        x1="22"
        y1="108"
        x2="100"
        y2="108"
        stroke="#334155"
        strokeWidth="0.6"
      />

      {/* START 버튼 (녹색) */}
      <rect
        x="22"
        y="113"
        width="22"
        height="10"
        rx="1.5"
        fill="#166534"
        stroke="#4ade80"
        strokeWidth="0.7"
      />
      <rect
        x="22"
        y="113"
        width="22"
        height="4"
        rx="1.5"
        fill="#22c55e"
        opacity="0.5"
      />
      <text
        x="33"
        y="120"
        textAnchor="middle"
        fill="#f0fdf4"
        fontSize="5.5"
        fontWeight="800"
        letterSpacing="0.8"
      >
        START
      </text>

      {/* STOP 버튼 (빨강) */}
      <rect
        x="48"
        y="113"
        width="22"
        height="10"
        rx="1.5"
        fill="#1e293b"
        stroke="#475569"
        strokeWidth="0.7"
      />
      <text
        x="59"
        y="120"
        textAnchor="middle"
        fill="#94a3b8"
        fontSize="5.5"
        fontWeight="800"
        letterSpacing="0.8"
      >
        STOP
      </text>

      {/* 상태 LED 배열 */}
      <rect
        x="74"
        y="113"
        width="26"
        height="10"
        rx="1.5"
        fill="#0a0f1a"
        stroke="#475569"
        strokeWidth="0.6"
      />
      <circle cx="79" cy="118" r="1.4" fill="#22c55e">
        <animate
          attributeName="opacity"
          values="1;0.4;1"
          dur="1.5s"
          repeatCount="indefinite"
        />
      </circle>
      <circle cx="85" cy="118" r="1.4" fill="#fbbf24" />
      <circle cx="91" cy="118" r="1.4" fill="#3b82f6" />
      <circle cx="97" cy="118" r="1.4" fill="#1e293b" stroke="#475569" strokeWidth="0.4" />

      {/* 하단 정보 라벨 */}
      <text
        x="64"
        y="133"
        textAnchor="middle"
        fill="#64748b"
        fontSize="4.5"
        letterSpacing="0.6"
      >
        MODEL NS-530 · 12V DC
      </text>

      {/* 좌측 원수 입력 포트 (원수 공급 라인이 들어오는 자리) */}
      <g>
        <rect
          x="9"
          y="45"
          width="9"
          height="6.4"
          rx="0.6"
          fill="#334155"
          stroke="#94a3b8"
          strokeWidth="0.4"
        />
        <circle cx="11" cy="48.2" r="2" fill="#020617" />
        <circle
          cx="11"
          cy="48.2"
          r="2"
          fill="none"
          stroke="#64748b"
          strokeWidth="0.5"
        />
        <text
          x="25"
          y="49.8"
          textAnchor="middle"
          fill="#64748b"
          fontSize="3.8"
          fontWeight="700"
        >
          IN
        </text>
      </g>

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
            {/* 포트 번호 (공급기 내부) */}
            <text
              x="103"
              y={y + 1.5}
              textAnchor="middle"
              fill="#64748b"
              fontSize="3.8"
              fontWeight="700"
            >
              P{i + 1}
            </text>
          </g>
        );
      })}

      {/* 좌측 볼트 디테일 */}
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
