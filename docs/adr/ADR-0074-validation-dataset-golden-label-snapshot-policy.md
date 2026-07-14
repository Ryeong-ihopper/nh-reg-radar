# ADR-0074: PoC 검증 데이터셋, 정답지 및 평가 Snapshot 관리 정책

## 상태

Accepted

## 배경

PoC 성능 평가는 검증 데이터셋, 담당자 판단 정답지, AI 검토 결과, 기준자료 버전, 모델/프롬프트/Parser/OCR 설정을 함께 사용한다. 이 중 정답지나 AI 검토 결과가 평가 실행 후 수정되면 같은 `evaluationId`의 점수가 달라질 수 있어 재현성과 고객사 설명 가능성이 약해진다.

반대로 모든 정답지를 Git fixture나 Excel 파일로만 관리하면 운영 화면에서 담당자가 수정하기 어렵고, 평가 제외 사유 확정자와 변경 이력 추적도 분산된다. PoC에서는 개발자와 담당자가 함께 검증 데이터를 다루므로 공식 원천과 평가 실행 시점의 고정본을 분리해야 한다.

## 결정

PoC 검증 데이터셋과 정답지의 공식 원천은 PostgreSQL의 `validation_datasets`, `validation_judgments`로 관리하고, 성능 평가 실행 시점에는 평가 입력과 AI 결과를 `evaluations`에 snapshot으로 고정한다.

| 항목 | 결정 |
| --- | --- |
| 공식 원천 | DB의 `validation_datasets`, `validation_judgments` |
| 개발/테스트 fixture | Git으로 관리하되 dev/test seed와 회귀 테스트용으로만 사용 |
| Excel/Notion | import/export 또는 검토 보조 자료로만 사용 |
| 평가 실행 | 실행 시점의 데이터셋, 판단, 제외 사유, AI 결과, 버전 정보를 snapshot으로 저장 |
| 평가 결과 | `evaluationId` 단위로 불변 처리. 정답지 수정 후 재평가가 필요하면 새 평가를 생성 |
| 구현 방식 | PoC에서는 `evaluations`의 JSONB snapshot 컬럼으로 관리 |
| 무결성 | snapshot hash를 저장해 재현성과 변경 여부 확인에 사용 |

## Snapshot 범위

평가 실행 시 다음 정보를 고정한다.

| Snapshot | 포함 정보 |
| --- | --- |
| 데이터셋 snapshot | datasetId, datasetVersion, 광고물/샘플 파일 ID, 상품군, 광고유형, 상품조건 파일 ID, `labelJson` |
| 담당자 판단 snapshot | judgmentId, judgmentVersion, targetText, reviewType, expectedStatus, riskLevel, comment |
| 제외 사유 snapshot | dataset/judgment 단위 excluded 여부, excludeReasonCode, excludeReason, excludedBy, excludedAt |
| AI 결과 snapshot | selected reviewId, review item 결과, 위험도, 근거, 추천 문구, 부분 정답 계산에 필요한 값 |
| 버전 snapshot | 기준자료 versionId, 모델/프롬프트 버전, Parser/OCR 엔진과 adapter 버전, RAG/Search 설정 버전 |
| 평가 정책 snapshot | KPI 코드, 목표 점수, 제외 적용 여부, review selection policy |

## 처리 규칙

1. `validation_datasets`와 `validation_judgments`는 담당자 검증 결과의 source of truth로 본다.
2. 정답지, 담당자 판단, 평가 제외 사유가 수정되면 dataset 또는 judgment version을 증가시킨다.
3. 평가 실행 시 현재 DB 값을 읽어 snapshot을 생성하고, 이후 같은 `evaluationId`는 현재 DB 값이 아니라 snapshot 기준으로 조회한다.
4. 정답지 수정, 기준자료 변경, AI 재분석 후 점수를 다시 산출하려면 새 evaluation을 생성한다.
5. `snapshotHash`는 snapshot JSON의 canonical serialization 기준으로 생성한다.
6. Git fixture는 초기 개발자 온보딩, 테스트 자동화, 회귀 테스트에 사용하며 공식 PoC 점수 산출 원천으로 사용하지 않는다.
7. 고객사 전달용 Excel은 DB 원천의 export 산출물로 보며, Excel 수정본을 반영할 때는 import 절차를 통해 DB에 반영한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| A. Git fixture를 정답지 source of truth로 사용 | 개발 재현성은 좋지만 고객사 담당자 수정, 제외 확정, 감사 추적이 어렵다 |
| B. DB만 source of truth로 두고 평가 시 snapshot을 만들지 않음 | 구현은 단순하지만 정답지 수정 후 과거 평가 결과가 흔들린다 |
| C. DB를 source of truth로 두고 평가 실행 snapshot을 고정 | 운영 편의성과 재현성 균형이 좋아 채택 |
| D. 별도 정규화 snapshot 테이블을 상세히 설계 | 장기 확장성은 좋지만 PoC 단계에서는 구현 비용이 크다 |
| E. Excel/Notion을 공식 정답지로 사용 | 협업은 쉽지만 권한, 이력, API 연계, 자동 평가와 정합성이 낮다 |

## 결정 근거

- PoC 평가 결과는 고객사 설명과 반복 비교가 필요하므로 같은 `evaluationId`의 점수가 나중에 바뀌면 안 된다.
- 정답지 수정과 재평가는 정상적인 업무 흐름이므로 과거 평가 보존과 신규 평가 생성을 분리해야 한다.
- DB 원천은 API, 화면, 감사 로그, 권한 정책과 자연스럽게 연결된다.
- JSONB snapshot은 PoC 범위에서 구현이 단순하고, 평가 입력 전체를 빠르게 보존할 수 있다.
- 정규화 snapshot 테이블은 데이터 규모와 운영 요구가 커지는 본사업 전환 시 재검토하는 편이 적절하다.

## 영향

- `validation_datasets`, `validation_judgments`에 version/update 정보를 추가한다.
- `evaluations`에 dataset/judgment/exclusion/AI/version/policy snapshot과 hash를 저장한다.
- 평가 조회 API는 현재 정답지가 아니라 실행 snapshot 기준 결과를 반환한다.
- 테스트케이스에 정답지 수정 후 기존 평가 불변, 신규 평가 생성, snapshot hash 검증을 추가한다.

## 후속 조치

- Snapshot JSON canonical serialization 규칙을 구현 단계에서 유틸리티로 고정한다.
- 본사업 전환 시 snapshot 규모, 조회 성능, 보관 기간에 따라 정규화 snapshot 테이블 분리를 재검토한다.
- 고객사 Excel import/export가 필요하면 DB 원천 반영 절차와 충돌 처리 기준을 별도 ADR로 검토한다.

## 관련 문서

- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/functional-specification.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0023-poc-kpi-formulas.md`
- `docs/adr/ADR-0024-evaluation-exclusion-policy.md`
- `docs/adr/ADR-0041-alembic-migration-and-seed-policy.md`
- `docs/adr/ADR-0044-ai-mock-fixture-test-policy.md`
