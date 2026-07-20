# DB 명세서

## AI 활용 금융상품 광고심의 적정성 검토 에이전트

## 문서 현행 정보

| 항목 | 내용 |
| --- | --- |
| 현행 버전 | v1.14 |
| 기준일 | 2026-07-20 |

## 변경 이력

| 버전 | 기준일 | 변경 내용 |
| --- | --- | --- |
| v1.14 | 2026-07-20 | ADR-0079 HWP/HWPX hybrid parser의 구성요소 raw artifact와 단일 병합 산출물 provenance 영속화 기준을 추가 |
| v1.13 | 2026-07-20 | 규정·가이드라인 초기 적재 시 standard version metadata에 parser provenance와 구조 통계를 보존하는 기준을 추가 |
| v1.12 | 2026-07-16 | 0009 운영 정합성 revision으로 OCR/layout 좌표 물리명·정밀도와 normalized text GIN 인덱스를 명세에 맞추고 현행 migration head를 동기화 |
| v1.11 | 2026-07-15 | M8 revision 동시 번호 직렬화, M6 PostgreSQL restart roundtrip과 additive 0008 runtime/readonly 권한 반영 |
| v1.10 | 2026-07-15 | G008 M7 PostgreSQL runtime repository의 version 증가, 원자 평가 저장, canonical snapshot/hash 및 기존 평가 불변 조회 실행 증거 반영 |
| v1.9 | 2026-07-14 | G008 M7 additive 0007 migration의 validation DB 원천 version, 승인 제외, immutable snapshot/hash 및 4개 KPI 저장 제약 반영 |
| v1.8 | 2026-07-14 | G007 M6 additive 0006 migration의 추천 판단 이력, fixed-reference Q&A, 의견 초안, immutable report snapshot 및 수정 비교/re-analysis 제약 반영 |
| v1.7 | 2026-07-14 | M5 worker의 parser 선택 산출물→결과 bundle 원자 영속화와 review snapshot/완료 상태 갱신 경계 반영 |
| v1.6 | 2026-07-14 | M5 owner revision의 review item/risk rationale/evidence 상태·버전 snapshot/Annotation 좌표·offset 불변조건 반영 |
| v1.5 | 2026-07-14 | M4 품질 재처리 전체 시도의 artifact metadata 기록과 단계별 단일 선택 산출물 영속화 불변조건 보강 |
| v1.4 | 2026-07-14 | M4 owner revision의 Review/Job/Step, normalized text/layout, raw parser artifact metadata와 retry/retention 제약 반영 |
| v1.3 | 2026-07-14 | M3 owner revision의 standards/version/evidence/chunk/reindex 원천 테이블, 결정적 인덱스 ID 제약과 분리된 synthetic seed 경계 반영 |
| v1.2 | 2026-07-14 | M2 owner revision의 auth/common/advertisement/file/audit 테이블과 분리된 idempotent common/dev seed 경계 반영 |
| v1.1 | 2026-07-14 | M1 schema-only Alembic base, 일회성 bootstrap, 계정별 최소권한 및 runtime/migration DSN 분리 기준 반영 |
| v1.0 | 2026-07-13 | ADR-0001~ADR-0074 검토 결과 반영, schema/계정/Parser/OCR/RAG/평가 snapshot 기준 보강 |

---

## 0. 문서 정보

| 항목 | 내용 |
| --- | --- |
| 문서명 | DB 명세서 |
| 프로젝트명 | AI 활용 금융상품 광고심의 적정성 검토 에이전트 |
| 대상 시스템 | 멀티모달 RAG 기반 금융상품 광고심의 적정성 검토 AI 에이전트 PoC |
| 문서 버전 | v1.9 |
| 작성 목적 | API, 백엔드, AI 분석 모듈, RAG 검색, PoC 검증을 위한 데이터 구조 정의 |
| 주요 DB | PostgreSQL |
| 벡터 DB | Qdrant |
| 키워드 검색 | OpenSearch |

---

# 1. DB 설계 개요

## 1.1 설계 목적

본 DB 명세서는 다음 데이터를 체계적으로 저장·조회·추적하기 위한 데이터베이스 구조를 정의한다.

- 사용자, 부서, 권한
- 광고물 기본정보 및 첨부파일
- 광고물 수정본
- AI 검토 요청 및 진행 상태
- OCR/VLM 텍스트 추출 결과
- 화면 레이아웃 분석 결과
- Rule/RAG/Multimodal 기반 검토 결과
- 검토 항목별 근거 매핑
- 광고 화면 Annotation 정보
- 법령, 내부 기준, 심의사례, 문구 템플릿
- Qdrant/OpenSearch 연계용 기준자료 Chunk
- 보완 문구 및 대체 문구 추천
- 광고 규정 Q&A 이력
- 심의 의견 초안
- 검토 리포트
- PoC 검증 데이터셋
- PoC 성능평가 결과
- 감사 로그

---

## 1.2 DB 구성 원칙

| 원칙 | 내용 |
| --- | --- |
| 추적성 | 광고물 등록부터 검토, 수정, 리포트 생성까지 이력을 보존한다. |
| 근거 기반 | AI 검토 결과는 기준자료, 법령, 심의사례 등 근거 데이터와 연결한다. |
| 버전 관리 | 기준자료, 광고물 수정본, AI 재검토 결과는 버전 또는 회차로 관리한다. |
| 확장성 | 예금·적금 외 대출, 카드, 투자성 상품 등으로 확장 가능한 구조로 설계한다. |
| 비동기 처리 지원 | AI 분석 Job과 Step 상태를 분리해 장시간 분석 작업을 추적한다. |
| 검색 연계 | PostgreSQL은 원천 메타데이터, Qdrant는 벡터 검색, OpenSearch는 키워드 검색을 담당한다. |
| 감사 대응 | 주요 사용자 행위와 데이터 변경 이력을 감사 로그로 저장한다. |

---

# 2. 전체 ERD 개요

## 2.1 주요 엔티티 관계

```text id=“eoek4l” departments └─ users └─ user_roles ─ roles

advertisements ├─ advertisement_files ├─ advertisement_revisions └─ reviews ├─ review_jobs ├─ review_steps ├─ ocr_text_blocks ├─ layout_blocks ├─ review_items │ ├─ review_item_evidences ─ evidences │ ├─ annotations │ └─ suggestions │ └─ suggestion_decisions ├─ opinion_drafts └─ reports

standards ├─ standard_versions └─ evidences └─ evidence_chunks

qa_sessions └─ qa_messages └─ qa_message_evidences ─ evidences

validation_datasets ├─ validation_judgments └─ evaluations └─ evaluation_metrics

audit_logs

```

---

## 2.2 저장소 역할 분리

| 저장소 | 역할 | 주요 데이터 |
|---|---|---|
| PostgreSQL | 원천 데이터 및 트랜잭션 관리 | 광고물, 검토 결과, 기준자료 메타데이터, 리포트, 사용자, 이력 |
| Qdrant | 벡터 검색 | 기준자료 Chunk 임베딩, 심의사례 임베딩, 상품설명서 Chunk 임베딩 |
| OpenSearch | 키워드 검색 | 기준자료 본문, OCR 텍스트, 심의사례, 광고 문구, 로그 검색 |

---

# 3. 공통 설계 기준

## 3.1 Schema 구성

PostgreSQL은 환경별 물리 DB를 분리하고, 각 DB 내부에서는 업무 영역별 schema를 분리한다. `dev` 환경은 `nh_ad_dev`, `prod(main)` 환경은 `nh_ad_prod` DB를 사용하며, 각 DB 안에 동일한 schema 구조를 둔다.

| Schema | 역할 | 주요 테이블 |
| --- | --- | --- |
| `app` | 사용자, 권한, 광고물, 검토, 리포트, 공통 코드 | `users`, `advertisements`, `reviews`, `review_items`, `reports`, `common_codes` |
| `rag` | 기준자료, 근거, chunk, Q&A, 검색 연계 메타데이터 | `standards`, `evidences`, `evidence_chunks`, `qa_sessions`, `qa_messages` |
| `validation` | PoC 검증 데이터셋, 담당자 판단, 평가 실행, KPI 결과 | `validation_datasets`, `validation_judgments`, `evaluations`, `evaluation_metrics` |
| `audit` | 감사 로그, 접근 로그, 주요 변경 이력 | `audit_logs` |

API, OpenAPI, 화면에는 DB schema명을 노출하지 않는다. DB 명세서 본문의 테이블명은 가독성을 위해 schema prefix 없이 표기하되, 실제 migration과 SQL에서는 본 매핑표의 schema를 적용한다.

Schema 간 FK 참조는 허용한다. 예를 들어 `app.review_item_evidences`는 `rag.evidences`를 참조할 수 있다.

세부 결정 기준은 [ADR-0029: PostgreSQL 영역별 Schema 분리](adr/ADR-0029-postgresql-schema-separation.md)를 따른다.

---

## 3.2 Schema별 테이블 매핑

| Schema | 테이블 |
| --- | --- |
| `app` | `departments`, `users`, `roles`, `user_roles`, `refresh_tokens`, `common_codes` |
| `app` | `advertisements`, `advertisement_files`, `advertisement_revisions` |
| `app` | `reviews`, `review_jobs`, `review_steps`, `ocr_text_blocks`, `layout_blocks` |
| `app` | `review_items`, `review_item_evidences`, `annotations`, `suggestions`, `suggestion_decisions` |
| `app` | `opinion_drafts`, `reports`, `comparisons`, `comparison_items` |
| `rag` | `standards`, `standard_versions`, `evidences`, `evidence_chunks` |
| `rag` | `qa_sessions`, `qa_messages`, `qa_message_evidences` |
| `validation` | `validation_datasets`, `validation_judgments`, `evaluations`, `evaluation_metrics` |
| `audit` | `audit_logs` |

---

## 3.3 Migration 및 Seed 기준

DB migration은 [ADR-0041: Alembic 기반 DB 마이그레이션 및 Seed 분리 정책](adr/ADR-0041-alembic-migration-and-seed-policy.md)을 따른다. M1의 `0001_schema_only_base`는 아래 4개 schema와 `app.alembic_version`만 생성한다. 업무 테이블은 각 기능 구현 시 후속 revision으로 추가하며 seed를 revision에 포함하지 않는다.

```sql
CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA IF NOT EXISTS rag;
CREATE SCHEMA IF NOT EXISTS validation;
CREATE SCHEMA IF NOT EXISTS audit;
```

| 항목 | 기준 |
| --- | --- |
| migration 도구 | Alembic |
| migration 위치 | `apps/backend/migrations` |
| version table | `app.alembic_version` |
| schema 생성 순서 | `app`, `rag`, `validation`, `audit` |
| ORM model | schema명을 명시 |
| SQL 작성 | `search_path` 의존보다 명시적 schema 사용 우선 |
| DB 계정 | ADR-0046 기준 `app`, `migration`, `readonly`, `admin` 분리 |
| 접속 정보 | API/Worker는 runtime DSN, Alembic은 migration DSN만 사용하며 상호 대체하지 않음 |
| 본사업 전환 | schema별 세부 권한, RLS, 컬럼 암호화, 백업, 보관 정책 재검토 |

Migration은 schema, table, column, index, FK, unique constraint, check constraint 등 DB 구조 변경만 담당한다. 공통 코드, 역할, dev 사용자, 샘플 기준자료 같은 seed data는 migration에 포함하지 않는다.

### DB 계정 분리 기준

DB 계정 분리 정책은 [ADR-0046: PostgreSQL DB 계정 분리 정책](adr/ADR-0046-postgresql-db-account-separation.md)을 따른다.

| 계정 | 용도 | 권한 기준 |
| --- | --- | --- |
| `app` | API 서버와 Worker 런타임 | 서비스에 필요한 CRUD, DDL 금지 |
| `migration` | Alembic migration 실행 | schema/table/index/constraint 변경, role 관리 금지 |
| `readonly` | 운영 조회, 리포트 검증, 장애 분석 | 필요한 테이블 `SELECT`, 쓰기 및 DDL 금지 |
| `admin` | 계정/권한 관리, 장애 대응, 복구, 예외적 수동 운영 | 앱 런타임 및 CI/CD 상시 사용 금지 |

PoC에서는 4종 계정을 분리하되 schema별 세부 권한 분리까지 강제하지 않는다. 본사업 전환 또는 고객사 보안 요구 확정 시 schema별 권한, RLS, 컬럼 암호화, 백업/복구 권한을 별도 정책으로 구체화한다.

Compose 초기화에서는 4종 운영 계정을 만들기 위한 별도의 일회성 bootstrap identity를 허용한다. 이 identity는 초기화 완료 전에 `NOLOGIN`으로 전환하고 비밀번호를 폐기한다. 장기 실행되는 PostgreSQL, API, Worker, Frontend 컨테이너에는 bootstrap/admin 자격증명을 주입하지 않으며, CI의 격리된 권한 probe도 같은 폐기와 재사용 거부를 검증해야 한다.

### Seed 관리 기준

| 데이터 | 관리 방식 |
| --- | --- |
| 공통 코드, 역할 코드 | `apps/backend/seeds`와 `scripts/seed-common-data.sh`에서 idempotent upsert |
| dev 샘플 사용자/부서 | `scripts/seed-dev-data.sh` 전용 |
| 고객사 승인 샘플 데이터 | 승인 범위 내 별도 import 또는 seed |
| 테스트 fixture | 테스트 코드 또는 fixture 파일 |
| 운영 데이터 | migration/seed로 임의 주입 금지 |

### M2 owner revision

