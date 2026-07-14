# ADR-0051: 검토 UI Annotation 표현 방식

| 항목 | 내용 |
| --- | --- |
| 상태 | Accepted |
| 날짜 | 2026-07-11 |
| 관련 문서 | 기능명세서, 화면설계서, 화면-API 매핑표, API 명세서, DB 명세서, 테스트케이스 |
| 관련 ADR | ADR-0003, ADR-0004, ADR-0010, ADR-0030, ADR-0037 |

## 배경

광고물 파일은 초기 PoC에서 `jpg`, `jpeg`, `png`, `pdf`, `hwp`, `hwpx`를 허용한다. 이미지와 PDF는 화면 좌표 기반 Bounding Box 표시가 자연스럽지만, HWP/HWPX는 브라우저 미리보기 좌표가 안정적이지 않을 수 있고 문서 파서가 텍스트 구조를 우선 제공할 가능성이 높다.

또한 AI/OCR/parser 결과는 항상 정확한 위치를 제공하지 않는다. 일부 문구만 특정되거나, 문서 단위 이슈처럼 특정 위치가 없는 검토 결과도 발생할 수 있다. 위치를 특정하지 못했다는 이유로 검토 결과가 누락되면 업무상 위험이 크므로, 표시 위치와 검토 결과 존재 여부를 분리해야 한다.

## 결정

검토 UI Annotation은 파일 형식과 위치 식별 가능 여부에 따라 표시 방식을 분리한다.

| 파일 형식 | 기본 표시 방식 | 설명 |
| --- | --- | --- |
| `jpg`, `jpeg`, `png` | `BOX` | 이미지 미리보기 위에 Bounding Box를 표시한다. |
| `pdf` | `BOX` | PDF 페이지 미리보기 위에 Bounding Box를 표시한다. |
| `hwp`, `hwpx` | `TEXT_HIGHLIGHT` | 파서가 추출한 텍스트 뷰에서 문제 문구를 하이라이트한다. |
| 파서/좌표 불가 | `LIST_ONLY` 또는 `UNAVAILABLE` | 위치 표시는 생략하되 검토 항목 목록과 상세 패널에는 반드시 표시한다. |

Annotation 단위로 다음 상태를 관리한다.

| 상태 | 의미 | 화면 처리 |
| --- | --- | --- |
| `LOCATED` | 위치가 충분히 특정됨 | Box 또는 텍스트 하이라이트를 일반 강조로 표시 |
| `PARTIALLY_LOCATED` | 일부 문구만 특정됨 | 특정된 부분만 표시하고 “일부 표시” 배지를 표시 |
| `NOT_LOCATED` | 위치를 특정하지 못함 | 검토 항목 목록과 상세 패널에 표시하고 “위치 확인 필요” 배지를 표시 |
| `LOW_CONFIDENCE` | 위치 신뢰도가 낮음 | 약한 강조 또는 목록 표시 후 “위치 신뢰도 낮음” 배지를 표시 |
| `DOCUMENT_LEVEL_ISSUE` | 문서 전체에 적용되는 이슈 | 문서 단위 이슈로 목록/상세 패널에 표시 |

API/DB에는 다음 표현 필드를 둔다. 좌표와 텍스트 위치 정보는 [ADR-0065: NormalizedDocument 공통 출력 스키마 및 Parser/OCR Adapter 계약 정책](ADR-0065-normalized-document-schema-and-adapter-contract.md)의 `TextBlock` 및 `Coordinate` 계약을 기준으로 생성하고, API 응답 구조는 [ADR-0066: Coordinate 필드 영속화 및 API 응답 구조 정합화 정책](ADR-0066-coordinate-persistence-and-api-response-policy.md)을 따른다.

| 필드 | 설명 |
| --- | --- |
| `annotationDisplayMode` / `annotation_display_mode` | `BOX`, `TEXT_HIGHLIGHT`, `LIST_ONLY`, `UNAVAILABLE` |
| `annotationStatus` / `annotation_status` | `LOCATED`, `PARTIALLY_LOCATED`, `NOT_LOCATED`, `LOW_CONFIDENCE`, `DOCUMENT_LEVEL_ISSUE` |
| `locationConfidence` / `location_confidence` | 위치 식별 신뢰도. 0.0~1.0 범위 |
| `displayReason` / `display_reason` | `MATCHED_BOX`, `MATCHED_TEXT`, `PARTIAL_TEXT_MATCH`, `NO_TEXT_SPAN`, `PARSER_LOW_CONFIDENCE`, `DOCUMENT_LEVEL_ISSUE` 등 |
| `x`, `y`, `width`, `height` | `BOX` 표시용 좌표. 위치가 없으면 `null` 허용 |
| `textBlockId`, `normalizedStartOffset`, `normalizedEndOffset`, `matchedText` | `TEXT_HIGHLIGHT` UI 표시용 텍스트 블록, normalized offset, 실제 매칭 문구 |
| `rawStartOffset`, `rawEndOffset`, `textPath` | 원문 재현과 감사 추적용 raw offset 및 문서 구조 경로. 세부 기준은 ADR-0052를 따른다. |

좌표 또는 텍스트 위치가 없는 검토 항목도 `review_items`에는 반드시 남긴다. `/reviews/{reviewId}/annotations` 응답에는 표시 가능한 Annotation뿐 아니라 `LIST_ONLY`, `UNAVAILABLE` 항목도 포함해 화면이 동일한 필터와 상세 패널 흐름으로 처리할 수 있게 한다.

## 대안

| 대안 | 내용 | 채택 여부 |
| --- | --- | --- |
| A | 모든 파일을 Bounding Box로 표시 | HWP/HWPX 좌표 안정성이 낮아 기각 |
| B | HWP/HWPX도 PDF 변환 후 Bounding Box 표시 | 변환 품질과 좌표 동기화 리스크가 커서 PoC 기본 방식으로는 기각 |
| C | 모든 파일을 텍스트 하이라이트로 표시 | 이미지 광고의 시각적 문제, 시인성 문제 표현이 약해 기각 |
| D | 위치가 있는 항목만 Annotation 표시 | 위치 미확정 검토 결과가 누락된 것처럼 보일 수 있어 기각 |
| E | 파일 형식별 표시 + 항목별 위치 상태 관리 | 채택 |

## 영향

- 화면은 이미지/PDF 미리보기 영역과 HWP/HWPX 텍스트 뷰를 모두 지원해야 한다.
- Annotation 클릭뿐 아니라 목록 항목 클릭도 동일하게 상세 패널을 열어야 한다.
- 위치가 없는 검토 항목은 오류가 아니라 정상 검토 결과로 취급한다.
- 리포트 생성 시 Annotation 포함 옵션은 Box/텍스트 하이라이트/목록형 위치 미확정 항목을 구분해 출력한다.

## 후속 과제

- HWP/HWPX parser 결과의 텍스트 offset 기준을 구현 단계에서 고정한다.
- HWP/HWPX 텍스트 하이라이트의 offset 기준은 ADR-0052를 따른다.
- `locationConfidence` 임계값과 확인 필요 처리는 ADR-0053을 따른다.
- 본사업 전환 시 HWP/HWPX PDF 변환 미리보기와 텍스트 하이라이트 병행 여부를 재검토한다.
