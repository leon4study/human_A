import type { CtpVisualizationMetric } from "../types/dashboard";

export const ctpVisualizationData: CtpVisualizationMetric[] = [
  {
    id: "pump-discharge-flow",
    label: "펌프 토출 유량",
    // 실제 RAW 수신 전까지 값 미표시
    value: Number.NaN,
    unit: "L/min",
    direction: "low",
    // 유량은 낮아질수록 위험
    thresholdMode: "low",
    // threshold는 inference payload에서 직접 수신
    caution: Number.NaN,
    warning: Number.NaN,
    critical: Number.NaN,
    // trend는 CTP 시각화 12시간 값 시계열
    // 초기 seed 제거, 실제 버퍼 누적 뒤 반영
    trend: [],
    timestamps: [],
    thresholdSource: "hydraulic.feature_details.flow_rate_l_min.bands",
  },
  {
    id: "pump-discharge-pressure",
    label: "펌프 토출 압력",
    value: Number.NaN,
    unit: "kPa",
    direction: "high",
    // 압력은 높아질수록 위험
    thresholdMode: "high",
    caution: Number.NaN,
    warning: Number.NaN,
    critical: Number.NaN,
    trend: [],
    timestamps: [],
    thresholdSource: "hydraulic.target_reference_profiles.differential_pressure_kpa.related_feature_lines.discharge_pressure_kpa",
  },
  {
    id: "motor-current",
    label: "모터 소비 전류",
    value: Number.NaN,
    unit: "A",
    direction: "high",
    // 전류는 upper/lower 범위를 둘 다 확인
    thresholdMode: "range",
    caution: Number.NaN,
    warning: Number.NaN,
    critical: Number.NaN,
    cautionLower: Number.NaN,
    warningLower: Number.NaN,
    criticalLower: Number.NaN,
    trend: [],
    timestamps: [],
    thresholdSource: "motor.target_reference_profiles.motor_current_a.target_lines",
  },
  {
    id: "mix-ec",
    label: "조제 현재 EC",
    value: Number.NaN,
    unit: "dS/m",
    direction: "high",
    // EC는 pid_error_ec related 기준을 빌려와 range로 판단
    thresholdMode: "range",
    caution: Number.NaN,
    warning: Number.NaN,
    critical: Number.NaN,
    cautionLower: Number.NaN,
    warningLower: Number.NaN,
    criticalLower: Number.NaN,
    trend: [],
    timestamps: [],
    thresholdSource: "nutrient.target_reference_profiles.pid_error_ec.related_feature_lines.mix_ec_ds_m",
  },
];
