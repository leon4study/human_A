export type SystemStatus = "normal" | "warning" | "danger";

export interface SystemStatusInfo {
  text: string;
  icon: string;
  className: string;
}

export const systemStatusMap: Record<SystemStatus, SystemStatusInfo> = {
  normal: {
    text: "정상 운영",
    icon: "✔",
    className: "is-normal",
  },
  warning: {
    text: "주의 필요",
    icon: "!",
    className: "is-warning",
  },
  danger: {
    text: "위험 상태",
    icon: "✖",
    className: "is-danger",
  },
};
