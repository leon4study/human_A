import { memo } from "react";
import Panel from "../common/Panel";
import type { ZoneItem } from "../../types/dashboard";

interface ZoneStatusPanelProps {
  zoneItems: ZoneItem[];
  selectedZoneId: string;
  onSelectZone: (zoneId: string) => void;
}

function ZoneStatusPanel({
  zoneItems,
  selectedZoneId,
  onSelectZone,
}: ZoneStatusPanelProps) {
  if (zoneItems.length === 0) {
    return (
      <Panel title="호기별 상태 (막힘율)">
        <div className="zone-status__empty">표시할 호기 데이터가 없습니다.</div>
      </Panel>
    );
  }

  const sortedZones = [...zoneItems].sort(
    (a, b) => b.blockageRate - a.blockageRate
  );

  const worstZone = sortedZones[0];
  const goldenZone = sortedZones[sortedZones.length - 1];
  const showGoldenRank = sortedZones.length > 1 && goldenZone.id !== worstZone.id;

  const getBarClassName = (value: number) => {
    if (value >= 61) {
      return "zone-bar__fill is-danger";
    }

    if (value >= 31) {
      return "zone-bar__fill is-warning";
    }

    return "zone-bar__fill is-normal";
  };

  return (
    <Panel title="호기별 상태 (막힘율)">
      <div className="zone-status">
        <div className="zone-status__summary">
          {/* <div className="zone-status__badge zone-status__badge--worst">
            Worst 구역: {worstZone.label}
          </div>
          <div className="zone-status__badge zone-status__badge--golden">
            Golden 구역: {goldenZone.label}
          </div> */}
        </div>

        <div className="zone-status__chart">
          {sortedZones.map((zone) => (
            <button
              key={zone.id}
              type="button"
              className={`zone-chart-row ${selectedZoneId === zone.id ? "is-selected" : ""}`}
              onClick={() => onSelectZone(zone.id)}
            >
              <div className="zone-chart-row__top">
                <span className="zone-chart-row__label">{zone.label}</span>
                <div className="zone-chart-row__right">
                  {zone.id === worstZone.id && (
                    <span className="zone-rank zone-rank--worst">Worst</span>
                  )}
                  {showGoldenRank && zone.id === goldenZone.id && (
                    <span className="zone-rank zone-rank--golden">Golden</span>
                  )}
                  <span className="zone-chart-row__value">
                    {zone.blockageRate}%
                  </span>
                </div>
              </div>

              <div className="zone-bar">
                <div
                  className={getBarClassName(zone.blockageRate)}
                  style={{ width: `${zone.blockageRate}%` }}
                />
              </div>
            </button>
          ))}
        </div>
      </div>
    </Panel>
  );
}

export default memo(ZoneStatusPanel);
