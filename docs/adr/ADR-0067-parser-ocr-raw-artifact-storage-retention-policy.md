# ADR-0067: Parser/OCR Raw Artifact 저장 위치, 보존 기간 및 접근 정책

## 상태

Accepted

## 배경

ADR-0065는 Parser/OCR Adapter의 공통 출력으로 `NormalizedDocument` v1을 사용하고, parser별 raw output은 업무 로직이 직접 참조하지 않도록 결정했다. 그러나 raw output을 어디에 저장하고, DB에는 어떤 참조 정보를 남기며, 누가 접근할 수 있는지는 별도 정책이 필요하다.

Parser/OCR raw artifact는 OCR 원문 JSON, 파서 중간 구조, layout 분석 결과, 경고 및 adapter 디버깅 정보를 포함할 수 있다. 이 데이터는 분석 실패 원인 조사, adapter 교체 검증, 재처리, PoC 품질 평가에 유용하지만 고객사 원문과 민감정보가 포함될 수 있으므로 일반 사용자 다운로드 대상이 되어서는 안 된다.

## 결정

Parser/OCR raw artifact는 **Object Storage의 `parser-artifacts` bucket에 저장하고, DB에는 참조 ID와 메타데이터만 저장**한다.

| 항목 | 결정 |
| --- | --- |
| 저장 위치 | ADR-0017 기준 S3 호환 Object Storage의 `parser-artifacts` bucket |
| DB 저장 | `parser_artifacts` 메타데이터 테이블에 참조 정보만 저장 |
| 업무 로직 의존 | ReviewPipeline, RAG, Annotation, 리포트는 raw artifact 구조에 직접 의존 금지 |
| API 노출 | 일반 사용자 API에는 raw artifact 다운로드 URL 또는 원문 JSON을 노출하지 않음 |
| 접근 권한 | worker/service account 내부 접근 원칙. 예외 접근은 관리자/개발자 디버깅 목적에 한정 |
| 보존 기간 | dev는 단기 보존, `prod(main)` PoC는 검증/인수 기간까지 보존 후 승인 기반 정리 |

## Object Key 기준

Object key는 외부 노출 ID만 단독으로 사용하지 않고 환경, 검토, 파일, 처리 단계, 내부 artifact ID를 조합한다.

```text
parser-artifacts/{env}/reviews/{reviewId}/files/{fileId}/steps/{stepId}/{artifactId}.json
```

| 구성요소 | 기준 |
| --- | --- |
| `env` | `dev`, `prod` 등 환경명 |
| `reviewId` | 외부 노출 검토 ID |
| `fileId` | 외부 노출 파일 ID |
| `stepId` | Parser/OCR 단계 ID 또는 `review_steps.step_id` |
| `artifactId` | 내부 UUID 또는 prefix ID |

Object key에는 원본 파일명, 사용자 email, 고객사명, 상품명, presigned URL, API key, prompt 원문을 넣지 않는다.

## DB 메타데이터 기준

DB에는 raw artifact 본문을 저장하지 않고 다음 메타데이터를 저장한다.

| 필드 | 설명 |
| --- | --- |
| `raw_artifact_id` | raw artifact 식별자 |
| `review_id` | 검토 ID |
| `file_id` | 원본 파일 ID |
| `review_step_id` | 생성한 처리 단계 ID |
| `artifact_type` | `OCR_RAW`, `PARSER_RAW`, `LAYOUT_RAW`, `NORMALIZED_DOCUMENT`, `WARNING_DETAIL` |
| `storage_provider` | `minio`, `s3`, `s3-compatible` 등 |
| `bucket` | `parser-artifacts` |
| `object_key` | Object Storage key |
| `checksum_sha256` | 무결성 검증용 checksum |
| `content_type` | 일반적으로 `application/json` |
| `file_size` | object 크기 |
| `parser_name` | Adapter 이름 |
| `parser_version` | Adapter 또는 모델 버전 |
| `parser_rule_version` | 정규화/구조 추출 rule set 버전 |
| `ir_version` | 관련 IR/schema 버전 |
| `retention_until` | 정리 가능 기준일 |
| `created_at` | 생성 시각 |

`NormalizedDocument.rawArtifactRef`는 `raw_artifact_id` 또는 내부 artifact URI를 가리키며, 일반 사용자 API에서 직접 다운로드 가능한 URL로 변환하지 않는다.

## 보존 및 정리 기준

