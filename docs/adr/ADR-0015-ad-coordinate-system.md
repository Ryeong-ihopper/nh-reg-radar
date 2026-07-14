# ADR-0015: 광고 화면 좌표 체계

## 상태

Accepted

## 배경

광고 화면 검토 UI는 OCR/VLM이 추출한 문구, AI 검토 항목, 문제 영역 Annotation을 원본 광고물 위에 Bounding Box 또는 하이라이트로 표시해야 한다. 입력 파일은 이미지, PDF, 스캔 PDF, 모바일 캡처, 배너 등으로 다양하며, 프론트엔드에서는 확대/축소, 페이지 이동, 화면 크기 변경이 발생한다.

좌표를 렌더링 화면 기준으로만 저장하면 뷰어 크기나 배율이 바뀔 때 재현성이 떨어진다. 반대로 원본 좌표만 저장하면 프론트엔드 표시 시 매번 변환이 필요하고, PDF와 이미지의 단위 차이를 처리해야 한다.

## 결정

광고 화면 좌표는 원본 기준 좌표와 정규화 좌표를 함께 저장한다.

원본 기준 좌표는 감사 추적, 재처리, 원본 파일 기준 재현을 위한 기준값으로 사용한다. 정규화 좌표는 프론트엔드 렌더링, 확대/축소, 반응형 표시를 위한 표시값으로 사용한다.

| 좌표 유형 | 용도 | 기준 |
| --- | --- | --- |
| 원본 좌표 | 파서/OCR 결과 재현, 원본 파일 기준 검증, 감사 추적 | 원본 페이지 또는 이미지의 실제 width/height 기준 |
| 정규화 좌표 | 프론트엔드 Bounding Box 표시, 확대/축소, 미리보기 렌더링 | 좌상단 `(0, 0)`, 우하단 `(1, 1)` 범위 |
| 렌더링 좌표 | 브라우저 표시용 일시 값 | 저장하지 않고 화면에서 계산 |

DB와 API는 원본 좌표와 정규화 좌표를 모두 표현할 수 있어야 한다. 렌더링 좌표는 저장하지 않는다.

## 좌표 모델

좌표는 기본적으로 좌상단 기준의 사각형으로 표현한다.

| 필드 | 설명 |
| --- | --- |
| `page_no` | PDF/다중 페이지 문서의 페이지 번호 |
| `source_width` | 원본 페이지 또는 이미지 너비 |
| `source_height` | 원본 페이지 또는 이미지 높이 |
| `source_unit` | px, pt 등 원본 좌표 단위 |
| `x` | 원본 좌표 X |
| `y` | 원본 좌표 Y |
| `width` | 원본 좌표 기준 너비 |
| `height` | 원본 좌표 기준 높이 |
| `normalized_x` | 정규화 X |
| `normalized_y` | 정규화 Y |
| `normalized_width` | 정규화 너비 |
| `normalized_height` | 정규화 높이 |
| `rotation` | 원본 페이지 회전값, 없으면 0 |
| `coordinate_confidence` | 좌표 추출 신뢰도 |

정규화 좌표는 다음 방식으로 계산한다.

```text
normalized_x = x / source_width
normalized_y = y / source_height
normalized_width = width / source_width
normalized_height = height / source_height
```

PDF처럼 원본 단위가 pt인 경우에도 `source_width`, `source_height`, `source_unit`을 함께 저장하고, 정규화 좌표는 동일한 방식으로 계산한다.

## 처리 원칙

| 상황 | 처리 |
| --- | --- |
| OCR/파서가 원본 좌표 제공 | 원본 좌표 저장 후 정규화 좌표 계산 |
| OCR/파서가 정규화 좌표만 제공 | 가능한 경우 원본 크기로 원본 좌표 역산, 불가능하면 원본 좌표 null 허용 |
| 좌표 신뢰도 낮음 | Annotation은 표시하되 `coordinate_confidence`와 경고를 함께 제공 |
| 좌표 없음 | 검토 항목은 저장하되 Annotation은 `hasAnnotation=false` 처리 |
| PDF 회전/크롭 존재 | 원본 기준 좌표계와 회전값을 저장하고 뷰어에서 변환 |
| 다중 페이지 문서 | 모든 Annotation에 `page_no` 필수 |

