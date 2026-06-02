# notebooks — 탐색·실험 노트북

이 디렉터리는 모델 개발 과정의 탐색적 분석과 실험 기록이다.

중요: 현재 운영되는 최종 파이프라인은 노트북이 아니라 `src/`(전처리·피처·학습·평가 Python 모듈)와
`services/inference/`(추론 서비스)에 있다. 노트북은 그 코드로 승격되기 전의 탐색·실험 단계 기록이며,
"살아있는 단일 기준"은 `src/`다. 아래 각 폴더의 대표(기준) 노트북은 그 단계의 결론을 담은 참조본이다.

## 폴더 구조

| 폴더 | 목적 | 대표(기준) 노트북 |
|---|---|---|
| `01_eda/` | 데이터 탐색·상관·파생변수·정제 | `EDA_jun.ipynb` |
| `02_modeling/` | 4도메인 AutoEncoder 학습·임계값 | `model_middle_0423.ipynb` |
| `03_evaluation/` | 성능 평가(F1)·모델 비교 | `eval_f1.ipynb` |
| `04_reporting/` | 고객 지표 대시보드 | `client_metrics_dashboard.ipynb` |
| `_archive/` | 옛 브랜치·팀원별 실험·빈 스텁(이력 보존용, 실행 대상 아님) | — |

## 각 폴더 상세

### 01_eda
- `EDA_jun.ipynb` — 대표. 가장 완성된 EDA(98셀). 데이터 로딩→형변환→결측·상관→파생변수까지 전 과정.
- `EDA_2.ipynb` — 같은 계보의 포크(60셀). 보조.
- `dabin_EDA_jun.ipynb` — dabin 데이터원본 기준 EDA(42셀). 생성 데이터 계보 확인용.
- `data_filtering.ipynb` — 데이터 필터링 룰 탐색(22셀). 프론트의 룰기반 필터 페이지 근거.

### 02_modeling
- `model_middle_0423.ipynb` — 기준(현 컴퓨터 기준 최신, leon, 2026-04-25 커밋). 4도메인
  AutoEncoder + 2σ/3σ 임계값 + F1을 담은 정리본(12셀).
- 대안: `_archive/model_middle_0420.ipynb`(yunseok, 7커밋, 36셀)는 더 풍부한 탐색본이다.
  - 0423(기준)과의 차이: 0423은 0420을 슬림화한 후속 컷으로, SHAP 피처중요도 탐색(0420은
    SHAP 약 40회 등장)을 걷어내고 도메인별 반복을 줄여 4도메인 AE + 임계값 + 평가 핵심만 남겼다.
    설명력(피처 기여·SHAP) 까지 보려면 0420을, 정리된 최종 흐름을 보려면 0423을 본다.

### 03_evaluation
- `eval_f1.ipynb` — 대표. 도메인별 F1/Precision/Recall, 혼동행렬, PR커브, 이벤트레벨 F1, 요약표.
- `model_comparison_jun.ipynb` — AutoEncoder vs IsolationForest vs One-Class SVM 비교.

### 04_reporting
- `client_metrics_dashboard.ipynb` — 고객 지표 대시보드.

### _archive (실행 대상 아님, 이력 보존)
- `model_middle_0420.ipynb` — 위 02_modeling 항목의 풍부본(SHAP 포함).
- `modeling_stronger_jun.ipynb`, `modeling_jun.ipynb` — SHAP 중심 옛 모델링 브랜치.
- `chuniiii_0423.ipynb` — 스크래치 실험(leon).
- `EDA.ipynb` — 빈 스텁(2셀). `Hypothesis_Testing.ipynb` — 코드 없는 메모(md 2셀).

## 이 폴더 밖의 노트북(참고)
- `data/smartfarm_pump_eda_v4.ipynb` — 학습용 60일 데이터 생성 노트북(데이터 산출물 성격).
- `data/Causal-Inference-and-Discovery-in-Python-main/*.ipynb` — 서드파티 교재(프로젝트 작업물 아님).
- `services/inference/notebooks_jun/test_data_gen.ipynb` — 추론 서비스용(gitignore 대상).
