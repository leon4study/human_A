# SESSION_LOG

## 2026-06-07 — B4 재학습 측정: jun baseline 정본화 + motor FAR 회귀 발견 — feat/sensor-fault-control

### 달성 (Accomplished)
1. 사용자가 jun 정상셋으로 4도메인 재학습(DOMAIN_ISOLATION=1, run ..110219..) + 서빙 동기화 완료.
   §7 관계피처 모델 진입 확인(motor:vibration_per_load·hydraulic:transpiration_demand 강제주입,
   nutrient:leaching_ratio SHAP 자연선정). 기동 band 정상상태 대비 6.5배 분리.
2. 측정도구 4종 + 도메인별 FAR 분해 재실행 → 새 jun baseline 정본화(ledger §3-6, MODEL_CHANGELOG Phase J).
3. 기동 regime band 재확인: 정상기동 FAR 1.3%, 비정상 ≥1.2배 recall 100%(양호).

### 발견 (Findings) — 정직 측정
- **motor FAR 회귀**: AE overall 정상 FAR 6.5%(> baseline 3.2%, > 5% 목표). 도메인 분해 결과
  motor 6.3%가 주범(hydraulic 2.7·nutrient 1.1·zone_drip 1.1). Phase I(dabin)는 1.4%였음.
- attribution: 4 root 모두 검출(O)하나 Phase I의 깨끗함 일부 후퇴 — bearing_wear에 hydraulic 0.43,
  nutrient_imbalance에 motor 0.86 오탐. motor 과발화와 동일 뿌리.
- 검출 유지: clog 6/6, 막힘률 0%, lead-time 47.5h(같은 데이터 baseline 45.5h).
- 집중도 판별 비재현: clog 0.65 > drift/spike 0.40(역전). dabin 분리(0.88 vs 0.45)가 jun에서 깨짐.
- §7 피처 vibration_per_load·transpiration_demand는 여전히 다중공선성 드롭 → 강제주입으로만 생존
  (자연 선택 실패 = 판별력 아닌 노이즈 가능성, motor FAR 회귀의 용의자).

### 절대 규칙 (Absolutes)
- 새 측정 수치(FAR 6.5%·lead-time 47.5h)는 jun 데이터 기준. dabin Phase I(1.4%·35.9h)와 직접 비교 금지
  (데이터셋·에피소드 배치 다름). 포트폴리오는 motor 수정·정본화 전까지 Phase I 수치 유지 + 단서.
- 측정도구는 PROJECT_ROOT/models(학습 저장 위치)를 읽는다. 재학습 후 services 동기화 cp 필수.

### 재개 지점 (Resume Point)
1. **motor FAR 수정**(사용자 방향 결정 대기): (i) motor threshold percentile화/sigma 상향,
   (ii) 강제주입 노이즈피처(vibration_per_load·temp_slope) 정리, (iii) 병행. → 재학습 → 재측정으로
   Phase I 대비 회복 확인.
2. 이후 C(화학·농학 현실화) 또는 D(포트폴리오 정직화) 중 선택.

## 2026-06-07 — 캐노니컬 데이터 전환 B (dabin → jun 정상셋 v5) — feat/sensor-fault-control

### 달성 (Accomplished)
1. 학습·평가·고장주입 파이프라인의 데이터 원천을 generated_data_from_dabin_0420.csv →
   smartfarm_normal_train_v5.csv로 일괄 전환(B3). dabin의 월1-클린업 artifact와 센서 인위적
   상관(~1.0, 다중공선성 필터에 도메인 피처가 깎이던 근본 원인)을 제거. 변경 7개 파일:
   src/train.py·services/inference/src/train.py(경로 전환+절대경로 제거, 두 트리 byte-동일),
   fault_injection 5종(build_faulty_testset·baseline_blockage·sensor_fault·startup_strategy·
   coupling_validate — CLEAN_CSV 전환 + 'dabin 월1' 잔존 주석을 'clean 90일셋 앞 30일'로 정정).
2. B1(직전 커밋): data_gen_jun.save_normal_training_set()로 공공앵커 기반 90일 clog-free
   정상셋 생성(129,600행, 독립성 게이트 통과: suction↔discharge -0.03·vibration↔discharge 0.02 등).
3. B2: faulty_testset_v1.csv를 jun 정상 base에서 재생성(하류 막힘 6건, anomaly 4.2%, 고장시점 전건 기록).
4. 검증: §7 관계피처 3종(vibration_per_load·leaching_ratio·transpiration_demand)이 새 데이터에서
   NaN 0으로 계산(leaching≈1.12=배액 농축·transpiration 주간↑야간0), train.py 두 트리 동일, py_compile 통과.

### 남은 과제 (Pending)
1. **B4(사용자 실행, 리소스 작업)**: jun 정상셋으로 4도메인 재학습 → 측정도구 4종 재실행 →
   새 baseline 정본화 + 기동 band 생성·regime 실활성. (명령은 아래 재개 지점)
2. C(화학·농학 현실화): Na 축적·pH-기온·습도-VPD-병해·EC-삼투·이온수지 관계를 data_gen에 인코딩
   → 재학습. (ledger §3-3 agenda)
3. D(포트폴리오 정직화): 재학습 확정 수치로 "F1 0.95"·"막힘률 10→2%" 교체.
4. 센서 설명 .md 동기화(COLUMNS_REFERENCE·DOMAIN_KNOWLEDGE). 미푸시분 푸시. 포트 불일치(README §5 vs compose) 확인.

