# Git 협업 전략

이 문서는 막힘주의보 팀이 `leon4study/human_A` 저장소에서 따르는 브랜치·커밋·PR 규칙을 정리한다.
실제 저장소의 브랜치 구성과 커밋 이력을 반영한다.

## 전략 요약

- 통합 기준 브랜치는 `main` 하나다. 배포·시연은 `main` 기준.
- 작업은 항상 별도 브랜치에서 하고 PR로 `main`에 합친다. `main` 직접 푸시는 지양한다.
- 커밋 메시지는 Conventional Commits 형식(`feat:`, `fix:`, `docs:`, `chore:` 등)을 쓴다.
  이미 이 형식으로 누적되어 있으므로 일관성을 유지한다.

## 브랜치 네이밍

현재 저장소에는 두 종류의 브랜치가 섞여 있다.

| 유형 | 예시 | 용도 |
|---|---|---|
| 인물 브랜치 | `Jun`, `KDB`, `Cheonui` | 개인 작업 공간(분석·모델 실험) |
| 기능/통합 브랜치 | `UI_develop`, `front-back`, `integrate-branch`, `new_front` | 화면·통합 작업 |

앞으로 새 작업은 **목적이 드러나는 기능 브랜치**를 권장한다.

```
feat/lead-time-eval
fix/startup-gate
docs/onboarding
```

인물 브랜치는 개인 실험에는 편하지만, 무엇을 하는 브랜치인지 외부에서 알기 어렵다.
공유·리뷰가 필요한 작업은 기능 브랜치로 분리한다.

## 브랜치 단위 정하는 법

판단 기준 한 줄: **하나의 PR로 리뷰하고 한 번에 머지해도 되는 단위인가.**

분리해야 하는 신호
- 서로 다른 관심사(모델 학습 변경 + 프론트 화면 변경)가 섞인다.
- 한쪽은 끝났는데 다른 쪽이 며칠 더 걸린다.
- 리뷰어가 달라야 한다(분석 vs 인프라).

한 브랜치에 묶어도 되는 신호
- 같은 기능을 위해 코드·문서·설정이 함께 움직인다(예: 기동 게이트 코드 + SESSION_LOG 갱신).
- 따로 머지하면 깨지는 의존 관계다.

## 커밋 컨벤션 (Conventional Commits)

```
<type>: <요약>

<본문 — 무엇을 왜 바꿨는지>
```

| type | 사용처 |
|---|---|
| `feat` | 기능 추가 (예: 현실적 고장 주입 프레임) |
| `fix` | 버그 수정 (예: 평가 경로 기동 게이트) |
| `docs` | 문서 (예: 온보딩 가이드) |
| `chore` | 잡무·구조 변경 (예: 노트북 폴더 재구성) |
| `refactor` | 동작 변화 없는 구조 개선 |
| `test` | 테스트 추가·수정 |

요약은 한국어로 간결하게, 본문에 배경·근거를 적는다. 모델 실험은 별도로
[.claude/MODEL_CHANGELOG.md](../.claude/MODEL_CHANGELOG.md)에 가설→시도→결과를 누적한다.

## 작업 플로우

```bash
# 1. main에서 브랜치 시작
git switch main && git pull
git switch -c feat/<작업명>

# 2. 작업 + 커밋 (여러 번 가능)
git add -p && git commit

# 3. main이 변경됐으면 따라잡기
git fetch origin && git rebase origin/main   # 또는 merge

# 4. 푸시 후 PR 오픈
git push -u origin feat/<작업명>
```

PR 본문은 [.github/PULL_REQUEST_TEMPLATE.md](../.github/PULL_REQUEST_TEMPLATE.md) 양식을 따른다.

## 머지 후 정리

- 머지된 기능 브랜치는 삭제한다. 현재 원격에 통합이 끝난 `UI_*`, `integrate-*`,
  `front-back`, `new_front` 등 오래된 브랜치가 다수 남아 있다. 역할이 끝난 브랜치는
  정리해 추적 대상을 줄인다.

```bash
git branch -d feat/<작업명>            # 로컬
git push origin --delete feat/<작업명>  # 원격
```

## 금지사항

- `main` 강제 푸시(`--force`) 금지.
- 비밀값(`.env`, `.env.prod`, 키 파일) 커밋 금지. 공유는 `.env.example` 템플릿으로만.
- 대용량 산출물(모델 `.keras`, 데이터 CSV) 커밋 지양. 용량 정책은
  [docker-cleanup.md](docker-cleanup.md) 및 `.gitignore` 참조.
