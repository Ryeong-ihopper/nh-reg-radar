# ADR-0072: Parser/OCR 기본 엔진 선택 및 파일 유형별 라우팅 정책

## 상태

Superseded

파일 유형별 Parser/OCR 라우팅과 HWP/HWPX 구성은 [ADR-0079: HWP/HWPX 이중 원천 Hybrid Parser 구성 정책](ADR-0079-hwp-hwpx-hybrid-parser-composition.md)으로 대체되었다. PDF·이미지 라우팅과 Adapter 경계 원칙은 ADR-0079에서 유지한다.

## 배경

ADR-0014는 문서 파서와 OCR을 교체 가능한 Adapter 구조로 설계하기로 했다. ADR-0065는 모든 Parser/OCR Adapter가 `NormalizedDocument` v1을 반환해야 한다고 정했고, ADR-0067은 raw output을 업무 로직이 직접 참조하지 않도록 분리했다.

초기 업로드 허용 파일은 ADR-0037 기준 `jpg`, `jpeg`, `png`, `pdf`, `hwp`, `hwpx`이며, 각 파일 유형마다 적합한 엔진이 다르다. 특히 HWP/HWPX는 한국 문서 포맷 특성이 강하고, Annotation UI는 ADR-0052 기준 `textBlockId + normalized offset`을 사용하므로 안정적인 Text IR 생성이 중요하다.

따라서 PoC 기본 엔진과 파일 유형별 라우팅 기준을 확정하되, 특정 엔진에 업무 로직이 직접 의존하지 않도록 Adapter 경계를 유지한다.

## 결정

Parser/OCR 기본 엔진은 **파일 유형별 1차 엔진 + 보조 엔진**으로 라우팅한다.

| 파일 유형 | 1차 엔진 | 보조/대체 엔진 | 비고 |
| --- | --- | --- | --- |
| PDF | `opendataloader-pdf` | `MinerU` | Markdown/JSON/HTML, bounding box 추출 우선 |
| 복합 PDF/표/다단 문서 | `opendataloader-pdf` | `MinerU` | PoC 초기에는 복합 PDF도 `opendataloader-pdf`를 우선 적용 |
| 스캔 PDF | `PaddleOCR` | `opendataloader-pdf`, `MinerU`, VLM OCR | 텍스트 레이어가 없거나 OCR 필요 시 OCR 경로 |
| JPG/JPEG/PNG | `PaddleOCR` | VLM OCR | 이미지 광고, 모바일 캡처, 배너 OCR |
| HWP/HWPX | `rhwp` | `document-processor` | HWP/HWPX 전용 Rust 기반 엔진 우선 |
| 기타 Office 형식 | PoC 초기 범위 제외 | `document-processor`, `MinerU` | ADR-0037 기준 초기 업로드 허용 대상 아님 |

모든 엔진은 직접 업무 로직에서 호출하지 않고 Adapter 뒤에 둔다.

```text
DocumentIngestionService
  -> ParserRouter
      -> PdfParserAdapter(opendataloader-pdf)
      -> ScannedPdfOcrAdapter(PaddleOCR)
      -> ImageOcrAdapter(PaddleOCR)
      -> HwpHwpxParserAdapter(rhwp)
      -> FallbackParserAdapter(MinerU/document-processor/VLM OCR)
  -> NormalizedDocument v1
  -> ReviewPipeline / RAG / Annotation / Report
```

## 교체 가능성 원칙

| 원칙 | 기준 |
| --- | --- |
| 직접 의존 금지 | ReviewPipeline, RAG, Annotation, 리포트는 엔진 SDK/CLI output을 직접 읽지 않는다 |
| Adapter 경계 | 각 엔진은 Adapter 내부 구현으로만 존재한다 |
| 표준 출력 | Adapter 출력은 ADR-0065 기준 `NormalizedDocument` v1이어야 한다 |
| 계약 테스트 | 엔진별 Adapter는 `NormalizedDocument` fixture 기반 contract test를 통과해야 한다 |
| raw output | raw output은 ADR-0067 기준 artifact로 보존하되 업무 로직 의존 금지 |
| 엔진 교체 | 엔진 교체는 Adapter와 fixture 변경으로 처리하고 후속 업무 로직 변경을 최소화한다 |
| 버전 추적 | `parserName`, `parserVersion`, `parserRuleVersion`, `irVersion`을 저장한다 |

`rhwp`를 사용하더라도 시스템 내부 계약은 `rhwp` 구조가 아니라 `NormalizedDocument` v1이다. HWP/HWPX 하이라이트는 ADR-0052 기준 `textBlockId`, `normalizedStartOffset`, `normalizedEndOffset`, `matchedText`를 사용한다.

## 라우팅 기준

ParserRouter는 업로드 파일의 확장자, MIME type, PDF 텍스트 레이어 유무, OCR 필요 여부를 기준으로 Adapter를 선택한다.

