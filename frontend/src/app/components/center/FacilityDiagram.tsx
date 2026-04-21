import { initialSensorData } from "./facility/model/facility.status";
import type { FacilityDiagramProps } from "./facility/model/facility.types";
import { FacilityEquipment } from "./facility/render/FacilityEquipment";
import { FacilityPipeLayout } from "./facility/render/FacilityPipeLayout";
import { FacilityZones } from "./facility/render/FacilityZones";
import { createEquipment } from "./facility/utils/facilityEquipment";

import "./facility/facility-diagram.css";

// 중앙 시설 모델링 화면의 조립을 담당하는 메인 컴포넌트
function FacilityDiagram({ onEquipmentSelect, sensorData }: FacilityDiagramProps) {
  const effectiveSensorData = sensorData ?? initialSensorData;

  const handleEquipmentClick = (
    id: string,
    currentValue?: number,
    unit?: string,
  ) => {
    const equipment = createEquipment(id, effectiveSensorData, currentValue, unit);
    onEquipmentSelect?.(equipment);
  };

  return (
    <div className="facility-diagram-wrap">
      <div className="facility-diagram-center">
        <div className="facility-diagram-inner">
          {/* 배관 및 유량 애니메이션 레이어 */}
          <FacilityPipeLayout />

          <div className="facility-content-area">
            {/* 장비 SVG와 클릭 인터랙션 레이어 */}
            <FacilityEquipment
              sensorData={effectiveSensorData}
              onEquipmentClick={handleEquipmentClick}
            />
            {/* 하단 재배 구역 카드 레이어 */}
            <FacilityZones onEquipmentClick={(id) => handleEquipmentClick(id)} />
          </div>
        </div>
      </div>
    </div>
  );
}

export default FacilityDiagram;
