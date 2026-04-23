import { useEffect, useState } from "react";

function CurrentTime() {
  // 현재 시간을 저장하는 state
  const [currentTime, setCurrentTime] = useState("");

  useEffect(() => {
    // 현재 시간을 원하는 형식으로 만드는 함수
    const updateTime = () => {
      const now = new Date();

      const year = now.getFullYear();
      const month = String(now.getMonth() + 1).padStart(2, "0");
      const date = String(now.getDate()).padStart(2, "0");
      
      const hours = now.getHours();
      const minutes = String(now.getMinutes()).padStart(2, "0");
      const seconds = String(now.getSeconds()).padStart(2, "0");

      // 오전 / 오후 구분
      const period = hours < 12 ? "오전" : "오후";

      // 12시간 형식으로 변환
      let displayHour = hours % 12;
      if (displayHour === 0) {
        displayHour = 12;
      }

      const formattedHour = String(displayHour).padStart(2, "0");

      setCurrentTime(`${year}.${month}.${date}. ${period} ${formattedHour}:${minutes}:${seconds}`);
    };

    // 처음 실행
    updateTime();

    // 1초마다 갱신
    const timer = setInterval(updateTime, 1000);

    // 컴포넌트 종료 시 정리
    return () => clearInterval(timer);
  }, []);

  return <span>{currentTime}</span>;
}

export default CurrentTime;