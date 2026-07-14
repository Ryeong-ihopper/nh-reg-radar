# ADR-0066: Coordinate 필드 영속화 및 API 응답 구조 정합화 정책

## 상태

Accepted

## 배경

ADR-0015는 광고 화면 좌표를 원본 기준 좌표와 정규화 좌표로 함께 저장하기로 결정했다. ADR-0065도 `NormalizedDocument`의 `Coordinate` 계약에 `sourceWidth`, `sourceHeight`, `sourceUnit`, 원본 좌표, 정규화 좌표, 회전값, 좌표 신뢰도를 포함했다.

하지만 현재 DB 명세의 `ocr_text_blocks`, `layout_blocks`, `annotations`는 `x`, `y`, `width`, `height` 중심으로 작성되어 있고, API 예시도 top-level 좌표 필드 중심이다. 이 상태로 구현하면 원본 좌표인지 렌더링 좌표인지 혼동될 수 있고, 프론트엔드가 확대/축소와 반응형 표시를 위해 필요한 원본 크기와 정규화 좌표를 안정적으로 받을 수 없다.

## 결정

Coordinate는 **DB에는 명시 컬럼으로 저장하고, API에는 `coordinate` object로 표준화**한다.

| 항목 | 결정 |
| --- | --- |
| DB 저장 | `ocr_text_blocks`, `layout_blocks`, `annotations`에 좌표 관련 명시 컬럼을 둔다 |
| API 응답 | `coordinate` object로 원본/정규화 좌표와 원본 크기를 함께 반환한다 |
| 렌더링 좌표 | 저장하지 않고 프론트엔드가 현재 뷰어 크기와 배율로 계산한다 |
| 좌표 없음 | `coordinate: null` 허용 |
| 원본 좌표만 있는 경우 | adapter 또는 후처리에서 정규화 좌표를 계산한다 |
| 정규화 좌표만 있는 경우 | 원본 크기가 있으면 원본 좌표를 역산하고, 불가능하면 원본 좌표 null 허용 |

## DB 컬럼 기준

좌표를 저장하는 테이블은 다음 필드를 공통으로 가진다.

| 컬럼 | 설명 |
| --- | --- |
| `source_width` | 원본 페이지 또는 이미지 너비 |
| `source_height` | 원본 페이지 또는 이미지 높이 |
| `source_unit` | 원본 좌표 단위. 예: `px`, `pt` |
| `x`, `y`, `width`, `height` | 원본 기준 좌표 |
| `normalized_x`, `normalized_y`, `normalized_width`, `normalized_height` | 0~1 정규화 좌표 |
| `rotation` | 원본 페이지 회전값. 기본 0 |
| `coordinate_confidence` | 좌표 추출 신뢰도 |

적용 대상은 다음과 같다.

| 테이블 | 적용 |
| --- | --- |
| `ocr_text_blocks` | OCR/parser 텍스트 블록 좌표 |
| `layout_blocks` | 레이아웃 블록 좌표 |
| `annotations` | UI 표시용 Annotation 좌표 |

HWP/HWPX 텍스트 하이라이트처럼 좌표 기반 표시가 아닌 경우 좌표 컬럼은 null을 허용하고 `text_block_id`, `normalized_start_offset`, `normalized_end_offset`을 사용한다.

## API Coordinate Object

API는 좌표를 top-level `x`, `y`, `width`, `height`로 흩어 반환하지 않고 다음 객체로 반환한다.

```json
{
  "sourceWidth": 1080,
  "sourceHeight": 1920,
  "sourceUnit": "px",
  "x": 120,
  "y": 240,
  "width": 320,
  "height": 48,
  "normalizedX": 0.1111,
  "normalizedY": 0.125,
  "normalizedWidth": 0.2963,
  "normalizedHeight": 0.025,
  "rotation": 0,
  "coordinateConfidence": 0.94
}
```

