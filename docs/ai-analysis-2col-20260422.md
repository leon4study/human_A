# AI 분석 결과 모달 2열 레이아웃 개편 (2026-04-22)

## 목적

AI 분석 결과 모달을 기존 단일 컬럼 구조에서 **2열 레이아웃**으로 개편하고, 우측 "원인진단" 섹션을 사용자 스케치대로 **FIP + SHAP 2패널 + Top-3 문제점** 구조로 재설계.

## 변경 요약

### 레이아웃
- 모달 width: `equipment-modal--wide` (640px) → **신규 `equipment-modal--xwide` (1040px)**
- 전체 폭 상단: 헤더, 전체 시스템 상태 배너, 스파이크 배지
- 2열 그리드:
  - **좌측**: 비교분석 (ComparativeSection)
  - **우측**: 원인진단 + AI 모델 성능 결과

### 원인진단 섹션 재설계 (스케치 기반)
- 상단 2패널:
  - **Feature Importance (FIP)**: 피처별 가로 막대 차트 (상위 4개, RCA 데이터 사용)
  - **SHAP 값 분포**: 피처별 sparkline 자리 (데이터 미연동, 빈 행)
- 하단: **Top-3 문제점** — 순위 배지 + 피처명 + 기여도 %

### 제거된 것
- `ScatterChart`, `ScatterChartProps` — 도메인 상세 산점도 (현재 레이아웃에서 사용 안 함)
- `getDomainCharts`, `interface ChartRow` (타입) — 도메인별 센서 차트 매핑
- `AlarmBadge`, `RcaBar`, `DomainCard` — 도메인 카드/알람 뱃지 (스케치에 없음)
- `ComparativeSection` wrapper의 인라인 `marginTop: 20px`
- 빈 `//` 주석 한 줄

### 새로 추가된 컴포넌트/상수
- `CauseDiagnosisSection`: 원인진단 섹션 전체
- `safePct(v)`: contribution을 CSS width로 안전 변환 (NaN/음수/>100 방어)
- CSS 클래스:
  - `.equipment-modal--xwide` (max-width: 1040px)
  - `.ai-modal-grid`, `.ai-modal-col`, `.ai-modal-placeholder`
  - `.ai-diag-grid`, `.ai-diag-panel`, `.ai-diag-subtitle`
  - `.ai-diag-feature-row / -label / -bar-wrap / -bar / -pct`
  - `.ai-diag-shap-sparkline / -empty`
  - `.ai-top3-list / -item / -rank / -feature / -pct`
  - `.ai-perf-row / -label / -value` (추후 AI 성능 결과 행 스타일용)

## 비판적 리뷰에서 발견한 버그와 수정 사항

1차 구현 직후 자기 리뷰에서 아래 4가지 이슈를 발견하여 수정함.

### 🔴 버그 1 — 좌우 컬럼 시작점 정렬 불일치
- **원인**: `ComparativeSection` 렌더 wrapper에 `style={{ marginTop: "20px" }}` 인라인 스타일이 남아 있었음
- **증상**: 좌측 비교분석만 20px 아래로 밀려서 우측 원인진단과 시작 위치가 다름
- **수정**: 해당 marginTop 제거. 부모 `.ai-modal-grid` 의 `margin-top: 18px` 로 공통 간격 확보

### 🔴 버그 2 — 정상 상태(level 0)에서도 Top-3 문제점이 표시됨
- **원인**: `hasRca = rca.length > 0` 조건만 확인. 백엔드가 level 0이어도 rca 배열을 채워 보낼 수 있음
- **증상**: "이상 없음"인데 "Top-3 문제점"이 리스트로 표시됨 → 사용자 오해 유발
- **수정**: `hasRca = level > 0 && rca.length > 0` 로 강화. level 0일 때는 "이상 징후 없음" placeholder 표시

### 🔴 버그 3 — contribution NaN/음수 시 width 깨짐
- **원인**: `Math.min(item.contribution, 100)`
  - `contribution = -5` → `width: -5%` (브라우저 무시하지만 정의되지 않은 동작)
  - `contribution = NaN` → `width: NaN%` (무효 스타일)
- **수정**: `safePct()` 헬퍼 추가. `Number.isFinite` 체크 → `Math.max(0, Math.min(v, 100))` 클램프

### 🟡 결함 4 — 도메인 맥락 상실
- **원인**: 스케치에 도메인 라벨이 없다고 `DOMAIN_LABELS` 상수를 제거
- **증상**: "Top-3 문제점"이 어느 도메인(모터 구동/수압/유압/양액-수질/구역 점적)의 RCA인지 모호
- **수정**: `DOMAIN_LABELS` 복원 + 원인진단 섹션 제목에 `— 수압/유압` 같은 도메인 라벨 병기 (RCA 있을 때만)

## 트레이드오프 / 향후 과제

### 남긴 것 / 의도적 결정
- **도메인별 알람 카드(DomainCard) 완전 제거**: 스케치가 FIP/SHAP/Top-3만 표시하므로 따랐지만, 네 도메인의 상태를 한눈에 보는 요약 UX는 사라짐. 사용자가 필요하다고 하면 전체 폭 배너 근처에 compact 버전으로 복원 가능.
- **SHAP 패널이 FIP와 피처 이름이 중복**: 피처 라벨이 좌우 두 번 반복됨. 데이터 연동 전까지는 구조만 잡아두는 placeholder 상태. SHAP 시계열 데이터가 실려오면 sparkline으로 변환 (`<svg>`에 작은 꺾은선 또는 비올린 plot).
- **AI 모델 성능 결과 섹션은 `<div class="ai-modal-placeholder">데이터 연동 예정</div>`**: 행 스타일(`.ai-perf-row`)만 CSS에 준비. 추후 각 도메인 모델의 MSE/AUC/precision/recall/latency 등을 테이블 형태로 채울 예정.
- **`ScatterChart`/`getDomainCharts` 완전 삭제**: 복원하려면 git history 참조.

### 제약 / 주의
- 우측 컬럼 내부 FIP/SHAP 2패널은 폭이 빡빡함 (~215px 내부). 피처 라벨 58px 고정 → 긴 라벨은 ellipsis로 잘림. `title` 속성으로 마우스 호버 시 전체 표시.
- 좌측 비교분석은 6개 차트가 세로로 쌓여서 우측 원인진단+성능 섹션보다 훨씬 길어짐. `align-items: start` 로 시작만 맞춤, 세로 길이 맞추지 않음.
- `equipment-modal--wide` (640px) 클래스는 유지. 향후 `EquipmentModal`이 쓸 수 있음.

## 영향받은 파일

- `frontend/src/app/components/detail/AiAnalysisModal.tsx` — 원인진단 섹션 재설계, 사용하지 않는 컴포넌트 제거
- `frontend/src/app/components/detail/equipment-modal.css` — `--xwide`, 2열 그리드, FIP/SHAP/Top-3 스타일 추가

## 검증

- `npx tsc --noEmit -p .` 통과 (에러 없음)
- 브라우저 실제 렌더링 확인은 사용자 검토 대기
