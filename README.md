# 🌿 스마트팜 양액펌프 막힘 사전 감지 AI 시스템

> **점적관수 노즐·관로 폐쇄로 인한 다운타임과 작물 피해를, 고장 발생 *전*에 예측하여 차단합니다.**

스마트팜 양액 시스템에서 발생하는 점적 노즐 막힘·관로 폐쇄·펌프 과부하를 **AutoEncoder 기반 4도메인 이상 탐지 모델**로 사전에 감지하고, 근본 원인(RCA)까지 함께 제공하는 예지보전 시스템입니다.

| 팀명 | 기간 | 팀 구성 (5명) |
|---|---|---|
| **막힘주의보** | 2026.04.07 ~ 2026.04.23 | 김현준 (팀장·분석) · 김다빈 (분석) · 김천의 (분석) · 한승보 (백엔드·인프라) · 오윤석 (프론트·백엔드) |

---

## 1. 왜 양액펌프인가

스마트팜의 **양액 시스템은 사람의 심장과 같은 역할**을 합니다. 원수와 비료를 최적 비율로 혼합해 점적관수 호스로 재배지 곳곳에 균일하게 공급하죠. 국내 스마트팜 90% 이상이 점적 관수 방식을 사용합니다.

문제는 **염류 축적·유기물 침전·이물질 유입으로 점적 노즐과 관로가 점차 막힌다**는 점입니다. 이게 진행되면:

- **부분 막힘** → 구역별 급수 편차 → 일부 작물만 시들거나 과습으로 뿌리 부패
- **펌프 과부하** → 베어링 마모, 캐비테이션, 임펠러 손상 → 펌프 수명 급감
- **돌발 정지** → 재배사 *전체* 작물에 동시 수분 미공급 → 회복 불가능한 스트레스

→ **고장 후 수리비보다 생산 중단 손실이 훨씬 큽니다.** 미리 잡는 게 핵심입니다.

> 양액 시스템·점적관수·CNL 핀·양액 결정화·기동 spike 메커니즘 등 자세한 도메인 지식은 [docs/DOMAIN_KNOWLEDGE.md](docs/DOMAIN_KNOWLEDGE.md) 참조.

## 2. 시스템 개요

```
┌─────────────┐  MQTT  ┌──────────┐  WebSocket  ┌──────────┐
│  Sensor Sim │───────▶│ Backend  │────────────▶│ Frontend │
└─────────────┘        │ (FastAPI)│             │  (React) │
       │               └────┬─────┘             └──────────┘
       │ MQTT               │ REST
       ▼                    ▼
┌─────────────┐  10min   ┌──────────────┐
│   S3 Sink   │─────────▶│ AI Inference │──┐
│  (MinIO)    │  batch   │ (4 AE models)│  │ Postgres
└─────────────┘          └──────────────┘  ▼
                                       (alarms · scores)
```

두 개의 데이터 흐름:

1. **실시간 흐름** — MQTT로 발행된 센서값을 backend가 직접 구독 → WebSocket으로 프론트에 즉시 전달 (저장 없음)
2. **배치 추론 흐름** — 같은 MQTT 데이터를 S3 Sink가 10분 단위로 MinIO에 적재 → Inference 엔진이 전처리·피처 선택·AE 추론·임계치 판정·DB 저장

### 4개 도메인 AE 모델

농장을 4개 도메인으로 분리해 도메인별 AE를 학습합니다. 단일 센서 임계값으로는 외부 환경·작물 상태에 따라 변하는 정상 범위를 따라잡을 수 없기 때문입니다.

| 도메인 | 감시 대상 | 주요 이상 |
|---|---|---|
| `motor` | 모터 전력·전류·온도·RPM·베어링 진동 | 베어링 마모, 과부하, 권선 절연 열화 |
| `hydraulic` | 토출/흡입 압력·유량·필터 차압 | 배관 막힘, 누수, 밸브 이상 |
| `nutrient` | 양액 EC/pH·목표 오차·염류 축적 | A/B액 비율 오류, 양액펌프 막힘, 센서 드리프트 |
| `zone_drip` | 구역 유량·압력·배지 수분/EC | 점적 노즐 막힘, 구역 관수 불균일, 배지 염류 |

> 필터 막힘은 별도 AE 없이 **룰 기반 페이지**로 운영합니다 (학습 데이터 부족, 단일 변수 r=0.37로 독립 신호 약함).

## 3. 핵심 기술 결정

### 왜 AutoEncoder인가
- 고장 데이터가 드물고 라벨이 없어 **지도학습 불가**
- 정상 데이터는 수십만 건 → "정상 구조만 학습 → 벗어나면 이상" 비지도 접근 적합
- One-Class SVM·Isolation Forest·GMM 등 전통 기법은 40+ 차원 비선형 데이터에 한계
- AE는 **복원 오차를 피처별로 분해**할 수 있어 RCA(어느 센서가 이상한지) 자연스럽게 제공

### 왜 EC/pH를 학습에서 제외했나
화학 센서인 EC/pH는 양액에 상시 노출되어 미생물막·스케일로 오감지가 잦고 지속적인 보정이 필요합니다. **현실 시나리오에서 신뢰도가 떨어지므로 학습 입력에서 배제**하고, 더 안정적인 물리 센서(압력·유량·전류·진동·RPM·온도)로 예지보전 학습을 수행했습니다.

