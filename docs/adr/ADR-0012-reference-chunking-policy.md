# ADR-0012: 기준자료 Chunking 정책

## 상태

Accepted

## 배경

RAG 근거 검색 품질은 기준자료를 어떤 단위로 분할하고 어떤 메타데이터를 붙이는지에 크게 좌우된다. 금융광고 심의에서는 조문번호, 필수 문구, 금지 표현, 상품 기준, 심의사례 맥락이 모두 근거로 사용되므로 단순 고정 길이 Chunking만으로는 근거 정확도와 설명 가능성을 확보하기 어렵다.

특히 법령과 정형 내규는 조, 항, 호, 목 같은 구조가 의미 단위와 직접 연결된다. 반면 내부 가이드라인, 지침, 매뉴얼은 문서 작성 형식이 엄격히 지켜지지 않을 수 있으므로 구조 인식 파싱이 실패해도 검색 가능한 Chunk를 만들 수 있어야 한다.

## 결정

기준자료는 자료 유형별 혼합 Chunking을 사용한다.

법령과 정형 내규는 rule base 기반의 structure aware parsing을 우선 적용한다. 내부 가이드라인, 지침, 매뉴얼처럼 형식이 불규칙할 수 있는 문서는 구조 인식 결과를 참고하되, 문단·섹션·의미 단위 fallback을 함께 사용한다.

| 자료 유형 | 기본 파싱/Chunking 기준 | Fallback 기준 |
| --- | --- | --- |
| 법령, 감독규정, 고시 | 조, 항, 호, 목 구조를 rule base로 인식 | 긴 조항은 문단 단위 분할, 구조 불명확 시 제목+문단 단위 |
| 정형 내규, 업무 기준 | 장, 절, 조, 항, 번호 목록 구조를 rule base로 인식 | 번호 체계가 깨진 경우 제목 추론+문단 단위 |
| 내부 가이드라인, 지침, 매뉴얼 | 제목, 번호 목록, 표, 강조 문구를 구조 힌트로 사용 | 의미 단위, 문단 묶음, 표 단위 혼합 |
| 심의사례 | 사안, 판단, 근거, 조치 결과를 보존하는 의미 단위 | 섹션 구분이 없으면 문단 클러스터링 |
| 상품설명서, 약관 | 섹션, 표, 유의사항, 수수료/금리 정보 단위 | 표 추출 실패 시 주변 제목+행 텍스트 단위 |

## Structure Aware Parsing 원칙

법령과 정형 내규의 rule base는 다음 구조를 인식한다.

| 구조 | 예시 |
| --- | --- |
| 문서 계층 | 편, 장, 절, 관 |
| 조문 | 제1조, 제1조의2 |
| 항 | ①, ②, 1., 2. |
| 호/목 | 1., 가., 나., a. |
| 별표/서식 | 별표, 별지, 서식 |
| 시행 정보 | 시행일, 개정일, 적용 대상 |

구조 인식 결과에는 `structure_confidence`를 부여한다. 신뢰도가 낮거나 구조가 부분적으로만 인식된 경우에도 처리를 중단하지 않고 fallback Chunking을 수행한다. 구조 인식 신뢰도 임계값은 ADR-0053의 parser structure confidence 기준을 따른다.

## Chunk 메타데이터

모든 Chunk에는 검색, 필터링, 감사 추적을 위해 다음 메타데이터를 붙인다.

| 메타데이터 | 설명 |
| --- | --- |
| `document_id` | 기준자료 문서 식별자 |
| `document_type` | 법령, 내규, 가이드라인, 지침, 매뉴얼, 심의사례, 상품자료 등 |
| `document_version` | 문서 버전 또는 개정일 |
| `effective_from` | 시행일 또는 적용 시작일 |
| `effective_to` | 적용 종료일, 없으면 null |
| `section_path` | 장/절/조/항/호 또는 제목 경로 |
| `article_no` | 조문번호, 없으면 null |
| `page_no` | 원문 페이지 번호, 없으면 null |
| `chunk_index` | 문서 내 Chunk 순번 |
| `parser_rule_version` | 적용한 구조 인식 rule set 버전 |
| `structure_confidence` | 구조 인식 신뢰도 |
| `source_span` | 원문 내 위치 또는 문자 범위 |

