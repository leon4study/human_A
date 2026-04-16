import type { AlertItem } from "../types/dashboard";

function createMockAlertData(count: number): AlertItem[] {
  const equipmentList = [
    "1호기 펌프",
    "2호기 펌프",
    "3호기 펌프",
    "1호기 필터",
    "2호기 필터",
    "3호기 필터",
    "1호기 원수탱크",
    "2호기 원수탱크",
    "3호기 원수탱크",
    "1구역 밸브",
    "2구역 밸브",
    "3구역 밸브",
  ];

  const causeList = [
    "유량 저하 감지",
    "차압 상승",
    "진동 수치 증가",
    "모터 온도 상승",
    "수위 저하",
    "EC 제어 오차",
    "pH 편차 발생",
    "센서 통신 이상",
    "전력 사용량 증가",
    "막힘 가능성 감지",
  ];

  const levelList = ["INFO", "WARNING", "CRITICAL"];

  const result: AlertItem[] = [];

  for (let i = 0; i < count; i++) {
    const hour = 8 + Math.floor(i / 12);
    const minute = (i * 5) % 60;
    const second = (i * 13) % 60;

    result.push({
      id: `alert-${i + 1}`,
      time: `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}:${String(second).padStart(2, "0")}`,
      equipment: equipmentList[i % equipmentList.length],
      cause: causeList[i % causeList.length],
      level: levelList[i % levelList.length],
    });
  }

  return result.reverse();
}

export const alertData: AlertItem[] = createMockAlertData(200);