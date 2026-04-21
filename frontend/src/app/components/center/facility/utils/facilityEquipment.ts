import {
  equipmentCategoryLabels,
  getEquipmentDefinition,
} from "../model/facility.catalog";
import type { Equipment, SensorData } from "../model/facility.types";

export function createEquipment(
  id: string,
  _sensorData: SensorData,
  currentValue?: number,
  unit?: string,
): Equipment {
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
  };
}
