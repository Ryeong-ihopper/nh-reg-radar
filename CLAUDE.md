# Claude Code Project Instructions

이 저장소에서 작업할 때는 루트 `AGENTS.md`와 `docs/project-rules.md`를 먼저 읽고 따른다.

- 문서 또는 구현 변경에는 `project-doc-governance` Skill을 사용한다.
- 요구사항, 기능, 화면, API, DB, AI/RAG, 배포 동작 변경 전에는 `spec-change-impact` Skill을 사용한다.
- 아키텍처·보안·운영 의사결정에는 `adr-management` Skill을 사용한다.
- 완료 전 `scripts/check-doc-consistency.sh`와 `python3 -m scripts.doc_guard validate --scope working`을 실행한다.
- 검사를 우회하거나 결정 전 Accepted ADR을 임의로 변경하지 않는다.
