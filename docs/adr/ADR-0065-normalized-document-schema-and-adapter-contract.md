# ADR-0065: NormalizedDocument 공통 출력 스키마 및 Parser/OCR Adapter 계약 정책

## 상태

Accepted

## 배경

ADR-0014는 문서 파서와 OCR을 교체 가능한 Adapter 구조로 설계하고 내부 표준 출력으로 `NormalizedDocument`를 사용하기로 했다. ADR-0008은 Parser/OCR 어댑터가 입력 파일을 `NormalizedDocument`로 변환하는 계약 테스트를 필수로 정했다. ADR-0051, ADR-0052, ADR-0015는 Annotation, Text IR, 좌표 체계가 `NormalizedDocument`의 텍스트 블록과 좌표 정보를 사용한다고 정의한다.

그러나 `NormalizedDocument`의 v1 필수 필드와 adapter별 최소 출력 계약이 명확하지 않으면 PDF, 이미지, HWP/HWPX 파서가 서로 다른 구조를 반환하고 후속 ReviewPipeline, RAG, Annotation, 테스트 fixture가 파서별 분기 로직에 의존하게 된다.

## 결정

`NormalizedDocument`는 **v1 스키마를 먼저 확정하고 Parser/OCR Adapter의 공통 출력 계약으로 사용**한다.

| 항목 | 결정 |
| --- | --- |
| 스키마 이름 | `NormalizedDocument` |
| 버전 | `normalized-document-v1` |
| 적용 대상 | PDF, 이미지/스캔 PDF, HWP/HWPX, 복합 레이아웃 문서 |
| 계약 위치 | API/OpenAPI schema, backend shared schema, adapter contract test |
| DB 저장 | `ocr_text_blocks`, `layout_blocks`, `annotations`, `parser_artifacts` metadata로 영속화 |
| raw output | 업무 로직 직접 사용 금지. ADR-0067 기준 Object Storage에 보존하고 DB에는 참조 ID만 저장 |

업무 로직, RAG, Annotation, 리포트는 개별 파서의 raw output을 직접 읽지 않고 `NormalizedDocument` v1 필드만 사용한다.

## NormalizedDocument v1 필수 구조

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `documentId` | Y | 정규화 문서 산출물 ID |
| `sourceFileId` | Y | 원본 파일 ID |
| `reviewId` | Y | 검토 ID |
| `sourceFileType` | Y | `jpg`, `jpeg`, `png`, `pdf`, `hwp`, `hwpx` |
| `parserName` | Y | 사용 adapter 이름 |
| `parserVersion` | Y | adapter 또는 모델 버전 |
| `parserRuleVersion` | Y | 정규화/구조 추출 rule set 버전 |
| `irVersion` | Y | `normalized-document-v1` |
| `pages` | Y | 페이지 또는 논리 문서 단위 목록 |
| `textBlocks` | Y | OCR/parser 텍스트 블록 목록 |
| `layoutBlocks` | Y | 제목/본문/표/배너/버튼/고지문구 등 레이아웃 블록 목록 |
| `tables` | N | 표 구조 목록 |
| `warnings` | Y | 판독 실패, 낮은 신뢰도, 구조 인식 실패 등 경고 목록 |
| `confidence` | Y | 문서 전체 추출 신뢰도와 상태 |
| `rawArtifactRef` | N | 원본 parser/OCR 산출물 저장 위치 또는 artifact ID |
| `createdAt` | Y | 산출 시각 |

목록형 필드는 비어 있을 수 있지만 `null`이 아니라 빈 배열로 반환한다.

## TextBlock 계약

