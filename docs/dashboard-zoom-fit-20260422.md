# 대시보드 zoom 기반 반응형 스케일

- 일자: 2026-04-22
- 대상 파일:
  - `frontend/src/app/layout/DashboardFrame.tsx`
  - `frontend/src/app/styles/dashboard.css`
  - `frontend/src/app/components/center/facility/facility-diagram.css`
- 변경 요지: 뷰포트 크기/비율과 무관하게 대시보드를 (1) 텍스트 블러 없이, (2) 찌그러짐 없이, (3) 빈 공간 없이 보이도록 `zoom` 기반 균등 스케일 + 매칭 배경 전략 적용.

---

## 1. 배경 — 이전 시도들의 문제

### 시도 1 (letterbox, uniform transform:scale)
- `transform: scale(min(sx, sy))`. 비율 유지하지만 16:9 아닌 뷰포트에 letterbox 생김. 1920×1080 초과 해상도에선 상한 때문에 빈 공간.
- **사용자 불만**: 빈 공간 보임.

### 시도 2 (non-uniform transform:scale(sx, sy))
- 가로/세로 독립 스케일로 꽉 채움. 빈 공간 없음.
- **사용자 불만**: SVG(펌프/탱크) 찌그러짐 심함.

### 시도 3 (위 + facility 내부 역변환)
- 비균등 scale 을 하되 facility 만 역변환으로 비율 복구.
- **사용자 불만**: 텍스트 블러 — `transform: scale` 이 래스터화된 픽셀을 다시 스케일해 서브픽셀 aliasing.

### 시도 4 (롤백)
- 전부 되돌리고 원본 flex 레이아웃 복귀.

### 시도 5 (zoom + 매칭 배경) — 초기 버전
- `.dashboard` 를 1920×1080 **고정** 으로 두고 `zoom: min(sx,sy)`. Body 배경에 대시보드와 같은 그라데이션 → letterbox 영역이 시각적으로 연속.
- **사용자 불만**: 16:9 넘는 뷰포트(특히 ultrawide) 에선 여전히 letterbox 가 보임 — 배경이 아무리 톤 맞아도 '비어있는 영역' 인상 지울 수 없음.

---

## 2. 최종 해법 — zoom + **동적 설계 크기**

### 핵심 아이디어 (v2 - 2026-04-22 업데이트)
1. **`zoom`** 사용: 텍스트 블러 없음 (v1 과 동일).
2. 배율은 뷰포트의 "짧은 축" 기준: 넓은 뷰포트면 `vh/1080`, 좁은 뷰포트면 `vw/1920`.
3. **대시보드 설계 크기를 뷰포트 비율에 맞춰 동적으로 확장** — letterbox 자체가 생기지 않음.
   - 넓은 뷰포트: `width = vw/zoom`, `height = 1080` → 가로 확장
   - 좁은 뷰포트: `width = 1920`, `height = vh/zoom` → 세로 확장
4. 내부 `facility-diagram-inner` 는 `1100px` 고정 → 비율 유지, `flex:1` 인 center-wrap 이 확장 공간 흡수.

배경 매칭 그라데이션(body) 은 이젠 letterbox 가 없어 불필요하지만, 초기 페인트 플래시 대비 안전망으로 유지.

### 요소
```
viewport (fixed inset:0, .dashboard-fit, flex center, overflow hidden)
 └ .dashboard  (width:1920px height:1080px zoom:var(--app-zoom))
    ├ .dashboard__bg (기존 그라데이션)
    ├ .dashboard__overlay (height:100%)
    │   └ header / body / modals
    └ ...
```

### JS (`DashboardFrame.tsx`)
```ts
const DESIGN_W = 1920;
const DESIGN_H = 1080;
const DESIGN_ASPECT = DESIGN_W / DESIGN_H;

function useFitScale() {
  useLayoutEffect(() => {
    const update = () => {
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const viewportAspect = vw / vh;

      let zoom: number, width: number, height: number;
      if (viewportAspect >= DESIGN_ASPECT) {
        zoom = vh / DESIGN_H;
        width = vw / zoom;
        height = DESIGN_H;
      } else {
        zoom = vw / DESIGN_W;
        width = DESIGN_W;
        height = vh / zoom;
      }

      const root = document.documentElement;
      root.style.setProperty("--app-zoom", String(zoom));
      root.style.setProperty("--app-width", `${width}px`);
      root.style.setProperty("--app-height", `${height}px`);
    };
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);
}
```

### CSS 핵심 변경
```css
html, body, #root {
  height: 100%;
  overflow: hidden;
}
body {
  /* dashboard__bg 의 linear-gradient 와 동일한 색상 */
  background: linear-gradient(90deg, #7496bb 0%, #4c7197 50%, #7496bb 100%);
}
.dashboard-fit {
  position: fixed; inset: 0;
  display: flex; align-items: center; justify-content: center;
  overflow: hidden;
}
.dashboard {
  /* v2: width/height 는 JS 가 뷰포트에 맞춰 동적으로 세팅 */
  width: var(--app-width, 1920px);
  height: var(--app-height, 1080px);
  flex-shrink: 0;
  zoom: var(--app-zoom, 1);
}
.dashboard__overlay { height: 100%; }  /* 기존 min-height: 100vh 에서 변경 */
```

### 시나리오 표 (v2 — letterbox 모두 제거됨)

