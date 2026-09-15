# ADR 목록

본 디렉터리는 프로젝트의 아키텍처 및 개발 운영 의사결정을 누적 기록한다.

ADR은 다음 원칙으로 관리한다.

- 의사결정이 필요한 후보는 `docs/adr-candidates.md`에 먼저 등록한다.
- 사용자의 판단이 필요한 후보는 [ADR 의사결정 질문지](decision-questions.md)에 선택지와 추천안을 정리한다.
- 결정 전에는 질문지의 답변을 받아 ADR 초안을 작성한다.
- 결정이 확정되면 본 디렉터리에 `ADR-0000-의사결정-제목.md` 형식으로 기록한다.
- 한 번 Accepted 된 ADR은 직접 삭제하거나 덮어쓰지 않는다.
- 결정이 바뀌면 기존 ADR의 상태를 `Superseded`로 변경하고 새 ADR을 추가한다.
- 구현 중 세부 조정은 ADR의 후속 조치 또는 별도 ADR로 남긴다.

## 상태값

| 상태 | 의미 |
| --- | --- |
| Proposed | 후보 또는 검토 중인 결정 |
| Accepted | 현재 프로젝트 기준으로 채택된 결정 |
| Deprecated | 더 이상 권장하지 않는 결정 |
| Superseded | 이후 ADR로 대체된 결정 |

## 결정 목록

