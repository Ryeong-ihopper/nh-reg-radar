# ADR-0054: 리포트 스냅샷 및 HWPX-PDF 변환 방식

| 항목 | 내용 |
| --- | --- |
| 상태 | Accepted |
| 날짜 | 2026-07-11 |
| 관련 문서 | 기능명세서, API 명세서, DB 명세서, 화면설계서, 테스트케이스 |
| 관련 ADR | ADR-0017, ADR-0021, ADR-0022, ADR-0038, ADR-0040, ADR-0043, ADR-0051 |

## 배경

ADR-0038에서 초기 PoC 리포트 출력 형식은 HWPX 우선, PDF 지원으로 확정했다. 또한 HWPX와 PDF는 서로 다른 판단 결과를 만들면 안 되며, 같은 구조화 리포트 스냅샷에서 생성되어야 한다고 정했다.

남은 결정은 PDF를 어떻게 생성할지이다. HWPX와 PDF를 각각 별도 renderer로 만들면 온프렘 이전과 확장성은 좋지만 두 포맷 간 내용 정합성 검증이 복잡해진다. 반대로 HWPX를 기준 산출물로 만들고 PDF는 HWPX 변환본으로 만들면 고객사 보고서 원본과 PDF 공유본의 내용 정합성을 더 쉽게 보장할 수 있다.

## 결정

PoC에서는 HWPX를 기준 리포트 산출물로 생성하고, PDF는 생성된 HWPX를 변환해 만든다.

단, 리포트 내용은 파일 생성 전에 `report_snapshot` JSON으로 먼저 고정 저장한다. HWPX renderer와 PDF converter는 adapter 경계로 분리해, 온프렘 환경에서 변환 도구 사용이 어렵거나 품질 문제가 확인되면 동일 snapshot 기반 별도 PDF renderer로 전환할 수 있게 한다.

처리 순서는 다음과 같다.

```text
review result
  -> ReportSnapshotBuilder
  -> report_snapshot 저장 + snapshot_hash 생성
  -> HwpxReportRenderer
  -> HWPX 파일 저장
  -> HwpxToPdfConverter
  -> PDF 파일 저장
```

## 리포트 스냅샷

`report_snapshot`에는 다음 정보를 포함한다.

| 항목 | 설명 |
| --- | --- |
| `snapshotVersion` | 리포트 스냅샷 스키마 버전 |
| `reviewId` | 검토 ID |
| `standardVersionIds` | ADR-0040 기준 검토에 고정 적용한 기준자료 버전 ID |
| `summary` | 종합 위험도, 항목 수, 확인 필요 항목 수 |
| `reviewItems` | 항목별 판단, 위험도, 판단 사유, 원문, 수정 권고 |
| `evidences` | ADR-0043 기준 리포트 표시 근거 1~3개 |
| `annotations` | ADR-0051 기준 표시 모드, 위치 상태, 참조 정보 |
| `suggestions` | AI 추천 문구와 담당자 판단 |
| `opinionDraft` | 심의 의견 초안 또는 담당자 수정본 |
| `generatedBy`, `generatedAt` | 생성자와 생성 시각 |
| `rendererVersion` | HWPX renderer 버전 |
| `converterVersion` | PDF converter 버전 |

`snapshot_hash`는 canonical JSON 기준으로 계산한다. HWPX와 PDF는 같은 `snapshot_hash`를 참조해야 한다.

## 상태 처리

| 상황 | 처리 |
| --- | --- |
| `format=HWPX` | snapshot 저장 후 HWPX만 생성 |
| `format=PDF` | snapshot 저장 후 HWPX 생성, HWPX를 PDF로 변환 |
| HWPX 생성 실패 | `report_status=FAILED`, PDF 변환 수행 안 함 |
| PDF 변환 실패 | HWPX 파일은 보존하고 PDF report row는 `FAILED`로 기록 |
| 변환 도구 미지원 | `report_status=FAILED`, 실패 사유에 converter 미지원 기록 |

## 대안

| 대안 | 내용 | 채택 여부 |
| --- | --- | --- |
| A | HWPX만 생성하고 PDF는 추후 지원 | ADR-0038과 충돌해 기각 |
| B | HWPX 생성 후 PDF 변환 | 채택 |
| C | 동일 snapshot에서 HWPX/PDF renderer를 각각 실행 | 장기 전환 가능 대안으로 유지 |
| D | HTML 기준 PDF 생성, HWPX 별도 생성 | 내용 차이 위험으로 기각 |
| E | 리포트 파일 없이 화면 출력만 제공 | 고객사 산출물 요구와 맞지 않아 기각 |

## 영향

- `reports`는 `report_snapshot`, `snapshot_hash`, renderer/converter 버전, 변환 원본 report ID를 저장해야 한다.
- PDF 리포트는 독립 판단 결과가 아니라 HWPX 기준 산출물의 변환본으로 취급한다.
- HWPX 생성과 PDF 변환 실패는 분리해 기록한다.
- 리포트 정합성 검증은 같은 `snapshot_hash` 사용 여부와 필수 섹션 포함 여부를 확인한다.
- PDF 변환 도구는 직접 호출하지 않고 adapter로 감싼다.

## 후속 과제

- PoC 구현 시 사용 가능한 HWPX renderer와 HWPX-to-PDF converter 후보를 검증한다.
- 온프렘 환경에서 HWPX-to-PDF converter 설치, 라이선스, headless 실행 가능성을 확인한다.
- 변환 품질이 낮거나 도구 사용이 불가하면 동일 snapshot 기반 별도 PDF renderer 방식으로 후속 ADR을 검토한다.