### 임계치 — 6시그마 3단계 알람
복원 오차 MSE에 대해 도메인별로 임계치를 잡되, **"정상 분포에서 상위 몇 σ"**로 통일해 설비별 공정한 비교가 가능하게 합니다.

| 단계 | 기준 | 의미 |
|---|---|---|
| 🟡 주의 (Caution) | 2σ | 운영자 모니터링 강화 |
| 🟠 경고 (Warning) | 3σ | 정비 일정 사전 조율 |
| 🔴 치명 (Critical) | 6σ | 즉시 점검 / 출동 |

추가로 **"N분 이상 연속 임계 초과"** 룰로 헛출동 인건비까지 줄였습니다.

## 4. 폴더 구조

```
human_A/
├── docker-compose.yaml          # 서비스 오케스트레이션
├── README.md                    # 이 파일
│
├── infra/                       # 검증된 인프라 설정
│   ├── mosquitto/               # MQTT 브로커
│   └── postgres/                # DB 초기화 스크립트
│
├── services/                    # 비즈니스 로직 (이미지 빌드)
│   ├── frontend/                # React + Vite — 모니터링 대시보드
│   ├── backend/                 # FastAPI — API/WebSocket 중계
│   ├── sensor-simulator/        # MQTT 센서값 발행 (CSV → MQTT)
│   ├── s3-sink/                 # MQTT → MinIO 적재 (10분 배치)
│   └── inference/               # AI 추론 서비스
│       ├── src/                 # 학습/추론 코드 (단일 소스)
│       └── models/              # 학습된 AE 4종 + threshold + SHAP
│
├── docs/                        # 📚 프로젝트 문서 — docs/README.md 부터 보세요
├── notebooks/                   # EDA / 모델 비교 / 시각화
├── data/                        # 데이터셋 (gitignore)
└── ppt/                         # 발표 자료
```

> **참고**: 루트 [src/](src/)는 [services/inference/src/](services/inference/src/)와 동일한 미러본입니다. 단일 소스화 작업 진행 예정.

## 5. 빠른 시작

### 전체 스택 기동
```bash
docker compose up -d
```
- Frontend: http://localhost:5173
- Backend (Swagger): http://localhost:8000/docs
- Inference (Swagger): http://localhost:9977/docs
- MinIO Console: http://localhost:9001

### 모델 학습 (로컬)
```bash
cd services/inference
pip install -r requirements.txt
python src/train.py        # 4개 도메인 AE 학습 → models/ 저장
```

### 단일 추론 테스트
```bash
curl -X POST http://localhost:9977/predict \
  -H "Content-Type: application/json" \
  -d @sample_payload.json
```

API 스펙은 [docs/INFERENCE_API.md](docs/INFERENCE_API.md) 참조.

## 6. 기술 스택

| 영역 | 사용 기술 |
|---|---|
| 언어 | Python 3.12, TypeScript |
| 인프라 | Docker, Mosquitto (MQTT), MinIO (S3 mock), PostgreSQL |
| 백엔드 | FastAPI, SQLAlchemy, Paho-MQTT, WebSocket |
| 프론트 | React, Vite, TailwindCSS |
| 데이터/ML | Pandas, scikit-learn, **TensorFlow Keras** (AutoEncoder), **SHAP**, Optuna |

## 7. 문서

| 문서 | 내용 |
|---|---|
| [docs/README.md](docs/README.md) | 📚 문서 인덱스 — 여기부터 시작 |
| [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md) | 프로젝트 진행 기록 — 팀·일정·실패 학습·다음 단계 |
| [docs/DOMAIN_KNOWLEDGE.md](docs/DOMAIN_KNOWLEDGE.md) | 양액·점적관수·CNL 핀·딸기 환경 등 도메인 배경지식 |
| [docs/ANALYSIS.md](docs/ANALYSIS.md) | 데이터 분석 — EDA, 도메인 정의, SHAP 인사이트 |
| [docs/MODELING.md](docs/MODELING.md) | 모델링 — 전처리 5단계, AE 아키텍처, 임계치 |
| [docs/INFERENCE_API.md](docs/INFERENCE_API.md) | 추론 API — 요청/응답 스키마, 파생변수 |
| [docs/FRONTEND_PAGES.md](docs/FRONTEND_PAGES.md) | 프론트 페이지 설계 |
| [docs/COLUMNS_REFERENCE.md](docs/COLUMNS_REFERENCE.md) | 전체 컬럼 사전 (Raw + 파생) |
| [docs/SHAP_BEESWARM_FRONTEND.md](docs/SHAP_BEESWARM_FRONTEND.md) | SHAP beeswarm 프론트 연동 |

## 8. 기대 효과

자료조사 결과 1000평 딸기 스마트팜 기준으로 추정한 정량 가치:

- 신규 양액 시스템 교체 회피: **약 4,000만원**
- 균일한 양액 공급으로 고품질 등급 상품 비율 약 **10% 증가** 예상
- 헛출동·긴급 정비 인건비 절감

→ 연간 **약 4천만원 이상의 경제적 가치 창출** + 재배 안정성 확보 + 스마트팜 운영 노하우의 기술적 자산화

## 9. 향후 발전 방향

- **멀티모달 확장** — 양액펌프 + 환경/생육 데이터 결합한 복합 이상 탐지
- **Edge AI** — 현장 장비에서 실시간 추론 가능한 경량화 모델
- **B2B 플랫폼화** — 기존 스마트팜 제어 솔루션과 API 연동, 양액기 제조사 협업

## License
[MIT](LICENSE)
