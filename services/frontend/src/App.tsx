import MainLayout from './layouts/MainLayout';
import Dashboard from './pages/Dashboard';

function App() {
  return (
    // 레이아웃이 겉을 감싸고, 그 안에 대시보드 페이지가 들어갑니다.
    <MainLayout>
      <Dashboard />
    </MainLayout>
  );
}

export default App;