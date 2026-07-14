# ADR-0034: Claude/Codex Skills 표준화 및 온보딩 설치

## 상태

Superseded

프로젝트 Skills의 사용자 홈 설치 방식은 [ADR-0075: 프로젝트 범위 Skills 배포 및 온보딩 설치 정책](ADR-0075-project-scoped-skills-distribution.md)으로 대체되었다. Skills 표준화, Git 원본 관리, Git hook 설치와 개발자 최종 책임 원칙은 ADR-0075에서 계속 유지한다.

## 배경

프로젝트는 AI를 활용해 문서 작성, ADR 정리, 코드 초안 작성, 테스트 초안 작성, 리팩토링 검토를 수행한다. 개인별 프롬프트에만 의존하면 같은 작업도 개발자마다 산출물 품질과 검증 기준이 달라질 수 있다.

이미 ADR-0031에서 AI 산출물은 초안이며 담당 개발자가 최종 책임을 진다고 결정했다. 이제 반복 작업을 어떤 실행 표준으로 운영하고, 신규 개발자가 초기에 동일한 도구 기준을 바로 설치할 수 있게 할지 정해야 한다.

## 결정

반복되는 AI 활용 개발 작업은 **Claude/Codex Skills로 표준화**한다.

프로젝트 Skills와 로컬 Git hook은 저장소의 스크립트로 설치한다.

| 항목 | 결정 |
| --- | --- |
| Skills 원본 위치 | `skills/*/SKILL.md` |
| 설치 방식 | `scripts/setup-dev-tools.sh` 실행 |
| Codex 설치 위치 | `${CODEX_HOME:-$HOME/.codex}/skills/nh-ad-compliance-*` 심볼릭 링크 |
| Claude 설치 위치 | `${CLAUDE_HOME:-$HOME/.claude}/skills/nh-ad-compliance-*` 심볼릭 링크 |
| Hook 설치 | `git config core.hooksPath .githooks` |
| 문서 정합성 검사 | `.githooks/pre-commit`에서 `scripts/check-doc-consistency.sh` 실행 |
| 산출물 책임 | ADR-0031에 따라 담당 개발자가 최종 검증 |

## Skills 적용 범위

초기 Skills는 다음 반복 작업을 대상으로 한다.

| Skill | 목적 |
| --- | --- |
| `adr-management` | ADR 후보 검토, 선택지 정리, 결정 결과 문서화 |
| `docs-consistency` | 문서 변경 시 링크, API 예시, 관련 문서 동기화 항목 점검 |

추가 Skills는 반복성이 있고 검증 기준을 문서화할 수 있는 작업에 한해 도입한다. 일회성 개인 프롬프트나 검증되지 않은 작업 절차는 프로젝트 표준 Skills로 등록하지 않는다.

## 문서 정합성 Hook 기준

문서 변경이 포함된 commit은 pre-commit 단계에서 다음 검사를 수행한다.

| 검사 | 기준 |
| --- | --- |
| Markdown 내부 링크 | `docs/**/*.md`, `README.md`의 상대 Markdown 링크 대상 파일 존재 여부 확인 |
| API JSON 예시 | `docs/api-specification.md`의 `json` 코드블록이 JSON으로 파싱되는지 확인 |
| OpenAPI lint | `openapi/openapi.yaml`과 Spectral 실행 환경이 있으면 lint 수행 |

로컬 hook은 `git commit --no-verify`로 우회할 수 있으므로, CI가 구성되면 [ADR-0064: CI/CD 검증 Gate 및 테스트 실행 분리 정책](ADR-0064-ci-cd-quality-gate-test-split-policy.md)에 따라 같은 `scripts/check-doc-consistency.sh`를 PR 필수 Gate에도 연결한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| Skills 표준화 | 반복 작업 품질과 검증 기준을 맞출 수 있고 온보딩이 쉽다. |
| 개인별 프롬프트 자율 사용 | 빠르지만 산출물 품질 편차가 크고 변경 이력을 추적하기 어렵다. |
| AI 도구 사용 제한 | 통제는 쉽지만 ADR-0031의 AI 적극 활용 방향과 충돌한다. |
| 기준 문서만 두고 Skills 설치는 보류 | 도구 종속성은 낮지만 실행 편차가 남는다. |

## 결정 근거

- ADR-0031은 AI 적극 활용과 개발자 최종 책임을 이미 확정했다.
- Skills는 반복 작업의 입력, 출력, 검증 기준을 표준화하는 데 적합하다.
- Skills 원본을 Git에 두면 리뷰, diff, rollback이 가능하다.
- 온보딩 스크립트로 설치하면 신규 개발자가 같은 작업 기준을 즉시 사용할 수 있다.
- 문서 변경 hook을 함께 설치하면 문서 Source of Truth의 기본 정합성을 commit 전에 확인할 수 있다.

## 영향

- 신규 개발자는 저장소 clone 후 `scripts/setup-dev-tools.sh`를 실행한다.
- AI 도구용 반복 작업 지침은 개인 로컬 프롬프트가 아니라 `skills/`를 우선 기준으로 삼는다.
- 문서 변경 commit은 내부 링크와 JSON 예시 검사를 통과해야 한다.
- Skills 변경도 코드 변경과 동일하게 PR 리뷰 대상이 된다.
- 고객사 자료, secret, 개인정보는 Skills 본문과 예시에 포함하지 않는다.

## 후속 조치

- CI가 구성되면 ADR-0064 기준 `scripts/check-doc-consistency.sh`를 PR 필수 Gate에 연결한다.
- 반복 작업이 늘어나면 `skills/`에 별도 Skill을 추가하되, 적용 범위와 검증 기준을 `SKILL.md`에 명시한다.
- 본사업 전환 시 Claude/Codex 외 도구까지 포함한 사내 표준 프롬프트/Skill Registry 필요성을 재검토한다.

## 관련 문서

- `docs/project-rules.md`
- `docs/adr/ADR-0031-ai-assisted-development-responsibility.md`
- `docs/adr/ADR-0016-prompt-agent-config-versioning.md`
- `docs/adr/ADR-0001-spec-driven-development.md`
- `docs/adr/ADR-0026-api-contract-management.md`
- `docs/adr/ADR-0064-ci-cd-quality-gate-test-split-policy.md`
