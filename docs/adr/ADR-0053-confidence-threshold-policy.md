# ADR-0053: OCR/Parser/Annotation 신뢰도 임계값 및 확인 필요 처리 기준

| 항목 | 내용 |
| --- | --- |
| 상태 | Accepted |
| 날짜 | 2026-07-11 |
| 관련 문서 | 기능명세서, API 명세서, DB 명세서, 테스트케이스, PoC 평가 제외 기준표, 위험도 산정 기준표 |
| 관련 ADR | ADR-0014, ADR-0015, ADR-0018, ADR-0024, ADR-0043, ADR-0051, ADR-0052 |

## 배경

기능명세와 ADR에는 OCR/Parser 신뢰도 부족, Annotation 위치 신뢰도 부족, 구조 인식 신뢰도 부족 시 “확인 필요”로 처리한다는 원칙이 이미 있다. 그러나 정상, 확인 필요, 판독 불가 또는 위치 없음으로 나누는 임계값이 없으면 화면 표시, 위험도 산정, KPI 평가 제외, 테스트 fixture가 서로 다르게 해석될 수 있다.

## 결정

OCR, parser 구조 인식, Annotation 위치 신뢰도는 용도별 임계값을 분리한다. 임계값은 YAML 설정으로 관리하고, PoC 기본값은 다음으로 시작한다.

| 대상 | 정상 | 확인 필요 | 실패/위치 없음 |
| --- | --- | --- | --- |
| OCR text confidence | `>= 0.80` | `0.50 <= score < 0.80` | `< 0.50` |
| Parser structure confidence | `>= 0.75` | `0.50 <= score < 0.75` | `< 0.50` |
| Annotation location confidence | `>= 0.80` | `0.50 <= score < 0.80` | `< 0.50` |
| RAG relevance score | ADR-0043 기준 | ADR-0043 기준 확인 필요 | 근거 없음 처리 |

상태 매핑은 다음 기준을 따른다.

| 입력 | 정상 | 확인 필요 | 실패/위치 없음 |
| --- | --- | --- | --- |
| OCR text | `READABLE` | `LOW_CONFIDENCE` | `UNREADABLE` |
| Parser structure | `STRUCTURED` | `PARTIALLY_STRUCTURED` | `UNSTRUCTURED` |
| Annotation location | `LOCATED` | `LOW_CONFIDENCE` 또는 `PARTIALLY_LOCATED` | `NOT_LOCATED` |

OCR/Parser 실패가 검토 판단 자체를 불가능하게 만들면 `OCR_UNREADABLE` 평가 제외 후보로 기록한다. 단순히 Annotation 위치만 낮은 경우는 KPI 제외가 아니라 `LOW_CONFIDENCE` 또는 `NOT_LOCATED` 표시로 처리한다.

## 설정 관리

임계값은 코드 상수로 고정하지 않고 설정 파일로 관리한다. 설정에는 버전을 둔다.

```yaml
confidence_policy_version: "confidence-thresholds-v1"
thresholds:
  ocr_text:
    readable_min: 0.80
    review_required_min: 0.50
  parser_structure:
    structured_min: 0.75
    review_required_min: 0.50
  annotation_location:
    located_min: 0.80
    review_required_min: 0.50
```

설정값을 변경하면 변경 사유, 적용일, 영향받는 fixture 또는 평가 결과를 함께 기록한다.

## 대안

| 대안 | 내용 | 채택 여부 |
| --- | --- | --- |
| A | 임계값 없이 parser/OCR 결과를 그대로 표시 | 확인 필요 기준이 주관적이라 기각 |
| B | 모든 신뢰도에 단일 임계값 사용 | 단순하지만 OCR, 구조 인식, 위치 매칭의 차이를 반영하기 어려워 기각 |
| C | 용도별 임계값 분리 | 채택 |
| D | 샘플 데이터 평가 전까지 모두 확인 필요로 처리 | 자동화 효과가 낮아 기각 |
| E | LLM이 신뢰도 상태까지 판단 | 재현성과 테스트 안정성이 낮아 기각 |

## 영향

- `ocr_text_blocks`, `layout_blocks`, `annotations`는 신뢰도 점수와 상태를 함께 저장한다.
- 위험도 산정에서 OCR/Parser 확인 필요는 `CHECK_REQUIRED` 후보로 처리한다.
- 평가 제외는 OCR/Parser가 판정 대상 문구를 식별하지 못한 경우에만 후보로 올린다.
- 테스트 fixture는 경계값 `0.80`, `0.75`, `0.50` 전후 케이스를 포함해야 한다.

## 후속 과제

- PoC 샘플 평가 후 임계값 조정 필요 여부를 검토한다.
- 실제 OCR/parser 후보별 confidence score 분포가 다르면 adapter별 score calibration을 별도 ADR로 검토한다.
- Parser/OCR 품질 미달 시 보조 엔진 재처리 여부와 최종 산출물 선택 기준은 ADR-0073을 따른다.
