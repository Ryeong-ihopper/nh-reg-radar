# ADR-0055: API 인가 범위 및 부서 Scope 판정 기준

| 항목 | 내용 |
| --- | --- |
| 상태 | Accepted |
| 날짜 | 2026-07-12 |
| 관련 문서 | 기능명세서, API 명세서, DB 명세서, 테스트케이스 |
| 관련 ADR | ADR-0021, ADR-0022, ADR-0036, ADR-0048 |

## 배경

ADR-0036에서 PoC 인증은 자체 로그인 + JWT Bearer Token으로 정했고, API 인가는 role + department scope 기준으로 수행하기로 했다. 그러나 구현 단계에서는 목록 조회, 단건 조회, 파일 다운로드, 기준자료 변경, 관리자 API 같은 업무별 범위 판정이 더 구체적이어야 한다.

특히 상품부서 담당자는 자기 부서 광고물만 다뤄야 하고, 준법감시 담당자는 검토 업무상 더 넓은 범위를 조회할 수 있어야 하며, 기준 관리자는 기준자료 관리를 담당하지만 광고 원본 다운로드 권한과는 분리되어야 한다. 시스템 관리자의 원본 파일 접근도 장애 대응 목적과 사유 기록이 필요하다.

## 결정

API 인가는 role + department scope를 기본으로 적용하고, 일부 업무는 assigned reviewer 또는 resource owner 조건을 추가한다.

| 역할 | 기본 인가 범위 |
| --- | --- |
| `PRODUCT_DEPARTMENT_USER` | 본인 또는 소속 부서 광고물 등록, 조회, 분석 요청, 검토 결과 조회, 리포트 다운로드 |
| `COMPLIANCE_REVIEWER` | 검토 대상 광고물 전체 또는 배정 범위 조회, 검토 결과 확인, 심의 의견 작성, 리포트 생성 |
| `STANDARD_MANAGER` | 기준자료 등록, 수정, 비활성화, 기준자료 원문 조회. 광고 원본 다운로드는 기본 불가 |
| `SYSTEM_ADMIN` | 사용자, 권한, 감사 로그, 시스템 설정 관리. 원본 파일 접근은 장애 대응 사유 기록 필요 |
| `service account` | 배정된 job 수행에 필요한 내부 리소스 접근만 허용 |

권한 밖 데이터 처리 기준은 다음과 같다.

| API 유형 | 권한 밖 데이터 처리 |
| --- | --- |
| 목록 조회 | 권한 범위 밖 데이터는 결과에서 제외 |
| 단건 조회 | 권한 없으면 `403 FORBIDDEN` |
| 다운로드/미리보기/presigned URL 발급 | 권한 없으면 `403 FORBIDDEN` 및 거부 감사 로그 기록 |
| 등록/수정/삭제/상태 변경 | 권한 없으면 `403 FORBIDDEN` |
| 관리자 API | `SYSTEM_ADMIN`만 허용 |
| 기준자료 변경 API | `STANDARD_MANAGER` 또는 `SYSTEM_ADMIN`만 허용 |

## Scope 판정 기준

| 리소스 | Scope 기준 |
| --- | --- |
| 광고물 | `advertisements.department_id`, `registered_by`, 검토 배정 정보 |
| 광고 파일 | 연결된 `advertisement_id`의 scope와 파일 유형 |
| 검토 결과 | 연결된 광고물 scope와 검토 배정 정보 |
| 리포트 | 연결된 `review_id`와 광고물 scope |
| 기준자료 | 기준 관리자 role. 원문 조회는 준법감시/기준 관리자 중심 |
| 검증 데이터셋 | 준법감시, 기준 관리자, 시스템 관리자 |
| 사용자/권한 | 시스템 관리자 |
| 감사 로그 | 시스템 관리자. 필요 시 감사 조회 권한 별도 분리 검토 |

준법감시 담당자의 기본 PoC 범위는 전체 검토 대상 광고물 조회 가능으로 둔다. 본사업에서 부서별 준법 담당자 배정이 확정되면 assigned reviewer 또는 department mapping을 강화한다.

## 감사 로그

인가 판정은 다음 경우 감사 로그로 남긴다.

| 상황 | 기록 기준 |
| --- | --- |
| 민감 조회 허용 | ADR-0022 핵심 민감 조회 기준에 따라 기록 |
| 다운로드/미리보기/presigned URL 허용 | ADR-0021/ADR-0022 기준 기록 |
| 권한 거부 | 단건 조회, 다운로드, 변경성 행위, 관리자 API 접근 거부 기록 |
| 목록 조회 scope 필터 | 기본적으로 기록하지 않되 민감 조건 검색은 조건부 기록 |

감사 로그에는 `result=SUCCESS|FAILURE|DENIED`, `reason_code`, `actor_department_id`, `actor_role`, `target_type`, `target_id`, `request_id`, 민감 원문을 제외한 `metadata_json`을 저장한다.

## 대안

| 대안 | 내용 | 채택 여부 |
| --- | --- | --- |
| A | role만으로 인가 | 부서별 데이터 분리가 약해 기각 |
| B | role + 본인 소유 데이터 기준 | 부서 공동 업무와 맞지 않아 기각 |
| C | role + department scope 기본, 일부 업무는 assigned reviewer 또는 resource owner 추가 | 채택 |
| D | 모든 리소스에 row-level ACL 적용 | PoC에는 과도해 기각 |
| E | 관리자/일반 사용자만 구분 | 감사 로그와 보안 검증 신뢰도가 낮아 기각 |

## 영향

- API 라우터별 임의 조건문 대신 `AuthorizationService`에서 공통 판정을 수행한다.
- 목록 조회는 scope filter를 query에 적용한다.
- 단건 조회와 다운로드는 리소스 로드 후 scope를 검증한다.
- 권한 거부는 403으로 통일하고, 민감 리소스 접근 거부는 감사 로그에 남긴다.
- 테스트케이스는 목록 filtering, 단건 403, 다운로드 403, 기준자료 변경 403, 관리자 API 403을 구분한다.

## 후속 과제

- 본사업 전환 시 준법감시 담당자 배정 모델과 감사 조회 전용 role 분리 여부를 재검토한다.
- PostgreSQL RLS는 PoC 필수 범위에서 제외하고, 본사업 보안 요구 확정 시 검토한다.
