# Project Agent Instructions

## Source Of Truth

Git으로 관리되는 `docs/`가 개발 명세의 Source of Truth다. Notion과 회의록에 다른 내용이 있으면 `docs/`와 Accepted ADR을 기준으로 구현한다.

작업 전 다음 순서로 확인한다.

1. `docs/project-rules.md`
2. 변경 영역의 요구사항, 기능, 화면, API, DB, 테스트 명세
3. `docs/adr/README.md`와 관련 Accepted ADR
4. `governance/document-policy.json`

## Required Workflow

1. 변경 영향을 요구사항, 기능, 화면, API, DB, AI/RAG, 인프라, 테스트, 운영으로 분류한다.
2. `python3 -m scripts.doc_guard impact --scope working`으로 동기화 대상 문서를 확인한다.
3. 계약 또는 동작 변경은 관련 명세와 테스트를 같은 작업 단위에서 갱신한다.
4. 새 아키텍처·보안·운영 결정이나 Accepted ADR 변경이 필요하면 `docs/adr-candidates.md`와 `docs/adr/decision-questions.md`에 검토 항목을 먼저 작성하고 사용자 결정을 받는다.
5. 결정 전에는 Accepted ADR을 임의로 변경하지 않는다. 변경 결정은 새 ADR로 기존 ADR을 Superseded 처리한다.
6. 완료 전 다음 명령을 실행한다.

```bash
scripts/check-doc-consistency.sh
python3 -m scripts.doc_guard validate --scope working
python3 -m unittest discover -s tests/governance -v
```

Windows에서는 마지막 검사를 `python scripts/run_governance_tests.py`로 실행한다.
실행 중인 Docker Desktop의 Linux 엔진이 필요하다. 동일한 전체 unittest를 Linux
파일시스템에서 수행하며, POSIX 심볼릭 링크·권한·FIFO 검사를 생략하지 않는다.
Linux/WSL에서는 위 unittest 명령 또는 같은 Python 실행기를 사용한다.

## Documentation Rules

- 활성 Markdown 문서 파일명은 영문 kebab-case를 사용한다.
- 문서 상단의 현행 버전과 기준일은 변경 이력의 최신 행과 일치해야 한다.
- 요구사항 ID, 기능 ID, 화면 ID, 테스트 ID와 ADR 참조를 임의로 바꾸지 않는다.
- 고객사 원문, 개인정보, secret, token, 내부 접속정보를 Skill, 예시, 로그에 포함하지 않는다.
- Git hook이나 CI 검사를 우회하기 위해 거버넌스 설정을 완화하지 않는다.
