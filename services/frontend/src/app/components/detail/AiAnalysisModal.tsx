import { useEffect, useMemo, useState } from "react";
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
  differential_pressure_kpa: "차압",
  pid_error_ec: "EC PID 오차",
  pid_error_ph: "pH PID 오차",
  flow_drop_rate: "유량 감소율",
  flow_trend_10: "유량 10분 추세",
  pressure_diff: "압력차",
  pressure_flow_ratio: "유량 대비 압력 비율",
  dp_per_flow: "차압 대비 유량",
  flow_per_power: "유량 대비 전력 효율",
  temp_slope_c_per_s: "온도 변화율",
  zone1_ec_accumulation: "구역1 EC 축적",
  zone1_moisture_response_pct: "구역1 수분 반응",
};

const LEVEL_COLORS: Record<number, string> = {
  0: "#4caf50",
  1: "#ffc107",
  2: "#ff9800",
  3: "#f44336",
};


const CW = 200;
const CH = 75;
const PAD = 8;
const IW = CW - PAD * 2;
const IH = CH - PAD * 2;

interface FeatureDetailItem {
  name: string;
  actual_value?: number;
  expected_value?: number;
  scaled_error?: number;
  feature_alarm?: {
    level?: number;
    label?: string;
  };
}

interface MetricSeries {
  trainLoss: number[];
  valLoss: number[];
  currentMse?: number;
}

function clampFinite(values: number[]): number[] {
  return values.filter((v) => Number.isFinite(v));
}

function defaultFmt(v: number): string {
  const abs = Math.abs(v);
  if (abs === 0) return "0";
  if (abs < 0.01) return v.toExponential(2);
  if (abs < 1) return v.toFixed(3);
  if (abs < 100) return v.toFixed(2);
  return v.toFixed(1);
}

interface LineChartProps {
  values: number[];
  color?: string;
  label: string;
  unit: string;
  refValues?: number[];
  refColor?: string;
  warningThreshold?: number;
  formatValue?: (v: number) => string;
}

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
      <div style={{ width: "100%" }}>
        <div className="ai-chart-label">{label}</div>
        <div className="ai-chart-empty">데이터 수집 중...</div>
        <div className="ai-chart-value" style={{ color }}>{lastValStr}</div>
      </div>
    );
  }

  const mn = Math.min(...allValid);
  const mx = Math.max(...allValid);
  const rng = mx - mn || 1;
  const toX = (i: number, len: number) => PAD + (len > 1 ? (i / (len - 1)) * IW : IW / 2);
  const toY = (v: number) => PAD + IH - ((v - mn) / rng) * IH;

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

  let lastFiniteIdx = -1;
  for (let i = values.length - 1; i >= 0; i -= 1) {
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

  const warnY = warningThreshold !== undefined ? toY(warningThreshold) : null;
  const pointsStr = (seg: Array<{ x: number; y: number }>) => seg.map((p) => `${p.x},${p.y}`).join(" ");

  return (
    <div style={{ width: "100%" }}>
      <div className="ai-chart-label">{label}</div>
      <svg
        viewBox={`0 0 ${CW} ${CH}`}
        width="100%"
        height={CH}
        preserveAspectRatio="none"
        style={{ display: "block" }}
      >
        <rect width={CW} height={CH} rx={6} fill="rgba(255,255,255,0.04)" />

        {/* 경고선 반영 */}
        {warnY !== null && (
          <line
            x1={PAD} y1={warnY} x2={CW - PAD} y2={warnY}
            stroke="rgba(255,152,0,0.55)" strokeWidth={1} strokeDasharray="4,3"
          />
        )}

        {/* 채움 영역 반영 */}
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

        {/* 실제 라인 반영 */}
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
            <circle key={`dot-${idx}`} cx={seg[0].x} cy={seg[0].y} r={1.5} fill={color} />
          ),
        )}

        {/* 기준선 반영 */}
        {refPts && (
          <polyline
            points={refPts}
            fill="none"
            stroke={refColor}
            strokeWidth={1}
            strokeDasharray="4,3"
          />
        )}

        {/* 마지막 값 강조 */}
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