### 절대 규칙 (Absolutes)
- data/는 gitignore — 정상셋·faulty_testset은 스크립트+고정seed(42)로 재현. CSV를 커밋하지 않는다.
- src/ 트리 .py는 CRLF 유지(형제 파일 일관성). Edit 후 줄바꿈 정규화로 diff가 부풀면 바이트 보존 치환으로 복구.
- 물리적으로 결합된 센서를 인위적으로 디커플하지 않는다 — 관계피처로 고장신호를 잡고 실제 물리는 보존(사용자 교정).

### 재개 지점 (Resume Point)
1. **B4 재학습(사용자)** — 권장 명령:
   ```bash
   cd /Users/jun/GitStudy/human_A
   DOMAIN_ISOLATION=1 python src/train.py      # 타 도메인 핵심센서 격리(깨끗한 귀인). 기동 band 자동 생성.
   # 재학습 후 서빙 동기화:
   cp models/*_model.keras models/*_scaler.pkl models/*_config.json services/inference/models/
   ```
2. 재학습 후 측정도구 4종 재실행(cd fault_injection && python <도구>.py): coupling_validate·
   baseline_blockage_eval·sensor_fault_eval·startup_strategy_eval → 새 baseline 표를 ledger §3-6·08에 정본화.
3. 그 다음 C(화학·농학) 또는 D(정직화) 중 사용자 선택.

## 2026-06-05 — 문서 쉬운 말로 풀어쓰기 (가독성) — feat/sensor-fault-control

### 달성 (Accomplished)
- 어려운 문서를 표현만 쉽게 재작성(사실·숫자·경로·링크·표·코드 100% 보존, 매 파일 기계 검증).
  깊게 재작성: ledger 10, modeling 03, 08(+제목 07→08 오류 수정), MODELING.
  용어 풀이: modeling 01·02·04·05·06·07·09·11, DOMAIN_KNOWLEDGE, ANALYSIS, INFERENCE_API, PROJECT_BRIEF.
- 검증 방식: HEAD vs 현재의 숫자·링크·백틱코드·헤딩 멀티셋 대조로 "사라진 사실 0" 확인 후 커밋.
- 서브에이전트 6개로 병렬 시도했으나 Edit/Write 권한 없어 실패 → 메인에서 직접 수행.
- 남은 문서(DOMAIN_DESIGN·ONBOARDING·DEPLOYMENT·git-strategy·ADR 등)는 이미 평이,
  COLUMNS_REFERENCE·docker-cleanup·로그는 정의·명령·로그라 풀이 대상 아님 → 사용자 결정으로 마무리.

### 재개 지점 (Resume Point) — 변동 없음
1. Phase 3 재학습(사용자): DOMAIN_ISOLATION ON/OFF + 기동 band 생성 → coupling_validate 재측정.
2. Phase 2 #2(motor 진동 민감도), 포트폴리오 정직화(F1 0.95 교체).
3. 미푸시분 한 번에 푸시(feat/fault-injection-eval는 푸시됨, feat/sensor-fault-control 미푸시).
4. 포트 불일치(README §5 vs compose) 사용자 확인.

## 2026-06-05 — Phase 1: 결합 영향 모델 일반화 + baseline 측정 도구 — feat/sensor-fault-control

### 달성 (Accomplished)
1. 고장을 '근본원인→s(t)→가중치 다중센서/도메인 전파' 영향 프로파일로 일반화(`fault_signatures.py`).
   방향=data_gen_jun clog 계수, 크기·보정=ledger §3. 위치 4종: clog(광역)·bearing(motor국소)·
   suction(흡입,토출압↓)·nutrient(국소). inject.py failure_rule에 ratio_above·below_abs 추가.
2. `coupling_validate.py`: 데이터 ripple(propagates_to 정답지 대조) + 현재 6/2 모델 baseline 검출지도.
3. 검증: ripple이 각 위치 propagates_to와 일치(위치 바꾸면 의도 센서가 가중치대로 움직임).
   baseline이 약점 3개 발견 — zone_drip이 motor고장 오탐(motor_temp 누설), motor가 suction 진동 놓침,
   nutrient 수력 부분오탐. ledger §3-6 기록.

### 추가 (2026-06-05): Phase 2 #1 도메인 격리 플래그 + 문서 쉽게 풀기 시작
- Phase 2 #1: `DOMAIN_ISOLATION=1`(기본 OFF) — 도메인별 피처 선택에서 타 도메인 핵심 센서
  (SENSOR_MANDATORY) 제외. zone_drip의 motor_temperature_c 누설 차단. train.py·feature_selection.py.
  A-3 위험 지대라 재학습 시 ON/OFF를 coupling_validate로 비교 후 도입. 약점 2(motor 진동)는 미구현.
- 문서 쉽게 풀기: 서브에이전트는 Edit 권한 없어 실패 → 메인(내가) 직접. 가장 어려운 것부터
  (ledger 10, modeling 03·09, SESSION_LOG) 진행 중.

### 재개 지점 (Resume Point)
1. **Phase 3** — 재학습(사용자, 체크리스트 11) `DOMAIN_ISOLATION=1` ON/OFF 둘 다 → coupling_validate로
   "zone_drip이 motor 고장 오탐 사라졌나" 비교. + 기동 band 생성·regime 활성.
2. Phase 2 #2 — motor 진동 민감도(vibration_per_load §3-4) 미구현.
3. 문서 쉽게 풀기 계속(나머지 docs).
4. 미푸시분 한 번에 푸시. 포트 불일치 확인.

## 2026-06-04 — 센서고장 대조군 실험 (강사 원칙 검증) — feat/sensor-fault-control

