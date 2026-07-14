# ADR-0029: PostgreSQL 영역별 Schema 분리

## 상태

Accepted

## 배경

PostgreSQL은 광고물, 검토 결과, 기준자료/RAG 메타데이터, PoC 검증 데이터, 감사 로그를 함께 관리한다. 이 데이터들은 저장 목적, 접근 권한, 보관 정책, 조회 패턴이 서로 다르다.

ADR-0020에서 PoC 환경은 `dev`와 `prod(main)`으로 나누고, 환경별 PostgreSQL DB를 분리하기로 했다. 이제 각 환경 DB 내부에서 업무 영역별 schema를 분리할지 결정해야 한다.

초기 단일 `public` schema는 구현이 단순하지만, 감사 로그, RAG 기준자료, 검증 데이터셋이 늘어날수록 테이블 경계와 권한 경계가 흐려질 수 있다. 본 프로젝트는 감사 추적, RAG 근거 관리, PoC 평가를 핵심 범위로 포함하므로 PoC 단계부터 논리 schema를 분리한다.

## 결정

PoC 단계부터 PostgreSQL schema를 업무 영역별로 분리한다.

| Schema | 역할 |
| --- | --- |
| `app` | 사용자, 부서, 권한, 광고물, 파일 메타데이터, 검토, 리포트, 공통 코드 |
| `rag` | 기준자료, 기준자료 버전, 근거, chunk, Q&A, 검색 연계 메타데이터 |
| `validation` | 검증 데이터셋, 담당자 판단, 평가 실행, KPI 결과 |
| `audit` | 감사 로그, 접근 로그, 주요 변경 이력 |

물리 DB는 환경별로 분리하고, DB 내부 schema는 업무 영역별로 분리한다.

| 구분 | 기준 |
| --- | --- |
| dev DB | `nh_ad_dev` |
| prod(main) DB | `nh_ad_prod` |
| 업무 schema | `app`, `rag`, `validation`, `audit` |
| API/OpenAPI | schema명을 노출하지 않음 |
| ORM/migration | schema명을 명시적으로 사용 |

## Schema 매핑 기준

초기 테이블은 다음 schema에 둔다.

| Schema | 테이블 |
| --- | --- |
| `app` | `departments`, `users`, `roles`, `user_roles`, `common_codes` |
| `app` | `advertisements`, `advertisement_files`, `advertisement_revisions` |
| `app` | `reviews`, `review_jobs`, `review_steps`, `ocr_text_blocks`, `layout_blocks` |
| `app` | `review_items`, `review_item_evidences`, `annotations`, `suggestions`, `suggestion_decisions` |
| `app` | `opinion_drafts`, `reports`, `comparisons`, `comparison_items` |
| `rag` | `standards`, `standard_versions`, `evidences`, `evidence_chunks` |
| `rag` | `qa_sessions`, `qa_messages`, `qa_message_evidences` |
| `validation` | `validation_datasets`, `validation_judgments`, `evaluations`, `evaluation_metrics` |
| `audit` | `audit_logs` |

Schema 간 FK 참조는 허용한다. 예를 들어 `app.review_item_evidences`는 `rag.evidences`를 참조할 수 있고, `audit.audit_logs`는 대상 엔티티의 내부 UUID와 외부 노출 ID를 기록할 수 있다.

## Migration 및 구현 기준

| 항목 | 기준 |
| --- | --- |
| schema 생성 | 초기 migration에서 `CREATE SCHEMA IF NOT EXISTS app`, `rag`, `validation`, `audit` 순서로 생성 |
| migration version table | ADR-0041 기준 `app.alembic_version` 사용 |
| ORM model | SQLAlchemy model에 schema를 명시 |
| search_path | 운영 쿼리는 `search_path` 의존보다 명시적 schema 사용을 우선 |
| 권한 | ADR-0046 기준 `app`, `migration`, `readonly`, `admin` DB 계정을 분리하되, schema별 세부 권한 분리는 본사업 전환 시 재검토 |
| 백업 | ADR-0047 기준 PostgreSQL/Object Storage/Qdrant 백업, OpenSearch 재색인 복구 적용 |

## 대안

| 대안 | 판단 |
| --- | --- |
| 단일 `public` schema | 구현은 단순하지만 감사/RAG/검증 데이터 경계가 흐려진다. |
| 영역별 schema 분리 | 데이터 성격과 권한 경계가 명확하고 본사업 전환 비용을 줄일 수 있다. |
| DB 자체 분리 | 격리는 강하지만 PoC 단계에서는 배포, 연결, 백업, 운영 부담이 과도하다. |
| PoC는 `public`, 본사업 때 재검토 | 초기 속도는 빠르지만 본사업 전환 시 schema 이동 migration 비용이 생길 수 있다. |

## 결정 근거

- 감사 로그, RAG 기준자료, PoC 검증 데이터는 보관 정책과 접근 성격이 다르다.
- ADR-0020의 환경별 DB 분리와 충돌하지 않고, 같은 DB 내부의 논리 경계를 강화한다.
- ADR-0022의 감사 로그 저장 범위, ADR-0013의 Rule/RAG/LLM 역할 분리, ADR-0023/0024의 PoC 평가 기준과 정합하다.
- PoC부터 schema를 분리하면 본사업 전환 시 테이블 이동과 FK 재구성 부담을 줄일 수 있다.
- Docker Compose와 단일 PostgreSQL 인스턴스 구조를 유지하면서도 데이터 경계를 명확히 할 수 있다.

## 영향

- DB 명세서의 테이블은 schema 매핑 기준을 함께 읽어야 한다.
- 초기 migration은 schema 생성 후 테이블을 생성해야 한다.
- SQLAlchemy, Alembic, raw SQL은 schema명을 명시해야 한다.
- 테스트 DB 초기화와 fixture 로딩도 schema 생성 순서를 포함해야 한다.
- API path, OpenAPI schema, 화면에는 DB schema명이 노출되지 않는다.

## 후속 조치

- DB 명세서에 schema 매핑표를 반영한다.
- Alembic 초기 migration 작성 시 schema를 생성하고 version table은 ADR-0041 기준 `app.alembic_version`을 사용한다.
- DB 계정 분리 정책은 ADR-0046을 따른다.
- 백업 및 복구 정책은 ADR-0047을 따른다.
- 본사업 전환 시 schema별 세부 권한, 장기 백업, 보관 정책을 별도 ADR 또는 운영 정책으로 보완한다.
- 테스트케이스 작성 시 schema 생성 및 migration 적용 실패 케이스를 개발 환경 검증에 포함한다.

## 관련 문서

- `docs/database-specification.md`
- `docs/adr/ADR-0006-postgresql-primary-database.md`
- `docs/adr/ADR-0020-dev-prod-environment-separation.md`
- `docs/adr/ADR-0022-audit-log-scope.md`
- `docs/adr/ADR-0013-rule-rag-llm-responsibility.md`
- `docs/adr/ADR-0046-postgresql-db-account-separation.md`
- `docs/adr/ADR-0047-poc-backup-and-restore-policy.md`