| 환경 | 보존 기준 |
| --- | --- |
| `dev` | 기본 7~14일 단기 보존. 로컬 개발/fixture 재생성 가능 데이터는 정리 가능 |
| `prod(main)` PoC | PoC 검증, 결과보고서 작성, 고객사 인수 확인까지 보존 |
| PoC 종료 후 | 고객사와 산출물 정리 범위를 확인한 뒤 승인 기반 삭제 또는 별도 보관 |

보존 기간이 지나도 다음 상태의 artifact는 자동 삭제하지 않는다.

- 분석 실패 원인 조사 중인 artifact
- 고객사 검증 이슈와 연결된 artifact
- PoC 결과보고서 근거 재현에 필요한 artifact
- adapter 교체 전후 비교 기준 fixture로 승인된 artifact

## 접근 및 감사 기준

| 접근 주체 | 허용 범위 |
| --- | --- |
| Parser/OCR worker | 생성, 읽기, 재처리 목적 읽기 |
| ReviewPipeline | `NormalizedDocument` 참조만 사용. raw artifact 직접 파싱 금지 |
| 일반 사용자 | raw artifact 원문 조회/다운로드 금지 |
| 관리자/개발자 | 장애 분석, 재현, adapter 검증 목적의 예외 접근 |
| 백업/복구 작업 | ADR-0047 기준 bucket backup/restore |

예외 접근, presigned URL 발급, 수동 다운로드, 삭제는 ADR-0022 기준 감사 로그 대상이다. 로그에는 object key 전체나 presigned URL 전체값을 남기지 않고 artifact ID, 용도, 만료 시각, 사용자 또는 service account만 남긴다.

## 대안

| 대안 | 판단 |
| --- | --- |
| A. raw artifact 저장하지 않음 | 저장 부담은 작지만 OCR/parser 오류 재현과 품질 검증이 어려워 기각 |
| B. Object Storage에 저장하고 DB에는 참조/메타데이터만 저장 | 재현성, 보안, 백업, 저장 비용의 균형이 좋아 채택 |
| C. DB `raw_json` 중심 저장 | 구현은 단순하지만 DB 비대화, 백업 부담, 대용량 JSON 처리 리스크가 커 기각 |
| D. dev만 저장하고 `prod(main)`에는 저장하지 않음 | 실제 PoC 샘플 이슈를 사후 분석하기 어려워 기각 |
| E. raw + normalized artifact 모두 장기 보존 | 재현성은 높지만 PoC 단계의 보관 부담과 민감정보 관리 범위가 과해 기각 |

## 결정 근거

- ADR-0017에서 이미 OCR/파서 산출물용 `parser-artifacts` bucket을 정의했다.
- raw artifact는 대용량 JSON이 될 수 있어 PostgreSQL 본문 저장보다 Object Storage가 적합하다.
- DB에는 참조와 checksum만 남겨도 무결성 검증, 재처리, 감사 추적이 가능하다.
- 일반 사용자 기능은 `NormalizedDocument`, Text IR, Annotation 결과를 사용하면 충분하며 raw output 원문 노출이 필요하지 않다.
- Parser/OCR 도구를 교체하려면 raw artifact 보존과 업무 로직 의존 금지를 동시에 지켜야 한다.

## 영향

- DB 명세에 `parser_artifacts` 메타데이터 테이블을 추가한다.
- `ocr_text_blocks` 등 영속화 테이블은 raw JSON 본문 대신 `raw_artifact_id`를 참조한다.
- API 명세의 `rawArtifactRef`는 내부 참조값이며 다운로드 URL이 아님을 명확히 한다.
- Object Storage 백업에는 `parser-artifacts` bucket이 포함된다.
- 테스트는 raw artifact 저장 메타데이터, checksum, 접근 제한, `NormalizedDocument` 의존 분리를 검증해야 한다.

## 후속 조치

- `parser_artifacts` migration을 작성한다.
- `ObjectStorageAdapter`에 artifact 저장/조회/삭제 보조 API를 추가한다.
- Parser/OCR adapter contract test에 raw artifact metadata fixture를 추가한다.
- 보존 기간 정리 script는 dev부터 적용하고, `prod(main)` 삭제는 승인 절차를 거친다.
- 예외 접근과 삭제 작업을 감사 로그에 연결한다.

## 관련 문서

- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0017-s3-compatible-object-storage.md`
- `docs/adr/ADR-0021-file-access-download-policy.md`
- `docs/adr/ADR-0022-audit-log-scope.md`
- `docs/adr/ADR-0047-poc-backup-and-restore-policy.md`
- `docs/adr/ADR-0065-normalized-document-schema-and-adapter-contract.md`
