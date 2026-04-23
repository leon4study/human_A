import type { ZoneCauseItem } from "../types/dashboard";

export const zoneCauseTopData: ZoneCauseItem[] = [
  {
    id: "zone1-cause1",
    zoneId: "zone1",
    equipment: "펌프",
    cause: "유량 저하",
    count: 18,
  },
  {
    id: "zone1-cause2",
    zoneId: "zone1",
    equipment: "필터",
    cause: "차압 상승",
    count: 14,
  },
  {
    id: "zone1-cause3",
    zoneId: "zone1",
    equipment: "밸브",
    cause: "개폐 불량",
    count: 9,
  },

  {
    id: "zone2-cause1",
    zoneId: "zone2",
    equipment: "필터",
    cause: "막힘 누적",
    count: 16,
  },
  {
    id: "zone2-cause2",
    zoneId: "zone2",
    equipment: "펌프",
    cause: "압력 이상",
    count: 11,
  },
  {
    id: "zone2-cause3",
    zoneId: "zone2",
    equipment: "배관",
    cause: "유속 저하",
    count: 7,
  },

  {
    id: "zone3-cause1",
    zoneId: "zone3",
    equipment: "밸브",
    cause: "응답 지연",
    count: 8,
  },
  {
    id: "zone3-cause2",
    zoneId: "zone3",
    equipment: "펌프",
    cause: "전류 이상",
    count: 5,
  },
  {
    id: "zone3-cause3",
    zoneId: "zone3",
    equipment: "센서",
    cause: "측정 오차",
    count: 3,
  },
];