`0002_m2_auth_advertisement_audit`은 `0001_schema_only_base`를 직접 상속하며 아래 테이블만 생성한다.

| Schema | M2 소유 테이블 |
| --- | --- |
| `app` | `departments`, `roles`, `users`, `user_roles`, `refresh_tokens`, `common_codes` |
| `app` | `advertisements`, `advertisement_revisions`, `advertisement_files` |
| `audit` | `audit_logs` |

M2 revision은 seed, role 생성/변경, M1 schema bootstrap, M3 이후 `reviews`/검색/리포트 테이블을 포함하지 않는다. `advertisements.latest_review_id`와 `advertisement_revisions.base_review_id`는 M2에서 nullable 식별자 컬럼으로만 두고 reviews owner revision이 생성될 때 FK를 추가한다.

Migration 완료 후 runtime `app`에는 `app`/`audit` schema의 DML만, `readonly`에는 조회만 부여한다. 공통 역할/코드는 `apps/backend/seeds/common.sql`, synthetic 부서/사용자는 `apps/backend/seeds/dev.sql`로 분리하고 두 seed 모두 idempotent하게 적용한다. Dev seed는 `NH_ENVIRONMENT=dev`, `app` runtime identity, 평문이 아닌 `NH_DEV_SEED_PASSWORD_HASH`를 요구한다.

Refresh session은 발급 당시 `token_version`을 저장하고 `users.auth_token_version` 불일치 시 거부한다. `(user_id, revoked_at, expires_at)` active index는 권한 변경·사용자 비활성화 시 사용자별 미폐기 token 전체 revoke를 지원한다. 광고 파일의 `storage_provider`/`bucket`/`object_key`/`checksum_sha256`은 repository 내부 필드이며 API DTO, 일반 로그와 감사 조회 응답에는 포함하지 않는다.

### M3 owner revision

`0003_m3_standards_search`는 `0002_m2_auth_advertisement_audit`을 직접 상속하며 기존 0001/0002를 수정하지 않는다.

| 구분 | M3 기준 |
| --- | --- |
| Owner tables | `rag.standards`, `rag.standard_versions`, `rag.evidences`, `rag.evidence_chunks`, `rag.standard_reindex_jobs` |
| Source of truth | PostgreSQL 불변 version과 Chunk row. Qdrant/OpenSearch는 재생성 가능한 인덱스 |
| Seed | migration과 분리된 `apps/backend/seeds/m3_test.sql`, synthetic/direct-text/idempotent 전용 |
| Upgrade | 빈 DB 0001→0002→0003 및 기존 M2 DB 0002→0003 모두 지원 |
| Exclusion | Parser/OCR, review/job/result/report 및 실제 embedding provider는 M3 owner 범위가 아님 |

Runtime `app`은 `rag` schema의 DML만, `readonly`는 조회만 허용한다. 고정 fixture의 vector와 score는 테스트 재현성 전용이며 외부 embedding provider를 호출하지 않는다.

### M4 owner revision

`0004_m4_parser_ocr_jobs`는 `0003_m3_standards_search`를 직접 상속하며 기존 0001~0003을 수정하지 않는다.

| 구분 | M4 기준 |
| --- | --- |
| Owner tables | `app.reviews`, `app.review_jobs`, `app.review_steps`, `app.parser_artifacts`, `app.ocr_text_blocks`, `app.layout_blocks` |
| 상태 원천 | Review/Job/Step 상태와 retry/heartbeat/dead-letter 이력은 PostgreSQL 원천 |
| 중복 방지 | 광고물별 활성 `ANALYSIS_REQUESTED`/`ANALYZING` review partial unique index |
| Parser 결과 | 최종 `is_selected_output=true` NormalizedDocument의 text/layout block만 업무 테이블에 반영 |
| Raw artifact | 환경별 `parser-artifacts` bucket 본문과 DB reference/checksum/version/attempt/retention metadata 분리 |
| Upgrade | 빈 DB 0001→0002→0003→0004 및 기존 M3 DB 0003→0004 모두 지원 |
| Exclusion | backend/worker 실행, provider SDK와 실제 OCR 품질 평가는 M4 entry gate migration 범위가 아님 |

`review_jobs`는 최대 retry 3회, `RETRY_PENDING`/`STALE`/`FAILED_FINAL`, 다음 retry, timeout, lock/heartbeat와 dead-letter 시각을 보존한다. `parser_artifacts`는 시도 순번, primary/selected 여부, 품질 재처리 사유, checksum, parser/rule/IR 버전, confidence, 보존 만료/hold/삭제 시각을 보존한다. 일반 사용자 API는 raw 본문, bucket/object key, presigned URL을 노출하지 않는다.

### M5 owner revision

`0005_m5_review_results`는 `0004_m4_parser_ocr_jobs`를 직접 상속하며 기존 0001~0004를 수정하지 않는다.

| 구분 | M5 기준 |
| --- | --- |
| Owner tables | `app.review_items`, `app.review_item_evidences`, `app.annotations` |
| Risk rationale | `risk_policy_version`, `risk_reason_codes`, `risk_score_detail`, source engine/version 필수 |
| Evidence state | 연결/Rule 불필요/업무적 부족/검색 장애를 `evidence_status`와 제한된 failure code로 분리 |
| Version snapshot | evidence, chunk, `standard_version_id`, rank, relevance, match source를 검토 시점 값으로 보존 |
| Annotation | BOX는 원본·정규화 Coordinate, TEXT_HIGHLIGHT는 text block+normalized offset, 위치 미확정은 목록 fallback |
| Upgrade | 빈 DB 0001→0002→0003→0004→0005 및 기존 M4 DB 0004→0005 모두 지원 |
| Exclusion | backend pipeline/frontend runtime, provider SDK, 실제 LLM 호출은 M5 entry gate migration 범위가 아님 |

검토 항목은 evidence mapping이 없어도 `NOT_REQUIRED`, `INSUFFICIENT`, `SEARCH_UNAVAILABLE` 중 하나를 저장해야 한다. 검색 장애에만 `RAG_SEARCH_UNAVAILABLE` 또는 `RAG_SEARCH_FAILED`를 허용하고 정상 검색의 근거 부족과 분리한다. 항목별 저장 근거는 ADR-0043 기준 최대 5개이며 `rank_no`는 1~5로 제한한다.

M5 worker는 선택된 `NormalizedDocument`와 raw artifact metadata가 먼저 영속화된 동일 Job에 대해서만 결과 bundle을 저장한다. `review_items`와 연결 근거·Annotation을 한 transaction에서 추가하고, 동일 Job·동일 결과 식별자 bundle의 재전달은 idempotent no-op으로 처리하되 내용이 충돌하는 중복 bundle은 거부한다. 이후 `reviews.applied_standard_version_ids`와 `overall_risk_level` snapshot을 갱신하고 Rule/RAG/결과 단계 완료와 Job/Review 완료를 순서대로 반영한다. 검색 장애 또는 structured schema 오류가 발생해도 기존 Rule item row를 삭제·정상화하지 않는다.

### M7 owner revision

`0007_m7_validation_kpi`는 `0006_m6_support_outputs`를 직접 상속하며 기존 0001~0006을 수정하지 않는다.

| 구분 | M7 기준 |
| --- | --- |
| Owner tables | `validation.validation_datasets`, `validation.validation_judgments`, `validation.evaluations`, `validation.evaluation_metrics` |
| Runtime source | 데이터셋과 정답지는 PostgreSQL 원천이고 Git fixture는 dev/test 회귀 입력 전용 |
| Version | 정답/메타데이터 또는 담당자 판단 변경은 각각 양의 `dataset_version`, `judgment_version`으로 식별 |
| Exclusion | 승인된 사유 코드와 확정자/시각이 있는 제외만 확정 제외로 저장하며 AI 오답은 제외하지 않음 |
| Snapshot | dataset/judgment/exclusion/AI/version/policy JSONB와 canonical `snapshot_hash`, `LATEST_COMPLETED` 선택 정책을 평가 ID별로 고정 |
| KPI | 4개 metric code별 numerator/denominator/partial/excluded/target/score/달성 여부를 저장하고 분모 0은 nullable score와 `not_applicable=true`, `achieved=false` |
| Upgrade | 실제 PostgreSQL 빈 DB 0001→0007 및 기존 M6 DB 0006→0007을 모두 실행 검증 |
| Scope exclusion | backend/frontend 실행, 외부 provider, network, credential은 M7 entry gate 범위가 아님 |

M7 backend runtime은 `PostgresValidationRepository`를 통해 데이터셋·판단 version 증가와 평가·4개 KPI row 저장을 transaction 단위로 수행한다. 평가 조회는 현재 데이터셋/판단 row를 재계산하지 않고 `evaluations`의 snapshot과 `evaluation_metrics` 저장값을 반환한다. 실제 PostgreSQL roundtrip은 `apps/backend/tests/test_m7_postgres_repository.py`가 검증하고, clean 0001→0007 및 기존 0006→0007 upgrade는 `tests/integration/test_m7_database_contract.py`가 계속 잠근다.

### M8 runtime privilege revision과 durability

`0008_m8_support_privileges`는 `0007_m7_validation_kpi`를 상속하는 additive 권한 revision이며 0001~0007 schema를 수정하지 않는다. `app.suggestions`, `app.suggestion_decisions`, `app.opinion_drafts`, `app.reports`, `app.comparisons`, `app.comparison_items`와 `rag.qa_sessions`, `rag.qa_messages`, `rag.qa_message_evidences`에 runtime `app` CRUD와 `readonly` SELECT만 부여한다. QA 테이블은 `rag` schema 소유이므로 `app.*`로 잘못 qualification하지 않는다.

`PostgresRepository.add_revision`은 대상 `advertisements` row를 `FOR UPDATE`로 잠그고 checksum 중복을 거부한 뒤 `MAX(revision_no)+1`을 배정한다. 따라서 같은 광고물의 동시 등록도 양의 연속 revision 번호를 가지며 revision/file/advertisement `REVISED` 상태가 한 transaction에 저장된다. `PostgresSupportRepository`는 M6 owner tables를 그대로 사용하고 report canonical payload, immutable hash, HWPX/PDF source linkage, comparison item을 재시작 이후에도 복원한다.

### 운영 정합성 revision

`0009_operational_consistency`는 기존 owner revision을 수정하지 않고 `0008_m8_support_privileges`를 상속한다. `ocr_text_blocks`와 `layout_blocks`의 좌표 물리명을 `x`, `y`, `width`, `height`로 통일하고 normalized 좌표와 rotation 정밀도를 본 명세에 맞춘다. `ocr_text_blocks.normalized_text`에는 built-in `to_tsvector('simple', ...)` 표현식 기반 `idx_ocr_blocks_text_gin`을 생성한다. Worker SQL은 0009 head의 물리 컬럼명만 사용하며 배포·복구 smoke는 `0009_operational_consistency`를 현행 head로 확인한다.

---

## 3.4 Naming Convention

| 구분 | 규칙 | 예시 |
|---|---|---|
| 테이블명 | snake_case 복수형 | `advertisements`, `review_items` |
| 컬럼명 | snake_case | `created_at`, `review_status` |
| PK | `id` 또는 `{entity}_id` | `advertisement_id` |
| FK | 참조 엔티티명 + `_id` | `review_id`, `user_id` |
| 외부 노출 ID | `{entity}_public_id` 또는 업무상 명확한 ID명 | `advertisement_public_id` |
| 일시 | `timestamptz` 사용 | `created_at` |
| 상태값 | varchar + Enum 정의 | `review_status` |
| Boolean | `is_` 접두사 | `is_active`, `is_deleted` |
| JSON | `jsonb` 사용 | `metadata`, `result_json` |

---

## 3.5 ID 생성 기준

DB 내부 PK/FK는 UUID를 사용한다. API, 화면, 리포트, 고객사 커뮤니케이션에 노출하는 ID는 Prefix 문자열을 별도 컬럼으로 관리한다.

| 구분 | 타입 | 용도 |
| --- | --- | --- |
| 내부 PK | `uuid` | DB 관계, FK, migration, 내부 처리 |
| 내부 FK | `uuid` | 참조 무결성 |
| 외부 노출 ID | `varchar` | API path, 화면 표시, 리포트, 감사 추적 |

외부 노출 ID 컬럼에는 unique constraint를 둔다. 감사 로그와 파일 접근 로그는 가능한 경우 내부 UUID와 외부 노출 ID를 함께 저장한다. 세부 기준은 [ADR-0028: ID 생성 규칙](adr/ADR-0028-id-generation-policy.md)을 따른다.

---

## 3.6 공통 컬럼

대부분의 업무 테이블은 다음 공통 컬럼을 포함한다.

| 컬럼명 | 타입 | 설명 |
|---|---|---|
| created_at | timestamptz | 생성일시 |
| created_by | varchar(100) | 생성자 ID |
| updated_at | timestamptz | 수정일시 |
| updated_by | varchar(100) | 수정자 ID |
| is_deleted | boolean | 논리 삭제 여부 |

---

## 3.7 주요 Enum

### 상품군 `product_group`

| 값 | 설명 |
|---|---|
| DEPOSIT | 예금 |
| SAVINGS | 적금 |
| DEMAND_DEPOSIT | 입출금 |
| EVENT_FINANCIAL_PRODUCT | 이벤트성 금융상품 |
| LOAN | 대출 |
| CARD | 카드 |
| INVESTMENT | 투자성 상품 |

### 광고유형 `advertisement_type`

