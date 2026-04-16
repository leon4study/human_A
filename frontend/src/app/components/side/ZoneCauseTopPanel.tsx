import Panel from "../common/Panel";
import { zoneCauseTopData } from "../../data/zoneCauseTopData";
import type { ZoneItem } from "../../types/dashboard";

interface ZoneCauseTopPanelProps {
  selectedZoneId: string;
  zoneItems: ZoneItem[];
}

function ZoneCauseTopPanel({
  selectedZoneId,
  zoneItems,
}: ZoneCauseTopPanelProps) {
  const selectedZone =
    zoneItems.find((item) => item.id === selectedZoneId) ?? null;

  const items = zoneCauseTopData
    .filter((item) => item.zoneId === selectedZoneId)
    .sort((a, b) => b.count - a.count)
    .slice(0, 3);

  const maxCount = Math.max(...items.map((item) => item.count), 1);

  return (
    <Panel title={`${selectedZone?.label ?? "-"} 설비(원인) Top 3`}>
      <div className="zone-cause-top">
        {items.map((item) => (
          <div key={item.id} className="zone-cause-top__row">
            <div className="zone-cause-top__top">
              <span className="zone-cause-top__label">
                {item.equipment} / {item.cause}
              </span>
              <span className="zone-cause-top__value">{item.count}건</span>
            </div>

            <div className="zone-cause-top__bar">
              <div
                className="zone-cause-top__fill"
                style={{ width: `${(item.count / maxCount) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

export default ZoneCauseTopPanel;