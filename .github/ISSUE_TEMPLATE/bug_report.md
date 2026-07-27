---
name: "결함 신고"
about: "동작 오류를 신고합니다. 제목은 프로젝트 규칙 §11.3의 `fix: <한글 요약>` 형식을 사용합니다."
title: "fix: "
labels: ""
assignees: ""
---

<!--
제목 규칙 (프로젝트 규칙 §11.3)
- 형식: <type>: <한글 요약>   예) fix: 검토 결과 화면 근거 하이라이트 누락
- type은 소문자, scope·대괄호 접두어([BUG] 등) 사용 금지
- 요약은 한글, `한다`·`됩니다` 같은 종결 어미 없이 증상·대상을 간결히
- 운영 장애는 hotfix, 그 밖의 결함은 fix
- 이슈 하나에는 하나의 문제만
-->

## 증상

<!-- 무엇이 잘못 동작하는지 한두 문장으로 -->

## 재현 절차

1.
2.
3.

## 기대 동작

## 실제 동작

<!-- 오류 메시지·응답 코드·사유 코드가 있으면 함께. 자격증명·고객사 자료·개인정보는 남기지 않습니다 -->

## 확인 환경

- 위치: 로컬 / 공용 개발 VM
- 대상 commit:
- 관련 설정: `NH_PARSER_SERVICES_ENABLED`, `NH_EXTERNAL_AI_ENABLED` 등 해당 시

## 관련 명세·ADR

<!-- 착수 전 확인 대상. 예) docs/functional-specification.md FR-0xx, docs/adr/ADR-00xx-... -->

## 참고

<!-- 로그 위치, 스크린샷, 관련 이슈·PR -->

---

- [ ] Notion 칸반을 운영하는 경우 해당 카드에 이 이슈 링크를 남김
- [ ] 착수 시 브랜치를 `fix/<issue-number>-<short-description>`(운영 긴급 수정은 `hotfix/*`)로 생성하고 PR 본문에 `#<issue-number>` 참조