| 값 | 설명 |
|---|---|
| LEAFLET | 상품 안내장 |
| BRANCH_MEMO | 영업점 메모 |
| CUSTOMER_NOTICE | 고객 안내문 |
| MOBILE_BANNER | 모바일 배너 |
| INTERNET_BANKING_BANNER | 인터넷뱅킹 배너 |
| EVENT_PAGE | 이벤트 페이지 |
| APP_PUSH | 앱 Push |
| SMS | SMS |
| ALIMTALK | 알림톡 |
| HTML_CAPTURE | HTML 캡처 |

### 검토상태 `review_status`

| 값 | 설명 |
|---|---|
| DRAFT | 임시저장 |
| UPLOADED | 업로드 완료 |
| ANALYSIS_REQUESTED | 분석 요청 |
| EXTRACTING | 텍스트 추출 중 |
| ANALYZING | AI 검토 중 |
| REVIEW_COMPLETED | 검토 완료 |
| REVIEW_FAILED | 검토 실패 |
| REVISED | 수정본 등록 |
| COMPARED | 수정 전후 비교 완료 |
| REPORT_CREATED | 리포트 생성 완료 |

### 검토유형 `review_type`

| 값 | 설명 |
|---|---|
| REQUIRED_PHRASE | 필수 문구 검토 |
| INTEREST_RATE | 금리·수익률·조건 표시 검토 |
| MISLEADING_EXPRESSION | 과장·오인 표현 검토 |
| PRODUCT_CONSISTENCY | 상품설명서·약관 정합성 검토 |
| VISIBILITY | 위치·크기·강조·시인성 검토 |
| EVIDENCE_MATCHING | 근거 매칭 검토 |
| OCR_QUALITY | OCR 판독 품질 검토 |

### 판정결과 `result_status`

| 값 | 설명 |
|---|---|
| APPROPRIATE | 적정 |
| NEEDS_REVISION | 수정 필요 |
| NEEDS_CONFIRMATION | 확인 필요 |
| NOT_APPLICABLE | 해당 없음 |
| REVIEW_EXCLUDED | 평가 제외 |

### 위험도 `risk_level`

| 값 | 설명 |
|---|---|
| HIGH | 높음 |
| MEDIUM | 중간 |
| LOW | 낮음 |
| CHECK_REQUIRED | 확인 필요 |

---

# 4. 사용자 및 권한 테이블

## 4.1 departments

부서 정보를 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| department_id | varchar(50) | Y |  | Y | 부서 ID |
| department_name | varchar(200) |  |  | Y | 부서명 |
| parent_department_id | varchar(50) |  | departments |  | 상위 부서 ID |
| is_active | boolean |  |  | Y | 활성 여부 |
| created_at | timestamptz |  |  | Y | 생성일시 |
| updated_at | timestamptz |  |  |  | 수정일시 |

### Index

| 인덱스명 | 컬럼 |
|---|---|
| idx_departments_parent | parent_department_id |
| idx_departments_active | is_active |

---

## 4.2 users

사용자 정보를 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| user_id | varchar(100) | Y |  | Y | 사용자 ID |
| auth_provider | varchar(50) |  |  | Y | LOCAL, OIDC, SAML 등 |
| external_subject | varchar(255) |  |  |  | 외부 인증 제공자 사용자 식별자 |
| user_name | varchar(100) |  |  | Y | 사용자명 |
| email | varchar(255) |  |  | Y | 이메일 |
| password_hash | varchar(255) |  |  |  | PoC 자체 로그인용 비밀번호 hash |
| department_id | varchar(50) |  | departments | Y | 부서 ID |
| user_status | varchar(30) |  |  | Y | ACTIVE, INACTIVE |
| auth_token_version | int |  |  | Y | ADR-0056 기준 access token 무효화 버전 |
| failed_login_count | int |  |  | Y | ADR-0058 기준 연속 로그인 실패 횟수 |
| last_failed_login_at | timestamptz |  |  |  | 마지막 로그인 실패 시각 |
| locked_until | timestamptz |  |  |  | 계정 잠금 만료 시각 |
| password_changed_at | timestamptz |  |  |  | 비밀번호 변경 시각 |
| last_login_at | timestamptz |  |  |  | 최종 로그인 일시 |
| created_at | timestamptz |  |  | Y | 생성일시 |
| updated_at | timestamptz |  |  |  | 수정일시 |

### Constraint

| 제약조건 | 내용 |
|---|---|
| uk_users_email | email unique |
| uk_users_auth_subject | auth_provider, external_subject unique |

### Index

| 인덱스명 | 컬럼 |
|---|---|
| idx_users_locked_until | locked_until |

---

## 4.3 roles

권한 마스터를 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| role_id | varchar(50) | Y |  | Y | 권한 ID |
| role_name | varchar(100) |  |  | Y | 권한명 |
| role_description | text |  |  |  | 권한 설명 |
| is_active | boolean |  |  | Y | 활성 여부 |

### 기본 권한

| role_id | 설명 |
|---|---|
| PRODUCT_DEPARTMENT_USER | 상품부서 담당자 |
| COMPLIANCE_REVIEWER | 준법감시 담당자 |
| STANDARD_MANAGER | 기준 관리자 |
| SYSTEM_ADMIN | 시스템 관리자 |

---

## 4.4 user_roles

사용자와 권한의 매핑 정보를 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| user_role_id | uuid | Y |  | Y | 사용자 권한 매핑 ID |
| user_id | varchar(100) |  | users | Y | 사용자 ID |
| role_id | varchar(50) |  | roles | Y | 권한 ID |
| created_at | timestamptz |  |  | Y | 생성일시 |

### Constraint

| 제약조건 | 내용 |
|---|---|
| uk_user_roles | user_id, role_id unique |

---

## 4.5 refresh_tokens

ADR-0056 기준 refresh token 세션과 폐기 이력을 관리한다. Token 원문은 저장하지 않고 hash만 저장한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| refresh_token_id | uuid | Y |  | Y | refresh token ID |
| user_id | varchar(100) |  | users | Y | 사용자 ID |
| token_hash | varchar(255) |  |  | Y | refresh token hash |
| token_version | int |  |  | Y | 발급 시점 `users.auth_token_version`; 불일치 시 refresh 거부 |
| issued_at | timestamptz |  |  | Y | 발급 일시 |
| expires_at | timestamptz |  |  | Y | 만료 일시 |
| revoked_at | timestamptz |  |  |  | 폐기 일시 |
| revoked_reason | varchar(50) |  |  |  | LOGOUT, ROLE_CHANGED, USER_DISABLED, ROTATED, EXPIRED, ADMIN_REVOKED |
| created_ip | varchar(100) |  |  |  | 발급 IP |
| user_agent | text |  |  |  | 발급 User Agent |
| created_at | timestamptz |  |  | Y | 생성일시 |

### Index

| 인덱스명 | 컬럼 |
|---|---|
| idx_refresh_tokens_user | user_id |
| idx_refresh_tokens_hash | token_hash |
| idx_refresh_tokens_expires_at | expires_at |
| idx_refresh_tokens_active | user_id, revoked_at, expires_at |

---

# 5. 광고물 관리 테이블

## 5.1 advertisements

광고물 기본정보를 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| advertisement_id | varchar(50) | Y |  | Y | 광고물 ID |
| advertisement_name | varchar(300) |  |  | Y | 광고명 |
| product_group | varchar(50) |  |  | Y | 상품군 |
| advertisement_type | varchar(50) |  |  | Y | 광고유형 |
| channel_type | varchar(50) |  |  |  | 광고채널 |
| department_id | varchar(50) |  | departments | Y | 등록 부서 |
| owner_user_id | varchar(100) |  | users | Y | 담당자 |
| review_status | varchar(50) |  |  | Y | 검토 상태 |
| overall_risk_level | varchar(50) |  |  |  | 종합 위험도 |
| latest_review_id | varchar(50) |  | reviews |  | 최근 검토 ID |
| memo | text |  |  |  | 검토 요청 메모 |
| created_at | timestamptz |  |  | Y | 생성일시 |
| created_by | varchar(100) |  | users | Y | 생성자 |
| updated_at | timestamptz |  |  |  | 수정일시 |
| updated_by | varchar(100) |  | users |  | 수정자 |
| is_deleted | boolean |  |  | Y | 삭제 여부 |

### Index

| 인덱스명 | 컬럼 |
|---|---|
| idx_advertisements_status | review_status |
| idx_advertisements_product_type | product_group, advertisement_type |
| idx_advertisements_owner | owner_user_id |
| idx_advertisements_created_at | created_at |
| idx_advertisements_latest_review | latest_review_id |

---

## 5.2 advertisement_files

광고물에 첨부된 파일 정보를 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| file_id | varchar(50) | Y |  | Y | 파일 ID |
| advertisement_id | varchar(50) |  | advertisements | Y | 광고물 ID |
| revision_id | varchar(50) |  | advertisement_revisions |  | 수정본 ID |
| file_type | varchar(50) |  |  | Y | ADVERTISEMENT, PRODUCT_DESCRIPTION, TERMS, ADDITIONAL |
| original_file_name | varchar(500) |  |  | Y | 원본 파일명 |
| storage_provider | varchar(50) |  |  | Y | S3 호환 저장소 provider 식별자 |
| bucket | varchar(255) |  |  | Y | 환경별 private bucket 이름 |
| object_key | text |  |  | Y | 내부 object key. API/로그/감사 응답 노출 금지 |
| mime_type | varchar(100) |  |  | Y | MIME Type |
| file_size | bigint |  |  | Y | 파일 크기 |
| page_count | int |  |  |  | 페이지 수 |
| checksum_sha256 | varchar(64) |  |  | Y | 중복/무결성 확인용 SHA-256 |
| preview_status | varchar(50) |  |  |  | 미리보기 생성 상태 |
| created_at | timestamptz |  |  | Y | 생성일시 |
| created_by | varchar(100) |  | users | Y | 생성자 |

### Index

| 인덱스명 | 컬럼 |
|---|---|
| idx_ad_files_advertisement | advertisement_id |
| idx_ad_files_revision | revision_id |
| idx_ad_files_type | file_type |
| idx_ad_files_checksum | checksum |

---

## 5.3 advertisement_revisions

광고물 수정본 정보를 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| revision_id | varchar(50) | Y |  | Y | 수정본 ID |
| advertisement_id | varchar(50) |  | advertisements | Y | 광고물 ID |
| revision_no | int |  |  | Y | 수정 회차 |
| base_review_id | varchar(50) |  | reviews |  | 기준 검토 ID |
| revision_memo | text |  |  |  | 수정 사유 |
| created_at | timestamptz |  |  | Y | 생성일시 |
| created_by | varchar(100) |  | users | Y | 생성자 |

### Constraint

| 제약조건 | 내용 |
|---|---|
| uk_ad_revision_no | advertisement_id, revision_no unique |

---

# 6. AI 검토 테이블

## 6.1 reviews

광고물별 AI 검토 요청과 결과 요약을 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| review_id | varchar(50) | Y |  | Y | 검토 ID |
| advertisement_id | varchar(50) |  | advertisements | Y | 광고물 ID |
| revision_id | varchar(50) |  | advertisement_revisions |  | 수정본 ID |
| review_round | int |  |  | Y | 검토 회차 |
| review_status | varchar(50) |  |  | Y | 검토 상태 |
| overall_risk_level | varchar(50) |  |  |  | 종합 위험도 |
| standard_effective_date | date |  |  |  | 기준 적용일 |
| applied_standard_version_ids | jsonb |  |  | Y | 검토에 고정 적용한 기준자료 버전 ID 목록 |
| review_types | jsonb |  |  | Y | 요청 검토유형 목록 |
| include_suggestion | boolean |  |  | Y | 문구 추천 포함 여부 |
| include_opinion_draft | boolean |  |  | Y | 의견 초안 포함 여부 |
| request_memo | text |  |  |  | 검토 요청 메모 |
| requested_at | timestamptz |  |  | Y | 요청일시 |
| requested_by | varchar(100) |  | users | Y | 요청자 |
| completed_at | timestamptz |  |  |  | 완료일시 |
| failed_reason | text |  |  |  | 실패 사유 |
| created_at | timestamptz |  |  | Y | 생성일시 |
| updated_at | timestamptz |  |  |  | 수정일시 |

### Index

| 인덱스명 | 컬럼 |
|---|---|
| idx_reviews_advertisement | advertisement_id |
| idx_reviews_revision | revision_id |
| idx_reviews_status | review_status |
| idx_reviews_requested_at | requested_at |

---

## 6.2 review_jobs

비동기 AI 분석 Job 정보를 관리한다. Redis Queue는 작업 전달에 사용하고, 진행 상태 조회와 이력의 원천은 `review_jobs`, `review_steps`로 둔다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| job_id | varchar(50) | Y |  | Y | Job ID |
| review_id | varchar(50) |  | reviews | Y | 검토 ID |
| job_type | varchar(50) |  |  | Y | REVIEW_ANALYSIS, RE_REVIEW 등 |
| job_status | varchar(50) |  |  | Y | PENDING, RUNNING, RETRY_PENDING, STALE, COMPLETED, FAILED, FAILED_FINAL, CANCELED |
| queue_name | varchar(100) |  |  | Y | Redis Queue 이름 |
| progress_rate | numeric(5,2) |  |  |  | 진행률 |
| current_step | varchar(100) |  |  |  | 현재 단계 |
| retry_count | int |  |  | Y | 재시도 횟수 |
| max_retries | int |  |  | Y | 최대 재시도 횟수 |
| next_retry_at | timestamptz |  |  |  | 다음 재시도 예정 시각 |
| timeout_at | timestamptz |  |  |  | 전체 Job timeout 예정 시각 |
| enqueued_at | timestamptz |  |  |  | Queue 등록 시각 |
| locked_by | varchar(100) |  |  |  | 처리 중인 worker 식별자 |
| locked_at | timestamptz |  |  |  | worker lock 획득 시각 |
| heartbeat_at | timestamptz |  |  |  | worker heartbeat 시각 |
| started_at | timestamptz |  |  |  | 시작일시 |
| completed_at | timestamptz |  |  |  | 완료일시 |
| failed_reason_code | varchar(100) |  |  |  | 실패 사유 코드 |
| failed_reason | text |  |  |  | 실패 사유 |
| is_retryable | boolean |  |  | Y | 재시도 가능 여부 |
| dead_lettered_at | timestamptz |  |  |  | 최종 실패/dead-letter 전환 시각 |
| created_at | timestamptz |  |  | Y | 생성일시 |