| 뷰포트 | 뷰포트 비율 | zoom | 설계 크기 (width × height) | 렌더 결과 | letterbox |
|---|---|---|---|---|---|
| 1920×1080 (기준) | 1.78 | 1 | 1920×1080 | 1920×1080 | 없음 |
| 3840×2160 (4K 16:9) | 1.78 | 2 | 1920×1080 | 3840×2160 | 없음 |
| 2560×1080 (ultrawide 21:9) | 2.37 | 1 | **2560**×1080 | 2560×1080 | 없음 (center-wrap 가 여유 공간 흡수) |
| 3440×1440 (QHD ultrawide) | 2.39 | 1.33 | **2580**×1080 | 3440×1440 | 없음 |
| 1920×1200 (WUXGA 16:10) | 1.60 | 1 | 1920×**1200** | 1920×1200 | 없음 (panel 하단 여유 흡수) |
| 1280×720 (HD) | 1.78 | 0.667 | 1920×1080 | 1280×720 | 없음 |
| 900×600 | 1.5 | 0.469 | 1920×**1280** | 900×600 | 없음 |

---

## 3. 자기 비판적 리뷰에서 찾은 이슈와 수정

### [FIX-1] `.facility-diagram-inner` 의 `width: min(1100px, 88vw)` 이중 축소
- **증상**: zoom 이 뷰포트 맞춤을 전담하는 상황에서 `88vw` 는 **실제 뷰포트 기준** 으로 계산 (CSS 표준상 vw 는 zoom 무관). 좁은 뷰포트에서 facility 가 `zoom × 88vw` 꼴로 이중 축소되어 비례 불일치.
- **수정**: `width: 1100px` 고정. 뷰포트 맞춤은 상위 zoom 이 전담.

### [KNOWN-1] `zoom` 브라우저 호환성
- Chrome / Safari / Edge: 오래 전부터 지원.
- Firefox: **126+ (2024-05)** 부터 정식 지원. 이전 버전은 `zoom` 속성을 파싱만 하고 효과 없음.
- **영향 / 대응**: 2026-04 기준 Firefox 유저 대부분이 126+. 구버전 유저는 1920×1080 고정으로 렌더되며 작은 뷰포트에선 스크롤/잘림 발생 (이전 "롤백" 상태와 동일). 중요 유저베이스가 있다면 JS 피처 탐지 + `transform: scale` 폴백 추가 필요.

### [OBS-1] 모달 (`position: fixed`) 와 zoom 상호작용
- 모달 overlay 는 `.dashboard` 내부에 있고 `position: fixed; inset: 0`.
- `zoom` 된 부모 아래 fixed 자식 동작은 브라우저마다 약간 다를 수 있음.
- 일반적으론 overlay 가 뷰포트 전체를 덮되 내부 모달 박스 치수(max-width, font 등)는 zoom 비례로 렌더됨 → **의도된 동작 (대시보드와 함께 확대/축소)**.
- **관찰 필요**: 특히 letterbox 영역이 있는 뷰포트 (비 16:9) 에서 모달 overlay 가 letterbox 영역까지 덮는지 실사용 확인 권장. 안 덮으면 모달을 `document.body` 로 포털하는 방안 검토.

### [NOTE-1] 서브픽셀 아티팩트
- zoom 배율이 비정수일 때 border(1px) 이나 box-shadow 가 살짝 굵어/얇아질 수 있음.
- `transform: scale` 대비 텍스트 블러는 없지만 이 아티팩트는 zoom 에도 존재.
- 수용 가능한 수준, 별도 대응 없음.

---

## 4. 검증
- `npx tsc --noEmit -p tsconfig.app.json` → exit 0.
- 브라우저 실렌더 검증은 **미수행**. 사용자가 다음 확인 권장:
  1. 1920×1080 창에서 1:1 렌더인지 (zoom = 1)
  2. 브라우저 창 폭/높이 줄일 때 텍스트가 선명하게 유지되는지
  3. 울트라와이드 (21:9) 로 열었을 때 좌우 letterbox 가 대시보드 배경과 톤 매치되어 자연스러운지
  4. 장비/AI 분석 모달을 띄웠을 때 전체 화면 (letterbox 포함) 을 덮는지

---

## 5. 이전 시도와의 비교 요약

| 접근 | 찌그러짐 | 빈 공간 | 텍스트 블러 | 1920×1080 초과 |
|---|---|---|---|---|
| (1) uniform scale | 없음 | 생김 | 있음 | 상한 있음 |
| (2) non-uniform scale | 심함 | 없음 | 있음 | 채움 |
| (3) 2 + 역변환 | 일부만 복구 | 없음 | 있음 | 채움 |
| (4) 롤백 | 원본 상태 | — | — | — |
| (5) zoom + 고정 1920×1080 + 매칭 배경 | 없음 | 배경으로 커버 (보임) | 없음 | 채움 |
| **(6) zoom + 동적 설계 크기** | **없음** | **실제로 없음** | **없음** | **채움** |

## 6. v2 추가 자기 리뷰 — 확인한 엣지 케이스

- **초기 페인트 플래시**: `useLayoutEffect` 가 paint 전 실행되므로 기본값(1920/1080/1) 노출 안 됨.
- **극단 비율 뷰포트 (32:9, 9:32 등)**: center-wrap(flex:1) 또는 panel-col(justify:space-between) 이 극단적으로 넓/높어 보일 수 있음. letterbox 보다는 낫지만 사용성 저해 시 추후 `max-width`/`max-height` cap 고려.
- **서브픽셀**: zoom 이 비정수일 때 1px border 가 미세하게 굵어/얇어짐. 수용.
- **float 부동소수 오차**: `vw/zoom × zoom ≈ vw` 라 최대 1px 오차. `.dashboard-fit` 의 `overflow:hidden` 로 안전.
- **모달 × zoom**: v1 과 동일한 상호작용. 이제 dashboard 가 뷰포트와 동일 크기라 모달이 letterbox 걱정 없음 — 오히려 v1 대비 개선.
