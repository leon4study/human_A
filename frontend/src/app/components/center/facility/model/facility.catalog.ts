import type { EquipmentCategory } from "./facility.types";

// 장비별 고정 메타데이터 정의
export type EquipmentDefinition = {
  id: string;
  name: string;
  type: string;
  category: EquipmentCategory;
};

export const equipmentCategoryLabels: Record<EquipmentCategory, string> = {
  storage: "저장",
  treatment: "처리",
  transfer: "이송",
  control: "제어",
  distribution: "분배",
  zone: "재배구역",
};

// 화면에서 쓰는 장비 id를 실제 이름/종류/분류로 매핑
export const facilityEquipmentCatalog: Record<string, EquipmentDefinition> = {
  rawWaterTank: {
    id: "rawWaterTank",
    name: "원수 탱크",
    type: "저장 탱크",
    category: "storage",
  },
  filter: {
    id: "filter",
    name: "필터",
    type: "여과 장치",
    category: "treatment",
  },
  rawWaterPump: {
    id: "rawWaterPump",
    name: "원수 펌프",
    type: "이송 펌프",
    category: "transfer",
  },
  autoSupply: {
    id: "autoSupply",
    name: "양액 자동공급기",
    type: "자동 공급 장치",
    category: "control",
  },
  tankA: {
    id: "tankA",
    name: "양액 A",
    type: "양액 탱크",
    category: "storage",
  },
  tankB: {
    id: "tankB",
    name: "양액 B",
    type: "양액 탱크",
    category: "storage",
  },
  tankPH: {
    id: "tankPH",
    name: "pH 조절제",
    type: "보정제 탱크",
    category: "storage",
  },
  tankD: {
    id: "tankD",
    name: "첨가제 D",
    type: "첨가제 탱크",
    category: "storage",
  },
  tankE: {
    id: "tankE",
    name: "첨가제 E",
    type: "첨가제 탱크",
    category: "storage",
  },
  valve1: {
    id: "valve1",
    name: "밸브 1",
    type: "분기 밸브",
    category: "distribution",
  },
  valve2: {
    id: "valve2",
    name: "밸브 2",
    type: "분기 밸브",
    category: "distribution",
  },
  valve3: {
    id: "valve3",
    name: "밸브 3",
    type: "분기 밸브",
    category: "distribution",
  },
  growingZone1: {
    id: "growingZone1",
    name: "1구역 딸기 재배지",
    type: "재배 구역",
    category: "zone",
  },
  growingZone2: {
    id: "growingZone2",
    name: "2구역 딸기 재배지",
    type: "재배 구역",
    category: "zone",
  },
  growingZone3: {
    id: "growingZone3",
    name: "3구역 딸기 재배지",
    type: "재배 구역",
    category: "zone",
  },
};

export function getEquipmentDefinition(id: string) {
  return facilityEquipmentCatalog[id];
}