### Index

| 인덱스명 | 컬럼 |
|---|---|
| idx_review_jobs_status_retry | job_status, next_retry_at |
| idx_review_jobs_heartbeat | job_status, heartbeat_at |

Redis Queue 메시지에는 `job_id`, `review_id`, `job_type` 등 최소 식별자만 포함한다. 광고 원문, OCR 결과, 기준자료 본문, 고객사 민감정보는 Redis 메시지에 저장하지 않는다.

AI 분석 Job timeout, retry, dead-letter 기준은 ADR-0059를 따른다. 전체 Job timeout 기본값은 30분, 최대 retry는 3회, backoff는 1분/3분/10분이다.

---

## 6.3 review_steps

AI 분석 단계별 진행 상태를 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| review_step_id | uuid | Y |  | Y | 검토 단계 ID |
| review_id | varchar(50) |  | reviews | Y | 검토 ID |
| job_id | varchar(50) |  | review_jobs | Y | Job ID |
| step_code | varchar(100) |  |  | Y | FILE_PREPROCESSING, OCR_EXTRACTION 등 |
| step_name | varchar(200) |  |  | Y | 단계명 |
| step_status | varchar(50) |  |  | Y | PENDING, RUNNING, RETRY_PENDING, COMPLETED, FAILED, SKIPPED |
| sequence_no | int |  |  | Y | 실행 순서 |
| started_at | timestamptz |  |  |  | 시작일시 |
| timeout_at | timestamptz |  |  |  | 단계별 timeout 예정 시각 |
| timeout_seconds | int |  |  |  | 단계별 timeout 설정값 |
| completed_at | timestamptz |  |  |  | 완료일시 |
| failed_reason_code | varchar(100) |  |  |  | 실패 사유 코드 |
| error_message | text |  |  |  | 오류 메시지 |

### Index

| 인덱스명 | 컬럼 |
|---|---|
| idx_review_steps_review | review_id |
| idx_review_steps_job | job_id |

---

# 7. OCR 및 레이아웃 분석 테이블

OCR 및 레이아웃 분석 테이블은 ADR-0065 기준 `NormalizedDocument` v1의 영속화 결과로 해석한다. Parser/OCR raw output은 업무 로직이 직접 참조하지 않고 ADR-0067 기준 Object Storage raw artifact와 `parser_artifacts` metadata 참조로 보존한다.

## 7.1 ocr_text_blocks

OCR/VLM/parser가 생성한 `NormalizedDocument.textBlocks`와 좌표/offset 정보를 관리한다. PoC에서는 기존 테이블명을 유지하되, HWP/HWPX parser 텍스트 블록도 이 테이블에 저장한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| ocr_block_id | varchar(50) | Y |  | Y | OCR 블록 ID |
| review_id | varchar(50) |  | reviews | Y | 검토 ID |
| file_id | varchar(50) |  | advertisement_files | Y | 파일 ID |
| page_no | int |  |  |  | 페이지 번호. HWP/HWPX 구조 기반 텍스트는 null 허용 |
| block_text | text |  |  | Y | parser 원문에 가까운 추출 텍스트(rawText) |
| normalized_text | text |  |  |  | 화면 표시, 검색, 하이라이트용 정규화 텍스트 |
| text_path | varchar(500) |  |  |  | 문서 구조 내 위치. 예: body/section[1]/paragraph[3] |
| text_block_type | varchar(50) |  |  |  | PARAGRAPH, TABLE_CELL, TITLE, FOOTNOTE, NOTICE 등 |
| raw_start_offset | int |  |  |  | parser 원문 기준 시작 offset |
| raw_end_offset | int |  |  |  | parser 원문 기준 종료 offset |
| normalized_start_offset | int |  |  |  | normalized_text 기준 시작 offset |
| normalized_end_offset | int |  |  |  | normalized_text 기준 종료 offset |
| parser_name | varchar(100) |  |  |  | 사용 parser/OCR adapter 이름 |
| parser_version | varchar(100) |  |  |  | parser/OCR adapter 버전 |
| parser_rule_version | varchar(100) |  |  |  | 텍스트 정규화 또는 구조 추출 rule set 버전 |
| ir_version | varchar(50) |  |  |  | Text IR 스키마 버전 |
| confidence_score | numeric(5,4) |  |  |  | OCR/parser 신뢰도 |
| confidence_status | varchar(50) |  |  |  | READABLE, LOW_CONFIDENCE, UNREADABLE |
| confidence_policy_version | varchar(100) |  |  |  | ADR-0053 기준 신뢰도 임계값 정책 버전 |
| source_width | numeric(12,4) |  |  |  | 원본 페이지 또는 이미지 너비 |
| source_height | numeric(12,4) |  |  |  | 원본 페이지 또는 이미지 높이 |
| source_unit | varchar(20) |  |  |  | 원본 좌표 단위. px, pt 등 |
| x | numeric(12,4) |  |  |  | 원본 기준 좌표 X |
| y | numeric(12,4) |  |  |  | 원본 기준 좌표 Y |
| width | numeric(12,4) |  |  |  | 원본 기준 너비 |
| height | numeric(12,4) |  |  |  | 원본 기준 높이 |
| normalized_x | numeric(8,7) |  |  |  | 정규화 좌표 X |
| normalized_y | numeric(8,7) |  |  |  | 정규화 좌표 Y |
| normalized_width | numeric(8,7) |  |  |  | 정규화 너비 |
| normalized_height | numeric(8,7) |  |  |  | 정규화 높이 |
| rotation | numeric(6,2) |  |  |  | 원본 페이지 회전값 |
| coordinate_confidence | numeric(5,4) |  |  |  | 좌표 추출 신뢰도 |
| raw_artifact_id | varchar(50) |  | parser_artifacts |  | ADR-0067 기준 raw artifact 참조 ID |
| created_at | timestamptz |  |  | Y | 생성일시 |

### Index

| 인덱스명 | 컬럼 |
|---|---|
| idx_ocr_blocks_review | review_id |
| idx_ocr_blocks_file_page | file_id, page_no |
| idx_ocr_blocks_text_gin | normalized_text |
| idx_ocr_blocks_text_path | file_id, text_path |

---

## 7.2 parser_artifacts

Parser/OCR adapter의 raw output과 중간 산출물에 대한 Object Storage 참조 메타데이터를 관리한다. 본문 JSON은 DB에 저장하지 않고 ADR-0067 기준 `parser-artifacts` bucket에 저장한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| raw_artifact_id | varchar(50) | Y |  | Y | raw artifact ID |
| review_id | varchar(50) |  | reviews | Y | 검토 ID |
| file_id | varchar(50) |  | advertisement_files | Y | 파일 ID |
| review_step_id | varchar(50) |  | review_steps |  | 생성한 처리 단계 ID |
| artifact_type | varchar(50) |  |  | Y | OCR_RAW, PARSER_RAW, LAYOUT_RAW, NORMALIZED_DOCUMENT, WARNING_DETAIL |
| storage_provider | varchar(50) |  |  | Y | minio, s3, s3-compatible |
| bucket | varchar(100) |  |  | Y | parser-artifacts |
| object_key | text |  |  | Y | Object Storage key |
| checksum_sha256 | varchar(128) |  |  | Y | 무결성 검증용 checksum |
| content_type | varchar(100) |  |  | Y | application/json 등 |
| file_size | bigint |  |  | Y | object 크기 |
| parser_name | varchar(100) |  |  |  | 사용 parser/OCR adapter 이름 |
| parser_version | varchar(100) |  |  |  | parser/OCR adapter 버전 |
| parser_rule_version | varchar(100) |  |  |  | 정규화 또는 구조 추출 rule set 버전 |
| ir_version | varchar(50) |  |  |  | 관련 IR/schema 버전 |
| attempt_no | int |  |  |  | ADR-0073 기준 같은 파일/단계 내 Parser/OCR 시도 순번 |
| is_primary_attempt | boolean |  |  |  | 1차 엔진 시도 여부 |
| is_selected_output | boolean |  |  |  | ReviewPipeline에 전달된 최종 산출물 여부 |
| rerun_reason_code | varchar(100) |  |  |  | LOW_CONFIDENCE, STRUCTURE_FAILED, TABLE_EXTRACTION_MISSING 등 |
| rerun_reason_message | text |  |  |  | 보조 엔진 재처리 또는 미채택 사유 |
| confidence_score | numeric(5,4) |  |  |  | 해당 시도 산출물의 대표 confidence |
| confidence_status | varchar(50) |  |  |  | ADR-0053 기준 confidence status |
| retention_until | timestamptz |  |  |  | 정리 가능 기준일 |
| created_at | timestamptz |  |  | Y | 생성일시 |
| created_by | varchar(100) |  | users |  | 생성자 또는 service account |

### Index

| 인덱스명 | 컬럼 |
|---|---|
| idx_parser_artifacts_review | review_id |
| idx_parser_artifacts_file | file_id |
| idx_parser_artifacts_step | review_step_id |
| idx_parser_artifacts_selected | review_step_id, is_selected_output |
| idx_parser_artifacts_retention | retention_until |

Parser/OCR 품질 미달 시 보조 엔진 재처리와 최종 산출물 선택 기준은 ADR-0073을 따른다. 정책 사유가 있고 허용·구성된 보조 adapter만 실행하며 1차와 보조 시도 각각의 engine, `attempt_no`, `is_primary_attempt`, `rerun_reason_code`, confidence, raw artifact 참조와 `is_selected_output`을 `parser_artifacts`에 기록한다. HWP/HWPX는 ADR-0079에 따라 rhwp 텍스트, document-processor 구조와 aligner 중간 artifact를 미채택 구성요소 artifact로 보존하고, `parser_name=hwp-hybrid`인 병합 `NORMALIZED_DOCUMENT`만 선택 산출물로 표시한다. `uk_parser_artifacts_selected_step`으로 처리 단계마다 선택 artifact가 최대 하나임을 보장하고, worker는 정확히 하나를 선택한 뒤 `ocr_text_blocks`, `layout_blocks`, `annotations`와 후속 ReviewPipeline에 그 `NormalizedDocument`만 반영한다. 미채택 시도와 구성요소 artifact는 `parser_artifacts` metadata와 raw artifact로만 보존한다.

---

## 7.3 layout_blocks

광고 화면의 `NormalizedDocument.layoutBlocks` 분석 결과를 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| layout_block_id | varchar(50) | Y |  | Y | 레이아웃 블록 ID |
| review_id | varchar(50) |  | reviews | Y | 검토 ID |
| file_id | varchar(50) |  | advertisement_files | Y | 파일 ID |
| page_no | int |  |  | Y | 페이지 번호 |
| block_type | varchar(50) |  |  | Y | TITLE, BODY, FOOTNOTE, NOTICE, BUTTON, BANNER |
| related_ocr_block_ids | jsonb |  |  |  | 연결된 OCR 블록 ID 목록 |
| confidence_score | numeric(5,4) |  |  |  | 분류 신뢰도 |
| confidence_status | varchar(50) |  |  |  | STRUCTURED, PARTIALLY_STRUCTURED, UNSTRUCTURED |
| confidence_policy_version | varchar(100) |  |  |  | ADR-0053 기준 신뢰도 임계값 정책 버전 |
| source_width | numeric(12,4) |  |  |  | 원본 페이지 또는 이미지 너비 |
| source_height | numeric(12,4) |  |  |  | 원본 페이지 또는 이미지 높이 |
| source_unit | varchar(20) |  |  |  | 원본 좌표 단위. px, pt 등 |
| x | numeric(12,4) |  |  |  | 원본 기준 좌표 X |
| y | numeric(12,4) |  |  |  | 원본 기준 좌표 Y |
| width | numeric(12,4) |  |  |  | 원본 기준 너비 |
| height | numeric(12,4) |  |  |  | 원본 기준 높이 |
| normalized_x | numeric(8,7) |  |  |  | 정규화 좌표 X |
| normalized_y | numeric(8,7) |  |  |  | 정규화 좌표 Y |
| normalized_width | numeric(8,7) |  |  |  | 정규화 너비 |
| normalized_height | numeric(8,7) |  |  |  | 정규화 높이 |
| rotation | numeric(6,2) |  |  |  | 원본 페이지 회전값 |
| coordinate_confidence | numeric(5,4) |  |  |  | 좌표 추출 신뢰도 |
| style_json | jsonb |  |  |  | 글자 크기, 색상, 굵기 등 스타일 정보 |
| created_at | timestamptz |  |  | Y | 생성일시 |

---

# 8. 검토 결과 테이블

## 8.1 review_items

