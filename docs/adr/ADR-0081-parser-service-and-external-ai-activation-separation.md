# ADR-0081: Private Parser/OCR와 외부 AI 활성화 분리 정책

| 항목 | 내용 |
| --- | --- |
| 상태 | Accepted |
| 날짜 | 2026-07-22 |
| 관련 문서 | 기능명세서, 테스트케이스, 프로젝트 규칙, 환경변수 예제 |
| 관련 ADR | ADR-0065, ADR-0079, ADR-0080 |

## 배경

기존 worker는 `NH_EXTERNAL_AI_ENABLED=false`일 때 빈 `ParserRouter`를 조립했다. 이 설정은 OpenAI·임베딩·RAG의 외부 호출을 막는 목적이지만, Compose 내부의 `opendataloader-pdf`, `paddleocr`, `rhwp`, `document-processor`까지 사용할 수 없게 했다. 따라서 외부 LLM을 비활성화한 상태에서 OCR·HWP/HWPX 정규화와 결정적 Rule 검토를 수행할 수 없었다.

## 결정

1. private Parser/OCR adapter는 `NH_PARSER_SERVICES_ENABLED`로 별도 제어하며 기본값은 `true`다.
2. `NH_EXTERNAL_AI_ENABLED`는 OpenAI Responses, embedding, hybrid 근거 검색과 문구 보강의 opt-in만 제어한다.
3. parser service가 활성화된 경우 external AI가 비활성화되어도 PDF·이미지·HWP/HWPX는 `NormalizedDocument v1`으로 정규화하고 결정적 Rule 결과까지 처리한다.
4. parser service를 명시적으로 비활성화한 상태에서 검토 요청을 받으면 기존처럼 `PARSER_ADAPTER_NOT_CONFIGURED`으로 fail-closed 처리한다.
5. 외부 AI가 필요한 검색·구조화 판단은 설정 누락 또는 backend 장애를 성공으로 가장하지 않고 기존 `SEARCH_UNAVAILABLE`/구성 오류 경계를 유지한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| `NH_EXTERNAL_AI_ENABLED`가 모든 adapter를 계속 제어 | 외부 AI와 private parser의 책임이 결합되어 제외 |
| Parser/OCR을 항상 강제하고 비활성화 설정을 제거 | 격리 테스트·명시적 fail-closed 운영 경계를 잃어 제외 |
| 별도 parser 서비스 활성화 설정을 도입 | 기능 경계와 폐쇄망 전환 경계를 명확히 하므로 채택 |

## 영향

- 개발·폐쇄망 환경은 외부 LLM 없이도 private Parser/OCR 서비스와 Rule 검토를 실행할 수 있다.
- 실제 RAG·구조화 LLM 결과 확인에는 기존대로 `NH_EXTERNAL_AI_ENABLED=true`, 유효한 provider·embedding 설정 및 적재된 기준자료가 필요하다.
- 운영 배포 환경 파일은 `NH_PARSER_SERVICES_ENABLED=true`를 명시한다.
- private parser service HTTP 실제 호출 검증은 Compose 기반 수동 E2E(`TC-LIVE-007`)로 유지하며, router 조립 단위 테스트와 구분한다.

## 검증

- external AI 비활성화 상태에서도 production runner가 `opendataloader-pdf`, `paddleocr`, `hwp-hybrid` adapter를 조립하는 단위 테스트를 둔다.
- parser service를 명시 비활성화하면 빈 router와 `PARSER_ADAPTER_NOT_CONFIGURED` fail-closed 경계를 유지하는 테스트를 둔다.
- 실제 private service HTTP·파일 유형별 처리는 배포된 Compose 환경에서 PDF·이미지·HWP/HWPX 승인 샘플로 검증한다.

## 후속 조치

- 개발 VM Compose 배포 후 `TC-LIVE-007`로 네 private parser service의 health와 실제 HTTP 처리 경로를 검증한다.
- 폐쇄망 전환 시 `NH_PARSER_SERVICES_ENABLED`는 유지하고, 외부 LLM/embedding endpoint만 내부 승인 endpoint로 전환한다.
- parser service를 비활성화해야 하는 격리 테스트·장애 조치에서는 검토 job이 fail-closed로 끝나는지 확인한다.

## 관련 문서

- `apps/worker/src/nh_ad_worker/main.py`
- `apps/worker/src/nh_ad_worker/settings.py`
- `apps/worker/tests/test_openai_provider.py`
- `docs/functional-specification.md`
- `docs/test-cases.md`
- `docs/project-rules.md`