좌표 변환은 파서/OCR Adapter 또는 후처리 단계에서 수행하고, ReviewPipeline 이후의 업무 로직은 공통 좌표 모델만 사용한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| 원본 좌표만 저장 | 재현성은 좋지만 프론트엔드 확대/축소와 반응형 표시 구현이 반복적으로 복잡해진다. |
| 렌더링 좌표만 저장 | 화면 표시는 쉽지만 뷰어 크기, 배율, 기기 해상도 변경 시 재현성이 낮다. |
| 정규화 좌표만 저장 | 화면 표시에는 유리하지만 원본 파일 기준 검증과 파서 결과 추적이 약하다. |
| 원본 좌표와 정규화 좌표 함께 저장 | 저장 필드는 늘어나지만 재현성과 화면 표시 안정성을 모두 확보할 수 있다. |

## 결정 근거

- 광고심의 결과는 원본 광고물의 어느 위치가 문제인지 재현 가능해야 한다.
- 프론트엔드 검토 UI는 확대/축소, 페이지별 보기, 반응형 미리보기를 지원해야 한다.
- PDF, 이미지, 스캔 문서의 좌표 단위가 다를 수 있어 단일 좌표계만으로는 부족하다.
- Parser/OCR 도구 교체 시에도 후속 ReviewPipeline과 화면 표시 로직이 안정적으로 유지되어야 한다.
- 좌표 없는 AI 판단도 존재할 수 있으므로 Annotation은 검토 항목의 필수 조건이 아니라 선택 정보로 다룬다.

## 영향

- `NormalizedDocument`, `ocr_text_blocks`, `layout_blocks`, `annotations`는 ADR-0065의 `Coordinate` 계약에 따라 원본 좌표와 정규화 좌표를 표현해야 한다.
- Annotation 조회 API는 프론트엔드가 직접 렌더링 좌표를 계산할 수 있는 원본 크기와 정규화 좌표를 제공해야 한다.
- 프론트엔드는 저장 좌표를 그대로 쓰지 않고 현재 뷰어 크기와 배율에 맞춰 렌더링 좌표를 계산한다.
- 좌표 변환 테스트와 다중 페이지 PDF 테스트가 필요하다.
- 기존 명세의 “OCR 좌표 체계 미확정” 항목은 본 ADR과 ADR-0066 기준으로 정리한다.

## 후속 조치

- DB 명세의 `ocr_text_blocks`, `layout_blocks`, `annotations`에 ADR-0066 기준 정규화 좌표와 원본 크기 필드를 반영한다.
- API 명세의 Annotation 응답은 ADR-0066 기준 `Coordinate` object로 원본 좌표, 정규화 좌표, 원본 크기, 회전값, 좌표 신뢰도를 반영한다.
- 테스트케이스에 이미지, PDF, 다중 페이지, 회전 페이지, 좌표 없음 케이스를 추가한다.
- 화면설계서의 S-007 광고 화면 검토 UI에 좌표 변환 책임을 명시한다.
- `ADR-0014`의 `NormalizedDocument.bounding_boxes` 정의는 ADR-0065의 `Coordinate` 계약과 본 ADR 기준으로 구체화한다.

## 관련 문서

- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/functional-specification.md`
- `docs/screen-specification.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0014-pluggable-document-parser-ocr.md`
- `docs/adr/ADR-0065-normalized-document-schema-and-adapter-contract.md`
- `docs/adr/ADR-0066-coordinate-persistence-and-api-response-policy.md`