AI 검토 항목별 판정 결과를 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| review_item_id | varchar(50) | Y |  | Y | 검토 항목 ID |
| review_id | varchar(50) |  | reviews | Y | 검토 ID |
| review_type | varchar(50) |  |  | Y | 검토유형 |
| target_text | text |  |  |  | 검토 대상 문구 |
| normalized_target_text | text |  |  |  | 정규화 문구 |
| ocr_block_id | varchar(50) |  | ocr_text_blocks |  | OCR 블록 ID |
| layout_block_id | varchar(50) |  | layout_blocks |  | 레이아웃 블록 ID |
| result_status | varchar(50) |  |  | Y | 판정 결과 |
| risk_level | varchar(50) |  |  | Y | 위험도 |
| risk_policy_version | varchar(100) |  |  | Y | ADR-0068 기준 위험도 산정 정책 버전 |
| risk_reason_codes | jsonb |  |  | Y | ADR-0068 기준 위험도 산정 사유 코드 배열 |
| risk_score_detail | jsonb |  |  | Y | Rule/RAG/LLM/confidence 입력과 최종 결정 상세 |
| evidence_status | varchar(50) |  |  | Y | CONNECTED, NOT_REQUIRED, INSUFFICIENT, SEARCH_UNAVAILABLE |
| evidence_failure_code | varchar(100) |  |  |  | 검색 장애일 때만 RAG_SEARCH_UNAVAILABLE 또는 RAG_SEARCH_FAILED |
| reason | text |  |  | Y | 판단 사유 |
| recommendation | text |  |  |  | 수정 권고 |
| engine_type | varchar(50) |  |  | Y | RULE, RAG, MULTIMODAL, LLM |
| engine_version | varchar(100) |  |  | Y | 결과를 생성한 rule/search/structured schema 버전 |
| confidence_score | numeric(5,4) |  |  |  | 판정 신뢰도 |
| page_no | int |  |  |  | 페이지 번호 |
| result_json | jsonb |  |  | Y | 엔진별 상세 결과. 위험도 계약 원천은 risk_* 필드 |
| created_at | timestamptz |  |  | Y | 생성일시 |

### Index

| 인덱스명 | 컬럼 |
|---|---|
| idx_review_items_review | review_id |
| idx_review_items_type | review_type |
| idx_review_items_status | result_status |
| idx_review_items_risk | risk_level |
| idx_review_items_ocr_block | ocr_block_id |
| idx_review_items_evidence_status | evidence_status |

`risk_reason_codes`는 PoC 초기에는 필터 인덱스 대상에서 제외한다. 사유 코드별 통계 조회가 필요해지면 GIN 인덱스를 별도 migration으로 추가한다.

---

## 8.2 review_item_evidences

검토 항목과 근거 자료 간 매핑을 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| review_item_evidence_id | uuid | Y |  | Y | 검토 근거 매핑 ID |
| review_item_id | varchar(50) |  | review_items | Y | 검토 항목 ID |
| evidence_id | varchar(50) |  | evidences | Y | 근거 ID |
| standard_version_id | varchar(50) |  | standard_versions | Y | 검토에 사용한 기준자료 버전 ID |
| evidence_chunk_id | varchar(50) |  | evidence_chunks |  | 근거 Chunk ID |
| matched_text | text |  |  |  | 매칭된 근거 문구 |
| relevance_score | numeric(5,4) |  |  | Y | 관련도 점수. 0.0~1.0 |
| rank_no | int |  |  | Y | 검토 항목 저장 근거 순위. ADR-0043 기준 1~5 |
| match_source | varchar(50) |  |  | Y | KEYWORD, VECTOR, HYBRID, RULE_METADATA |
| score_detail | jsonb |  |  | Y | keyword/vector/metadata/rule 점수 상세 |
| created_at | timestamptz |  |  | Y | 생성일시 |

### Constraint

| 제약조건 | 내용 |
|---|---|
| uk_review_item_evidence | review_item_id, evidence_id, evidence_chunk_id unique |
| ck_item_evidence_rank | rank_no 1~5 |

### Index

| 인덱스명 | 컬럼 |
|---|---|
| idx_review_item_evidences_item_rank | review_item_id, rank_no |
| idx_review_item_evidences_chunk | evidence_chunk_id |

---

## 8.3 annotations

광고 화면 또는 HWP/HWPX 텍스트 뷰에 표시할 문제 영역 정보를 관리한다. 위치를 특정하지 못한 검토 항목도 목록/상세 표시를 위해 `LIST_ONLY` 또는 `UNAVAILABLE` 상태로 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| annotation_id | varchar(50) | Y |  | Y | Annotation ID |
| review_id | varchar(50) |  | reviews | Y | 검토 ID |
| review_item_id | varchar(50) |  | review_items | Y | 검토 항목 ID |
| file_id | varchar(50) |  | advertisement_files | Y | 파일 ID |
| page_no | int |  |  |  | 페이지 번호. 위치 미확정 또는 텍스트 기반 표시 시 null 허용 |
| text_block_id | varchar(50) |  | ocr_text_blocks |  | TEXT_HIGHLIGHT 대상 텍스트 IR 블록 ID |
| text_path | varchar(500) |  |  |  | 문서 구조 내 위치 |
| annotation_display_mode | varchar(50) |  |  | Y | BOX, TEXT_HIGHLIGHT, LIST_ONLY, UNAVAILABLE |
| annotation_status | varchar(50) |  |  | Y | LOCATED, PARTIALLY_LOCATED, NOT_LOCATED, LOW_CONFIDENCE, DOCUMENT_LEVEL_ISSUE |
| location_confidence | numeric(5,4) |  |  |  | 위치 식별 신뢰도. 0.0~1.0 |
| confidence_policy_version | varchar(100) |  |  | Y | ADR-0053 기준 신뢰도 임계값 정책 버전 |
| display_reason | varchar(100) |  |  | Y | MATCHED_BOX, MATCHED_TEXT, PARTIAL_TEXT_MATCH, NO_TEXT_SPAN 등 |
| annotation_type | varchar(50) |  |  |  | 세부 표시 유형. PoC에서는 `annotation_display_mode` 기준 사용 |
| source_width | numeric(12,4) |  |  |  | 원본 페이지 또는 이미지 너비 |
| source_height | numeric(12,4) |  |  |  | 원본 페이지 또는 이미지 높이 |
| source_unit | varchar(20) |  |  |  | 원본 좌표 단위. px, pt 등 |
| x | numeric(12,4) |  |  |  | 원본 기준 좌표 X |
| y | numeric(12,4) |  |  |  | 원본 기준 좌표 Y |
| width | numeric(12,4) |  |  |  | 원본 기준 너비 |
| height | numeric(12,4) |  |  |  | 원본 기준 높이 |
| normalized_x | numeric(8,7) |  |  |  | 정규화 좌표 X |
| normalized_y | numeric(8,7) |  |  |  | 정규화 좌표 Y |
| normalized_width | numeric(8,7) |  |  |  | 정규화 너비 |
| normalized_height | numeric(8,7) |  |  |  | 정규화 높이 |
| rotation | numeric(6,2) |  |  |  | 원본 페이지 회전값 |
| coordinate_confidence | numeric(5,4) |  |  |  | 좌표 추출 신뢰도 |
| raw_start_offset | int |  |  |  | parser 원문 기준 시작 offset |
| raw_end_offset | int |  |  |  | parser 원문 기준 종료 offset |
| normalized_start_offset | int |  |  |  | UI 하이라이트 기준 시작 offset |
| normalized_end_offset | int |  |  |  | UI 하이라이트 기준 종료 offset |
| matched_text | text |  |  |  | 실제 매칭된 문구 |
| risk_level | varchar(50) |  |  | Y | 위험도 |
| review_type | varchar(50) |  |  | Y | 검토 유형 |
| display_order | int |  |  | Y | 표시 순서. 기본 0 |
| created_at | timestamptz |  |  | Y | 생성일시 |

### Index

| 인덱스명 | 컬럼 |
|---|---|
| idx_annotations_review | review_id |
| idx_annotations_file_page | file_id, page_no |
| idx_annotations_item | review_item_id |
| idx_annotations_type_risk | review_type, risk_level |
| idx_annotations_display_status | annotation_display_mode, annotation_status |
| idx_annotations_text_block | text_block_id |

---

# 9. 기준자료 및 RAG 지식베이스 테이블

## 9.1 standards

기준자료의 마스터 정보를 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| standard_id | varchar(50) | Y |  | Y | 기준자료 ID |
| title | varchar(500) |  |  | Y | 기준자료명 |
| evidence_type | varchar(50) |  |  | Y | LAW, REGULATION, INTERNAL_STANDARD, CASE, TEMPLATE |
| product_group | varchar(50) |  |  |  | 적용 상품군 |
| advertisement_type | varchar(50) |  |  |  | 적용 광고유형 |
| rule_type | varchar(50) |  |  | Y | REQUIRED, PROHIBITED, RECOMMENDED, REFERENCE |
| importance | varchar(50) |  |  |  | HIGH, MEDIUM, LOW |
| effective_date | date |  |  |  | 적용일 |
| expired_date | date |  |  |  | 만료일 |
| metadata_json | jsonb |  |  |  | ADR-0050 기준 유형별 확장 메타데이터 |
| current_version | varchar(30) |  |  | Y | 현재 버전 |
| is_active | boolean |  |  | Y | 활성 여부 |
| created_at | timestamptz |  |  | Y | 생성일시 |
| created_by | varchar(100) |  | users | Y | 생성자 |
| updated_at | timestamptz |  |  |  | 수정일시 |
| updated_by | varchar(100) |  | users |  | 수정자 |

### Index

| 인덱스명 | 컬럼 |
|---|---|
| idx_standards_type | evidence_type |
| idx_standards_product_ad_type | product_group, advertisement_type |
| idx_standards_rule_type | rule_type |
| idx_standards_effective_date | effective_date |
| idx_standards_active | is_active |

---

## 9.2 standard_versions

기준자료 버전별 본문과 변경 이력을 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| standard_version_id | varchar(50) | Y |  | Y | 기준자료 버전 ID |
| standard_id | varchar(50) |  | standards | Y | 기준자료 ID |
| version | varchar(30) |  |  | Y | 버전 |
| title | varchar(500) |  |  | Y | 기준자료명 |
| content | text |  |  | Y | 기준 내용 |
| source_file_id | varchar(50) |  | advertisement_files |  | 원문 파일 ID |
| change_reason | text |  |  |  | 변경 사유 |
| effective_date | date |  |  |  | 적용일 |
| expired_date | date |  |  |  | 적용 종료일 |
| metadata_json | jsonb |  |  |  | 해당 버전에 적용된 유형별 메타데이터 |
| created_at | timestamptz |  |  | Y | 생성일시 |
| created_by | varchar(100) |  | users | Y | 생성자 |

### Constraint

| 제약조건 | 내용 |
|---|---|
| uk_standard_versions | standard_id, version unique |

---

## 9.3 evidences

검토 결과에 연결되는 근거 단위를 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| evidence_id | varchar(50) | Y |  | Y | 근거 ID |
| standard_id | varchar(50) |  | standards | Y | 기준자료 ID |
| standard_version_id | varchar(50) |  | standard_versions | Y | 기준자료 버전 ID |
| evidence_type | varchar(50) |  |  | Y | 근거 유형 |
| title | varchar(500) |  |  | Y | 근거 제목 |
| article_no | varchar(100) |  |  |  | 조문번호/항목번호 |
| content | text |  |  | Y | 근거 내용 |
| content_summary | text |  |  |  | 요약 내용 |
| product_group | varchar(50) |  |  |  | 상품군 |
| advertisement_type | varchar(50) |  |  |  | 광고유형 |
| rule_type | varchar(50) |  |  | Y | 필수/금지/권고/참고 |
| importance | varchar(50) |  |  |  | 중요도 |
| effective_date | date |  |  |  | 적용일 |
| expired_date | date |  |  |  | 적용 종료일 |
| metadata_json | jsonb |  |  |  | 검색/필터/표시용 유형별 메타데이터 |
| is_active | boolean |  |  | Y | 활성 여부 |
| created_at | timestamptz |  |  | Y | 생성일시 |

### Index

| 인덱스명 | 컬럼 |
|---|---|
| idx_evidences_standard | standard_id |
| idx_evidences_type | evidence_type |
| idx_evidences_rule | rule_type |
| idx_evidences_product_ad_type | product_group, advertisement_type |
| idx_evidences_article_no | article_no |

---

## 9.4 evidence_chunks

