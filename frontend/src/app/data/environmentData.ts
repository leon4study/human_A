import type { EnvironmentItem } from "../types/dashboard";

export const environmentData: EnvironmentItem[] = [
  {
    id: "light",
    label: "광량",
    value: 400,
    unit: "μmol/m²·s",
  },
  {
    id: "temp",
    label: "온도",
    value: 23.4,
    unit: "°C",
  },
  {
    id: "humidity",
    label: "습도",
    value: 68,
    unit: "%",
  },
  {
    id: "co2",
    label: "CO₂",
    value: 800,
    unit: "ppm",
  },
];