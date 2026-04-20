import FacilityDiagram from "./FacilityDiagram";
import type { Equipment } from "./facility/model/facility.types";

interface CenterPlaceholderProps {
  onEquipmentSelect?: (equipment: Equipment) => void;
}

// 중앙 구조도
function CenterPlaceholder({ onEquipmentSelect }: CenterPlaceholderProps) {
  return (
    <div className="dashboard__center-layer">
      <FacilityDiagram onEquipmentSelect={onEquipmentSelect} />
    </div>
  );
}

export default CenterPlaceholder;
