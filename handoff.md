# HANDOFF — 작업 인수인계

> 이 프로젝트를 이어서 작업할 때 먼저 읽는 문서. 현재 상태 요약은 [status.md](status.md), 세션별 상세 이력은 [SESSION_LOG.md](SESSION_LOG.md).
> 최종 갱신: 2026-06-01

## 1. 지금까지 한 일
1. 모델링 기획·방법론 문서 [docs/modeling/](docs/modeling/) (README + 01~09): 01 실험프로토콜 / 02 평가설계 / 03 threshold / 04 착수체크리스트 / 05 재현성구현 / 06 시각화 / 07 학습런북 / 08 도메인지표검증 / 09 피처 근거 원장
2. 재현성·추적 인프라 [src/repro.py](src/repro.py) + 진단 시각화 [src/viz.py](src/viz.py), train/evaluate 연동(services 동기화). 커밋 `5de0f9e`.
3. 재현성 진범(PYTHONHASHSEED) 규명·수정(re-exec) → **2회 학습 config 동일 확인(확보 완료)**.
4. zone_drip 퇴화 원인 규명(전역 `model_cols`가 zone 센서를 누락) → 배지 센서 복원 코드 수정(재학습 대기).
5. EC/pH 처리 재정리(Path B: 보조 지표) — 문서·포트폴리오 발화 9곳 수정.
6. [09 피처 근거 원장](docs/modeling/09_feature_rationale_ledger.md) 신설 — 기존+제안 파생 피처를 공식·물리근거·탐지로 정리.

## 2. 핵심 발견
- **재현성 진범 = Python 해시 무작위화(PYTHONHASHSEED)**. 2회차 테스트가 잡음(config 4도메인 전부 다름). set 순서가 매 실행 달라져 다중공선성 드롭·robust voting이 다른 컬럼 선택. 런타임 os.environ 대입 무효 → re-exec로 수정, 재검증 통과. (초기 "TF가 진범"은 오진) — [MODEL_CHANGELOG Phase D](.claude/MODEL_CHANGELOG.md).
- **zone_drip 퇴화 = 전역 `model_cols` 화이트리스트에 zone 센서 부재** → 집계 전에 잘려 배지 센서 0개로 학습. 배지 센서(`zone1_substrate_moisture_pct`·`_ec`, Raw) + 구역 편차 파생 복원, 펌프 중복인 zone 압력/유량은 제외. (도메인 경계 정리: `supply_balance_index`는 유량 지표라 hydraulic으로 이동, zone_drip은 순수 "구역 배지 상태"가 됨 — [docs/DOMAIN_DESIGN.md](docs/DOMAIN_DESIGN.md))
- **EC/pH는 삭제된 적 없음** — nutrient가 raw `mix_ec`/`mix_ph` 사용. "제외" 서사는 틀렸고, 실제는 "보조 지표로 분리(voting 제외)". 다변량 AE가 단일 센서 노이즈 흡수 + `EXCLUDE_FROM_OVERALL={"nutrient"}`가 보조 취급 뒷받침.
- 복원오차 분포 skew 14~18 → σ 고정 threshold 부적절, percentile 전환 정당화.

## 3. 파일 지도
- 방법론/기획: [docs/modeling/](docs/modeling/) (README가 색인)
- 학습 전 체크리스트: [docs/modeling/07_training_runbook.md](docs/modeling/07_training_runbook.md)
- 인프라 코드: [src/repro.py](src/repro.py), [src/viz.py](src/viz.py) (services/inference/src에 동일본)
- 학습: [src/train.py](src/train.py) / 평가: [src/evaluate_test_metrics.py](src/evaluate_test_metrics.py)
- 산출물: `models/runs/<run_id>/` (모델 + figures + run_meta.json), `logs/experiment_board.csv`
- 실험 서사: [.claude/MODEL_CHANGELOG.md](.claude/MODEL_CHANGELOG.md) / 세션 이력: [SESSION_LOG.md](SESSION_LOG.md)

## 4. 실행법
### 학습
```bash
export PHASE=<실험라벨>
python src/train.py
```
사전 체크리스트(모델 백업·환경·데이터·PHASE)는 [07_training_runbook.md](docs/modeling/07_training_runbook.md).

### 재현성 검증 (이미 통과 — 재확인용)
re-exec 수정 후 `repro-a`·`repro-b` 2회 학습 config가 4도메인 모두 동일함을 확인했다(확보 완료). 코드 변경 후 다시 확인하려면 새 run 2개를 같은 방식으로 비교:
```bash
export PHASE=chk-a; python src/train.py; A=$(cat models/LATEST_RUN.txt)
export PHASE=chk-b; python src/train.py; B=$(cat models/LATEST_RUN.txt)
for d in motor hydraulic nutrient zone_drip; do
  diff -q "models/runs/$A/${d}_config.json" "models/runs/$B/${d}_config.json" \
    && echo "$d 동일 (재현 OK)" || echo "$d 다름"
done
```

### 평가 (라벨 데이터 + 이상 음영 타임라인)
```bash
python src/evaluate_test_metrics.py
```
결과 그림은 같은 run의 `models/runs/<run_id>/figures/<도메인>__eval_timeline.png`에 합류.

## 5. 미해결 이슈 (우선순위)
[status.md](status.md) "열린 이슈" 참조. 순서: **피처 1차 배치 구현([09 §5](docs/modeling/09_feature_rationale_ledger.md)) + zone-soil 복원을 `PHASE=feature-v2`로 학습 → 진단 그림으로 빈약 해소 + 타 도메인 회귀 점검 → percentile threshold 실험.** (재현성·zone 원인규명은 완료)

## 6. 운영 규칙
- 문서·코드 주석에 이모지 금지, 친절하되 격식 있는 문어체. (수학기호 σ μ → 는 허용)
- 무거운 학습(`train.py`)·대량 렌더는 사용자가 직접 실행.
- 모델 아티팩트는 덮어쓰지 않음 — 라이브 `models/`는 서빙용, `models/runs/<run_id>/`는 보존본.
- 재현성 확보 전의 "성능 개선"은 보고하지 않음 (우연과 구분 불가).
