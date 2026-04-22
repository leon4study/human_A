import { useCallback, useEffect, useRef } from "react";
import { initialSensorData } from "./model/facility.status";
import type { FacilityDiagramProps } from "./model/facility.types";
import { FacilityEquipment } from "./render/FacilityEquipment";
import { FacilityPipeLayout } from "./render/FacilityPipeLayout";
import { FacilityZones } from "./render/FacilityZones";
import { createEquipment } from "./utils/facilityEquipment";

import "./facility-diagram.css";

// 중앙 시설 모델링 화면의 조립을 담당하는 메인 컴포넌트
function FacilityDiagram({ onEquipmentSelect, sensorData }: FacilityDiagramProps) {
  const effectiveSensorData = sensorData ?? initialSensorData;

  // 콜백이 매번 재생성되면 하위 memo가 무의미해지므로 sensorData는 ref로 읽는다
  const sensorDataRef = useRef(effectiveSensorData);
  useEffect(() => {
    sensorDataRef.current = effectiveSensorData;
  }, [effectiveSensorData]);

  const handleEquipmentClick = useCallback(
    (id: string, currentValue?: number, unit?: string) => {
      const equipment = createEquipment(
        id,
        sensorDataRef.current,
        currentValue,
        unit,
      );
      onEquipmentSelect?.(equipment);
    },
    [onEquipmentSelect],
  );

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
            <FacilityZones onEquipmentClick={handleEquipmentClick} />
          </div>
        </div>
      </div>
    </div>
  );
}

export default FacilityDiagram;
