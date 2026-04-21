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
  status?: "normal" | "caution" | "warning" | "danger";
  isHeader?: boolean;
}

const STATUS_COLORS: Record<string, string> = {
  caution: "#ffc107",
  warning: "#ff9800",
  danger: "#f44336",
};

function fmt(v: unknown, decimals = 1): string {
  return typeof v === "number" && Number.isFinite(v) ? v.toFixed(decimals) : "—";
}

const EPS = 1e-6;

function computeRpmStability(rpms: number[]): number | undefined {
  const valid = rpms.filter(Number.isFinite);
  if (valid.length < 2) return undefined;
  const mean = valid.reduce((a, b) => a + b, 0) / valid.length;
  const last = valid[valid.length - 1];
  return Math.abs(last - mean) / (mean + EPS);
}

function computeTempSlope(temps: number[], ts: number[]): number | undefined {
  const n = Math.min(temps.length, ts.length);
  if (n < 2) return undefined;
  const dT = temps[n - 1] - temps[n - 2];
  const dt = (ts[n - 1] - ts[n - 2]) / 1000;
  if (!Number.isFinite(dT) || !Number.isFinite(dt) || dt <= 0) return undefined;
  return dT / dt;
}

function getSensorRows(
  id: string,
  s: RawSensorPayload,
  chart?: ChartBuffer | null,
): SensorRow[] {
  if (id === "rawWaterPump") {
    // §1-1 Motor
    const dp = s.discharge_pressure_kpa;
    const sp = s.suction_pressure_kpa;
    const fl = s.flow_rate_l_min;
    const pw = s.motor_power_kw;
    const diffP =
      typeof dp === "number" && typeof sp === "number" ? dp - sp : undefined;
    const hydPow =
      diffP !== undefined && typeof fl === "number"
        ? (fl * diffP) / 60000
        : undefined;
    const w2w =
      hydPow !== undefined && typeof pw === "number"
        ? hydPow / (pw + EPS)
        : undefined;
    const rpmStability = chart ? computeRpmStability(chart.pump_rpm) : undefined;
    const tempSlope = chart
      ? computeTempSlope(chart.motor_temp, chart.ts)
      : undefined;

    // §1-2 Hydraulic
    const z1p = s.zone1_pressure_kpa;
    const z1f = s.zone1_flow_l_min;
    const pfratio =
      typeof dp === "number" && typeof fl === "number"
        ? dp / (fl + EPS)
        : undefined;
    const dpPerFlow =
      diffP !== undefined && typeof fl === "number"
        ? diffP / (fl + EPS)
        : undefined;
    const zone1Resistance =
      typeof z1p === "number" && typeof z1f === "number"
        ? (z1p as number) / ((z1f as number) + EPS)
        : undefined;

    return [
      { label: "── 모터 구동", value: "", isHeader: true },
      { label: "모터 전류", value: `${fmt(s.motor_current_a)} A` },
      { label: "모터 전력", value: `${fmt(pw, 2)} kW` },
      { label: "모터 온도", value: `${fmt(s.motor_temperature_c)} °C` },
      { label: "펌프 회전수", value: `${fmt(s.pump_rpm, 0)} RPM` },
      {
        label: "베어링 진동",
        value: `${fmt(s.bearing_vibration_rms_mm_s, 2)} mm/s RMS`,
      },
      { label: "베어링 온도", value: `${fmt(s.bearing_temperature_c)} °C` },
      {
        label: "RPM 안정도 지수",
        value: rpmStability !== undefined ? rpmStability.toFixed(4) : "—",
      },
      {
        label: "온도 변화율",
        value: tempSlope !== undefined ? `${tempSlope.toFixed(4)} °C/s` : "—",
      },
      {
        label: "전기→수력 효율",
        value: w2w !== undefined ? w2w.toFixed(3) : "—",
      },
      { label: "── 수압/유압", value: "", isHeader: true },
      { label: "토출 압력", value: `${fmt(dp)} kPa` },
      { label: "흡입 압력", value: `${fmt(sp)} kPa` },
      { label: "메인 유량", value: `${fmt(fl)} L/min` },
      { label: "1구역 압력", value: `${fmt(z1p)} kPa` },
      { label: "1구역 유량", value: `${fmt(z1f)} L/min` },
      {
        label: "차압 (토출−흡입)",
        value: diffP !== undefined ? `${diffP.toFixed(1)} kPa` : "—",
      },
      {
        label: "배관 저항 지수",
        value: pfratio !== undefined ? `${pfratio.toFixed(2)} kPa·min/L` : "—",
      },
      {
        label: "차압/유량 비",
        value: dpPerFlow !== undefined ? `${dpPerFlow.toFixed(2)} kPa·min/L` : "—",
      },
      { label: "유량 감소율", value: "—" },
      {
        label: "수력 동력",
        value: hydPow !== undefined ? `${hydPow.toFixed(4)} kW` : "—",
      },
      {
        label: "1구역 배관 저항",
        value:
          zone1Resistance !== undefined
            ? `${zone1Resistance.toFixed(2)} kPa·min/L`
            : "—",
      },
    ];
  }

  if (id === "filter") {
    // §1-5 Filter
    const inP = s.filter_pressure_in_kpa;
    const outP = s.filter_pressure_out_kpa;
    const delta =
      typeof inP === "number" && typeof outP === "number" ? inP - outP : undefined;
    return [
      { label: "입구 압력", value: `${fmt(inP)} kPa` },
      { label: "출구 압력", value: `${fmt(outP)} kPa` },
      {
        label: "필터 차압 (ΔP)",
        value: delta !== undefined ? `${delta.toFixed(1)} kPa` : "—",
        status:
          delta !== undefined
            ? delta >= 25
              ? "danger"
              : delta >= 15
              ? "warning"
              : "normal"
            : undefined,
      },
    ];
  }

  if (id === "autoSupply") {
    // §1-3 Nutrient
    const ec = s.mix_ec_ds_m;
    const targetEc = s.mix_target_ec_ds_m;
    const ph = s.mix_ph;
    const targetPh = s.mix_target_ph;
    const drainEc = s.drain_ec_ds_m;

    const pidEc =
      typeof ec === "number" && typeof targetEc === "number"
        ? ec - targetEc
        : undefined;
    const pidPh =
      typeof ph === "number" && typeof targetPh === "number"
        ? ph - targetPh
        : undefined;
    const saltDelta =
      typeof drainEc === "number" && typeof ec === "number"
        ? drainEc - ec
        : undefined;
    const phFlag =
      typeof ph === "number" ? (ph > 6.5 ? 1 : 0) : undefined;

    return [
      { label: "── 양액/수질", value: "", isHeader: true },
      { label: "혼합액 EC", value: `${fmt(ec, 2)} dS/m` },
      { label: "혼합액 pH", value: `${fmt(ph, 2)} pH` },
      { label: "목표 EC", value: `${fmt(targetEc, 2)} dS/m` },
      { label: "목표 pH", value: `${fmt(targetPh, 2)} pH` },
      { label: "배액 EC", value: `${fmt(drainEc, 2)} dS/m` },
      { label: "A 비료통 수위", value: `${fmt(s.tank_a_level_pct)} %` },
      { label: "── 제어 오차 / 파생", value: "", isHeader: true },
      {
        label: "EC 제어 오차",
        value:
          pidEc !== undefined
            ? `${pidEc >= 0 ? "+" : ""}${pidEc.toFixed(2)} dS/m`
            : "—",
        status:
          pidEc !== undefined
            ? Math.abs(pidEc) > 0.3
              ? "warning"
              : "normal"
            : undefined,
      },
      {
        label: "pH 제어 오차",
        value:
          pidPh !== undefined
            ? `${pidPh >= 0 ? "+" : ""}${pidPh.toFixed(2)} pH`
            : "—",
        status:
          pidPh !== undefined
            ? Math.abs(pidPh) > 0.3
              ? "warning"
              : "normal"
            : undefined,
      },
      {
        label: "염분 축적량",
        value: saltDelta !== undefined ? `${saltDelta.toFixed(2)} dS/m` : "—",
        status:
          saltDelta !== undefined
            ? saltDelta > 0.8
              ? "warning"
              : "normal"
            : undefined,
      },
      {
        label: "pH 불안정 플래그",
        value: phFlag !== undefined ? (phFlag === 1 ? "경고 (> 6.5)" : "정상") : "—",
        status: phFlag === 1 ? "caution" : phFlag === 0 ? "normal" : undefined,
      },
      { label: "A통 고갈 예상", value: "—" },
    ];
  }

  if (id === "rawWaterTank") {
    return [
      { label: "수위", value: `${fmt(s.raw_tank_level_pct)} %` },
      { label: "원수 온도", value: `${fmt(s.raw_water_temp_c)} °C` },
    ];
  }

  if (id === "tankA") {
    return [{ label: "수위", value: `${fmt(s.tank_a_level_pct)} %` }];
  }

  if (id === "tankB") {
    return [{ label: "수위", value: `${fmt(s.tank_b_level_pct)} %` }];
  }

  if (id === "tankPH") {
    return [
      { label: "수위", value: `${fmt(s.acid_tank_level_pct)} %` },
      { label: "산 투입량", value: `${fmt(s.dosing_acid_ml_min, 2)} mL/min` },
    ];
  }

  const zoneNum =
    id === "growingZone1"
      ? 1
      : id === "growingZone2"
      ? 2
      : id === "growingZone3"
      ? 3
      : null;

  if (zoneNum !== null) {
    // §1-4 Zone Drip
    const flow = s[`zone${zoneNum}_flow_l_min`];
    const pressure = s[`zone${zoneNum}_pressure_kpa`];
    const moisture = s[`zone${zoneNum}_substrate_moisture_pct`];
    const zoneEc = s[`zone${zoneNum}_substrate_ec_ds_m`];
    const mixEc = s.mix_ec_ds_m;
    const mainFlow = s.flow_rate_l_min;

    const resistance =
      typeof pressure === "number" && typeof flow === "number"
        ? (pressure as number) / ((flow as number) + EPS)
        : undefined;

    const ecAccumulation =
      typeof zoneEc === "number" && typeof mixEc === "number"
        ? (zoneEc as number) - mixEc
        : undefined;

    const z1f = s["zone1_flow_l_min"];
    const z2f = s["zone2_flow_l_min"];
    const z3f = s["zone3_flow_l_min"];
    const sumZoneFlow =
      typeof z1f === "number" && typeof z2f === "number" && typeof z3f === "number"
        ? (z1f as number) + (z2f as number) + (z3f as number)
        : undefined;
    const supplyBalance =
      sumZoneFlow !== undefined && typeof mainFlow === "number"
        ? sumZoneFlow / (mainFlow + EPS)
        : undefined;

    return [
      { label: "── 원시 센서", value: "", isHeader: true },
      { label: "유량", value: `${fmt(flow)} L/min` },
      { label: "압력", value: `${fmt(pressure)} kPa` },
      { label: "배지 수분", value: `${fmt(moisture)} %` },
      { label: "배지 EC", value: `${fmt(zoneEc, 2)} dS/m` },
      { label: "── 파생 지표", value: "", isHeader: true },
      {
        label: "배관 저항",
        value:
          resistance !== undefined ? `${resistance.toFixed(2)} kPa·min/L` : "—",
      },
      { label: "수분 반응률", value: "—" },
      {
        label: "배지 염류 축적",
        value:
          ecAccumulation !== undefined
            ? `${ecAccumulation >= 0 ? "+" : ""}${ecAccumulation.toFixed(2)} dS/m`
            : "—",
        status:
          ecAccumulation !== undefined
            ? ecAccumulation > 0.5
              ? "warning"
              : "normal"
            : undefined,
      },
      {
        label: "공급 밸런스 지수",
        value: supplyBalance !== undefined ? supplyBalance.toFixed(3) : "—",
        status:
          supplyBalance !== undefined
            ? supplyBalance < 0.9 || supplyBalance > 1.1
              ? "warning"
              : "normal"
            : undefined,
      },
    ];
  }

  return [];
}