function SpikeBadges({ spike }: { spike: SpikeInfo }) {
  if (!spike.is_spike && !spike.is_startup_spike && !spike.is_anomaly_spike) {
    return null;
  }

  return (
    <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginTop: "8px" }}>
      {spike.is_anomaly_spike && (
        <span className="ai-spike-badge ai-spike-badge--danger">⚡ 이상 스파이크</span>
      )}
      {spike.is_startup_spike && !spike.is_anomaly_spike && (
        <span className="ai-spike-badge ai-spike-badge--muted">기동 스파이크</span>
      )}
    </div>
  );
}

function safePct(v: number): number {
  if (!Number.isFinite(v)) return 0;
  return Math.max(0, Math.min(v, 100));
}

function pickRcaItems(report?: InferenceDomainReport | null) {
  if (!report) return [] as Array<{ feature: string; contribution: number }>;

  const fromRca = Array.isArray((report as { rca?: unknown }).rca)
    ? ((report as { rca?: Array<{ feature: string; contribution: number }> }).rca ?? [])
    : [];

  const fromTop3 = Array.isArray((report as { rca_top3?: unknown }).rca_top3)
    ? ((report as { rca_top3?: Array<{ feature: string; contribution: number }> }).rca_top3 ?? [])
    : [];

  const list = fromRca.length > 0 ? fromRca : fromTop3;

  return list
    .filter((item) => item && typeof item.feature === "string" && Number.isFinite(item.contribution))
    .sort((a, b) => b.contribution - a.contribution);
}

function pickFeatureDetails(report?: InferenceDomainReport | null): FeatureDetailItem[] {
  const raw = (report as { feature_details?: unknown } | undefined)?.feature_details;
  if (!Array.isArray(raw)) return [];

  return raw
    .filter((item): item is FeatureDetailItem => {
      if (!item || typeof item !== "object") return false;
      const feature = item as FeatureDetailItem;
      return typeof feature.name === "string";
    })
    .sort((a, b) => {
      const aScore = Math.abs(a.scaled_error ?? 0);
      const bScore = Math.abs(b.scaled_error ?? 0);
      return bScore - aScore;
    });
}

function pickMetrics(report?: InferenceDomainReport | null): MetricSeries {
  const metrics = (report as { metrics?: unknown } | undefined)?.metrics;
  if (!metrics || typeof metrics !== "object") {
    return { trainLoss: [], valLoss: [] };
  }

  const typed = metrics as {
    train_loss?: unknown;
    val_loss?: unknown;
    current_mse?: unknown;
  };

  return {
    trainLoss: Array.isArray(typed.train_loss)
      ? typed.train_loss.filter((v): v is number => typeof v === "number" && Number.isFinite(v))
      : [],
    valLoss: Array.isArray(typed.val_loss)
      ? typed.val_loss.filter((v): v is number => typeof v === "number" && Number.isFinite(v))
      : [],
    currentMse: typeof typed.current_mse === "number" && Number.isFinite(typed.current_mse)
      ? typed.current_mse
      : undefined,
  };
}

function getDomainLabel(domainKey: string) {
  return DOMAIN_LABELS[domainKey] ?? domainKey;
}

function getFeatureLabel(featureKey: string) {
  return FEATURE_LABELS[featureKey] ?? featureKey;
}

function toProblemLabel(featureKey: string, contribution: number) {
  const label = getFeatureLabel(featureKey);
  return `${label} 영향 증가 (${safePct(contribution).toFixed(1)}%)`;
}

function formatMetricShort(v?: number) {
  if (v === undefined || !Number.isFinite(v)) return "—";
  return defaultFmt(v);
}