### 달성 (Accomplished)
1. 단일 센서 고장 주입기 `fault_injection/sensor_faults.py`(drift·spike·stuck) + 판별 실험 `sensor_fault_eval.py` 구현.
2. 실험(hydraulic, discharge_pressure 단일센서 vs faulty_testset_v1 다중 막힘):
   - 총 MSE/알람으로는 구분 불가(단일 센서도 알람 99~100%, 진짜 막힘 69%).
   - **집중도(per-feature concentration)가 판별 신호**: 단일 0.88~0.92 vs 다중 0.45. 강사 원칙 정량화.
   - 한계: n_active는 큰 spike에서 오히려 증가(부적합), stuck은 집중도 0.49로 애매.
3. ledger §3-5 실험 결과 기록, §5 가설을 실측으로 교정, §6 진행상태 갱신.

### 발견 (Findings)
- 모델이 두 곳에 갈림(2026-06-04 정정): `PROJECT_ROOT/models`(6/2, zone_drip 19피처 복원본) ↔
  `services/inference/models`(4/22, zone_drip 6피처 퇴화 구버전). lead-time 평가(leadtime_eval→
  src/evaluate)는 **6/2 복원본**을 썼고(정정: 앞서 "구모델"이라 한 것은 오류), sensor_fault_eval·
  startup_strategy_eval만 4/22 구버전을 읽었다. 서빙도 4/22를 사용 중. **재학습 + 서빙 동기화 필요**.
  체크리스트: [docs/modeling/11_retrain_checklist.md].

### 추가 작업 — 기동 regime band 구현(2026-06-04)
- 실험: `fault_injection/startup_strategy_eval.py` — 통째게이트(현재) vs regime band 비교.
  통째게이트는 비정상 기동 recall 0(사각지대), regime band는 FAR 3.3%로 1.1×부터 100% 검출. → regime 채택.
- 발견: 기존 `is_startup_spike`(preprocessing §6)는 위치로만 분류(크기 무시)·표시용이라 "90→130"을 못 잡음.
- 구현: train.py가 `threshold_startup`(기동 점수 백분위) 산출·저장. inference_api·evaluate가 `STARTUP_MODE`
  (gate|regime, 기본 regime)로 분기, band 없으면 gate 폴백. 구모델 회귀 없음(lead-time 29.9h 동일).
  실제 regime은 재학습으로 band 생성 후 활성. 문서 03 §4-2.

### 재개 지점 (Resume Point)
1. **재학습** — 현재 src/ 피처로 4도메인 재학습. 이때 기동 band 생성 → regime 실활성. lead-time·집중도 갱신(리소스 작업 → 사용자 실행).
2. 재학습 후 regime 실검증(startup_strategy_eval를 실데이터 band로 재실행) + 집중도 시각화.
3. (c) 포트폴리오 정직화 — 재학습 후 확정 수치로 "F1 0.95" 교체.
4. 포트 불일치(README §5 vs compose) — 사용자 확인 대기.

---

## 2026-06-02 — 평가 경로 기동 게이트 + lead-time 정직화

### 달성 (Accomplished)
1. 검증으로 결함 포착: `leadtime_eval.py`에 특이도(FAR) 리포트 추가 → 평가 경로에 기동 게이트가 없어 기동 윈도우 FAR 100%였음을 발견. 운영(inference_api)만 게이트하고 평가는 안 함.
2. `evaluate_test_metrics.run_inference`에 운영과 동일한 기동 게이트 추가(is_startup_phase>=0.5 → 모든 *_level=0). src/ + services/ 동기화.
3. 재검증: 기동 FAR 100%→0%. **기동 오탐 제거 후에도 막힘 6/6 100% 검출, 평균 lead-time 36.1h→29.9h** (부풀려졌던 6h가 기동 오탐분). 검출이 진짜 막힘 신호임 증명. 커밋 5fc93c7.

### 재개 지점 (Resume Point)
1. (b) 센서고장 대조군(단일센서 drift/spike/stuck) — 강사 원칙 검증(진짜고장 잡고 센서글리치 안 잡음).
2. (a) 타 도메인 고장모드(motor 베어링·nutrient·zone_drip) 시그니처 추가.
3. (c) 포트폴리오 정직화 — "F1 0.95"→검증된 lead-time 수치로 교체.
4. 노트북(ipynb) 버전정리 — 폴더 구조 결정(2026-06-02 진행 중).

---

## 2026-06-01 — 재현성 진범 규명·수정 (PYTHONHASHSEED re-exec)

### 달성 (Accomplished)
1. 재현성 2회차 테스트 실패 → 진범 규명: TF 아님, **Python 해시 무작위화(PYTHONHASHSEED 미고정)**. set 순서가 매 실행 달라져 다중공선성 드롭·robust voting이 다른 컬럼 선택 → config 4도메인 전부 다름. 격리검증으로 set 순서 변동 확인.
2. `repro.set_global_determinism` 수정 — 런타임 os.environ 대입은 무효이므로, PYTHONHASHSEED 미설정 시 환경변수 박고 `os.execv`로 프로세스 재실행(re-exec). set 순서 고정 격리검증 완료.
3. 오진 정정 — 01·05 문서, handoff/status, MODEL_CHANGELOG에서 "TF가 진범" 서술을 해시 원인으로 수정. MODEL_CHANGELOG Phase D + 절대규칙 #7 추가.

### 재개 지점 (Resume Point)
1. 재현성 재검증: `train.py` 2회(re-exec 적용본) → config 동일 확인 (handoff.md §4 명령).
2. 통과 시 zone_drip 센서 드롭 추적 → percentile threshold 실험.
3. 미커밋: repro.py(CSV 안전장치+re-exec), 정리된 csv, status/handoff, 문서 정정 → 다음 커밋.

---

## 2026-05-31 — 첫 기준선 학습 실행 + 진단 그림 + handoff/status 신설

### 달성 (Accomplished)

