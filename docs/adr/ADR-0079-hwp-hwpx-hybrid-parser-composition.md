# ADR-0079: HWP/HWPX 이중 원천 Hybrid Parser 구성 정책

| 항목 | 내용 |
| --- | --- |
| 상태 | Accepted |
| 날짜 | 2026-07-20 |
| 관련 문서 | 기능명세서, API 명세서, DB 설계서, 테스트케이스, 프로젝트 규칙 |
| 관련 ADR | ADR-0014, ADR-0052, ADR-0053, ADR-0065, ADR-0067, ADR-0073 |
| 대체 ADR | ADR-0072 |

## 배경

ADR-0072는 HWP/HWPX의 1차 엔진을 `rhwp`, 보조 엔진을 `document-processor`로 정했다. 실제 구현에서 `rhwp export-text`는 원문 텍스트의 공백과 문단을 안정적으로 보존하지만, 페이지 전체를 하나의 `BODY` TextBlock으로 만들고 `layoutBlocks`와 `tables`를 생성하지 않아 문단·표·항목 구조를 후속 검토에 전달하지 못한다.

ReviewPipeline은 `NormalizedDocument.textBlocks`를 검토 단위로 소비하므로 페이지 전체가 하나의 TextBlock이면 문서 일부의 금리·최상급·필수 문구가 문서 전체 결과와 검색 질의로 확대된다. 반대로 `document-processor`만 단독 원천으로 사용하면 현재 검증된 `rhwp` 텍스트 완전성을 잃을 수 있고, 구조 파서 변환 과정의 텍스트 차이가 감사 가능한 원문 기준을 흔들 수 있다.

두 엔진은 동일 목적의 경쟁 후보가 아니라 각각 텍스트 보존과 구조 복원에 강점이 있는 상호 보완 원천이다. 따라서 HWP/HWPX에 한해 한 결과를 선택하는 방식이 아니라 두 결과를 정렬·병합하는 기준이 필요하다.

## 결정

파일 유형별 Parser/OCR 라우팅은 다음과 같이 운영하며, 본 ADR이 ADR-0072를 대체한다.

| 파일 유형 | 기본 처리 | 보조/품질 재처리 | 비고 |
| --- | --- | --- | --- |
| PDF, 복합 PDF/표/다단 | `opendataloader-pdf` | `MinerU` | 구조·좌표 품질 재처리는 ADR-0073 적용 |
| 스캔 PDF | `PaddleOCR` | `opendataloader-pdf`, `MinerU`, 승인된 VLM OCR | OCR 필요 여부에 따라 라우팅 |
| JPG/JPEG/PNG | `PaddleOCR` | 승인된 VLM OCR | 외부 AI 입력 정책 준수 |
| HWP/HWPX | `HwpHybridParserAdapter` | 구성요소 기술 재시도와 구조 확인 필요 처리 | `rhwp` 텍스트와 `document-processor` 구조를 병합 |
| 기타 Office 형식 | PoC 초기 범위 제외 | `document-processor`, `MinerU` 후보 | ADR-0037 범위 유지 |

HWP/HWPX Hybrid Parser의 책임은 다음과 같다.

1. `rhwp export-text` 산출물을 raw/normalized 텍스트의 **기준 원천**으로 사용한다.
2. `document-processor`의 문단, run, 표·셀, 목록, 스타일, 페이지와 안정적인 node 식별자를 **구조 기준 원천**으로 사용한다.
3. `document-processor` 구조 노드의 텍스트를 `rhwp` 기준 텍스트에 정렬해 문단·표 셀 단위 `textPath`, raw/normalized offset과 관련 `layoutBlocks`·`tables`를 생성한다.
4. 구조에 정렬되지 않은 `rhwp` 텍스트는 삭제하거나 `document-processor` 텍스트로 덮어쓰지 않고 별도 미정렬 TextBlock과 warning으로 보존한다.
5. 두 엔진의 raw artifact와 버전·confidence·정렬 결과는 ADR-0067 기준으로 보존한다.
6. 후속 ReviewPipeline에는 `parserName=hwp-hybrid`인 **단 하나의 병합된 `NormalizedDocument` v1**만 전달한다.
7. ReviewPipeline, RAG, Annotation, 리포트는 두 엔진의 raw output을 직접 읽지 않고 ADR-0065의 공통 출력만 사용한다.
8. 정렬된 TextBlock에 직접 좌표가 없고 연관 `layoutBlock`에 검증된 좌표가 있으면 그 layout 좌표를 TextBlock의 시각 위치로 보존한다. HWP/HWPX 변환 SVG에서 `matchedText`와 실제 글자열이 정확히 일치하면 UI는 해당 SVG 글자 좌표를 원본 표시용으로 사용할 수 있다. 어느 원천에서도 정확한 위치를 확인하지 못한 offset 항목은 원본 위치 미확정으로 남긴다.

