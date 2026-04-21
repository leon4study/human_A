import type { InferenceDomainReport, InferencePayload, SpikeInfo } from "../../types/dashboard";
import type { ChartBuffer, ComparativeMetrics } from "../../hooks/useDashboardSocket";
import "./equipment-modal.css";

interface AiAnalysisModalProps {
  open: boolean;
  onClose: () => void;
  inference?: InferencePayload | null;
  chartSnapshot?: ChartBuffer | null;
  comparativeMetrics?: ComparativeMetrics | null;
}

// ─── 상수 ────────────────────────────────────────────────────────────────────

const DOMAIN_LABELS: Record<string, string> = {
  motor: "모터 구동",
  hydraulic: "수압/유압",
  nutrient: "양액/수질",
  zone_drip: "구역 점적",
};

const FEATURE_LABELS: Record<string, string> = {
  flow_rate_l_min: "메인 유량",
  hydraulic_power_kw: "수력 동력",
  bearing_vibration_rms_mm_s: "베어링 진동",
  filter_pressure_in_kpa: "필터 입구 압력",
  zone1_substrate_moisture_pct: "배지 수분",
  flow_baseline_l_min: "기준 유량",
  zone1_resistance: "배관 저항",
  turbidity_ntu: "탁도",
  tank_a_level_pct: "A비료통 수위",
  bearing_temperature_c: "베어링 온도",
  air_temp_c: "실내 기온",
  pressure_trend_10: "압력 10분 트렌드",
  motor_temperature_c: "모터 온도",
  pump_rpm: "펌프 회전수",
  motor_power_kw: "모터 전력",
  wire_to_water_efficiency: "전기→수력 효율",
  rpm_slope: "RPM 변화율",
  motor_current_a: "모터 전류",
  discharge_pressure_kpa: "토출 압력",
  mix_ph: "혼합액 pH",
  mix_ec_ds_m: "혼합액 EC",
  drain_ec_ds_m: "배액 EC",
};

const LEVEL_COLORS: Record<number, string> = {
  0: "#4caf50",
  1: "#ffc107",
  2: "#ff9800",
  3: "#f44336",
};

const LEVEL_LABELS_KO: Record<number, string> = {
  0: "정상",
  1: "주의",
  2: "경고",
  3: "위험",
};

// ─── SVG 차트 컴포넌트 ────────────────────────────────────────────────────────

const CW = 200; // chart width
const CH = 75;  // chart height
const PAD = 8;
const IW = CW - PAD * 2;
const IH = CH - PAD * 2;

function clampFinite(values: number[]): number[] {
  return values.filter((v) => Number.isFinite(v));
}

interface LineChartProps {
  values: number[];
  color?: string;
  label: string;
  unit: string;
  refValues?: number[];  // 목표선 (예: target_ec)
  refColor?: string;
  warningThreshold?: number;
}

