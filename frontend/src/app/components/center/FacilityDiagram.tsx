import { useEffect, useState } from "react";

import { initialSensorData } from "./facility/model/facility.status";
import type {
  FacilityDiagramProps,
  SensorData,
} from "./facility/model/facility.types";
import { FacilityEquipment } from "./facility/render/FacilityEquipment";
import { FacilityPipeLayout } from "./facility/render/FacilityPipeLayout";
import { FacilityZones } from "./facility/render/FacilityZones";
import { createEquipment } from "./facility/utils/facilityEquipment";

import "./facility/facility-diagram.css";

// 중앙 시설 모델링 화면의 조립을 담당하는 메인 컴포넌트
function FacilityDiagram({ onEquipmentSelect }: FacilityDiagramProps) {
  const [sensorData, setSensorData] = useState<SensorData>(initialSensorData);

  useEffect(() => {
    const interval = setInterval(() => {
      setSensorData((prev) => ({
        waterLevel: Math.min(
          100,
          Math.max(0, prev.waterLevel + (Math.random() - 0.5) * 2),
        ),
        ph: Math.max(
          5.5,
          Math.min(7.5, prev.ph + (Math.random() - 0.5) * 0.1),
        ),
        ec: Math.max(
          1.0,
          Math.min(2.5, prev.ec + (Math.random() - 0.5) * 0.05),
        ),
        temperature: Math.max(
          18,
          Math.min(28, prev.temperature + (Math.random() - 0.5) * 0.3),
        ),
        pressure: Math.max(
          1.5,
          Math.min(3.5, prev.pressure + (Math.random() - 0.5) * 0.1),
        ),
      }));
    }, 2000);

    return () => clearInterval(interval);
  }, []);

  const handleEquipmentClick = (
    id: string,
    currentValue?: number,
    unit?: string,
  ) => {
    const equipment = createEquipment(id, sensorData, currentValue, unit);
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
              sensorData={sensorData}
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
