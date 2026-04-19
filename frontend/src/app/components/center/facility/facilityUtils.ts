import type { Equipment, SensorData } from './facilityTypes';

// 차트용 히스토리 데이터 생성 함수
export function generateHistory(baseValue: number, variation: number) {
  return Array.from({ length: 10 }, (_, i) => ({
    time: `${10 - i}분 전`,   // 시간 텍스트
    value: Number((baseValue + (Math.random() - 0.5) * variation).toFixed(2)),   // 값
  }));
}

// 장비별 추가정보 생성 함수
export function getAdditionalInfo(id: string, sensorData: SensorData): Record<string, string> | undefined {
  switch (id) {
    case 'rawWaterTank':
      return {
        용량: '5000 L',
        경보수위: '20%',
        현재수량: `${((5000 * sensorData.waterLevel) / 100).toFixed(0)} L`,
      };

    case 'rawWaterPump':
      return {
        전류: '12.5 A',
        전압: '220 V',
        가동시간: '142 시간',
        효율: '94%',
      };

    case 'autoSupply':
      return {
        'pH 제어': '자동',
        'EC 제어': '자동',
        가동모드: '연속',
      };

    default:
      return undefined;
  }
}

// 클릭 시 팝업으로 넘길 장비 객체 생성 함수
export function createEquipment(
  id: string,
  name: string,
  type: string,
  sensorData: SensorData,
  currentValue?: number,
  unit?: string,
): Equipment {
  return {
    id,
    name,
    type,
    status: 'normal',
    currentValue,
    unit,
    history: currentValue !== undefined ? generateHistory(currentValue, currentValue * 0.1) : undefined,
    additionalInfo: getAdditionalInfo(id, sensorData),
  };
}