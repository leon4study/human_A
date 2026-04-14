import Panel from "../common/Panel";

function AlertHistoryPanel() {
  return (
    <Panel title="Alert 이력">
      <div className="alert-table">
        <div className="alert-table__head">
          <span>시간</span>
          <span>장비</span>
          <span>원인</span>
          <span>위험도</span>
        </div>

        <div className="alert-table__body">
          <div className="alert-table__row">
            <span>-</span>
            <span>-</span>
            <span>-</span>
            <span>-</span>
          </div>
          <div className="alert-table__row">
            <span>-</span>
            <span>-</span>
            <span>-</span>
            <span>-</span>
          </div>
          <div className="alert-table__row">
            <span>-</span>
            <span>-</span>
            <span>-</span>
            <span>-</span>
          </div>
        </div>
      </div>
    </Panel>
  );
}

export default AlertHistoryPanel;