RAG 검색을 위한 기준자료 Chunk 정보를 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| evidence_chunk_id | varchar(50) | Y |  | Y | 근거 Chunk ID |
| evidence_id | varchar(50) |  | evidences | Y | 근거 ID |
| standard_id | varchar(50) |  | standards | Y | 기준자료 ID |
| standard_version_id | varchar(50) |  | standard_versions | Y | 기준자료 버전 ID |
| chunk_no | int |  |  | Y | Chunk 순번 |
| chunk_text | text |  |  | Y | Chunk 본문 |
| token_count | int |  |  |  | 토큰 수 |
| section_path | varchar(500) |  |  |  | 장/절/조/항/호 또는 제목 경로 |
| article_no | varchar(100) |  |  |  | 조문번호 또는 항목번호 |
| page_no | int |  |  |  | 원문 페이지 번호 |
| source_span | jsonb |  |  |  | 원문 내 문자 범위 또는 위치 |
| structure_confidence | numeric(5,4) |  |  |  | 구조 인식 신뢰도 |
| parser_rule_version | varchar(100) |  |  |  | 구조 인식 parser rule version |
| chunking_policy_version | varchar(100) |  |  |  | Chunking 정책 버전 |
| qdrant_collection | varchar(100) |  |  |  | Qdrant Collection 명 |
| qdrant_point_id | varchar(100) |  |  |  | Qdrant Point ID |
| qdrant_index_status | varchar(50) |  |  |  | ADR-0070 기준 PENDING, INDEXING, ACTIVE, FAILED, EXCLUDED, DELETED |
| qdrant_indexed_at | timestamptz |  |  |  | Qdrant 색인 완료 시각 |
| qdrant_index_error_code | varchar(100) |  |  |  | Qdrant 색인 실패 코드 |
| qdrant_index_error_message | text |  |  |  | Qdrant 색인 실패 메시지 |
| opensearch_index | varchar(100) |  |  |  | OpenSearch Index 명 |
| opensearch_doc_id | varchar(100) |  |  |  | OpenSearch Document ID |
| opensearch_index_status | varchar(50) |  |  |  | ADR-0070 기준 PENDING, INDEXING, ACTIVE, FAILED, EXCLUDED, DELETED |
| opensearch_indexed_at | timestamptz |  |  |  | OpenSearch 색인 완료 시각 |
| opensearch_index_error_code | varchar(100) |  |  |  | OpenSearch 색인 실패 코드 |
| opensearch_index_error_message | text |  |  |  | OpenSearch 색인 실패 메시지 |
| embedding_model | varchar(100) |  |  |  | 임베딩 모델명 |
| search_schema_version | varchar(100) |  |  |  | ADR-0071 기준 검색 인덱스 schema version |
| opensearch_analyzer_version | varchar(100) |  |  |  | ADR-0071 기준 OpenSearch analyzer version |
| synonym_version | varchar(100) |  |  |  | ADR-0071 기준 synonym 사전 version |
| metadata | jsonb |  |  |  | 검색용 메타데이터 |
| created_at | timestamptz |  |  | Y | 생성일시 |

### Index

| 인덱스명 | 컬럼 |
|---|---|
| idx_evidence_chunks_evidence | evidence_id |
| idx_evidence_chunks_standard_version | standard_version_id |
| idx_evidence_chunks_qdrant | qdrant_collection, qdrant_point_id |
| idx_evidence_chunks_opensearch | opensearch_index, opensearch_doc_id |
| idx_evidence_chunks_index_status | qdrant_index_status, opensearch_index_status |

Qdrant point ID와 OpenSearch document ID는 ADR-0070 기준 deterministic ID를 사용한다. Qdrant payload와 OpenSearch document의 표준 필드, analyzer, synonym, highlight 기준은 ADR-0071을 따른다. 검색 쿼리는 `ACTIVE` 상태, 기준일 유효성, 활성 기준자료 조건을 함께 적용한다.

---

## 9.5 standard_reindex_jobs

기준자료 재색인 요청과 처리 상태를 관리한다. 재색인 API와 Job 상태 조회는 ADR-0069를 따른다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| reindex_job_id | varchar(50) | Y |  | Y | 기준자료 재색인 Job ID |
| standard_id | varchar(50) |  | standards | Y | 기준자료 ID |
| standard_version_id | varchar(50) |  | standard_versions | Y | 기준자료 버전 ID |
| reindex_scope | varchar(50) |  |  | Y | INDEX_ONLY, CHUNK_AND_INDEX, KEYWORD_ONLY, VECTOR_ONLY |
| job_status | varchar(50) |  |  | Y | QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELED |
| reason | text |  |  |  | 재색인 사유. prod(main)은 필수 |
| target_indexes | jsonb |  |  |  | QDRANT, OPENSEARCH 등 대상 인덱스 목록 |
| parser_rule_version | varchar(100) |  |  |  | 구조 인식 parser rule version |
| chunking_policy_version | varchar(100) |  |  |  | Chunking 정책 버전 |
| embedding_model | varchar(100) |  |  |  | 임베딩 모델명 |
| search_schema_version | varchar(100) |  |  |  | 검색 인덱스 schema version |
| opensearch_analyzer_version | varchar(100) |  |  |  | OpenSearch analyzer version |
| synonym_version | varchar(100) |  |  |  | synonym 사전 version |
| qdrant_collection | varchar(100) |  |  |  | 대상 Qdrant collection |
| opensearch_index | varchar(100) |  |  |  | 대상 OpenSearch index |
| qdrant_status | varchar(50) |  |  |  | Qdrant 독립 처리 상태 |
| opensearch_status | varchar(50) |  |  |  | OpenSearch 독립 처리 상태 |
| created_chunk_count | int |  |  |  | 생성 또는 재생성된 Chunk 수 |
| indexed_chunk_count | int |  |  |  | 인덱싱 완료 Chunk 수 |
| failed_reason_code | varchar(100) |  |  |  | 실패 사유 코드 |
| failed_reason_message | text |  |  |  | 실패 메시지 |
| requested_by | varchar(100) |  | users | Y | 요청자 |
| requested_at | timestamptz |  |  | Y | 요청일시 |
| started_at | timestamptz |  |  |  | 시작일시 |
| completed_at | timestamptz |  |  |  | 완료일시 |

### Index

| 인덱스명 | 컬럼 |
|---|---|
| idx_standard_reindex_jobs_standard | standard_id, standard_version_id |
| idx_standard_reindex_jobs_status | job_status |
| idx_standard_reindex_jobs_requested_at | requested_at |

---

## 9.6 기준자료 유형별 메타데이터 기준

기준자료 유형별 메타데이터 및 관리 단위는 [ADR-0050: 기준자료 유형별 메타데이터 및 관리 단위 정책](adr/ADR-0050-reference-metadata-policy.md)을 따른다.

| 자료 유형 | evidence_type | 필수 메타데이터 |
| --- | --- | --- |
| 법령/감독규정/고시 | `LAW`, `REGULATION` | 기관, 문서명, 조문번호, 시행일, 개정일, 원문 출처 |
| 내부기준/내규 | `INTERNAL_STANDARD` | 소관 부서, 문서명, 장/절/조 경로, 시행일, 버전, 적용 상품군 |
| 가이드라인/지침/매뉴얼 | `GUIDELINE`, `MANUAL` | 문서명, 문서유형, 섹션 경로, 적용 상품군, 광고유형, 버전 |
| 심의사례 | `REVIEW_CASE` | 사례번호, 상품군, 광고유형, 판단유형, 지적사항, 조치결과, 판단일 |
| 문구 템플릿 | `TEMPLATE` | 문구유형, 필수/권고/금지 여부, 상품군, 광고유형, 적용 조건 |
| 상품 기준자료 | `PRODUCT_STANDARD` | 상품명, 상품군, 금리/수수료/조건 항목, 적용일, 파일 버전 |

검색, 필터, 판단에 자주 쓰는 값은 명시 컬럼으로 유지하고, 자료 유형별 확장값은 `metadata_json`에 저장한다. 기준자료 등록/수정 API는 `evidence_type`별 필수 메타데이터 누락을 검증해야 한다.

---

# 10. 문구 추천 테이블

## 10.1 suggestions

AI가 생성한 보완 문구 및 대체 문구를 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| suggestion_id | varchar(50) | Y |  | Y | 추천 문구 ID |
| review_id | varchar(50) |  | reviews | Y | 검토 ID |
| review_item_id | varchar(50) |  | review_items | Y | 검토 항목 ID |
| original_text | text |  |  | Y | 원문 문구 |
| suggested_text | text |  |  | Y | 추천 문구 |
| suggestion_reason | text |  |  |  | 추천 사유 |
| suggestion_type | varchar(50) |  |  | Y | ALTERNATIVE, ADDITIONAL_NOTICE, SOFTENING |
| evidence_ids | jsonb |  |  |  | 관련 근거 ID 목록 |
| decision_status | varchar(50) |  |  | Y | 최신 판단 상태. PENDING, ACCEPTED, REJECTED, MODIFIED_AND_USED |
| created_at | timestamptz |  |  | Y | 생성일시 |

### Index

| 인덱스명 | 컬럼 |
|---|---|
| idx_suggestions_review | review_id |
| idx_suggestions_item | review_item_id |
| idx_suggestions_decision | decision_status |

---

## 10.2 suggestion_decisions

담당자의 추천 문구 채택 여부와 최종 사용 문구를 이력으로 관리한다. 동일 추천 문구에 대한 판단이 변경되면 기존 row를 갱신하지 않고 새 row를 추가하며, `suggestions.decision_status`에는 최신 상태만 반영한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| suggestion_decision_id | uuid | Y |  | Y | 추천 판단 ID |
| suggestion_id | varchar(50) |  | suggestions | Y | 추천 문구 ID |
| decision_status | varchar(50) |  |  | Y | ACCEPTED, REJECTED, MODIFIED_AND_USED |
| final_text | text |  |  |  | 최종 사용 문구. MODIFIED_AND_USED일 때 필수 |
| comment | text |  |  |  | 담당자 의견 |
| decided_by | varchar(100) |  | users | Y | 판단자 |
| decided_at | timestamptz |  |  | Y | 판단일시 |

---

# 11. Q&A 테이블

## 11.1 qa_sessions

광고 규정 Q&A 세션을 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| qa_session_id | varchar(50) | Y |  | Y | Q&A 세션 ID |
| user_id | varchar(100) |  | users | Y | 사용자 ID |
| product_group | varchar(50) |  |  |  | 상품군 |
| advertisement_type | varchar(50) |  |  |  | 광고유형 |
| standard_effective_date | date |  |  |  | 기준 적용일 |
| title | varchar(500) |  |  |  | 세션 제목 |
| created_at | timestamptz |  |  | Y | 생성일시 |

---

## 11.2 qa_messages

Q&A 질문과 답변을 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| qa_message_id | varchar(50) | Y |  | Y | Q&A 메시지 ID |
| qa_session_id | varchar(50) |  | qa_sessions | Y | Q&A 세션 ID |
| question | text |  |  | Y | 사용자 질문 |
| answer_summary | text |  |  |  | 답변 요약 |
| answer_detail | text |  |  |  | 상세 답변 |
| needs_human_review | boolean |  |  | Y | 담당자 검토 필요 여부 |
| suggested_phrases | jsonb |  |  |  | 추천 문구 목록 |
| raw_response_json | jsonb |  |  |  | LLM 원본 응답 |
| created_at | timestamptz |  |  | Y | 생성일시 |

---

## 11.3 qa_message_evidences

Q&A 답변과 근거 자료 간 매핑을 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| qa_message_evidence_id | uuid | Y |  | Y | Q&A 근거 매핑 ID |
| qa_message_id | varchar(50) |  | qa_messages | Y | Q&A 메시지 ID |
| evidence_id | varchar(50) |  | evidences | Y | 근거 ID |
| evidence_chunk_id | varchar(50) |  | evidence_chunks |  | 근거 Chunk ID |
| relevance_score | numeric(5,4) |  |  |  | 관련도 |
| rank_no | int |  |  |  | 순위 |

---

# 12. 심의 의견 및 리포트 테이블

## 12.1 opinion_drafts

AI가 생성한 심의 의견 초안과 담당자 수정본을 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| draft_id | varchar(50) | Y |  | Y | 초안 ID |
| review_id | varchar(50) |  | reviews | Y | 검토 ID |
| template_type | varchar(100) |  |  | Y | 템플릿 유형 |
| draft_content | text |  |  | Y | AI 생성 초안 |
| final_content | text |  |  |  | 담당자 수정본 |
| included_review_item_ids | jsonb |  |  |  | 포함 검토 항목 ID |
| additional_instruction | text |  |  |  | 생성 지시사항 |
| created_at | timestamptz |  |  | Y | 생성일시 |
| created_by | varchar(100) |  | users | Y | 생성자 |
| updated_at | timestamptz |  |  |  | 수정일시 |
| updated_by | varchar(100) |  | users |  | 수정자 |

---

## 12.2 reports

검토 리포트 생성 이력을 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| report_id | varchar(50) | Y |  | Y | 리포트 ID |
| review_id | varchar(50) |  | reviews | Y | 검토 ID |
| source_report_id | varchar(50) |  | reports |  | PDF 변환본의 원본 HWPX report ID |
| report_type | varchar(50) |  |  | Y | FULL, SELECTED |
| report_format | varchar(30) |  |  | Y | HWPX, PDF |
| report_status | varchar(50) |  |  | Y | CREATED, FAILED |
| file_id | varchar(50) |  | advertisement_files |  | 리포트 파일 ID |
| report_payload | jsonb |  |  | Y | ADR-0054 기준 리포트 렌더링 원본 스냅샷 |
| snapshot_hash | varchar(128) |  |  | Y | canonical report_snapshot hash |
| snapshot_version | varchar(50) |  |  | Y | 리포트 스냅샷 스키마 버전 |
| renderer_version | varchar(100) |  |  |  | HWPX renderer 버전 |
| converter_version | varchar(100) |  |  |  | PDF converter 버전 |
| failure_reason | text |  |  |  | 생성 또는 변환 실패 사유 |
| include_annotations | boolean |  |  | Y | Annotation 포함 여부 |
| include_suggestions | boolean |  |  | Y | 문구 추천 포함 여부 |
| include_opinion_draft | boolean |  |  | Y | 의견 초안 포함 여부 |
| include_evidence_details | boolean |  |  | Y | 상세 근거 포함 여부 |
| created_at | timestamptz |  |  | Y | 생성일시 |
| created_by | varchar(100) |  | users | Y | 생성자 |

### Index

| 인덱스명 | 컬럼 |
|---|---|
| idx_reports_review | review_id |
| idx_reports_source | source_report_id |
| idx_reports_snapshot_hash | snapshot_hash |

