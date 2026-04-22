import FacilityDiagram from "./facility/FacilityDiagram";
import type { Equipment, SensorData } from "./facility/model/facility.types";

interface CenterPlaceholderProps {
  onEquipmentSelect?: (equipment: Equipment) => void;
  sensorData?: SensorData;
}

// 중앙 구조도
function CenterPlaceholder({ onEquipmentSelect, sensorData }: CenterPlaceholderProps) {
  return (
    <div className="dashboard__center-layer">
      <FacilityDiagram onEquipmentSelect={onEquipmentSelect} sensorData={sensorData} />
    </div>
  );
}

export default CenterPlaceholder;
