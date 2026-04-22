import { memo } from "react";
import { motion } from "framer-motion";
import { growingZones } from "../model/facility.layout";

type FacilityZonesProps = {
  onEquipmentClick: (id: string) => void;
};

// 하단 재배 베드 시각화와 클릭 영역을 렌더링
function FacilityZonesImpl({ onEquipmentClick }: FacilityZonesProps) {
  return (
    <>
      {growingZones.map((zone, index) => (
        <motion.div
          key={zone.title}
          className="facility-zone-wrap facility-zone-wrap--clickable"
          style={{ left: zone.left, top: "63%" }}
          whileHover={{ scale: 1.04, y: -4 }}
          transition={{ type: "spring", stiffness: 240, damping: 18 }}
          onClick={() => onEquipmentClick(`growingZone${index + 1}`)}
        >
          <div className="facility-zone-card">
            {/* 베드 상단의 은은한 조명 표현 */}
            <div className="facility-zone-glow" />
            {/* 베드 내부 흙/배지 표현 */}
            <div className="facility-zone-soil" />

            {/* 좌우 두 줄 재배 베드를 동일한 패턴으로 렌더링 */}
            {[0, 1].map((column) => (
              <div
                key={column}
                className="facility-zone-column"
                style={{ left: `${20 + column * 32}%` }}
              >
                {/* 베드 기둥의 입체감을 주는 좌우 그림자 */}
                <div className="facility-zone-column-shadow-left" />
                <div className="facility-zone-column-shadow-right" />

                {/* 각 베드 컬럼 안의 작물 반복 표현 */}
                {[0, 1, 2, 3, 4].map((crop) => (
                  <div
                    key={crop}
                    className="facility-crop"
                    style={{ top: `${8 + crop * 18}%` }}
                  >
                    {/* 줄기 */}
                    <div
                      className="facility-crop-stem"
                      style={{ boxShadow: `0 0 8px ${zone.accent}30` }}
                    />
                    {/* 좌측 잎 */}
                    <div
                      className="facility-crop-leaf-left"
                      style={{ border: `1px solid ${zone.accent}66` }}
                    />
                    {/* 우측 잎 */}
                    <div
                      className="facility-crop-leaf-right"
                      style={{ border: `1px solid ${zone.accent}55` }}
                    />
                    {/* 열매 포인트 */}
                    <div
                      className="facility-crop-fruit"
                      style={{
                        backgroundColor: zone.accent,
                        opacity: 0.9,
                      }}
                    />
                  </div>
                ))}
              </div>
            ))}

            <div className="facility-zone-title">{/* zone.title */}</div>
          </div>
        </motion.div>
      ))}
    </>
  );
}

// onEquipmentClick이 안정적이라면 sensorData 변경에도 리렌더되지 않도록 memo
export const FacilityZones = memo(FacilityZonesImpl);
