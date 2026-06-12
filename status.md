# STATUS — 현재 상태 대시보드

> 프로젝트 진행을 한눈에 보는 공용 대시보드. "지금 어디까지 됐고 다음이 무엇인가"는 여기만 보면 된다.
> 상세 이력 → [SESSION_LOG.md](SESSION_LOG.md) · 방법론 → [docs/modeling/](docs/modeling/) · 실험 서사 → [.claude/MODEL_CHANGELOG.md](.claude/MODEL_CHANGELOG.md) · 앞으로의 계획 → [docs/DEVELOPMENT_ROADMAP.md](docs/DEVELOPMENT_ROADMAP.md)
> 최종 갱신: 2026-06-12

## 프로젝트
4도메인(motor / hydraulic / nutrient / zone_drip) AutoEncoder 예지보전. 정상 패턴 학습 + 복원오차로 이상 판정 + 6σ 3단계 알람 + SHAP RCA.

## 브랜치·모델 현황
- **main에 통합·푸시 완료** — Phase E~N 작업을 토픽 머지(`topic/01~07`)로 정리해 `main`에 올림(원격 PR #13 통합 포함). 현재 작업: **`topic/08-portfolio-honesty`**(포트폴리오 4지표 근거화, D).
- 백업: `backup/full-history`(원래 단일 브랜치 전체 이력 보존).
- **정본 모델**: run `2026-06-08_182343__d8773ae`(C v6 현실화 데이터 + percentile 임계 + crest_factor). 학습·평가가 읽는 `PROJECT_ROOT/models`.
- 모델 위치 두 곳(주의): `PROJECT_ROOT/models`(정본, 학습·평가) vs `services/inference/models`(서빙 — 구버전, 재학습 후 동기화 필요). ([modeling/11 §6](docs/modeling/11_retrain_checklist.md))

## 작동 확인된 것 (검증됨)
- 재현성(PYTHONHASHSEED re-exec), run 보존본 + experiments.csv, 진단 시각화 자동저장.
- **현실적 고장 주입 프레임** — [fault_injection/](fault_injection/): 영향모델(위치별 cross-domain 전파) + held-out v2 평가셋(독립 seed·4유형 16건) + **막힘률·lead-time·FAR 평가**(baseline 대비 공정 비교) + **Cpk 산출**(`cpk_eval.py`).
- **기동 게이트 정직화** — 평가 경로도 운영처럼 기동 게이트(기동 FAR 100%→0%, lead-time 정직화).
- **센서고장 대조군** — 총 MSE로는 진짜고장/센서글리치 구분 불가, per-feature 집중도가 판별자(단일 0.88~0.92 vs 다중 0.45). ([modeling/10 §3-5](docs/modeling/10_anomaly_signature_ledger.md))
- **Phase 1 측정도구** — `coupling_validate.py` baseline 검출지도(약점 발견: zone_drip이 motor고장 오탐, motor가 suction 진동 놓침).
- 문서 가독성 재작성(어려운 docs 18개, 사실 보존 검증).

## 정본 모델 (2026-06-08, run `..182343__d8773ae`, C v6 + percentile + crest)
- **조건부/마스크 재구성**(context·foreign 피처는 입력만, 채점 제외, Phase K) + **robust slope**(rolling 평균 후 미분, Phase L) + **percentile@99 임계 기본값**(Phase N, FAR whack-a-mole 종결) + **C v6 물리 현실화 데이터**(Na 축적·EC-삼투 디커플링·열관성, Phase M) + **crest_factor**(베어링 조기지표 — 효과 한계적, 정직한 null).
- **held-out v2 평가셋**(독립 seed·4유형 고장 16건)으로 정직 측정 — `fault_injection/baseline_blockage_eval.py`·`cpk_eval.py`:
  - 막힘 에피소드 검출: baseline 12/12 = AE 12/12(동등).
  - **FAR: baseline 3.1% → AE 1.8%**(~1.7배↓, 운영점 P99.5·tumbling 정합 Phase O). 평균 lead-time AE ~28.4h(baseline과 동등). FAR 93%가 정상운전·7%만 기동. nutrient 막힘 RCA는 motor로 오귀인(약점).
  - **유량 공정능력 Cpk ≈1.67**(±10% 스펙, n=9360, 측정값).
  - AE의 측정된 우위 = **FAR↓ + 도메인별 RCA**(baseline은 "어딘가 이상"까지, AE는 "어느 도메인·왜"까지).
- **정직한 포트폴리오 발화**: "단일센서 baseline과 동일 검출하며 오탐 FAR ~1.3배↓ + 원인 도메인 귀인, 막힘을 평균 ~30h 전 감지." 비즈니스 4지표(Cpk·막힘률·OEE·4000만원)는 측정/근거 있는 추정으로 부활 → [portfolio_interview_facts.md §0](docs/portfolio_interview_facts.md).

## 바로 다음 할 일 (우선순위)
1. **포트폴리오 정직화(D) — 진행 중**(`topic/08`): SSOT §0에 4지표 근거화 반영 완료(측정 Cpk + 추정 막힘률·OEE·4000만원). 남은 것: 다운타임 n(다운 1건 길이) 현업 확정 → OEE 가용성 식 채움, jun_portfolio 발화 격상 반영.
2. **README §3 임계 서술 갱신** — "6σ 3단계(2σ/3σ/6σ)"가 정본(percentile@99/99.6)과 불일치. 발화/문서 정합.
3. (선택) motor 기동 band 일반화 — held-out에서 기동 FAR 잔존(기동 시간 바뀌면 재현). validation 기반 재보정.
4. (후속) C3 pH-수온·C4 VPD-증산 데이터 현실화 / hydraulic·nutrient 누락 센서 model_cols 점검.

## 열린 이슈
- **포트 불일치**: README §5(inference 9977/backend 8000/frontend 5173) ↔ docker-compose. 사용자 확인 후 한쪽으로 정합.
- **README §3 임계 서술 낡음**: "6시그마 3단계(2σ/3σ/6σ)"로 적혀 있으나 정본 기본값은 **percentile@99/99.6**(Phase N). README 임계 섹션 갱신 필요.
- **문서↔코드 "F1 0.95"**: MODELING §6·DEVELOPMENT_ROADMAP §0의 F1 0.95는 엄격 eval과 괴리. held-out v2는 검출·FAR·RCA 중심으로 평가(F1은 임계·표본에 민감) → 발화는 검출/FAR/RCA로 정본화함. 문서 내 F1 표기 정합 필요.
- MODELING §3-3 SENSOR_MANDATORY zone_drip 표 구버전(feature_engineering와 불일치) — 동기화 필요.

## 미커밋·미푸시
- `topic/08-portfolio-honesty`의 이번 D 작업(SSOT §0·로드맵 §0 갱신, `cpk_eval.py` 신설, status.md 갱신) — 사용자 커밋 대기.
- 그 외 Phase E~N은 main에 통합·푸시 완료.