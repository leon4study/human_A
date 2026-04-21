import { motion } from "framer-motion";
import { FilterSVG } from "../../../equipment/FilterSVG";
import { NutrientSupplierSVG } from "../../../equipment/NutrientSupplierSVG";
import { PumpSVG } from "../../../equipment/PumpSVG";
import { TankSVG } from "../../../equipment/TankSVG";
import { ValveSVG } from "../../../equipment/ValveSVG";
import { nutrientTanks, valveCardLeftPositions } from "../model/facility.layout";
import { staticEquipmentStatus } from "../model/facility.status";
import type { SensorData } from "../model/facility.types";

type FacilityEquipmentProps = {
  sensorData: SensorData;
  onEquipmentClick: (id: string, currentValue?: number, unit?: string) => void;
};

// 장비 SVG와 상태 표시를 렌더링하는 레이어
export function FacilityEquipment({
  sensorData,
  onEquipmentClick,
}: FacilityEquipmentProps) {
  return (
    <>
      {/* 원수 저장 탱크 */}
      <motion.div
        className="facility-equipment-item facility-equipment-item--tank"
        style={{ left: "13%", top: "-1.5%" }}
        whileHover={{ scale: 1.05, y: -3 }}
        transition={{ type: "spring", stiffness: 260, damping: 18 }}
        onClick={() => onEquipmentClick("rawWaterTank", sensorData.waterLevel, "%")}
      >
        <TankSVG
          fillLevel={sensorData.waterLevel}
          color="#3b82f6"
          label="rawWater"
          width={110}
          height={140}
        />
        <div className="facility-label-wrap">
          <div className="facility-label-title">원수 탱크</div>
        </div>
      </motion.div>

      {/* 원수 여과 장치 */}
      <motion.div
        className="facility-equipment-item facility-equipment-item--filter"
        style={{ left: "25%", top: "11.2%" }}
        whileHover={{ scale: 1.05, y: -3 }}
        transition={{ type: "spring", stiffness: 260, damping: 18 }}
        onClick={() => onEquipmentClick("filter")}
      >
        <FilterSVG width={70} height={100} />
        <div className="facility-label-wrap">
          <div className="facility-label-title">필터</div>
        </div>
      </motion.div>

      {/* 원수 이송 펌프 */}
      <motion.div
        className="facility-equipment-item facility-equipment-item--pump"
        style={{ left: "35%", top: "12.5%" }}
        whileHover={{ scale: 1.05, y: -3 }}
        transition={{ type: "spring", stiffness: 260, damping: 18 }}
        onClick={() => onEquipmentClick("rawWaterPump")}
      >
        <PumpSVG
          isActive={staticEquipmentStatus.rawWaterPump}
          width={80}
          height={80}
        />
        <div className="facility-label-wrap">
          <div className="facility-label-title">원수 펌프</div>
          <div
            className={
              staticEquipmentStatus.rawWaterPump
                ? "facility-status-on"
                : "facility-status-off"
            }
          >
            {staticEquipmentStatus.rawWaterPump ? "ON" : "OFF"}
          </div>
        </div>
      </motion.div>

      {/* 양액 자동공급 제어 장치 */}
      <motion.div
        className="facility-equipment-item facility-equipment-item--controller"
        style={{ left: "44.2%", top: "10.1%" }}
        whileHover={{ scale: 1.05, y: -3 }}
        transition={{ type: "spring", stiffness: 260, damping: 18 }}
        onClick={() => onEquipmentClick("autoSupply")}
      >
        <NutrientSupplierSVG width={130} height={160} />
        <div className="facility-label-wrap">
          <div className="facility-label-title">양액 자동공급기</div>
        </div>
      </motion.div>

      {/* 상단 양액/첨가제 탱크 묶음 */}
      {nutrientTanks.map((tank) => {
        const level = tank.levelKey
          ? sensorData[tank.levelKey]
          : (tank.fallbackLevel ?? 0);

        return (
          <motion.div
            key={tank.id}
            className="facility-equipment-item facility-equipment-item--nutrient"
            style={{ left: `${tank.x - 5}%`, top: "0%" }}
            whileHover={{ scale: 1.05, y: -3 }}
            transition={{ type: "spring", stiffness: 260, damping: 18 }}
            onClick={() => onEquipmentClick(tank.id, level, "%")}
          >
            <TankSVG
              fillLevel={level}
              color={tank.color}
              label={tank.id}
              width={65}
              height={80}
            />
            <div className="facility-label-wrap">
              <div className="facility-label-small">{tank.label}</div>
            </div>
          </motion.div>
        );
      })}

      {/* 하단 분기 밸브 */}
      {staticEquipmentStatus.valves.map((isOpen, i) => (
        <motion.div
          key={`valve-${i}`}
          className="facility-equipment-item facility-equipment-item--valve"
          style={{ left: valveCardLeftPositions[i], top: "52.5%", zIndex: 33 }}
          whileHover={{ scale: 1.15 }}
          transition={{ type: "spring", stiffness: 260, damping: 18 }}
          onClick={() => onEquipmentClick(`valve${i + 1}`)}
        >
          <ValveSVG isOpen={isOpen} size={35} />
          <div className="facility-label-wrap">
            <div className="facility-label-valve">V{i + 1}</div>
          </div>
        </motion.div>
      ))}
    </>
  );
}