---

# 13. 수정 전후 비교 테이블

## 13.1 comparisons

수정 전후 비교 실행 결과 요약을 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| comparison_id | varchar(50) | Y |  | Y | 비교 ID |
| advertisement_id | varchar(50) |  | advertisements | Y | 광고물 ID |
| base_review_id | varchar(50) |  | reviews | Y | 기준 검토 ID |
| revision_id | varchar(50) |  | advertisement_revisions | Y | 수정본 ID |
| comparison_status | varchar(50) |  |  | Y | COMPLETED, FAILED |
| compare_types | jsonb |  |  | Y | 비교 유형 목록 |
| resolved_issue_count | int |  |  | Y | 해결 건수 |
| unresolved_issue_count | int |  |  | Y | 미해결 건수 |
| new_issue_count | int |  |  | Y | 신규 리스크 건수 |
| created_at | timestamptz |  |  | Y | 생성일시 |
| created_by | varchar(100) |  | users | Y | 생성자 |

---

## 13.2 comparison_items

수정 전후 비교 항목별 결과를 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| comparison_item_id | varchar(50) | Y |  | Y | 비교 항목 ID |
| comparison_id | varchar(50) |  | comparisons | Y | 비교 ID |
| review_item_id | varchar(50) |  | review_items |  | 기존 검토 항목 ID |
| original_text | text |  |  |  | 수정 전 문구 |
| revised_text | text |  |  |  | 수정 후 문구 |
| resolution_status | varchar(50) |  |  | Y | RESOLVED, UNRESOLVED, NEW_ISSUE, CHECK_REQUIRED |
| comment | text |  |  |  | 비교 설명 |
| created_at | timestamptz |  |  | Y | 생성일시 |

---

# 14. PoC 검증 및 성능평가 테이블

## 14.1 validation_datasets

PoC 검증 데이터셋을 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| dataset_id | varchar(50) | Y |  | Y | 검증 데이터셋 ID |
| dataset_name | varchar(300) |  |  | Y | 데이터셋명 |
| advertisement_id | varchar(50) |  | advertisements |  | 연결 광고물 ID |
| product_group | varchar(50) |  |  | Y | 상품군 |
| advertisement_type | varchar(50) |  |  | Y | 광고유형 |
| sample_file_id | varchar(50) |  | advertisement_files |  | 샘플 광고물 파일 ID |
| product_condition_file_id | varchar(50) |  | advertisement_files |  | 상품 조건 파일 ID |
| human_review_comment | text |  |  |  | 준법 검토 의견 |
| label_json | jsonb |  |  |  | 정답 데이터 JSON |
| dataset_version | int |  |  | Y | 정답지/메타데이터 수정 버전 |
| is_excluded | boolean |  |  | Y | 평가 제외 여부 |
| exclude_reason_code | varchar(100) |  |  |  | 평가 제외 사유 코드 |
| exclude_reason | text |  |  |  | 평가 제외 상세 사유 |
| excluded_by | varchar(100) |  | users |  | 평가 제외 확정자 |
| excluded_at | timestamptz |  |  |  | 평가 제외 확정일시 |
| created_at | timestamptz |  |  | Y | 생성일시 |
| created_by | varchar(100) |  | users | Y | 생성자 |
| updated_at | timestamptz |  |  |  | 수정일시 |
| updated_by | varchar(100) |  | users |  | 수정자 |

`validation_datasets`는 PoC 검증 데이터셋과 정답지의 공식 원천이다. Git fixture와 Excel export는 개발/검토 보조 자료로만 사용하며, 공식 평가 산출은 DB에 반영된 값을 기준으로 한다.

---

## 14.2 validation_judgments

담당자 판단 결과를 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| judgment_id | varchar(50) | Y |  | Y | 판단 ID |
| dataset_id | varchar(50) |  | validation_datasets | Y | 데이터셋 ID |
| target_text | text |  |  | Y | 판단 대상 문구 |
| review_type | varchar(50) |  |  | Y | 검토유형 |
| expected_status | varchar(50) |  |  | Y | 기대 판정 |
| risk_level | varchar(50) |  |  |  | 위험도 |
| evidence_comment | text |  |  |  | 근거 또는 의견 |
| is_excluded | boolean |  |  | Y | 평가 제외 여부 |
| exclude_reason_code | varchar(100) |  |  |  | 평가 제외 사유 코드 |
| exclude_reason | text |  |  |  | 평가 제외 상세 사유 |
| excluded_by | varchar(100) |  | users |  | 평가 제외 확정자 |
| excluded_at | timestamptz |  |  |  | 평가 제외 확정일시 |
| judgment_version | int |  |  | Y | 담당자 판단 수정 버전 |
| judged_by | varchar(100) |  | users | Y | 판단자 |
| judged_at | timestamptz |  |  | Y | 판단일시 |
| updated_at | timestamptz |  |  |  | 수정일시 |
| updated_by | varchar(100) |  | users |  | 수정자 |

---

## 14.3 evaluations

PoC 성능평가 실행 결과를 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| evaluation_id | varchar(50) | Y |  | Y | 평가 ID |
| evaluation_name | varchar(300) |  |  |  | 평가명 |
| evaluation_status | varchar(50) |  |  | Y | COMPLETED, FAILED |
| dataset_ids | jsonb |  |  | Y | 평가 대상 데이터셋 ID |
| exclude_invalid_samples | boolean |  |  | Y | 유효하지 않은 샘플 제외 여부 |
| total_sample_count | int |  |  | Y | 전체 샘플 수 |
| excluded_sample_count | int |  |  | Y | 제외 샘플 수 |
| exclusion_summary_json | jsonb |  |  |  | 제외 사유별 집계 |
| dataset_snapshot_json | jsonb |  |  | Y | 평가 실행 시점 데이터셋/정답지 snapshot |
| judgment_snapshot_json | jsonb |  |  | Y | 평가 실행 시점 담당자 판단 snapshot |
| exclusion_snapshot_json | jsonb |  |  | Y | 평가 실행 시점 제외 사유 snapshot |
| ai_result_snapshot_json | jsonb |  |  | Y | 평가 실행 시점 AI 검토 결과 snapshot |
| version_snapshot_json | jsonb |  |  |  | 기준자료, 모델, 프롬프트, Parser/OCR, RAG/Search 버전 snapshot |
| evaluation_policy_snapshot_json | jsonb |  |  | Y | KPI, 목표 점수, review 선택 정책 snapshot |
| snapshot_hash | varchar(128) |  |  | Y | canonical snapshot hash |
| snapshot_created_at | timestamptz |  |  | Y | snapshot 생성일시 |
| created_at | timestamptz |  |  | Y | 생성일시 |
| created_by | varchar(100) |  | users | Y | 생성자 |

`evaluations`는 평가 실행 시점의 입력과 AI 결과를 snapshot으로 저장한다. 정답지나 AI 검토 결과가 이후 수정되어도 기존 `evaluation_id`의 결과는 snapshot 기준으로 불변이며, 재평가가 필요하면 새 평가를 생성한다.

---

## 14.4 evaluation_metrics

평가 지표별 결과를 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| evaluation_metric_id | uuid | Y |  | Y | 평가 지표 ID |
| evaluation_id | varchar(50) |  | evaluations | Y | 평가 ID |
| metric_code | varchar(100) |  |  | Y | 지표 코드 |
| metric_name | varchar(200) |  |  | Y | 지표명 |
| score | numeric(6,2) |  |  |  | 산출 점수. 분모 0이면 null |
| target_score | numeric(6,2) |  |  | Y | 목표 점수 |
| achieved | boolean |  |  | Y | 목표 달성 여부 |
| numerator | numeric(10,2) |  |  | Y | 항목별 match score 합계 |
| denominator | int |  |  | Y | 평가 대상 항목 수 또는 근거 수 |
| excluded_count | int |  |  | Y | 평가 제외 건수 |
| partial_count | int |  |  | Y | 부분 정답 건수 |
| not_applicable | boolean |  |  | Y | 분모 0으로 KPI 미적용 여부 |
| detail_json | jsonb |  |  |  | 상세 산출 결과, 부분 정답 사유 |

### 주요 metric_code

| metric_code | 설명 |
|---|---|
| REQUIRED_PHRASE_ACCURACY | 필수 문구 검토 정확도 |
| MISLEADING_EXPRESSION_ACCURACY | 위험 표현 검토 정확도 |
| EVIDENCE_PRECISION | 근거 매칭 적정성 |
| HUMAN_AGREEMENT_RATE | 담당자 판단 일치율 |

### 주요 exclude_reason_code

| exclude_reason_code | 설명 |
|---|---|
| OCR_UNREADABLE | ADR-0053 기준 OCR/Parser confidence `< 0.50`이고 판정 대상 문구 식별 불가 |
| PRODUCT_CONDITION_AMBIGUOUS | 상품조건 불명확 |
| REFERENCE_NOT_PROVIDED | 기준자료 미제공 |
| SOURCE_FILE_CORRUPTED | 원본 파일 손상 또는 분석 불가 |
| LABEL_UNCLEAR | 정답지 또는 담당자 판단 불명확 |
| DUPLICATE_SAMPLE | 중복 샘플 |
| OUT_OF_SCOPE | PoC 범위 외 샘플 |

---

# 15. 공통 코드 및 감사 로그 테이블

## 15.1 common_codes

상품군, 광고유형, 검토유형 등 공통 코드를 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| code_id | uuid | Y |  | Y | 코드 ID |
| code_group | varchar(100) |  |  | Y | 코드 그룹 |
| code | varchar(100) |  |  | Y | 코드값 |
| code_name | varchar(200) |  |  | Y | 코드명 |
| description | text |  |  |  | 설명 |
| sort_order | int |  |  |  | 정렬 순서 |
| is_enabled | boolean |  |  | Y | 사용 여부 |
| created_at | timestamptz |  |  | Y | 생성일시 |

### Constraint

| 제약조건 | 내용 |
|---|---|
| uk_common_codes | code_group, code unique |

---

## 15.2 audit_logs

주요 사용자 행위와 시스템 변경 이력을 관리한다.

| 컬럼명 | 타입 | PK | FK | NN | 설명 |
|---|---|---:|---:|---:|---|
| audit_log_id | uuid | Y |  | Y | 감사 로그 ID |
| user_id | varchar(100) |  | users |  | 사용자 ID |
| actor_department_id | varchar(50) |  | departments |  | 수행 당시 사용자 부서 ID |
| actor_role | varchar(50) |  | roles |  | 수행 당시 대표 역할 |
| action_type | varchar(100) |  |  | Y | 행위 유형 |
| target_type | varchar(100) |  |  | Y | 대상 유형 |
| target_id | varchar(100) |  |  |  | 대상 ID |
| result | varchar(30) |  |  | Y | SUCCESS, FAILURE, DENIED |
| reason_code | varchar(100) |  |  |  | 실패 또는 권한 거부 사유 |
| request_id | varchar(100) |  |  |  | 요청 추적 ID |
| ip_address | varchar(100) |  |  |  | IP 주소 |
| user_agent | text |  |  |  | User Agent |
| before_json | jsonb |  |  |  | 변경 전 데이터 |
| after_json | jsonb |  |  |  | 변경 후 데이터 |
| metadata_json | jsonb |  |  |  | 민감 원문을 제외한 추가 메타데이터 |
| message | text |  |  |  | 로그 메시지 |
| created_at | timestamptz |  |  | Y | 생성일시 |

### Index

| 인덱스명 | 컬럼 |
|---|---|
| idx_audit_logs_user | user_id |
| idx_audit_logs_actor_department | actor_department_id |
| idx_audit_logs_action | action_type |
| idx_audit_logs_target | target_type, target_id |
| idx_audit_logs_result | result |
| idx_audit_logs_created_at | created_at |

---

# 16. Qdrant 설계

## 16.1 Collection 구성

| Collection | 설명 | 주요 Payload |
|---|---|---|
| evidence_chunks | 법령, 내부기준, 심의사례, 문구 템플릿 Chunk 임베딩 | evidence_chunk_id, evidence_id, standard_id, standard_version_id, evidence_type, product_group, advertisement_type, rule_type, importance, effective_date, expired_date, index_status, embedding_model, chunking_policy_version, search_schema_version |
| product_documents | 상품설명서, 약관, 핵심상품설명서 Chunk 임베딩 | advertisement_id, file_id, product_group, document_type |
| review_cases | 과거 심의사례 Chunk 임베딩 | case_id, product_group, advertisement_type, decision_type |

---

## 16.2 Qdrant Payload 예시

```json id="pqq0t1"
{
  "evidence_chunk_id": "ECH-0001",
  "evidence_id": "EVD-0001",
  "standard_id": "STD-0001",
  "standard_version_id": "STDVER-0001",
  "evidence_type": "INTERNAL_STANDARD",
  "product_group": "SAVINGS",
  "advertisement_type": "MOBILE_BANNER",
  "rule_type": "PROHIBITED",
  "importance": "HIGH",
  "effective_date": "2026-01-01",
  "expired_date": null,
  "index_status": "ACTIVE",
  "embedding_model": "text-embedding-3-large",
  "chunking_policy_version": "reference-chunking-v1",
  "search_schema_version": "search-schema-v1",
  "opensearch_analyzer_version": "ko-analyzer-v1",
  "synonym_version": "synonyms-v1",
  "text": "객관적 근거 없는 최고, 유일, 보장 등 표현 사용 주의"
}
```

---

# 17. OpenSearch 설계

## 17.1 Index 구성