| 조건 | 선택 Adapter |
| --- | --- |
| `.hwp`, `.hwpx` | `HwpHwpxParserAdapter(rhwp)` |
| `.pdf`이고 텍스트 레이어/구조 추출 가능 | `PdfParserAdapter(opendataloader-pdf)` |
| `.pdf`이고 텍스트 레이어가 없거나 스캔 문서로 판단 | `ScannedPdfOcrAdapter(PaddleOCR)` |
| `.pdf`이고 표/다단/복합 레이아웃 | 우선 `PdfParserAdapter(opendataloader-pdf)`, 품질 미달 시 `MinerU` 재처리 후보 |
| `.jpg`, `.jpeg`, `.png` | `ImageOcrAdapter(PaddleOCR)` |
| 1차 엔진 실패 | 오류 유형과 정책에 따라 보조 엔진 재처리 또는 확인 필요 처리 |

보조 엔진 사용은 자동 fallback이라기보다 재처리 후보로 관리한다. 엔진 장애, 낮은 confidence, 구조 인식 실패는 ADR-0053, ADR-0059, ADR-0073 기준으로 상태와 경고를 남긴다.

## 대안

| 대안 | 판단 |
| --- | --- |
| A. `document-processor` 중심 통합 파서 우선 | Adapter 수는 줄지만 HWP/HWPX 전용 품질과 PDF bbox 품질 검증이 약해 기각 |
| B. PDF/복합 PDF는 `opendataloader-pdf`, HWP/HWPX는 `rhwp`, 이미지/스캔 PDF는 `PaddleOCR` 우선 | 파일 유형별 강점을 살리면서 교체 가능성을 유지해 채택 |
| C. `MinerU`를 PDF/복합 문서 기본 엔진으로 사용 | 복합 문서에 강점이 있을 수 있으나 설치, 운영, 온프렘 검증 부담이 있어 보조로 둠 |
| D. 모든 문서를 VLM/OCR 중심으로 처리 | 비용, 속도, 재현성, 온프렘 제약이 커 기각 |
| E. 기본 엔진을 정하지 않고 Adapter mock부터 구현 | 실제 샘플 품질 검증과 Annotation/RAG 구현이 늦어져 기각 |

## 결정 근거

- HWP/HWPX는 포맷 특성이 강하므로 전용 Rust 기반 엔진인 `rhwp`를 우선 검증하는 것이 합리적이다.
- PDF와 복합 PDF는 PoC 초기에는 `opendataloader-pdf`를 우선 사용해 Markdown/JSON/HTML과 bounding box 산출물을 표준화한다.
- 스캔 PDF와 이미지는 텍스트 레이어가 없으므로 OCR 엔진인 `PaddleOCR`이 기본 경로에 적합하다.
- `MinerU`와 VLM OCR은 설치/리소스/온프렘 제약이 있으므로 기본 경로가 아니라 보조 또는 실험 경로로 두는 것이 안전하다.
- 엔진 선택보다 중요한 것은 업무 로직이 `NormalizedDocument` v1에만 의존하도록 유지하는 것이다.

## 영향

- ADR-0014의 PoC 기본 후보 표는 본 ADR의 라우팅 정책으로 구체화한다.
- ParserRouter는 파일 유형과 문서 특성에 따라 Adapter를 선택해야 한다.
- `HwpHwpxParserAdapter`의 1차 구현은 `rhwp`를 사용한다.
- `PdfParserAdapter`의 1차 구현은 일반 PDF와 복합 PDF 모두 `opendataloader-pdf`를 우선 사용한다.
- `ImageOcrAdapter`와 스캔 PDF OCR 경로는 `PaddleOCR`을 우선 사용한다.
- 테스트케이스에 엔진 라우팅, HWP/HWPX `rhwp` Text IR, 복합 PDF `opendataloader-pdf` 우선 처리, 엔진 교체 contract test를 추가한다.

## 후속 조치

- `ParserRouter` 설정을 YAML 또는 동등한 설정 파일로 분리해 엔진 우선순위를 변경 가능하게 둔다.
- `rhwp`, `opendataloader-pdf`, `PaddleOCR` Adapter의 `NormalizedDocument` fixture를 만든다.
- 샘플 HWP/HWPX, 일반 PDF, 복합 PDF, 스캔 PDF, 이미지 광고물로 contract test와 수동 품질 검증을 수행한다.
- `MinerU`와 VLM OCR은 보조 엔진으로 설치 가능성, 라이선스, 리소스, 온프렘 이전성을 별도 검증한다.
- 품질 미달 시 보조 엔진 재처리 조건과 최종 산출물 선택 기준은 ADR-0073을 따른다.

## 관련 문서

- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/functional-specification.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0014-pluggable-document-parser-ocr.md`
- `docs/adr/ADR-0037-file-upload-allowlist-and-size-limit.md`
- `docs/adr/ADR-0052-text-ir-offset-policy.md`
- `docs/adr/ADR-0053-confidence-threshold-policy.md`
- `docs/adr/ADR-0065-normalized-document-schema-and-adapter-contract.md`
- `docs/adr/ADR-0067-parser-ocr-raw-artifact-storage-retention-policy.md`
- `docs/adr/ADR-0073-parser-ocr-quality-rerun-policy.md`
