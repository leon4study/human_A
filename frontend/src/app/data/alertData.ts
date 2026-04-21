import type { AlertItem } from "../types/dashboard";

// 초기 Alert 이력은 비워둔다. 실제 데이터는 INFERENCE 웹소켓 메시지로 들어온다.
export const alertData: AlertItem[] = [];
