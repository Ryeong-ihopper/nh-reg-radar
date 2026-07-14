# ADR-0069: 기준자료 재색인 및 Chunk 조회 API 정책

## 상태

Accepted

## 배경

ADR-0012는 기준자료를 자료 유형별 혼합 Chunking으로 처리하고, 법령/정형 내규에는 rule base 기반 structure aware parsing을 우선 적용하기로 결정했다. ADR-0043은 RAG 근거 선정 기준을 정했고, ADR-0047은 OpenSearch를 원천 데이터 기준 재색인 복구 대상으로 관리하기로 했다.

현재 API 명세에는 근거 검색과 근거 상세 조회만 있고, 기준자료 재색인 요청/상태 조회와 Chunk 단위 조회 API는 없다. 이 상태에서는 기준자료 버전 변경, chunking 규칙 변경, 임베딩 모델 변경, OpenSearch analyzer 변경, Qdrant/OpenSearch 복구 시 어떤 작업을 누가 요청했고 어떤 인덱스가 갱신되었는지 추적하기 어렵다.

## 결정

기준자료 재색인 요청/상태 API와 관리자용 Chunk 조회 API를 제공한다. 일반 사용자에게 Chunk API를 직접 노출하지 않고, 검토 결과 화면에서는 기존 근거 표시 API를 통해 필요한 근거만 제공한다.

| 항목 | 결정 |
| --- | --- |
| 재색인 요청 | 기준자료 특정 버전 기준 비동기 Job으로 요청 |
| 재색인 범위 | `INDEX_ONLY`, `CHUNK_AND_INDEX`, `KEYWORD_ONLY`, `VECTOR_ONLY` |
| 상태 조회 | `standard_reindex_jobs` 기준으로 상태, 실패 사유, 대상 인덱스 반환 |
| Chunk 조회 | `STANDARD_MANAGER`, `SYSTEM_ADMIN` 전용 관리자/운영 API |
| 일반 사용자 노출 | Chunk 직접 조회 금지. 검토 결과 근거 API만 사용 |
| 감사 로그 | 재색인 요청, 실패, 성공, 관리자 Chunk 조회는 ADR-0022 기준 기록 |

## API 기준

초기 PoC에서는 다음 API를 둔다.

| API | 용도 | 권한 |
| --- | --- | --- |
| `POST /api/v1/standards/{standardId}/versions/{standardVersionId}/reindex` | 기준자료 특정 버전 재색인 요청 | `STANDARD_MANAGER`, `SYSTEM_ADMIN` |
| `GET /api/v1/standard-reindex-jobs/{jobId}` | 재색인 Job 상태 조회 | `STANDARD_MANAGER`, `SYSTEM_ADMIN` |
| `GET /api/v1/evidences/{evidenceId}/chunks` | 근거 기준 Chunk 목록 조회 | `STANDARD_MANAGER`, `SYSTEM_ADMIN` |
| `GET /api/v1/evidence-chunks/{evidenceChunkId}` | Chunk 단건 상세 조회 | `STANDARD_MANAGER`, `SYSTEM_ADMIN` |

재색인 요청은 다음 범위를 지원한다.

| `reindexScope` | 처리 |
| --- | --- |
| `INDEX_ONLY` | 기존 `evidence_chunks`는 유지하고 Qdrant/OpenSearch 인덱스만 재생성 |
| `CHUNK_AND_INDEX` | 기준자료 버전을 다시 parser/chunker에 통과시켜 `evidence_chunks`를 재생성하고 Qdrant/OpenSearch 재색인 |
| `KEYWORD_ONLY` | OpenSearch만 재색인 |
| `VECTOR_ONLY` | Qdrant embedding/point만 재생성 |

임베딩 모델 변경은 보통 `VECTOR_ONLY` 또는 `INDEX_ONLY`에 해당한다. Chunking 규칙, parser rule, 기준자료 본문, 표 추출 정책이 바뀐 경우에는 `CHUNK_AND_INDEX`를 사용한다.

## 재색인 요청 기준

재색인 요청에는 변경 사유와 적용 버전 정보를 포함한다.

```json
{
  "reindexScope": "INDEX_ONLY",
  "reason": "embedding model changed",
  "parserRuleVersion": "reference-parser-rules-v1",
  "chunkingPolicyVersion": "reference-chunking-v1",
  "embeddingModel": "text-embedding-3-large",
  "targetIndexes": [
    "QDRANT",
    "OPENSEARCH"
  ]
}
```

`prod(main)`에서는 `reason`을 필수로 두고, dev에서는 실험성 재색인을 허용한다. `prod(main)`에서 기준자료 버전, chunking 정책, 임베딩 모델, 검색 인덱스를 바꾸는 재색인은 감사 로그에 남긴다.

## 상태 및 실패 처리

재색인 Job 상태는 다음 값을 사용한다.

