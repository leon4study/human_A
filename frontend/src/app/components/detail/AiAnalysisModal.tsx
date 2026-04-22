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
const PAD = 8; // 안쪽 여백
const IW = CW - PAD * 2; // 실제 내부 너비 = 전체너비 - 양쪽 여백 합
const IH = CH - PAD * 2; // 실제 내부 높이 = 전체높이 - 양쪽 여백 합

// 정상 숫자만 걸러내는 전처리 함수
function clampFinite(values: number[]): number[] {
  return values.filter((v) => Number.isFinite(v));
}

// 간단한 라인 차트 컴포넌트 — NaN 구간에서 선 끊김, 최신값 강조, 목표선 옵션, 경고선 옵션, 자동 포맷팅
interface LineChartProps {
  values: number[]; // 차트 데이터 값 배열
  color?: string; // 차트 색상
  label: string; // 차트 이름
  unit: string; // 값의 단위
  refValues?: number[];  // 목표선 (예: target_ec)
  refColor?: string; // 기준선 색상
  warningThreshold?: number; // 경고 임계값
  formatValue?: (v: number) => string; // 값 포맷터 (기본: 자동 단위 변환)
}

// 숫자를 문자열로 반환 (자동 단위 변환 포함)
function defaultFmt(v: number): string {
  const abs = Math.abs(v);
  if (abs === 0) return "0";
  if (abs < 0.01) return v.toExponential(2);
  if (abs < 1) return v.toFixed(3);
  if (abs < 100) return v.toFixed(2);
  return v.toFixed(1);
}

// 
function MiniLineChart({
  values,
  color = "#3eb8ff",
  label,
  unit,
  refValues,
  refColor = "rgba(255,200,0,0.7)",
  warningThreshold,
  formatValue,
}: LineChartProps) {
  const valid = clampFinite(values);
  const refValid = refValues ? clampFinite(refValues) : [];
  const allValid = [...valid, ...refValid];

  const fmt = formatValue ?? defaultFmt;
  const lastVal = valid[valid.length - 1];
  const lastValStr =
    lastVal !== undefined
      ? `${fmt(lastVal)}${unit ? ` ${unit}` : ""}`
      : "—";

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
  const toX = (i: number, len: number) =>
    PAD + (len > 1 ? (i / (len - 1)) * IW : IW / 2);
  const toY = (v: number) => PAD + IH - ((v - mn) / rng) * IH;

  // NaN 구간에서 선을 끊는다 (연속된 유한값 구간만 폴리라인으로 묶음)
  const segments: Array<Array<{ x: number; y: number }>> = [];
  let cur: Array<{ x: number; y: number }> = [];
  values.forEach((v, i) => {
    if (Number.isFinite(v)) {
      cur.push({ x: toX(i, values.length), y: toY(v) });
    } else if (cur.length > 0) {
      segments.push(cur);
      cur = [];
    }
  });
  if (cur.length > 0) segments.push(cur);

  // 마지막 유한값의 실제 인덱스 (끝이 NaN일 때 원 위치 보정)
  let lastFiniteIdx = -1;
  for (let i = values.length - 1; i >= 0; i--) {
    if (Number.isFinite(values[i])) {
      lastFiniteIdx = i;
      break;
    }
  }

  const refPts =
    refValues && refValues.length >= 2
      ? refValues
          .map((v, i) =>
            Number.isFinite(v)
              ? `${toX(i, refValues.length)},${toY(v)}`
              : null,
          )
          .filter((s): s is string => s !== null)
          .join(" ")
      : null;

  const warnY =
    warningThreshold !== undefined ? toY(warningThreshold) : null;

  const pointsStr = (seg: Array<{ x: number; y: number }>) =>
    seg.map((p) => `${p.x},${p.y}`).join(" ");

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

        {/* 영역 채우기 — 구간별 */}
        {segments.map((seg, idx) =>
          seg.length >= 2 ? (
            <polyline
              key={`area-${idx}`}
              points={`${seg[0].x},${CH - PAD} ${pointsStr(seg)} ${seg[seg.length - 1].x},${CH - PAD}`}
              fill={`${color}18`}
              stroke="none"
            />
          ) : null,
        )}

        {/* 메인 라인 — 구간별 (고립된 1점 구간은 작은 점으로) */}
        {segments.map((seg, idx) =>
          seg.length >= 2 ? (
            <polyline
              key={`line-${idx}`}
              points={pointsStr(seg)}
              fill="none"
              stroke={color}
              strokeWidth={1.5}
              strokeLinejoin="round"
            />
          ) : (
            <circle
              key={`dot-${idx}`}
              cx={seg[0].x}
              cy={seg[0].y}
              r={1.5}
              fill={color}
            />
          ),
        )}

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

        {/* 마지막 유한 포인트 */}
        {lastFiniteIdx >= 0 && (
          <circle
            cx={toX(lastFiniteIdx, values.length)}
            cy={toY(values[lastFiniteIdx])}
            r={3}
            fill={color}
          />
        )}
      </svg>
      <div className="ai-chart-value" style={{ color }}>{lastValStr}</div>
    </div>
  );
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

