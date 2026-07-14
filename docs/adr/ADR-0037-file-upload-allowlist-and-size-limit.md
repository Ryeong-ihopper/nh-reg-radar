# ADR-0037: 파일 업로드 허용 확장자 및 용량 제한

## 상태

Accepted

## 배경

광고물 등록, 상품설명서/약관 등록, 기준자료 등록은 모두 파일 업로드를 사용한다. ADR-0017에서 파일 저장소는 S3 호환 Object Storage로 결정했고, ADR-0021에서 파일 접근과 다운로드 권한 정책을 결정했다.

그러나 업로드 단계에서 허용할 파일 확장자와 최대 용량이 정해지지 않으면 API validation, 화면 메시지, 테스트케이스, parser/OCR 파이프라인의 입력 계약이 흔들릴 수 있다. 특히 광고물 파일도 이미지/PDF뿐 아니라 HWP/HWPX 형식으로 제공될 수 있다.

## 결정

초기 PoC 업로드 허용 확장자는 파일 목적과 무관하게 다음으로 제한한다.

| 항목 | 결정 |
| --- | --- |
| 허용 확장자 | `jpg`, `jpeg`, `png`, `pdf`, `hwp`, `hwpx` |
| 최대 파일 크기 | 파일 1개당 50MB |
| 확장자 기준 | 파일명 확장자와 MIME/content sniffing 결과를 함께 확인 |
| 저장 방식 | ADR-0017 기준 S3 호환 Object Storage |
| 접근/다운로드 | ADR-0021 기준 backend 권한 검증 후 접근 |
| 분석 가능 여부 | 업로드 허용과 자동 분석 가능 여부를 분리 |

`doc`, `docx`, `xls`, `xlsx`, `ppt`, `pptx`는 실제 업무에서 광고물 파일로 제공될 수 있지만, 초기 PoC 업로드 허용 대상에서는 제외한다. 필요 시 후속 ADR 또는 요구사항 변경으로 확장한다.

## 처리 기준

| 상황 | 처리 |
| --- | --- |
| 허용 확장자 | 파일 저장 후 메타데이터 생성 |
| 허용되지 않은 확장자 | `FILE_NOT_SUPPORTED` 반환 |
| 50MB 초과 | `FILE_SIZE_EXCEEDED` 반환 |
| 파일 손상 또는 파싱 불가 | `FILE_READ_FAILED` 또는 분석 단계의 실패/확인 필요 상태 |
| HWP/HWPX 분석 미지원 케이스 | 업로드는 허용하되 parser adapter 결과에 따라 분석 가능 여부를 `확인 필요` 또는 `불가`로 표시 |

업로드 validation은 저장 전 수행한다. 저장 후 parser/OCR 단계에서 발생하는 판독 실패는 업로드 실패와 구분한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| PDF, PNG, JPG/JPEG만 허용 | 구현은 단순하지만 광고물 원본이 HWP/HWPX인 업무 현실을 반영하지 못한다. |
| Office 파일 전반 허용 | 업무 범위는 넓지만 초기 parser/보안/검증 부담이 크다. |
| 파일 목적별 허용 확장자 분리 | 세밀하지만 초기 PoC validation과 사용자 안내가 복잡해진다. |
| 초기 PoC는 `jpg/jpeg/png/pdf/hwp/hwpx`, 50MB 제한 | 업무 현실과 초기 구현 안정성의 균형이 좋다. |

## 결정 근거

- 이미지와 PDF는 OCR/미리보기/Annotation 검증의 핵심 입력이다.
- HWP/HWPX는 실제 광고물 원본 또는 설명자료로 제공될 수 있어 초기부터 업로드 허용이 필요하다.
- DOC/DOCX/XLS/XLSX/PPT/PPTX까지 허용하면 parser 후보 검증과 보안 검토 범위가 크게 늘어난다.
- 50MB 제한은 PoC 개발 VM, Object Storage, parser/OCR 처리 시간을 고려한 보수적 기준이다.
- 업로드 허용과 자동 분석 가능 여부를 분리하면 원본 보존과 분석 안정성을 함께 확보할 수 있다.

## 영향

- API validation은 허용 확장자와 50MB 제한을 공통 파일 업로드 정책으로 적용한다.
- 화면은 허용 확장자와 최대 용량을 업로드 입력 근처에 안내해야 한다.
- 테스트케이스는 허용 확장자, 미허용 확장자, 50MB 초과, 손상 파일을 구분한다.
- Parser/OCR adapter는 HWP/HWPX 입력을 받을 수 있어야 하지만, 초기 분석 실패 시 `확인 필요` 또는 `분석 불가`로 처리할 수 있다.
- 바이러스 검사는 PoC에서 필수 차단 조건으로 두지 않고, 연동 환경이 준비되면 업로드 후 검사 상태를 기록하는 방식으로 확장한다.

## 후속 조치

- API 명세서의 파일 오류 메시지와 후속 상세화 항목을 본 ADR 기준으로 갱신한다.
- 기능명세서의 광고 파일 입력 형식과 후속 상세화 항목을 갱신한다.
- 테스트케이스에 50MB 초과 케이스를 추가한다.
- 구현 시 공통 `FileUploadPolicy` 또는 동등한 validation 모듈을 둔다.
- 본사업 전환 또는 고객사 샘플 확대 시 `doc/docx/xls/xlsx/ppt/pptx` 허용 여부를 재검토한다.

## 관련 문서

- `docs/api-specification.md`
- `docs/functional-specification.md`
- `docs/test-cases.md`
- `docs/screen-specification.md`
- `docs/screen-api-mapping.md`
- `docs/adr/ADR-0017-s3-compatible-object-storage.md`
- `docs/adr/ADR-0021-file-access-download-policy.md`
- `docs/adr/ADR-0014-pluggable-document-parser-ocr.md`
