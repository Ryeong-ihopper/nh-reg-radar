# ADR-0014: 교체 가능한 문서 파서 및 OCR 아키텍처

## 상태

Accepted

## 배경

광고심의 적정성 검토는 PDF, 이미지, HWP/HWPX, 모바일 캡처, 배너 등 다양한 입력 문서를 다룬다. 문서 파서와 OCR 도구는 정확도, 속도, GPU 필요 여부, 라이선스, 온프렘 가능성에 따라 교체될 수 있으므로 특정 엔진에 업무 로직이 직접 의존하면 안 된다.

참조 후보는 다음과 같다.

| 후보 | 검토 용도 |
| --- | --- |
| `document-processor` | HWP, HWPX, DOCX, PDF를 통합 구조로 파싱하는 사내/참조 후보 |
| `opendataloader-pdf` | PDF를 Markdown, JSON, HTML 및 bounding box 중심으로 추출하는 후보 |
| `rhwp` | HWP/HWPX 렌더링 및 파싱 후보 |
| `PaddleOCR` | 이미지/PDF OCR 기본 후보 |
| `MinerU` | 복합 PDF/Office 문서의 Markdown/JSON 변환 후보 |
| `Unlimited-OCR` | GPU 기반 VLM OCR 실험 후보 |

## 결정

문서 파서와 OCR은 교체 가능한 Adapter 구조로 설계한다.

업무 로직은 특정 오픈소스 라이브러리를 직접 호출하지 않고, 내부 표준 인터페이스만 사용한다.

```text
upload file
  -> DocumentIngestionService
  -> ParserRouter
      -> PdfParserAdapter
      -> HwpParserAdapter
      -> ImageOcrAdapter
      -> VlmOcrAdapter
  -> NormalizedDocument
  -> ReviewPipeline
```

내부 표준 출력은 `NormalizedDocument`로 둔다. `NormalizedDocument` v1의 필수 필드와 adapter 계약은 [ADR-0065: NormalizedDocument 공통 출력 스키마 및 Parser/OCR Adapter 계약 정책](ADR-0065-normalized-document-schema-and-adapter-contract.md)을 따른다.

| 필드 | 설명 |
| --- | --- |
| `source_file_id` | 원본 파일 식별자 |
| `parser_name` | 사용된 파서 또는 OCR 어댑터 이름 |
| `parser_version` | 어댑터 또는 모델 버전 |
| `pages` | 페이지 단위 텍스트, 이미지, 레이아웃 정보 |
| `text_blocks` | OCR/파서가 추출한 텍스트 블록 |
| `layout_blocks` | 제목, 본문, 유의사항, 표, 버튼, 배너 등 영역 |
| `tables` | 표 구조와 셀 텍스트 |
| `bounding_boxes` | 원본 좌표 및 정규화 좌표 |
| `confidence` | 추출 신뢰도 |
| `warnings` | 판독 실패, 낮은 신뢰도, 손상 파일 등 경고 |

PoC 기본 후보와 파일 유형별 라우팅은 [ADR-0072: Parser/OCR 기본 엔진 선택 및 파일 유형별 라우팅 정책](ADR-0072-parser-ocr-engine-routing-policy.md)을 따른다. 요약은 다음과 같다.

| 입력 유형 | 1차 후보 | 보조 후보 | 비고 |
| --- | --- | --- | --- |
| PDF | `opendataloader-pdf` | `MinerU` | Markdown/JSON/HTML과 bounding box 추출 우선 |
| 복합 PDF/표/다단 문서 | `opendataloader-pdf` | `MinerU` | PoC 초기에는 복합 PDF도 `opendataloader-pdf` 우선 |
| 이미지/스캔 PDF | `PaddleOCR` | `MinerU`, VLM OCR | 텍스트 레이어가 없거나 OCR 필요 시 OCR 경로 |
| HWP/HWPX | `rhwp` | `document-processor` | HWP/HWPX 전용 Rust 기반 엔진 우선 |

## 대안

| 대안 | 판단 |
| --- | --- |
| 단일 OCR/파서에 직접 의존 | 초기 구현은 빠르지만 교체 비용과 장애 영향이 크다. |
| 파일 유형별 라이브러리 직접 호출 | 구현이 흩어지고 결과 포맷이 달라져 후속 검토 로직이 복잡해진다. |
| Adapter + 표준 IR 구조 | 초기 인터페이스 설계가 필요하지만 교체 가능성과 테스트 가능성이 높다. |
| 모든 문서를 VLM 하나로 처리 | 복합 문서에는 유리할 수 있으나 비용, GPU, 재현성, 온프렘 제약이 크다. |

## 결정 근거

- 문서 파서와 OCR 후보는 프로젝트 진행 중 변경 가능성이 높다.
- 광고 화면 Annotation과 근거 매핑을 위해 bounding box, 페이지, 블록 단위 표준 출력이 필요하다.
- 온프렘 이전 가능성을 고려하면 GPU 의존 OCR/VLM은 필수 경로가 아니라 fallback 또는 실험 경로로 두어야 한다.
- PDF, HWP/HWPX, 이미지 OCR 결과를 같은 후속 검토 파이프라인에 넣으려면 표준 IR이 필요하다.

## 영향

- 초기 구현 시 파서별 Adapter는 ADR-0065의 `NormalizedDocument` v1 계약을 먼저 만족해야 한다.
- OCR/파서 품질 평가는 도구별 raw output이 아니라 `NormalizedDocument` 기준으로 비교한다.
- `parser_name`, `parser_version`, `confidence`, `warnings`를 DB에 저장해 재현성과 감사 추적성을 확보한다.
- 특정 도구 교체 시 ReviewPipeline, RAG, 화면 표시 로직은 변경하지 않는 것을 목표로 한다.

## 후속 조치

- `NormalizedDocument` v1 스키마는 ADR-0065 기준으로 DB 명세와 API 명세에 반영한다.
- HWP/HWPX Text IR과 offset 저장 기준은 ADR-0052를 따른다.
- Parser/OCR 기본 엔진과 파일 유형별 라우팅은 ADR-0072를 따른다.
- PDF, 이미지, HWP/HWPX 샘플 광고물로 파서 후보를 비교하는 PoC 테스트셋을 만든다.
- 파서/OCR Adapter별 최소 계약은 ADR-0065 기준으로 정의한다.
- GPU 필요 OCR/VLM은 온프렘 가능성과 자료 반출 제한 ADR을 확인한 뒤 활성화한다.
- 좌표 체계는 ADR-0015와 ADR-0066 기준 원본 좌표와 정규화 좌표를 함께 사용한다.

## 관련 문서

- `docs/reference-repositories.md`
- `docs/functional-specification.md`
- `docs/database-specification.md`
- `docs/screen-specification.md`
- `docs/adr/ADR-0065-normalized-document-schema-and-adapter-contract.md`
- `docs/adr/ADR-0072-parser-ocr-engine-routing-policy.md`
