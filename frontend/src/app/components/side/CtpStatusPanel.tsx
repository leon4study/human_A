import Panel from "../common/Panel";

function CtpStatusPanel() {
  return (
    <Panel title="CTP 상태">
      <div className="ctp-grid">
        <div className="ctp-card">
          <span>펌프 토출 유량</span>
          <strong>1.650</strong>
        </div>

        <div className="ctp-card is-alert">
          <span>펌프 토출 압력</span>
          <strong>650</strong>
        </div>

        <div className="ctp-card">
          <span>필터 차압</span>
          <strong>1.650</strong>
        </div>

        <div className="ctp-card is-warning">
          <span>베어링 진동</span>
          <strong>650</strong>
        </div>
      </div>
    </Panel>
  );
}

export default CtpStatusPanel;