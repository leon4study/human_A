// 장비 데이터 타입 정의
export type Equipment = {
  id: string;   // 장비 id
  name: string;   // 장비 이름
  type: string;   // 장비 종류
  status: string;   // 현재 상태
  currentValue?: number;   // 현재 값
  unit?: string;   // 단위
  history?: { time: string; value: number }[];   // 히스토리 데이터
  additionalInfo?: Record<string, string>;   // 추가정보 (key-value 형태)
};

// FacilityDiagram 컴포넌트 props
export interface FacilityDiagramProps {
  onEquipmentSelect?: (equipment: Equipment) => void;   // 장비 클릭 시 부모로 장비정보 전달
}

// 배관 종류 정의
export type PipeTone = 'water' | 'nutrient' | 'steel';

// 센서 데이터 타입 정의
export type SensorData = {
  waterLevel: number;   // 원수 탱크 수위
  ph: number;   // pH 값
  ec: number;   // EC 값
  temperature: number;   // 온도
  pressure: number;   // 압력
};