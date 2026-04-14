import Panel from "../common/Panel";

function ZoneStatusPanel() {
  return (
    <Panel title="구역별 상태">
      <div className="zone-status">
        <div className="zone-status__boxes">
          <div className="zone-box is-active">1구역</div>
          <div className="zone-box">2구역</div>
          <div className="zone-box">3구역</div>
        </div>

        <div className="zone-status__summary">
          <div>현재 Green 구역: 1구역</div>
          <div>현재 Yellow 구역: 2구역</div>
          <div>현재 Red 구역: 3구역</div>
        </div>
      </div>
    </Panel>
  );
}

export default ZoneStatusPanel;