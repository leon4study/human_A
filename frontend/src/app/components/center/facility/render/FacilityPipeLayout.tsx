import { SprayAnimation } from "../../../equipment/SprayAnimation";
import {
  nutrientManifoldY,
  nutrientTankPipeStartY,
  nutrientTanks,
  valvePositions,
  waterJointPositions,
} from "../model/facility.layout";
import { staticEquipmentStatus } from "../model/facility.status";
import { PipeJoint, PipeRun } from "./FacilityPipes";

// 배관 경로와 유량/분사 애니메이션 배치를 담당하는 레이어
export function FacilityPipeLayout() {
  return (
    <>
      {/* 
        메인 공급/회수 배관 레이어
        - 상단 원수 라인
        - 탱크 상단 매니폴드
        - 각 탱크 연결 배관
        - 중앙에서 좌우로 퍼지는 메인 양액 라인
      */}
      <svg
        className="facility-background-svg"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        style={{ zIndex: 0 }}
      >
        <defs>
          {/* 매니폴드 중심부 발광 */}
          <radialGradient id="manifoldGlow">
            <stop offset="0%" stopColor="#fb923c" stopOpacity="0.55" />
            <stop offset="100%" stopColor="#fb923c" stopOpacity="0" />
          </radialGradient>

          {/* 상단 수평 라인 연결부 발광 */}
          <radialGradient id="junctionGlow">
            <stop offset="0%" stopColor="#93c5fd" stopOpacity="0.55" />
            <stop offset="100%" stopColor="#93c5fd" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* 주요 배관 중심 포인트 */}
        <circle cx="55.2" cy="54.6" r="0.32" fill="url(#manifoldGlow)" />
        <circle cx="41.3" cy="17.8" r="0.23" fill="url(#junctionGlow)" />

        {/* 원수 공급 라인 */}
        <PipeRun d="M 10.8 17.8 H 20" tone="water" width={0.6} flowWidth={0.22} />
        <PipeRun d="M 21 17.8 H 40" tone="water" width={0.6} flowWidth={0.22} />
        <PipeRun d="M 40 17.8 H 54" tone="water" width={0.6} flowWidth={0.22} />

        {/* 탱크 상단 세로/가로 매니폴드 */}
        <PipeRun
          d={`M 59.4 17.8 V ${nutrientManifoldY} H 95`}
          tone="steel"
          width={0.5}
          flowWidth={0.18}
          duration="2.2s"
          reverseFlow
        />

        {/* 각 탱크와 상단 매니폴드를 연결하는 세로 배관 */}
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

        {/* 자동공급기에서 하단 분기 전까지 내려오는 메인 라인 */}
        <PipeRun
          d="M 55.5 20 V 55"
          tone="nutrient"
          width={0.7}
          flowWidth={0.26}
          duration="1.6s"
        />

        {/* 메인 라인이 좌우 재배 구역으로 갈라지는 수평 구간 */}
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

        {/* 상단 원수 라인의 연결 지점 */}
        {waterJointPositions.map((x) => (
          <PipeJoint key={`joint-${x}`} x={x} y={17.8} tone="water" />
        ))}

        {/* 메인 매니폴드 연결 지점 */}
        <PipeJoint x={59.4} y={17.8} tone="steel" size={0.12} />
        <PipeJoint x={59.4} y={nutrientManifoldY} tone="steel" size={0.12} />

        {/* 각 탱크 매니폴드 연결 지점 */}
        {nutrientTanks.map((tank) => (
          <PipeJoint
            key={`nutrient-manifold-${tank.id}`}
            x={tank.x + 2.15}
            y={nutrientManifoldY}
            tone="steel"
            size={0}
          />
        ))}

        {/* 하단 메인 분기 지점 */}
        <PipeJoint x={94.2} y={nutrientManifoldY} tone="steel" size={0.12} />
        <PipeJoint x={55.5} y={55} tone="nutrient" size={0.13} />
      </svg>

      {/* 
        하단 분기관 오버레이
        - 밸브 아래로 내려가는 세 갈래 분기관
        - 밸브 접점 조인트
      */}
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

      {/* 밸브 개방 여부에 따라 표시되는 분사 애니메이션 */}
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
    </>
  );
}
