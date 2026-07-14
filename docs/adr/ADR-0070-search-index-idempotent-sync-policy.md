# ADR-0070: Qdrant/OpenSearch 인덱스 동기화 및 Idempotent Upsert/Delete 정책

## 상태

Accepted

## 배경

ADR-0009는 Qdrant를 벡터 DB로 채택했고, ADR-0010은 OpenSearch를 키워드 검색 엔진으로 채택했다. ADR-0069는 기준자료 재색인 API와 Chunk 조회 API를 제공하기로 결정했다.

재색인 Job은 네트워크 오류, worker 재시작, Qdrant/OpenSearch 일시 장애, timeout 때문에 재시도될 수 있다. 같은 Job 또는 같은 기준자료 버전 재색인이 여러 번 실행될 때 Qdrant point와 OpenSearch document가 중복 생성되거나, 한쪽 인덱스만 성공하고 다른 쪽은 실패한 상태가 남으면 RAG 검색 결과의 재현성과 신뢰성이 깨진다.

따라서 PostgreSQL 원천 데이터와 Qdrant/OpenSearch 검색 인덱스 간 동기화 기준, deterministic ID, upsert/delete 처리 방식을 명확히 정한다.

## 결정

Qdrant/OpenSearch 인덱스 동기화는 **deterministic ID 기반 idempotent upsert + soft delete/search exclusion** 방식으로 처리한다.

| 항목 | 결정 |
| --- | --- |
| 원천 데이터 | PostgreSQL `evidence_chunks` |
| Qdrant point ID | deterministic ID 사용 |
| OpenSearch document ID | deterministic ID 사용 |
| 재시도 처리 | 같은 ID에 upsert하여 중복 생성 방지 |
| 비활성화/만료 | 물리 삭제보다 검색 제외 상태를 우선 적용 |
| 부분 실패 | chunk별 Qdrant/OpenSearch index status와 Job 실패 사유로 추적 |
| 물리 삭제 | cleanup Job 또는 운영 절차로 지연 삭제 |

## Deterministic ID 규칙

기준자료 Chunk 인덱스 ID는 다음 요소를 조합한다.

```text
{env}:{standardVersionId}:{evidenceChunkId}:{embeddingModel}:{chunkingPolicyVersion}
```

| 구성요소 | 포함 이유 |
| --- | --- |
| `env` | dev/prod(main) 인덱스 충돌 방지 |
| `standardVersionId` | 기준자료 버전별 재현성 보장 |
| `evidenceChunkId` | Chunk 단위 식별 |
| `embeddingModel` | 임베딩 모델 변경 시 vector ID 분리 |
| `chunkingPolicyVersion` | Chunking 정책 변경 시 ID 분리 |

OpenSearch document ID도 동일한 logical ID를 사용한다. `KEYWORD_ONLY`에서는 `embeddingModel` 값이 검색 내용에 직접 영향은 없지만, Qdrant/OpenSearch 정합성을 쉽게 비교하기 위해 같은 ID 규칙을 유지한다.

## Index Status 기준

`evidence_chunks`는 Qdrant와 OpenSearch 각각의 색인 상태를 저장한다.

| 상태 | 의미 |
| --- | --- |
| `PENDING` | 색인 대기 |
| `INDEXING` | 색인 진행 중 |
| `ACTIVE` | 검색 대상 |
| `FAILED` | 색인 실패 |
| `EXCLUDED` | 비활성화/만료/버전 전환으로 검색 제외 |
| `DELETED` | 물리 삭제 완료 |

Qdrant와 OpenSearch는 독립적으로 성공/실패할 수 있으므로 상태 필드는 분리한다. Hybrid Search는 ADR-0061 기준 한쪽 인프라 또는 인덱스가 정상 검색 불가 상태이면 fallback하지 않는다.

## Upsert 기준

재색인 Worker는 다음 원칙을 따른다.

1. PostgreSQL `evidence_chunks`와 기준자료 버전을 읽는다.
2. deterministic ID를 계산한다.
3. Qdrant point payload와 OpenSearch document를 생성한다.
4. 같은 ID에 upsert한다.
5. 성공한 대상의 `*_index_status`를 `ACTIVE`로 갱신한다.
6. 실패한 대상은 `FAILED`, `*_index_error_code`, `*_index_error_message`를 기록한다.
7. 모든 대상이 성공하면 `standard_reindex_jobs.job_status=SUCCEEDED`로 전환한다.
8. 하나라도 실패하면 Job은 `FAILED` 또는 retry 상태로 처리한다.

같은 입력으로 같은 재색인 작업을 여러 번 실행해도 같은 point/document ID에 upsert되어야 한다. 중복 point/document를 새로 만들지 않는다.

## Delete/Search Exclusion 기준

기준자료는 ADR-0040 기준 불변 버전을 보존하고, 기준자료 삭제는 기본적으로 비활성화 처리한다. 따라서 검색 인덱스에서도 물리 삭제보다 검색 제외를 우선한다.

