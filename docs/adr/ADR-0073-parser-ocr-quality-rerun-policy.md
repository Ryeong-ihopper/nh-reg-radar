# ADR-0073: Parser/OCR 품질 미달 시 재처리 및 보조 엔진 사용 정책

## 상태

Accepted

## 배경

ADR-0079는 파일 유형별 Parser/OCR 기본 처리와 HWP/HWPX Hybrid Parser 구성을 정했다. PDF와 복합 PDF는 `opendataloader-pdf`, HWP/HWPX는 `rhwp` 기준 텍스트와 `document-processor` 구조를 결합한 `hwp-hybrid`, 이미지와 스캔 PDF는 `PaddleOCR`을 사용한다. ADR-0053은 OCR text, parser structure, annotation location의 confidence 임계값을 정의했고, ADR-0059는 기술 오류와 업무 확인 필요 오류의 retry 기준을 정의했다.

남은 문제는 1차 엔진 결과가 낮은 품질이거나 구조 인식에 실패했을 때의 처리 기준이다. 모든 저신뢰도 결과에 보조 엔진을 자동 실행하면 비용과 처리 시간이 늘고, 어떤 결과가 최종 근거인지 추적이 어려워진다. 반대로 보조 엔진을 전혀 사용하지 않으면 PoC 샘플에서 파서/OCR 품질을 개선할 기회가 줄어든다.

따라서 기술 retry와 품질 기반 재처리를 분리하고, 보조 엔진 사용 조건과 기록 기준을 정한다.

## 결정

Parser/OCR 품질 미달 처리는 **기술 실패는 ADR-0059 기준 retry, 품질 미달은 정책 조건 충족 시 보조 엔진 재처리 후보, 판독 불가는 확인 필요/평가 제외 후보**로 분리한다.

| 항목 | 결정 |
| --- | --- |
| 기술 실패 | timeout, 일시적 실행 오류, Object Storage 오류는 ADR-0059 기준 retry |
| 입력 문제 | 파일 손상, 암호화, 미지원 형식은 retry 제외 |
| 품질 미달 | confidence, 누락 의심, 구조 인식 실패 조건에 따라 보조 엔진 재처리 후보 |
| 보조 엔진 | 항상 자동 fallback하지 않고 정책 조건 기반으로 실행 |
| 최종 산출물 | 최종 채택된 `NormalizedDocument` v1만 ReviewPipeline 입력으로 사용 |
| 이력 보존 | 모든 엔진 시도, 사유, confidence, raw artifact, 채택 여부를 기록 |
| 담당자 표시 | 판독 불가/품질 미달/재처리 실패는 확인 필요 상태로 표시 |

## 처리 기준

| 상황 | 처리 |
| --- | --- |
| 엔진 timeout, 일시적 실행 오류, Object Storage 오류 | ADR-0059 기준 retry |
| 파일 손상, 미지원 형식, 암호화 파일 | retry 제외, 최종 실패 또는 담당자 확인 |
| OCR confidence `< 0.50`이고 판정 대상 문구 식별 불가 | 자동 retry 제외, `OCR_UNREADABLE` 확인 필요/평가 제외 후보 |
| OCR confidence `0.50~0.79` | 담당자 확인 필요. 핵심 문구 누락 의심 또는 text block 수 비정상 시 보조 엔진 재처리 후보 |
| Parser structure confidence `< 0.50` | 구조 인식 실패. HWP/HWPX/PDF는 보조 엔진 재처리 후보 |
| Parser structure confidence `0.50~0.75` | `PARTIALLY_STRUCTURED`, 검토는 진행하되 구조 기반 판단은 낮은 신뢰도로 표시 |
| 복합 PDF에서 표/다단 추출 누락 | `MinerU` 보조 재처리 후보 |
| HWP/HWPX에서 기준 텍스트 생성 실패 | `rhwp` 구성요소 기술 retry 또는 최종 실패 후보 |
| HWP/HWPX에서 구조 정렬·표 셀·offset 생성 실패 | ADR-0079 기준 구조 보강 retry 후 미정렬 텍스트 보존과 확인 필요 처리 |
| 이미지/스캔 PDF에서 OCR 누락 | VLM OCR 보조 재처리 후보. 단, 외부 AI 입력 가능 자료에 한정 |

보조 엔진 결과가 1차 엔진보다 항상 우선하는 것은 아니다. 최종 채택 기준은 confidence, 필수 필드 충족 여부, Text IR/Coordinate 생성 여부, warning 수, 판정 대상 문구 식별 여부를 함께 비교한다.

## 보조 엔진 실행 기준

| 파일 유형 | 1차 엔진 | 보조 엔진 조건 |
| --- | --- | --- |
| PDF/복합 PDF | `opendataloader-pdf` | 구조 confidence `< 0.50`, 표/다단 누락 의심, text block 수 비정상 |
| 스캔 PDF | `PaddleOCR` | OCR confidence `< 0.80`이면서 판정 대상 문구 누락 의심 |
| JPG/JPEG/PNG | `PaddleOCR` | 저해상도/복잡 배경으로 핵심 문구 누락 의심. VLM OCR은 승인된 자료에 한정 |
| HWP/HWPX | `hwp-hybrid` | `rhwp` 텍스트와 `document-processor` 구조의 구성요소 retry·정렬 품질 저하를 ADR-0079 기준으로 처리 |

