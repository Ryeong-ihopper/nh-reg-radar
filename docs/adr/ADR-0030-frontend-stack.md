# ADR-0030: 프론트엔드 스택 선택

## 상태

Accepted

## 배경

본 프로젝트의 프론트엔드는 단순 CRUD 화면만 제공하지 않는다. 광고물 등록, 검토 결과 목록/상세, 광고 이미지 또는 PDF 미리보기, 좌표 기반 Annotation 표시, 기준자료 관리, PoC 검증 화면, 리포트 미리보기 등 복잡한 업무 UI를 구현해야 한다.

ADR-0026에서 API 계약 원천을 `openapi/openapi.yaml`로 정했고, ADR-0027에서 성공/오류 응답 표준을 정했다. 따라서 프론트엔드는 OpenAPI 기반 타입 생성, 안정적인 API 상태 관리, 복잡한 테이블/폼/검증 UI를 지원하는 스택이 필요하다.

## 결정

프론트엔드 기본 스택은 React + Vite + TypeScript로 한다.

| 영역 | 선택 |
| --- | --- |
| Framework | React |
| Build tool | Vite |
| Language | TypeScript |
| Routing | React Router |
| Server state/API cache | TanStack Query |
| Table | TanStack Table |
| Form | React Hook Form |
| Validation | Zod |
| API type generation | `openapi-typescript` |
| UI component base | shadcn/ui 또는 Radix 기반 컴포넌트 |

## 구현 기준

| 항목 | 기준 |
| --- | --- |
| API 타입 | `openapi/openapi.yaml`에서 TypeScript 타입을 생성 |
| API client | 생성 타입을 사용하는 얇은 client wrapper를 둠 |
| 오류 처리 | ADR-0027의 오류 응답 schema를 공통 처리 |
| Annotation | ADR-0015 좌표계를 기준으로 별도 컴포넌트로 분리 |
| 상태 관리 | 서버 상태는 TanStack Query, 화면 내부 UI 상태는 React state 중심 |
| 폼 검증 | React Hook Form과 Zod schema를 사용 |
| 테이블 | 정렬, 필터, pagination이 필요한 화면은 TanStack Table 사용 |
| 디자인 시스템 | shadcn/ui 또는 Radix 기반 컴포넌트를 사용하되 화면설계서 기준 업무 UI를 우선 |

전역 상태 저장소는 PoC 초기 필수 도입 대상에서 제외한다. 인증 사용자, 권한, 공통 코드처럼 여러 화면에서 공유되는 값은 TanStack Query cache와 React Context를 우선 사용하고, 구현 중 복잡도가 커질 경우 별도 ADR로 Zustand 등 전역 상태 라이브러리 도입을 검토한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| React + Vite + TypeScript | 복잡한 업무 UI, Annotation, 타입 생성, 라이브러리 생태계 측면에서 적합하다. |
| Vue + Vite + TypeScript | 구조가 단순하고 학습 곡선이 완만하지만 팀 경험이 React 중심이면 속도 이점이 줄어든다. |
| SvelteKit | 코드량은 줄일 수 있지만 기업 PoC와 유지보수 인력 확보 측면에서 보수적 선택은 아니다. |
| Next.js | 라우팅과 SSR 기능이 강하지만 내부 업무 PoC에는 서버 렌더링과 풀스택 기능이 과할 수 있다. |

## 결정 근거

- 광고 이미지/PDF 미리보기와 좌표 기반 Annotation UI는 컴포넌트 생태계와 캔버스/DOM 조합이 중요한 영역이다.
- OpenAPI 타입 생성과 TypeScript 기반 API client를 사용하면 프론트엔드/백엔드 계약 불일치를 줄일 수 있다.
- Vite는 PoC 단계에서 빠른 개발 서버와 단순한 정적 빌드 구성이 가능하다.
- React Router, TanStack Query/Table, React Hook Form, Zod 조합은 내부 업무 도구의 목록/상세/폼/검증 패턴에 적합하다.
- Next.js의 SSR/서버 기능은 현재 PoC 요구사항의 핵심이 아니다.

## 영향

- `apps/frontend`는 React + Vite + TypeScript 프로젝트로 생성한다.
- API 타입 생성 스크립트는 `openapi-typescript` 기준으로 구성한다.
- API 계약 변경 시 생성 타입 diff를 PR/CI에서 확인한다.
- 화면별 데이터 조회/변경은 TanStack Query mutation/query 구조를 따른다.
- 공통 오류 처리는 ADR-0027의 `code`, `message`, `details`, `traceId`를 기준으로 구현한다.
- Annotation 컴포넌트는 ADR-0015 좌표계와 API 명세의 좌표 필드를 기준으로 구현한다.

## 후속 조치

- `apps/frontend` skeleton을 React + Vite + TypeScript로 생성한다.
- OpenAPI 타입 생성 명령을 `package.json` script 또는 workspace script에 추가한다.
- 공통 API client, 오류 처리, 인증 header 주입 기준을 구현한다.
- 화면설계서와 화면-API 매핑표 기준으로 라우팅 구조를 정의한다.
- UI 컴포넌트 라이브러리 초기 설정과 theme token 기준을 정리한다.

## 관련 문서

- `docs/project-rules.md`
- `docs/api-contract-sync-policy.md`
- `docs/api-specification.md`
- `docs/screen-specification.md`
- `docs/screen-api-mapping.md`
- `docs/adr/ADR-0026-api-contract-management.md`
- `docs/adr/ADR-0027-api-response-standard.md`
- `docs/adr/ADR-0015-ad-coordinate-system.md`
