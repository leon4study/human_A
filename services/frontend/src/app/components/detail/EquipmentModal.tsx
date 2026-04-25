import type { ChartBuffer } from "../../hooks/useDashboardSocket";
import type { Equipment } from "../center/facility/model/facility.types";
import type { RawSensorPayload } from "../../types/dashboard";
import "./equipment-modal.css";

interface EquipmentModalProps {
  equipment: Equipment | null;
  sensorPayload?: RawSensorPayload | null;
  chartSnapshot?: ChartBuffer | null;
  onClose: () => void;
}

interface SensorRow {
  label: string;
  value: string;
}

interface TrendCard {
  title: string;
  unit: string;
  values: number[];
}

// 그래프 좌표 타입
interface ChartPoint {
  x: number;
  y: number;
  value: number;
}

// critical을 넘는 구간 정보를 담는 인터페이스
interface Segment {
  polygonPoints: string;
  linePath: string;
}

const CHART_WIDTH = 260;
const CHART_HEIGHT = 92;
const CHART_PADDING = 8;
function fmt(value: unknown, decimals = 1): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(decimals) : "—";
}


function finiteValues(values: number[]) {
  return values.filter((value) => Number.isFinite(value));
}

function takeRecent(values: number[], count = 12) {
  return values.slice(-count);
}

// 필터 차압 계산
function computeFilterDiff(inlet: number[], outlet: number[]) {
  const length = Math.min(inlet.length, outlet.length);
  const result: number[] = [];

  for (let index = 0; index < length; index += 1) {
    const inValue = inlet[index];
    const outValue = outlet[index];

    if (!Number.isFinite(inValue) || !Number.isFinite(outValue)) {
      result.push(NaN);
      continue;
    }

    result.push(inValue - outValue);
  }

  return result;
}

// 원수펌프 차압 계산
function computeDifferentialPressure(discharge: number[], suction: number[]) {
  const length = Math.min(discharge.length, suction.length);
  const result: number[] = [];

  for (let index = 0; index < length; index += 1) {
    const dischargeValue = discharge[index];
    const suctionValue = suction[index];

    if (!Number.isFinite(dischargeValue) || !Number.isFinite(suctionValue)) {
      result.push(NaN);
      continue;
    }

    result.push(dischargeValue - suctionValue);
  }

  return result;
}

// 목표값 대비 오차 계산
function computePidError(actual: number[], target: number[]) {
  const length = Math.min(actual.length, target.length);
  const result: number[] = [];

  for (let index = 0; index < length; index += 1) {
    const actualValue = actual[index];
    const targetValue = target[index];

    if (!Number.isFinite(actualValue) || !Number.isFinite(targetValue)) {
      result.push(NaN);
      continue;
    }

    result.push(actualValue - targetValue);
  }

  return result;
}

// 배액 EC - 혼합EC 계산
function computeSaltAccumulation(drainEc: number[], mixEc: number[]) {
  const length = Math.min(drainEc.length, mixEc.length);
  const result: number[] = [];

  for (let index = 0; index < length; index += 1) {
    const drainValue = drainEc[index];
    const mixValue = mixEc[index];

    if (!Number.isFinite(drainValue) || !Number.isFinite(mixValue)) {
      result.push(NaN);
      continue;
    }

    result.push(drainValue - mixValue);
  }

  return result;
}

// 구역 배지 EC - 혼합EC 계산
function computeZoneEcAccumulation(zoneEc: number[], mixEc: number[]) {
  const length = Math.min(zoneEc.length, mixEc.length);
  const result: number[] = [];

  for (let index = 0; index < length; index += 1) {
    const zoneValue = zoneEc[index];
    const mixValue = mixEc[index];

    if (!Number.isFinite(zoneValue) || !Number.isFinite(mixValue)) {
      result.push(NaN);
      continue;
    }

    result.push(zoneValue - mixValue);
  }

  return result;
}

// 첫 유효값 대비 수분 변화량 계산
function computeMoistureResponse(values: number[]) {
  const baselineIndex = values.findIndex((value) => Number.isFinite(value));
  if (baselineIndex === -1) return values.map(() => NaN);

  const baseline = values[baselineIndex];
  return values.map((value) => {
    if (!Number.isFinite(value) || !Number.isFinite(baseline)) return NaN;
    return value - baseline;
  });
}