| ADR | 상태 | 주제 | 관련 후보 |
| --- | --- | --- | --- |
| [ADR-0001](ADR-0001-spec-driven-development.md) | Accepted | 명세 기반 개발 방식 채택 | ADR 후보 001, 002 |
| [ADR-0002](ADR-0002-customer-sample-data-ai-input-policy.md) | Accepted | 고객사 샘플 데이터 외부 AI 입력 정책 | ADR 후보 035 |
| [ADR-0003](ADR-0003-monorepo-structure.md) | Accepted | PoC 단계 모노레포 구조 채택 | ADR 후보 003 |
| [ADR-0004](ADR-0004-git-notion-wiki-roles.md) | Accepted | Git, Notion, Wiki 역할 분리 | ADR 후보 004, 005 |
| [ADR-0005](ADR-0005-fastapi-backend-framework.md) | Accepted | Python 백엔드 프레임워크로 FastAPI 채택 | ADR 후보 011 |
| [ADR-0006](ADR-0006-postgresql-primary-database.md) | Accepted | 기본 관계형 DB로 PostgreSQL 채택 | ADR 후보 014 |
| [ADR-0007](ADR-0007-docker-compose-build-deploy.md) | Accepted | Docker Compose 기반 빌드 및 배포 방식 | ADR 후보 031 |
| [ADR-0008](ADR-0008-tdd-and-test-scope.md) | Accepted | TDD 및 테스트 적용 범위 | ADR 후보 028, 029, 030 |
| [ADR-0009](ADR-0009-qdrant-vector-database.md) | Accepted | 벡터 DB로 Qdrant 채택 | ADR 후보 018 |
| [ADR-0010](ADR-0010-opensearch-keyword-search.md) | Accepted | 키워드 검색 엔진으로 OpenSearch 채택 | ADR 후보 019 |
| [ADR-0011](ADR-0011-hybrid-search-strategy.md) | Accepted | Hybrid Search 전략 채택 | ADR 후보 020 |
| [ADR-0012](ADR-0012-reference-chunking-policy.md) | Accepted | 기준자료 Chunking 정책 | ADR 후보 021, 022 |
| [ADR-0013](ADR-0013-rule-rag-llm-responsibility.md) | Accepted | Rule, RAG, LLM 역할 분리 | ADR 후보 023 |
| [ADR-0014](ADR-0014-pluggable-document-parser-ocr.md) | Accepted | 교체 가능한 문서 파서 및 OCR 아키텍처 | ADR 후보 024, 025 |
| [ADR-0015](ADR-0015-ad-coordinate-system.md) | Accepted | 광고 화면 좌표 체계 | ADR 후보 025 |
| [ADR-0016](ADR-0016-prompt-agent-config-versioning.md) | Accepted | 프롬프트 및 Agent 설정 버전관리 | ADR 후보 027 |
| [ADR-0017](ADR-0017-s3-compatible-object-storage.md) | Accepted | S3 호환 Object Storage 기반 파일 저장소 | ADR 후보 016 |
| [ADR-0018](ADR-0018-risk-level-decision-policy.md) | Accepted | 위험도 산정 기준 | ADR 후보 026 |
| [ADR-0019](ADR-0019-self-hosted-runner-deployment.md) | Accepted | Self-hosted Runner 배포 방식 | ADR 후보 033 |
| [ADR-0020](ADR-0020-dev-prod-environment-separation.md) | Accepted | PoC dev/prod(main) 환경 분리 정책 | ADR 후보 034 |
| [ADR-0021](ADR-0021-file-access-download-policy.md) | Accepted | 파일 접근 권한 및 다운로드 정책 | ADR 후보 036 |
| [ADR-0022](ADR-0022-audit-log-scope.md) | Accepted | 감사 로그 저장 범위 | ADR 후보 037 |
| [ADR-0023](ADR-0023-poc-kpi-formulas.md) | Accepted | PoC KPI 산식 확정 | ADR 후보 038 |
| [ADR-0024](ADR-0024-evaluation-exclusion-policy.md) | Accepted | 평가 제외 기준 | ADR 후보 039 |
| [ADR-0025](ADR-0025-defer-qualitative-evaluation.md) | Accepted | 정성 평가 보류 및 담당자 피드백 대체 | ADR 후보 040 |
| [ADR-0026](ADR-0026-api-contract-management.md) | Accepted | API 명세 관리 및 동기화 강제 방식 | ADR 후보 012 |
| [ADR-0027](ADR-0027-api-response-standard.md) | Accepted | API 응답 표준 | ADR 후보 013 |
| [ADR-0028](ADR-0028-id-generation-policy.md) | Accepted | ID 생성 규칙 | ADR 후보 017 |
| [ADR-0029](ADR-0029-postgresql-schema-separation.md) | Accepted | PostgreSQL 영역별 Schema 분리 | ADR 후보 015 |
| [ADR-0030](ADR-0030-frontend-stack.md) | Accepted | 프론트엔드 스택 선택 | ADR 후보 010 |
| [ADR-0031](ADR-0031-ai-assisted-development-responsibility.md) | Accepted | AI 활용 개발 및 검증 책임 | ADR 후보 006, 008 |
| [ADR-0032](ADR-0032-frontend-first-implementation-policy.md) | Accepted | 프론트엔드 1차 구현 및 디자인 개선 방식 | ADR 후보 009 |
| [ADR-0033](ADR-0033-local-and-shared-dev-vm.md) | Accepted | 로컬 개발 및 공용 개발 VM 병행 | ADR 후보 032 |
| [ADR-0034](ADR-0034-codex-claude-skills-standardization.md) | Superseded | Claude/Codex Skills 표준화 및 사용자 홈 설치 | ADR 후보 007 |
| [ADR-0035](ADR-0035-redis-queue-postgresql-job-state.md) | Accepted | Redis Queue 및 PostgreSQL Job 상태 테이블 병행 | 후속 구현 결정 |
| [ADR-0036](ADR-0036-jwt-auth-sso-ready-authorization.md) | Accepted | PoC 자체 JWT 인증 및 SSO 전환 가능 인가 구조 | 후속 구현 결정 |
| [ADR-0037](ADR-0037-file-upload-allowlist-and-size-limit.md) | Accepted | 파일 업로드 허용 확장자 및 용량 제한 | 후속 구현 결정 |
| [ADR-0038](ADR-0038-report-output-format-policy.md) | Accepted | 리포트 출력 형식 정책 | 후속 구현 결정 |
| [ADR-0039](ADR-0039-suggestion-decision-policy.md) | Accepted | 문구 추천 검토·채택·수정 정책 | 후속 구현 결정 |
| [ADR-0040](ADR-0040-standard-versioning-and-effective-date-policy.md) | Accepted | 기준자료 버전관리 및 검토 기준일 정책 | 후속 구현 결정 |
| [ADR-0041](ADR-0041-alembic-migration-and-seed-policy.md) | Accepted | Alembic 기반 DB 마이그레이션 및 Seed 분리 정책 | 후속 구현 결정 |
| [ADR-0042](ADR-0042-poc-runtime-performance-targets.md) | Accepted | PoC 런타임 성능 목표 기준 | 후속 구현 결정 |
| [ADR-0043](ADR-0043-rag-evidence-selection-policy.md) | Accepted | RAG 검색 결과 선정 및 근거 표시 정책 | 후속 구현 결정 |
| [ADR-0044](ADR-0044-ai-mock-fixture-test-policy.md) | Accepted | AI/OCR/RAG Mock 및 Fixture 테스트 정책 | 후속 구현 결정 |
| [ADR-0045](ADR-0045-user-error-message-policy.md) | Accepted | 사용자 오류 메시지 및 오류 코드 표시 정책 | 후속 구현 결정 |
| [ADR-0046](ADR-0046-postgresql-db-account-separation.md) | Accepted | PostgreSQL DB 계정 분리 정책 | 후속 구현 결정 |
| [ADR-0047](ADR-0047-poc-backup-and-restore-policy.md) | Accepted | PoC 백업 및 복구 정책 | 후속 구현 결정 |
| [ADR-0048](ADR-0048-poc-personal-sensitive-data-policy.md) | Accepted | PoC 개인정보 및 민감정보 저장/노출 정책 | 후속 구현 결정 |
| [ADR-0049](ADR-0049-poc-table-partitioning-policy.md) | Accepted | PoC 대용량 테이블 파티셔닝 적용 정책 | 후속 구현 결정 |
| [ADR-0050](ADR-0050-reference-metadata-policy.md) | Accepted | 기준자료 유형별 메타데이터 및 관리 단위 정책 | 후속 구현 결정 |
| [ADR-0051](ADR-0051-annotation-display-policy.md) | Accepted | 검토 UI Annotation 표현 방식 | 후속 구현 결정 |
| [ADR-0052](ADR-0052-text-ir-offset-policy.md) | Accepted | HWP/HWPX 텍스트 IR 및 Offset 기준 | 후속 구현 결정 |
| [ADR-0053](ADR-0053-confidence-threshold-policy.md) | Accepted | OCR/Parser/Annotation 신뢰도 임계값 및 확인 필요 처리 기준 | 후속 구현 결정 |
| [ADR-0054](ADR-0054-report-snapshot-hwpx-pdf-conversion.md) | Accepted | 리포트 스냅샷 및 HWPX-PDF 변환 방식 | 후속 구현 결정 |
| [ADR-0055](ADR-0055-api-authorization-scope-policy.md) | Accepted | API 인가 범위 및 부서 Scope 판정 기준 | 후속 구현 결정 |
| [ADR-0056](ADR-0056-jwt-session-token-lifetime-policy.md) | Accepted | JWT 세션 및 토큰 수명 정책 | 후속 구현 결정 |
| [ADR-0057](ADR-0057-browser-security-cors-csrf-headers.md) | Accepted | 브라우저 보안 정책, CORS/CSRF 및 보안 헤더 기준 | 후속 구현 결정 |
| [ADR-0058](ADR-0058-login-failure-lockout-password-policy.md) | Accepted | 로그인 실패 제한, 계정 잠금 및 비밀번호 정책 | 후속 구현 결정 |
| [ADR-0059](ADR-0059-ai-job-timeout-retry-deadletter-policy.md) | Accepted | AI 분석 Job Timeout, Retry, Dead-letter 및 Worker 장애 복구 정책 | 후속 구현 결정 |
| [ADR-0060](ADR-0060-poc-core-screen-ui-detail-policy.md) | Accepted | PoC 핵심 화면 UI 상세화 및 반응형 범위 정책 | 후속 구현 결정 |
| [ADR-0061](ADR-0061-rag-search-infra-failure-policy.md) | Accepted | RAG 검색 인프라 장애 처리 및 Fallback 금지 정책 | 후속 구현 결정 |
| [ADR-0062](ADR-0062-openapi-initial-contract-scope-and-validation.md) | Accepted | OpenAPI 초기 계약 작성 범위 및 검증 단계 정책 | 후속 구현 결정 |
| [ADR-0063](ADR-0063-compose-base-dev-prod-override-policy.md) | Accepted | Docker Compose 공통 파일 및 dev/prod Override 구성 정책 | 후속 구현 결정 |
| [ADR-0064](ADR-0064-ci-cd-quality-gate-test-split-policy.md) | Accepted | CI/CD 검증 Gate 및 테스트 실행 분리 정책 | 후속 구현 결정 |
| [ADR-0065](ADR-0065-normalized-document-schema-and-adapter-contract.md) | Accepted | NormalizedDocument 공통 출력 스키마 및 Parser/OCR Adapter 계약 정책 | 후속 구현 결정 |
| [ADR-0066](ADR-0066-coordinate-persistence-and-api-response-policy.md) | Accepted | Coordinate 필드 영속화 및 API 응답 구조 정합화 정책 | 후속 구현 결정 |
| [ADR-0067](ADR-0067-parser-ocr-raw-artifact-storage-retention-policy.md) | Accepted | Parser/OCR Raw Artifact 저장 위치, 보존 기간 및 접근 정책 | 후속 구현 결정 |
| [ADR-0068](ADR-0068-risk-rationale-persistence-and-api-response-policy.md) | Accepted | 위험도 산정 근거 영속화 및 API 응답 정책 | 후속 구현 결정 |
| [ADR-0069](ADR-0069-standard-reindex-and-chunk-query-api-policy.md) | Accepted | 기준자료 재색인 및 Chunk 조회 API 정책 | 후속 구현 결정 |
| [ADR-0070](ADR-0070-search-index-idempotent-sync-policy.md) | Accepted | Qdrant/OpenSearch 인덱스 동기화 및 Idempotent Upsert/Delete 정책 | 후속 구현 결정 |
| [ADR-0071](ADR-0071-search-index-schema-analyzer-payload-policy.md) | Accepted | 검색 인덱스 스키마, Analyzer/Synonym/Highlight 및 Payload 표준화 정책 | 후속 구현 결정 |
| [ADR-0072](ADR-0072-parser-ocr-engine-routing-policy.md) | Superseded | Parser/OCR 기본 엔진 선택 및 파일 유형별 라우팅 정책 | 후속 구현 결정 |
| [ADR-0073](ADR-0073-parser-ocr-quality-rerun-policy.md) | Accepted | Parser/OCR 품질 미달 시 재처리 및 보조 엔진 사용 정책 | 후속 구현 결정 |
| [ADR-0074](ADR-0074-validation-dataset-golden-label-snapshot-policy.md) | Accepted | PoC 검증 데이터셋, 정답지 및 평가 Snapshot 관리 정책 | 후속 구현 결정 |
| [ADR-0075](ADR-0075-project-scoped-skills-distribution.md) | Accepted | 프로젝트 범위 Skills 배포 및 온보딩 설치 정책 | ADR 후보 041 |
| [ADR-0076](ADR-0076-ai-tool-lifecycle-hook-enforcement-policy.md) | Accepted | AI 도구 Lifecycle Hook 적용 범위 및 문서 거버넌스 강제 계층 | ADR 후보 042 |
| [ADR-0077](ADR-0077-git-notion-one-way-document-sync-policy.md) | Accepted | Git-Notion 단방향 문서 자동 동기화 정책 | ADR 후보 043 (원천 branch는 ADR-0083 개정) |
| [ADR-0078](ADR-0078-poc-two-account-operation-profile.md) | Accepted | PoC 2계정 운영 프로필 정책 | ADR 후보 044 |
| [ADR-0079](ADR-0079-hwp-hwpx-hybrid-parser-composition.md) | Accepted | HWP/HWPX 이중 원천 Hybrid Parser 구성 정책 | ADR 후보 045 |
| [ADR-0080](ADR-0080-self-hosted-runner-compose-cd-policy.md) | Accepted | GitHub-hosted CI 및 Self-hosted Compose CD 정책 | CI·배포 실행 경계 결정 |
| [ADR-0081](ADR-0081-parser-service-and-external-ai-activation-separation.md) | Accepted | Private Parser/OCR와 외부 AI 활성화 분리 정책 | Parser·외부 AI 설정 경계 결정 |
| [ADR-0082](ADR-0082-development-default-branch-dev.md) | Accepted | 개발 기간 GitHub 기본 브랜치 dev 운영 정책 | ADR 후보 047 (Q76) |
| [ADR-0083](ADR-0083-development-notion-sync-source-dev.md) | Accepted | 개발 기간 Notion 동기화 원천 dev 확장 정책 | ADR 후보 047 (Q76 후속·ADR-0077 개정) |
| [ADR-0084](ADR-0084-python-311-dual-gpu-runtime-profiles.md) | Accepted | Python 3.11 및 DGX·H200 이중 GPU 실행 프로필 | 고객사 DAP 반입 환경 확정 |
| [ADR-0084](ADR-0084-python-311-dual-gpu-runtime-profiles.md) | Accepted | Python 3.11 및 DGX·H200 이중 GPU 실행 프로필 | 고객사 DAP 반입 환경 확정 |
| [ADR-0085](ADR-0085-source-structure-and-evidence-bundles.md) | Accepted | 원문 구조 보존과 규칙별 근거 묶음 검색 | 후보048·Q78 사용자 실행 승인 |

## 결정 대기 질문지

| 문서 | 용도 |
| --- | --- |
| [ADR 의사결정 질문지](decision-questions.md) | ADR 전체 목록이 아니라 사용자 선택지, 추천안, 결정 결과를 남긴 보조 기록. 공식 목록은 본 README와 개별 ADR 파일을 기준으로 함 |
