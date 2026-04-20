// 양액 탱크의 위치와 표시 정보
export const nutrientTanks = [
  { id: "tankA", label: "양액 A", color: "#eab308", x: 70, level: 82 },
  { id: "tankB", label: "양액 B", color: "#22c55e", x: 75.5, level: 76 },
  { id: "tankPH", label: "pH 조절제", color: "#a855f7", x: 81, level: 68 },
  { id: "tankD", label: "첨가제 D", color: "#94a3b8", x: 86.5, level: 45 },
  { id: "tankE", label: "첨가제 E", color: "#64748b", x: 92, level: 55 },
] as const;

export const valvePositions = [21, 47, 73] as const;
export const valveCardLeftPositions = ["19.45%", "45.45%", "71.45%"] as const;

// 상단 매니폴드 및 탱크 연결관 위치
export const nutrientTankPipeStartY = 14.4;
export const nutrientManifoldY = 17.8;

// 하단 재배 구역 카드 배치 데이터
export const growingZones = [
  { left: "15.5%", title: "1구역 딸기 재배지", ph: "6.2", ec: "1.4", accent: "#f472b6" },
  { left: "41.5%", title: "2구역 딸기 재배지", ph: "6.3", ec: "1.5", accent: "#fb7185" },
  { left: "67.5%", title: "3구역 딸기 재배지", ph: "6.1", ec: "1.3", accent: "#f43f5e" },
] as const;

export const waterJointPositions = [17, 21, 39, 43.8, 50.8, 55.2] as const;
