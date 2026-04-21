import { memo } from "react";
import { SprayAnimation } from "../../../equipment/SprayAnimation";
import {
  nutrientFeedSmallValveY,
  nutrientMixerPortX,
  nutrientMixerPortYs,
  nutrientTankPipeStartY,
  nutrientTanks,
  valvePositions,
  waterJointPositions,
} from "../model/facility.layout";
import { staticEquipmentStatus } from "../model/facility.status";
import { PipeJoint, PipeRun, SmallValve } from "./FacilityPipes";

// 배관 경로와 유량/분사 애니메이션 배치를 담당하는 레이어
function FacilityPipeLayoutImpl() {
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
        <PipeRun d="M 18 17.8 H 54" tone="water" width={0.6} flowWidth={0.22} />
        

        {/*
          각 탱크 → 자동공급기 우측 포트 1:1 개별 연결 (L자 경로)
          - 수직: 탱크 하단(y=nutrientTankPipeStartY)에서 포트 y까지
          - 수평: 포트 y에서 자동공급기 우측 포트 x까지
          - 흐름 점선 색은 탱크별 액체 색상(tank.color)으로 override
        */}
        {nutrientTanks.map((tank, i) => {
          const portY = nutrientMixerPortYs[i];
          return (
            <PipeRun
              key={`nutrient-feed-${tank.id}`}
              d={`M ${tank.x} ${nutrientTankPipeStartY} V ${portY} H ${nutrientMixerPortX}`}
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
          d="M 50 20 V 55"
          tone="nutrient"
          width={0.7}
          flowWidth={0.26}
          duration="1.6s"
        />

        {/* 메인 라인이 좌우 재배 구역으로 갈라지는 수평 구간 */}
        <PipeRun
          d="M 50.6 55 H 74.8"
          tone="nutrient"
          width={0.9}
          flowWidth={0.34}
          duration="1.9s"
        />
        <PipeRun
          d="M 49.8 55 H 25.2"
          tone="nutrient"
          width={0.9}
          flowWidth={0.34}
          duration="1.9s"
        />

        {/* 상단 원수 라인의 연결 지점 */}
        {waterJointPositions.map((x) => (
          <PipeJoint key={`joint-${x}`} x={x} y={17.8} tone="water" />
        ))}

        {/* 각 탱크 피드 파이프의 꺾이는 지점(L자 모서리) + 자동공급기 입력 포트 */}
        {nutrientTanks.map((tank, i) => {
          const portY = nutrientMixerPortYs[i];
          return (
            <g key={`nutrient-corner-${tank.id}`}>
              {/* 수직→수평 꺾이는 모서리 */}
              <PipeJoint x={tank.x} y={portY} tone="nutrient" size={0.18} />
              {/* 자동공급기 입력 포트 연결부 */}
              <PipeJoint
                x={nutrientMixerPortX}
                y={portY}
                tone="nutrient"
                size={0.12}
              />
            </g>
          );
        })}

        {/* 하단 메인 분기 지점 */}
        <PipeJoint x={55.5} y={55} tone="nutrient" size={0.13} />
      </svg>

      {/*
        하단 분기관 오버레이
        - 밸브 아래로 내려가는 세 갈래 분기관
        - 밸브 접점 조인트
        - 밭 카드(z-index 30)보다 위에 그려지도록 31로 설정
      */}
      <svg
        className="facility-background-svg"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        style={{ zIndex: 31 }}
      >
        {valvePositions.map((x, i) => (
          <PipeRun
            key={`branch-overlay-${x}`}
            d={`M ${x} 55 V 57.8 Q ${x} 59 ${x - 0.4} 60.2 V 90`}
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

      {/* 밸브 개방 여부에 따라 표시되는 분사 애니메이션 (밭 카드 위) */}
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

// props 없이 항상 동일한 결과 → memo로 리렌더 차단
export const FacilityPipeLayout = memo(FacilityPipeLayoutImpl);
