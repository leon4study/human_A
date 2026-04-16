import type { ReactNode } from 'react';

const MainLayout = ({ children }: { children: ReactNode }) => {
  return (
    <div style={{ 
      width: '100vw', 
      height: '100vh', 
      position: 'relative', 
      // --- 여기에 이미지 URL을 넣으세요 ---
      backgroundImage: `url('/images/smart_background.png')`,
      backgroundSize: 'cover',       // 화면에 꽉 차게 조절
      backgroundPosition: 'center',  // 정중앙 배치
      backgroundRepeat: 'no-repeat', // 반복 금지
      backgroundColor: '#d9dbde',    // 이미지 로딩 전이나 실패 시 보일 배경색
      // --------------------------------
      overflow: 'hidden',
      color: '#fff'
    }}>
      
      {/* 1. 헤더: 투명하게 라인만 (이미지 위에 뜸) */}
      <header style={{ 
        position: 'absolute', top: 0, left: 0, width: '100%', height: '60px',
        zIndex: 100, display: 'flex', alignItems: 'center', padding: '0 40px',
        background: 'transparent', 
        borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
        justifyContent: 'space-between'
      }}>
        <h2 style={{ fontSize: '1.1rem', color: '#00ff9d', margin: 0 }}>SMART FARM NOC</h2>
        <div style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.3)' }}>SYSTEM ACTIVE</div>
      </header>

      {/* 2. 메인 콘텐츠: 대시보드 박스들이 배치될 영역 */}
      <main style={{ position: 'relative', zIndex: 10, width: '100%', height: '100%' }}>
        {children}
      </main>
    </div>
  );
};

export default MainLayout;