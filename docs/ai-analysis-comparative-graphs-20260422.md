# AI 분석 모달 — 비교분석 섹션 그래프화

- 일자: 2026-04-22
- 대상 파일: `frontend/src/app/components/detail/AiAnalysisModal.tsx`
- 변경 요지: `ComparativeSection`의 6개 텍스트 행을 모두 시계열 라인 차트로 전환. 아울러 `MiniLineChart`의 NaN 처리 관련 **기존 버그 2건**을 수정.

---

## 1. 바뀐 것 (요약)

### Before
비교분석 섹션은 label / value / description 3열 텍스트 행 6개:

| 항목 | 표시 방식 |
|---|---|
| 유량 대비 압력 비율 | 최신 1개 값 (kPa·min/L) |
| 차압 대비 유량 | 최신 1개 값 |
| 유량 대비 전력 효율 | 최신 1개 값 |
| 압력 변동성 (12h) | 12h 집계 단일 값 or "수집 중" |
| 유량 변동성 (12h) | 12h 집계 단일 값 or "수집 중" |
| 온도 변화율 | 마지막 2포인트 기울기 1개 |

### After
6개 항목 모두 `MiniLineChart` + `ChartRow` 패턴 — 차트(좌) + 설명(우). `chartSnapshot`의 20포인트 링버퍼를 순회하면서 **포인트별 파생 시계열**을 계산.

| 항목 | 시계열 계산 | 단위 |
|---|---|---|
| 유량 대비 압력 비율 | `pressure[i] / flow[i]` (flow ≥ 1 L/min일 때) | kPa·min/L |
| 차압 대비 유량 | `(pressure[i] − suction[i]) / flow[i]` | kPa·min/L |
| 유량 대비 전력 효율 | `flow[i] / motor_power[i]` (power ≥ 0.05 kW) | L/min/kW |
| 압력 변동성 (최근) | rolling `std(pressure)`, window=5 | kPa |
| 유량 변동성 (최근) | rolling `std(flow)/mean(flow)`, window=5 | 무단위 |
| 온도 변화율 | `diff(motor_temp[i]) / dt` | °C/s |

변동성 2개는 `chartSnapshot`(최대 20포인트)을 쓰는 **롤링 단기** 버전. 기존 `comparative.pressureVolatility/flowCv`(12h 집계)는 description 영역에 `12h 값: 0.123` 형태로 병기. 집계가 30샘플 미만이면 `수집 중 N/30`로 표시.

---

## 2. 자기 비판적 리뷰에서 찾은 버그

1차 구현 직후 코드를 다시 읽으며 아래 3건을 발견하고 같은 커밋 범위에서 모두 수정했다.

### [BUG-1] `MiniLineChart`가 NaN 값을 차트 바닥에 렌더 (기존 버그, 내 변경으로 노출도 증폭)

**증상**
```tsx
const mainPts = values
  .map((v, i) =>
    `${toX(i, values.length)},${Number.isFinite(v) ? toY(v) : toY(mn)}`
  ).join(" ");
```
- NaN이면 y좌표를 `toY(mn)` = 차트 **맨 아래**로 찍음.
- 폴리라인이 NaN 지점에서 바닥까지 급강하 → 사용자가 “값이 0으로 떨어졌다”고 오해.
- 원래 쓰이던 센서 차트에서도 센서 한두 점 누락 시 "가짜 0 dip"가 나왔음.

**왜 내 변경으로 심해졌나**
- 새 차트들은 NaN을 자주 방출한다:
  - 롤링 변동성: 인덱스 0에서 창 크기 부족 → NaN 1개
  - 온도 변화율: 인덱스 0에서 이전 포인트 없음 → NaN 1개
  - 비율 3종: flow/power가 임계 미만이면 NaN (펌프 기동/정지 구간에서 흔함)

**수정**
- `MiniLineChart`를 **NaN 기준으로 폴리라인을 끊도록** 리팩터. 연속된 유한값 구간을 `segments: Array<Array<{x,y}>>`로 묶어, 각 구간마다 별개 영역/라인 폴리라인을 렌더. 고립된 1-포인트 구간은 작은 점(r=1.5)으로 표시.
- 영역 채우기도 구간별로 수행해 구간 밖으로 fill이 새지 않도록.

### [BUG-2] 마지막 포인트 원이 엉뚱한 곳에 찍힘 (기존 버그)

