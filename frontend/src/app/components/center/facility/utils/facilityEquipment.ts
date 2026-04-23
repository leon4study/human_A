import {
  equipmentCategoryLabels,
  getEquipmentDefinition,
} from "../model/facility.catalog";
import type { Equipment, SensorData } from "../model/facility.types";

// 현재값 주변으로 간단한 모의 히스토리를 생성
export function generateHistory(baseValue: number, variation: number) {
  return Array.from({ length: 10 }, (_, i) => ({
    time: `${10 - i}분 전`,
    value: Number((baseValue + (Math.random() - 0.5) * variation).toFixed(2)),
  }));
}

export function getAdditionalInfo(
  id: string,
  sensorData: SensorData,
): Record<string, string> | undefined {
  // 장비 종류에 따라 모달에 보여줄 추가 정보만 분기한다.
  switch (id) {
    case "rawWaterTank":
      return {
        용량: "5000 L",
        경보수위: "20%",
        현재저장량: `${((5000 * sensorData.waterLevel) / 100).toFixed(0)} L`,
      };
    case "rawWaterPump":
      return {
        전류: "12.5 A",
        전압: "220 V",
        가동시간: "142 시간",
        효율: "94%",
      };
    case "autoSupply":
      return {
        "pH 제어": "자동",
        "EC 제어": "자동",
        가동모드: "연속",
      };
    default:
      return undefined;
  }
}

export function createEquipment(
  id: string,
  sensorData: SensorData,
  currentValue?: number,
  unit?: string,
): Equipment {
  // 다이어그램 클릭 정보를 모달 표시용 장비 객체로 변환한다.
  const definition = getEquipmentDefinition(id);

  if (!definition) {
    throw new Error(`Unknown equipment id: ${id}`);
  }

  return {
    id,
    name: definition.name,
    type: definition.type,
    category: equipmentCategoryLabels[definition.category],
    status: "normal",
    currentValue,
    unit,
    history:
      currentValue !== undefined
        ? generateHistory(currentValue, currentValue * 0.1)
        : undefined,
    additionalInfo: getAdditionalInfo(id, sensorData),
  };
}
