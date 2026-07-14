# ADR-0038: 리포트 출력 형식 정책

## 상태

Accepted

## 배경

검토 리포트는 고객사 담당자와 개발자가 PoC 결과를 확인하는 핵심 산출물이다. 기능명세서, API 명세서, DB 명세서에는 리포트 생성과 다운로드가 정의되어 있으나 출력 형식은 `PDF`, `DOCX`, `XLSX`, `Word` 등으로 혼재되어 있었다.

금융권 실무에서는 편집 가능한 보고서 원본과 외부 공유·열람용 출력물이 모두 필요할 수 있다. 다만 초기 PoC에서 여러 문서 포맷을 동시에 지원하면 리포트 템플릿, 렌더링, 서식 검증, 다운로드 테스트 범위가 커진다.

## 결정

초기 PoC의 리포트 출력 형식은 `HWPX`를 우선 지원하고, `PDF` 출력도 함께 지원한다.

| 항목 | 결정 |
| --- | --- |
| 기본 리포트 형식 | `HWPX` |
| 추가 지원 형식 | `PDF` |
| 초기 제외 형식 | `DOCX`, `XLSX`, `HWP` |
| API 요청값 | `format`은 `HWPX` 또는 `PDF`만 허용 |
| 기본값 | `format` 미지정 시 `HWPX` |
| 저장 위치 | ADR-0017 기준 S3 호환 Object Storage의 `reports` 영역 |
| 다운로드 권한 | ADR-0021 기준 backend 권한 검증 후 제공 |
| 감사 로그 | ADR-0022 기준 리포트 생성과 다운로드를 필수 기록 |

리포트 생성 시 렌더링 결과 파일과 함께 구조화된 리포트 스냅샷을 저장한다. 스냅샷에는 검토 요약, 항목별 판단, 근거, Annotation 참조, 문구 추천, 심의 의견 초안, 기준자료 버전, 생성자, 생성 시각, 렌더러 버전이 포함되어야 한다.

## 처리 기준

| 상황 | 처리 |
| --- | --- |
| `format=HWPX` | 편집 가능한 공식 리포트 원본 파일 생성 |
| `format=PDF` | ADR-0054 기준 HWPX 기준 산출물을 생성한 뒤 열람·공유용 PDF로 변환 |
| `format` 미지정 | `HWPX`로 처리 |
| `DOCX`, `XLSX`, 기타 포맷 요청 | `UNSUPPORTED_REPORT_FORMAT` 반환 |
| 리포트 생성 실패 | `report_status=FAILED` 저장 후 실패 사유 기록 |

HWPX와 PDF는 서로 다른 판단 결과를 만들면 안 된다. 두 포맷은 ADR-0054 기준 같은 `report_snapshot`과 `snapshot_hash`를 사용해야 하며, PDF는 HWPX 기준 산출물의 변환본으로 생성한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| PDF만 지원 | 구현은 단순하지만 고객사 내부 편집·보완 흐름을 지원하기 어렵다. |
| HWPX만 지원 | 국내 문서 업무에는 적합하지만 브라우저 열람, 외부 공유, 인쇄 확인이 약하다. |
| DOCX 중심 지원 | 범용성은 있으나 고객사 업무 문서 관행과 HWPX 요구를 우선 반영하지 못한다. |
| XLSX 포함 지원 | 항목 목록 검토에는 유용하지만 공식 리포트 문서 형식으로는 부적합하다. |
| HWPX 우선 + PDF 지원 | 편집 가능한 원본과 공유용 출력물을 모두 제공하면서 초기 범위를 통제할 수 있다. |

## 결정 근거

- HWPX는 고객사 내부 보고서 편집과 문서 양식 반영에 적합하다.
- PDF는 공유, 인쇄, 브라우저 미리보기, 파일 무결성 확인에 적합하다.
- DOCX와 XLSX를 초기 범위에 포함하면 렌더러와 서식 테스트가 증가한다.
- 구조화된 리포트 스냅샷을 저장하면 포맷을 추가해도 AI 검토를 다시 실행하지 않고 재렌더링할 수 있다.
- 리포트 생성과 다운로드는 감사 로그 대상이므로 포맷별 이력 추적이 필요하다.

## 영향

- API의 `format` 허용값은 `HWPX`, `PDF`로 제한한다.
- DB의 `reports.report_format` 설명은 `HWPX, PDF`로 갱신한다.
- DB는 리포트 파일 외에 구조화된 `report_payload`를 저장할 수 있어야 한다.
- 화면은 리포트 형식 선택 기본값을 `HWPX`로 두고, `PDF` 선택지를 제공한다.
- 테스트케이스는 HWPX 생성, PDF 생성, 미지원 포맷 요청을 분리한다.
- Object Storage의 리포트 object key에는 포맷을 포함한다.

## 후속 조치

- 리포트 템플릿 구조와 HWPX 렌더러 후보는 ADR-0054 기준 HWPX 기준 산출물 생성 방식으로 검증한다.
- PDF 렌더링은 ADR-0054 기준 HWPX-to-PDF converter adapter로 구현한다.
- DOCX, XLSX는 고객사 요구가 확인되면 후속 ADR 또는 요구사항 변경으로 추가한다.

## 관련 문서

- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/functional-specification.md`
- `docs/screen-specification.md`
- `docs/screen-api-mapping.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0017-s3-compatible-object-storage.md`
- `docs/adr/ADR-0021-file-access-download-policy.md`
- `docs/adr/ADR-0022-audit-log-scope.md`
- `docs/adr/ADR-0054-report-snapshot-hwpx-pdf-conversion.md`
