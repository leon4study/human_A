import {
  nutrientMixerPortX,
  nutrientTankPipeStartY,
} from "./facility.layout";

// 고정 메인 파이프 경로
export const facilityMainPipePaths = {
  rawWaterMain: "M 18 17.8 H 54",
  supplyMainVertical: "M 50 20 V 55",
  supplyMainRight: "M 50.6 55 H 74.8",
  supplyMainLeft: "M 49.8 55 H 25.2",
} as const;

// 각 탱크 → 자동공급기 포트 연결 경로
export function getNutrientFeedPath(tankX: number, portY: number) {
  return `M ${tankX} ${nutrientTankPipeStartY} V ${portY} H ${nutrientMixerPortX}`;
}

// 하단 분기관 경로
export function getBranchPipePath(x: number) {
  return `M ${x} 55 V 57.8 Q ${x} 59 ${x - 0.4} 60.2 V 90`;
}