# ADR-0050: 기준자료 유형별 메타데이터 및 관리 단위 정책

## 상태

Accepted

## 배경

ADR-0012는 기준자료를 자료 유형별로 Chunking하는 정책을 정했고, ADR-0040은 기준자료 버전관리와 검토 기준일 선택 정책을 정했다. 그러나 법령, 내규, 가이드라인, 심의사례, 문구 템플릿, 상품 기준자료를 등록할 때 어떤 메타데이터를 필수로 받아야 하는지는 아직 명확하지 않았다.

기준자료 메타데이터는 RAG 검색 필터, Rule Engine 입력, 화면 필터, 리포트 근거 표시, 테스트 fixture 구성에 모두 영향을 준다. 모든 자료를 공통 필드만으로 관리하면 유형별 필수 정보가 누락되기 쉽고, 반대로 자료 유형별 테이블을 모두 분리하면 PoC 단계에서 migration과 화면/API 구현이 과도하게 복잡해진다.

## 결정

기준자료는 공통 필드와 유형별 필수 메타데이터를 함께 관리한다. 공통 필드는 명시 컬럼으로 두고, 유형별 필수 메타데이터는 표준 key로 검증한다. 자료 유형별 확장값은 `metadata_json`에 저장한다.

| 항목 | 결정 |
| --- | --- |
| 기본 관리 단위 | `standards` master + 불변 `standard_versions` + 검색 근거 `evidences`/`evidence_chunks` |
| 공통 필드 | `standard_id`, `standard_version_id`, `title`, `evidence_type`, `product_group`, `advertisement_type`, `rule_type`, `effective_date`, `expired_date`, `version` |
| 유형별 필수값 | `evidence_type`별 필수 메타데이터 표준을 적용 |
| 확장값 | 유형별 추가 값은 `metadata_json`에 저장 |
| 테이블 분리 | PoC에서는 자료 유형별 별도 테이블을 만들지 않음 |
| 승격 기준 | 검색/필터/판단에 자주 쓰는 값은 명시 컬럼 또는 인덱스 대상으로 승격 |

## 자료 유형별 필수 메타데이터

| 자료 유형 | `evidence_type` | 필수 메타데이터 |
| --- | --- | --- |
| 법령/감독규정/고시 | `LAW`, `REGULATION` | 기관, 문서명, 조문번호, 시행일, 개정일, 원문 출처 |
| 내부기준/내규 | `INTERNAL_STANDARD` | 소관 부서, 문서명, 장/절/조 경로, 시행일, 버전, 적용 상품군 |
| 가이드라인/지침/매뉴얼 | `GUIDELINE`, `MANUAL` | 문서명, 문서유형, 섹션 경로, 적용 상품군, 광고유형, 버전 |
| 심의사례 | `REVIEW_CASE` | 사례번호, 상품군, 광고유형, 판단유형, 지적사항, 조치결과, 판단일 |
| 문구 템플릿 | `TEMPLATE` | 문구유형, 필수/권고/금지 여부, 상품군, 광고유형, 적용 조건 |
| 상품 기준자료 | `PRODUCT_STANDARD` | 상품명, 상품군, 금리/수수료/조건 항목, 적용일, 파일 버전 |

## 공통 필드와 확장 필드

공통 필드는 검색, 필터, 버전 선택, 권한 확인, 화면 목록에 직접 사용되는 값이다.

| 필드 | 기준 |
| --- | --- |
| `title` | 기준자료명 또는 근거 제목 |
| `evidence_type` | 자료 유형 |
| `product_group` | 적용 상품군. 전 상품군 공통이면 null 허용 |
| `advertisement_type` | 적용 광고유형. 전 광고유형 공통이면 null 허용 |
| `rule_type` | REQUIRED, PROHIBITED, RECOMMENDED, REFERENCE 등 |
| `importance` | HIGH, MEDIUM, LOW |
| `effective_date` | 시행일 또는 적용 시작일 |
| `expired_date` | 적용 종료일, 없으면 null |
| `version` | ADR-0040 기준 불변 version |
| `article_no` | 법령/내규/가이드라인의 조문 또는 항목 번호 |

