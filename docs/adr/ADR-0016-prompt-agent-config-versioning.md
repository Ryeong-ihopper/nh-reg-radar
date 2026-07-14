# ADR-0016: 프롬프트 및 Agent 설정 버전관리

## 상태

Accepted

## 배경

LLM Agent는 검토 항목 분류, 판단 사유 설명, 보완 문구 추천, 심의 의견 초안 생성 등 재현성과 추적성이 필요한 작업을 수행한다. 프롬프트와 Agent 설정이 코드 내부에 흩어지거나 개인별 프롬프트로 운영되면 동일 입력에 대한 결과 차이를 추적하기 어렵고, 변경 이력도 남기기 어렵다.

PoC 단계에서는 빠른 변경과 리뷰 가능성이 중요하므로 프롬프트와 Agent 설정을 Git에서 관리한다. 다만 본사업 전환 시 DB 또는 Prompt Registry로 이동할 수 있도록 구조화된 설정 파일 형식을 사용한다.

## 결정

PoC 단계의 프롬프트와 Agent 설정은 Git에서 YAML 파일로 관리한다.

기본 원칙은 다음과 같다.

| 항목 | 결정 |
| --- | --- |
| 저장 방식 | Git 관리 YAML 파일 |
| 기본 경로 | `configs/agents/*.yaml`, `configs/prompts/*.yaml` |
| 예시 문서 | `docs/ai/prompt-agent-config.example.yaml` |
| 변경 절차 | PR 리뷰를 통해 변경 |
| 런타임 적용 | worker/API 서버가 시작 시 또는 job 실행 시 YAML을 로드 |
| 버전 식별 | `config_version`, `prompt_version`, Git commit hash를 함께 기록 |
| 실험 관리 | PoC는 YAML variant로 관리, 본사업은 DB/Registry 검토 |

프롬프트 본문, 모델 파라미터, 출력 스키마, 입력 변수, 안전 규칙, fallback 정책은 코드에 하드코딩하지 않고 YAML 설정에서 정의한다. 코드에는 YAML을 로드하고 검증하는 로직과 Agent 실행 인터페이스만 둔다.

## YAML 스키마 원칙

YAML 설정은 다음 정보를 포함해야 한다.

| 필드 | 설명 |
| --- | --- |
| `agent_id` | Agent 식별자 |
| `agent_type` | rule, rag, llm, orchestrator 등 |
| `config_version` | Agent 설정 버전 |
| `prompt_version` | 프롬프트 본문 버전 |
| `model` | 모델 제공자, 모델명, temperature 등 |
| `inputs` | 필수 입력 변수와 설명 |
| `output_schema` | 기대 출력 JSON 구조 |
| `system_prompt` | 시스템 프롬프트 또는 역할 지시 |
| `task_prompt` | 작업별 프롬프트 템플릿 |
| `safety` | 금지 사항, 보수 처리 기준, 자료 반출 제한 |
| `fallback` | 실패, 근거 부족, 파싱 실패 시 처리 |
| `evaluation` | 샘플셋, golden fixture, 검증 기준 |

민감정보, API Key, 고객사 비밀값은 YAML에 저장하지 않는다. 환경별 secret은 환경변수 또는 secret manager를 사용한다.

## 예시

예시 설정은 `docs/ai/prompt-agent-config.example.yaml`에 둔다.

```yaml
agent_id: review-explanation-agent
agent_type: llm
config_version: "0.1.0"
prompt_version: "2026-07-06.review-explanation.v1"

model:
  provider: openai
  name: gpt-5
  temperature: 0.2
  max_output_tokens: 1200

inputs:
  - name: review_item
    required: true
  - name: evidences
    required: true

output_schema:
  type: object
  required:
    - decision
    - reason
    - evidence_ids
  properties:
    decision:
      enum: [APPROPRIATE, NEEDS_REVISION, NEEDS_CONFIRMATION]
    reason:
      type: string
    evidence_ids:
      type: array

system_prompt: |
  You support financial advertisement compliance review.
  Your output is advisory. The final decision is made by a human reviewer.

task_prompt: |
  Review the item using only the provided evidences.
  If evidence is insufficient, return NEEDS_CONFIRMATION.
```

## 런타임 적용 기준

| 시점 | 처리 |
| --- | --- |
| 애플리케이션 시작 | YAML 스키마 검증, 필수 필드 누락 시 실패 |
| Job 실행 | 사용한 `agent_id`, `config_version`, `prompt_version`, Git commit hash 저장 |
| LLM 호출 | YAML의 모델 파라미터와 프롬프트 템플릿 사용 |
| 출력 수신 | YAML의 `output_schema` 기준으로 구조 검증 |
| 검증 실패 | fallback 정책에 따라 `NEEDS_CONFIRMATION` 또는 재시도 |

운영 중 설정 변경은 코드 배포와 동일하게 PR, 리뷰, 배포 절차를 따른다. 긴급 수정이 필요하면 변경 사유와 영향 범위를 PR 또는 ADR 후속 기록에 남긴다.

## 대안

| 대안 | 판단 |
| --- | --- |
| 코드 내부 하드코딩 | 구현은 빠르지만 변경 이력, 리뷰, 실험 비교가 어렵다. |
| DB 관리 | 운영 중 변경은 편하지만 PoC 단계에서는 관리 UI와 권한 모델이 필요하다. |
| Prompt Registry | 실험 관리에는 좋지만 초기 도입 비용과 도구 종속성이 있다. |
| Git YAML 관리 | 리뷰, diff, rollback, 배포 추적이 쉬워 PoC에 적합하다. |

## 결정 근거

- Git 문서를 개발자 Source of Truth로 쓰는 기존 결정과 정합하다.
- YAML은 사람이 읽고 리뷰하기 쉬우며, 코드에서 구조화해 검증하기 쉽다.
- 프롬프트와 Agent 설정을 코드와 분리하면 모델, 출력 스키마, fallback 정책을 교체하기 쉽다.
- `prompt_version`과 Git commit hash를 저장하면 AI 판단 결과를 재현하고 변경 영향을 추적할 수 있다.
- 본사업에서 DB/Registry로 이동하더라도 YAML 스키마를 기준 계약으로 유지할 수 있다.

## 영향

- Agent 실행 로직은 설정 파일 로더와 스키마 검증을 포함해야 한다.
- Review 결과에는 사용한 Agent 설정 버전과 프롬프트 버전을 저장해야 한다.
- 테스트는 YAML fixture를 로드해 필수 필드, 출력 스키마, fallback 정책을 검증해야 한다.
- 프롬프트 변경은 코드 변경과 동일하게 리뷰 대상이 된다.
- 외부 AI 입력 정책과 충돌하지 않도록 safety 설정에 자료 입력 제한을 명시해야 한다.

## 후속 조치

- `configs/agents/`, `configs/prompts/` 디렉터리 구조를 구현 단계에서 생성한다.
- YAML 스키마 검증 방식을 Pydantic 또는 JSON Schema 기반으로 구현한다.
- DB 명세에 `agent_id`, `config_version`, `prompt_version`, `model_name`, `prompt_hash` 저장 항목을 반영한다.
- 테스트케이스에 프롬프트 설정 누락, 출력 스키마 불일치, fallback 동작 검증을 추가한다.
- 본사업 전환 시 Prompt Registry 또는 DB 관리 필요성을 재평가한다.

## 관련 문서

- `docs/project-rules.md`
- `docs/functional-specification.md`
- `docs/database-specification.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0002-customer-sample-data-ai-input-policy.md`
- `docs/adr/ADR-0013-rule-rag-llm-responsibility.md`
