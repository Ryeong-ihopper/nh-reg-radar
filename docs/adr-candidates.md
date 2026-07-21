# 의사결정 필요사항

## AI 활용 금융상품 광고심의 적정성 검토 에이전트

## 문서 현행 정보

| 항목 | 내용 |
| --- | --- |
| 현행 버전 | v1.6 |
| 기준일 | 2026-07-22 |

## 변경 이력

| 버전 | 기준일 | 변경 내용 |
| --- | --- | --- |
| v1.6 | 2026-07-22 | ADR 후보 046을 private Parser/OCR와 외부 AI 활성화 설정 분리로 확정하고 ADR-0081 반영 |
| v1.5 | 2026-07-20 | ADR 후보 044를 PoC 2계정 운영 프로필로 확정하고 ADR-0078 반영 |
| v1.4 | 2026-07-16 | ADR 후보 043을 Git `main` 원본의 기존 Notion page ID 보존 단방향 자동 동기화로 확정하고 ADR-0077 반영 |
| v1.3 | 2026-07-14 | ADR 후보 042를 A안으로 확정하고 ADR-0076 AI 도구 lifecycle hook 및 문서 거버넌스 강제 계층 정책 반영 |
| v1.2 | 2026-07-14 | ADR 후보 041을 B안으로 확정하고 ADR-0075 프로젝트 범위 Skills 배포 정책 반영 |
| v1.1 | 2026-07-13 | 문서 거버넌스 적용에 따른 Skills 프로젝트 로컬 배포와 AI 도구 lifecycle hook 범위 재검토 후보 추가 |
| v1.0 | 2026-07-13 | ADR-0001~ADR-0074 결정 완료 현황, 신규 ADR 추가 기준, ADR 로드맵 누락 항목, ADR 관련 문서 역할 분리 기준 정리 |

---

## 1. 문서 목적

본 문서는 프로젝트 수행 과정에서 향후 의사결정이 필요한 주요 항목을 사전에 식별하고, 각 항목을 아키텍처 의사결정 기록(ADR, Architecture Decision Record)로 관리하기 위한 기준 문서이다.

본 문서의 목적은 다음과 같다.

- 기술 선택과 구현 방향을 임의로 결정하지 않도록 한다.
- 주요 의사결정 사항을 사전에 식별한다.
- 결정 배경, 대안, 선택 근거, 영향 범위를 ADR로 남긴다.
- 향후 요구사항 변경, 기술 변경, 운영 전환 시 판단 근거를 추적 가능하게 한다.

---

# 2. ADR 관리 기준

## 2.1 ADR로 남겨야 하는 결정

다음에 해당하는 사항은 반드시 ADR로 남긴다.

| 구분 | 설명 |
| --- | --- |
| 아키텍처 구조 | 시스템 전체 구조, 서비스 분리 방식, 배포 구조 |
| 기술 선택 | 프레임워크, DB, 검색엔진, 벡터DB, LLM 연동 방식 |
| 데이터 관리 | 기준자료 버전관리, 파일 저장소, 개인정보/보안 정책 |
| AI 처리 방식 | RAG 구조, OCR/VLM 선택, Agent 구조, 프롬프트 관리 |
| 개발 운영 | 모노레포, 브랜치 전략, CI/CD, 테스트 전략 |
| 인프라 운영 | VM, Docker, Self-hosted Runner, 네트워크 구성 |
| 품질 기준 | 테스트 범위, 성능 기준, 평가 지표, 오류 처리 정책 |
| 고객사 협의 사항 | 요구사항 변경, PoC 범위 변경, 평가 제외 기준 |

---

## 2.2 ADR 기본 템플릿

```
# ADR-0000: 의사결정 제목

## 상태
Proposed / Accepted / Deprecated / Superseded

## 배경
왜 이 결정을 해야 하는가?

## 결정
무엇을 선택했는가?

## 대안
검토한 대안은 무엇인가?

## 결정 근거
왜 이 결정을 선택했는가?

## 영향
이 결정이 시스템, 일정, 비용, 운영, 보안, 유지보수에 미치는 영향은 무엇인가?

## 후속 조치
이 결정 이후 수행해야 할 작업은 무엇인가?
```

---

## 2.3 ADR 관련 문서 역할 분리

ADR 관련 문서는 다음 역할로 분리한다. 같은 내용을 여러 문서가 모두 원장처럼 관리하면 누락과 중복이 생기므로, 공식 목록과 후보 백로그의 책임을 분리한다.

| 문서 | 역할 | 관리 기준 |
| --- | --- | --- |
| `docs/adr/README.md` | 공식 ADR 목록과 현재 상태 원장 | 모든 Accepted ADR의 번호, 제목, 상태, 관련 후보를 빠짐없이 관리 |
| `docs/adr/ADR-0000-*.md` | 개별 의사결정의 공식 본문 | 배경, 결정, 대안, 영향, 후속 조치를 기록하는 최종 기준 |
| `docs/adr/decision-questions.md` | 사용자 선택지와 검토 과정 보조 기록 | 모든 ADR의 1:1 목록이 아니며, 사용자 판단이 필요했던 분기만 기록 |
| 본 문서 | ADR 후보 백로그, 우선순위, 신규 ADR 필요 여부 판단 기준 | 후보 상태와 로드맵을 관리하되, 공식 결정 목록은 `docs/adr/README.md`를 참조 |

따라서 본 문서의 `ADR 후보 001~040` 상세 항목은 최초 후보 백로그의 이력이다. ADR-0035 이후의 후속 구현 ADR은 별도 후보 번호를 새로 부여하지 않고 `17.5 후속 구현 ADR`에 정리한다. 공식 ADR 총목록과 상태는 `docs/adr/README.md`를 기준으로 한다.

---

# 3. 의사결정 필요사항 요약

| 영역 | 의사결정 주제 | 우선순위 | ADR 필요 여부 |
| --- | --- | --- | --- |
| 개발 방법론 | 명세 기반 개발 범위 확정 | 높음 | 필요 |
| 저장소 | 모노레포 구조 확정 | 높음 | 필요 |
| 문서관리 | Git, Notion, Wiki 역할 분리 | 높음 | 필요 |
| AI 개발 | AI 활용 개발 책임 기준 | 높음 | 필요 |
| 프론트엔드 | 프론트 선구현 후 디자인 개선 방식 | 중간 | 필요 |
| 백엔드 | Python 기반 백엔드 프레임워크 선택 | 높음 | 필요 |
| 패키지 관리 | uv 사용 확정 | 중간 | 필요 |
| 테스트 | TDD 및 테스트 필수 범위 확정 | 높음 | 필요 |
| 컨테이너 | Docker 서비스 분리 기준 | 높음 | 필요 |
| DB | PostgreSQL 사용 확정 | 높음 | 필요 |
| 벡터 DB | Qdrant 사용 확정 | 높음 | 필요 |
| 키워드 검색 | OpenSearch 사용 확정 | 높음 | 필요 |
| 검색 구조 | Hybrid Search 전략 확정 | 높음 | 필요 |
| RAG | 기준자료 Chunking 및 검색 정책 | 높음 | 필요 |
| AI Agent | Rule/RAG/LLM Agent 역할 분리 | 높음 | 필요 |
| OCR/VLM | 광고물 텍스트 추출 방식 선택 | 높음 | 필요 |
| 파일 저장 | 광고물 원본 저장 방식 | 높음 | 필요 |
| 보안 | 고객사 자료 및 민감정보 처리 정책 | 높음 | 필요 |
| 인프라 | 개발 VM 및 네트워크 구성 | 높음 | 필요 |
| CI/CD | Self-hosted Runner 배포 방식 | 높음 | 필요 |
| 평가 | PoC KPI 산식 및 평가 제외 기준 | 높음 | 필요 |
| 운영 | 기준자료 버전관리 정책 | 높음 | 필요 |

---

# 4. 개발 방법론 관련 의사결정