```text
HWP/HWPX
  -> HwpHybridParserAdapter
      -> RhwpTextSource              # 기준 텍스트, raw/normalized offset
      -> DocumentProcessorStructure  # 문단, 표/셀, 스타일, node/page 구조
      -> HwpStructureAligner          # 구조-기준 텍스트 정렬, 미정렬 범위 보존
  -> NormalizedDocument v1 (parserName=hwp-hybrid)
  -> ReviewPipeline / RAG / Annotation / Report
```

### 실패와 품질 저하 처리

| 상황 | 처리 |
| --- | --- |
| `rhwp` 기술 실패 또는 텍스트 없음 | 기준 텍스트를 확정할 수 없으므로 ADR-0059/0073에 따라 retry 또는 최종 실패 처리 |
| `document-processor` 일시 장애 | 기술 retry 후에도 실패하면 `rhwp` 텍스트를 보존하고 구조 보강 실패 warning과 `PARTIALLY_STRUCTURED` 또는 `UNSTRUCTURED` 상태로 확인 필요 처리 |
| 두 원천의 텍스트 불일치 | `rhwp` 텍스트를 유지하고 정렬 실패 구간을 미정렬 TextBlock으로 보존하며 구조 confidence를 낮춤 |
| 일부 표·문단만 정렬 성공 | 성공 구간만 구조 블록으로 만들고 나머지 기준 텍스트를 누락 없이 별도 블록으로 보존 |
| 최종 병합 계약 불충족 | 불완전한 구조를 정상 완료로 가장하지 않고 확인 필요 또는 최종 실패 처리 |

`document-processor`는 HWP/HWPX에서 더 이상 ADR-0073의 경쟁 보조 산출물이 아니다. 두 구성요소를 합쳐 하나의 `hwp-hybrid` 산출물을 만드는 내부 구조 원천이다. ADR-0073의 “최종 채택 산출물 하나만 후속 전달” 원칙은 병합 완료 후의 단일 `NormalizedDocument`에 적용한다.

## 정합성 및 감사 기준

- 비공백 기준 텍스트가 구조 정렬에 포함되지 않더라도 반드시 미정렬 TextBlock으로 남아야 한다.
- TextBlock·LayoutBlock·Table의 식별자와 `textPath`는 동일 입력과 parser/rule 버전에서 결정적으로 생성해야 한다.
- `rhwp`, `document-processor`, aligner의 버전과 각 raw artifact checksum을 추적할 수 있어야 한다.
- 구조 confidence는 텍스트 confidence와 분리하고 정렬 범위, 표·셀 복원, warning을 반영해야 한다.
- HWP/HWPX 미리보기는 기존 private `rhwp` SVG 경계를 유지하며, 검토용 텍스트·구조 산출물과 시각 미리보기 artifact를 혼동하지 않는다.
- 문단·표 블록은 후속 금융광고 항목 분할의 입력이며, parser 자체가 금융 규정 위반 여부를 판단하지 않는다.

## 대안

| 대안 | 판단 |
| --- | --- |
| A. `rhwp`만 유지하고 페이지 전체 텍스트를 검토 | 텍스트는 보존되지만 문단·표·항목 단위 검토와 정확한 근거 연결이 어려워 제외 |
| B. `document-processor`를 HWP/HWPX 단독 원천으로 사용 | 구조는 풍부하지만 검증된 기준 텍스트의 누락·변형 가능성을 독립적으로 통제하기 어려워 제외 |
| C. 기존처럼 `rhwp`와 `document-processor` 결과 중 하나를 선택 | 상호 보완 정보를 결합하지 못하고 winner-take-all 비교가 텍스트 완전성과 구조를 동시에 보장하지 못해 제외 |
| D. `rhwp` 텍스트와 `document-processor` 구조를 병합 | 기준 텍스트를 보존하면서 문단·표·offset 구조를 제공할 수 있어 채택 |
| E. 전체 원문을 LLM에 전달해 구조를 생성 | 비용·재현성·폐쇄망·감사 추적 부담이 크고 결정적 parser 계약을 대체할 수 없어 제외 |

## 영향