1. `python src/train.py` 첫 실행 성공(run_id `2026-05-31_172229__5de0f9e__baseline-repro`, 4도메인 2분37초). 결정성 고정·run 스냅샷(16파일)·figures·contact sheet·experiments.csv 모두 정상 산출.
2. experiments.csv 스키마 버그 수정 — 옛 6열 파일에 새 8열 행이 어긋나 쌓이던 문제. `repro.append_experiment_row`에 스키마 변경 시 `.legacy.csv` 자동 보존장치 추가, 현재 파일은 `experiment_board.legacy.csv`(145행) + 새 스키마(4행)로 분리.
3. `status.md`·`handoff.md` 신설(루트) — 최초 질문의 "handoff/status" 요청 반영. status=현재상태 대시보드, handoff=인수인계+실행법. 둘 다 SESSION_LOG/docs/modeling을 가리키는 front door.

### 핵심 발견 (Findings)

- 진단 그림이 모델 품질 문제를 즉시 가시화. motor는 건강(skew 14.82, 기동이 threshold 안 부풀림, 꼬리에 drift). zone_drip은 퇴화(기동 spike가 threshold 약 10배 부풀림, MSE가 0.5만 반복·무변동).
- zone_drip 원인 규명 진행: `zone1_*` 센서가 **raw 데이터엔 존재**(zone1_flow/pressure/substrate_* + zone2/3까지)하나 **집계본 df_agg에서 누락** → 실제 구역 센서 0개로 학습. preprocessing의 드롭 지점(collinearity/whitelist) 추적이 다음 과제.

### 재개 지점 (Resume Point)

1. 재현성 2회차: `train.py` 재실행 후 run1 vs run2 config diff (handoff.md §4).
2. 통과 시 zone_drip 센서 드롭 추적 → percentile threshold 실험.
3. 미커밋: `repro.py` CSV 안전장치 + 정리된 csv → 다음 커밋.

---

## 2026-05-31 — 도메인 운영 지표 검증(막힘률·Cpk·OEE) 핸드오프 (docs/modeling/08 신설)

현재 진행 중인 모델 성능 작업(재현성 인프라 → NUTRIENT threshold → 단일센서 baseline)이 끝난 뒤 이어서 수행할 검증 작업을 문서로 고정했다. 강사가 경력기술서에 제시한 제조 지표(막힘률 10→2% · Cpk 1.67 · OEE 78→85%)를 실제 측정해 격상하는 단계다.

### 달성 (Accomplished)

1. `docs/modeling/08_domain_metrics_validation.md` 신설 — 막힘률·Cpk·OEE의 정의·측정 절차·효과 책정 기준을 정리. 효과 크기의 절대값이 아니라 "도메인이 인정하는 지표를 정의하고 그에 맞춘 테스트를 했다"는 점에 집중.
   - 막힘률: 막힘 사건 조작적 정의 + episode 단위 + baseline 대비 동일 시나리오 비교
   - Cpk: CTQ(토출 유량) 선정 → LSL/USL 명시 → within σ(R̄/d₂) → 정규성 → Cpk 산출. F1과 분리 강조
   - OEE: 가용성×성능×품질 구성요소 정의 + 출처 표기
   - RMSE/Confusion Matrix는 모델 지표군으로 분리
2. `docs/modeling/README.md` 색인에 08 추가, `04_modeling_kickoff_checklist.md` 현재 우선순위 표에 6(막힘률)·7(Cpk)·8(OEE) 추가.

### 재개 지점 (Resume Point)

`04_modeling_kickoff_checklist.md` "현재 프로젝트 적용 우선순위" 표 순서대로. 현재 작업(1~5번: 인프라·threshold·baseline)이 끝나면 **6번 막힘률부터** [08_domain_metrics_validation.md](docs/modeling/08_domain_metrics_validation.md) §8 착수 체크리스트를 따라 진행한다. 5번 baseline이 6번의 선행 조건이다.

### 절대 규칙 (Absolutes)

- 막힘률은 baseline 대비 비교가 핵심 — baseline 없이 단독 측정하면 "10→2%"가 목표에 머문다.
- F1(분류)과 Cpk(공정 산포)는 별개 지표 — 한 결과로 묶지 않는다.
- 측정이 검증값으로 확정되면 08 §7 동기화 5종(로드맵 §0 표·portfolio_interview_facts·CEDR 원칙·경력기술서/SSOT·MODEL_CHANGELOG)을 함께 갱신한다.

---

## 2026-05-31 — 모델링 기획 문서(docs/modeling/) + 재현성·추적 인프라(repro.py) 신설

참고: 이 항목부터 신규 규칙(이모지 금지·격식 문어체, 메모리 feedback_no_emoji_formal_docs)을 적용한다. 이전 항목들의 이모지 섹션 마커는 레거시로 보존한다.

### 달성 (Accomplished)

1. `docs/modeling/` 폴더 신설 — 모델 성능 검증·모델링 기획을 어떻게 체계적으로 수행할지 방법론으로 정리. 기존 `docs/MODELING.md`(as-built 구조)와 역할 분리(이 폴더 = 앞으로의 프로세스).
   - `README.md` 색인+철학(반복 실험을 복원·비교 가능하게)
   - `01_experiment_protocol.md` 재현성·덮어쓰지 않는 저장·experiments.csv·한 번에 한 변수
   - `02_evaluation_design.md` 시간순 split·정상 순도·메트릭(FAR≤5%)·baseline-first·에러분석
   - `03_threshold_methodology.md` dynamic threshold: σ 고정 → PR curve/percentile, 도메인별 보정
   - `04_modeling_kickoff_checklist.md` 착수 전 게이트 0~4 + 현재 우선순위
   - `05_reproducibility_implementation.md` repro.py 구현·신규 개념 설명
   - `06_visualization_logging.md` 진단 시각화 자동 저장·실험별 이미지 관리(구현 반영)