`metadata_json`에는 공통 필드로 승격하지 않은 유형별 정보를 저장한다.

```json
{
  "agency": "금융위원회",
  "source_url": "https://example.invalid/source",
  "section_path": "제2장 > 제3조",
  "parser_rule_version": "law-v1",
  "structure_confidence": 0.92
}
```

## 검증 기준

| 검증 대상 | 기준 |
| --- | --- |
| 등록 API | `evidence_type`별 필수 메타데이터 누락 시 `BAD_REQUEST` 또는 도메인 오류 반환 |
| 수정 API | ADR-0040 기준 기존 version 덮어쓰기 금지, 새 version 생성 |
| Chunk 생성 | ADR-0012 기준 `document_type`, `section_path`, `parser_rule_version`, `structure_confidence` 저장 |
| 검색 인덱스 | 공통 필드와 유형별 주요 metadata를 Qdrant payload/OpenSearch document에 포함 |
| 테스트 fixture | 법령형, 내부기준형, 불규칙 매뉴얼형, 심의사례형, 문구 템플릿형 샘플 포함 |

## 대안

| 대안 | 판단 |
| --- | --- |
| 모든 기준자료를 공통 필드만으로 관리 | 구현은 단순하지만 자료 유형별 필수값 누락과 검색 품질 저하 위험이 크다. |
| 공통 필드 + `metadata_json`만 사용 | 유연하지만 필수값 검증과 화면 입력 기준이 약하다. |
| 공통 필드 + 유형별 필수 메타데이터 표준화 + 확장값 `metadata_json` | PoC 구현 복잡도와 검색 품질의 균형이 좋다. |
| 자료 유형별 별도 테이블 분리 | 정규화는 좋지만 PoC에서는 migration, API, 화면이 과도하게 복잡해진다. |
| 샘플 데이터가 모인 뒤 결정 | 늦게 정하면 DB/API/화면/테스트 fixture 구조가 흔들린다. |

## 결정 근거

- RAG 검색 품질은 상품군, 광고유형, 조문번호, 판단유형, 적용일 같은 metadata 품질에 크게 의존한다.
- 기준자료 관리 화면은 자료 유형에 따라 필수 입력값을 안내해야 한다.
- 유형별 별도 테이블은 본사업에서는 검토할 수 있지만 PoC에서는 자료 유형과 샘플 형태가 변동될 수 있다.
- `metadata_json`만 사용하면 초기 속도는 빠르지만 필수값 누락을 방지하기 어렵다.
- 공통 필드와 유형별 필수 metadata 표준을 함께 두면 API 검증, 검색 필터, 테스트 fixture를 안정적으로 설계할 수 있다.

## 영향

- 기준자료 등록/수정 API는 `evidence_type`별 필수 metadata 검증을 수행해야 한다.
- 기준자료 관리 화면은 자료 유형 선택에 따라 필수 입력 필드를 다르게 표시해야 한다.
- DB 명세는 공통 필드와 `metadata_json` 확장 필드를 함께 표현해야 한다.
- Qdrant payload와 OpenSearch document에는 ADR-0071 기준 검색 필터에 필요한 공통 필드와 주요 metadata를 포함해야 한다.
- 테스트케이스는 유형별 필수 metadata 누락과 정상 등록 케이스를 포함해야 한다.

## 후속 조치

- DB 명세서의 기준자료 테이블에 `metadata_json` 기준을 반영한다.
- API 명세서의 기준자료 등록/수정 요청에 `metadata` 입력 필드와 유형별 필수값 검증 기준을 반영한다.
- 기능명세서의 기준 DB 구조 후속 상세화 항목을 본 ADR 기준으로 갱신한다.
- 구현 시 `ReferenceMetadataValidator` 또는 동등한 검증 모듈을 둔다.

## 관련 문서

- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/functional-specification.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0012-reference-chunking-policy.md`
- `docs/adr/ADR-0040-standard-versioning-and-effective-date-policy.md`
- `docs/adr/ADR-0043-rag-evidence-selection-policy.md`
- `docs/adr/ADR-0071-search-index-schema-analyzer-payload-policy.md`
