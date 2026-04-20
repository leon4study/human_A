import { useEffect, useState } from 'react';

const Dashboard = () => {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    // 1. FastAPI 백엔드 웹소켓 주소로 연결 (ws:// 프로토콜 사용)
    // 백엔드 포트가 8080이고 엔드포인트가 /ws 인 경우
    const socket = new WebSocket('ws://127.0.0.1:8080/ws/smart-farm');

    socket.onopen = () => {
      console.log("✅ FastAPI 실시간 서버 연결 성공!");
    };

    socket.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        console.log("📥 받은 메시지:", parsed);

        if (parsed.type === "RAW") {
          // payload 안에 sensor_data가 있으면 그걸 쓰고, 없으면 payload 자체를 씀
          setData(parsed.payload.sensor_data || parsed.payload);
        } else if (parsed.type === "INFERENCE") {
          setData(parsed.payload.sensor_data || parsed.payload);
        }
      } catch (error) {
        console.error("❌ 데이터 파싱 에러:", error);
      }
    };

    socket.onclose = () => {
      console.log("🔌 서버 연결 종료");
    };

    // 컴포넌트 언마운트 시 연결 해제
    return () => {
      socket.close();
    };
  }, []);

  return (
    <div style={{ 
      display: 'grid', gridTemplateColumns: '380px 1fr 380px', 
      width: '100%', height: '100%', boxSizing: 'border-box'
    }}>
      
      {/* [좌측 영역] - 배경 및 레이아웃 유지 */}
      <section style={{ 
        display: 'grid', gridTemplateRows: 'repeat(3, 1fr)', 
        background: 'linear-gradient(to right, rgba(10, 25, 47, 0.95) 0%, rgba(10, 25, 47, 0) 100%)'
      }}>
        <MetricCard id="pump_metrics_raw" kor="펌프 실시간 데이터">
          {/* JSON 필드명에 맞춰 value 수정 */}
          <RawRow label="discharge_pres" value={data?.discharge_pressure_kpa} color="#00ff9d" />
          <RawRow label="flow_rate" value={data?.flow_rate_l_min} color="#00ff9d" />
          <RawRow label="pump_rpm" value={data?.pump_rpm} color="#00ff9d" />
        </MetricCard>

        <MetricCard id="line_status_raw" kor="라인 공급 수치">
          <RawRow label="raw_water_ph" value={data?.raw_water_ph} color="#00e5ff" />
          <RawRow label="tank_pressure" value={data?.raw_tank_pressure_kpa} color="#00e5ff" />
          <RawRow label="mix_flow" value={data?.mix_flow_l_min} color="#00e5ff" />
        </MetricCard>

        <MetricCard id="equipment_health_raw" kor="설비 건전성 데이터">
          <RawRow label="bearing_vibration" value={data?.bearing_vibration_peak_mm_s} color="#ffcc00" />
          <RawRow label="motor_temp" value={data?.motor_temperature_c} color="#ffcc00" />
        </MetricCard>
      </section>

      {/* [중앙 도식 영역] */}
      <div />

      {/* [우측 영역] - 배경 및 레이아웃 유지 */}
      <section style={{ 
        display: 'grid', gridTemplateRows: 'repeat(3, 1fr)', 
        background: 'linear-gradient(to left, rgba(10, 25, 47, 0.95) 0%, rgba(10, 25, 47, 0) 100%)'
      }}>
        <MetricCard id="environment_raw" kor="대기 환경 데이터">
          <RawRow label="air_temp" value={data?.air_temp_c} color="#00ff9d" />
          <RawRow label="humidity" value={data?.relative_humidity_pct} color="#00ff9d" />
          <RawRow label="co2_level" value={data?.co2_ppm} color="#00ff9d" />
        </MetricCard>

        <MetricCard id="nutrient_chemical_raw" kor="배양액 조성 수치">
          <RawRow label="mix_ph" value={data?.mix_ph} color="#00e5ff" />
          <RawRow label="mix_ec" value={data?.mix_ec_ds_m} color="#00e5ff" />
          <RawRow label="mix_temp" value={data?.mix_temp_c} color="#00e5ff" />
        </MetricCard>

        <MetricCard id="system_analysis_raw" kor="분석 및 네트워크">
          {/* is_anomaly는 sensor_data 밖의 상위 depth에 있으므로 parsed 구조에 따라 조정 필요할 수 있음 */}
          <RawRow label="zone3_flow" value={data?.zone3_flow_l_min} color="#fff" />
          <RawRow label="zone3_pres" value={data?.zone3_pressure_kpa} color="#fff" />
          <RawRow label="substrate_ph" value={data?.zone3_substrate_ph} color="#fff" />
        </MetricCard>
      </section>
    </div>
  );
};

// --- Raw 데이터 한 줄 표시용 컴포넌트 (디자인 유지) ---
const RawRow = ({ label, value, color }: any) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
    <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.75rem', fontFamily: 'monospace' }}>{label}</span>
    <span style={{ color: color, fontSize: '1.1rem', fontWeight: 'bold', fontFamily: 'monospace' }}>
      {value !== undefined && value !== null ? value : '---'}
    </span>
  </div>
);

// --- 기존 스타일과 구조를 유지한 카드 컴포넌트 (디자인 유지) ---
const MetricCard = ({ id, kor, children }: any) => (
  <div style={{ padding: '25px 45px', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
    <div style={{ color: 'rgba(255,255,255,0.2)', fontSize: '0.65rem', fontFamily: 'monospace', letterSpacing: '1px', marginBottom: '4px' }}>
      {`// ${id.toUpperCase()}`}
    </div>
    <div style={{ color: '#00ff9d', fontSize: '1rem', fontWeight: 'bold', marginBottom: '15px' }}>{kor}</div>
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      {children}
    </div>
  </div>
);

export default Dashboard;