2. `src/repro.py` 신설(코드) — `set_global_determinism`(TF 포함 전역 시드+op_determinism), `get_git_sha`, `new_run_id`, `snapshot_run`(models/runs/<run_id> 보존본+LATEST_RUN.txt), `append_experiment_row`. 상세 주석 포함.
3. `src/viz.py` 신설(코드) — `plot_threshold_diagnosis`(히스토그램 skew + 시계열 임계치 + 기동/이상 음영 + '기동 제외 시 임계치' 점선 병기), `plot_loss_curve`, `build_contact_sheet`. matplotlib Agg, import 실패 흡수.
4. `src/train.py` 연동 — 메인 시작 시 결정성 고정·run_id 생성, 도메인 학습에 run_id/git_sha/figures_dir 전달, experiments CSV에 run_id·git_sha 컬럼, 도메인별 진단 그래프를 `models/runs/<run_id>/figures/`에 저장, 4도메인 후 contact sheet + snapshot_run 1회. (services/inference/src/ 동일 동기화, 구문 검증 통과, matplotlib 3.7.5 확인)
5. `src/evaluate_test_metrics.py` 시각화 연동 — `run_inference`가 도메인별 임계치 맵 반환, 도메인별 MSE 타임라인(이상 라벨 음영 + 학습/평가 경계선)을 `latest_run_dir`로 찾은 같은 run의 figures/에 `<도메인>__eval_timeline.png`로 저장 + contact sheet. 평가에선 `show_excl_startup=False`. `repro.latest_run_dir` 헬퍼 추가. (런타임 렌더 검증: 합성 데이터로 그림 생성 확인)
6. `docs/MODELING.md` 상단 교차 링크 추가.

### 향후 (다음 모델링 세션)

- 재현성 검증: `python src/train.py` 2회 실행 → 두 `*_config.json`의 thresholds·features 동일 확인. 다르면 비결정 연산 격리.
- 실제 학습/평가 1회 실행으로 figures/ 산출 확인(데이터 월1 정상→월2 drift→월3 이상 구조에서 경계선 이후 MSE가 critical 돌파하는지). 무거운 작업이라 사용자 직접 실행.
- 그 다음 NUTRIENT threshold(percentile/PR) 실험·baseline 구축.

### 절대 규칙 (Absolutes)

- 재현성 확보 전의 "성능 개선"은 보고하지 않는다(우연과 구분 불가). A-3 비결정성 교훈.
- 모델 아티팩트는 덮어쓰지 않는다 — 라이브(models/)는 서빙용 유지 + runs/<run_id> 보존본 추가. inference_api 서빙 계약 불변.
- `docs/modeling/`(방법론)과 `docs/MODELING.md`(구조)는 분리 유지.
- 비결정성 직접 원인은 TF(무시드)였음. feature_selection RF/KMeans는 이미 random_state로 재현 가능.

### 재개 지점 (Resume Point)

`docs/modeling/04_modeling_kickoff_checklist.md` "현재 프로젝트 적용 우선순위" 표 순서대로. 무거운 학습(train.py)·대량 렌더는 사용자 직접 실행. 다음 후보: 06 시각화 viz.py 구현 여부 결정.

---

## 2026-05-28 — 포트폴리오 강점 강화 디벨롭 로드맵 신설 (docs/DEVELOPMENT_ROADMAP.md)

### ✅ 달성 (Accomplished)

1. **MDOF·NN 보정·Cpk·OEE/막힘률 4개 항목의 출처·현재 상태 검증 완료**:
   - 출처: 전부 `jun_portfolio/03_A트랙_데이터기술_notion.md`·`05_노션_경력기술서_페이지.md`의 **팀 기획·목표 단계** 기술. 외부 레퍼런스(커리큘럼 명세 인용·산업 벤치마크·논문) 0건
   - 현재 상태: **네 항목 모두 최종 코드에 미구현/미측정** (MDOF·NN은 시도 기록도 0건, Cpk·OEE는 측정 로직 0줄)
   - 최종 모델 = 4도메인 독립 AutoEncoder + 6σ 3단계 알람 + SHAP RCA (물리모델 없음)

2. **`docs/DEVELOPMENT_ROADMAP.md` 신설** — 강사님 제시 키워드를 "제거"가 아니라 **"실제 구현·측정해 포트폴리오 강점으로 격상"**하기 위한 향후 디벨롭 계획. 항목별 [무엇인가·왜 강점·구현할 것·완료 시 발화 격상] + 권장 작업 순서(§4 막힘률/OEE → §3 Cpk → §1 MDOF → §2 NN) + 동기화 체크리스트.

### ⏳ 향후 (다음 디벨롭 세션)

- 1순위 §4 막힘률·OEE baseline 비교 시뮬레이션부터. 상세는 `docs/DEVELOPMENT_ROADMAP.md` §5 참조.
- 구현 완료 항목은 ROADMAP §0 상태 표(❌→✅) + `docs/portfolio_interview_facts.md` + make_portfolio CEDR 카탈로그 동기화.

### 🔒 절대 규칙 (Absolutes)

- 구현·측정 전까지 MDOF·NN·Cpk·OEE·막힘률 %는 **포트폴리오 본문 노출 금지** (현 상태 = 목표/기획값). P-002 원칙 유지.
- 디벨롭 시 출처(기계공학 수식 레퍼런스, OEE 78/85 근거)를 **반드시 표기** — 현재 출처 0건이 가장 큰 약점.

---

## 2026-05-27 — 포트폴리오 발화 정확도 점검 (docs/portfolio_interview_facts.md 신설)