`textBlocks`는 ADR-0052의 Text IR 기준을 따른다.

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `textBlockId` | Y | 텍스트 블록 ID. DB에서는 `ocr_text_blocks.ocr_block_id` |
| `pageNo` | 조건부 | PDF/이미지/스캔 PDF는 필수. HWP/HWPX 논리 구조 블록은 null 허용 |
| `textPath` | 조건부 | HWP/HWPX, 표, 구조 문서에서는 필수. 이미지 OCR은 null 허용 |
| `textBlockType` | Y | `PARAGRAPH`, `TABLE_CELL`, `TITLE`, `NOTICE`, `FOOTNOTE`, `BUTTON`, `BANNER` 등 |
| `rawText` | Y | parser/OCR 원문에 가까운 텍스트 |
| `normalizedText` | Y | 화면 표시, 검색, 하이라이트용 정규화 텍스트 |
| `rawStartOffset`, `rawEndOffset` | 조건부 | raw text 기준 offset. 이미지 OCR은 null 허용 |
| `normalizedStartOffset`, `normalizedEndOffset` | 조건부 | normalized text 기준 offset. 텍스트 하이라이트 대상이면 필수 |
| `coordinates` | 조건부 | 이미지/PDF/스캔 PDF 등 좌표 기반 표시 대상이면 필수 |
| `confidenceScore` | Y | 0.0~1.0 |
| `confidenceStatus` | Y | ADR-0053 기준 `READABLE`, `LOW_CONFIDENCE`, `UNREADABLE` |
| `metadata` | N | parser별 확장 정보. 업무 로직 필수 의존 금지 |

## LayoutBlock 계약

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `layoutBlockId` | Y | 레이아웃 블록 ID |
| `pageNo` | 조건부 | 페이지 기반 문서는 필수 |
| `blockType` | Y | `TITLE`, `BODY`, `NOTICE`, `FOOTNOTE`, `TABLE`, `BUTTON`, `BANNER`, `IMAGE` 등 |
| `relatedTextBlockIds` | Y | 연결된 `textBlockId` 목록. 없으면 빈 배열 |
| `coordinates` | 조건부 | 좌표 기반 표시 대상이면 필수 |
| `style` | N | 글자 크기, 색상, 굵기, 배경 등 |
| `confidenceScore` | Y | 구조 인식 신뢰도 |
| `confidenceStatus` | Y | ADR-0053 기준 `STRUCTURED`, `PARTIALLY_STRUCTURED`, `UNSTRUCTURED` |

## Coordinate 계약

좌표는 ADR-0015 기준 원본 좌표와 정규화 좌표를 함께 표현한다.

| 필드 | 설명 |
| --- | --- |
| `sourceWidth`, `sourceHeight`, `sourceUnit` | 원본 페이지/이미지 크기와 단위 |
| `x`, `y`, `width`, `height` | 원본 기준 좌표 |
| `normalizedX`, `normalizedY`, `normalizedWidth`, `normalizedHeight` | 0~1 정규화 좌표 |
| `rotation` | 원본 페이지 회전값 |
| `coordinateConfidence` | 좌표 추출 신뢰도 |

좌표가 없는 검토 가능 문구는 TextBlock으로 저장하되 `coordinates`는 null로 둘 수 있다. DB/API 영속화 세부 기준은 ADR-0066을 따르며, 좌표가 없는 Annotation은 ADR-0051 기준 `LIST_ONLY`, `UNAVAILABLE`, `NOT_LOCATED` 등으로 처리한다.

## Adapter 계약

모든 Parser/OCR Adapter는 다음 계약을 만족해야 한다.

| 계약 | 기준 |
| --- | --- |
| 입력 | `sourceFileId`, 파일 위치, 파일 유형, review context |
| 출력 | `NormalizedDocument` v1 |
| 실패 | 복구 가능 오류와 복구 불가 오류를 ADR-0059 기준 error code로 반환 |
| 신뢰도 | ADR-0053 기준 score와 status를 함께 반환 |
| 버전 | `parserName`, `parserVersion`, `parserRuleVersion`, `irVersion` 필수 |
| raw output | `rawArtifactRef`로만 연결하고 ReviewPipeline이 직접 의존하지 않음 |
| 테스트 | synthetic fixture 기반 contract test 필수 |

Adapter별 raw output은 감사 추적과 재처리를 위해 보존할 수 있지만, raw output 구조 변경은 ReviewPipeline, RAG, Annotation UI를 깨뜨리지 않아야 한다.

## 저장 기준

