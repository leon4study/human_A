import type { EnvironmentItem } from "../types/dashboard";

export const environmentData: EnvironmentItem[] = [
  {
    id: "light",
    label: "광량",
    // 실제 RAW 수신 전까지 placeholder 표시
    value: "---",
    unit: "μmol/m²·s",
  },
  {
    id: "temp",
    label: "온도",
    // 실제 RAW 수신 전까지 placeholder 표시
    value: "---",
    unit: "°C",
  },
  {
    id: "humidity",
    label: "습도",
    // 실제 RAW 수신 전까지 placeholder 표시
    value: "---",
    unit: "%",
  },
  {
    id: "co2",
    label: "CO₂",
    // 실제 RAW 수신 전까지 placeholder 표시
    value: "---",
    unit: "ppm",
  },
];