function MiniLineChart({
  values,
  color = "#3eb8ff",
  label,
  unit,
  refValues,
  refColor = "rgba(255,200,0,0.7)",
  warningThreshold,
}: LineChartProps) {
  const valid = clampFinite(values);
  const refValid = refValues ? clampFinite(refValues) : [];
  const allValid = [...valid, ...refValid];

  const lastVal = valid[valid.length - 1];
  const lastValStr =
    lastVal !== undefined ? `${lastVal.toFixed(1)} ${unit}` : "—";

  if (valid.length < 2) {
    return (
      <div style={{ width: CW }}>
        <div className="ai-chart-label">{label}</div>
        <div className="ai-chart-empty">데이터 수집 중...</div>
        <div className="ai-chart-value" style={{ color }}>{lastValStr}</div>
      </div>
    );
  }

  const mn = Math.min(...allValid);
  const mx = Math.max(...allValid);
  const rng = mx - mn || 1;
  const toX = (i: number, len: number) => PAD + (i / (len - 1)) * IW;
  const toY = (v: number) => PAD + IH - ((v - mn) / rng) * IH;

  const mainPts = values
    .map((v, i) => `${toX(i, values.length)},${Number.isFinite(v) ? toY(v) : toY(mn)}`)
    .join(" ");

  const areaClose = `${toX(values.length - 1, values.length)},${CH - PAD} ${PAD},${CH - PAD}`;

  const refPts =
    refValues && refValues.length >= 2
      ? refValues.map((v, i) => `${toX(i, refValues.length)},${toY(v)}`).join(" ")
      : null;

  const warnY =
    warningThreshold !== undefined ? toY(warningThreshold) : null;

  return (
    <div style={{ width: CW }}>
      <div className="ai-chart-label">{label}</div>
      <svg width={CW} height={CH} style={{ display: "block" }}>
        <rect width={CW} height={CH} rx={6} fill="rgba(255,255,255,0.04)" />

        {/* 경고 임계선 */}
        {warnY !== null && (
          <line
            x1={PAD} y1={warnY} x2={CW - PAD} y2={warnY}
            stroke="rgba(255,152,0,0.55)" strokeWidth={1} strokeDasharray="4,3"
          />
        )}

        {/* 영역 채우기 */}
        <polyline
          points={`${PAD},${CH - PAD} ${mainPts} ${areaClose}`}
          fill={`${color}18`}
          stroke="none"
        />

        {/* 메인 라인 */}
        <polyline
          points={mainPts}
          fill="none"
          stroke={color}
          strokeWidth={1.5}
          strokeLinejoin="round"
        />

        {/* 목표선 */}
        {refPts && (
          <polyline
            points={refPts}
            fill="none"
            stroke={refColor}
            strokeWidth={1}
            strokeDasharray="4,3"
          />
        )}

        {/* 마지막 포인트 */}
        {Number.isFinite(lastVal) && (
          <circle
            cx={toX(values.length - 1, values.length)}
            cy={toY(lastVal)}
            r={3}
            fill={color}
          />
        )}
      </svg>
      <div className="ai-chart-value" style={{ color }}>{lastValStr}</div>
    </div>
  );
}

interface ScatterChartProps {
  xValues: number[];
  yValues: number[];
  xLabel: string;
  yLabel: string;
  xUnit: string;
  yUnit: string;
}

function ScatterChart({
  xValues,
  yValues,
  xLabel,
  yLabel,
  xUnit,
  yUnit,
}: ScatterChartProps) {
  const pairs = xValues
    .map((x, i) => [x, yValues[i]] as [number, number])
    .filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y));

  const lastPair = pairs[pairs.length - 1];
  const lastStr =
    lastPair
      ? `${lastPair[0].toFixed(1)} ${xUnit}, ${lastPair[1].toFixed(1)} ${yUnit}`
      : "—";

  if (pairs.length < 2) {
    return (
      <div style={{ width: CW }}>
        <div className="ai-chart-label">{yLabel} vs {xLabel}</div>
        <div className="ai-chart-empty">데이터 수집 중...</div>
        <div className="ai-chart-value" style={{ color: "#3eb8ff" }}>{lastStr}</div>
      </div>
    );
  }

  const xs = pairs.map((p) => p[0]);
  const ys = pairs.map((p) => p[1]);
  const xMn = Math.min(...xs), xMx = Math.max(...xs);
  const yMn = Math.min(...ys), yMx = Math.max(...ys);
  const xRng = xMx - xMn || 1;
  const yRng = yMx - yMn || 1;
  const toX = (v: number) => PAD + ((v - xMn) / xRng) * IW;
  const toY = (v: number) => PAD + IH - ((v - yMn) / yRng) * IH;

  return (
    <div style={{ width: CW }}>
      <div className="ai-chart-label">{yLabel} vs {xLabel}</div>
      <svg width={CW} height={CH} style={{ display: "block" }}>
        <rect width={CW} height={CH} rx={6} fill="rgba(255,255,255,0.04)" />

        {/* 이력 점 */}
        {pairs.slice(0, -1).map(([x, y], i) => (
          <circle
            key={i}
            cx={toX(x)}
            cy={toY(y)}
            r={2}
            fill="rgba(62,184,255,0.4)"
          />
        ))}

        {/* 최신 포인트 */}
        {lastPair && (
          <circle
            cx={toX(lastPair[0])}
            cy={toY(lastPair[1])}
            r={3.5}
            fill="#3eb8ff"
          />
        )}

        {/* 축 라벨 */}
        <text x={PAD} y={CH - 1} fontSize={8} fill="rgba(220,242,255,0.35)">{xLabel}</text>
        <text x={PAD} y={PAD + 7} fontSize={8} fill="rgba(220,242,255,0.35)">{yLabel}</text>
      </svg>
      <div className="ai-chart-value" style={{ color: "#3eb8ff" }}>{lastStr}</div>
    </div>
  );
}

