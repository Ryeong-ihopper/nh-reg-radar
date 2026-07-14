# ADR-0021: 파일 접근 권한 및 다운로드 정책

## 상태

Accepted

## 배경

본 프로젝트는 광고 원본, 상품설명서, 약관, 기준자료 원문, OCR/파서 산출물, 검토 리포트, PoC 검증 데이터셋 등 민감할 수 있는 파일을 저장하고 제공한다. 파일은 화면 미리보기, 다운로드, OCR/파싱, 리포트 생성, 감사 추적에 사용된다.

ADR-0017에서 파일 저장소는 S3 호환 Object Storage를 기준으로 정했다. 따라서 bucket은 기본 비공개로 두고, 모든 사용자 파일 접근은 backend 권한 검증을 통과해야 한다.

## 결정

파일 접근은 역할+부서 기반 권한을 기본으로 통제한다. 세부 API 인가 범위와 부서 scope 판정은 ADR-0055를 따른다. 파일 다운로드와 민감 파일 미리보기는 감사 로그 대상에 포함한다.

| 항목 | 결정 |
| --- | --- |
| bucket 공개 여부 | 기본 비공개 |
| 사용자 접근 | backend 권한 검증 필수 |
| 브라우저 미리보기 | backend proxy 또는 짧은 만료시간의 presigned URL |
| 사용자 다운로드 | backend 권한 검증 후 backend proxy 또는 presigned URL |
| 내부 worker 접근 | `ObjectStorageAdapter`를 통한 서버 내부 접근 |
| 공개 영구 URL | 금지 |
| 감사 로그 | 다운로드, presigned URL 발급, 민감 파일 미리보기 기록 |

`presigned URL`은 파일 접근 권한을 부여하는 수단이 아니라, backend 권한 검증 이후 파일 전송을 위임하는 일시적 URL로만 사용한다.

## 파일 접근 활용 범위

| 기능 | 파일 접근 용도 | 접근 방식 |
| --- | --- | --- |
| 광고물 등록 | 광고 원본, 상품설명서, 약관 업로드 | backend upload |
| 광고물 상세/검토 UI | 원본 PDF/이미지 미리보기 | backend proxy 또는 presigned URL |
| OCR/문서 파싱 | worker가 원본 파일을 읽어 텍스트, 표, 좌표 추출 | 내부 Adapter 접근 |
| 기준자료 관리 | 법령, 내규, 매뉴얼 원문 업로드 및 재색인 | backend upload, 내부 Adapter 접근 |
| Annotation UI | 원본 광고 화면 위 Bounding Box 표시 | 미리보기 접근 |
| 리포트 생성 | 검토 결과 파일 생성 및 저장 | 내부 Adapter 접근 |
| 리포트 다운로드 | 담당자 리포트 다운로드 | backend proxy 또는 presigned URL |
| 검증 데이터셋 | PoC 샘플 파일과 평가 결과 보존 | backend 권한 검증 |
| 감사/재현 | 판단에 사용된 원본, 기준자료, 산출물 버전 추적 | 메타데이터 조회, 필요 시 권한 검증 후 접근 |

## 권한 기준

| 사용자 유형 | 접근 가능 범위 |
| --- | --- |
| 상품부서 담당자 | 본인 또는 소속 부서가 등록한 광고물, 관련 첨부파일, 해당 검토 리포트 |
| 준법감시 담당자 | 검토 대상 광고물, 관련 첨부파일, 검토 결과, 리포트 |
| 기준 관리자 | 기준자료 원문, 기준자료 파싱 산출물, 기준자료 재색인 결과 |
| 시스템 관리자 | 운영/장애 대응 목적의 파일 메타데이터 및 감사 로그. 원본 파일 접근은 사유 기록 필요 |
| worker/service account | 배정된 job 수행에 필요한 파일만 내부 접근 |

파일 접근 권한은 역할만으로 결정하지 않고, 광고물 담당 부서, 검토 배정, 기준자료 관리 권한, 환경(`dev`, `prod(main)`)을 함께 확인한다. 권한이 없는 미리보기, 다운로드, presigned URL 발급 요청은 `403 FORBIDDEN`으로 처리하고 권한 거부 감사 로그를 남긴다.

## 접근 방식 선택 기준

| 파일/기능 | 기본 방식 | 비고 |
| --- | --- | --- |
| 광고 원본 미리보기 | backend proxy 또는 짧은 만료 presigned URL | 대용량 PDF/이미지는 presigned URL 가능 |
| 광고 원본 다운로드 | presigned URL 또는 backend proxy | 감사 로그 필수 |
| 상품설명서/약관 다운로드 | presigned URL 또는 backend proxy | 광고물 권한과 연결 |
| 기준자료 원문 미리보기 | backend proxy 우선 | 기준 관리자/준법감시 권한 확인 |
| 기준자료 원문 다운로드 | backend proxy 또는 presigned URL | 감사 로그 필수 |
| OCR/파서 산출물 | 내부 Adapter 접근 | 일반 사용자 직접 다운로드 제한 |
| 검토 리포트 다운로드 | presigned URL 또는 backend proxy | 감사 로그 필수 |
| 평가 결과 다운로드 | backend proxy 또는 presigned URL | PoC 평가 권한 확인 |

