# 📚 docs/ 인덱스

스마트팜 양액펌프 막힘 사전 감지 AI 시스템의 모든 문서.
프로젝트 개요는 루트 [README.md](../README.md)부터 보세요.

---

## 읽는 순서

목적에 따라 순서가 다릅니다.

### 🎯 처음 본 사람 — 프로젝트가 뭐 하는지 알고 싶다
1. 루트 [README.md](../README.md) — 프로젝트 정체성·시스템 개요
2. [PROJECT_BRIEF.md](PROJECT_BRIEF.md) — 팀·일정·핵심 의사결정 타임라인
3. [DOMAIN_KNOWLEDGE.md](DOMAIN_KNOWLEDGE.md) — 양액·점적관수·왜 막히는가
4. [ANALYSIS.md](ANALYSIS.md) — 어떤 데이터로 무엇을 봤는가
5. [MODELING.md](MODELING.md) — 어떻게 모델링했는가

### 🔌 프론트엔드 작업자 — API 붙이고 화면 그려야 한다
1. [FRONTEND_PAGES.md](FRONTEND_PAGES.md) — 어떤 페이지에 무엇을 그릴지
2. [INFERENCE_API.md](INFERENCE_API.md) — `/predict` 요청/응답 스키마, 파생변수
3. [COLUMNS_REFERENCE.md](COLUMNS_REFERENCE.md) — 모든 컬럼 의미·단위
4. [SHAP_BEESWARM_FRONTEND.md](SHAP_BEESWARM_FRONTEND.md) — XAI 시각화 데이터 계약

### 🧠 모델 담당 / 합류한 데이터 사이언티스트
1. [PROJECT_BRIEF.md](PROJECT_BRIEF.md) — 무엇이 시도됐고 실패했는지 (Phase A-1, A-3, NUTRIENT 오탐)
2. [DOMAIN_KNOWLEDGE.md](DOMAIN_KNOWLEDGE.md) — 왜 startup spike가 정상인지의 물리적 근거 등
3. [ANALYSIS.md](ANALYSIS.md) — EDA·도메인 정의·SHAP 인사이트
4. [MODELING.md](MODELING.md) — 전처리·AE 구조·임계치 전략·알려진 이슈
5. [COLUMNS_REFERENCE.md](COLUMNS_REFERENCE.md) — 피처 사전
6. 루트 [.claude/MODEL_CHANGELOG.md](../.claude/MODEL_CHANGELOG.md) — 모델 실험 변천사 (가설 → 시도 → 결과)
7. 루트 [SESSION_LOG.md](../SESSION_LOG.md) — 세션 인수인계 로그

---

## 문서 일람

| 문서 | 한 줄 요약 | 주요 독자 |
|---|---|---|
| [PROJECT_BRIEF.md](PROJECT_BRIEF.md) | 팀·일정·핵심 의사결정·실패 학습·진행 중 문제·다음 단계 | 신규 합류자, 인수인계 |
| [DOMAIN_KNOWLEDGE.md](DOMAIN_KNOWLEDGE.md) | 양액 시스템·점적관수·CNL 핀·기동 spike·딸기 환경 권장값 | 모두 (특히 신규 합류자) |
| [ANALYSIS.md](ANALYSIS.md) | 데이터 출처·EDA·도메인 정의·SHAP 인사이트 | DS, 신규 합류자 |
| [MODELING.md](MODELING.md) | 전처리 5단계·AE 구조·6시그마 임계치·학습 결과·알려진 이슈 | DS, 모델 담당 |
| [INFERENCE_API.md](INFERENCE_API.md) | `/predict` API 스펙 · 응답 필드 · 파생변수 정의 | 프론트, 백엔드 |
| [FRONTEND_PAGES.md](FRONTEND_PAGES.md) | 도메인별 페이지 구성·차트·KPI 설계 | 프론트, 디자이너 |
| [COLUMNS_REFERENCE.md](COLUMNS_REFERENCE.md) | Raw + 파생 컬럼 사전 (단위·정의) | 모두 |
| [SHAP_BEESWARM_FRONTEND.md](SHAP_BEESWARM_FRONTEND.md) | SHAP beeswarm 렌더용 JSON 계약 | 프론트, ML |

---

## 코드 ↔ 문서 매핑

| 코드 위치 | 관련 문서 |
|---|---|
| [services/inference/src/preprocessing.py](../services/inference/src/preprocessing.py) | [MODELING.md §전처리](MODELING.md), [COLUMNS_REFERENCE.md](COLUMNS_REFERENCE.md) |
| [services/inference/src/feature_selection.py](../services/inference/src/feature_selection.py) | [MODELING.md §피처 선택](MODELING.md), [SHAP_BEESWARM_FRONTEND.md](SHAP_BEESWARM_FRONTEND.md) |
| [services/inference/src/feature_engineering.py](../services/inference/src/feature_engineering.py) | [MODELING.md §VIP/필수 센서](MODELING.md) |
| [services/inference/src/model_builder.py](../services/inference/src/model_builder.py) | [MODELING.md §AE 아키텍처](MODELING.md) |
| [services/inference/src/train.py](../services/inference/src/train.py) | [MODELING.md §학습·임계치](MODELING.md) |
| [services/inference/src/inference_api.py](../services/inference/src/inference_api.py) | [INFERENCE_API.md](INFERENCE_API.md) |
| [services/inference/src/inference_core.py](../services/inference/src/inference_core.py) | [INFERENCE_API.md](INFERENCE_API.md) |
| [services/frontend/src/](../services/frontend/src/) | [FRONTEND_PAGES.md](FRONTEND_PAGES.md) |

## 외부 자료 ↔ 문서 매핑

| 외부 자료 | 흡수된 위치 |
|---|---|
| 노션 — 최종 보고서 | [PROJECT_BRIEF.md](PROJECT_BRIEF.md) (전반), [MODELING.md §9 알려진 이슈](MODELING.md), [ANALYSIS.md §1-3 EC/pH 배제](ANALYSIS.md) |
| 노션 — 데이터 분석 프로젝트 기획서 | [PROJECT_BRIEF.md §3-1 기획 단계](PROJECT_BRIEF.md), 루트 [README.md §1](../README.md) |
| 노션 — 프로젝트 중간 보고서 | [PROJECT_BRIEF.md](PROJECT_BRIEF.md) |
| 노션 — 프로젝트 docs (배경지식·논문·환경) | [DOMAIN_KNOWLEDGE.md](DOMAIN_KNOWLEDGE.md) |
| 노션 — 강사님 피드백 | [PROJECT_BRIEF.md §7](PROJECT_BRIEF.md) |
| PPT 발표 스크립트 | 전 docs (기조·정량값·도메인별 SHAP 인사이트) |

## 문서 작성 규칙

- 모든 코드 참조는 마크다운 링크 형식: `[파일명](상대경로)` 또는 `[파일명:줄번호](경로#L줄번호)`
- 상대 경로는 `docs/` 기준 `../` 사용
- 한국어 우선 (영문 용어는 처음 등장 시 괄호 병기)
- 표·다이어그램으로 구조를 먼저 보이고, 본문에서 디테일 설명
- **사실의 단일 소스화** — 같은 사실(예: 알람 시그마 레벨)을 여러 곳에 쓸 때는 한 곳에만 본문, 다른 곳은 링크
