# nh-parser-fin 운영 연결 감사 — 2026-09-22

## 문서 현행 정보

| 항목 | 값 |
| --- | --- |
| 현행 버전 | v1.0 |
| 기준일 | 2026-09-22 |
| 상태 | 계약·패키징 검증 완료, spark-1118 실광고 E2E 대기 |

## 변경 이력

| 버전 | 기준일 | 변경 내용 |
| --- | --- | --- |
| v1.0 | 2026-09-22 | P1 v3/P3 v6, bbox 출처, Python 3.13 격리, 실기 전환 게이트를 기록 |

검토 대상은 `cg-wnsdud/nh-parser-fin` 커밋 `a322ab5d29f8b9fcd101f31642d812475423a417`이다.

## 결론

새 스키마를 그대로 기존 운영 runner에 넣을 수는 없다. 최신 출력은 P1
`nh-ad-parse-evidence-v3`, P3 `nh-ad-region-review-input-v6`이며 기존 외부 계약 v1/v1과
필드와 출력 경로가 다르다. 버전별 어댑터와 `nh_parser_fin` runner를 추가했으며 계약 테스트는
통과했다. 실광고 원격 OCR/VLM 스모크와 운영 컨테이너 배포 전까지는 기본 runner를 바꾸지 않는다.

## bbox 계약

- `bbox=[x1,y1,x2,y2]`는 렌더된 원본 페이지의 픽셀 좌표다.
- PaddleX layout, OCR line, PDF digital line만 좌표 출처가 될 수 있다.
- P3 `selected_text`와 의미 라벨은 VLM이 보완할 수 있지만 bbox를 만들지 않는다.
- P3가 line_ref를 생략하므로 어댑터는 같은 page/region의 P1 line_ref를 복원한다.
- selected_text가 P1 line 문자열과 다르면 `region_level_selected_text`로 남기며 line-exact
  인용으로 승격하지 않는다.
- P3 압축 과정에서 빠질 수 있는 P1 unassigned line과 페이지별 recovery candidate도 운영
  통합 입력에 보존한다.

## 배포 경계

nh-parser-fin은 Python 3.13 이상을 요구한다. 애플리케이션/RAG의 Python 3.11 제약은 그대로
유지하고 `infra/operational/Dockerfile`의 별도 `/opt/python313` 런타임에서 파서를 실행한다.
이미지/PDF는 공개 의존성만으로 실행 가능하다. HWP/HWPX는 사내 `document-processor`가 추가로
필요하며 패키징 단계에서 그 소스가 없으면 실패시킨다.

## 남은 실기 게이트

1. spark-1118 SSH 인증 복구
2. 승인된 광고 한 건을 PaddleX 8081·Gemma 8102로 실행
3. P1/P3 doc/page/region 결합, canvas와 bbox 범위, unassigned/recovery 보존 확인
4. 새 운영 이미지 빌드 후 기존 상태의 사본과 파일 해시·광고/검토 건수 대조
5. 새 주소에서 등록→파싱→검색→판정→bbox 표시 한 건 완주

이 다섯 단계 전에는 `temp/operational-config.local.json`의 fc87 설정을 변경하지 않는다.