function buildShapRows(report?: InferenceDomainReport | null) {
  const detailList = pickFeatureDetails(report);
  const rcaList = pickRcaItems(report);
  const rcaMap = new Map(rcaList.map((item) => [item.feature, item.contribution]));

  const baseRows = detailList.slice(0, 5).map((item) => {
    const detailMagnitude = Math.abs(item.scaled_error ?? 0);
    const contributionMagnitude = rcaMap.get(item.name) ?? 0;

    return {
      feature: item.name,
      label: getFeatureLabel(item.name),
      magnitude: detailMagnitude,
      contribution: contributionMagnitude,
      actual: item.actual_value,
      expected: item.expected_value,
      alarmLevel: item.feature_alarm?.level ?? 0,
    };
  });

  if (baseRows.length > 0) {
    const maxMagnitude = Math.max(...baseRows.map((row) => row.magnitude), 1);

    return baseRows.map((row, index) => {
      const direction = index % 2 === 0 ? 1 : -1;
      return {
        ...row,
        offset: (row.magnitude / maxMagnitude) * 46 * direction,
      };
    });
  }

  const fallbackRows = rcaList.slice(0, 5).map((item, index) => ({
    feature: item.feature,
    label: getFeatureLabel(item.feature),
    magnitude: item.contribution,
    contribution: item.contribution,
    actual: undefined,
    expected: undefined,
    alarmLevel: 0,
    offset: (safePct(item.contribution) / 100) * 46 * (index % 2 === 0 ? 1 : -1),
  }));

  return fallbackRows;
}