| Index | 설명 |
| --- | --- |
| standards_index | 기준자료 본문 및 메타데이터 검색 |
| evidence_chunks_index | RAG Chunk 키워드 검색 |
| advertisement_text_index | 광고물 OCR 텍스트 검색 |
| review_items_index | 검토 결과 검색 |
| audit_logs_index | 운영 로그 검색. 필요 시 |

---

## 17.2 OpenSearch Document 예시

```json
{
  "evidence_chunk_id": "ECH-0001",
  "evidence_id": "EVD-0001",
  "standard_id": "STD-0001",
  "standard_version_id": "STDVER-0001",
  "title": "금융상품 광고심의 내부 기준",
  "article_no": "3.2.1",
  "chunk_text": "객관적 근거 없는 최고, 유일, 보장 등 표현 사용 주의",
  "product_group": "SAVINGS",
  "advertisement_type": "MOBILE_BANNER",
  "rule_type": "PROHIBITED",
  "effective_date": "2026-01-01",
  "expired_date": null,
  "index_status": "ACTIVE",
  "embedding_model": "text-embedding-3-large",
  "chunking_policy_version": "reference-chunking-v1",
  "search_schema_version": "search-schema-v1",
  "opensearch_analyzer_version": "ko-analyzer-v1",
  "synonym_version": "synonyms-v1"
}
```

OpenSearch index mapping은 ADR-0071 기준으로 `chunk_text`, `title`, `article_no`, `section_path`에 text field를 두고, 정확 match와 filter가 필요한 필드는 keyword subfield 또는 keyword field를 둔다. `chunk_text`와 `title`은 highlight 대상이다.

---

# 18. 주요 인덱스 전략

## 18.1 조회 성능용 인덱스

| 테이블 | 인덱스 대상 |
| --- | --- |
| advertisements | 상태, 상품군, 광고유형, 등록자, 등록일 |
| reviews | 광고물 ID, 상태, 요청일 |
| review_items | 검토 ID, 검토유형, 판정결과, 위험도 |
| annotations | 검토 ID, 파일 ID, 페이지 번호 |
| evidences | 기준자료 ID, 상품군, 광고유형, 기준성격 |
| evidence_chunks | evidence_id, standard_version_id, qdrant_point_id, opensearch_doc_id, qdrant_index_status, opensearch_index_status |
| suggestions | 검토 ID, 검토 항목 ID, 채택 상태 |
| refresh_tokens | 사용자, token hash, 만료일, 폐기일 |
| validation_datasets | 상품군, 광고유형, dataset_version, 생성일 |
| validation_judgments | 데이터셋 ID, 검토유형, judgment_version |
| evaluations | 생성일, snapshot_hash |
| audit_logs | 사용자, 행위 유형, 대상 ID, 생성일시 |

---

## 18.2 JSONB 인덱스 후보

| 테이블 | 컬럼 | 목적 |
| --- | --- | --- |
| reviews | review_types | 검토유형 포함 여부 조회 |
| review_items | result_json | AI 엔진 상세 결과 검색 |
| evidences | metadata | 기준자료 메타데이터 검색 |
| validation_datasets | label_json | 정답 데이터 검색 |
| evaluations | dataset_ids | 평가 대상 데이터셋 검색 |

---

# 19. API-DB 매핑 요약

| API | 주요 테이블 |
| --- | --- |
| POST `/advertisements` | advertisements, advertisement_files |
| GET `/advertisements` | advertisements, reviews, reports |
| POST `/advertisements/{id}/reviews` | reviews, review_jobs, review_steps |
| GET `/reviews/{id}/status` | reviews, review_jobs, review_steps |
| GET `/reviews/{id}/summary` | reviews, review_items |
| GET `/reviews/{id}/items` | review_items, review_item_evidences, suggestions |
| GET `/reviews/{id}/annotations` | annotations, review_items |
| GET `/evidences/search` | evidences, evidence_chunks, Qdrant, OpenSearch |
| GET `/reviews/{id}/suggestions` | suggestions, suggestion_decisions |
| POST `/qa/questions` | qa_sessions, qa_messages, qa_message_evidences |
| POST `/reviews/{id}/opinion-drafts` | opinion_drafts |
| POST `/reviews/{id}/reports` | reports, advertisement_files |
| POST `/validation/datasets` | validation_datasets, advertisement_files |
| POST `/validation/datasets/{id}/judgments` | validation_judgments |
| POST `/validation/evaluations` | evaluations, evaluation_metrics |
| GET `/validation/evaluations/{id}` | evaluations, evaluation_metrics |
| POST `/auth/login` | users, user_roles, refresh_tokens |
| POST `/auth/refresh` | users, user_roles, refresh_tokens |
| POST `/auth/logout` | refresh_tokens |
| GET `/admin/audit-logs` | audit_logs |

---

# 20. 삭제 및 보관 정책

## 20.1 삭제 정책

| 대상 | 정책 |
| --- | --- |
| 광고물 | 기본적으로 논리 삭제 |
| 첨부파일 | 메타데이터 논리 삭제, 물리 파일은 보관 정책에 따름 |
| 기준자료 | 삭제하지 않고 비활성화 |
| 검토 결과 | 삭제하지 않고 이력 보존 |
| 리포트 | 생성 이력 보존 |
| 감사 로그 | 삭제 금지. 보관 기간 정책 적용 |

---

## 20.2 보관 정책

| 데이터 | 권장 보관 방식 |
| --- | --- |
| 광고물 원본 | PoC 기간 동안 보관 |
| AI 검토 결과 | PoC 검증 및 결과보고서 작성 완료까지 보관 |
| 기준자료 | 버전별 영구 보관 권장 |
| 감사 로그 | 내부 보안정책에 따라 보관 |
| Qdrant/OpenSearch 인덱스 | PostgreSQL 원천 데이터 기준 재생성 가능해야 함 |

## 20.3 백업 및 복구 정책

백업 및 복구 정책은 [ADR-0047: PoC 백업 및 복구 정책](adr/ADR-0047-poc-backup-and-restore-policy.md)을 따른다.

| 구성요소 | PoC 백업 기준 |
| --- | --- |
| PostgreSQL | `prod(main)` 기준 매일 1회 dump, migration 전 수동 backup 필수 |
| Object Storage/MinIO | bucket 단위 백업, 광고 원본/기준자료/리포트/파서 산출물 포함 |
| Qdrant | collection snapshot 또는 export 관리 |
| OpenSearch | PoC에서는 snapshot 필수 제외, 원천 데이터 기준 재색인 복구 |
| Redis | queue/cache 성격으로 백업 대상 제외 |

복구 후에는 PostgreSQL row count, 주요 bucket object count, Qdrant collection count, OpenSearch 재색인 완료 여부를 확인한다.

---

# 21. 개인정보 및 민감정보 저장 정책

개인정보 및 민감정보 저장/노출 정책은 [ADR-0048: PoC 개인정보 및 민감정보 저장/노출 정책](adr/ADR-0048-poc-personal-sensitive-data-policy.md)을 따른다.

| 항목 | PoC 기준 |
| --- | --- |
| 사용자 email | 로그인 ID로 사용하므로 DB 평문 저장 허용 |
| 사용자명 | 소규모 사용자 식별과 화면 표시를 위해 DB 평문 저장 허용 |
| 부서/역할 | 권한 판단과 화면 표시를 위해 DB 평문 저장 허용 |
| 비밀번호 | ADR-0058 기준 `password_hash`만 저장, 최소 길이/사용자 정보 포함 금지 정책 적용 |
| token/API key/secret | DB/로그 평문 저장 금지. refresh token은 ADR-0056 기준 hash만 저장 |
| presigned URL 전체값 | DB/로그 저장 금지. 발급 여부, object 식별자, 만료 시각, 용도만 기록 |
| IP/User-Agent | 감사 로그 목적 저장 허용, 화면 노출 제한 |
| 고객사 원문 | 업무 저장소에는 저장 가능하되 로그, 오류 응답, fixture 저장 금지 |

컬럼 암호화, KMS/Vault, field-level encryption은 PoC 필수 범위에서 제외한다. 본사업 전환, 고객사 보안 요구, 사용자 수 확대, 운영 데이터 입력이 확정되면 별도 ADR 또는 운영 정책으로 재검토한다.

---

# 22. 파티셔닝 정책

대용량 테이블 파티셔닝 정책은 [ADR-0049: PoC 대용량 테이블 파티셔닝 적용 정책](adr/ADR-0049-poc-table-partitioning-policy.md)을 따른다.

| 대상 | PoC 기준 |
| --- | --- |
| `audit_logs` | 일반 테이블 사용, `created_at`, `user_id`, `action_type`, `target_type + target_id` 인덱스 기준 조회 |
| `review_items` | 일반 테이블 사용, `review_id`, `review_type`, `result_status`, `risk_level`, `ocr_block_id` 인덱스 기준 조회 |
| 파티셔닝 | PoC 초기 미적용 |
| 조회 기준 | 감사 로그는 기간 조건과 페이징, 검토 항목은 `review_id` 기준 조회와 페이징 적용 |
| 재검토 기준 | 본사업 전환, 100만 건 이상 누적, 조회 P95 지속 초과, 월/연 단위 보관 정책 확정 시 |

---

# 23. 후속 상세화 필요사항

| 항목 | 상세화 필요 내용 |
| --- | --- |
| 물리 DB명 | 개발/검증/운영 DB명 확정 |
| 스키마명 | `app`, `rag`, `validation`, `audit` 영역별 schema 사용 |
| ID 생성 규칙 | 내부 PK/FK는 UUID, 외부 노출 ID는 Prefix 문자열 사용 |
| 파일 저장소 | 로컬, NAS, Object Storage 등 저장 방식 확정 |
| 파티셔닝 | ADR-0049 기준 PoC 초기 미적용, 일반 테이블 + 인덱스 + 페이징/기간 조건으로 시작하고 본사업 전환 또는 데이터 증가 기준 충족 시 재검토 |
| 개인정보/민감정보 | ADR-0048 기준 email/name 평문 저장 허용, password/token/secret/presigned URL 평문 저장 금지, 컬럼 암호화는 본사업 전환 시 재검토 |
| 백업 정책 | ADR-0047 기준 PostgreSQL/Object Storage/Qdrant 백업, OpenSearch 재색인 복구 적용 |
| 마이그레이션 도구 | ADR-0041 기준 Alembic 사용, `apps/backend/migrations`, `app.alembic_version` 적용 |
| Seed 데이터 관리 | ADR-0041 기준 migration과 분리하여 `apps/backend/seeds`, `scripts/seed-*.sh`로 관리 |
| DB 권한 | ADR-0046 기준 `app`, `migration`, `readonly`, `admin` 계정 분리, 본사업 전환 시 schema별 세부 권한 재검토 |
| API 인가 | ADR-0055 기준 role + department scope 적용. 목록 조회는 scope 밖 데이터 제외, 단건/다운로드 권한 거부는 `DENIED` 감사 로그 기록 |
| 세션/토큰 | ADR-0056 기준 `refresh_tokens` hash 저장, `users.auth_token_version`으로 access token 무효화 |
| 로그인 보호 | ADR-0058 기준 `failed_login_count`, `locked_until`, `last_failed_login_at`, `password_changed_at` 관리 |
| AI Job 정책 | ADR-0059 기준 `RETRY_PENDING`, `STALE`, `FAILED_FINAL`, `timeout_at`, `failed_reason_code`, `is_retryable`, `dead_lettered_at` 관리 |
| 성능 기준 | ADR-0042 기준 목록 조회 P95 1.5초, 검토 항목 조회 P95 2초, 근거 검색 P95 3초를 PoC 관찰 목표로 관리 |
| RAG 근거 선정 | ADR-0043 기준 검토 항목별 최대 5개 근거 저장, rank/score/source 저장. 검색 인프라 장애는 ADR-0061 기준 `review_jobs.failed_reason_code`, `review_steps.failed_reason_code`에 기록 |
| Parser/OCR 엔진 라우팅 | ADR-0079 기준 PDF/복합 PDF는 `opendataloader-pdf`, 이미지/스캔 PDF는 `PaddleOCR`, HWP/HWPX는 `hwp-hybrid` 적용. DB에는 구성요소 raw output이 아니라 단일 병합 `NormalizedDocument` 영속화 결과와 parser metadata를 저장 |
| Parser/OCR 품질 재처리 | ADR-0073 기준 기술 retry와 품질 재처리를 분리하고, 보조 엔진 시도/사유/최종 채택 여부는 `parser_artifacts` metadata로 추적 |

---

# 22. 결론

본 DB 명세서는 AI 기반 금융상품 광고심의 적정성 검토 에이전트 PoC 구현을 위한 데이터 구조를 정의한다.

핵심 설계 방향은 다음과 같다.

1. PostgreSQL은 광고물, 검토 결과, 기준자료, 사용자 행위 이력의 원천 저장소로 사용한다.
2. Qdrant는 기준자료와 심의사례의 의미 기반 검색을 담당한다.
3. OpenSearch는 법령명, 조문번호, 금지어, 광고 문구 등 키워드 기반 검색을 담당한다.
4. AI 검토 결과는 반드시 근거 자료와 연결될 수 있도록 `review_item_evidences` 구조를 둔다.
5. 광고 화면 표시 기능을 위해 OCR 좌표, 레이아웃 블록, Annotation 데이터를 별도로 관리한다.
6. PoC 검증을 위해 담당자 판단 결과와 AI 검토 결과를 비교할 수 있는 검증 데이터셋 및 평가 테이블을 둔다.

본 문서를 기준으로 다음 단계에서는 테스트케이스를 작성한다.
