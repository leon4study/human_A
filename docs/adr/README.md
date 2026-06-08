# 아키텍처 결정 기록 (ADR)

이 디렉터리는 프로젝트의 중요한 기술 결정을 한 건당 한 파일로 기록한다.
Michael Nygard의 Architecture Decision Record 형식을 따른다.

## 원칙

- 중요한 결정은 번호가 붙은 파일로 남긴다(`NNNN-제목.md`).
- 이전 결정은 고쳐 쓰지 않는다. 바뀌면 새 ADR이 이전 것을 대체(Supersedes)한다.
- 각 ADR은 Status / Context / Decision / Consequences 를 갖는다.

## 목록

| 번호 | 제목 | 상태 |
|---|---|---|
| [0001](0001-record-architecture-decisions.md) | ADR을 사용해 결정을 기록한다 | Accepted |
| [0002](0002-autoencoder-anomaly-detection.md) | 이상 탐지에 AutoEncoder를 쓴다 | Accepted |
| [0003](0003-four-domain-split.md) | 농장을 4개 도메인으로 나눠 도메인별 AE를 학습한다 | Accepted |
| [0004](0004-six-sigma-threshold.md) | 6시그마 3단계 알람 + skew-adaptive 임계값 | Accepted |
| [0005](0005-ecph-nutrient-separation.md) | EC/pH는 nutrient 도메인으로 분리, 필터는 룰 기반 | Accepted |

새 ADR을 추가할 때는 다음 번호를 쓰고 이 표에 한 줄 추가한다.
