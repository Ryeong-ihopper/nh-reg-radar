# Document Governance

이 디렉터리는 프로젝트 문서 작성·변경·검증 규칙의 설정과 템플릿을 관리한다. 실제 개발 명세의 Source of Truth는 `docs/`이며, 이 디렉터리는 그 정합성을 검사하는 정책 계층이다.

## 구성

| 경로 | 역할 |
| --- | --- |
| `document-policy.json` | 필수 문서, 메타데이터, ADR, 추적성, 변경 영향 규칙 |
| `pyrightconfig.json` | 문서 거버넌스 Python 모듈의 타입 검사 범위와 최소 호환 버전 |
| `templates/standard-document.md` | 신규 일반 문서의 최소 형식 |
| `templates/adr.md` | 신규 ADR의 최소 형식 |
| `scripts/doc_guard.py` | 설정을 실행하는 검증 CLI |
| `scripts/manage-skill-adapters.sh` | `skills/` 원본을 프로젝트 로컬 Codex/Claude 탐색 경로에 설치하고 drift를 검증 |

## 명령

```bash
python3 -m scripts.doc_guard validate --scope all
python3 -m scripts.doc_guard validate --scope working
python3 -m scripts.doc_guard validate --scope staged
python3 -m scripts.doc_guard impact --scope working
scripts/manage-skill-adapters.sh validate
uvx ruff check scripts/doc_guard.py scripts/doc_governance tests/governance
uvx basedpyright --project governance/pyrightconfig.json
```

`error`는 hook과 CI를 실패시킨다. `warning`은 변경자가 영향 없음의 근거를 검토하도록 알리되 자동 차단하지 않는다.

고객사 원본 자료, `temp/`, 로컬 agent runtime 경로는 변경 파일명 자체가 외부 로그나 CI 출력에 노출되지 않도록 영향 분석 입력에서 제외한다. 해당 자료의 보안·반출 정책은 문서 거버넌스가 아니라 관련 Accepted ADR을 따른다.

## 강제 계층

| 계층 | 구성 | 역할 |
| --- | --- | --- |
| 작업 지침·예방 | `AGENTS.md`, `CLAUDE.md`, `skills/*/SKILL.md` | 작업 전 source of truth와 변경 영향 확인 |
| 로컬 차단 | `.githooks/pre-commit`, `.githooks/pre-push` | commit과 push 전 공통 검사 실행 |
| 중앙 강제 | `.github/workflows/document-governance.yml`, 브랜치 보호 | 로컬 hook 우회 여부와 관계없이 병합 전 필수 검사 실행 |

PoC에서는 Claude/Codex의 도구별 lifecycle hook을 필수 설치하지 않는다. 개인 보조 hook을 사용하더라도 Git으로 관리되는 공통 검사 명령을 호출해야 하며, 공식 통과 기준은 Git hook과 CI 결과다. 상세 기준은 [ADR-0076](../docs/adr/ADR-0076-ai-tool-lifecycle-hook-enforcement-policy.md)을 따른다.

## 변경 원칙

- 프로젝트별 문서 경로와 동기화 규칙은 `document-policy.json` 한 곳에서 관리한다.
- 범용 킷의 문서 템플릿을 기존 명세 위에 복사하지 않는다.
- 새 문서는 영문 kebab-case 파일명과 `standard-document.md` 형식을 사용한다.
- ADR 후보는 `docs/adr-candidates.md`, 사용자 선택지는 `docs/adr/decision-questions.md`, 확정 결정은 개별 ADR과 `docs/adr/README.md`에 기록한다.