### ✅ 달성 (Accomplished)

1. **`docs/portfolio_interview_facts.md` 신설** — 1분 자기소개·면접 발화에 들어가는 펌프 프로젝트 사실 매핑 SSOT. 발화 표현 ↔ 코드/문서 위치 매핑, 검증된 결과(F1 0.95) vs 환산값(연 4000만원) vs **제외된 수치(막힘률 10%→2%)** 명확히 구분.

2. **"막힘률 10% → 2%" 표현을 발화에서 제거 결정** — 코드·문서 검증 결과 측정 근거 부재 확인:
   - `evaluate_test_metrics.py`는 `anomaly_label`(0/1)만 측정. "막힘률" 측정 로직 부재
   - "10%"·"2%"는 `jun_portfolio/03_A트랙_데이터기술_notion.md:16`에 "목표"로만 기술
   - F1 0.95 → 막힘률 환산 공식 없음
   - → 정직성 위해 본문/두괄식에서 모두 삭제

3. **1분 자기소개 옵션 B 확정** — 검증된 사실(F1 0.95)만 본문 결과로 노출 + 비즈니스 임팩트는 "환산" 단어로 추정값임을 명시:
   - 두괄식: "양액 펌프 막힘을 95% 정확도로 사전에 감지하는 모델을 만든"
   - 본문 마지막 문장: "네 모델 모두 정상·이상 구분에서 F1 0.95를 넘겼고, 1000평 농장 기준 연 4000만원 손실 예방 효과로 환산했습니다"

### ⏳ 향후 코드/문서 수정 시 점검 필요

다음 항목 변경 시 `docs/portfolio_interview_facts.md` §4 체크리스트 + 원본 발화(`~/GitStudy/make_portfolio/분석가_포트폴리오_범용/1분_자기소개.md`)도 같이 갱신:

1. **F1 0.95 수치 변동** — nutrient 도메인 오탐 근본 수정 시 발화 검토
2. **4도메인 구성 변경** (motor/hydraulic/nutrient/zone_drip)
3. **AutoEncoder → 다른 모델 전환**
4. **6시그마 3단계 알람 사양 변경** (현재 2σ/3σ/6σ → 1σ/2σ/3σ + 디바운싱 예정)
5. **연 4000만원 환산 가정 변경** (1000평·작물·고품질 비율)
6. **농장 실측 배포 시작** — "환산" → "달성"으로 표현 격상 가능
7. **막힘률 % 표현 부활 금지** — 실측 로직이 코드에 들어오기 전까지 발화 재진입 불가

### 🔒 절대 규칙 (Absolutes)

- 포트폴리오 발화는 **검증된 사실만 본문에 노출**. 환산값은 "환산" 단어로 신호.
- "막힘률 10%→2%" 같은 목표 수치는 본문에서 사용 금지. 면접 후속 질문에서 "사업 목표였습니다"로 풀이 가능.
- 원본 발화 갱신은 `~/GitStudy/make_portfolio/분석가_포트폴리오_범용/1분_자기소개.md` 단일 SSOT. 본 docs는 매핑 참조용.

---

## 2026-04-21 — 프론트 연동 스펙 정리 (FRONTEND_PAGES.md 신설 · 필터 페이지 결정 · raw_inputs 확장)

### ✅ 달성 (Accomplished)

