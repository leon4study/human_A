import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { ControllerSVG } from "../equipment/ControllerSVG";
import { FilterSVG } from "../equipment/FilterSVG";
import { PumpSVG } from "../equipment/PumpSVG";
import { SprayAnimation } from "../equipment/SprayAnimation";
import { TankSVG } from "../equipment/TankSVG";
import { ValveSVG } from "../equipment/ValveSVG";

import type {
  FacilityDiagramProps,
  SensorData,
} from "./facility/facilityTypes";
import {
  growingZones,
  initialSensorData,
  nutrientManifoldY,
  nutrientTankPipeStartY,
  nutrientTanks,
  staticEquipmentStatus,
  valveCardLeftPositions,
  valvePositions,
  waterJointPositions,
} from "./facility/facilityData";
import { createEquipment } from "./facility/facilityUtils";
import { PipeJoint, PipeRun } from "./facility/FacilityPipes";

import "./facility/facility-diagram.css";

// 설비 도식화 메인 컴포넌트
function FacilityDiagram({ onEquipmentSelect }: FacilityDiagramProps) {
  // 센서 데이터 상태값
  const [sensorData, setSensorData] = useState<SensorData>(initialSensorData);

  // 센서값 변동 애니메이션용 useEffect
  useEffect(() => {
    const interval = setInterval(() => {
      setSensorData((prev) => ({
        waterLevel: Math.min(
          100,
          Math.max(0, prev.waterLevel + (Math.random() - 0.5) * 2),
        ),
        ph: Math.max(5.5, Math.min(7.5, prev.ph + (Math.random() - 0.5) * 0.1)),
        ec: Math.max(1.0, Math.min(2.5, prev.ec + (Math.random() - 0.5) * 0.05)),
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

  // 장비 클릭 시 팝업으로 전달할 장비 데이터 생성
  const handleEquipmentClick = (
    id: string,
    name: string,
    type: string,
    currentValue?: number,
    unit?: string,
  ) => {
    const equipment = createEquipment(
      id,
      name,
      type,
      sensorData,
      currentValue,
      unit,
    );

    if (onEquipmentSelect) {
      onEquipmentSelect(equipment);
    }
  };

  return (
    <div className="facility-diagram-wrap">
      {/* 전체 중앙 정렬 영역 */}
      <div className="facility-diagram-center">
        {/* 실제 설비 도식화 전체 영역 */}
        <div className="facility-diagram-inner">
          {/* 배경 배관 SVG */}
          <svg
            className="facility-background-svg"
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            style={{ zIndex: 0 }}
          >
            <defs>
              <radialGradient id="manifoldGlow">
                <stop offset="0%" stopColor="#fb923c" stopOpacity="0.55" />
                <stop offset="100%" stopColor="#fb923c" stopOpacity="0" />
              </radialGradient>

              <radialGradient id="junctionGlow">
                <stop offset="0%" stopColor="#93c5fd" stopOpacity="0.55" />
                <stop offset="100%" stopColor="#93c5fd" stopOpacity="0" />
              </radialGradient>
            </defs>

            <circle cx="55.2" cy="54.6" r="0.32" fill="url(#manifoldGlow)" />
            <circle cx="41.3" cy="17.8" r="0.23" fill="url(#junctionGlow)" />

            <PipeRun
              d="M 10.8 17.8 H 20"
              tone="water"
              width={0.6}
              flowWidth={0.22}
            />
            <PipeRun
              d="M 21 17.8 H 40"
              tone="water"
              width={0.6}
              flowWidth={0.22}
            />
            <PipeRun
              d="M 40 17.8 H 54"
              tone="water"
              width={0.6}
              flowWidth={0.22}
            />

            <PipeRun
              d={`M 59.4 17.8 V ${nutrientManifoldY} H 95`}
              tone="steel"
              width={0.5}
              flowWidth={0.18}
              duration="2.2s"
              reverseFlow
            />

            {nutrientTanks.map((tank) => (
              <PipeRun
                key={tank.id}
                d={`M ${tank.x} ${nutrientManifoldY} V ${nutrientTankPipeStartY}`}
                tone="steel"
                width={0.36}
                flowWidth={0.13}
                duration="2.4s"
                reverseFlow
              />
            ))}

            <PipeRun
              d="M 55.5 20 V 55"
              tone="nutrient"
              width={0.7}
              flowWidth={0.26}
              duration="1.6s"
            />
            <PipeRun
              d="M 55.5 55 H 72"
              tone="nutrient"
              width={0.9}
              flowWidth={0.34}
              duration="1.9s"
            />
            <PipeRun
              d="M 55.4 55 H 20"
              tone="nutrient"
              width={0.9}
              flowWidth={0.34}
              duration="1.9s"
            />

            {waterJointPositions.map((x) => (
              <PipeJoint key={`joint-${x}`} x={x} y={17.8} tone="water" />
            ))}

            <PipeJoint x={59.4} y={17.8} tone="steel" size={0.12} />
            <PipeJoint x={59.4} y={nutrientManifoldY} tone="steel" size={0.12} />

            {nutrientTanks.map((tank) => (
              <PipeJoint
                key={`nutrient-manifold-${tank.id}`}
                x={tank.x + 2.15}
                y={nutrientManifoldY}
                tone="steel"
                size={0}
              />
            ))}

            <PipeJoint x={94.2} y={nutrientManifoldY} tone="steel" size={0.12} />
            <PipeJoint x={55.5} y={55} tone="nutrient" size={0.13} />
          </svg>

          {/* 장비와 구역 렌더링 영역 */}
          <div className="facility-content-area">
            {/* 원수 탱크 */}
            <motion.div
              className="facility-equipment-item facility-equipment-item--tank"
              style={{ left: "2.5%", top: "-1.5%" }}
              whileHover={{ scale: 1.05, y: -3 }}
              transition={{ type: "spring", stiffness: 260, damping: 18 }}
              onClick={() =>
                handleEquipmentClick(
                  "rawWaterTank",
                  "원수 탱크",
                  "저장탱크",
                  sensorData.waterLevel,
                  "%",
                )
              }
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

            {/* 필터 */}
            <motion.div
              className="facility-equipment-item facility-equipment-item--filter"
              style={{ left: "16%", top: "11%" }}
              whileHover={{ scale: 1.05, y: -3 }}
              transition={{ type: "spring", stiffness: 260, damping: 18 }}
              onClick={() => handleEquipmentClick("filter", "필터", "여과장치")}
            >
              <FilterSVG width={70} height={100} />
              <div className="facility-label-wrap">
                <div className="facility-label-title">필터</div>
              </div>
            </motion.div>

            {/* 원수 펌프 */}
            <motion.div
              className="facility-equipment-item facility-equipment-item--pump"
              style={{ left: "35.5%", top: "12.5%" }}
              whileHover={{ scale: 1.05, y: -3 }}
              transition={{ type: "spring", stiffness: 260, damping: 18 }}
              onClick={() =>
                handleEquipmentClick("rawWaterPump", "원수 펌프", "펌프")
              }
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

            {/* 양액 자동공급기 */}
            <motion.div
              className="facility-equipment-item facility-equipment-item--controller"
              style={{ left: "50%", top: "10.1%" }}
              whileHover={{ scale: 1.05, y: -3 }}
              transition={{ type: "spring", stiffness: 260, damping: 18 }}
              onClick={() =>
                handleEquipmentClick(
                  "autoSupply",
                  "양액 자동공급기",
                  "자동공급장치",
                )
              }
            >
              <ControllerSVG width={120} height={150} />
              <div className="facility-label-wrap">
                <div className="facility-label-title">양액 자동공급기</div>
              </div>
            </motion.div>

            {/* 원액 탱크들 */}
            {nutrientTanks.map((tank) => (
              <motion.div
                key={tank.id}
                className="facility-equipment-item facility-equipment-item--nutrient"
                style={{ left: `${tank.x - 0.8}%`, top: "3%" }}
                whileHover={{ scale: 1.05, y: -3 }}
                transition={{ type: "spring", stiffness: 260, damping: 18 }}
                onClick={() =>
                  handleEquipmentClick(
                    tank.id,
                    tank.label,
                    "원액탱크",
                    tank.level,
                    "%",
                  )
                }
              >
                <TankSVG
                  fillLevel={tank.level}
                  color={tank.color}
                  label={tank.id}
                  width={65}
                  height={80}
                />
                <div className="facility-label-wrap">
                  <div className="facility-label-small">{tank.label}</div>
                </div>
              </motion.div>
            ))}

            {/* 밸브 */}
            {staticEquipmentStatus.valves.map((isOpen, i) => (
              <motion.div
                key={`valve-${i}`}
                className="facility-equipment-item facility-equipment-item--valve"
                style={{ left: valveCardLeftPositions[i], top: "52%", zIndex: 30 }}
                whileHover={{ scale: 1.15 }}
                transition={{ type: "spring", stiffness: 260, damping: 18 }}
                onClick={() =>
                  handleEquipmentClick(`valve${i + 1}`, `밸브 ${i + 1}`, "분기밸브")
                }
              >
                <ValveSVG isOpen={isOpen} size={35} />
                <div className="facility-label-wrap">
                  <div className="facility-label-valve">V{i + 1}</div>
                </div>
              </motion.div>
            ))}

            {/* 분기 배관 오버레이 */}
            <svg
              className="facility-background-svg"
              viewBox="0 0 100 100"
              preserveAspectRatio="none"
              style={{ zIndex: 28 }}
            >
              {valvePositions.map((x) => (
                <PipeRun
                  key={`branch-overlay-${x}`}
                  d={`M ${x} 55 V 57.8 Q ${x} 59 ${x - 0.4} 60.2 V 90`}
                  tone="nutrient"
                  width={0.6}
                  flowWidth={0.22}
                  duration="1.5s"
                />
              ))}

              {valvePositions.map((x) => (
                <PipeJoint
                  key={`valve-joint-overlay-${x}`}
                  x={x}
                  y={55}
                  tone="nutrient"
                  size={0.125}
                />
              ))}
            </svg>

            {/* 물 분사 애니메이션 */}
            <svg
              className="facility-background-svg"
              viewBox="0 0 100 100"
              preserveAspectRatio="none"
              style={{ zIndex: 29 }}
            >
              {staticEquipmentStatus.valves.map((isOpen, i) => (
                <SprayAnimation
                  key={i}
                  x={valvePositions[i] - 0.4}
                  y={69}
                  isActive={isOpen}
                />
              ))}
            </svg>

            {/* 재배 구역 카드 */}
            {growingZones.map((zone, index) => (
              <motion.div
                key={zone.title}
                className="facility-zone-wrap facility-zone-wrap--clickable"
                style={{ left: zone.left, top: "63%" }}
                whileHover={{ scale: 1.04, y: -4 }}
                transition={{ type: "spring", stiffness: 240, damping: 18 }}
                onClick={() =>
                  handleEquipmentClick(
                    `growingZone${index + 1}`,
                    zone.title,
                    "재배구역",
                  )
                }
              >
                <div className="facility-zone-card">
                  <div className="facility-zone-glow" />
                  <div className="facility-zone-soil" />

                  {[0, 1].map((column) => (
                    <div
                      key={column}
                      className="facility-zone-column"
                      style={{ left: `${20 + column * 32}%` }}
                    >
                      <div className="facility-zone-column-shadow-left" />
                      <div className="facility-zone-column-shadow-right" />

                      {[0, 1, 2, 3, 4].map((crop) => (
                        <div
                          key={crop}
                          className="facility-crop"
                          style={{ top: `${8 + crop * 18}%` }}
                        >
                          <div
                            className="facility-crop-stem"
                            style={{ boxShadow: `0 0 8px ${zone.accent}30` }}
                          />
                          <div
                            className="facility-crop-leaf-left"
                            style={{ border: `1px solid ${zone.accent}66` }}
                          />
                          <div
                            className="facility-crop-leaf-right"
                            style={{ border: `1px solid ${zone.accent}55` }}
                          />
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

                  <div className="facility-zone-title">{/*zone.title*/}</div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default FacilityDiagram;