보조 엔진은 자동 fallback이 아니라 **재처리 시도**로 기록한다. 재처리 시도는 Job/Step 상태와 raw artifact metadata에 남기며, 최종 채택된 산출물만 후속 ReviewPipeline에 전달한다.

## 기록 기준

Parser/OCR 재처리는 다음 정보를 남긴다.

| 필드 | 설명 |
| --- | --- |
| `attempt_no` | 같은 파일/단계 내 Parser/OCR 시도 순번 |
| `is_primary_attempt` | 1차 엔진 시도 여부 |
| `is_selected_output` | ReviewPipeline에 전달된 최종 산출물 여부 |
| `rerun_reason_code` | `LOW_CONFIDENCE`, `STRUCTURE_FAILED`, `TABLE_EXTRACTION_MISSING`, `TEXT_OFFSET_MISSING`, `ENGINE_TIMEOUT`, `MANUAL_REPROCESS_REQUESTED` 등 |
| `rerun_reason_message` | 운영자/개발자 확인용 상세 사유 |
| `parser_name` | 실행한 Adapter/엔진 이름 |
| `parser_version` | Adapter/엔진 버전 |
| `confidence_score` | 해당 시도 산출물의 대표 confidence |
| `confidence_status` | ADR-0053 기준 상태 |
| `raw_artifact_id` | ADR-0067 기준 raw artifact 참조 |

최종 채택되지 않은 보조 엔진 산출물은 raw artifact와 metadata로 보존할 수 있지만, `ocr_text_blocks`, `layout_blocks`, `annotations`의 업무 조회 결과에는 최종 채택 산출물 기준으로 반영한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| A. 1차 엔진 실패/저신뢰도 시 항상 보조 엔진 자동 실행 | 품질 개선 가능성은 높지만 비용, 시간, 재현성 관리 부담이 커 기각 |
| B. 기술 실패는 retry, 품질 미달은 정책 조건 충족 시 보조 엔진 재처리, 판독 불가는 확인 필요 | 비용과 품질, 추적성의 균형이 좋아 채택 |
| C. 보조 엔진은 자동 실행하지 않고 관리자 수동 재처리만 허용 | 운영 통제는 명확하지만 PoC 품질 개선 루프가 느려 기각 |
| D. 보조 엔진 없이 1차 결과만 사용 | 구현은 단순하지만 Parser/OCR 품질 이슈가 검토 품질 저하로 연결되어 기각 |
| E. LLM/VLM으로 품질 미달 케이스를 모두 보정 | 비용, 보안, 온프렘, 재현성 부담이 커 기각 |

## 결정 근거

- Parser/OCR 품질 문제는 RAG 검색 인프라 장애와 달리 보조 엔진으로 개선될 수 있으나, 항상 fallback하면 비용과 이력 관리가 과해진다.
- ADR-0053의 confidence 임계값을 재처리 조건으로 사용하면 화면, KPI, 테스트 기준과 정합성이 맞다.
- ADR-0059의 retry 정책과 분리해야 기술 장애 retry와 품질 보정 재처리를 혼동하지 않는다.
- 모든 시도와 최종 채택 산출물을 기록해야 PoC 품질 분석과 엔진 교체 검증이 가능하다.
- VLM OCR은 외부 AI 입력 가능 자료와 온프렘 제약을 고려해 제한적으로만 사용해야 한다.

## 영향

- `parser_artifacts` 또는 동등한 metadata에 attempt, selected output, rerun reason 정보를 저장한다.
- ParserRouter/Worker는 기술 retry와 품질 재처리를 분리해 처리한다.
- API/화면은 판독 불가, 품질 미달, 재처리 실패를 담당자 확인 필요 상태로 표시한다.
- 테스트케이스에 기술 retry, 보조 엔진 재처리, 최종 산출물 선택, VLM OCR 제한 조건을 추가한다.

## 후속 조치

- Parser/OCR 품질 재처리 조건을 YAML 또는 동등한 설정 파일로 관리한다.
- `ParserAttempt` 또는 동등한 내부 모델을 정의해 시도 이력을 표준화한다.
- 실제 샘플 평가 후 confidence score calibration이 필요하면 ADR-0053 후속 과제로 조정한다.
- 관리자 수동 재처리 API/화면이 필요할지는 PoC 운영 중 별도 ADR로 검토한다.

## 관련 문서

- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/functional-specification.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0053-confidence-threshold-policy.md`
- `docs/adr/ADR-0059-ai-job-timeout-retry-deadletter-policy.md`
- `docs/adr/ADR-0065-normalized-document-schema-and-adapter-contract.md`
- `docs/adr/ADR-0067-parser-ocr-raw-artifact-storage-retention-policy.md`
- `docs/adr/ADR-0079-hwp-hwpx-hybrid-parser-composition.md`
