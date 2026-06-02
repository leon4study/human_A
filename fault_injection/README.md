# fault_injection — 현실적 고장 주입 & 사전감지 검증

합성 데이터에 **실제 물리 고장의 다중 센서 시그니처**를 주입하고, 모델이 그 고장을 **고장 전에(lead-time)** 잡는지 검증하는 dev/research 서브시스템입니다.

> 서빙 코드(`src/`, `services/inference/src/`)가 아니라 **데이터 현실화·검증 도구**라 별도 폴더로 분리.
> SSOT 스펙: [docs/modeling/10_anomaly_signature_ledger.md](../docs/modeling/10_anomaly_signature_ledger.md). 이 폴더 코드는 그 ledger를 구현한다.

## 왜

현재 평가셋의 이상은 생성기가 만든 합성 이상이라 실제 고장 시그니처와 다를 수 있다(현재 엄격 F1 약 0.50은 "우리가 만든 이상"에 대한 점수). 목표: **근거(논문·벤더·표준) 기반의 현실적 고장을 "열화 ramp → 고장 이벤트" 궤적으로 주입**하고, 모델이 누적 구간을 **일찍** 잡는지(lead-time) 측정한다.

## 핵심 원칙 (ledger §1)

- **real fault** = 공통 고장강도 s(t)(0→1 ramp)가 여러 센서를 **상관되게** 끌어감. 강사 원칙: "여러 값이 함께 요동 = 진짜 고장".
- **sensor fault**(대조군) = 단일 센서만 편차. 모델이 덜 반응해야 함.
- 탐지 목표 = **열화 누적 구간**(고장 전). 성공지표 = **lead-time**(고장 N시간 전 알람).

## 구성

| 파일 | 역할 | 상태 |
|---|---|---|
| `fault_signatures.py` | 고장 모드 → 센서별 방향·크기(ledger 인코딩) | hydraulic 막힘 구현 |
| `inject.py` | s(t) ramp → 상관 델타 주입 + 라벨(`degradation_severity`·`failure_time`·`fault_mode`) | 구현 |
| `build_faulty_testset.py` | 정상 데이터에 다수 고장 주입 → 라벨 test set CSV | 예정 |
| `leadtime_eval.py` | 추론 결과 vs failure_time → lead-time·사전감지율 | 예정 |

## 워크플로

```
정상 데이터(data_gen) → inject.py(고장 주입) → build_faulty_testset(라벨 test set)
   → src/train.py(학습) → 추론 → leadtime_eval(고장 전에 잡았나)
```