// contribution(%) 을 CSS width 로 안전 변환: NaN/음수/>100 방어
function safePct(v: number): number {
  if (!Number.isFinite(v)) return 0;
  return Math.max(0, Math.min(v, 100));
}

// 원인진단 섹션 — 스케치 레이아웃: 상단(FIP | SHAP) + 하단(Top-3 문제점)
function CauseDiagnosisSection({
  worstEntry,
}: {
  worstEntry: [string, InferenceDomainReport] | null;
}) {
  const level = worstEntry?.[1]?.alarm?.level ?? 0;
  const rca = worstEntry?.[1]?.rca ?? [];
  // 이상 레벨이 0이거나 RCA가 없으면 "원인"이 없는 것으로 본다
  const hasRca = level > 0 && rca.length > 0;
  const topFeatures = rca.slice(0, 4);
  const top3 = rca.slice(0, 3);
  const domainLabel = worstEntry
    ? DOMAIN_LABELS[worstEntry[0]] ?? worstEntry[0]
    : "";

  return (
    <div className="equipment-modal-section">
      <div className="equipment-modal-section-title">
        원인진단
        {hasRca && domainLabel && (
          <span
            style={{
              marginLeft: "8px",
              fontSize: "11px",
              fontWeight: 600,
              color: "rgba(159,231,255,0.55)",
            }}
          >
            — {domainLabel}
          </span>
        )}
      </div>

      {/* 상단: Feature Importance | SHAP 값 분포 */}
      <div className="ai-diag-grid">
        <div className="ai-diag-panel">
          <div className="ai-diag-subtitle">Feature Importance (FIP)</div>
          {hasRca ? (
            topFeatures.map((item) => {
              const label = FEATURE_LABELS[item.feature] ?? item.feature;
              const pct = safePct(item.contribution);
              return (
                <div className="ai-diag-feature-row" key={item.feature}>
                  <span className="ai-diag-feature-label" title={label}>
                    {label}
                  </span>
                  <div className="ai-diag-feature-bar-wrap">
                    <div
                      className="ai-diag-feature-bar"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="ai-diag-feature-pct">{pct.toFixed(0)}%</span>
                </div>
              );
            })
          ) : (
            <div className="ai-modal-placeholder">
              {level === 0 ? "이상 징후 없음" : "데이터 수집 중"}
            </div>
          )}
        </div>

        <div className="ai-diag-panel">
          <div className="ai-diag-subtitle">SHAP 값 분포</div>
          {hasRca ? (
            topFeatures.map((item) => {
              const label = FEATURE_LABELS[item.feature] ?? item.feature;
              return (
                <div className="ai-diag-feature-row" key={item.feature}>
                  <span className="ai-diag-feature-label" title={label}>
                    {label}
                  </span>
                  <div
                    className="ai-diag-shap-empty"
                    title="데이터 연동 예정"
                  />
                </div>
              );
            })
          ) : (
            <div className="ai-modal-placeholder">데이터 연동 예정</div>
          )}
        </div>
      </div>

      {/* 하단: Top-3 문제점 */}
      <div className="ai-diag-subtitle">Top-3 문제점</div>
      {hasRca ? (
        <ol className="ai-top3-list">
          {top3.map((item, i) => {
            const label = FEATURE_LABELS[item.feature] ?? item.feature;
            const pct = safePct(item.contribution);
            return (
              <li className="ai-top3-item" key={item.feature}>
                <span className="ai-top3-rank">{i + 1}</span>
                <span className="ai-top3-feature">{label}</span>
                <span className="ai-top3-pct">{pct.toFixed(1)}%</span>
              </li>
            );
          })}
        </ol>
      ) : (
        <div className="ai-modal-placeholder">
          {level === 0 ? "이상 징후 없음" : "데이터 수집 중"}
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

const CMP_MIN_DENOM_FLOW = 1;      // L/min — 이보다 작으면 비율 무의미 (펌프 정지 구간 제외)
const CMP_MIN_DENOM_POWER = 0.05;  // kW — 저전력 구간 비율 불안정
const CMP_WIN = 5;                 // 최근 변동성 윈도우 (포인트 수)
const CMP_MIN_SAMPLES = 30;        // 12h 통계 유효 샘플 수

function stdOf(arr: number[]): number {
  if (arr.length < 2) return NaN;
  const m = arr.reduce((a, b) => a + b, 0) / arr.length;
  return Math.sqrt(
    arr.reduce((s, v) => s + (v - m) ** 2, 0) / arr.length,
  );
}

function meanOf(arr: number[]): number {
  if (arr.length === 0) return NaN;
  return arr.reduce((a, b) => a + b, 0) / arr.length;
}

function ComparativeSection({
  chartSnapshot,
  comparative,
}: {
  chartSnapshot?: ChartBuffer | null;
  comparative?: ComparativeMetrics | null;
}) {
  const n = chartSnapshot?.ts?.length ?? 0;

  // 포인트별 파생 시계열 생성
  const pressureFlowRatio: number[] = [];
  const dpPerFlow: number[] = [];
  const flowPerPower: number[] = [];
  const pVolSeries: number[] = []; // 최근 압력 std
  const fCvSeries: number[] = [];  // 최근 유량 CV
  const tempSlope: number[] = [];  // °C/s

  if (chartSnapshot && n > 0) {
    const { pressure, suction, flow, motor_power, motor_temp, ts } = chartSnapshot;

    for (let i = 0; i < n; i++) {
      const dp = pressure[i];
      const sp = suction[i];
      const fl = flow[i];
      const pw = motor_power[i];

      pressureFlowRatio.push(
        Number.isFinite(dp) && Number.isFinite(fl) && fl >= CMP_MIN_DENOM_FLOW
          ? dp / fl
          : NaN,
      );
      dpPerFlow.push(
        Number.isFinite(dp) &&
          Number.isFinite(sp) &&
          Number.isFinite(fl) &&
          fl >= CMP_MIN_DENOM_FLOW
          ? (dp - sp) / fl
          : NaN,
      );
      flowPerPower.push(
        Number.isFinite(fl) && Number.isFinite(pw) && pw >= CMP_MIN_DENOM_POWER
          ? fl / pw
          : NaN,
      );

      // 롤링 윈도우 변동성 (최근 CMP_WIN 포인트 중 유한값만 사용)
      const winStart = Math.max(0, i - CMP_WIN + 1);
      const winP: number[] = [];
      const winF: number[] = [];
      for (let j = winStart; j <= i; j++) {
        if (Number.isFinite(pressure[j])) winP.push(pressure[j]);
        if (Number.isFinite(flow[j])) winF.push(flow[j]);
      }
      pVolSeries.push(winP.length >= 2 ? stdOf(winP) : NaN);
      const mF = meanOf(winF);
      fCvSeries.push(
        winF.length >= 2 && Number.isFinite(mF) && mF > 0
          ? stdOf(winF) / mF
          : NaN,
      );

      // 온도 변화율 (i=0은 이전 포인트 없음)
      if (i === 0) {
        tempSlope.push(NaN);
      } else {
        const dT = motor_temp[i] - motor_temp[i - 1];
        const dt = (ts[i] - ts[i - 1]) / 1000;
        tempSlope.push(
          Number.isFinite(dT) && Number.isFinite(dt) && dt > 0
            ? dT / dt
            : NaN,
        );
      }
    }
  }

  const samples = comparative?.samples ?? 0;
  const pVol12h = comparative?.pressureVolatility;
  const fCv12h = comparative?.flowCv;
  const aggReady = samples >= CMP_MIN_SAMPLES;
  const fmtAgg = (v: number | null | undefined) =>
    v == null || !Number.isFinite(v) ? "—" : v.toFixed(3);

  interface CmpChart {
    key: string;
    label: string;
    unit: string;
    series: number[];
    color: string;
    description: string;
  }

  const charts: CmpChart[] = [
    {
      key: "p_over_f",
      label: "유량 대비 압력 비율",
      unit: "kPa·min/L",
      series: pressureFlowRatio,
      color: "#9fe7ff",
      description: "discharge / flow\n배관 저항 지표",
    },
    {
      key: "dp_over_f",
      label: "차압 대비 유량",
      unit: "kPa·min/L",
      series: dpPerFlow,
      color: "#3eb8ff",
      description: "(discharge − suction) / flow\n막힘·누수 조기감지",
    },
    {
      key: "f_over_p",
      label: "유량 대비 전력 효율",
      unit: "L/min/kW",
      series: flowPerPower,
      color: "#4caf50",
      description: "flow / motor_power\n펌프 효율 추이",
    },
    {
      key: "p_vol",
      label: "압력 변동성 (최근)",
      unit: "kPa",
      series: pVolSeries,
      color: "#ff9800",
      description: `rolling std, win=${CMP_WIN}\n12h 값: ${aggReady ? fmtAgg(pVol12h) : `수집 중 ${samples}/${CMP_MIN_SAMPLES}`}`,
    },
    {
      key: "f_cv",
      label: "유량 변동성 (최근)",
      unit: "",
      series: fCvSeries,
      color: "#ffc107",
      description: `rolling CV, win=${CMP_WIN}\n12h 값: ${aggReady ? fmtAgg(fCv12h) : `수집 중 ${samples}/${CMP_MIN_SAMPLES}`}`,
    },
    {
      key: "temp_slope",
      label: "온도 변화율",
      unit: "°C/s",
      series: tempSlope,
      color: "#f44336",
      description: "diff(motor_temp) / dt\n발열 추이",
    },
  ];

  return (
    <div className="equipment-modal-section">
      <div className="equipment-modal-section-title">비교분석</div>
      {charts.map((c) => (
        <ChartRow
          key={c.key}
          chartEl={
            <MiniLineChart
              values={c.series}
              label={c.label}
              unit={c.unit}
              color={c.color}
            />
          }
          description={c.description}
        />
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
        className="equipment-modal equipment-modal--xwide"
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
              {/* 전체 상태 배너 (전체 폭) */}
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
                      maxWidth: "240px",
                      lineHeight: 1.5,
                    }}
                  >
                    {inference.action_required}
                  </div>
                )}
              </div>

              {/* 스파이크 배지 (전체 폭) */}
              {inference.spike_info && (
                <SpikeBadges spike={inference.spike_info} />
              )}

              {/* 2열 그리드: 좌=비교분석, 우=원인진단+AI모델성능 */}
              <div className="ai-modal-grid">
                {/* ── 좌측: 비교분석 ─────────────────── */}
                <div className="ai-modal-col">
                  <ComparativeSection
                    chartSnapshot={chartSnapshot}
                    comparative={comparativeMetrics}
                  />
                </div>

                {/* ── 우측: 원인진단 + AI 모델 성능 결과 ── */}
                <div className="ai-modal-col">
                  <CauseDiagnosisSection worstEntry={worstEntry} />

                  {/* AI 모델 성능 결과 (placeholder — 데이터 연동 예정) */}
                  <div
                    className="equipment-modal-section"
                    style={{ marginTop: "20px" }}
                  >
                    <div className="equipment-modal-section-title">
                      AI 모델 성능 결과
                    </div>
                    <div className="ai-modal-placeholder">
                      데이터 연동 예정
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default AiAnalysisModal;
