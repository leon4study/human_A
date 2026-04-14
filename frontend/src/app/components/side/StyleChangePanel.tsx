import Panel from "../common/Panel";

function StyleChangePanel() {
  return (
    <Panel title="스타일 변경 예정">
      <div className="style-change">
        <div className="style-dot style-dot--blue">블루</div>
        <div className="style-dot style-dot--green">그린</div>
        <div className="style-dot style-dot--red">레드</div>
      </div>
    </Panel>
  );
}

export default StyleChangePanel;