**증상**
```tsx
const lastVal = valid[valid.length - 1]; // 마지막 유한값
// ...
<circle cx={toX(values.length - 1, values.length)}  // 끝 x
        cy={toY(lastVal)} />                         // 유한값 y
```
- `lastVal`은 필터된 배열의 끝값인데 `cx`는 원본 끝 인덱스. 원본 끝이 NaN이면 x는 차트 맨 우측, y는 마지막 유한값의 y → 실제 데이터 위치와 어긋남.
- 내 새 차트 중 롤링/온도 변화율은 끝값이 NaN이 될 가능성은 낮지만(끝 쪽은 창이 충분함), 비율 3종은 끝 구간 flow가 줄면 NaN이 가능.

**수정**
- 원본 `values` 배열을 역방향 스캔해 **마지막 유한값의 실제 인덱스** `lastFiniteIdx`를 구함. 원 위치는 `toX(lastFiniteIdx, values.length)`로 보정.

### [BUG-3] `unit=""` 차트에서 최신 값 표기에 후행 공백

**증상**
```tsx
`${lastVal.toFixed(1)} ${unit}`
// unit="" 이면 "0.02 "
```
- 유량 CV는 무단위 → unit=""을 주면 후행 공백 1칸이 남음.

**수정**
```tsx
`${fmt(lastVal)}${unit ? ` ${unit}` : ""}`
```

---

## 3. 그 외 함께 적용한 개선

### 3-1. `MiniLineChart`에 `formatValue` prop 추가 + 스마트 디폴트
기존은 `toFixed(1)` 고정. 온도 변화율(10⁻³ °C/s)이나 CV(10⁻²)는 `"0.0"`으로 잘려 무의미. 새 `defaultFmt`:
- |v| < 0.01 → 지수표기 2자리 (`1.23e-3`)
- |v| < 1 → 소수 3자리
- |v| < 100 → 소수 2자리
- 그 외 → 소수 1자리

기존 도메인 차트(모터 전류, 베어링 진동 등) 표시값도 살짝 더 정밀해지지만 읽기 어려워지는 수준은 아니고 의미는 동일.

### 3-2. 목표선(refValues) NaN 방어
`target_ph`/`target_ec`에 NaN이 섞여도 해당 포인트만 건너뛰고 나머지는 그리도록 필터 추가. 기존에는 NaN 하나로 폴리라인 좌표가 `"x,NaN"`이 되어 SVG 렌더 실패 위험이 있었음.

### 3-3. `toX` 길이 1 방어
`len=1`이면 `(i/0)*IW`로 Infinity가 나오던 것을 중앙 정렬(`IW/2`)로 정리. 현 흐름상 `valid.length >= 2` 얼리리턴으로 도달 불가 경로지만, 방어적으로 추가.

---

## 4. 검증
- `npx tsc --noEmit -p tsconfig.app.json` → exit 0.
- UI 실제 구동/시각 검증은 **수행하지 않음.** 데이터 스트림(INFERENCE WS)이 붙어야 차트가 의미 있으므로, 사용자가 실제 대시보드에서 확인 필요.
  - 체크 포인트: (1) 6개 차트 모두 렌더되는지, (2) 펌프 기동 구간에서 비율 차트가 맨 아래로 떨어지지 않고 선이 끊어지는지, (3) 마지막 값 포맷(특히 온도 변화율과 CV)이 제대로 읽히는지, (4) 변동성 차트 우측 설명에 `12h 값` 병기가 맞는지.

---

## 5. 남은 한계 / 향후 과제

- **롤링 변동성(window=5)과 12h 변동성은 서로 다른 지표.** 이름 혼동 방지 차원에서 차트 라벨을 "(최근)"으로, 12h는 설명에 병기. 더 의미 있는 추이를 원하면 `useDashboardSocket`에서 12h 롤링 시계열을 별도 링버퍼에 축적해서 내려주는 쪽이 깨끗함.
- **비율 차트의 임계값(1 L/min, 0.05 kW)은 경험적 상수.** 실제 펌프 스펙에 맞게 조정 필요.
- **x축 시간 라벨 없음.** 현재는 점 개수 기준 정규화. 실제 시간축(ts)을 쓰려면 MiniLineChart를 수정해야 함.
- **`defaultFmt` 변경이 기존 도메인 차트에도 영향.** 시각적 회귀가 있으면 도메인 차트는 `formatValue={(v) => v.toFixed(1)}`을 명시적으로 넘기면 원복 가능.