민감도가 높은 파일이거나 접근 이력을 강하게 통제해야 하는 파일은 backend proxy를 우선한다. 대용량 파일 전송이나 브라우저 미리보기 성능이 중요한 경우에는 짧은 만료시간의 presigned URL을 사용할 수 있다.

## Presigned URL 기준

| 항목 | 기준 |
| --- | --- |
| 발급 조건 | backend 권한 검증 통과 |
| 만료 시간 | 기본 5분, 최대 15분 |
| URL 범위 | 단일 object에 한정 |
| 권한 | 읽기 전용 |
| 재사용 | 만료 후 재발급 필요 |
| 기록 | 발급 사용자, 파일 ID, 용도, 만료 시각, 요청 IP 기록 |

고객사 자료, 광고 원본, 기준자료 원문은 외부 공개 URL 또는 장기 URL로 제공하지 않는다.

## 감사 로그 대상

다음 행위는 감사 로그로 남긴다.

| 행위 | 기록 항목 |
| --- | --- |
| 파일 업로드 | 사용자, 파일 ID, 파일 유형, checksum, 크기 |
| 파일 미리보기 | 사용자, 파일 ID, 화면/기능, IP |
| 파일 다운로드 | 사용자, 파일 ID, 파일 유형, IP, user agent |
| presigned URL 발급 | 사용자, 파일 ID, 만료 시각, 용도 |
| 기준자료 원문 접근 | 사용자, 기준자료 ID, 버전, 접근 목적 |
| 리포트 다운로드 | 사용자, 리포트 ID, 검토 ID, 파일 형식 |
| worker 내부 접근 | job ID, service account, 파일 ID, 처리 단계 |

감사 로그의 상세 보관 기간과 조회 범위는 `ADR-0022 감사 로그 저장 범위`에서 확정한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| 역할 기반 접근만 사용 | 단순하지만 상품부서별 데이터 분리를 표현하기 어렵다. |
| 부서 기반 접근만 사용 | 광고물 담당 범위는 표현하기 쉽지만 준법감시/관리자 권한을 표현하기 어렵다. |
| 건별 권한만 사용 | 가장 세밀하지만 PoC 단계 구현 부담이 크다. |
| 역할+부서 기반 접근 | PoC 업무 흐름과 보안 요구의 균형이 좋다. |

## 결정 근거

- 광고 원본과 상품설명서는 고객사 자료이므로 공개 URL로 제공하면 안 된다.
- 파일 미리보기와 다운로드는 사용자 편의상 필요하지만 권한 검증과 감사 로그가 필요하다.
- worker 내부 접근은 사용자 다운로드와 분리해야 한다.
- S3 호환 Object Storage를 사용하더라도 접근 정책은 애플리케이션 권한 모델과 연결되어야 한다.
- 역할+부서 기반 접근은 기존 기능명세서의 권한 매트릭스와 정합하다.

## 영향

- 파일 미리보기/다운로드 API는 권한 검증을 공통 처리해야 한다.
- `files/{fileId}/download` API 추가 또는 명세 보완이 필요하다.
- presigned URL 발급 시 감사 로그 기록이 필요하다.
- Object Storage bucket은 private로 유지한다.
- 테스트케이스에 권한 없음, 타 부서 파일 접근, 만료 URL, 다운로드 감사 로그 기록을 추가해야 한다.

## 후속 조치

- API 명세에 `/files/{fileId}/download`를 추가하고 응답 방식을 정의한다.
- 파일 미리보기 API에 backend proxy와 presigned URL 선택 기준을 반영한다.
- 감사 로그 명세를 `ADR-0022`에서 확정한다.
- 기능명세서의 권한 매트릭스에 파일 미리보기/다운로드 범위를 보완한다.
- 테스트케이스에 파일 접근 권한과 다운로드 감사 로그 검증을 추가한다.

## 관련 문서

- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/functional-specification.md`
- `docs/test-cases.md`
- `docs/screen-api-mapping.md`
- `docs/adr/ADR-0017-s3-compatible-object-storage.md`
- `docs/adr/ADR-0020-dev-prod-environment-separation.md`
- `docs/adr/ADR-0055-api-authorization-scope-policy.md`
- `docs/adr/ADR-0002-customer-sample-data-ai-input-policy.md`
