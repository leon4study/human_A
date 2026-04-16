// 알림 레벨 타입
export type AlertLevel = "info" | "warning" | "critical";

// 알림 한 개의 형태
export interface AlertHistoryItem {
  id: number;
  time: string;
  equipment: string;
  title: string;
  message: string;
  level: AlertLevel;
  value: string;
}

// 많은 양의 알림 테스트용 더미 데이터 생성 함수
export function createMockAlertHistory(count: number): AlertHistoryItem[] {
  const levels: AlertLevel[] = ["info", "warning", "critical"];

  const equipments = [
    "1호기 펌프",
    "2호기 펌프",
    "3호기 펌프",
    "1호기 필터",
    "2호기 필터",
    "3호기 필터",
    "1호기 원수탱크",
    "2호기 원수탱크",
    "3호기 원수탱크",
    "1호기 배양액 공급기",
    "2호기 배양액 공급기",
    "3호기 배양액 공급기",
    "1구역 밸브",
    "2구역 밸브",
    "3구역 밸브",
  ];

  const titles = [
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

  const messages = [
    "기준 범위를 초과했습니다.",
    "주의 임계치를 넘어섰습니다.",
    "단기 추세가 비정상적으로 변하고 있습니다.",
    "예지보전 모델이 이상 패턴을 감지했습니다.",
    "최근 10분 평균값이 정상 범위를 벗어났습니다.",
    "설정값과 실제값 차이가 커지고 있습니다.",
  ];

  const values = [
    "42.3 L/min",
    "18.1 kPa",
    "5.2 mm/s",
    "74.8°C",
    "16%",
    "3.7 kW",
    "pH 6.8",
    "위험도 82%",
    "응답 지연 2.5 sec",
    "EC 2.9",
  ];

  const data: AlertHistoryItem[] = [];

  for (let i = 0; i < count; i++) {
    const hour = 8 + Math.floor(i / 12);
    const minute = (i * 5) % 60;
    const second = (i * 13) % 60;

    data.push({
      id: i + 1,
      time: `2026.04.16 ${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}:${String(second).padStart(2, "0")}`,
      equipment: equipments[i % equipments.length],
      title: titles[i % titles.length],
      message: messages[i % messages.length],
      level: levels[i % levels.length],
      value: values[i % values.length],
    });
  }

  // 최신 데이터가 위에 오도록 뒤집기
  return data.reverse();
}

// 화면에서 바로 사용할 예시 데이터
export const alertHistoryData: AlertHistoryItem[] = createMockAlertHistory(200);