# ADR-0068: 위험도 산정 근거 영속화 및 API 응답 정책

## 상태

Accepted

## 배경

ADR-0018은 위험도 산정을 Rule 우선, RAG/LLM 보조, 불확실성은 `CHECK_REQUIRED` 원칙으로 결정했다. 또한 `docs/risk-assessment-criteria.md`를 구현과 테스트의 기준으로 사용하기로 했다.

하지만 `review_items`와 API 응답이 `risk_level`과 자유문 `reason`만 제공하면 다음 문제가 생긴다.

- 담당자가 `HIGH`, `MEDIUM`, `LOW`, `CHECK_REQUIRED`가 부여된 구조적 이유를 비교하기 어렵다.
- 위험도 산정 기준이 바뀌었을 때 어떤 정책 버전으로 판단했는지 추적하기 어렵다.
- 테스트 fixture가 자유문 reason에 과도하게 의존할 수 있다.
- 리포트와 화면에서 위험도 사유를 일관된 코드로 표시하거나 집계하기 어렵다.

## 결정

위험도 산정 근거는 **`review_items`에 명시 필드와 JSON 상세를 함께 저장하고, API에도 구조화 응답으로 제공**한다.

| 항목 | 결정 |
| --- | --- |
| 핵심 필드 | `risk_level`, `risk_policy_version`, `risk_reason_codes`, `risk_score_detail` |
| 자유문 설명 | 기존 `reason` 유지. 사용자 표시용 문장으로 사용 |
| 구조화 사유 | `risk_reason_codes`에 위험도 산정 사유 코드를 배열로 저장 |
| 상세 입력 | `risk_score_detail`에 rule, RAG, LLM, confidence 판단 근거를 JSON으로 저장 |
| API 응답 | 목록은 핵심 요약, 단건은 `riskRationale` object로 상세 반환 |
| 정렬/필터 | `risk_level`은 기존 인덱스 기준 유지. 사유 코드 필터는 PoC 초기 필수 범위에서 제외 |

## DB 필드 기준

`review_items`에 다음 필드를 추가한다.

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `risk_policy_version` | `varchar(100)` | 위험도 산정 기준표 또는 정책 버전. 예: `risk-policy-v1` |
| `risk_reason_codes` | `jsonb` | 위험도 산정 사유 코드 배열 |
| `risk_score_detail` | `jsonb` | rule/RAG/LLM/confidence 입력과 점수 상세 |

`risk_reason_codes`는 배열 형태를 사용한다.

```json
[
  "PROHIBITED_EXPRESSION",
  "HIGH_RAG_RELEVANCE",
  "LLM_MISLEADING_CONTEXT"
]
```

`risk_score_detail`은 다음 구조를 기준으로 한다.

```json
{
  "rule": {
    "matched": true,
    "ruleIds": ["RULE-MISLEADING-001"],
    "severity": "HIGH"
  },
  "rag": {
    "topRelevanceScore": 0.91,
    "evidenceCount": 2,
    "evidenceSufficient": true
  },
  "llm": {
    "decision": "RISKY",
    "confidence": 0.86
  },
  "parser": {
    "confidenceStatus": "READABLE"
  },
  "final": {
    "riskLevel": "HIGH",
    "decisionRule": "RULE_HIGH_OVERRIDES_LLM"
  }
}
```

## 사유 코드 기준

초기 PoC에서는 다음 코드군을 사용한다. 상세 코드는 구현 중 확장할 수 있지만, 코드 의미를 변경할 때는 기준표와 테스트 fixture를 함께 갱신한다.

| 코드 | 의미 |
| --- | --- |
| `RULE_EXPLICIT_VIOLATION` | Rule이 명시 위반으로 판정 |
| `REQUIRED_PHRASE_MISSING` | 필수 고지 또는 필수 문구 누락 |
| `INTEREST_RATE_MISMATCH` | 금리/수익률 핵심 정보 불일치 |
| `REVIEW_NUMBER_INVALID` | 심의필 번호 누락 또는 오류 |
| `PROHIBITED_EXPRESSION` | 금지 또는 주의 표현 탐지 |
| `HIGH_RAG_RELEVANCE` | 관련도 높은 기준자료 근거 존재 |
| `LOW_RAG_RELEVANCE` | 기준자료 근거 관련도 부족 |
| `LLM_MISLEADING_CONTEXT` | LLM 문맥 판단상 오인 가능성 |
| `RULE_LLM_CONFLICT` | Rule과 LLM 판단 충돌 |
| `PARSER_LOW_CONFIDENCE` | OCR/Parser 신뢰도 부족 |
| `REFERENCE_MISSING` | 기준자료 미제공 또는 근거 부족 |
| `PRODUCT_CONDITION_UNCLEAR` | 상품조건 불명확 |