1. **필터 페이지 처리 방침 결정** (dabin.csv 43,200행 상관분석 근거):
   - `filter_pressure_in` vs `discharge_pressure`: r=**0.757** (비슷하지만 중복은 아님)
   - `filter_pressure_in` vs `filter_pressure_out`: r=**0.994** → out 측은 이미 [preprocessing.py:621](src/preprocessing.py#L621)에서 drop됨
   - **`filter_delta_p` vs `pump_delta_p`: r=0.374** → **독립 정보** (펌프 상태 ≠ 필터 오염도)
   - 하지만 dabin.csv엔 필터 막힘 시나리오 거의 없음 (`filter_delta_p` CV=3.1%, `hidden_risk_stage=watch`에서도 +0.26 kPa만)
   - **결정**: 필터 페이지는 **AE 모델 없이 룰 기반**으로 운영 (경고 Δp>15 kPa, 위험 Δp>25 kPa)

2. **`docs/FRONTEND_PAGES.md` 신설**: 프론트 작업자 질의(설비별 페이지 구성·AI 분석 페이지 내용·비교분석 7지표·CTP 시각화·타임라인 간격·데이터 정보)에 코드 기반 답변. 4개 AE 도메인(motor/hydraulic/nutrient/zone_drip) + 필터 룰 페이지.

3. **`docs/INFERENCE_API.md` 업데이트**:
   - §4-3 `raw_inputs`에 `filter_pressure_in_kpa`, `filter_pressure_out_kpa` 추가 문서화
   - §7-1 한글 라벨 정정 (`flow_per_power` = 유량 대비 전력 효율, `pressure_per_power` = 압력 대비 전력 효율 — 사용자 네이밍 규칙 준수)
   - §7-1 `pressure_flow_ratio_discharge` → `pressure_flow_ratio`로 단순화 (해석용 공식 = 토출/유량 으로 프론트 통일)
   - §7-4 신설: 필터 페이지 룰 기반 가이드 (`filter_delta_p_kpa` 계산법·임계)
   - §8-2 업데이트: `pressure_flow_ratio` 인코딩 활용 여부 검토 중임을 명시
   - §3-3, §10 용어집에 필터 관련 키 추가

4. **`inference_api.py` raw_inputs passthrough 확장** (src/ + services/inference/src/ 두 파일 모두):
   - `raw_input_keys`에 `filter_pressure_in_kpa`, `filter_pressure_out_kpa` 2개 추가
   - 요청 body에 존재하는 키만 담는 기존 안전장치 유지
   - AE 모델 config는 건드리지 않음 (filter는 모델 입력 아님, 프론트 파생용)

### ⏳ 남은 과제 (Pending)

1. **프론트 작업자에게 `docs/FRONTEND_PAGES.md` + `docs/INFERENCE_API.md` 전달** → 설비 페이지 4개(motor/hydraulic/nutrient/zone_drip) + 필터 룰 페이지 + AI 분석 페이지 UI 구현
2. **`client_simulator.py` 점검**: filter 2개 키가 POST body에 포함되는지 확인 (없으면 `raw_inputs`에서 누락됨)
3. **`pressure_flow_ratio` 인코딩 결정**: 모델 입력으로 쓸지/해석용만 둘지 결정 필요. 쓸 경우 [preprocessing.py:225-227](src/preprocessing.py#L225-L227)·[preprocessing.py:455-457](src/preprocessing.py#L455-L457) 두 공식 중 하나로 통일
4. **`pressure_volatility` / `flow_cv` 12h 파생**: 프론트 링버퍼 720점으로 자체 계산하도록 합의(백엔드엔 없음)
5. **재학습 대기 건 (이전 세션)**: `python src/train.py` 사용자 실행 필요

### 🔒 절대 규칙 (Absolutes)

- 필터는 **AE에 넣지 않는다** (학습 데이터에 막힘 시나리오 부재). `collinear_drop_list`의 `filter_pressure_out_kpa` 제외 유지
- `raw_inputs`는 **passthrough 채널**. 추가해도 모델 config/학습과 무관해야 함
- `pressure_flow_ratio` 공식은 당분간 프론트=해석용(`discharge/flow`), 모델=공식 미정. 재학습 전엔 둘 다 유지
- `flow_per_power` = 유량/전력, `pressure_per_power` = 압력/전력. 수식-라벨 일치 유지

### 🔄 재개 지점 (Resume Point)

1. `curl -X POST http://127.0.0.1:9977/predict ... ` 응답의 `raw_inputs`에 `filter_pressure_in_kpa` 키가 있는지 확인 (요청에 포함해서 보냈을 때)
2. 프론트팀과 `docs/FRONTEND_PAGES.md` §5 체크리스트 확인
3. `pressure_flow_ratio` 인코딩 방향 결정 필요 — 결정되면 preprocessing.py에서 두 공식 통일

---

## 2026-04-21 — inference_api에 데이터 저장 로직 이식 (inference_api2.py → inference_api.py)

### ✅ 달성 (Accomplished)

1. **`~/Downloads/inference_api2.py`의 저장 로직을 `src/inference_api.py`로 그대로 이식** (총 571 lines)
   - 추가된 import: `sqlalchemy`, `boto3`, `BytesIO`, `dotenv`, `apscheduler.BackgroundScheduler`, `preprocessing.step1_prepare_window_data`
   - `.env.local` 로딩 블록 (ENV=local 일 때 `../../../.env.local` 로드)
   - DB 설정: `DB_URL`, `DEFAULT_SENSOR_ID`(=`SF-ZONE-01-MAIN`), `engine`, `DB_STATUS`
   - S3/MinIO 설정: `S3_ENDPOINT`, `BATCH_STATUS`
   - 신규 함수: `_mask_db_url`, `_set_db_status`, `initialize_db_engine`, `save_inference_history`, `_update_batch_status`, `_build_batch_payload_from_dataframe`, `run_inference_batch`
   - `/predict` 본체를 `run_inference_pipeline(realtime_data, trigger_source)`로 리팩터 → `/predict`와 배치가 동일 파이프라인 공유
   - `@app.on_event("startup")` → APScheduler 1분 주기 배치 + DB 엔진 초기화
   - `/health` 엔드포인트 신설 (DB/배치 상태 반환)
   - 포트는 **9977 유지** (inference_api2.py의 8000 채택 안 함)

2. **기존 로직은 전부 보존**:
   - `scoring_features` 기반 MSE 계산
   - `is_startup_phase` 게이팅
   - `per_feature_thresholds` passthrough
   - `feature_details`의 `scaled_error` / `feature_thresholds` / `feature_alarm`
   - `target_reference_profiles`, `spike_info`, `raw_inputs` 블록
   - 응답 구조 변경 없음 (프론트 계약 유지)

3. **미채택 (의도적 제외)**: `get_alarm_status_with_consecutive_delay`, `MSE_HISTORY deque`, `hourly_thresholds`, `threshold_hard_ceiling`, `rca_report` flat format — 응답 구조/알람 동작을 바꾸므로 요청 범위 밖

### ⏳ 남은 과제 (Pending)

1. **의존성 설치 확인**: analyzer conda env에 `sqlalchemy`, `boto3`, `python-dotenv`, `apscheduler` 설치 필요
2. **DB 테이블 존재 확인**: PostgreSQL에 `inference_history` 테이블이 있어야 저장 성공 (없으면 `save_inference_history`는 로그만 남기고 skip)
3. **`.env.local` 파일 배치**: `/Users/jun/GitStudy/.env.local` 위치에 DB/S3 자격 필요 (DB_URL, S3_ENDPOINT, MinIO 키)
4. **서버 재기동 필요**: 기존 uvicorn 프로세스 종료 후 `python -m uvicorn inference_api:app --reload` 재실행
5. **배치 스케줄러 실 동작 검증**: MinIO 버킷에 창(window) 파일이 쌓이면 1분마다 `run_inference_batch`가 폴링해서 `run_inference_pipeline` 호출하는지 관찰

### 🔒 절대 규칙 (Absolutes)

- `run_inference_pipeline`은 `/predict`와 배치가 공유하는 단일 진입점 — 응답 페이로드 변경 시 두 호출자 모두에 동일하게 반영돼야 함
- `save_inference_history` 실패는 추론 결과 반환을 막지 않는다 (try/except로 격리) — 저장 이슈가 사용자 요청에 영향 주면 안 됨
- 포트/환경 변수는 프로젝트 기존 설정 우선 (9977, `.env.local` 경로 등)

### 🔄 재개 지점 (Resume Point)

1. 서버 재기동 후 `curl http://127.0.0.1:9977/health` → `{"db": {...}, "batch": {...}}` 반환 확인
2. `curl -X POST http://127.0.0.1:9977/predict -H "Content-Type: application/json" -d @<sample>.json` 응답 구조 불변 확인 (raw_inputs, domain_reports 등)
3. PostgreSQL `inference_history` 테이블에 해당 요청 row 저장됐는지 확인

---

## 2026-04-21 — inference_api `/predict` 응답에 `raw_inputs` 추가

### ✅ 달성 (Accomplished)

1. **inference_api.py** `response_payload`에 `raw_inputs` 블록 신설 ([src/inference_api.py:190](src/inference_api.py#L190) 근처)
   - 요청 body에서 6개 키를 passthrough: `discharge_pressure_kpa`, `suction_pressure_kpa`, `flow_rate_l_min`, `motor_power_kw`, `motor_temperature_c`, `pump_rpm`
   - 요청에 **존재하는 키만** 담음 (없는 값을 0.0으로 위장하지 않음 → 프론트가 "센서 미보고"와 "실제 0"을 구분 가능)
   - 목적: 프론트에서 `pressure_flow_ratio`, `dp_per_flow`, `flow_per_power`, `pressure_volatility` 등 파생변수를 만들 수 있게 원시값 노출

### ⏳ 남은 과제 (Pending)

1. **문서 통합 완료** (2026-04-21): `docs/INFERENCE_API_RESPONSE.md` 삭제, [docs/INFERENCE_API.md](docs/INFERENCE_API.md) 하나로 §0–§12 구조 재정리. §4-3 `raw_inputs`, §7 프론트 파생변수 가이드, §8 preprocessing.py 중복 맵, §9 파생변수 위치 구조 신설.
2. **프론트 작업**: `raw_inputs.discharge_pressure_kpa`를 링버퍼에 쌓아 `pressure_volatility`(std/IQR), `flow_volatility`(CV), `temp_slope` 계산 로직 구현. §7-2/§7-3 설계 참고.
3. **⚠️ preprocessing.py 이름 충돌 정리**: `pressure_flow_ratio`가 line 225(모델용, `differential/flow`)와 line 455(해석용, `discharge/flow`) 두 곳에서 **다른 공식으로 같은 이름** 사용 중. 이름 분리 또는 공식 통일 결정 필요.
4. **(선택) 응답에 `computed_ratios` 블록 추가**: preprocessing의 해석용 4개 비율(`pressure_flow_ratio`, `dp_per_flow`, `flow_per_power`, `pressure_per_power`)을 서버가 단일시점 계산해서 응답에 포함 — 프론트 로직 단순화. 사용자 승인 대기.
5. **재학습 대기 건 (이전 세션)**: per-feature threshold 반영 모델 재학습 — `python src/train.py` 사용자 실행 필요

### 🔒 절대 규칙 (Absolutes)

- `raw_inputs`는 **모델 입력이 아닌 passthrough 채널**. 여기에 값을 추가해도 모델 config/학습 파이프라인과 무관해야 한다.
- 키 추가 시 반드시 `if k in realtime_data` 필터 유지 — 요청에 없던 키를 0.0으로 채워넣으면 프론트가 잘못된 파생값을 계산하게 된다.
- 프론트 파생변수는 분모에 ε(1e-6) 추가해 0-division 방지.

### 🔄 재개 지점 (Resume Point)

재시작 시 `curl http://127.0.0.1:8000/predict ...` 응답 최상위에 `raw_inputs` 키가 존재하는지 확인. 예시:

```json
{
  "timestamp": "...",
  "overall_alarm_level": 0,
  "raw_inputs": {
    "discharge_pressure_kpa": 310.5,
    "flow_rate_l_min": 18.5,
    ...
  },
  "domain_reports": {...}
}
```

---

## 이전 세션 — Per-Feature Threshold Implementation

### ✅ 달성

1. **train.py**: per-feature threshold 계산 로직 추가 (열별 σ 컷, config에 `per_feature_thresholds` 저장)
2. **inference_core.py**: `build_feature_details`에 `scaled_errors`/`per_feature_thresholds` 인자 추가 → `scaled_error`/`feature_thresholds`/`feature_alarm` 출력
3. **inference_api.py**: 도메인 보고서에 `per_feature_thresholds` passthrough 및 `build_feature_details` 호출에 인자 전달

### ⏳ 남은 과제

- **재학습 필수**: `python src/train.py` — 기존 모델에는 `per_feature_thresholds` 필드가 없음 (graceful fallback 중)

### 🔒 절대 규칙

- `per_feature_thresholds` 계산은 도메인 MSE와 동일 σ 정책(2/3/6σ)
- 컨텍스트 피처(`is_startup_phase`, `pump_on` 등)는 threshold 대상 제외 (scoring_mask 준수)
- inference_core와 train.py의 feature 제외 기준 일치 유지

### 🔄 재개 지점

재학습 후 `domain_reports[system].feature_details[i]`에 `scaled_error`/`feature_thresholds`/`feature_alarm` 세 필드와 `domain_reports[system].per_feature_thresholds` 전체 매핑 확인.