function EquipmentModal({
  equipment,
  sensorPayload,
  chartSnapshot,
  onClose,
}: EquipmentModalProps) {
  if (!equipment) return null;

  const sensorRows =
    sensorPayload ? getSensorRows(equipment.id, sensorPayload, chartSnapshot) : [];

  return (
    <div className="equipment-modal-overlay" onClick={onClose}>
      <div className="equipment-modal" onClick={(e) => e.stopPropagation()}>
        <div className="equipment-modal-header">
          <div>
            <div className="equipment-modal-title">{equipment.name}</div>
            <div className="equipment-modal-subtitle">{equipment.type}</div>
          </div>

          <button className="equipment-modal-close" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="equipment-modal-body">
          {/* 기본 정보 */}
          <div className="equipment-modal-section">
            <div className="equipment-modal-section-title">기본 정보</div>

            <div className="equipment-modal-row">
              <span className="equipment-modal-label">장비 분류</span>
              <span className="equipment-modal-value">{equipment.category}</span>
            </div>

            <div className="equipment-modal-row">
              <span className="equipment-modal-label">상태</span>
              <span className="equipment-modal-value">{equipment.status}</span>
            </div>
          </div>

          {/* 센서 데이터 */}
          {sensorRows.length > 0 && (
            <div className="equipment-modal-section">
              <div className="equipment-modal-section-title">센서 데이터</div>
              {sensorRows.map((row, idx) =>
                row.isHeader ? (
                  <div className="equipment-modal-subheader" key={idx}>
                    {row.label}
                  </div>
                ) : (
                  <div className="equipment-modal-row" key={row.label}>
                    <span className="equipment-modal-label">{row.label}</span>
                    <span
                      className="equipment-modal-value"
                      style={
                        row.status && row.status !== "normal"
                          ? { color: STATUS_COLORS[row.status] }
                          : undefined
                      }
                    >
                      {row.value}
                    </span>
                  </div>
                ),
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default EquipmentModal;
