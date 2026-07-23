# ADR-0082: 개발 기간 GitHub 기본 브랜치 dev 운영 정책

| 항목 | 내용 |
| --- | --- |
| 상태 | Accepted |
| 날짜 | 2026-07-23 |
| 관련 문서 | 프로젝트 규칙, CI·배포 가이드, README |
| 관련 ADR | ADR-0080, ADR-0083 |

## 배경

운영 반입이 한참 뒤인 NH 내부 폐쇄망 프로젝트에서 일상 협업 기준선은 `dev`이고 `main`은 릴리스 기준선으로만 사용한다. ADR-0080의 `deploy-compose.yml`은 `dev` push의 `Product CI` 성공을 `workflow_run`으로 받아 development Compose에 자동 배포하도록 구성되어 있다.

그러나 GitHub Actions의 `workflow_run` 트리거는 **기본 브랜치에 존재하는 workflow만** 실행한다. 기본 브랜치가 `main`이고 `deploy-compose.yml`이 `dev`에만 있는 동안에는 dev 자동 배포가 발동하지 않았고, clone·신규 PR 기본 대상도 개발 코드가 없는 `main`을 가리켰다.

## 결정

1. 개발 기간 동안 GitHub 기본 브랜치를 `dev`로 운영한다(2026-07-23 적용).
2. 이로써 `deploy-compose.yml`의 `workflow_run` development 자동 배포가 활성 등록되고, clone·신규 PR 기본 대상·README 온보딩이 실제 개발 코드(`dev`)와 일치한다.
3. `main`은 폐쇄망 반입 릴리스 기준선으로 유지하며, `dev`→`main` 병합·태그·반입 artifact 전략은 Q77(후속 ADR)로 별도 확정한다.
4. 운영 릴리스 준비 시점에 기본 브랜치를 `main`으로 복귀할지 여부는 Q77 확정과 함께 재검토한다.
5. 기본 브랜치 변경으로 `main` push가 드물어져 발생하는 Notion 공유본 최신성 영향은 ADR-0083으로 처리한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| A. 기본 브랜치를 `main`으로 유지 | dev 자동 배포 미발동, clone·PR 기본 대상이 미완성 `main`이라 제외 |
| B. 개발 기간 기본 브랜치를 `dev`로 설정 | 자동 배포 활성화와 온보딩 일관성을 함께 확보하여 채택 |
| C. `main` 유지 + Product CI에 dev 배포 job을 `needs`로 연결하거나 CD workflow를 `main`에도 반영 | 관례는 유지하나 CI 결합도 증가와 workflow 이중 관리로 제외 |

## 영향

- `dev` push → Product CI 성공 시 `deploy-compose.yml`의 `workflow_run` 자동 배포가 발동한다(런타임 운영은 `nh-ad-deploy-dev` self-hosted runner 등록·최초 성공 이후 시작).
- clone·신규 PR 기본 대상과 README 온보딩이 `dev` 기준으로 일치한다.
- `main` push 빈도가 낮아져 ADR-0077의 `main` 기준 Notion 동기화 최신성에 영향을 준다(ADR-0083에서 처리).
- 릴리스 준비 시 기본 브랜치 복귀는 Q77과 함께 판단한다.

## 검증

- GitHub 기본 브랜치가 `dev`임을 저장소 설정에서 확인한다.
- `workflow_run` development 배포 job이 push·`dev` 브랜치·동일 저장소 source 가드 조건에서만 발동하는지 확인한다(가드는 ADR-0080 운영 기준).

## 후속 조치

- `nh-ad-deploy-dev` self-hosted runner 등록 후 최초 배포 성공으로 자동 배포 운영을 검증한다.
- Q77(폐쇄망 반입 릴리스 파이프라인) 확정 시 기본 브랜치 복귀 여부와 `main` 릴리스 CI를 함께 결정한다.

## 관련 문서

- `docs/project-rules.md`
- `docs/self-hosted-runner-guide.md`
- `docs/adr/decision-questions.md`
- `docs/adr-candidates.md`
- `README.md`
