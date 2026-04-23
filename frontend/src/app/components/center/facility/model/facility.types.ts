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
}

// 배관 표현에 사용하는 라인 톤
export type PipeTone = "water" | "nutrient" | "steel";

// 중앙 모델링에서 순환되는 센서 값 상태
export type SensorData = {
  waterLevel: number;
  ph: number;
  ec: number;
  temperature: number;
  pressure: number;
};
