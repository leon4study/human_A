import { memo } from "react";
import { SprayAnimation } from "../equipment/SprayAnimation";
import {
  nutrientFeedSmallValveY,
  nutrientMixerPortYs,
  nutrientTanks,
  valvePositions,
  waterJointPositions,
} from "../model/facility.layout";
import {
  facilityMainPipePaths,
  getBranchPipePath,
  getNutrientFeedPath,
} from "../model/facility.paths";
import { staticEquipmentStatus } from "../model/facility.status";
import { PipeJoint, PipeRun, SmallValve } from "./FacilityPipes";

function FacilityPipeLayoutImpl() {
  return (
    <>
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

        {/* 원수 공급 라인 */}
        <PipeRun
          d={facilityMainPipePaths.rawWaterMain}
          tone="water"
          width={0.6}
          flowWidth={0.22}
        />

        {/* 각 탱크 → 자동공급기 우측 포트 1:1 연결 */}
        {nutrientTanks.map((tank, i) => {
          const portY = nutrientMixerPortYs[i];
          return (
            <PipeRun
              key={`nutrient-feed-${tank.id}`}
              d={getNutrientFeedPath(tank.x, portY)}
              tone="nutrient"
              width={0.55}
              flowWidth={0.4}
              duration="2.2s"
              flowColor={tank.color}
              bodyColor="#94a3b8"
              shellColor="#475569"
            />
          );
        })}

        {/* 각 탱크 바로 아래 피드 파이프에 붙는 작은 밸브 */}
        {nutrientTanks.map((tank) => (
          <SmallValve
            key={`nutrient-valve-${tank.id}`}
            x={tank.x}
            y={nutrientFeedSmallValveY}
            isOpen={true}
          />
        ))}

        {/* 자동공급기에서 하단 분기 전까지 내려오는 메인 라인 */}
        <PipeRun
          d={facilityMainPipePaths.supplyMainVertical}
          tone="nutrient"
          width={0.7}
          flowWidth={0.26}
          duration="1.6s"
        />

        {/* 메인 라인이 좌우 재배 구역으로 갈라지는 수평 구간 */}
        <PipeRun
          d={facilityMainPipePaths.supplyMainRight}
          tone="nutrient"
          width={0.9}
          flowWidth={0.34}
          duration="1.9s"
        />
        <PipeRun
          d={facilityMainPipePaths.supplyMainLeft}
          tone="nutrient"
          width={0.9}
          flowWidth={0.34}
          duration="1.9s"
        />

        {/* 상단 원수 라인 연결 지점 */}
        {waterJointPositions.map((x) => (
          <PipeJoint key={`joint-${x}`} x={x} y={17.8} tone="water" />
        ))}

        {/* 탱크 피드 파이프 꺾이는 지점 + 자동공급기 입력 포트 */}
        {nutrientTanks.map((tank, i) => {
          const portY = nutrientMixerPortYs[i];
          return (
            <g key={`nutrient-corner-${tank.id}`}>
              <PipeJoint x={tank.x} y={portY} tone="nutrient" size={0.18} />
              <PipeJoint x={54.9} y={portY} tone="nutrient" size={0.12} />
            </g>
          );
        })}

        <PipeJoint x={55.5} y={55} tone="nutrient" size={0.13} />
      </svg>

      {/* 하단 분기관 오버레이 — 밸브 상태에 따라 흐름 표시 여부 결정 */}
      <svg
        className="facility-background-svg"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        style={{ zIndex: 31 }}
      >
        {valvePositions.map((x, i) => (
          <PipeRun
            key={`branch-overlay-${x}`}
            d={getBranchPipePath(x)}
            tone="nutrient"
            width={0.6}
            flowWidth={0.22}
            duration="1.5s"
            flowing={staticEquipmentStatus.valves[i]}
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

      {/* 밸브 개방 여부에 따라 표시되는 분사 애니메이션 */}
      <svg
        className="facility-background-svg"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        style={{ zIndex: 32 }}
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
    </>
  );
}

export const FacilityPipeLayout = memo(FacilityPipeLayoutImpl);