function CauseDiagnosisSection({
  domainKey,
  report,
}: {
  domainKey: string | null;
  report: InferenceDomainReport | null;
}) {
  const rcaList = pickRcaItems(report);
  const featureImportanceRows = rcaList.slice(0, 5);
  const top3 = rcaList.slice(0, 3);
  const shapRows = buildShapRows(report).slice(0, 5);
  const level = report?.alarm?.level ?? 0;
  const domainLabel = domainKey ? getDomainLabel(domainKey) : "";

  return (
    <div className="equipment-modal-section">
      <div className="equipment-modal-section-title">
        원인진단
        {domainLabel && (
          <span className="ai-diag-domain-label">— {domainLabel}</span>
        )}
      </div>

      <div className="ai-diag-grid">
        <div className="ai-diag-panel">
          <div className="ai-diag-subtitle">Feature Importance</div>
          {featureImportanceRows.length > 0 ? (
            featureImportanceRows.map((item) => {
              const pct = safePct(item.contribution);
              return (
                <div className="ai-diag-feature-row" key={item.feature}>
                  <span className="ai-diag-feature-label" title={getFeatureLabel(item.feature)}>
                    {getFeatureLabel(item.feature)}
                  </span>
                  <div className="ai-diag-feature-bar-wrap">
                    <div className="ai-diag-feature-bar" style={{ width: `${pct}%` }} />
                  </div>
                  <span className="ai-diag-feature-pct">{pct.toFixed(0)}%</span>
                </div>
              );
            })
          ) : (
            <div className="ai-modal-placeholder">
              {level === 0 ? "이상 징후 없음" : "표시할 기여도 데이터 없음"}
            </div>
          )}
        </div>

        <div className="ai-diag-panel">
          <div className="ai-diag-subtitle">SHAP</div>
          {shapRows.length > 0 ? (
            <div className="ai-shap-list">
              {shapRows.map((item) => {
                const badgeColor = LEVEL_COLORS[item.alarmLevel] ?? "#9fe7ff";
                const actualText = formatMetricShort(item.actual);
                const expectedText = formatMetricShort(item.expected);

                return (
                  <div className="ai-shap-row" key={item.feature}>
                    <div className="ai-shap-header">
                      <span className="ai-shap-label" title={item.label}>{item.label}</span>
                      <span className="ai-shap-meta">
                        실제 {actualText} / 예측 {expectedText}
                      </span>
                    </div>

                    <div className="ai-shap-track">
                      <div className="ai-shap-axis" />
                      <div
                        className="ai-shap-node"
                        style={{
                          left: `calc(50% + ${item.offset.toFixed(1)}%)`,
                          background: badgeColor,
                          boxShadow: `0 0 10px ${badgeColor}55`,
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="ai-modal-placeholder">
              {level === 0 ? "이상 징후 없음" : "표시할 SHAP 데이터 없음"}
            </div>
          )}
        </div>
      </div>

      <div className="ai-diag-subtitle">Top-3 문제현상</div>
      {top3.length > 0 ? (
        <ol className="ai-top3-list">
          {top3.map((item, index) => (
            <li className="ai-top3-item" key={item.feature}>
              <span className="ai-top3-rank">{index + 1}</span>
              <span className="ai-top3-feature">{toProblemLabel(item.feature, item.contribution)}</span>
              <span className="ai-top3-pct">{safePct(item.contribution).toFixed(1)}%</span>
            </li>
          ))}
        </ol>
      ) : (
        <div className="ai-modal-placeholder">
          {level === 0 ? "이상 징후 없음" : "표시할 문제현상 데이터 없음"}
        </div>
      )}
    </div>
  );
}

function DomainTabs({
  selectedDomain,
  domainKeys,
  onSelect,
}: {
  selectedDomain: string | null;
  domainKeys: string[];
  onSelect: (domainKey: string) => void;
}) {
  if (domainKeys.length === 0) {
    return null;
  }

  return (
    <div className="ai-domain-tabs">
      {domainKeys.map((domainKey) => (
        <button
          key={domainKey}
          type="button"
          className={`ai-domain-tab ${selectedDomain === domainKey ? "is-active" : ""}`}
          onClick={() => onSelect(domainKey)}
        >
          {getDomainLabel(domainKey)}
        </button>
      ))}
    </div>
  );
}

function ChartRow({
  chartEl,
  description,
}: {
  chartEl: React.ReactNode;
  description: string;
}) {
  return (
    <div className="ai-chart-row">
      <div className="ai-chart-200px">{chartEl}</div>
      <div className="ai-chart-desc">
        {description.split("\n").map((line, i) => (
          <div key={i} style={{ lineHeight: 1.5 }}>
            <span style={{ fontWeight: i === 0 ? 600 : 400, fontSize: i === 0 ? "inherit" : "11px", color: i === 0 ? "rgba(220,242,255,0.8)" : "rgba(220,242,255,0.5)" }}>{line}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

const CMP_MIN_DENOM_FLOW = 1;
const CMP_MIN_DENOM_POWER = 0.05;
const CMP_WIN_SHORT = 5;
const SHORT_SERIES_POINTS = 60;
const CMP_MIN_SAMPLES = 30;
const LONG_SERIES_POINTS = 72;

function stdOf(arr: number[]): number {
  if (arr.length < 2) return NaN;
  const m = arr.reduce((a, b) => a + b, 0) / arr.length;
  return Math.sqrt(arr.reduce((s, v) => s + (v - m) ** 2, 0) / arr.length);
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

  const pressureFlowRatio: number[] = [];
  const dpPerFlow: number[] = [];
  const flowPerPower: number[] = [];
  const pVolSeries: number[] = [];
  const fCvSeries: number[] = [];
  const tempSlope: number[] = [];

  if (chartSnapshot && n > 0) {
    const { pressure, suction, flow, motor_power, motor_temp, ts } = chartSnapshot;

    const shortStart = Math.max(0, n - SHORT_SERIES_POINTS);
    const longStart = Math.max(0, n - LONG_SERIES_POINTS);

    for (let i = shortStart; i < n; i += 1) {
      const dp = pressure[i];
      const sp = suction[i];
      const fl = flow[i];
      const pw = motor_power[i];

      pressureFlowRatio.push(
        Number.isFinite(dp) && Number.isFinite(fl) && fl >= CMP_MIN_DENOM_FLOW ? dp / fl : NaN,
      );
      dpPerFlow.push(
        Number.isFinite(dp) && Number.isFinite(sp) && Number.isFinite(fl) && fl >= CMP_MIN_DENOM_FLOW
          ? (dp - sp) / fl
          : NaN,
      );
      flowPerPower.push(
        Number.isFinite(fl) && Number.isFinite(pw) && pw >= CMP_MIN_DENOM_POWER ? fl / pw : NaN,
      );

      if (i === shortStart) {
        tempSlope.push(NaN);
      } else {
        const dT = motor_temp[i] - motor_temp[i - 1];
        const dt = (ts[i] - ts[i - 1]) / 1000;
        tempSlope.push(Number.isFinite(dT) && Number.isFinite(dt) && dt > 0 ? dT / dt : NaN);
      }
    }

    for (let i = longStart; i < n; i += 1) {
      const winStart = Math.max(longStart, i - CMP_WIN_SHORT + 1);
      const winP: number[] = [];
      const winF: number[] = [];

      for (let j = winStart; j <= i; j += 1) {
        if (Number.isFinite(pressure[j])) winP.push(pressure[j]);
        if (Number.isFinite(flow[j])) winF.push(flow[j]);
      }

      const flowMean = meanOf(winF);
      const flowStd = stdOf(winF);
      const pressureStd = stdOf(winP);
      const pressureIqr = winP.length >= 4
        ? [...winP].sort((a, b) => a - b)[Math.floor(winP.length * 0.75)] - [...winP].sort((a, b) => a - b)[Math.floor(winP.length * 0.25)]
        : NaN;

      pVolSeries.push(
        Number.isFinite(pressureStd) && Number.isFinite(pressureIqr) && pressureIqr > 0
          ? pressureStd / pressureIqr
          : NaN,
      );

      fCvSeries.push(
        Number.isFinite(flowStd) && Number.isFinite(flowMean) && flowMean > 0
          ? flowStd / flowMean
          : NaN,
      );
    }
  }

  const samples = comparative?.samples ?? 0;
  const pVol12h = comparative?.pressureVolatility;
  const fCv12h = comparative?.flowCv;
  const aggReady = samples >= CMP_MIN_SAMPLES;
  const fmtAgg = (v: number | null | undefined) =>
    v == null || !Number.isFinite(v) ? "—" : v.toFixed(3);

  const charts = [
    {
      key: "p_over_f",
      label: "유량 대비 압력 비율",
      unit: "kPa·min/L",
      series: pressureFlowRatio,
      color: "#9fe7ff",
      description: "배관 저항 지표",
    },
    {
      key: "dp_over_f",
      label: "차압 대비 유량",
      unit: "kPa·min/L",
      series: dpPerFlow,
      color: "#3eb8ff",
      description: "에너지 대비 유량",
    },
    {
      key: "f_over_p",
      label: "유량 대비 전력 효율",
      unit: "L/min/kW",
      series: flowPerPower,
      color: "#4caf50",
      description: "펌프 효율",
    },
    {
      key: "p_vol",
      label: "압력 변동성",
      unit: "kPa",
      series: pVolSeries,
      color: "#ff9800",
      description: `현재 12시간 값 ${aggReady ? fmtAgg(pVol12h) : `수집 중 ${samples}/${CMP_MIN_SAMPLES}`}`,
    },
    {
      key: "f_cv",
      label: "유량 변동성",
      unit: "",
      series: fCvSeries,
      color: "#ffc107",
      description: `현재 12시간 값 ${aggReady ? fmtAgg(fCv12h) : `수집 중 ${samples}/${CMP_MIN_SAMPLES}`}`,
    },
    {
      key: "temp_slope",
      label: "초당 시간 대비 온도 변화율",
      unit: "°C/s",
      series: tempSlope,
      color: "#f44336",
      description: "",
    },
  ];

  return (
    <div className="equipment-modal-section">
      <div className="equipment-modal-section-title">비교분석</div>
      {charts.map((chart) => (
        <ChartRow
          key={chart.key}
          chartEl={<MiniLineChart values={chart.series} label={chart.label} unit={chart.unit} color={chart.color} />}
          description={chart.description}
        />
      ))}
    </div>
  );
}

function ModelPerformanceSection({
  domainKey,
  report,
}: {
  domainKey: string | null;
  report: InferenceDomainReport | null;
}) {
  const metrics = pickMetrics(report);
  const domainLabel = domainKey ? getDomainLabel(domainKey) : "";
  const hasData = metrics.trainLoss.length > 0 || metrics.valLoss.length > 0 || metrics.currentMse !== undefined;

  return (
    <div className="equipment-modal-section" style={{ marginTop: "20px" }}>
      <div className="equipment-modal-section-title">
        AI 모델 성능 결과
        {domainLabel && <span className="ai-diag-domain-label">— {domainLabel}</span>}
      </div>

      {hasData ? (
        <>
          <div className="ai-perf-grid">
            <div className="ai-perf-row">
              <span className="ai-perf-label">Current MSE</span>
              <span className="ai-perf-value">{formatMetricShort(metrics.currentMse)}</span>
            </div>
            <div className="ai-perf-row">
              <span className="ai-perf-label">Train Loss Count</span>
              <span className="ai-perf-value">{metrics.trainLoss.length}</span>
            </div>
            <div className="ai-perf-row">
              <span className="ai-perf-label">Val Loss Count</span>
              <span className="ai-perf-value">{metrics.valLoss.length}</span>
            </div>
          </div>

          <div className="ai-perf-chart-grid">
            <MiniLineChart values={metrics.trainLoss} label="Train Loss" unit="" color="#4caf50" />
            <MiniLineChart values={metrics.valLoss} label="Validation Loss" unit="" color="#3eb8ff" />
          </div>
        </>
      ) : (
        <div className="ai-modal-placeholder">표시할 모델 성능 데이터 없음</div>
      )}
    </div>
  );
}

function AiAnalysisModal({
  open,
  onClose,
  inference,
  chartSnapshot,
  comparativeMetrics,
}: AiAnalysisModalProps) {
  const domainKeys = useMemo(() => {
    const reports = inference?.domain_reports ?? {};
    return Object.keys(reports).filter((key) => reports[key]);
  }, [inference]);

  const [selectedDomain, setSelectedDomain] = useState<string | null>(null);

  // 현재 응답에 있는 도메인 기준 선택 유지
  useEffect(() => {
    if (!inference) {
      setSelectedDomain(null);
      return;
    }

    setSelectedDomain((prev) => {
      if (prev && domainKeys.includes(prev)) return prev;
      return domainKeys[0] ?? null;
    });
  }, [inference, domainKeys]);

  if (!open) return null;

  const hasData = inference != null;
  const selectedReport = selectedDomain ? (inference?.domain_reports?.[selectedDomain] ?? null) : null;

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
      <div className="equipment-modal equipment-modal--xwide" onClick={(e) => e.stopPropagation()}>
        <div className="equipment-modal-header">
          <div>
            <div className="equipment-modal-title">AI 분석 결과</div>
            <div className="equipment-modal-subtitle">{tsDisplay ?? "AI 기반 설비 이상 분석"}</div>
          </div>
          <button className="equipment-modal-close" onClick={onClose}>×</button>
        </div>

        <div className="equipment-modal-body">
          {!hasData && (
            <div style={{ textAlign: "center", padding: "40px 0", color: "rgba(225,243,255,0.4)", fontSize: "14px" }}>
              추론 데이터 수신 대기 중...
            </div>
          )}

          {hasData && (
            <>
              {/* <div
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
                  <div style={{ fontSize: "12px", color: "rgba(220,242,255,0.6)", marginBottom: "4px" }}>
                    전체 시스템 상태
                  </div>
                  <div style={{ fontSize: "22px", fontWeight: 700, color: overallColor }}>
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
              </div> */}

              {inference.spike_info && <SpikeBadges spike={inference.spike_info} />}

              <div className="ai-modal-grid">
                <div className="ai-modal-col">
                  <ComparativeSection chartSnapshot={chartSnapshot} comparative={comparativeMetrics} />
                </div>

                <div className="ai-modal-col">
                  {/* 선택 도메인 반영 */}
                  <DomainTabs
                    selectedDomain={selectedDomain}
                    domainKeys={domainKeys}
                    onSelect={setSelectedDomain}
                  />

                  <CauseDiagnosisSection domainKey={selectedDomain} report={selectedReport} />
                  <ModelPerformanceSection domainKey={selectedDomain} report={selectedReport} />
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