Annotation, TextBlock, LayoutBlock API schema는 모두 동일한 `Coordinate` object를 재사용한다. 좌표가 없으면 `coordinate`는 `null`이다.

## 계산 및 검증 기준

정규화 좌표는 ADR-0015 기준 계산식을 따른다.

```text
normalized_x = x / source_width
normalized_y = y / source_height
normalized_width = width / source_width
normalized_height = height / source_height
```

검증 기준은 다음과 같다.

| 검증 | 기준 |
| --- | --- |
| 값 범위 | `normalized_*`는 0 이상 1 이하 |
| 원본 크기 | 좌표가 있으면 `source_width`, `source_height`, `source_unit` 필요 |
| 다중 페이지 | PDF/스캔 PDF/다중 이미지 문서는 `page_no` 필요 |
| 회전 | PDF 회전이 있으면 `rotation`을 저장하고 프론트엔드에서 변환 |
| 좌표 없음 | Annotation 결과는 유지하고 `coordinate: null`, 상태는 ADR-0051 기준 |
| 좌표 신뢰도 | ADR-0053 기준 location/coordinate confidence와 함께 판단 |

## 대안

| 대안 | 판단 |
| --- | --- |
| A. 현재 `x/y/width/height`만 유지 | 단순하지만 ADR-0015, ADR-0065와 불일치해 기각 |
| B. DB에는 명시 컬럼, API에는 `Coordinate` object로 표준화 | 재현성, UI 변환, 테스트 계약이 명확해 채택 |
| C. DB/API 모두 JSONB coordinate로 저장 | 유연하지만 검색, 검증, OpenAPI 계약이 약해 기각 |
| D. DB는 원본 좌표만 저장하고 API에서 정규화 계산 | 저장은 단순하지만 계산 기준이 API 구현에 분산되어 기각 |

## 결정 근거

- DB 명시 컬럼은 좌표 검증, 인덱스, 디버깅, 감사 추적에 유리하다.
- API object는 프론트엔드가 동일한 구조로 이미지/PDF/Annotation/TextBlock 좌표를 처리하게 해준다.
- 원본 좌표와 정규화 좌표를 함께 보관해야 원본 재현성과 화면 렌더링 안정성을 모두 확보할 수 있다.
- `Coordinate` object를 재사용하면 OpenAPI, TypeScript 타입, adapter contract test를 단순화할 수 있다.

## 영향

- `ocr_text_blocks`, `layout_blocks`, `annotations` DB 명세에 `source_*`, `normalized_*`, `rotation`, `coordinate_confidence` 컬럼을 추가한다.
- API 명세의 Annotation/TextBlock/LayoutBlock/NormalizedDocument는 `Coordinate` schema를 참조한다.
- 화면 구현은 저장 좌표를 직접 CSS 좌표로 쓰지 않고 `coordinate.normalized*`를 현재 뷰어 크기에 곱해 렌더링 좌표를 계산한다.
- 좌표 없는 검토 결과는 실패가 아니라 `coordinate: null`인 정상 결과로 처리한다.
- 기존 “OCR 좌표 체계 미확정” 후속 항목은 ADR-0015와 ADR-0066 기준으로 해소한다.

## 후속 조치

- `openapi/openapi.yaml`에 `Coordinate` schema를 추가한다.
- DB migration 작성 시 세 테이블의 좌표 컬럼을 반영한다.
- 좌표 변환 contract test와 API 응답 테스트를 추가한다.
- 프론트엔드 Annotation 컴포넌트는 `coordinate` object 기준으로 렌더링 좌표를 계산한다.

## 관련 문서

- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/screen-specification.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0015-ad-coordinate-system.md`
- `docs/adr/ADR-0051-annotation-display-policy.md`
- `docs/adr/ADR-0053-confidence-threshold-policy.md`
- `docs/adr/ADR-0065-normalized-document-schema-and-adapter-contract.md`