PoC에서는 별도 `normalized_documents` 테이블을 만들지 않고 다음 방식으로 영속화한다.

| NormalizedDocument 영역 | 저장 위치 |
| --- | --- |
| document metadata | `review_steps` 또는 parser result artifact metadata |
| `textBlocks` | `ocr_text_blocks` |
| `layoutBlocks` | `layout_blocks` |
| `coordinates` | `ocr_text_blocks`, `layout_blocks`, `annotations` 좌표 필드 |
| `warnings`, raw output | ADR-0067 기준 Object Storage artifact + `parser_artifacts.raw_artifact_id` |
| 신뢰도 | `confidence_score`, `confidence_status`, `confidence_policy_version` |

`ocr_text_blocks` 명칭은 PoC에서는 유지하되, 의미상 OCR 전용이 아니라 OCR/VLM/parser 텍스트 IR 블록 저장소로 사용한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| A. 최소 필드만 정의하고 구현 중 확장 | 빠르지만 adapter별 출력 편차와 테스트 불안정성이 커져 기각 |
| B. `NormalizedDocument` v1 스키마를 먼저 확정 | 교체 가능성과 계약 테스트 기준이 명확해 채택 |
| C. 파서별 raw output을 저장하고 후처리에서 통합 | 원본 보존은 좋지만 후속 로직 복잡도와 파서 종속성이 커져 기각 |
| D. OCR/Text IR/Annotation 세부 스키마를 모두 한 번에 완전 확정 | 완성도는 높지만 PoC 초기 결정 부담이 커져 기각 |

## 결정 근거

- Parser/OCR 교체 가능성을 유지하려면 후속 로직이 raw output이 아니라 표준 계약에 의존해야 한다.
- HWP/HWPX Text IR, 이미지/PDF 좌표, Annotation 표시 정책을 하나의 공통 산출물로 연결해야 한다.
- Adapter contract test를 만들려면 필수 필드와 null/empty array 기준이 명확해야 한다.
- raw output 보존과 업무 로직 의존을 분리하면 감사 추적과 유지보수를 동시에 만족할 수 있다.

## 영향

- Parser/OCR adapter 구현은 `NormalizedDocument` v1 schema를 먼저 통과해야 한다.
- `ocr_text_blocks`, `layout_blocks`, `annotations`는 `NormalizedDocument` 영속화 결과로 해석한다.
- API/OpenAPI에는 `NormalizedDocument`, `TextBlock`, `LayoutBlock`, ADR-0066 기준 `Coordinate` schema를 추가한다.
- Mock/Fixture 테스트는 raw parser output이 아니라 `NormalizedDocument` fixture를 기준으로 작성한다.
- 파서별 raw output 변경은 ReviewPipeline 변경 사유가 아니라 adapter 내부 변경으로 처리한다.

## 후속 조치

- `openapi/openapi.yaml`에 `NormalizedDocument`, `TextBlock`, `LayoutBlock`, `Coordinate` schema를 추가한다.
- backend shared schema에 `NormalizedDocument` v1 모델을 정의한다.
- Parser/OCR adapter contract test fixture를 추가한다.
- 기존 `ocr_text_blocks`, `layout_blocks` DB 필드가 v1 필수 저장 항목을 모두 담는지 구현 시 확인한다.
- raw artifact 저장 위치, 보존 기간, 접근 정책은 ADR-0067을 따른다.

## 관련 문서

- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/functional-specification.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0008-tdd-and-test-scope.md`
- `docs/adr/ADR-0014-pluggable-document-parser-ocr.md`
- `docs/adr/ADR-0015-ad-coordinate-system.md`
- `docs/adr/ADR-0051-annotation-display-policy.md`
- `docs/adr/ADR-0052-text-ir-offset-policy.md`
- `docs/adr/ADR-0053-confidence-threshold-policy.md`
- `docs/adr/ADR-0064-ci-cd-quality-gate-test-split-policy.md`
- `docs/adr/ADR-0066-coordinate-persistence-and-api-response-policy.md`
- `docs/adr/ADR-0067-parser-ocr-raw-artifact-storage-retention-policy.md`