| 상황 | 처리 |
| --- | --- |
| 기준자료 비활성화 | 관련 chunk의 index status를 `EXCLUDED`로 변경하고 검색 filter에서 제외 |
| 기준자료 버전 만료 | 만료 버전 chunk를 `EXCLUDED`로 변경 |
| 새 버전 성공 색인 | 새 버전 `ACTIVE` 전환 후 이전 버전은 기준일/활성 상태 filter에서 제외 |
| 잘못 생성된 chunk | 원천 row를 보존한 뒤 `EXCLUDED` 또는 cleanup 대상으로 표시 |
| 보관 기간 만료 또는 운영 정리 | cleanup Job으로 Qdrant/OpenSearch 물리 삭제 후 `DELETED` 기록 |

검색 쿼리는 `indexStatus=ACTIVE`, 기준일 유효성, `standardVersionId`, `isActive` payload/document field를 함께 사용한다.

## 부분 실패 처리

| 상태 | 처리 |
| --- | --- |
| Qdrant upsert 성공, OpenSearch 실패 | Qdrant status `ACTIVE`, OpenSearch status `FAILED`, Job 실패 또는 retry |
| OpenSearch upsert 성공, Qdrant 실패 | OpenSearch status `ACTIVE`, Qdrant status `FAILED`, Job 실패 또는 retry |
| 두 인덱스 모두 실패 | 두 status `FAILED`, Job 실패 또는 retry |
| 재시도 성공 | 실패 상태를 `ACTIVE`로 갱신 |
| retry 한도 초과 | ADR-0059 기준 최종 실패로 남김 |

부분 성공 상태의 한쪽 인덱스만으로 RAG 판단을 계속하지 않는다. ADR-0061 기준 RAG 검색 인프라 장애 또는 인덱스 정합성 오류로 처리한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| A. 단순 insert 후 실패 시 수동 정리 | 구현은 단순하지만 재시도 시 중복 point/doc와 stale index 위험이 커 기각 |
| B. deterministic ID 기반 idempotent upsert + soft delete/search exclusion | 재시도 안전성, 복구성, 감사 추적의 균형이 좋아 채택 |
| C. 매번 전체 index drop 후 rebuild | 정합성은 단순하지만 검색 공백과 처리 시간이 커져 기각 |
| D. PostgreSQL outbox/event sourcing 기반 동기화 | 확장성은 높지만 PoC 단계에는 구현 부담이 커 기각 |
| E. Qdrant/OpenSearch를 임시 cache로 보고 정합성 검증 생략 | 빠르지만 RAG 근거 재현성과 장애 분석이 약해 기각 |

## 결정 근거

- PoC에서도 재색인 Job은 retry될 수 있으므로 idempotent해야 한다.
- PostgreSQL을 원천으로 두면 Qdrant/OpenSearch는 재생성 가능한 검색 인덱스로 관리할 수 있다.
- deterministic ID는 중복 색인과 stale document를 줄이고 복구 검증을 쉽게 한다.
- soft delete/search exclusion은 기준자료 버전 보존 정책과 맞다.
- 부분 실패를 명시적으로 남겨야 RAG 장애와 업무적 근거 부족을 구분할 수 있다.

## 영향

- `evidence_chunks`에 Qdrant/OpenSearch별 index status, indexed timestamp, error code/message 필드를 추가한다.
- Qdrant payload와 OpenSearch document에 `indexStatus`, `standardVersionId`, `embeddingModel`, `chunkingPolicyVersion`, `searchSchemaVersion`, `opensearchAnalyzerVersion`, `synonymVersion`, `isActive`, `effectiveDate`, `expiredDate`를 포함한다. 상세 schema와 highlight 기준은 ADR-0071을 따른다.
- 재색인 Worker는 insert가 아니라 upsert를 기본 동작으로 사용한다.
- 기준자료 비활성화/만료 시 검색 제외 처리를 수행한다.
- 테스트케이스에 중복 재색인, 부분 실패, 비활성화 검색 제외, cleanup 삭제를 추가한다.

## 후속 조치

- `openapi/openapi.yaml`의 Chunk schema에 index status 필드를 반영한다.
- Qdrant/OpenSearch adapter에 deterministic ID 생성 함수를 공통화한다.
- 검색 query builder는 `ACTIVE`와 기준일 유효성 filter를 항상 적용한다.
- cleanup Job의 실제 물리 삭제 주기와 권한은 운영 정책에서 조정한다.

## 관련 문서

- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0009-qdrant-vector-database.md`
- `docs/adr/ADR-0010-opensearch-keyword-search.md`
- `docs/adr/ADR-0040-standard-versioning-and-effective-date-policy.md`
- `docs/adr/ADR-0047-poc-backup-and-restore-policy.md`
- `docs/adr/ADR-0061-rag-search-infra-failure-policy.md`
- `docs/adr/ADR-0069-standard-reindex-and-chunk-query-api-policy.md`
- `docs/adr/ADR-0071-search-index-schema-analyzer-payload-policy.md`
