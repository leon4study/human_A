// 시설 모델링에서 공통으로 사용하는 장비 분류 키
export type EquipmentCategory =
  | "storage"
  | "treatment"
  | "transfer"
  | "control"
  | "distribution"
  | "zone";

// 장비 상세 모달에 전달되는 표준 데이터 형태
export type Equipment = {
  id: string;
  name: string;
  type: string;
  category: string;
  status: string;
  currentValue?: number;
  unit?: string;
  history?: { time: string; value: number }[];
  additionalInfo?: Record<string, string>;
};

export interface FacilityDiagramProps {
  onEquipmentSelect?: (equipment: Equipment) => void;
  sensorData?: SensorData;
}

// 배관 표현에 사용하는 라인 톤
export type PipeTone = "water" | "nutrient" | "steel";

// 중앙 모델링에서 순환되는 센서 값 상태
export type SensorData = {
  waterLevel: number; // 원수 탱크 수위 (raw_tank_level_pct)
  ph: number;
  ec: number;
  temperature: number;
  pressure: number;
  tankALevel: number; // 양액 A 수위 (tank_a_level_pct)
  tankBLevel: number; // 양액 B 수위 (tank_b_level_pct)
  acidTankLevel: number; // pH 조절액(산) 수위 (acid_tank_level_pct)
};

// SensorData에 저장되는 탱크 수위 키 (nutrientTanks.levelKey 에서 사용)
export type TankLevelKey =
  | "waterLevel"
  | "tankALevel"
  | "tankBLevel"
  | "acidTankLevel";
