## 변경 요약

-

## API 계약 변경 확인

API 변경이 있는 경우 아래 항목을 확인한다.

- [ ] `openapi/openapi.yaml`을 갱신했다.
- [ ] `docs/api-specification.md`의 설명과 예시를 갱신했다.
- [ ] `docs/screen-api-mapping.md`의 화면 영향 범위를 확인했다.
- [ ] `docs/test-cases.md`의 계약/권한/예외 테스트를 갱신했다.
- [ ] OpenAPI lint와 API contract test를 확인했다.
- [ ] FastAPI generated `/openapi.json`과 원천 OpenAPI 차이를 확인했다. 구현 전이면 해당 없음으로 표시한다.

API 변경이 없으면 다음에 사유를 적는다.

- API 변경 없음 사유:

## 문서 정합성

문서 변경이 있는 경우 아래 항목을 확인한다.

- [ ] `scripts/check-doc-consistency.sh`를 실행했다.
- [ ] `python3 -m scripts.doc_guard validate --scope working`을 실행했다.
- [ ] `python3 -m scripts.doc_guard impact --scope working` 결과의 동기화 대상을 확인했다.
- [ ] 관련 Source of Truth 문서가 함께 갱신되었다.
- [ ] ADR 변경 시 `docs/adr/README.md`, `docs/adr/decision-questions.md`, `docs/adr-candidates.md`를 확인했다.

## AI 산출물 검증

AI 도움을 받은 변경이 있는 경우 아래 항목을 확인한다. AI 도움을 받지 않았으면 해당 없음으로 표시한다.

- [ ] 변경 내용을 담당 개발자가 이해하고 설명할 수 있다.
- [ ] lint, type check, 테스트 또는 수동 검증을 수행했다.
- [ ] 보안/권한/감사 로그/DB migration/KPI 산식/위험도 산정/prompt config 변경은 담당 개발자가 별도 확인했다.
- [ ] secret, token, 개인정보, 승인되지 않은 고객사 원문 자료가 포함되지 않았다.

## 검증

-