// 그래프용 좌표 계산
function buildChartPoints(values: number[]) {
  const innerWidth = CHART_WIDTH - CHART_PADDING * 2;
  const innerHeight = CHART_HEIGHT - CHART_PADDING * 2;
  const valid = finiteValues(values);

  if (valid.length < 2) {
    return { points: [] as ChartPoint[], max: 1 };
  }

  const min = Math.min(...valid);
  const max = Math.max(...valid);
  const range = max - min || 1;

  const points = values.map((value, index) => {
    const x = CHART_PADDING + (index / Math.max(values.length - 1, 1)) * innerWidth;

    if (!Number.isFinite(value)) {
      return { x, y: NaN, value: NaN };
    }

    const y = CHART_PADDING + innerHeight - ((value - min) / range) * innerHeight;
    return { x, y, value };
  });

  return { points, max };
}

// 선 path 생성
function buildLinePath(points: ChartPoint[]) {
  return points
    .filter((point) => Number.isFinite(point.y))
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`)
    .join(" ");
}

// 가장 높은 구간을 critical 구간으로 강조
function buildCriticalSegments(points: ChartPoint[], critical: number) {
  const segments: Segment[] = [];
  let current: ChartPoint[] = [];

  points.forEach((point) => {
    const isCritical = Number.isFinite(point.value) && point.value >= critical;

    if (isCritical) {
      current.push(point);
      return;
    }

    if (current.length >= 2) {
      segments.push({
        polygonPoints: [
          `${current[0].x},${CHART_HEIGHT - CHART_PADDING}`,
          ...current.map((item) => `${item.x},${item.y}`),
          `${current[current.length - 1].x},${CHART_HEIGHT - CHART_PADDING}`,
        ].join(" "),
        linePath: current
          .map((item, index) => `${index === 0 ? "M" : "L"} ${item.x} ${item.y}`)
          .join(" "),
      });
    }

    current = [];
  });

  if (current.length >= 2) {
    segments.push({
      polygonPoints: [
        `${current[0].x},${CHART_HEIGHT - CHART_PADDING}`,
        ...current.map((item) => `${item.x},${item.y}`),
        `${current[current.length - 1].x},${CHART_HEIGHT - CHART_PADDING}`,
      ].join(" "),
      linePath: current
        .map((item, index) => `${index === 0 ? "M" : "L"} ${item.x} ${item.y}`)
        .join(" "),
    });
  }

  return segments;
}

function latestValue(values: number[], decimals = 2) {
  const valid = finiteValues(values);
  const last = valid[valid.length - 1];
  return Number.isFinite(last) ? last.toFixed(decimals) : "—";
}

// 원수펌프 데이터 구성
function pumpRows(sensor: RawSensorPayload): SensorRow[] {
  const diffPressure =
    typeof sensor.discharge_pressure_kpa === "number" && typeof sensor.suction_pressure_kpa === "number"
      ? sensor.discharge_pressure_kpa - sensor.suction_pressure_kpa
      : undefined;

  return [
    { label: "펌프 RPM", value: `${fmt(sensor.pump_rpm, 0)} RPM` },
    { label: "펌프 토출 유량", value: `${fmt(sensor.flow_rate_l_min)} L/min` },
    { label: "펌프 흡입 압력", value: `${fmt(sensor.suction_pressure_kpa)} kPa` },
    { label: "펌프 토출 압력", value: `${fmt(sensor.discharge_pressure_kpa)} kPa` },
    { label: "모터 소비 전류", value: `${fmt(sensor.motor_current_a, 2)} A` },
    { label: "모터 전력", value: `${fmt(sensor.motor_power_kw, 2)} kW` },
    { label: "베어링 진동 실효값", value: `${fmt(sensor.bearing_vibration_rms_mm_s, 2)} mm/s` },
    { label: "모터 온도", value: `${fmt(sensor.motor_temperature_c)} °C` },
    { label: "베어링 온도", value: `${fmt(sensor.bearing_temperature_c)} °C` },
    { label: "차압", value: diffPressure !== undefined ? `${diffPressure.toFixed(1)} kPa` : "—" },
  ];
}

// 필터 데이터 구성
function filterRows(sensor: RawSensorPayload): SensorRow[] {
  const diffPressure =
    typeof sensor.filter_pressure_in_kpa === "number" && typeof sensor.filter_pressure_out_kpa === "number"
      ? sensor.filter_pressure_in_kpa - sensor.filter_pressure_out_kpa
      : undefined;

  return [
    { label: "필터 입구 압력", value: `${fmt(sensor.filter_pressure_in_kpa)} kPa` },
    { label: "필터 출구 압력", value: `${fmt(sensor.filter_pressure_out_kpa)} kPa` },
    { label: "필터 차압", value: diffPressure !== undefined ? `${diffPressure.toFixed(1)} kPa` : "—" },
  ];
}

// 양액자동공급기 데이터 구성
function autoSupplyRows(sensor: RawSensorPayload): SensorRow[] {
  const pidErrorEc =
    typeof sensor.mix_ec_ds_m === "number" && typeof sensor.mix_target_ec_ds_m === "number"
      ? sensor.mix_ec_ds_m - sensor.mix_target_ec_ds_m
      : undefined;
  const pidErrorPh =
    typeof sensor.mix_ph === "number" && typeof sensor.mix_target_ph === "number"
      ? sensor.mix_ph - sensor.mix_target_ph
      : undefined;
  const saltAccumulation =
    typeof sensor.drain_ec_ds_m === "number" && typeof sensor.mix_ec_ds_m === "number"
      ? sensor.drain_ec_ds_m - sensor.mix_ec_ds_m
      : undefined;

  return [
    { label: "조제 목표 EC", value: `${fmt(sensor.mix_target_ec_ds_m, 2)} dS/m` },
    { label: "혼합EC", value: `${fmt(sensor.mix_ec_ds_m, 2)} dS/m` },
    { label: "조제 목표 pH", value: `${fmt(sensor.mix_target_ph, 2)} pH` },
    { label: "조제 현재 pH", value: `${fmt(sensor.mix_ph, 2)} pH` },
    { label: "조제 온도", value: `${fmt(sensor.mix_temp_c)} °C` },
    { label: "조제 유량", value: `${fmt(sensor.mix_flow_l_min)} L/min` },
    { label: "산 주입량", value: `${fmt(sensor.dosing_acid_ml_min, 2)} mL/min` },
    { label: "배액 EC", value: `${fmt(sensor.drain_ec_ds_m, 2)} dS/m` },
    { label: "EC PID 오차", value: pidErrorEc !== undefined ? `${pidErrorEc.toFixed(3)} dS/m` : "—" },
    { label: "pH PID 오차", value: pidErrorPh !== undefined ? `${pidErrorPh.toFixed(3)} pH` : "—" },
    { label: "염류 축적 델타", value: saltAccumulation !== undefined ? `${saltAccumulation.toFixed(3)} dS/m` : "—" },
  ];
}

// 구역 데이터 구성
function zoneRows(zoneNumber: number, sensor: RawSensorPayload, chart: ChartBuffer | null): SensorRow[] {
  const flow = sensor[`zone${zoneNumber}_flow_l_min` as keyof RawSensorPayload];
  const pressure = sensor[`zone${zoneNumber}_pressure_kpa` as keyof RawSensorPayload];
  const moisture = sensor[`zone${zoneNumber}_substrate_moisture_pct` as keyof RawSensorPayload];
  const zoneEc = sensor[`zone${zoneNumber}_substrate_ec_ds_m` as keyof RawSensorPayload];
  const zonePh = sensor[`zone${zoneNumber}_substrate_ph` as keyof RawSensorPayload];

  const moistureSeries =
    zoneNumber === 1
      ? computeMoistureResponse(chart?.zone1_moisture ?? [])
      : zoneNumber === 2
        ? computeMoistureResponse(chart?.zone2_moisture ?? [])
        : computeMoistureResponse(chart?.zone3_moisture ?? []);

  const moistureReaction = latestValue(moistureSeries, 2);

  const ecAccumulation =
    typeof zoneEc === "number" && typeof sensor.mix_ec_ds_m === "number"
      ? zoneEc - sensor.mix_ec_ds_m
      : undefined;

  return [
    { label: `${zoneNumber}구역 유량`, value: `${fmt(flow)} L/min` },
    { label: `${zoneNumber}구역 압력`, value: `${fmt(pressure)} kPa` },
    { label: `${zoneNumber}구역 배지 수분`, value: `${fmt(moisture)} %` },
    { label: `${zoneNumber}구역 배지 EC`, value: `${fmt(zoneEc, 2)} dS/m` },
    { label: `${zoneNumber}구역 배지 pH`, value: `${fmt(zonePh, 2)} pH` },
    { label: `${zoneNumber}구역 수분 반응`, value: moistureReaction === "—" ? "—" : `${moistureReaction} %p` },
    { label: `${zoneNumber}구역 EC 축적`, value: ecAccumulation !== undefined ? `${ecAccumulation.toFixed(3)} dS/m` : "—" },
  ];
}

function getSensorRows(equipmentId: string, sensor: RawSensorPayload, chart: ChartBuffer | null) {
  if (equipmentId === "rawWaterTank") {
    return [
      { label: "원수 저장탱크 수위", value: `${fmt(sensor.raw_tank_level_pct)} %` },
      { label: "원수 탱크 물 온도", value: `${fmt(sensor.raw_water_temp_c)} °C` },
    ];
  }
  if (equipmentId === "filter") return filterRows(sensor);
  if (equipmentId === "rawWaterPump") return pumpRows(sensor);
  if (equipmentId === "autoSupply") return autoSupplyRows(sensor);
  if (equipmentId === "tankA") return [{ label: "양액 A 탱크 수위", value: `${fmt(sensor.tank_a_level_pct)} %` }];
  if (equipmentId === "tankB") return [{ label: "양액 B 탱크 수위", value: `${fmt(sensor.tank_b_level_pct)} %` }];
  if (equipmentId === "tankPH") return [{ label: "산 탱크 수위", value: `${fmt(sensor.acid_tank_level_pct)} %` }];
  if (equipmentId === "valve1") return [{ label: "1구역 유량", value: `${fmt(sensor.zone1_flow_l_min)} L/min` }, { label: "1구역 압력", value: `${fmt(sensor.zone1_pressure_kpa)} kPa` }];
  if (equipmentId === "valve2") return [{ label: "2구역 유량", value: `${fmt(sensor.zone2_flow_l_min)} L/min` }, { label: "2구역 압력", value: `${fmt(sensor.zone2_pressure_kpa)} kPa` }];
  if (equipmentId === "valve3") return [{ label: "3구역 유량", value: `${fmt(sensor.zone3_flow_l_min)} L/min` }, { label: "3구역 압력", value: `${fmt(sensor.zone3_pressure_kpa)} kPa` }];
  if (equipmentId === "growingZone1") return zoneRows(1, sensor, chart);
  if (equipmentId === "growingZone2") return zoneRows(2, sensor, chart);
  if (equipmentId === "growingZone3") return zoneRows(3, sensor, chart);
  return [];
}

// 계산값 그래프 구성
function getTrendCards(equipmentId: string, chart: ChartBuffer | null): TrendCard[] {
  if (!chart) return [];

  if (equipmentId === "rawWaterPump") {
    return [{ title: "차압 그래프", unit: "kPa", values: takeRecent(computeDifferentialPressure(chart.pressure, chart.suction)) }];
  }

  if (equipmentId === "filter") {
    return [{ title: "필터 차압 그래프", unit: "kPa", values: takeRecent(computeFilterDiff(chart.filter_in, chart.filter_out)) }];
  }

  if (equipmentId === "autoSupply") {
    return [
      { title: "EC PID 오차 그래프", unit: "dS/m", values: takeRecent(computePidError(chart.mix_ec, chart.mix_target_ec)) },
      { title: "pH PID 오차 그래프", unit: "pH", values: takeRecent(computePidError(chart.mix_ph, chart.mix_target_ph)) },
      { title: "염류 축적 델타 그래프", unit: "dS/m", values: takeRecent(computeSaltAccumulation(chart.drain_ec, chart.mix_ec)) },
    ];
  }

  if (equipmentId === "growingZone1") {
    return [
      { title: "1구역 수분 반응 그래프", unit: "%", values: takeRecent(computeMoistureResponse(chart.zone1_moisture)) },
      { title: "1구역 EC 축적 그래프", unit: "dS/m", values: takeRecent(computeZoneEcAccumulation(chart.zone1_ec, chart.mix_ec)) },
    ];
  }

  if (equipmentId === "growingZone2") {
    return [
      { title: "2구역 수분 반응 그래프", unit: "%", values: takeRecent(computeMoistureResponse(chart.zone2_moisture)) },
      { title: "2구역 EC 축적 그래프", unit: "dS/m", values: takeRecent(computeZoneEcAccumulation(chart.zone2_ec, chart.mix_ec)) },
    ];
  }

  if (equipmentId === "growingZone3") {
    return [
      { title: "3구역 수분 반응 그래프", unit: "%", values: takeRecent(computeMoistureResponse(chart.zone3_moisture)) },
      { title: "3구역 EC 축적 그래프", unit: "dS/m", values: takeRecent(computeZoneEcAccumulation(chart.zone3_ec, chart.mix_ec)) },
    ];
  }

  return [];
}

function TrendChart({ title, unit, values }: TrendCard) {
  const valid = finiteValues(values);
  if (valid.length < 2) return null;

  const { points, max } = buildChartPoints(values);
  const linePath = buildLinePath(points);
  const criticalSegments = buildCriticalSegments(points, max);

  return (
    <div className="equipment-modal-chart-card">
      {/* 계산값 그래프 표시 */}
      <div className="equipment-modal-chart-title">{title}</div>
      <svg className="equipment-modal-chart" viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}>
        <rect width={CHART_WIDTH} height={CHART_HEIGHT} rx={12} className="equipment-modal-chart__bg" />

        {criticalSegments.map((segment, index) => (
          <g key={`${title}-${index}`}>
            <polygon points={segment.polygonPoints} className="equipment-modal-chart__critical-fill" />
            <path d={segment.linePath} className="equipment-modal-chart__critical-line" />
          </g>
        ))}

        <path d={linePath} className="equipment-modal-chart__line" />
      </svg>
      <div className="equipment-modal-chart-value">{latestValue(values)} {unit}</div>
    </div>
  );
}

function EquipmentModal({ equipment, sensorPayload, chartSnapshot, onClose }: EquipmentModalProps) {
  if (!equipment) return null;

  const sensorRows = sensorPayload ? getSensorRows(equipment.id, sensorPayload, chartSnapshot ?? null) : [];
  const trendCards = getTrendCards(equipment.id, chartSnapshot ?? null).filter((item) => finiteValues(item.values).length >= 2);

  return (
    <div className="equipment-modal-overlay" onClick={onClose}>
      <div className="equipment-modal equipment-modal--wide" onClick={(event) => event.stopPropagation()}>
        <div className="equipment-modal-header">
          <div className="equipment-modal-header-main">
            <div className="equipment-modal-title">{equipment.name}</div>
            {/* 설비명 줄 오른쪽에 현재 상태만 표시 */}
            {/* <div className="equipment-modal-status">현재 상태 {statusLabel(equipment.status)}</div> */}
          </div>

          <button className="equipment-modal-close" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="equipment-modal-body">
          {sensorRows.length > 0 && (
            <div className="equipment-modal-section">
              <div className="equipment-modal-section-title">설비 데이터</div>
              {sensorRows.map((row) => (
                <div className="equipment-modal-row" key={`${equipment.id}-${row.label}`}>
                  <span className="equipment-modal-label">{row.label}</span>
                  <span className="equipment-modal-value">{row.value}</span>
                </div>
              ))}
            </div>
          )}

          {trendCards.length > 0 && (
            <div className="equipment-modal-section">
              {/* raw가 아닌 계산 지표 중 흐름 확인이 필요한 값만 그래프로 표시 */}
              <div className="equipment-modal-section-title">계산 지표 그래프</div>
              <div className="equipment-modal-chart-grid">
                {trendCards.map((card) => (
                  <TrendChart key={`${equipment.id}-${card.title}`} {...card} />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default EquipmentModal;