## ADR 후보 001. 명세 기반 개발 방식 채택

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | 명세 기반 개발을 공식 개발 방식으로 채택할 것인가 |
| 배경 | 요구사항, 기능, API, DB, 테스트가 분리되지 않으면 AI 활용 개발 시 산출물 간 불일치가 발생할 수 있음 |
| 검토 대안 | ① 명세 기반 개발 ② 애자일 이슈 중심 개발 ③ 개발자 자율 구현 |
| 결정 필요사항 | 어떤 문서를 개발 착수 기준으로 볼 것인지 확정 필요 |
| 주요 쟁점 | 명세 작성 부담과 개발 속도 간 균형 |
| 권장 방향 | 요구사항 정의서, 기능명세서, API 명세서, DB 명세서, 테스트케이스를 최소 기준으로 삼음 |
| ADR 필요성 | 높음 |
| 작성 ADR | [ADR-0001: 명세 기반 개발 방식 채택](adr/ADR-0001-spec-driven-development.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 002. 명세 변경 관리 기준

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | 요구사항 변경 발생 시 어떤 문서를 먼저 갱신할 것인가 |
| 배경 | 고객사 요구사항 변경, 회의 결정사항, 기능 변경이 코드에만 반영되면 추적이 어려움 |
| 검토 대안 | ① 문서 선갱신 후 개발 ② 코드 선반영 후 문서 보완 ③ 이슈만 관리 |
| 결정 필요사항 | 변경 요청 접수 → 영향 분석 → 문서 갱신 → 개발 반영 절차 확정 |
| 주요 쟁점 | 긴급 대응 시 문서 갱신 지연 가능성 |
| 권장 방향 | 주요 기능 변경은 문서 선갱신, 긴급 수정은 사후 ADR/회의록 보완 |
| ADR 필요성 | 높음 |
| 작성 ADR | [ADR-0001: 명세 기반 개발 방식 채택](adr/ADR-0001-spec-driven-development.md) |
| 결정 상태 | Accepted |

---

# 5. 저장소 및 문서관리 관련 의사결정

## ADR 후보 003. 모노레포 구조 채택

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | 코드베이스를 모노레포로 운영할 것인가 |
| 배경 | 백엔드, 프론트엔드, AI 워커, 공통 스키마, 인프라 설정이 밀접하게 연동됨 |
| 검토 대안 | ① 모노레포 ② 백엔드/프론트/AI 별도 레포 ③ 문서와 코드 분리 레포 |
| 결정 필요사항 | apps, packages, infra, docs 구조 확정 |
| 주요 쟁점 | 저장소 규모 증가, 권한 분리 어려움 |
| 권장 방향 | PoC 단계에서는 모노레포 채택 |
| ADR 필요성 | 높음 |
| 작성 ADR | [ADR-0003: PoC 단계 모노레포 구조 채택](adr/ADR-0003-monorepo-structure.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 004. Git과 Notion의 역할 분리

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | 문서 원천 저장소를 Git으로 둘 것인가 |
| 배경 | Notion은 공유에 편리하지만 변경 이력, 리뷰, 코드와의 동기화에는 한계가 있음 |
| 검토 대안 | ① Git 원천 + Notion 공유 ② Notion 원천 ③ Git Wiki 원천 |
| 결정 필요사항 | 공식 문서의 원본 위치 확정 |
| 주요 쟁점 | 고객사 공유 편의성과 개발 추적성 간 균형 |
| 권장 방향 | Git을 원천 저장소로, Notion은 읽기/공유 인터페이스로 활용 |
| ADR 필요성 | 높음 |
| 작성 ADR | [ADR-0004: Git, Notion, Wiki 역할 분리](adr/ADR-0004-git-notion-wiki-roles.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 005. Wiki 운영 범위

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | Wiki에 어떤 정보를 반드시 기록할 것인가 |
| 배경 | 고객사 요구사항, 회의록, ADR, 변경사항을 추적 가능한 지식층으로 관리할 필요가 있음 |
| 검토 대안 | ① 모든 회의/결정 기록 ② 주요 결정만 기록 ③ 이슈 트래커에만 기록 |
| 결정 필요사항 | Wiki 필수 기록 항목 정의 |
| 주요 쟁점 | 기록 부담과 추적성 간 균형 |
| 권장 방향 | Git docs를 개발 명세 원본으로 두고, Wiki는 운영 가이드·배포 절차·장애 대응 등 필요 시 선택 운영 |
| ADR 필요성 | 중간 |
| 작성 ADR | [ADR-0004: Git, Notion, Wiki 역할 분리](adr/ADR-0004-git-notion-wiki-roles.md) |
| 결정 상태 | Accepted |

---

# 6. AI 활용 개발 관련 의사결정

## ADR 후보 006. AI 활용 풀스택 개발 방식

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | AI를 풀스택 개발에 어느 수준까지 활용할 것인가 |
| 배경 | AI를 활용하면 API, 테스트, 프론트 초안 구현 속도를 높일 수 있으나 품질 검증 책임이 필요함 |
| 검토 대안 | ① AI 적극 활용 ② 문서/테스트 보조만 활용 ③ 코드 생성 제한 |
| 결정 필요사항 | AI가 생성 가능한 산출물과 개발자 검토 범위 확정 |
| 주요 쟁점 | AI 생성 코드의 품질, 보안, 유지보수성 |
| 권장 방향 | 문서, 코드 초안, 테스트 초안에 활용하되 최종 책임은 개발자에게 둠 |
| ADR 필요성 | 높음 |
| 작성 ADR | [ADR-0031: AI 활용 개발 및 검증 책임](adr/ADR-0031-ai-assisted-development-responsibility.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 007. Claude/Codex Skills 운영 방식

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | Claude/Codex Skills를 실행 표준화 계층으로 운영할 것인가 |
| 배경 | 반복되는 문서 작성, 코드 생성, 테스트 생성, 리팩토링 작업을 표준화할 필요가 있음 |
| 검토 대안 | ① Skills 표준화 ② 개인별 프롬프트 자율 사용 ③ AI 도구 사용 제한 |
| 결정 필요사항 | Skills 관리 위치, 버전관리, 사용 범위 확정 |
| 주요 쟁점 | 프롬프트 품질, 보안, 도구 종속성 |
| 권장 방향 | 반복 작업은 Skills로 표준화하고 Git에서 버전 관리 |
| ADR 필요성 | 중간 |
| 작성 ADR | [ADR-0034: Claude/Codex Skills 표준화 및 온보딩 설치](adr/ADR-0034-codex-claude-skills-standardization.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 008. AI 생성 코드 검증 책임

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | AI가 생성한 코드의 검증 책임을 어떻게 둘 것인가 |
| 배경 | AI 코드가 테스트 없이 병합될 경우 품질 리스크가 큼 |
| 검토 대안 | ① 담당 개발자 전면 책임 ② 리뷰어 공동 책임 ③ AI 결과 신뢰 |
| 결정 필요사항 | PR 체크리스트와 리뷰 기준 확정 |
| 주요 쟁점 | 생산성 향상과 품질 보증 간 균형 |
| 권장 방향 | AI 생성 코드도 사람이 작성한 코드와 동일하게 테스트, 리뷰, 린트를 통과해야 함 |
| ADR 필요성 | 높음 |
| 작성 ADR | [ADR-0031: AI 활용 개발 및 검증 책임](adr/ADR-0031-ai-assisted-development-responsibility.md) |
| 결정 상태 | Accepted |

---

# 7. 프론트엔드 개발 관련 의사결정

## ADR 후보 009. 프론트엔드 선구현 후 디자인 개선 방식

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | 프론트엔드를 1차 기능 중심으로 구현한 후 디자이너 개선안을 반영할 것인가 |
| 배경 | PoC에서는 기능 검증과 API 연동이 우선이며, 상세 디자인은 후속 개선 가능 |
| 검토 대안 | ① 기능 우선 구현 후 디자인 개선 ② 디자인 선확정 후 개발 ③ 최소 화면만 구현 |
| 결정 필요사항 | 1차 구현의 완료 기준 확정 |
| 주요 쟁점 | 초기 UI 품질, 재작업 가능성 |
| 권장 방향 | 핵심 화면은 기능 완결, 보조 화면은 최소 구현 후 디자인 개선 |
| ADR 필요성 | 중간 |
| 작성 ADR | [ADR-0032: 프론트엔드 1차 구현 및 디자인 개선 방식](adr/ADR-0032-frontend-first-implementation-policy.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 010. 프론트엔드 프레임워크 선택

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | 프론트엔드 프레임워크를 무엇으로 선택할 것인가 |
| 배경 | 검토 결과 화면, Annotation UI, 리포트 미리보기 등 복잡한 UI 구현 필요 |
| 검토 대안 | ① React ② Vue ③ Svelte ④ 기타 |
| 결정 필요사항 | 프론트엔드 프레임워크, 상태관리, UI 컴포넌트 라이브러리 확정 |
| 주요 쟁점 | 팀 역량, 개발 속도, 유지보수성 |
| 권장 방향 | React + Vite + TypeScript 기반 구현 |
| ADR 필요성 | 높음 |
| 작성 ADR | [ADR-0030: 프론트엔드 스택 선택](adr/ADR-0030-frontend-stack.md) |
| 결정 상태 | Accepted |

---

# 8. 백엔드 및 API 관련 의사결정

## ADR 후보 011. Python 기반 백엔드 프레임워크 선택

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | 백엔드 API 서버 프레임워크를 무엇으로 선택할 것인가 |
| 배경 | 프로젝트 기본 언어가 Python이며 AI/RAG/Worker와의 연계가 중요함 |
| 검토 대안 | ① FastAPI ② Django ③ Flask |
| 결정 필요사항 | API 서버 프레임워크 확정 |
| 주요 쟁점 | API 생산성, 비동기 처리, 문서화, ORM 연계 |
| 권장 방향 | PoC에서는 FastAPI 우선 검토 |
| ADR 필요성 | 높음 |
| 작성 ADR | [ADR-0005: Python 백엔드 프레임워크로 FastAPI 채택](adr/ADR-0005-fastapi-backend-framework.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 012. API 명세 관리 방식

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | API 명세를 어떤 방식으로 관리할 것인가 |
| 배경 | 화면-API 매핑, 테스트케이스, 프론트 연동을 위해 API 계약 관리 필요 |
| 검토 대안 | ① OpenAPI YAML 원천 관리 ② 문서형 Markdown 관리 ③ 코드 자동 생성 문서 |
| 결정 필요사항 | API 명세 원천과 변경 절차 확정 |
| 주요 쟁점 | 문서와 코드 불일치 가능성, 동기화 강제 방식 |
| 권장 방향 | OpenAPI YAML을 계약 원천으로 두고 Markdown/API 테스트/FastAPI 생성 스펙과 CI로 동기화 검증 |
| ADR 필요성 | 높음 |
| 작성 ADR | [ADR-0026: API 명세 관리 및 동기화 강제 방식](adr/ADR-0026-api-contract-management.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 013. API 응답 표준

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | 모든 API 응답을 공통 Wrapper로 감쌀 것인가 |
| 배경 | success, code, message, data, timestamp 형태의 공통 응답 구조를 제안함 |
| 검토 대안 | ① 공통 Wrapper 사용 ② REST 기본 응답 사용 ③ API별 자율 |
| 결정 필요사항 | 공통 응답 구조, 오류 응답 구조 확정 |
| 주요 쟁점 | 프론트 처리 일관성, 표준 REST 관점 |
| 권장 방향 | 성공 응답은 REST 기본 형식으로 두고 오류 응답만 표준화 |
| ADR 필요성 | 중간 |
| 작성 ADR | [ADR-0027: API 응답 표준](adr/ADR-0027-api-response-standard.md) |
| 결정 상태 | Accepted |

---

# 9. 데이터베이스 및 저장소 관련 의사결정

## ADR 후보 014. PostgreSQL 사용

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | 관계형 DB로 PostgreSQL을 사용할 것인가 |
| 배경 | 광고물, 검토 결과, 기준자료, 감사 로그 등 구조화 데이터 관리 필요 |
| 검토 대안 | ① PostgreSQL ② MySQL ③ MariaDB |
| 결정 필요사항 | RDBMS 선택 확정 |
| 주요 쟁점 | 팀 운영 경험, JSONB 활용, 검색/벡터 확장 가능성 |
| 권장 방향 | PostgreSQL 사용 |
| ADR 필요성 | 높음 |
| 작성 ADR | [ADR-0006: 기본 관계형 DB로 PostgreSQL 채택](adr/ADR-0006-postgresql-primary-database.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 015. DB 스키마 분리 방식

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | PostgreSQL 스키마를 업무 영역별로 분리할 것인가 |
| 배경 | app, audit, rag, validation 등 데이터 성격이 다름 |
| 검토 대안 | ① 단일 public 스키마 ② 영역별 스키마 분리 ③ DB 자체 분리 |
| 결정 필요사항 | 스키마 구조 확정 |
| 주요 쟁점 | 관리 복잡도와 데이터 분리 효과 |
| 권장 방향 | PoC부터 `app`, `rag`, `validation`, `audit` 영역별 schema 분리 |
| ADR 필요성 | 중간 |
| 작성 ADR | [ADR-0029: PostgreSQL 영역별 Schema 분리](adr/ADR-0029-postgresql-schema-separation.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 016. 파일 저장소 선택

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | 광고 원본, 상품설명서, 리포트 파일을 어디에 저장할 것인가 |
| 배경 | 광고물, PDF, 이미지, 상품설명서, 리포트 등 파일 보관 필요 |
| 검토 대안 | ① 로컬 파일시스템 ② NAS ③ Object Storage ④ DB BLOB |
| 결정 필요사항 | PoC 및 운영 단계 파일 저장 방식 확정 |
| 주요 쟁점 | 보안, 백업, 용량, 다운로드 권한, 운영 편의성 |
| 권장 방향 | S3 호환 Object Storage 인터페이스를 기준으로 설계하고 PoC는 MinIO 사용 |
| ADR 필요성 | 높음 |
| 작성 ADR | [ADR-0017: S3 호환 Object Storage 기반 파일 저장소](adr/ADR-0017-s3-compatible-object-storage.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 017. ID 생성 규칙

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | 주요 엔티티 ID를 UUID로 할지 Prefix 문자열로 할지 결정 |
| 배경 | API 명세에서는 `ADV-`, `REV-`, `ITEM-` 등 Prefix ID를 사용함 |
| 검토 대안 | ① UUID ② Prefix 문자열 ③ DB Sequence |
| 결정 필요사항 | ID 생성 규칙과 추적성 기준 확정 |
| 주요 쟁점 | 가독성, 충돌 가능성, DB 성능 |
| 권장 방향 | 내부 PK/FK는 UUID, 외부 노출 ID는 Prefix 문자열 사용 |
| ADR 필요성 | 중간 |
| 작성 ADR | [ADR-0028: ID 생성 규칙](adr/ADR-0028-id-generation-policy.md) |
| 결정 상태 | Accepted |

---

# 10. 검색 및 RAG 관련 의사결정

## ADR 후보 018. Qdrant 사용

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | 벡터 DB로 Qdrant를 사용할 것인가 |
| 배경 | 법령, 내부 기준, 심의사례, 상품설명서의 의미 기반 검색 필요 |
| 검토 대안 | ① Qdrant ② pgvector ③ Milvus ④ OpenSearch Vector |
| 결정 필요사항 | 벡터 DB 최종 선택 |
| 주요 쟁점 | 운영 편의성, 검색 성능, Python 연계, 인프라 부담 |
| 권장 방향 | PoC에서는 Qdrant 사용 |
| ADR 필요성 | 높음 |
| 작성 ADR | [ADR-0009: 벡터 DB로 Qdrant 채택](adr/ADR-0009-qdrant-vector-database.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 019. OpenSearch 사용

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | 키워드 검색 엔진으로 OpenSearch를 사용할 것인가 |
| 배경 | 법령명, 조문번호, 금지어, 광고 문구 등 정확 검색 필요 |
| 검토 대안 | ① OpenSearch ② Elasticsearch ③ PostgreSQL Full Text Search |
| 결정 필요사항 | 키워드 검색 엔진 선택 |
| 주요 쟁점 | 운영 복잡도, 검색 정확도, 인프라 리소스 |
| 권장 방향 | OpenSearch 사용 |
| ADR 필요성 | 높음 |
| 작성 ADR | [ADR-0010: 키워드 검색 엔진으로 OpenSearch 채택](adr/ADR-0010-opensearch-keyword-search.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 020. Hybrid Search 전략

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | Vector Search와 Keyword Search를 결합할 것인가 |
| 배경 | 법령/기준 검색은 조문번호 정확 검색과 의미 기반 검색이 모두 필요함 |
| 검토 대안 | ① Vector only ② Keyword only ③ Hybrid Search |
| 결정 필요사항 | 검색 결과 결합 방식, 가중치, Top-K 기준 확정 |
| 주요 쟁점 | 검색 품질, 구현 복잡도, 응답시간 |
| 권장 방향 | Hybrid Search 채택 |
| ADR 필요성 | 높음 |
| 작성 ADR | [ADR-0011: Hybrid Search 전략 채택](adr/ADR-0011-hybrid-search-strategy.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 021. 기준자료 Chunking 정책

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | 기준자료를 어떤 단위로 Chunking할 것인가 |
| 배경 | RAG 검색 품질은 Chunk 크기, 중복, 메타데이터에 크게 영향받음 |
| 검토 대안 | ① 조문 단위 ② 문단 단위 ③ 고정 토큰 단위 ④ 의미 단위 |
| 결정 필요사항 | Chunk 크기, overlap, metadata 정책 확정 |
| 주요 쟁점 | 근거 정확도, 검색 성능, 관리 복잡도 |
| 권장 방향 | 법령/매뉴얼은 조항+문단 혼합, 사례는 의미 단위 Chunking |
| ADR 필요성 | 높음 |
| 작성 ADR | [ADR-0012: 기준자료 Chunking 정책](adr/ADR-0012-reference-chunking-policy.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 022. RAG 근거 표시 개수 및 관련도 기준

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | AI 검토 결과마다 근거를 몇 개까지 표시할 것인가 |
| 배경 | 근거가 너무 많으면 사용성이 떨어지고, 너무 적으면 설명력이 부족함 |
| 검토 대안 | ① Top-1 ② Top-3 ③ Top-5 ④ 관련도 임계값 기반 |
| 결정 필요사항 | Top-K, relevance threshold, 근거 없음 처리 방식 확정 |
| 주요 쟁점 | 설명 가능성, 화면 복잡도, 검토 속도 |
| 권장 방향 | 기본 Top-3, 관련도 임계값 미달 시 “기준자료 확인 필요” 표시 |
| ADR 필요성 | 높음 |
| 작성 ADR | [ADR-0012: 기준자료 Chunking 정책](adr/ADR-0012-reference-chunking-policy.md) |
| 결정 상태 | Accepted |

---

# 11. AI 분석 엔진 관련 의사결정

## ADR 후보 023. Rule Engine과 LLM/RAG 역할 분리

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | 정형 검토와 문맥 검토를 어떻게 분리할 것인가 |
| 배경 | 필수 문구 누락, 금리 표시 등은 규칙 기반이 적합하고 과장·오인 표현은 문맥 판단이 필요함 |
| 검토 대안 | ① Rule 중심 ② LLM 중심 ③ Rule + RAG + LLM 하이브리드 |
| 결정 필요사항 | 검토 유형별 엔진 책임 범위 확정 |
| 주요 쟁점 | 정확도, 설명 가능성, 구현 복잡도 |
| 권장 방향 | 정형 항목은 Rule Engine, 문맥 항목은 RAG/LLM, 화면 요소는 Multimodal Engine |
| ADR 필요성 | 높음 |
| 작성 ADR | [ADR-0013: Rule, RAG, LLM 역할 분리](adr/ADR-0013-rule-rag-llm-responsibility.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 024. OCR/VLM 텍스트 추출 방식

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | 광고물 텍스트 추출을 어떤 기술로 수행할 것인가 |
| 배경 | PDF, 이미지, 모바일 캡처, 배너 등 비정형 광고물 인식 필요 |
| 검토 대안 | ① OCR 엔진 ② VLM 기반 추출 ③ OCR+VLM 혼합 |
| 결정 필요사항 | 기본 추출 엔진, 실패 시 fallback 정책 확정 |
| 주요 쟁점 | 정확도, 비용, 속도, 사내망 운영 가능성 |
| 권장 방향 | PoC에서는 OCR+VLM 혼합 검토 |
| ADR 필요성 | 높음 |
| 작성 ADR | [ADR-0014: 교체 가능한 문서 파서 및 OCR 아키텍처](adr/ADR-0014-pluggable-document-parser-ocr.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 025. 광고 화면 좌표 체계

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | OCR 좌표와 Annotation 좌표의 기준을 무엇으로 할 것인가 |
| 배경 | 광고 화면 위 Bounding Box 표시를 위해 좌표 기준이 일관되어야 함 |
| 검토 대안 | ① 원본 이미지 좌표 ② 렌더링 화면 좌표 ③ 정규화 좌표 |
| 결정 필요사항 | 좌표 저장 기준, 화면 변환 방식 확정 |
| 주요 쟁점 | 프론트 렌더링, 확대/축소, PDF 페이지별 좌표 처리 |
| 권장 방향 | 원본 기준 좌표와 정규화 좌표를 함께 관리 |
| ADR 필요성 | 높음 |
| 관련 ADR | [ADR-0014: 교체 가능한 문서 파서 및 OCR 아키텍처](adr/ADR-0014-pluggable-document-parser-ocr.md) |
| 작성 ADR | [ADR-0015: 광고 화면 좌표 체계](adr/ADR-0015-ad-coordinate-system.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 026. AI 판단 결과의 신뢰도 및 위험도 산정 기준

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | HIGH/MEDIUM/LOW/CHECK_REQUIRED 위험도를 어떻게 산정할 것인가 |
| 배경 | 사용자에게 검토 우선순위를 제공하려면 위험도 기준이 필요함 |
| 검토 대안 | ① Rule 기반 점수 ② LLM 판단 ③ Rule+LLM+근거 관련도 혼합 |
| 결정 필요사항 | 위험도 산정 로직과 기준표 확정 |
| 주요 쟁점 | 설명 가능성, 담당자 수용성, 일관성 |
| 권장 방향 | 정형 규칙 + 근거 관련도 + LLM 판단 사유를 조합하되 최종 기준표를 문서화 |
| ADR 필요성 | 높음 |
| 작성 ADR | [ADR-0018: 위험도 산정 기준](adr/ADR-0018-risk-level-decision-policy.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 027. 프롬프트 및 Agent 버전관리

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | LLM 프롬프트와 Agent 설정을 어떻게 버전관리할 것인가 |
| 배경 | AI 판단 결과 재현성과 변경 추적이 필요함 |
| 검토 대안 | ① 코드 내 관리 ② DB 관리 ③ Git 파일 관리 ④ Prompt Registry |
| 결정 필요사항 | 프롬프트 저장 위치, 배포 방식, 실험 이력 관리 기준 확정 |
| 주요 쟁점 | 재현성, 실험 관리, 운영 편의성 |
| 권장 방향 | PoC는 Git 관리, 본사업은 DB/Registry 검토 |
| ADR 필요성 | 높음 |
| 작성 ADR | [ADR-0016: 프롬프트 및 Agent 설정 버전관리](adr/ADR-0016-prompt-agent-config-versioning.md) |
| 결정 상태 | Accepted |

---

# 12. 테스트 및 품질 관련 의사결정

## ADR 후보 028. TDD 적용 범위

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | TDD를 모든 기능에 적용할 것인가, 핵심 기능에 우선 적용할 것인가 |
| 배경 | 모든 주요 기능에 테스트 케이스를 추가한다는 원칙이 있으나 PoC 일정 고려 필요 |
| 검토 대안 | ① 전 기능 TDD ② 핵심 API 우선 TDD ③ 사후 테스트 작성 |
| 결정 필요사항 | P0/P1 테스트 범위 확정 |
| 주요 쟁점 | 개발 속도와 품질 간 균형 |
| 권장 방향 | P0/P1 API와 핵심 서비스 로직은 테스트 필수 |
| ADR 필요성 | 높음 |
| 작성 ADR | [ADR-0008: TDD 및 테스트 적용 범위](adr/ADR-0008-tdd-and-test-scope.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 029. AI 결과 테스트 방식

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | AI 검토 결과를 어떻게 테스트할 것인가 |
| 배경 | LLM/RAG 결과는 deterministic하지 않을 수 있어 일반 단위 테스트와 다름 |
| 검토 대안 | ① Snapshot Test ② 정답 데이터셋 기반 평가 ③ 수동 검증 ④ Mock 기반 API 테스트 |
| 결정 필요사항 | AI 평가 기준, 허용 오차, Mock 사용 여부 확정 |
| 주요 쟁점 | 재현성, 비용, 테스트 안정성 |
| 권장 방향 | API 테스트는 Mock 기반, PoC 평가는 데이터셋 기반 정량 평가와 담당자 피드백 요약 |
| ADR 필요성 | 높음 |
| 작성 ADR | [ADR-0008: TDD 및 테스트 적용 범위](adr/ADR-0008-tdd-and-test-scope.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 030. CI에서 실행할 테스트 범위

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | CI에서 어떤 테스트까지 자동 실행할 것인가 |
| 배경 | ruff, pytest, Docker build는 기본 방침이나 AI 통합 테스트는 비용과 시간이 큼 |
| 검토 대안 | ① 전체 테스트 ② Unit/API 테스트만 ③ PR별 경량 테스트 + 야간 통합 테스트 |
| 결정 필요사항 | PR 시 필수 테스트와 정기 테스트 구분 |
| 주요 쟁점 | CI 시간, 비용, 신뢰성 |
| 권장 방향 | PR은 ruff+unit/API test, 통합/AI 평가는 별도 파이프라인 |
| ADR 필요성 | 중간 |
| 작성 ADR | [ADR-0008: TDD 및 테스트 적용 범위](adr/ADR-0008-tdd-and-test-scope.md) |
| 결정 상태 | Accepted |

---

# 13. 인프라 및 배포 관련 의사결정

## ADR 후보 031. Docker 컨테이너 분리 기준

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | 백엔드, 프론트엔드, AI 워커, DB, 검색엔진을 어떤 단위로 컨테이너화할 것인가 |
| 배경 | 서비스별 의존성과 리소스 특성이 다름 |
| 검토 대안 | ① 단일 컨테이너 ② 기능별 컨테이너 분리 ③ Kubernetes 전제 구성 |
| 결정 필요사항 | 컨테이너 구성 및 docker-compose 구조 확정 |
| 주요 쟁점 | 운영 복잡도, 장애 격리, 배포 편의성 |
| 권장 방향 | PoC는 docker-compose 기반 기능별 컨테이너 분리 |
| ADR 필요성 | 높음 |
| 작성 ADR | [ADR-0007: Docker Compose 기반 빌드 및 배포 방식](adr/ADR-0007-docker-compose-build-deploy.md) |
| 후속 ADR | [ADR-0063: Docker Compose 공통 파일 및 dev/prod Override 구성 정책](adr/ADR-0063-compose-base-dev-prod-override-policy.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 032. 개발 VM 구성

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | 여의도 서버 VM의 표준 사양과 구성 기준을 어떻게 둘 것인가 |
| 배경 | 개발 VM은 인프라 담당자에게 신청하여 사용 예정 |
| 검토 대안 | ① 개인별 VM ② 프로젝트 공용 VM ③ 서비스별 VM ④ 로컬 개발 + 프로젝트 공용 개발 VM 병행 |
| 결정 필요사항 | CPU, Memory, Disk, 포트, Docker 사용 기준 확정 |
| 주요 쟁점 | 리소스 효율, 접근권한, 보안 |
| 권장 방향 | PoC는 로컬 개발 + 프로젝트 공용 개발 VM 병행 |
| ADR 필요성 | 중간 |
| 작성 ADR | [ADR-0033: 로컬 개발 및 공용 개발 VM 병행](adr/ADR-0033-local-and-shared-dev-vm.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 033. Self-hosted Runner 배포 방식

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | CI/CD 배포를 Self-hosted Runner로 수행할 것인가 |
| 배경 | 내부망 또는 여의도 서버 접근이 필요할 수 있음 |
| 검토 대안 | ① GitHub-hosted Runner ② Self-hosted Runner ③ 수동 배포 |
| 결정 필요사항 | Runner 위치, 권한, 비밀값 관리, 배포 대상 확정 |
| 주요 쟁점 | 보안, 네트워크 접근, 운영 안정성 |
| 권장 방향 | Self-hosted Runner 사용 |
| ADR 필요성 | 높음 |
| 관련 ADR | [ADR-0007: Docker Compose 기반 빌드 및 배포 방식](adr/ADR-0007-docker-compose-build-deploy.md) |
| 작성 ADR | [ADR-0019: Self-hosted Runner 배포 방식](adr/ADR-0019-self-hosted-runner-deployment.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 034. 환경 분리 정책

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | dev/stage/prod 환경을 어떻게 분리할 것인가 |
| 배경 | PoC라도 기준자료, 광고물, 검증 데이터가 섞이면 문제가 발생할 수 있음 |
| 검토 대안 | ① 단일 dev ② dev/stage 분리 ③ dev/stage/prod 분리 |
| 결정 필요사항 | PoC 단계 환경 수와 데이터 분리 기준 확정 |
| 주요 쟁점 | 인프라 리소스, 보안, 테스트 신뢰성 |
| 권장 방향 | PoC는 dev와 prod(main) 2개 환경으로 분리하고 데이터/secret은 별도 관리 |
| ADR 필요성 | 중간 |
| 관련 ADR | [ADR-0007: Docker Compose 기반 빌드 및 배포 방식](adr/ADR-0007-docker-compose-build-deploy.md) |
| 작성 ADR | [ADR-0020: PoC dev/prod(main) 환경 분리 정책](adr/ADR-0020-dev-prod-environment-separation.md) |
| 결정 상태 | Accepted |

---

# 14. 보안 및 고객사 자료 관리 관련 의사결정

## ADR 후보 035. 고객사 자료 반출 및 AI 입력 제한

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | 고객사 자료를 외부 AI 도구에 입력할 수 있는가 |
| 배경 | 광고물, 내부 매뉴얼, 심의사례, 상품설명서 등 민감 자료 포함 가능 |
| 검토 대안 | ① 외부 AI 입력 금지 ② 익명화 후 허용 ③ 내부망 AI만 허용 |
| 결정 필요사항 | 자료 등급별 AI 입력 가능 여부 확정 |
| 주요 쟁점 | 보안, 계약, 개인정보, 내부 기준 |
| 권장 방향 | 고객사 원문/내부자료는 외부 AI 입력 금지, 필요 시 익명화·승인 절차 적용 |
| ADR 필요성 | 매우 높음 |
| 작성 ADR | [ADR-0002: 고객사 샘플 데이터 외부 AI 입력 정책](adr/ADR-0002-customer-sample-data-ai-input-policy.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 036. 파일 접근 권한 및 다운로드 정책

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | 광고물 원본과 리포트 파일의 접근 권한을 어떻게 통제할 것인가 |
| 배경 | 광고 원본, 상품설명서, 약관 등 민감 파일 접근 제어 필요 |
| 검토 대안 | ① 역할 기반 접근 ② 부서 기반 접근 ③ 건별 권한 |
| 결정 필요사항 | 파일 미리보기/다운로드 권한 기준 확정 |
| 주요 쟁점 | 업무 편의성, 보안, 감사 대응 |
| 권장 방향 | 역할+부서 기반 권한, 다운로드 감사 로그 필수 |
| ADR 필요성 | 높음 |
| 작성 ADR | [ADR-0021: 파일 접근 권한 및 다운로드 정책](adr/ADR-0021-file-access-download-policy.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 037. 감사 로그 저장 범위

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | 어떤 행위를 감사 로그로 남길 것인가 |
| 배경 | 광고물 검토와 기준자료 변경은 사후 추적이 필요함 |
| 검토 대안 | ① 주요 변경만 기록 ② 조회 포함 전체 기록 ③ 파일 다운로드만 추가 기록 |
| 결정 필요사항 | 로그 대상 행위, 보관 기간, 민감정보 제외 기준 확정 |
| 주요 쟁점 | 로그 용량, 개인정보, 감사 대응 |
| 권장 방향 | 등록/수정/삭제/분석요청/리포트생성/다운로드/기준자료 변경은 필수 기록 |
| ADR 필요성 | 높음 |
| 작성 ADR | [ADR-0022: 감사 로그 저장 범위](adr/ADR-0022-audit-log-scope.md) |
| 결정 상태 | Accepted |

---

# 15. PoC 검증 및 평가 관련 의사결정

## ADR 후보 038. PoC KPI 산식 확정

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | 필수 문구 정확도, 위험 표현 정확도, 근거 매칭 적정성, 담당자 판단 일치율 산식을 어떻게 확정할 것인가 |
| 배경 | 협업계획서에 KPI 목표는 있으나 실제 표본, 정답지, 제외 기준은 협의 필요 |
| 검토 대안 | ① 항목 단위 평가 ② 광고물 단위 평가 ③ 리스크 단위 평가 |
| 결정 필요사항 | 분자/분모, 평가 단위, 부분 정답 처리 기준 확정 |
| 주요 쟁점 | 평가 공정성, 담당자 판단 편차, 샘플 수 |
| 권장 방향 | 항목 단위 평가 + 평가 제외 기준 별도 관리 |
| ADR 필요성 | 높음 |
| 작성 ADR | [ADR-0023: PoC KPI 산식 확정](adr/ADR-0023-poc-kpi-formulas.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 039. 평가 제외 기준

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | 어떤 샘플 또는 항목을 평가에서 제외할 것인가 |
| 배경 | OCR 판독 불가, 상품조건 불명확, 내부 기준 미제공 등은 정답 판정이 어려움 |
| 검토 대안 | ① 제외 없음 ② 사전 정의 기준으로 제외 ③ 담당자 협의 후 제외 |
| 결정 필요사항 | 평가 제외 사유 코드 정의 |
| 주요 쟁점 | KPI 왜곡 가능성, 샘플 수 감소 |
| 권장 방향 | 제외 사유를 명시하고 산식에서 제외 여부를 평가보고서에 표시 |
| ADR 필요성 | 높음 |
| 작성 ADR | [ADR-0024: 평가 제외 기준](adr/ADR-0024-evaluation-exclusion-policy.md) |
| 결정 상태 | Accepted |

---

## ADR 후보 040. 정성 평가 수집 방식

| 항목 | 내용 |
| --- | --- |
| 의사결정 주제 | 담당자 피드백을 어떻게 수집하고 평가에 반영할 것인가 |
| 배경 | PoC는 정량 성능뿐 아니라 업무 적용 가능성, 설명 이해도, 문구 추천 유용성 평가가 중요함 |
| 검토 대안 | ① 설문 ② 인터뷰 ③ 시스템 내 피드백 버튼 ④ 회의록 기반 정리 |
| 결정 필요사항 | 정성 평가 진행 여부와 담당자 피드백 대체 범위 확정 |
| 주요 쟁점 | 응답 편차, 정량화 어려움, PoC 우선순위 |
| 권장 방향 | 정성 평가는 보류하고 담당자 피드백으로 대체, 추후 진행 여부 재검토 |
| ADR 필요성 | 중간 |
| 작성 ADR | [ADR-0025: 정성 평가 보류 및 담당자 피드백 대체](adr/ADR-0025-defer-qualitative-evaluation.md) |
| 결정 상태 | Accepted |

---

# 16. 우선적으로 ADR 작성이 필요한 항목

다음 항목은 개발 착수 전 또는 초기 Sprint 내에 우선 결정하는 것이 좋다.

| 우선순위 | ADR 후보 | 결정 필요 시점 |
| --- | --- | --- |
| 1 | 고객사 자료 반출 및 AI 입력 제한 | 즉시 |
| 2 | 명세 기반 개발 방식 채택 | 즉시 |
| 3 | 모노레포 구조 채택 | 저장소 생성 전 |
| 4 | Git/Notion/Wiki 역할 분리 | 문서 관리 시작 전 |
| 5 | Python 백엔드 프레임워크 선택 | 백엔드 구현 전 |
| 6 | PostgreSQL 사용 | DB 설계 확정 전 |
| 7 | Qdrant 사용 | RAG 개발 전 |
| 8 | OpenSearch 사용 | 검색 개발 전 |
| 9 | Hybrid Search 전략 | RAG 품질 검증 전 |
| 10 | Rule/RAG/LLM 역할 분리 | AI 엔진 설계 전 |
| 11 | OCR/VLM 텍스트 추출 방식 | 광고물 분석 구현 전 |
| 12 | 파일 저장소 선택 | 파일 업로드 구현 전 |
| 13 | Docker 컨테이너 분리 기준 | 개발환경 구성 전 |
| 14 | Self-hosted Runner 배포 방식 | CI/CD 구성 전 |
| 15 | TDD 적용 범위 | 개발 착수 전 |
| 16 | PoC KPI 산식 확정 | 검증 데이터셋 구축 전 |
| 17 | 평가 제외 기준 | PoC 평가 전 |

---

# 17. ADR 작성 로드맵

## 17.1 1차 ADR: 개발 착수 전

| ADR | 주제 |
| --- | --- |
| [ADR-0001](adr/ADR-0001-spec-driven-development.md) | 명세 기반 개발 방식 채택 |
| [ADR-0002](adr/ADR-0002-customer-sample-data-ai-input-policy.md) | 고객사 자료 반출 및 AI 입력 제한 |
| [ADR-0003](adr/ADR-0003-monorepo-structure.md) | 모노레포 구조 채택 |
| [ADR-0004](adr/ADR-0004-git-notion-wiki-roles.md) | Git, Notion, Wiki 역할 분리 |
| [ADR-0005](adr/ADR-0005-fastapi-backend-framework.md) | Python 백엔드 프레임워크 선택 |
| [ADR-0006](adr/ADR-0006-postgresql-primary-database.md) | PostgreSQL 사용 |
| [ADR-0007](adr/ADR-0007-docker-compose-build-deploy.md) | Docker Compose 기반 빌드 및 배포 방식 |
| [ADR-0008](adr/ADR-0008-tdd-and-test-scope.md) | TDD 적용 범위 |

---

## 17.2 2차 ADR: AI/RAG 구현 전

| ADR | 주제 |
| --- | --- |
| [ADR-0009](adr/ADR-0009-qdrant-vector-database.md) | Qdrant 사용 |
| [ADR-0010](adr/ADR-0010-opensearch-keyword-search.md) | OpenSearch 사용 |
| [ADR-0011](adr/ADR-0011-hybrid-search-strategy.md) | Hybrid Search 전략 |
| [ADR-0012](adr/ADR-0012-reference-chunking-policy.md) | 기준자료 Chunking 정책 |
| [ADR-0013](adr/ADR-0013-rule-rag-llm-responsibility.md) | Rule/RAG/LLM 역할 분리 |
| [ADR-0014](adr/ADR-0014-pluggable-document-parser-ocr.md) | 교체 가능한 문서 파서 및 OCR 아키텍처 |
| [ADR-0015](adr/ADR-0015-ad-coordinate-system.md) | 광고 화면 좌표 체계 |
| [ADR-0016](adr/ADR-0016-prompt-agent-config-versioning.md) | 프롬프트 및 Agent 버전관리 |
| [ADR-0017](adr/ADR-0017-s3-compatible-object-storage.md) | S3 호환 Object Storage 기반 파일 저장소 |
| [ADR-0018](adr/ADR-0018-risk-level-decision-policy.md) | 위험도 산정 기준 |

---

## 17.3 3차 ADR: 배포/검증 전

| ADR | 주제 |
| --- | --- |
| [ADR-0019](adr/ADR-0019-self-hosted-runner-deployment.md) | Self-hosted Runner 배포 방식 |
| [ADR-0020](adr/ADR-0020-dev-prod-environment-separation.md) | 환경 분리 정책 |
| [ADR-0021](adr/ADR-0021-file-access-download-policy.md) | 파일 접근 권한 및 다운로드 정책 |
| [ADR-0022](adr/ADR-0022-audit-log-scope.md) | 감사 로그 저장 범위 |
| [ADR-0023](adr/ADR-0023-poc-kpi-formulas.md) | PoC KPI 산식 확정 |
| [ADR-0024](adr/ADR-0024-evaluation-exclusion-policy.md) | 평가 제외 기준 |
| [ADR-0025](adr/ADR-0025-defer-qualitative-evaluation.md) | 정성 평가 보류 및 담당자 피드백 대체 |

---

## 17.4 구현 착수 전 보완 ADR

| ADR | 주제 |
| --- | --- |
| [ADR-0026](adr/ADR-0026-api-contract-management.md) | API 명세 관리 및 동기화 강제 방식 |
| [ADR-0027](adr/ADR-0027-api-response-standard.md) | API 응답 표준 |
| [ADR-0028](adr/ADR-0028-id-generation-policy.md) | ID 생성 규칙 |
| [ADR-0029](adr/ADR-0029-postgresql-schema-separation.md) | PostgreSQL 영역별 Schema 분리 |
| [ADR-0030](adr/ADR-0030-frontend-stack.md) | 프론트엔드 스택 선택 |
| [ADR-0031](adr/ADR-0031-ai-assisted-development-responsibility.md) | AI 활용 개발 및 검증 책임 |
| [ADR-0032](adr/ADR-0032-frontend-first-implementation-policy.md) | 프론트엔드 1차 구현 및 디자인 개선 방식 |
| [ADR-0033](adr/ADR-0033-local-and-shared-dev-vm.md) | 로컬 개발 및 공용 개발 VM 병행 |
| [ADR-0034](adr/ADR-0034-codex-claude-skills-standardization.md) | Claude/Codex Skills 표준화 및 온보딩 설치 |

---

## 17.5 후속 구현 ADR

| ADR | 주제 |
| --- | --- |
| [ADR-0035](adr/ADR-0035-redis-queue-postgresql-job-state.md) | Redis Queue 및 PostgreSQL Job 상태 테이블 병행 |
| [ADR-0036](adr/ADR-0036-jwt-auth-sso-ready-authorization.md) | PoC 자체 JWT 인증 및 SSO 전환 가능 인가 구조 |
| [ADR-0037](adr/ADR-0037-file-upload-allowlist-and-size-limit.md) | 파일 업로드 허용 확장자 및 용량 제한 |
| [ADR-0038](adr/ADR-0038-report-output-format-policy.md) | 리포트 출력 형식 정책 |
| [ADR-0039](adr/ADR-0039-suggestion-decision-policy.md) | 문구 추천 검토·채택·수정 정책 |
| [ADR-0040](adr/ADR-0040-standard-versioning-and-effective-date-policy.md) | 기준자료 버전관리 및 검토 기준일 정책 |
| [ADR-0041](adr/ADR-0041-alembic-migration-and-seed-policy.md) | Alembic 기반 DB 마이그레이션 및 Seed 분리 정책 |
| [ADR-0042](adr/ADR-0042-poc-runtime-performance-targets.md) | PoC 런타임 성능 목표 기준 |
| [ADR-0043](adr/ADR-0043-rag-evidence-selection-policy.md) | RAG 검색 결과 선정 및 근거 표시 정책 |
| [ADR-0044](adr/ADR-0044-ai-mock-fixture-test-policy.md) | AI/OCR/RAG Mock 및 Fixture 테스트 정책 |
| [ADR-0045](adr/ADR-0045-user-error-message-policy.md) | 사용자 오류 메시지 및 오류 코드 표시 정책 |
| [ADR-0046](adr/ADR-0046-postgresql-db-account-separation.md) | PostgreSQL DB 계정 분리 정책 |
| [ADR-0047](adr/ADR-0047-poc-backup-and-restore-policy.md) | PoC 백업 및 복구 정책 |
| [ADR-0048](adr/ADR-0048-poc-personal-sensitive-data-policy.md) | PoC 개인정보 및 민감정보 저장/노출 정책 |
| [ADR-0049](adr/ADR-0049-poc-table-partitioning-policy.md) | PoC 대용량 테이블 파티셔닝 적용 정책 |
| [ADR-0050](adr/ADR-0050-reference-metadata-policy.md) | 기준자료 유형별 메타데이터 및 관리 단위 정책 |
| [ADR-0051](adr/ADR-0051-annotation-display-policy.md) | 검토 UI Annotation 표현 방식 |
| [ADR-0052](adr/ADR-0052-text-ir-offset-policy.md) | HWP/HWPX 텍스트 IR 및 Offset 기준 |
| [ADR-0053](adr/ADR-0053-confidence-threshold-policy.md) | OCR/Parser/Annotation 신뢰도 임계값 및 확인 필요 처리 기준 |
| [ADR-0054](adr/ADR-0054-report-snapshot-hwpx-pdf-conversion.md) | 리포트 스냅샷 및 HWPX-PDF 변환 방식 |
| [ADR-0055](adr/ADR-0055-api-authorization-scope-policy.md) | API 인가 범위 및 부서 Scope 판정 기준 |
| [ADR-0056](adr/ADR-0056-jwt-session-token-lifetime-policy.md) | JWT 세션 및 토큰 수명 정책 |
| [ADR-0057](adr/ADR-0057-browser-security-cors-csrf-headers.md) | 브라우저 보안 정책, CORS/CSRF 및 보안 헤더 기준 |
| [ADR-0058](adr/ADR-0058-login-failure-lockout-password-policy.md) | 로그인 실패 제한, 계정 잠금 및 비밀번호 정책 |
| [ADR-0059](adr/ADR-0059-ai-job-timeout-retry-deadletter-policy.md) | AI 분석 Job Timeout, Retry, Dead-letter 및 Worker 장애 복구 정책 |
| [ADR-0060](adr/ADR-0060-poc-core-screen-ui-detail-policy.md) | PoC 핵심 화면 UI 상세화 및 반응형 범위 정책 |
| [ADR-0061](adr/ADR-0061-rag-search-infra-failure-policy.md) | RAG 검색 인프라 장애 처리 및 Fallback 금지 정책 |
| [ADR-0062](adr/ADR-0062-openapi-initial-contract-scope-and-validation.md) | OpenAPI 초기 계약 작성 범위 및 검증 단계 정책 |
| [ADR-0063](adr/ADR-0063-compose-base-dev-prod-override-policy.md) | Docker Compose 공통 파일 및 dev/prod Override 구성 정책 |
| [ADR-0064](adr/ADR-0064-ci-cd-quality-gate-test-split-policy.md) | CI/CD 검증 Gate 및 테스트 실행 분리 정책 |
| [ADR-0065](adr/ADR-0065-normalized-document-schema-and-adapter-contract.md) | NormalizedDocument 공통 출력 스키마 및 Parser/OCR Adapter 계약 정책 |
| [ADR-0066](adr/ADR-0066-coordinate-persistence-and-api-response-policy.md) | Coordinate 필드 영속화 및 API 응답 구조 정합화 정책 |
| [ADR-0067](adr/ADR-0067-parser-ocr-raw-artifact-storage-retention-policy.md) | Parser/OCR Raw Artifact 저장 위치, 보존 기간 및 접근 정책 |
| [ADR-0068](adr/ADR-0068-risk-rationale-persistence-and-api-response-policy.md) | 위험도 산정 근거 영속화 및 API 응답 정책 |
| [ADR-0069](adr/ADR-0069-standard-reindex-and-chunk-query-api-policy.md) | 기준자료 재색인 및 Chunk 조회 API 정책 |
| [ADR-0070](adr/ADR-0070-search-index-idempotent-sync-policy.md) | Qdrant/OpenSearch 인덱스 동기화 및 Idempotent Upsert/Delete 정책 |
| [ADR-0071](adr/ADR-0071-search-index-schema-analyzer-payload-policy.md) | 검색 인덱스 스키마, Analyzer/Synonym/Highlight 및 Payload 표준화 정책 |
| [ADR-0072](adr/ADR-0072-parser-ocr-engine-routing-policy.md) | Parser/OCR 기본 엔진 선택 및 파일 유형별 라우팅 정책(Superseded) |
| [ADR-0073](adr/ADR-0073-parser-ocr-quality-rerun-policy.md) | Parser/OCR 품질 미달 시 재처리 및 보조 엔진 사용 정책 |
| [ADR-0074](adr/ADR-0074-validation-dataset-golden-label-snapshot-policy.md) | PoC 검증 데이터셋, 정답지 및 평가 Snapshot 관리 정책 |
| [ADR-0075](adr/ADR-0075-project-scoped-skills-distribution.md) | 프로젝트 범위 Skills 배포 및 온보딩 설치 정책 |
| [ADR-0076](adr/ADR-0076-ai-tool-lifecycle-hook-enforcement-policy.md) | AI 도구 Lifecycle Hook 적용 범위 및 문서 거버넌스 강제 계층 |
| [ADR-0077](adr/ADR-0077-git-notion-one-way-document-sync-policy.md) | Git-Notion 단방향 문서 자동 동기화 정책 |
| [ADR-0078](adr/ADR-0078-poc-two-account-operation-profile.md) | PoC 2계정 운영 프로필 정책 |
| [ADR-0079](adr/ADR-0079-hwp-hwpx-hybrid-parser-composition.md) | HWP/HWPX 이중 원천 Hybrid Parser 구성 정책 |

---

## 17.6 ADR 검토 현황 및 종료 기준

현재 최초 후보 목록과 후속 구현 ADR 검토 과정에서 도출된 결정사항은 ADR-0081까지 문서화했다. 문서 거버넌스, Notion 공유본, PoC 계정, HWP/HWPX 구조화와 Parser/OCR 활성화 경계에서 도출된 후보 041~046도 모두 결정되었다.

| 항목 | 현황 |
| --- | --- |
| 작성 완료 ADR | ADR-0001 ~ ADR-0081, 총 81건 |
| 의사결정 질문지 | Q1 ~ Q75 모두 결정 결과 기록 완료 |
| 현재 대기 중인 ADR 후보 | 없음 |
| 남은 재검토 항목 | 본사업 전환, 고객사 보안 요구, 운영 데이터 확대, 성능 병목 확인 시 재검토할 항목만 존재 |

정합성 기준은 다음과 같다.

- ADR 번호, 제목, 상태의 공식 원장은 `docs/adr/README.md`이다.
- 본 문서의 후보 상세 항목은 최초 후보 001~040의 이력이며, ADR-0035 이후 후속 구현 ADR과 1:1 후보 번호를 맞추지 않는다.
- 사용자 질의 번호는 ADR 번호와 일치하지 않는다. 예를 들어 Q70은 ADR-0075, Q71은 ADR-0076, Q72는 ADR-0077, Q73은 ADR-0078, Q74는 ADR-0079, Q75는 ADR-0081의 검토 질문이다.
- 후속 구현 ADR은 본 문서 17.5에서 누락 없이 참조하고, 신규 결정이 생길 때만 별도 후보 또는 후속 구현 ADR로 추가한다.

PoC 구현 착수 기준의 제품 기술·업무·보안·품질 결정과 개발자 온보딩·AI 도구 거버넌스·Notion 공유본·HWP/HWPX hybrid parser·Parser/OCR 활성화 경계 재검토는 완료되었다. 후보 041은 ADR-0075, 후보 042는 ADR-0076, 후보 043은 ADR-0077, 후보 044는 ADR-0078, 후보 045는 ADR-0079, 후보 046은 ADR-0081로 확정했다. 이후 ADR은 정해진 목록을 계속 순회하지 않고, 다음 조건 중 하나가 발생할 때만 신규 후보로 추가한다.

1. 기존 ADR과 충돌하는 구현 제약이 발견된 경우
2. 고객사 요구나 보안 정책이 변경된 경우
3. PoC 범위가 본사업 수준으로 확대되는 경우
4. 성능, 비용, 품질, 운영 리스크가 기존 결정의 전제를 깨는 경우
5. 개발자가 임의로 판단하기 어려운 새 아키텍처 선택지가 발생한 경우

---

## 17.7 문서 거버넌스 적용 후 재검토 후보

### ADR 후보 041. 프로젝트 범위 Skills 배포 위치

| 항목 | 내용 |
| --- | --- |
| 상태 | 결정 완료(ADR-0075 Accepted) |
| 관련 질문 | Q70 |
| 관련 ADR | ADR-0034 |
| 승인 시 ADR | ADR-0075 제안 |
| 권고안 | `skills/` 단일 원본 + 프로젝트 로컬 탐색 경로 adapter 생성 |

ADR-0034는 `skills/`를 Git 원본으로 두고 사용자 홈의 `~/.codex/skills`, `~/.claude/skills`에 심볼릭 링크를 설치했다. 이 방식은 사용자 홈을 변경하고, 동일 이름의 다른 저장소 Skill과 충돌할 수 있으며, 저장소를 벗어난 세션에도 프로젝트 Skill이 노출된다.

결정 결과 B안을 채택했다. `skills/`를 단일 원본으로 유지하고 온보딩 스크립트가 `.agents/skills`, `.claude/skills`에 프로젝트 로컬 adapter를 생성한다. 심볼릭 링크를 우선하되 지원하지 않는 환경은 복사본과 hash 검증으로 대체하며 사용자 홈 설치는 중단한다. 상세 기준은 [ADR-0075](adr/ADR-0075-project-scoped-skills-distribution.md)를 따른다.

ADR-0034의 사용자 홈 설치 결정은 ADR-0075로 대체되었다.

### ADR 후보 042. AI 도구 lifecycle hook 적용 범위

| 항목 | 내용 |
| --- | --- |
| 상태 | 결정 완료(ADR-0076 Accepted) |
| 관련 질문 | Q71 |
| 관련 ADR | ADR-0034, ADR-0064 |
| 승인 ADR | [ADR-0076](adr/ADR-0076-ai-tool-lifecycle-hook-enforcement-policy.md) |
| 권고안 | PoC에서는 Git hook + CI를 강제 계층으로 유지 |

Claude/Codex의 도구별 lifecycle hook은 AI가 파일을 편집하거나 작업을 종료하는 시점에 즉시 검사할 수 있지만, 실행 이벤트와 설정 형식이 도구별로 달라 동일 정책을 이중 구현해야 한다. 프로젝트의 실제 merge 차단 기준은 개발자가 어떤 AI 도구나 IDE를 사용하더라도 동일해야 한다.

결정 결과 A안을 채택했다. PoC에서는 `AGENTS.md`, `CLAUDE.md`, Skills를 작업 지침·예방 계층으로 사용하고, `.githooks/pre-commit`, `.githooks/pre-push`, GitHub Actions를 공통 강제 계층으로 사용한다. Claude/Codex의 도구별 lifecycle hook은 필수 설치하지 않으며, 반복적인 누락이 관찰되거나 팀이 특정 도구로 표준화될 때 새 ADR 후보로 재검토한다. 상세 기준은 [ADR-0076](adr/ADR-0076-ai-tool-lifecycle-hook-enforcement-policy.md)을 따른다.

### ADR 후보 043. Git-Notion 문서 동기화 운영 방식

| 항목 | 내용 |
| --- | --- |
| 상태 | 결정 완료(ADR-0077 Accepted) |
| 관련 질문 | Q72 |
| 관련 ADR | ADR-0004 |
| 승인 ADR | [ADR-0077](adr/ADR-0077-git-notion-one-way-document-sync-policy.md) |
| 권고안 | Git `main` 원본에서 기존 Notion page ID를 보존하는 단방향 자동 증분 갱신 |

기존 Notion publisher는 비어 있는 부모 페이지에 전체 문서를 만드는 수동 테스트이므로 Git 문서 변경 후 공유본 drift를 방지하지 못한다. 전체 재생성은 page URL과 댓글을 잃고, 양방향 동기화는 공식 원천과 충돌 해결 책임을 불명확하게 만든다.

결정 결과 Git `main`을 원천으로 유지하고 변경된 Markdown만 기존 Notion page ID에 자동 갱신한다. source path-page ID mapping을 Git에서 관리하고 페이지별 잠금 해제, update, 내용 검증, 실패 rollback, 재잠금 순서로 실행한다. 신규·삭제·이름 변경은 mapping과 공유 URL 영향을 검토하지 않은 상태에서 자동 추론하지 않는다. 상세 기준은 ADR-0077을 따른다.

---

### ADR 후보 044. PoC 로그인 계정 운영 프로필

| 항목 | 내용 |
| --- | --- |
| 상태 | 결정 완료(ADR-0078 Accepted) |
| 관련 질문 | Q73 |
| 관련 ADR | ADR-0036, ADR-0055, ADR-0058 |
| 승인 ADR | [ADR-0078](adr/ADR-0078-poc-two-account-operation-profile.md) |
| 권고안 | 역할 모델은 유지하고 활성 PoC 로그인 계정만 test/admin 두 개로 운영 |

PoC 데모와 수동 검증에 역할별 별도 계정을 여러 개 사용하면 온보딩과 계정 선택이 복잡해진다. 반대로 권한 모델까지 두 역할로 축소하면 API 인가와 향후 본사업 역할 분리 검증이 약해진다.

결정 결과 `test@ihopper.co.kr`에는 광고 업무·검토와 기준자료 관리를 함께 검증할 수 있도록 `PRODUCT_DEPARTMENT_USER`, `COMPLIANCE_REVIEWER`, `STANDARD_MANAGER`를 부여한다. `admin@ihopper.co.kr`는 `SYSTEM_ADMIN`으로 운영한다. 기존 역할과 ADR-0055 인가 정책은 유지하며, 최소 권한과 거부 검증은 자동 fixture로 계속 수행한다.

---

### ADR 후보 045. HWP/HWPX 이중 원천 Hybrid Parser 구성

| 항목 | 내용 |
| --- | --- |
| 상태 | 결정 완료(ADR-0079 Accepted) |
| 관련 질문 | Q74 |
| 관련 ADR | ADR-0014, ADR-0065, ADR-0072, ADR-0073 |
| 승인 ADR | [ADR-0079](adr/ADR-0079-hwp-hwpx-hybrid-parser-composition.md) |
| 권고안 | `rhwp` 기준 텍스트와 `document-processor` 구조를 병합한 단일 `NormalizedDocument` 사용 |

`rhwp export-text`는 HWP/HWPX 원문을 안정적으로 보존하지만 현행 구현은 페이지 전체를 하나의 `BODY` 블록으로 만들어 문단·표·항목 구조를 후속 검토에 전달하지 못한다. `document-processor`는 구조 IR을 제공하지만 단독 텍스트 원천으로 교체하면 검증된 원문 완전성 기준이 흔들릴 수 있다.

결정 결과 두 엔진을 경쟁 후보로 선택하지 않고 `HwpHybridParserAdapter` 안에서 결합한다. `rhwp` 텍스트를 기준 원천, `document-processor`를 문단·표·스타일 구조 원천으로 사용하고 정렬되지 않은 기준 텍스트도 누락 없이 보존한다. 후속 파이프라인에는 `parserName=hwp-hybrid`인 단 하나의 병합 `NormalizedDocument`만 전달한다. 상세 기준은 ADR-0079를 따른다.

---

### ADR 후보 046. Private Parser/OCR와 외부 AI 활성화 경계

| 항목 | 내용 |
| --- | --- |
| 상태 | 결정 완료(ADR-0081 Accepted) |
| 관련 질문 | Q75 |
| 관련 ADR | ADR-0065, ADR-0079 |
| 승인 ADR | [ADR-0081](adr/ADR-0081-parser-service-and-external-ai-activation-separation.md) |
| 권고안 | private Parser/OCR와 external AI 설정을 분리 |

기존 `NH_EXTERNAL_AI_ENABLED` 하나가 OpenAI·embedding·RAG뿐 아니라 Compose 내부의 Parser/OCR adapter 조립까지 제어했다. 이 결합은 외부 LLM 호출을 허용하지 않는 개발·폐쇄망 환경에서 OCR·HWP/HWPX 정규화와 결정적 Rule 검토까지 막는다.

결정 결과 `NH_PARSER_SERVICES_ENABLED`를 별도로 두고 기본값은 true로 한다. private parser는 external AI가 비활성화되어도 `NormalizedDocument` v1을 만들며, OpenAI·embedding·RAG는 기존 `NH_EXTERNAL_AI_ENABLED` opt-in에서만 활성화한다. 상세 기준은 ADR-0081을 따른다.

---

# 18. 결론

본 프로젝트는 단순 웹 시스템이 아니라, 금융상품 광고심의 업무, AI 검토, RAG 검색, 문서 관리, PoC 평가가 결합된 복합 시스템이다.

따라서 다음 성격의 결정은 반드시 ADR로 남겨야 한다.

1. 개발 방식과 문서 관리 기준
2. 저장소 구조와 협업 방식
3. AI 활용 범위와 책임 기준
4. 백엔드·프론트엔드·DB·검색엔진 기술 선택
5. RAG 검색 및 AI 판단 구조
6. 고객사 자료 보안 정책
7. 테스트 및 CI/CD 운영 방식
8. PoC 평가 산식과 제외 기준

ADR은 단순히 “무엇을 선택했는지”를 기록하는 문서가 아니라, “왜 그렇게 선택했는지”와 “그 결정이 앞으로 어떤 영향을 주는지”를 남기는 문서이다.

향후 프로젝트 진행 중 중요한 기술·업무·보안·품질 관련 결정이 발생하면 본 목록에 ADR 후보를 추가하고, 결정 완료 후 ADR 문서로 승격하여 관리한다.