## 근거 표시 기준

RAG 근거는 ADR-0043 기준으로 선정하고, 기본적으로 검토 항목별 Top-3를 표시한다.

| 상황 | 처리 |
| --- | --- |
| 관련도 기준 이상 근거가 3개 이상 | Top-3 표시 |
| 관련도 기준 이상 근거가 1~2개 | 확보된 근거만 표시하고 부족 여부 표시 |
| 관련도 기준 미달 | “기준자료 확인 필요” 표시 |
| 구조 인식 신뢰도 낮음 | 근거 표시 시 구조 신뢰도 경고 또는 담당자 확인 상태로 처리 |

관련도 임계값과 rerank 산식은 ADR-0043의 초기 정책을 따른다. PoC 평가셋 결과에 따라 조정할 수 있으며, 임계값 변경은 검색 품질 평가 기록 또는 후속 ADR에 남긴다.

## 대안

| 대안 | 판단 |
| --- | --- |
| 모든 자료 고정 토큰 Chunking | 구현은 단순하지만 조문, 표, 사례 맥락이 끊겨 근거 품질이 낮아질 수 있다. |
| 모든 자료 문서 구조 단위 Chunking | 사람이 이해하기 쉽지만 내부 매뉴얼처럼 형식이 불규칙한 문서에서 실패 가능성이 높다. |
| 자료 유형별 혼합 Chunking | 구현 규칙은 늘어나지만 금융광고 심의 근거 검색에 가장 적합하다. |
| LLM 기반 자동 Chunking 중심 | 유연하지만 재현성, 비용, 온프렘 운영, 감사 추적 측면에서 기본 경로로 두기 어렵다. |

## 결정 근거

- 법령과 내규는 조문 구조 자체가 판단 근거가 되므로 structure aware parsing이 필요하다.
- 내부 가이드라인과 매뉴얼은 작성 형식이 일관되지 않을 수 있어 fallback 전략이 필요하다.
- Hybrid Search에서 keyword 검색은 조문번호와 정확 문구 메타데이터가 있을 때 품질이 높다.
- Vector Search는 의미 단위 Chunk가 유지되어야 유사 사례와 문맥 기준을 잘 찾을 수 있다.
- rule base와 parser rule version을 남기면 기준자료 재색인 결과를 추적할 수 있다.

## 영향

- 기준자료 ingestion 단계에 문서 유형 분류와 Chunking Router가 필요하다.
- 법령/내규 structure parser rule set은 Git에서 버전 관리한다.
- Chunk에는 원문 위치, 구조 경로, 적용일, 버전 정보를 함께 저장해야 한다.
- 검색 품질 평가는 chunk 단위, Top-K 근거 정확도, 담당자 확인 필요 비율을 함께 본다.
- 내부 가이드라인/매뉴얼의 불규칙한 형식은 오류가 아니라 낮은 구조 신뢰도와 fallback 처리 대상으로 본다.

## 후속 조치

- 기준자료 ingestion 설계에 `ReferenceChunker`와 `StructureParser` 책임을 추가한다.
- DB 명세에 Chunk 메타데이터와 parser rule version 저장 항목을 반영한다. 기준자료 유형별 필수 메타데이터는 ADR-0050을 따른다.
- API 명세의 기준자료 재색인과 Chunk 조회는 ADR-0069 기준으로 제공한다.
- 테스트케이스에 법령형, 정형 내규형, 불규칙 매뉴얼형 샘플을 포함한다.
- 검색 품질 평가셋에 Top-3 근거 적중률과 “기준자료 확인 필요” 처리 기준을 추가한다.

## 관련 문서

- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0011-hybrid-search-strategy.md`
- `docs/adr/ADR-0014-pluggable-document-parser-ocr.md`
- `docs/adr/ADR-0050-reference-metadata-policy.md`
- `docs/adr/ADR-0069-standard-reindex-and-chunk-query-api-policy.md`