// ─── 도메인별 차트 정의 ───────────────────────────────────────────────────────

interface ChartRow {
  key: string;
  element: React.ReactNode;
  description: string; // 우측 설명 텍스트
}

function getDomainCharts(domain: string, buf: ChartBuffer): ChartRow[] {
  switch (domain) {
    case "motor":
    case "hydraulic":
      return [
        {
          key: "p_vs_f",
          element: (
            <ScatterChart
              xValues={buf.flow}
              yValues={buf.pressure}
              xLabel="유량"
              yLabel="압력"
              xUnit="L/min"
              yUnit="kPa"
            />
          ),
          description: "펌프 운전 곡선\n압력-유량 관계 확인",
        },
        {
          key: "f_vs_pw",
          element: (
            <ScatterChart
              xValues={buf.motor_power}
              yValues={buf.flow}
              xLabel="전력"
              yLabel="유량"
              xUnit="kW"
              yUnit="L/min"
            />
          ),
          description: "에너지 효율\n전력 대비 유량 분포",
        },
        {
          key: "current",
          element: (
            <MiniLineChart
              values={buf.motor_current}
              label="모터 전류"
              unit="A"
              color="#9fe7ff"
            />
          ),
          description: "동특성 (모터 전류)\n급변 시 기동 이상 의심",
        },
        {
          key: "vib",
          element: (
            <MiniLineChart
              values={buf.bearing_vib}
              label="베어링 진동"
              unit="mm/s"
              color="#f44336"
            />
          ),
          description: "진동 추이\n상승 지속 시 베어링 마모",
        },
        {
          key: "temp",
          element: (
            <MiniLineChart
              values={buf.motor_temp}
              label="모터 온도"
              unit="°C"
              color="#ff9800"
              warningThreshold={80}
            />
          ),
          description: "설비 이상 표준도표\n온도 80°C 이상 경고",
        },
      ];

    case "nutrient":
      return [
        {
          key: "ec",
          element: (
            <MiniLineChart
              values={buf.mix_ec}
              label="혼합액 EC"
              unit="dS/m"
              color="#4caf50"
              refValues={buf.target_ec}
              refColor="rgba(255,200,0,0.8)"
            />
          ),
          description: "EC 추이\n점선=목표, 실선=실측",
        },
        {
          key: "ph",
          element: (
            <MiniLineChart
              values={buf.mix_ph}
              label="혼합액 pH"
              unit="pH"
              color="#3eb8ff"
              refValues={buf.target_ph}
              refColor="rgba(255,200,0,0.8)"
              warningThreshold={6.5}
            />
          ),
          description: "pH 추이\n점선=목표, 6.5 이상 침전 주의",
        },
        {
          key: "ec_vs_f",
          element: (
            <ScatterChart
              xValues={buf.flow}
              yValues={buf.mix_ec}
              xLabel="유량"
              yLabel="EC"
              xUnit="L/min"
              yUnit="dS/m"
            />
          ),
          description: "유량-EC 관계\n유량 변화에 따른 EC 반응",
        },
        {
          key: "motor_temp",
          element: (
            <MiniLineChart
              values={buf.motor_temp}
              label="모터 온도"
              unit="°C"
              color="#ff9800"
              warningThreshold={80}
            />
          ),
          description: "동특성 (모터 온도)\n급등 시 공급 과부하",
        },
        {
          key: "pressure",
          element: (
            <MiniLineChart
              values={buf.pressure}
              label="토출 압력"
              unit="kPa"
              color="#9fe7ff"
            />
          ),
          description: "설비 이상 표준도표\n배관 저항 변화 모니터링",
        },
      ];

    case "zone_drip":
      return [
        {
          key: "moisture",
          element: (
            <MiniLineChart
              values={buf.zone1_moisture}
              label="Zone1 배지 수분"
              unit="%"
              color="#4caf50"
            />
          ),
          description: "수분 반응 추이\n급액 후 수분 변화율 확인",
        },
        {
          key: "zone_flow",
          element: (
            <MiniLineChart
              values={buf.zone1_flow}
              label="Zone1 유량"
              unit="L/min"
              color="#3eb8ff"
            />
          ),
          description: "구역 유량 추이\n감소 시 점적 막힘 의심",
        },
        {
          key: "p_vs_f",
          element: (
            <ScatterChart
              xValues={buf.zone1_flow}
              yValues={buf.pressure}
              xLabel="Zone1 유량"
              yLabel="압력"
              xUnit="L/min"
              yUnit="kPa"
            />
          ),
          description: "배관 저항 분포\n압력-유량 비율 이상 시 막힘",
        },
        {
          key: "current",
          element: (
            <MiniLineChart
              values={buf.motor_current}
              label="모터 전류"
              unit="A"
              color="#9fe7ff"
            />
          ),
          description: "동특성 (모터 전류)\n점적 저항 증가 시 전류 상승",
        },
        {
          key: "vib",
          element: (
            <MiniLineChart
              values={buf.bearing_vib}
              label="베어링 진동"
              unit="mm/s"
              color="#f44336"
            />
          ),
          description: "설비 이상 표준도표\n진동 상승 = 펌프 부하 이상",
        },
      ];

    default:
      return [];
  }
}

