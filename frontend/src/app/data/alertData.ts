import type { AlertItem } from "../types/dashboard";

function formatDate(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");

  return `${year}.${month}.${day}`;
}

function formatTime(date: Date) {
  const hour = String(date.getHours()).padStart(2, "0");
  const minute = String(date.getMinutes()).padStart(2, "0");
  const second = String(date.getSeconds()).padStart(2, "0");

  return `${hour}:${minute}:${second}`;
}

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

  const levelList = ["CAUTION", "WARNING", "CRITICAL"];

  const result: AlertItem[] = [];

  for (let i = 0; i < count; i++) {
    const currentDate = new Date();
    currentDate.setMinutes(currentDate.getMinutes() - i * 5);

    result.push({
      id: `alert-${i + 1}`,
      date: formatDate(currentDate),
      time: formatTime(currentDate),
      equipment: equipmentList[i % equipmentList.length],
      cause: causeList[i % causeList.length],
      level: levelList[i % levelList.length],
    });
  }

  return result.reverse();
}

export const alertData: AlertItem[] = createMockAlertData(200);