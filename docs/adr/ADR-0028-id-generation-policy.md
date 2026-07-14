# ADR-0028: ID 생성 규칙

## 상태

Accepted

## 배경

API 명세서에는 `ADV-20260702-0001`, `REV-20260702-0001`, `ITEM-0001`, `FILE-0001`처럼 사람이 읽을 수 있는 Prefix ID가 예시로 사용되어 있다. 반면 DB 명세서는 대부분의 주요 테이블 PK를 `uuid` 타입으로 정의하고 있다.

두 방식을 하나로 통일하면 한쪽의 장점이 약해진다. UUID만 외부에 노출하면 화면, 로그, 고객사 커뮤니케이션에서 식별성이 떨어진다. Prefix 문자열만 DB PK로 사용하면 FK 길이, 인덱스 크기, 생성 규칙 관리 부담이 커진다.

따라서 내부 저장소 안정성과 외부 업무 추적성을 분리하는 ID 정책이 필요하다.

## 결정

내부 PK/FK는 UUID를 사용하고, 외부 노출 ID는 Prefix 문자열을 사용한다.

| 구분 | 기준 |
| --- | --- |
| DB 내부 PK | `uuid` 타입의 `id` 또는 `{entity}_id` |
| DB 내부 FK | 참조 대상 내부 UUID |
| 외부 노출 ID | Prefix 문자열. API, 화면, 리포트, 고객사 커뮤니케이션에 사용 |
| API path parameter | 외부 노출 ID 사용 |
| 감사 로그 | 내부 UUID와 외부 노출 ID를 함께 저장할 수 있어야 함 |
| 파일 Object Storage key | 외부 ID만 단독 사용하지 않고 내부 UUID, 날짜, 용도 prefix와 조합 |

## ID 종류

| 엔티티 | 외부 ID 예시 | 비고 |
| --- | --- | --- |
| 광고물 | `ADV-20260707-0001` | 날짜별 일련번호 |
| 검토 | `REV-20260707-0001` | 날짜별 일련번호 |
| 검토 항목 | `ITEM-0001` | 검토 내 순번 또는 전역 일련번호. OpenAPI 작성 시 확정 |
| 파일 | `FILE-0001` | Object Storage key와 동일하게 보지 않음 |
| 기준자료 | `STD-20260707-0001` | 기준자료 버전과 별도 |
| 리포트 | `RPT-20260707-0001` | 다운로드/감사 로그에서 사용 |
| 평가 데이터셋 | `VAL-20260707-0001` | PoC 평가 추적용 |
| 평가 실행 | `EVAL-20260707-0001` | KPI 결과 추적용 |

## 생성 원칙

외부 노출 ID는 다음 원칙을 따른다.

| 항목 | 기준 |
| --- | --- |
| 형식 | `{PREFIX}-{YYYYMMDD}-{NNNN}`를 기본으로 사용 |
| Prefix | 엔티티를 식별할 수 있는 3~5자 대문자 약어 |
| 일련번호 | 동일 날짜와 동일 Prefix 안에서 증가 |
| 중복 방지 | DB unique constraint로 보장 |
| 재사용 금지 | 삭제 또는 실패한 요청의 외부 ID는 재사용하지 않음 |
| 정렬 의미 | 외부 ID의 날짜와 순번은 업무 추적용이며 정밀한 생성 순서 판단은 `created_at`을 사용 |

단, 검토 항목처럼 상위 엔티티 내부에서만 의미가 있는 항목은 `ITEM-0001`처럼 범위 제한 Prefix ID를 사용할 수 있다. 이 경우 API와 DB 명세에서 scope를 명확히 적는다.

## 대안

| 대안 | 판단 |
| --- | --- |
| 모든 ID를 UUID로 사용 | 구현은 단순하지만 화면, 로그, 고객사 커뮤니케이션에서 식별성이 낮다. |
| 모든 ID를 Prefix 문자열로 사용 | 업무 추적성은 좋지만 DB FK, 인덱스, 변경 가능성 관리 부담이 커진다. |
| 내부 PK는 UUID, 외부 노출 ID는 Prefix 문자열 | DB 안정성과 업무 추적성을 모두 확보할 수 있다. |
| DB Sequence 기반 숫자 ID | 단순하지만 외부 노출 시 예측 가능하고 엔티티 의미가 약하다. |

## 결정 근거

- DB 내부 관계는 UUID 기반으로 두는 편이 FK, migration, 데이터 통합에 안정적이다.
- 고객사 담당자와 개발자가 화면, 리포트, 로그에서 같은 건을 논의하려면 사람이 읽을 수 있는 외부 ID가 필요하다.
- 외부 노출 ID와 내부 PK를 분리하면 향후 Prefix 형식이 바뀌어도 DB 관계를 보존할 수 있다.
- 감사 로그와 파일 접근 로그는 내부 UUID와 외부 ID를 함께 보관해야 추적성과 운영 대응이 좋아진다.

## 영향

- API 명세의 `advertisementId`, `reviewId`, `reviewItemId`, `fileId` 등은 외부 노출 ID로 해석한다.
- DB 명세에는 내부 UUID PK와 외부 노출 ID 컬럼의 역할을 구분해 기록한다.
- OpenAPI schema에서는 외부 노출 ID 필드를 `string`으로 정의하고 pattern을 추가한다.
- FastAPI 구현에서는 외부 ID를 받아 내부 UUID를 조회한 뒤 도메인 로직을 수행한다.
- 감사 로그에는 가능한 경우 내부 UUID와 외부 노출 ID를 함께 기록한다.

## 후속 조치

- `openapi/openapi.yaml` 작성 시 주요 ID 필드의 pattern을 정의한다.
- DB migration 작성 시 외부 노출 ID 컬럼에 unique constraint를 둔다.
- ID 생성기는 엔티티별 Prefix, 날짜, 일련번호 정책을 중앙 모듈로 구현한다.
- Object Storage key 설계 시 외부 ID만으로 경로를 구성하지 않는다.

## 관련 문서

- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/adr/ADR-0026-api-contract-management.md`
- `docs/adr/ADR-0022-audit-log-scope.md`
