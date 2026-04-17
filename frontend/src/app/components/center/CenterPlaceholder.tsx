import FacilityDiagram from "./FacilityDiagram";

function CenterPlaceholder() {
  return (
    <div className="dashboard__bg-safe-area">
      <div className="dashboard__bg-model-frame">
        <div className="dashboard__bg-model">
          <FacilityDiagram />
        </div>
      </div>
    </div> 
  );
}

export default CenterPlaceholder;