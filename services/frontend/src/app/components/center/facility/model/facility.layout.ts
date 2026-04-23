import type { TankLevelKey } from "./facility.types";

// 양액 탱크 표시 정보
//  - levelKey: SensorData 필드 키 (실시간 수위를 이 키로 조회)
//  - fallbackLevel: 센서 매핑이 없는 첨가제 탱크용 정적 수위
export interface NutrientTankLayout {
  id: string;
  label: string;
  color: string;
  x: number;
  levelKey?: TankLevelKey;
  fallbackLevel?: number;
}

export const nutrientTanks: NutrientTankLayout[] = [
  { id: "tankA", label: "양액 A", color: "#eab308", x: 65, levelKey: "tankALevel" },
  { id: "tankB", label: "양액 B", color: "#22c55e", x: 70.5, levelKey: "tankBLevel" },
  { id: "tankPH", label: "pH 조절제", color: "#a855f7", x: 76, levelKey: "acidTankLevel" },
  { id: "tankD", label: "임의 액", color: "#5a718f", x: 81.5, fallbackLevel: 45 },
  { id: "tankE", label: "임의 액", color: "#64748b", x: 87, fallbackLevel: 55 },
];

export const valvePositions = [25, 50, 75] as const;
export const valveCardLeftPositions = ["23.45%", "48.45%", "73.45%"] as const;

// 상단 매니폴드 및 탱크 연결관 위치
export const nutrientTankPipeStartY = 11;
export const nutrientManifoldY = 1.8;

// 양액 자동공급기 우측 입력 포트 위치
export const nutrientMixerPortX = 54.9;
export const nutrientMixerPortYs = [18.1, 20.1, 22.1, 24.1, 26.1] as const;

// 각 피드 파이프 수직 구간 상단(탱크 바로 아래)에 놓이는 작은 밸브의 y 좌표
export const nutrientFeedSmallValveY = 13;

// 장비 카드 위치값
// 디자인/위치 변경 없이 기존 값을 그대로 모아둔 것
export const facilityEquipmentPositions = {
  rawWaterTank: { left: "13%", top: "-1.5%" },
  filter: { left: "25%", top: "11.2%" },
  rawWaterPump: { left: "35%", top: "12.5%" },
  autoSupply: { left: "44.2%", top: "10.1%" },
  nutrientTankTop: "0%",
  valveTop: "52.5%",
  valveZIndex: 33,
} as const;

// 하단 재배 구역 카드 배치 데이터
export const growingZones = [
  { left: "19.5%", title: "1구역 딸기 재배지", ph: "6.2", ec: "1.4", accent: "#f472b6" },
  { left: "44.5%", title: "2구역 딸기 재배지", ph: "6.3", ec: "1.5", accent: "#fb7185" },
  { left: "69.5%", title: "3구역 딸기 재배지", ph: "6.1", ec: "1.3", accent: "#f43f5e" },
] as const;

export const waterJointPositions = [17, 21, 39, 43.8, 50.8, 55.2] as const;