- ADR-0072는 Superseded로 변경하고 현재 파일 유형별 라우팅 원천을 본 ADR로 전환한다.
- HWP/HWPX ParserRouter는 단일 `rhwp` 어댑터가 아니라 `HwpHybridParserAdapter`를 선택한다.
- `document-processor`는 별도 private service 또는 교체 가능한 HTTP adapter로 격리하며 worker가 해당 패키지에 직접 의존하지 않는다.
- 최종 `NormalizedDocument`의 `parserName`, TextBlock parser metadata와 raw artifact 추적 기준은 `hwp-hybrid` 경계를 사용한다.
- 현재 페이지 전체 `BODY` 한 개를 만드는 HWP 구현은 문단·표 셀 및 미정렬 범위 블록 생성으로 대체해야 한다.
- 후속 Rule/RAG/LLM 검토는 구조화된 블록과 이후 정의할 금융광고 항목 단위를 사용하며 전체 페이지 텍스트를 하나의 검토 문구로 사용하지 않는다.
- 공개 API의 URL이나 사용자 요청 스키마는 변경하지 않는다. 내부 NormalizedDocument 생성·영속화와 parser provenance가 변경된다.

## 후속 조치

- Python 3.13과 OpenJDK 25 runtime이 필요한 `document-processor`를 현재 Python 3.12 worker/rhwp 이미지와 분리한 private service로 구성한다.
- `DocumentProcessorServiceAdapter`, `HwpHybridParserAdapter`, `HwpStructureAligner`의 계약과 fixture를 구현한다.
- `NormalizedDocument` v1에서 구성요소별 provenance를 표현할 수 있는지 검토하고, 부족하면 하위 호환 optional metadata 또는 후속 IR 버전을 별도 ADR로 결정한다.
- 승인된 HWP/HWPX 광고 샘플로 텍스트 누락, 문단·표 셀 복원, offset 정렬, 미정렬 범위 보존, Annotation 위치를 검증한다.
- 구조화 블록을 대출금리·우대금리·대상·한도·기간·상환·비용·위험고지 등 금융광고 검토 단위로 변환하는 도메인 세그먼터 계약은 별도 명세와 테스트로 확정한다.
- 기준자료 HWP/HWPX 적재도 동일 hybrid parser를 재사용하되, 광고 검토 단위와 규정 조문 chunking의 도메인 정책은 분리한다.

## 구현 상태

2026-07-20 기준으로 본 결정의 parser 조합 경계와 실행 인프라를 구현했다.

- `HwpHybridParserAdapter`와 `HwpStructureAligner`가 `rhwp` 기준 텍스트를 `document-processor` 문단·표 구조에 결정적으로 정렬하고, 미정렬 텍스트를 별도 블록으로 보존한다.
- 광고 worker와 기준자료 적재가 모두 `parserName=hwp-hybrid`인 단일 `NormalizedDocument`를 후속 처리에 전달한다.
- worker는 `rhwp`, `document-processor` 구성요소 산출물을 감사용 `PARSER_RAW` artifact로 보존하고 최종 병합 산출물만 선택 상태로 저장한다.
- `document-processor`는 고정 commit, Python 3.13, OpenJDK 25 기반 private Compose 서비스로 격리했다.
- 실제 HWP 광고 샘플에서 `rhwp` 비공백 텍스트 전량 보존, 20개 병합 TextBlock, 7개 LayoutBlock, 4개 Table 생성을 확인했다.
- 2026-07-21부터는 HWP/HWPX 화면에서 구조 TextBlock 좌표를 우선하고, 직접 좌표가 누락된 경우 연관 layout 좌표를 보완해 변환 SVG 원본 위에 표시한다. 구조 좌표도 없으면 private SVG의 실제 글자 좌표와 `matchedText`를 정확히 대조해 일치한 항목만 원본 위에 표시한다. offset만 존재하거나 글자열이 일치하지 않는 항목은 위치를 추정해 하이라이트하지 않는다.

금융광고 항목별 도메인 세그먼터와 구성요소별 구조 confidence의 독립 표현은 별도 명세·ADR에서 다룬다.

## 관련 문서

- `docs/functional-specification.md`
- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/test-cases.md`
- `docs/project-rules.md`
- `docs/reference-repositories.md`
- `docs/adr/ADR-0014-pluggable-document-parser-ocr.md`
- `docs/adr/ADR-0052-text-ir-offset-policy.md`
- `docs/adr/ADR-0053-confidence-threshold-policy.md`
- `docs/adr/ADR-0065-normalized-document-schema-and-adapter-contract.md`
- `docs/adr/ADR-0067-parser-ocr-raw-artifact-storage-retention-policy.md`
- `docs/adr/ADR-0072-parser-ocr-engine-routing-policy.md`
- `docs/adr/ADR-0073-parser-ocr-quality-rerun-policy.md`