## API 응답 기준

검토 항목 목록 응답에는 화면 표시와 정렬에 필요한 요약을 포함한다.

```json
{
  "reviewItemId": "ITEM-0001",
  "riskLevel": "HIGH",
  "riskPolicyVersion": "risk-policy-v1",
  "riskReasonCodes": [
    "PROHIBITED_EXPRESSION",
    "HIGH_RAG_RELEVANCE",
    "LLM_MISLEADING_CONTEXT"
  ],
  "reason": "객관적 근거 없이 최고 수준이라는 표현을 사용하여 소비자 오인 가능성이 있습니다."
}
```

검토 항목 단건 응답에는 `riskRationale` object를 포함한다.

```json
{
  "riskRationale": {
    "riskLevel": "HIGH",
    "policyVersion": "risk-policy-v1",
    "reasonCodes": [
      "PROHIBITED_EXPRESSION",
      "HIGH_RAG_RELEVANCE",
      "LLM_MISLEADING_CONTEXT"
    ],
    "scoreDetail": {
      "rule": {
        "matched": true,
        "ruleIds": ["RULE-MISLEADING-001"],
        "severity": "HIGH"
      },
      "rag": {
        "topRelevanceScore": 0.91,
        "evidenceCount": 2,
        "evidenceSufficient": true
      },
      "llm": {
        "decision": "RISKY",
        "confidence": 0.86
      },
      "parser": {
        "confidenceStatus": "READABLE"
      },
      "final": {
        "riskLevel": "HIGH",
        "decisionRule": "RULE_HIGH_OVERRIDES_LLM"
      }
    }
  }
}
```

`reason`은 담당자에게 보여줄 자연어 설명이고, `riskRationale`은 구현, 테스트, 리포트, 디버깅에 사용하는 구조화 근거다.

## 대안

| 대안 | 판단 |
| --- | --- |
| A. 현재처럼 `risk_level`, `reason`만 저장 | 단순하지만 설명 가능성, 테스트 안정성, 기준 변경 추적이 약해 기각 |
| B. `review_items`에 정책 버전과 주요 산정 근거 필드를 명시 컬럼/JSON 조합으로 저장 | PoC 구현 부담과 설명 가능성의 균형이 좋아 채택 |
| C. 모든 산정 과정을 `result_json`에만 저장 | 유연하지만 API 계약과 필수 필드 검증이 약해 기각 |
| D. 별도 `risk_decisions` 테이블로 완전 분리 | 이력 확장성은 높지만 PoC 단계에는 과해 기각 |

## 결정 근거

- 위험도는 사용자 화면, 리포트, PoC 평가의 핵심 판단 기준이므로 자유문만으로 남기면 재현성이 약하다.
- 정책 버전이 있어야 기준표 변경 전후 결과를 비교할 수 있다.
- 사유 코드는 테스트 fixture와 리포트 집계에 유리하다.
- 모든 상세를 컬럼으로 분해하면 PoC 단계에서 과하므로, 핵심 필드와 JSON 상세를 조합한다.
- `result_json`은 엔진별 원시 상세를 담을 수 있지만, 위험도 산정 계약의 원천으로 삼지 않는다.

## 영향

- DB 명세의 `review_items`에 `risk_policy_version`, `risk_reason_codes`, `risk_score_detail`을 추가한다.
- API 명세의 검토 요약, 목록, 단건 응답에 위험도 산정 근거 필드를 반영한다.
- 테스트케이스에 위험도 정책 버전과 사유 코드 저장/응답 검증을 추가한다.
- 리포트는 자연어 `reason`과 구조화 사유 코드를 함께 사용할 수 있다.
- 위험도 기준표 변경 시 `risk_policy_version`을 갱신하고 fixture 기대값을 함께 조정한다.

## 후속 조치

- `openapi/openapi.yaml`의 `ReviewItem`과 `RiskRationale` schema에 필드를 추가한다.
- 위험도 산정 모듈은 `RiskRationale` value object 또는 schema를 반환하도록 구현한다.
- `risk_reason_codes` enum 후보를 코드 상수와 문서 기준표에 연결한다.
- PoC 평가 리포트에서 `CHECK_REQUIRED`와 주요 사유 코드별 빈도를 집계할지 구현 단계에서 결정한다.

## 관련 문서

- `docs/risk-assessment-criteria.md`
- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/functional-specification.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0018-risk-level-decision-policy.md`
- `docs/adr/ADR-0053-confidence-threshold-policy.md`
