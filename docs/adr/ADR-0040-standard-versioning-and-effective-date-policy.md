# ADR-0040: 기준자료 버전관리 및 검토 기준일 정책

## 상태

Accepted

## 배경

금융상품 광고심의 기준은 법령, 감독규정, 내부기준, 심의사례, 문구 템플릿 등으로 구성되며 개정될 수 있다. 같은 광고 문구라도 검토 시점 또는 적용 기준일에 따라 판단 근거가 달라질 수 있으므로, 검토 결과가 어떤 기준자료 버전으로 생성되었는지 재현할 수 있어야 한다.

현재 DB 명세에는 `standards`, `standard_versions`, `evidences`, `evidence_chunks` 구조가 있고 API에는 `effectiveDate`, `version` 필드가 정의되어 있다. 그러나 기준자료 수정 시 기존 내용을 덮어쓸지, 검토 요청 시 어떤 버전을 선택할지, 리포트와 감사 추적에 어떤 정보를 남길지에 대한 정책이 확정되지 않았다.

## 결정

기준자료는 불변 버전으로 보존하고, 검토 요청 시 `standard_effective_date` 기준으로 적용 가능한 기준자료 버전 세트를 자동 선택한다. 선택된 기준자료 버전 세트는 해당 review에 스냅샷으로 고정한다.

| 항목 | 결정 |
| --- | --- |
| 기준자료 수정 방식 | 기존 버전 덮어쓰기 금지, 새 `standard_versions` row 생성 |
| 버전 선택 기준 | `standard_effective_date` 기준 자동 선택 |
| 기본 검토 기준일 | 요청값이 없으면 광고물 등록일 또는 검토 요청일 중 구현 정책상 선택한 기본일을 사용하되 review에 저장 |
| 버전 스냅샷 | review 생성 시 선택된 `standard_version_id` 목록을 저장 |
| 근거 연결 | `review_item_evidences`는 실제 사용한 `evidence_id`, `evidence_chunk_id`, `standard_version_id`를 추적 |
| 재분석 | 기존 review 수정 금지, 새 review 생성 후 새 기준 버전 세트 적용 |
| 리포트 표시 | 사용한 기준자료 버전과 기준 적용일 표시 |

## 처리 기준

| 상황 | 처리 |
| --- | --- |
| 기준자료 최초 등록 | `standards` master 생성, `standard_versions.version=1.0` 생성 |
| 기준자료 수정 | 새 version 생성, `standards.current_version` 갱신 |
| 시행일이 다른 개정 기준 등록 | 새 version의 `effective_date`를 저장하고 기존 version의 적용 종료일을 보정 |
| 검토 요청 시 `standardEffectiveDate` 지정 | 해당 일자에 유효한 version만 검색/판단에 사용 |
| 검토 요청 시 기준일 미지정 | 시스템 기본 기준일을 산정해 `reviews.standard_effective_date`에 저장 |
| 과거 review 조회 | review에 고정된 기준 버전 세트로 결과와 근거를 재현 |
| 재분석 요청 | 새 review를 생성하고 현재 정책 기준으로 기준 버전 세트를 다시 선택 |

버전 선택 시 같은 `standard_id`에 대해 적용 가능한 version이 여러 개인 경우 `effective_date`가 기준일 이하인 것 중 가장 최신 version을 선택한다. 기준일에 유효한 version이 없으면 해당 기준자료는 자동 판단 근거에서 제외하고, 필요한 경우 `STANDARD_NOT_FOUND` 또는 `CHECK_REQUIRED` 흐름으로 처리한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| 최신 활성 기준만 사용 | 구현은 단순하지만 과거 검토 결과 재현과 감사 추적이 어렵다. |
| 기준자료 버전을 보존하고 `effectiveDate` 기준으로 자동 선택 | 재현성은 좋지만 review별 선택 버전 세트가 없으면 이후 인덱스 변경 영향을 받을 수 있다. |
| 버전 보존 + `effectiveDate` 자동 선택 + review 기준 버전 스냅샷 고정 | 재현성, 리포트, 감사 추적이 가장 안정적이다. |
| 담당자가 검토마다 기준자료 버전을 수동 선택 | 통제는 강하지만 업무 부담과 선택 오류 가능성이 크다. |
| 기준자료를 Git 파일로만 버전관리 | 변경 이력 추적은 쉽지만 화면/API/검색 인덱스 연계가 약하다. |

## 결정 근거

- 금융 광고심의 결과는 판단 당시 근거를 재현할 수 있어야 한다.
- 기준자료 개정 후에도 과거 review와 리포트가 다른 근거로 바뀌면 안 된다.
- `standard_effective_date`와 버전 스냅샷을 함께 저장하면 재분석 전후 차이를 설명할 수 있다.
- RAG 검색 인덱스가 재생성되더라도 review에 저장된 버전 세트가 있으면 감사 추적이 가능하다.
- 담당자 수동 선택보다 자동 선택이 PoC 업무 흐름에 적합하고 입력 오류를 줄인다.

## 영향

- API의 검토 요청과 근거 검색은 `standardEffectiveDate` 또는 `effectiveDate` 기준으로 기준자료 버전을 선택해야 한다.
- DB의 `reviews`에는 선택된 기준자료 버전 세트를 저장할 수 있는 필드가 필요하다.
- `review_item_evidences`에는 실제 사용한 `standard_version_id`를 저장해야 한다.
- 기준자료 수정 API는 기존 version을 갱신하지 않고 새 version을 생성해야 한다.
- 리포트와 검토 상세 화면은 사용한 기준자료 버전과 적용 기준일을 표시해야 한다.
- 테스트케이스는 기준자료 개정 후 과거 review가 기존 version을 유지하는지 검증해야 한다.

## 후속 조치

- 구현 시 `StandardVersionResolver` 또는 동등한 버전 선택 모듈을 둔다.
- 기준자료 version naming은 초기 PoC에서 `1.0`, `1.1` 형태를 허용하되, 중복은 `standard_id + version` unique로 제한한다.
- `effective_to` 또는 `expired_date` 컬럼 세부 명칭은 DB migration 작성 시 확정하되, 기능 의미는 적용 종료일로 통일한다.
- 검색 인덱스에는 `standard_version_id`, `effective_date`, 적용 종료일, `is_active`를 포함한다.
- 기준자료 유형별 필수 메타데이터는 ADR-0050 기준으로 검증한다.

## 관련 문서

- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/functional-specification.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0012-reference-chunking-policy.md`
- `docs/adr/ADR-0017-s3-compatible-object-storage.md`
- `docs/adr/ADR-0038-report-output-format-policy.md`
- `docs/adr/ADR-0050-reference-metadata-policy.md`