| 상태 | 의미 |
| --- | --- |
| `QUEUED` | 요청 접수 |
| `RUNNING` | parser/chunker/indexing 수행 중 |
| `SUCCEEDED` | 모든 대상 인덱스 갱신 완료 |
| `FAILED` | 복구 가능한 실패 또는 최종 실패 |
| `CANCELED` | 관리자 취소 또는 중단 |

실패 사유는 `failed_reason_code`, `failed_reason_message`로 남긴다. Qdrant/OpenSearch 장애는 ADR-0061 기준 fallback 없이 실패로 처리하고, 재시도 가능 여부는 Job 정책에 맞춰 관리한다.

## Chunk 조회 기준

Chunk 조회 API는 RAG 품질 검증과 장애 분석을 위한 관리자 기능이다. 다음 정보를 반환한다.

| 항목 | 설명 |
| --- | --- |
| 기준자료 식별자 | `standardId`, `standardVersionId`, `evidenceId`, `evidenceChunkId` |
| Chunk 내용 | `chunkNo`, `chunkText`, `tokenCount` |
| 구조 메타데이터 | `sectionPath`, `articleNo`, `pageNo`, `sourceSpan`, `structureConfidence` |
| 버전 정보 | `parserRuleVersion`, `chunkingPolicyVersion`, `embeddingModel` |
| 인덱스 연결 | `qdrantCollection`, `qdrantPointId`, `opensearchIndex`, `opensearchDocId` |

Chunk 조회 결과는 기준자료 원문 일부를 포함할 수 있으므로 일반 사용자에게 직접 노출하지 않는다. 검토 결과 화면의 근거 표시는 기존 `/evidences/search`, `/reviews/{reviewId}/items/{reviewItemId}` 응답을 사용한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| A. 재색인/Chunk 조회 API 없음 | 구현은 단순하지만 RAG 인덱스 문제 진단과 운영 복구가 어려워 기각 |
| B. 재색인 요청/상태 API만 제공 | 운영 최소 범위는 충족하지만 Chunk 품질 검증이 DB 직접 조회에 의존해 기각 |
| C. 재색인 요청/상태 API + 관리자용 Chunk 조회 API 제공 | 운영, 품질 검증, 보안 균형이 좋아 채택 |
| D. 일반 사용자에게도 Chunk 조회 제공 | 투명성은 높지만 내부 chunk 구조와 기준자료 원문 노출 위험이 있어 기각 |
| E. 배치/스크립트로만 재색인 | 초기 구현 부담은 낮지만 화면, 감사 로그, Job 상태 추적과 맞지 않아 기각 |

## 결정 근거

- RAG 품질은 chunking, embedding, keyword index 설정에 민감하므로 재색인 작업을 추적할 수 있어야 한다.
- 기준자료 버전과 검색 인덱스 상태가 어긋나면 검토 결과 재현성이 깨진다.
- 임베딩 모델 변경, OpenSearch analyzer 변경, 장애 복구는 API 기반 Job으로 남겨야 감사와 재시도가 가능하다.
- Chunk 본문은 기준자료 원문 일부이므로 일반 사용자에게 직접 제공하지 않는 것이 안전하다.
- 관리자용 Chunk 조회가 있어야 법령/내규 structure aware parsing 결과와 fallback chunk 품질을 검증할 수 있다.

## 영향

- API 명세에 재색인 요청/상태 조회, Chunk 목록/상세 조회를 추가한다.
- DB 명세에 `standard_reindex_jobs`를 추가하고 `evidence_chunks`에 기준 버전과 parser/chunking 정책 버전 필드를 명시한다.
- 기준자료 변경, 재색인, 관리자 Chunk 조회는 감사 로그 대상이 된다.
- 테스트케이스에 재색인 요청, 상태 조회, 권한 오류, Chunk 조회, 임베딩 모델 변경 재색인을 추가한다.
- `prod(main)` 재색인은 변경 사유를 필수로 기록한다.

## 후속 조치

- `openapi/openapi.yaml`에 재색인과 Chunk 조회 schema를 추가한다.
- 재색인 Worker는 `standard_reindex_jobs` 상태를 갱신하고 실패 사유를 남긴다.
- Qdrant/OpenSearch idempotent upsert/delete 기준은 ADR-0070을 따르고, schema/analyzer/synonym version 변경 재색인은 ADR-0071을 따른다.
- 화면에서는 기준자료 관리자가 재색인 요청과 상태를 확인할 수 있는 보조 action을 제공한다.

## 관련 문서

- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/screen-api-mapping.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0012-reference-chunking-policy.md`
- `docs/adr/ADR-0022-audit-log-scope.md`
- `docs/adr/ADR-0043-rag-evidence-selection-policy.md`
- `docs/adr/ADR-0047-poc-backup-and-restore-policy.md`
- `docs/adr/ADR-0061-rag-search-infra-failure-policy.md`
- `docs/adr/ADR-0070-search-index-idempotent-sync-policy.md`