// ─── 서브 컴포넌트 ────────────────────────────────────────────────────────────

function SpikeBadges({ spike }: { spike: SpikeInfo }) {
  if (!spike.is_spike && !spike.is_startup_spike && !spike.is_anomaly_spike)
    return null;
  return (
    <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginTop: "8px" }}>
      {spike.is_anomaly_spike && (
        <span className="ai-spike-badge ai-spike-badge--danger">
          ⚡ 이상 스파이크
        </span>
      )}
      {spike.is_startup_spike && !spike.is_anomaly_spike && (
        <span className="ai-spike-badge ai-spike-badge--muted">
          기동 스파이크
        </span>
      )}
    </div>
  );
}

function AlarmBadge({ level }: { level: number }) {
  const color = LEVEL_COLORS[level] ?? "#4caf50";
  const text = LEVEL_LABELS_KO[level] ?? "알 수 없음";
  return (
    <span
      style={{
        display: "inline-block",
        padding: "3px 10px",
        borderRadius: "20px",
        background: `${color}22`,
        color,
        border: `1px solid ${color}66`,
        fontSize: "12px",
        fontWeight: 700,
        whiteSpace: "nowrap",
      }}
    >
      {text}
    </span>
  );
}

function RcaBar({
  feature,
  contribution,
}: {
  feature: string;
  contribution: number;
}) {
  const label = FEATURE_LABELS[feature] ?? feature;
  return (
    <div style={{ marginBottom: "8px" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: "12px",
          marginBottom: "4px",
        }}
      >
        <span style={{ color: "rgba(225,243,255,0.75)" }}>{label}</span>
        <span style={{ color: "#9fe7ff", fontWeight: 600 }}>
          {contribution.toFixed(1)}%
        </span>
      </div>
      <div
        style={{
          height: "5px",
          background: "rgba(255,255,255,0.08)",
          borderRadius: "3px",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${Math.min(contribution, 100)}%`,
            background: "linear-gradient(90deg, #3eb8ff, #9fe7ff)",
            borderRadius: "3px",
          }}
        />
      </div>
    </div>
  );
}

function DomainCard({
  domain,
  report,
  compact = false,
}: {
  domain: string;
  report: InferenceDomainReport;
  compact?: boolean;
}) {
  const label = DOMAIN_LABELS[domain] ?? domain;
  const level = report.alarm?.level ?? 0;
  const borderColor = LEVEL_COLORS[level] ?? "#3eb8ff";

  return (
    <div
      style={{
        border: `1px solid ${borderColor}44`,
        borderRadius: "14px",
        padding: compact ? "10px 14px" : "14px 16px",
        background: `${borderColor}0d`,
        marginBottom: "10px",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom:
            !compact && report.rca && report.rca.length > 0 ? "12px" : "0",
        }}
      >
        <span
          style={{
            fontWeight: 700,
            fontSize: compact ? "13px" : "15px",
            color: "#f3fbff",
          }}
        >
          {label}
        </span>
        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          {report.score !== undefined && (
            <span
              style={{ fontSize: "11px", color: "rgba(220,242,255,0.5)" }}
            >
              MSE {report.score.toExponential(2)}
            </span>
          )}
          <AlarmBadge level={level} />
        </div>
      </div>

      {!compact && report.rca && report.rca.length > 0 && (
        <div>
          <div
            style={{
              fontSize: "11px",
              color: "rgba(159,231,255,0.6)",
              marginBottom: "8px",
              fontWeight: 600,
            }}
          >
            이상 기여 피처 Top {report.rca.length}
          </div>
          {report.rca.map((item) => (
            <RcaBar
              key={item.feature}
              feature={item.feature}
              contribution={item.contribution}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// 스케치 레이아웃: 차트(좌) + 설명(우)
function ChartRow({
  chartEl,
  description,
}: {
  chartEl: React.ReactNode;
  description: string;
}) {
  return (
    <div className="ai-chart-row">
      <div className="ai-chart-cell">{chartEl}</div>
      <div className="ai-chart-desc">
        {description.split("\n").map((line, i) => (
          <div key={i} style={{ lineHeight: 1.5 }}>
            {i === 0 ? (
              <span style={{ fontWeight: 600, color: "rgba(220,242,255,0.8)" }}>
                {line}
              </span>
            ) : (
              <span style={{ fontSize: "11px", color: "rgba(220,242,255,0.5)" }}>
                {line}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── 비교분석 섹션 (§2-2) ────────────────────────────────────────────────────

const CMP_EPS = 1e-6;
const CMP_MIN_SAMPLES = 30;

function lastFinite(arr?: number[]): number | undefined {
  if (!Array.isArray(arr)) return undefined;
  for (let i = arr.length - 1; i >= 0; i--) {
    if (Number.isFinite(arr[i])) return arr[i];
  }
  return undefined;
}

function ComparativeSection({
  chartSnapshot,
  comparative,
}: {
  chartSnapshot?: ChartBuffer | null;
  comparative?: ComparativeMetrics | null;
}) {
  // 순간 지표 — chartSnapshot 최신 포인트 사용
  const dp = chartSnapshot ? lastFinite(chartSnapshot.pressure) : undefined;
  const sp = chartSnapshot ? lastFinite(chartSnapshot.suction) : undefined;
  const fl = chartSnapshot ? lastFinite(chartSnapshot.flow) : undefined;
  const pw = chartSnapshot ? lastFinite(chartSnapshot.motor_power) : undefined;

  const pressureFlowRatio =
    dp !== undefined && fl !== undefined ? dp / (fl + CMP_EPS) : undefined;
  const dpPerFlow =
    dp !== undefined && sp !== undefined && fl !== undefined
      ? (dp - sp) / (fl + CMP_EPS)
      : undefined;
  const flowPerPower =
    fl !== undefined && pw !== undefined ? fl / (pw + CMP_EPS) : undefined;

  // 온도 변화율 — 마지막 2포인트 diff
  let tempSlope: number | undefined;
  if (
    chartSnapshot &&
    Array.isArray(chartSnapshot.motor_temp) &&
    Array.isArray(chartSnapshot.ts) &&
    chartSnapshot.motor_temp.length >= 2 &&
    chartSnapshot.ts.length >= 2
  ) {
    const n = Math.min(chartSnapshot.motor_temp.length, chartSnapshot.ts.length);
    const dT = chartSnapshot.motor_temp[n - 1] - chartSnapshot.motor_temp[n - 2];
    const dt = (chartSnapshot.ts[n - 1] - chartSnapshot.ts[n - 2]) / 1000;
    if (Number.isFinite(dT) && Number.isFinite(dt) && dt > 0) {
      tempSlope = dT / dt;
    }
  }

  const samples = comparative?.samples ?? 0;
  const collecting = samples < CMP_MIN_SAMPLES;
  const pVol = comparative?.pressureVolatility;
  const fCv = comparative?.flowCv;

  const rows: { label: string; value: string; desc: string }[] = [
    {
      label: "유량 대비 압력 비율",
      value:
        pressureFlowRatio !== undefined
          ? `${pressureFlowRatio.toFixed(2)} kPa·min/L`
          : "—",
      desc: "discharge / flow — 배관 저항 지표",
    },
    {
      label: "차압 대비 유량",
      value: dpPerFlow !== undefined ? `${dpPerFlow.toFixed(2)} kPa·min/L` : "—",
      desc: "(discharge − suction) / flow — 막힘·누수 조기감지",
    },
    {
      label: "유량 대비 전력 효율",
      value: flowPerPower !== undefined ? `${flowPerPower.toFixed(1)} L/min/kW` : "—",
      desc: "flow / motor_power — 펌프 효율",
    },
    {
      label: "압력 변동성 (12h)",
      value: collecting
        ? `수집 중 (${samples}/${CMP_MIN_SAMPLES})`
        : pVol !== null && pVol !== undefined
          ? pVol.toFixed(3)
          : "—",
      desc: "std(ΔP) / IQR(ΔP) — 부하 불안정/간헐 막힘",
    },
    {
      label: "유량 변동성 (12h)",
      value: collecting
        ? `수집 중 (${samples}/${CMP_MIN_SAMPLES})`
        : fCv !== null && fCv !== undefined
          ? fCv.toFixed(3)
          : "—",
      desc: "CV = std(flow) / mean(flow)",
    },
    {
      label: "온도 변화율",
      value: tempSlope !== undefined ? `${tempSlope.toFixed(4)} °C/s` : "—",
      desc: "diff(motor_temp) / dt — 발열 추이",
    },
  ];

  return (
    <div
      className="equipment-modal-section"
      style={{ marginTop: "20px" }}
    >
      <div className="equipment-modal-section-title">비교분석</div>
      {rows.map((r) => (
        <div className="equipment-modal-row" key={r.label}>
          <span className="equipment-modal-label">
            <div>{r.label}</div>
            <div
              style={{
                fontSize: "10px",
                color: "rgba(225,243,255,0.42)",
                marginTop: "3px",
                fontWeight: 400,
              }}
            >
              {r.desc}
            </div>
          </span>
          <span className="equipment-modal-value">{r.value}</span>
        </div>
      ))}
    </div>
  );
}

// ─── 메인 모달 ────────────────────────────────────────────────────────────────

function AiAnalysisModal({
  open,
  onClose,
  inference,
  chartSnapshot,
  comparativeMetrics,
}: AiAnalysisModalProps) {
  if (!open) return null;

  const overallLevel = inference?.overall_alarm_level ?? 0;
  const overallColor = LEVEL_COLORS[overallLevel] ?? "#4caf50";
  const overallText = LEVEL_LABELS_KO[overallLevel] ?? "정상";
  const domainReports = inference?.domain_reports ?? {};
  const hasData = inference != null;

  // 가장 심각한 도메인 찾기
  const worstEntry = Object.entries(domainReports).reduce<
    [string, InferenceDomainReport] | null
  >((best, [domain, report]) => {
    if (!best) return [domain, report];
    return (report.alarm?.level ?? 0) > (best[1].alarm?.level ?? 0)
      ? [domain, report]
      : best;
  }, null);

  const worstDomain = worstEntry?.[0] ?? null;
  const chartRows =
    worstDomain && chartSnapshot
      ? getDomainCharts(worstDomain, chartSnapshot)
      : [];

  const tsDisplay = (() => {
    if (!inference?.timestamp) return null;
    try {
      const d = new Date(inference.timestamp);
      return d.toLocaleString("ko-KR", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return inference.timestamp;
    }
  })();

  return (
    <div className="equipment-modal-overlay" onClick={onClose}>
      <div
        className="equipment-modal equipment-modal--wide"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 헤더 */}
        <div className="equipment-modal-header">
          <div>
            <div className="equipment-modal-title">AI 분석 결과</div>
            <div className="equipment-modal-subtitle">
              {tsDisplay ?? "AI 기반 설비 이상 분석"}
            </div>
          </div>
          <button className="equipment-modal-close" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="equipment-modal-body">
          {!hasData && (
            <div
              style={{
                textAlign: "center",
                padding: "40px 0",
                color: "rgba(225,243,255,0.4)",
                fontSize: "14px",
              }}
            >
              추론 데이터 수신 대기 중...
            </div>
          )}

          {hasData && (
            <>
              {/* 전체 상태 배너 */}
              <div
                style={{
                  borderRadius: "14px",
                  padding: "16px 20px",
                  background: `${overallColor}15`,
                  border: `1px solid ${overallColor}55`,
                  marginBottom: "4px",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: "12px",
                }}
              >
                <div>
                  <div
                    style={{
                      fontSize: "12px",
                      color: "rgba(220,242,255,0.6)",
                      marginBottom: "4px",
                    }}
                  >
                    전체 시스템 상태
                  </div>
                  <div
                    style={{
                      fontSize: "22px",
                      fontWeight: 700,
                      color: overallColor,
                    }}
                  >
                    {overallText}
                  </div>
                </div>
                {inference.action_required && (
                  <div
                    style={{
                      fontSize: "12px",
                      color: "rgba(220,242,255,0.65)",
                      textAlign: "right",
                      maxWidth: "200px",
                      lineHeight: 1.5,
                    }}
                  >
                    {inference.action_required}
                  </div>
                )}
              </div>

              {/* 스파이크 배지 */}
              {inference.spike_info && (
                <SpikeBadges spike={inference.spike_info} />
              )}

              {/* 도메인 요약 카드 (compact) */}
              <div
                className="equipment-modal-section"
                style={{ marginTop: "18px" }}
              >
                <div className="equipment-modal-section-title">도메인별 알람</div>
                {Object.entries(domainReports).map(([domain, report]) => (
                  <DomainCard
                    key={domain}
                    domain={domain}
                    report={report}
                    compact={true}
                  />
                ))}
                {Object.keys(domainReports).length === 0 && (
                  <div
                    style={{
                      fontSize: "13px",
                      color: "rgba(225,243,255,0.4)",
                      textAlign: "center",
                      padding: "16px 0",
                    }}
                  >
                    도메인 데이터 없음
                  </div>
                )}
              </div>

              {/* 비교분석 (§2-2) */}
              <ComparativeSection
                chartSnapshot={chartSnapshot}
                comparative={comparativeMetrics}
              />

              {/* 최악 도메인 상세 분석 (RCA + 차트) */}
              {worstEntry && (worstEntry[1].alarm?.level ?? 0) > 0 && (
                <div
                  className="equipment-modal-section"
                  style={{ marginTop: "20px" }}
                >
                  <div className="equipment-modal-section-title">
                    상세 분석 —{" "}
                    {DOMAIN_LABELS[worstDomain!] ?? worstDomain}
                  </div>

                  {/* RCA 기여도 바 */}
                  {worstEntry[1].rca && worstEntry[1].rca.length > 0 && (
                    <div style={{ marginBottom: "16px" }}>
                      <div
                        style={{
                          fontSize: "11px",
                          color: "rgba(159,231,255,0.6)",
                          marginBottom: "8px",
                          fontWeight: 600,
                        }}
                      >
                        이상 기여 피처 Top {worstEntry[1].rca.length}
                      </div>
                      {worstEntry[1].rca.map((item) => (
                        <RcaBar
                          key={item.feature}
                          feature={item.feature}
                          contribution={item.contribution}
                        />
                      ))}
                    </div>
                  )}

                  {/* 센서 차트 5종 */}
                  {chartRows.length > 0 ? (
                    <div>
                      {chartRows.map((row) => (
                        <ChartRow
                          key={row.key}
                          chartEl={row.element}
                          description={row.description}
                        />
                      ))}
                    </div>
                  ) : (
                    <div
                      style={{
                        fontSize: "13px",
                        color: "rgba(225,243,255,0.4)",
                        textAlign: "center",
                        padding: "16px 0",
                      }}
                    >
                      센서 데이터 수신 대기 중...
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default AiAnalysisModal;
