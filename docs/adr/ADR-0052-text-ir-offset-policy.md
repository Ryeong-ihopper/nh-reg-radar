# ADR-0052: HWP/HWPX 텍스트 IR 및 Offset 기준

| 항목 | 내용 |
| --- | --- |
| 상태 | Accepted |
| 날짜 | 2026-07-11 |
| 관련 문서 | 기능명세서, API 명세서, DB 명세서, 테스트케이스 |
| 관련 ADR | ADR-0014, ADR-0015, ADR-0051 |

## 배경

ADR-0051에서 HWP/HWPX 광고물은 미리보기 좌표 기반 Bounding Box 대신 텍스트 하이라이트로 표시하기로 했다. 이를 구현하려면 하이라이트 위치를 어떤 텍스트 기준으로 저장할지 정해야 한다.

HWP/HWPX parser 결과는 도구별로 문단, 표, 셀, 각주, 숨은 문단, 줄바꿈, 공백 처리 방식이 달라질 수 있다. parser 원본 offset만 저장하면 UI 표시가 흔들리고, 화면 표시용 정규화 텍스트 offset만 저장하면 원문 재현성과 감사 추적이 약해진다.

## 결정

텍스트 IR은 [ADR-0065: NormalizedDocument 공통 출력 스키마 및 Parser/OCR Adapter 계약 정책](ADR-0065-normalized-document-schema-and-adapter-contract.md)의 `textBlocks` 일부로 정의하고, HWP/HWPX Annotation은 텍스트 IR의 `textBlockId + normalized offset`을 UI 표시 기준으로 사용한다.

원문 재현과 감사 추적을 위해 raw 기준 위치와 normalized 기준 위치를 모두 저장한다.

| 기준 | 용도 |
| --- | --- |
| `rawText` | parser가 추출한 원문에 가까운 텍스트 |
| `normalizedText` | 화면 표시, 검색, 문구 매칭, 하이라이트에 사용할 정규화 텍스트 |
| `rawStartOffset`, `rawEndOffset` | parser 원문 기준 위치. 재처리, 감사 추적, 원문 비교에 사용 |
| `normalizedStartOffset`, `normalizedEndOffset` | UI 하이라이트 기준 위치 |
| `textPath` | 문서 구조 내 위치. 예: `body/section[1]/paragraph[3]`, `body/table[1]/row[2]/cell[3]` |
| `textBlockId` | 텍스트 IR 블록 식별자. DB에서는 `ocr_text_blocks.ocr_block_id`를 재사용 |
| `parserName`, `parserVersion`, `parserRuleVersion` | 파서와 rule set 버전 추적 |
| `irVersion` | Text IR 스키마 버전 |

UI는 `TEXT_HIGHLIGHT` Annotation을 표시할 때 `textBlockId`, `normalizedStartOffset`, `normalizedEndOffset`, `matchedText`를 우선 사용한다. raw offset은 화면 표시용으로 직접 사용하지 않는다.

## 텍스트 정규화 기준

PoC 기본 정규화는 재현 가능한 deterministic rule로 제한한다.

| 항목 | 기준 |
| --- | --- |
| Unicode | NFC 정규화 |
| 줄바꿈 | 화면 표시 단락 경계를 유지하되 CRLF는 LF로 통일 |
| 공백 | 연속 space/tab은 비교용 normalized text에서 단일 공백으로 축약 |
| 표 셀 | 셀 단위 `textPath`를 유지하고 셀 내부 텍스트만 정규화 |
| 숨은 문단/메모/각주 | parser가 추출한 경우 block metadata에 source type을 남긴다 |
| 원문 보존 | `rawText`와 raw offset은 parser 산출물 기준을 보존 |

정규화 rule이 바뀌면 `parserRuleVersion` 또는 `irVersion`을 올리고 기존 산출물 재처리 필요 여부를 기록한다.

## 대안

| 대안 | 내용 | 채택 여부 |
| --- | --- | --- |
| A | parser 원본 offset만 저장 | parser 교체 시 offset 의미가 달라져 기각 |
| B | 화면 표시용 정규화 텍스트 offset만 저장 | 원문 재현성과 감사 추적이 약해 기각 |
| C | raw offset과 normalized offset을 모두 저장 | 채택 |
| D | offset 없이 매번 문구 검색으로 위치 계산 | 동일 문구 반복과 성능 리스크로 기각 |
| E | HWP/HWPX는 위치 저장 없이 목록형 표시 | ADR-0051과 충돌해 기각 |

## 영향

- `ocr_text_blocks`는 OCR 전용 테이블이 아니라 OCR/VLM/parser가 만든 텍스트 IR 블록 저장소로 사용한다.
- HWP/HWPX Annotation은 `textBlockId + normalized offset`으로 표시하고, raw offset은 감사 추적에 사용한다.
- parser adapter는 Text IR 생성 시 `textPath`, raw/normalized text, raw/normalized offset, parser 버전을 채워야 한다.
- parser adapter는 ADR-0065의 `TextBlock` 계약을 만족해야 한다.
- 동일 문구가 여러 번 반복되는 경우 `textBlockId`와 offset이 없으면 `PARTIALLY_LOCATED` 또는 `NOT_LOCATED`로 처리한다.

## 후속 과제

- `ocr_text_blocks` 명칭은 PoC에서는 유지하되, 본사업 전환 시 `text_blocks` 또는 `document_text_blocks`로 rename할지 재검토한다.
- HWP/HWPX parser 후보별 Text IR 생성 품질을 샘플 문서로 비교한다.
- UI 하이라이트 컴포넌트는 normalized text 기준 offset을 사용하도록 구현한다.
