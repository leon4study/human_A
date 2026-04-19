import type { PipeTone, SensorData } from './facilityTypes';

// 배관 색상 테마 정의
export const pipePalette: Record<PipeTone, { shell: string; body: string; flow: string; glow: string }> = {
  water: {
    shell: '#020617',   // 가장 바깥 어두운 테두리
    body: '#1d4ed8',   // 배관 본체 색
    flow: '#60a5fa',   // 안쪽 흐름 색
    glow: '#bfdbfe',   // 약한 광택
  },
  nutrient: {
    shell: '#1c1917',
    body: '#9a3412',
    flow: '#fb923c',
    glow: '#fed7aa',
  },
  steel: {
    shell: '#0f172a',
    body: '#475569',
    flow: '#cbd5e1',
    glow: '#e2e8f0',
  },
};

// 양액탱크 목록
export const nutrientTanks = [
  { id: 'tankA', label: '원액 A', color: '#eab308', x: 70, level: 82 },   // id, 이름, 액체 색, x좌표, 수위
  { id: 'tankB', label: '원액 B', color: '#22c55e', x: 75.5, level: 76 },
  { id: 'tankPH', label: 'pH 조절제', color: '#a855f7', x: 81, level: 68 },
  { id: 'tankD', label: '첨가제 D', color: '#94a3b8', x: 86.5, level: 45 },
  { id: 'tankE', label: '첨가제 E', color: '#64748b', x: 92, level: 55 },
] as const;

// 밸브 관련 위치값
export const valvePositions = [21, 47, 73];   // SVG 내부 배관 분기 x 위치
export const valveCardLeftPositions = ['19.45%', '45.45%', '71.45%'];   // 실제 밸브 컴포넌트 left 값

// 약품 탱크 배관 관련 위치
export const nutrientTankPipeStartY = 14.4;   // 약품탱크 배관 시작 y
export const nutrientManifoldY = 17.8;   // 약품이 모이는 매니폴드 y

// 구역 카드 데이터
export const growingZones = [
  { left: '15.5%', title: '1구역 딸기 재배지', ph: '6.2', ec: '1.4', accent: '#f472b6' },   // left, 제목, pH, EC, 강조색
  { left: '41.5%', title: '2구역 딸기 재배지', ph: '6.3', ec: '1.5', accent: '#fb7185' },
  { left: '67.5%', title: '3구역 딸기 재배지', ph: '6.1', ec: '1.3', accent: '#f43f5e' },
] as const;

// 고정 장비 상태값
export const staticEquipmentStatus = {
  rawWaterPump: true,   // 원수펌프 ON/OFF
  valves: [true, true, false],   // 밸브 3개 열림 여부
} as const;

// 센서 초기값
export const initialSensorData: SensorData = {
  waterLevel: 75,   // 수위 초기값
  ph: 6.2,   // pH 초기값
  ec: 1.5,   // EC 초기값
  temperature: 22,   // 온도 초기값
  pressure: 2.5,   // 압력 초기값
};

// 물 배관 조인트 위치
export const waterJointPositions = [17, 21, 39, 43.8, 50.8, 55.2];