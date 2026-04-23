import type { SensorData } from "./facility.types";

// 설비의 고정 동작 상태
export const staticEquipmentStatus = {
  rawWaterPump: true,
  valves: [true, false, true],
  nutrientFeedValves: [true, true, true, true, false],
} as const;

// 센서 시뮬레이션의 초기값
export const initialSensorData: SensorData = {
  waterLevel: 75,
  ph: 6.2,
  ec: 1.5,
  temperature: 22,
  pressure: 2.5,
  tankALevel: 82,
  tankBLevel: 76,
  acidTankLevel: 68,
};
