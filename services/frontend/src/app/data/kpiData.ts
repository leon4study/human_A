import type { KpiItem } from "../types/dashboard";

export const kpiData: KpiItem[] = [
  {
    id: "operation-rate",
    label: "가동율",
    value: 85,
    color: "green",
    size: "small",
  },
  {
    id: "failure-rate",
    label: "고장율",
    value: 10,
    color: "orange",
    size: "small",
  },
  {
    id: "overall-efficiency",
    label: "설비 종합 효율",
    value: 81,
    color: "blue",
    size: "large",
  },
];