import Panel from "../common/Panel";

function EnvironmentPanel() {
  return (
    <Panel title="환경 정보">
      <div className="panel-list">
        <div className="panel-row">
          <span>광량</span>
          <strong>400 μmol/m²·s</strong>
        </div>
        <div className="panel-row">
          <span>온도</span>
          <strong>23.4°C</strong>
        </div>
        <div className="panel-row">
          <span>습도</span>
          <strong>68%</strong>
        </div>
        <div className="panel-row">
          <span>CO₂</span>
          <strong>800 ppm</strong>
        </div>
      </div>
    </Panel>
  );
}

export default EnvironmentPanel;