# NH 광고심의 평가셋 현황

## 2026-09-21 구조화 프롬프트 A0~A3 평가 준비

271개 계획·376개 원자 의무에 대해 A0 기존 프롬프트, A1 역할 분리 기본 프롬프트, A2 규칙군 프롬프트, A3 규칙군+복잡도 배치를 같은 봉인 입력으로 비교하는 평가기를 추가했다. 지표는 적용성 macro F1, 판정 macro F1, 위반 recall, 판단불가율, 미지원 인용률, 규칙군별 결과다. 비교기는 모든 광고·항목 키가 일치하지 않으면 실패한다.

새 모델 출력은 아직 없고 독립 holdout은0건이다. ISA6건66쌍은 이미 개발에 사용된 dev/regression이므로 A0~A3 회귀 비교에만 쓸 수 있다. 따라서 현재 주장 가능한 것은 구조 계약과 평가기 준비까지이며, 정확도 개선이나 일반화 성능은 주장할 수 없다. holdout 비교 함수는 라벨0건 상태에서 실행을 거부한다.

## 2026-09-18 실행 범위·채점 범위 진단

저장된 ISA 6회차의 화면 검토 범위는 377행이다. `INTERNAL_TEMPLATE` 66행은 모두 기존 dev/regression gold와 결합됐고, `REGULATION_V2` 311행은 결합 가능한 gold가 없어 전부 미채점이다. 따라서 이 결과에서 계산한 정확도는 템플릿 회귀 범위에만 유효하며 전체 운영 결과 정확도로 보고하지 않는다.

기존 모델 판정은 적용 제외까지 포함해 618쌍이다. 현행 정식 실행 정책을 저장 결과에 투영하면 이 ISA 6건은 `TEMPLATE_PRIMARY` 66쌍만 정식 판정하며 화면 표면도 66행이다. `MAPPED_V2` 114쌍은 템플릿 보강·평가 후보로, 화면 표면의 `GENERAL_V2_PRESENCE` 67행과 `SUPPLEMENTAL_V2` 149행은 발견 감사 후보로 이동한다. 저장 결과 투영에서는 정식 66행이 모두 채점되어 출처 커버리지 게이트를 통과하지만, 기존 점수 자체는 최신 파서·검색·판정 성능이 아니다. 진단 산출물은 `temp/investment-regression/evaluation-20260918/source-coverage.json`이다.

`temp/investment-regression/evaluation-20260918/mapped-v2-blind-label-queue.json`에는 적용 제외 후보를 포함한 114쌍의 규칙과 당시 허용 근거만 담고 모델 예측·판정은 제외했다. 사람 적용성·판정 라벨 필드는 비어 있으며, 이 큐를 채우기 전에는 v2 성능 수치를 만들지 않는다. 저장 요청이 최신 파서 수정 전 자료이므로 새 실행의 최종 gold를 만들 때는 원본 광고와 현행 청크를 함께 확인한다.

## 문서 현행 정보

| 항목 | 내용 |
| --- | --- |
| 현행 버전 | v1.4 |
| 기준일 | 2026-09-21 |
| 활성 규정 SHA-256 | `6989270c348983aac0e43579c25df55110aef805dccd4a2bbe926ca1fa3a8d7e` |

## 변경 이력

| 버전 | 기준일 | 변경 내용 |
| --- | --- | --- |
| v1.4 | 2026-09-21 | 구조화 프롬프트 A0~A3 평가기·필수 지표와 새 출력·독립 holdout 부재에 따른 성능 주장 차단 |
| v1.3 | 2026-09-18 | ISA 6건 템플릿 66행을 dev/regression으로 결합하고 수수료 기준 개정·적용 제외·판정 지표 경계 기록 |
| v1.2 | 2026-09-14 | 예측 봉인·블라인드 검수 패킷·복수 검수자 gold 봉인·오류유형 조인 평가 경로 추가 |
| v1.1 | 2026-09-10 | 템플릿 독립 항목의 원본·ID snapshot 및 사례 원문 운영 격리 조건 추가 |
| v1.0 | 2026-09-08 | 기존 평가·smoke·silver·회귀 자료의 실제 상태와 사용 금지 범위 최초 정리 |

2026-09-09 사용자 결정에 따른 추가 경계: 템플릿 기준 실행은 일반 템플릿 원본 SHA와
`TPL-` 항목의 원문 snapshot도 동결한다. v2 ID로 연결되지 않았다는 이유로 템플릿 검사를
제외하지 않는다. 심의사례 1~3의 광고문구·판단·판단근거는 운영 기준 입력이 아니며,
사람 검토·평가 프로세스에서만 사용한다. 기존 v2 gold와 새 템플릿 항목을 이름 유사도만으로
동일 정답 처리하지 않는다. 새 출처 체계에 맞는 별도 gold 결합은 아직 미구현이다.

## 1. 결론

현재 최종 성능을 계산할 수 있는 독립 holdout은 없다. 아래 자료는 개발·회귀·smoke·silver로
용도를 제한한다. 파일명에 `gold`가 들어가 있어도 v2 snapshot binding과 사람 확정 범위를
충족하지 않으면 최종 gold가 아니다.

## 2. 데이터 구분

| 세트 | 실제 상태 | 규모 | 허용 용도 | 금지 해석 |
| --- | --- | ---: | --- | --- |
| `search_gold19_reviewed_draft.json` | draft, v2 미결합 | 19쌍 | 규칙 ID·사례 검토 | 최종 검색/판정 정확도 |
| `judgment_workset19_*` | tiny smoke | 19 중 자동결론 3 | 실행 경로 smoke | 3/3을 전체 정확도로 보고 |
| `search_gold7_elasticsearch_nori_bge_m3.json` | 알려진 사례 smoke | 실제 8사례·15근거그룹 | 검색 방식 회귀 | 일반화 성능 |
| 연구원 답지파일럿 회신 | dev/regression | 29행 | 피드백 회귀 | holdout 성능 |
| ISA 심의정답 6건 | dev/regression | 6광고·템플릿 66행 | 템플릿 판정·적용성 회귀 | 일반화 정확도 |
| 광고 10건 silver | silver·검수 필요 | 10광고·1,095규칙검사 | 답지 생성 절차 검수 | gold 또는 운영 정확도 |
| 2026-09-07 NH005 운영 실행 | 무정답 single run | 1광고·64규칙쌍 | 계약·실행 확인 | 성능지표 |
| 독립 holdout | 없음 | 0 | 향후 구축 | 현재 수치 보고 금지 |

신탁형 광고1의 `D-177`, `D-183`, `D-198` 판정은 사용자 검토와 원문 대조에 사용됐으므로 `DEV_REGRESSION`이다. 세 항목은 정확 인용, 외부 대조 필요성, 가상 세제 예시와 실제 실적의 구분을 확인하는 회귀 자료로만 사용한다. 해당 ID나 광고명을 런타임 분기 조건으로 넣지 않으며 이 세 건의 개선을 독립 정확도 또는 일반화 성능으로 보고하지 않는다.

같은 광고의 `C-008`, `C-051`도 규칙 관계와 근거 승계 구현에 사용했으므로 `DEV_REGRESSION`이다. 개정 전 규제목록에 묶인 저장 판정은 당시 결과로 보존하고, 현행 규제목록 관계를 적용한 새 회차와 직접 섞어 정확도를 계산하지 않는다.

## 3. 19건 draft

파일:

```text
C:\work\output\_rag\review\search_gold19_reviewed_draft.json
C:\work\output\_rag\review\gold19_v2_binding_audit_0905.json
```

감사 결과:

```text
UNBOUND 19/19
evaluation_ready=false
사유: regulation_binding snapshot 없음
```

다음 조치:

1. 각 행의 item ID와 현재 v2 의미를 다시 확인한다.
2. 현재 v2 파일 전체 SHA와 해당 규칙 스냅샷을 gold에 기록한다.
3. 알려진 위반만 제공된 행은 `known-positive`로 명시한다.
4. 규칙 ID 정정은 해당 gold 행에만 적용한다.

## 4. 연구원 답지파일럿

원본:

```text
C:\Users\USER\Downloads\검수_답지파일럿.xlsx
SHA-256: a5ce7511efb7743ed31047cf684051591aba4c79393f8d2fbbb2d9994e165703
```

정규화 회신:

```text
C:\work\output\_rag\dev_regression\researcher_feedback_0902\연구원검수_회신_20260903.json
```

요약:

```text
29행
연구원 O 27 / X 2
최종 판정: 충족 25 / 위반 2 / 미해당 2
수정 행: 4, 29
```

이미 피드백을 확인하고 로직 논의에 사용했으므로 dev/regression이다. 이후 수정의 회귀
확인에는 쓸 수 있으나 새 일반화 성능에는 쓰지 않는다.

### 4.1 ISA 심의정답 6건

ISA 일반1·신탁형3·일임형2의 답안은 템플릿 66개 행과 연결된다. 광고와 답안을 이미
규칙·파서·판정 개발에 사용했으므로 `DEV_REGRESSION`으로만 채점한다. 과거 답안 중
수수료 부적정 2건은 2026-09-18 승인된 존재확인 기준과 충돌해 충족으로 버전 보정하고,
조건이 발동하지 않아 적정 여부를 판단하지 않은 3건은 적용 제외로 분리한다.

현재 저장 예측의 적용 대상 정확 일치는 34/63, 충족·위반 gold 중 확정 판정은 28/55,
확정 판정 정확도는 28/28이다. 다만 확정된 28건은 모두 충족 정답이며 위반 gold 2건은
모두 판단불가여서 위반 탐지율은 0/2다. 사람 확인 gold는 6/8을 판단불가로 보존했고
적용 제외 gold 3건은 모두 판단불가였다. 따라서 이 수치는 확정된 충족 판정의 회귀
증거와 과도한 기권·위반 미탐지 진단에는 쓸 수 있지만 균형 판정 정확도나 일반화 성능은
나타내지 않는다. 결합 행과 원 예측 해시는 비공개
`temp/investment-regression/evaluation-20260918/`에 보존한다.

## 5. 광고 10건 silver

파일:

```text
C:\work\output\_rag\human_review\answer10_current\광고10_silver_연구원검수.xlsx
C:\work\output\_rag\human_review\answer10_current\silver_검수표_요약.json
```

요약:

```text
광고 10건
규칙 검사 1,095
충족 520 / 위반 10 / 판단불가 64 / 미해당 489 / 출력실패 12
```

생성 당시 규제 입력은 v2만 사용했고 gold·사례 매핑·사례별 후처리는 읽지 않았다고
기록돼 있다. 그래도 사람 검수가 끝나지 않았으므로 silver다. 미해당 489건 전부를 운영
결과로 노출하는 자료가 아니라 적용성 분류 검수용 표본 풀이다.

## 6. 검색 smoke 8사례

파일명은 `search_gold7_*`지만 최신 Elasticsearch 결과의 실제 사례 수는 8이다.

```text
C:\work\output\_rag\review\search_gold7_elasticsearch_nori_bge_m3.json
```

환경·결과:

```text
Elasticsearch 8.15.0 + Nori
BGE-M3 1024차원, DGX CUDA
8사례 / 근거그룹 15
Hybrid RRF group recall@5 = 0.800000
Hybrid RRF group recall@10 = 0.933333
후보 합집합 coverage = 15/15
```

알려진 소규모 사례 smoke라 최종 공개 수치로 쓰지 않는다.

## 7. workset19 판정 smoke

```text
C:\work\output\_rag\review\judgment_workset19_input.json
C:\work\output\_rag\review\judgment_workset19_results.json
C:\work\output\_rag\review\judgment_workset19_eval.json
```

```text
전체 19
자동 결론 3
자동 정답 3
미판정 16
```

3/3은 자동 결론을 낸 세 건만의 조건부 결과다. 전체 19 정확도도 아니고 현 운영형
파이프라인의 최종 성능도 아니다.

## 8. 최신 무정답 운영 실행

```text
C:\work\nh-ad-compliance\temp\nh005-current-0907-v2\04_operational_results.json
```

```text
요청 64 / 출력 64 / 출력실패 0
본판정: 위반 3 / 충족 42 / 판단불가 3
미해당 제외 16
deferred rule 27
```

계약과 실행 복구 경로 확인용이다. 사람 확정 정답과 독립 조인한 결과가 아니므로 의미
정확도나 검색 Recall을 계산하지 않는다.

## 9. 격리·폐기 자료

다음 폴더는 사례별 보정이나 구판이 포함된 격리 자료다.

```text
C:\work\output\_rag\_quarantine_case_derived_20260904
C:\work\output\_rag\_retired_superseded_20260904
```

- 런타임 검색·판정 코드에 재도입하지 않는다.
- 최종 성능 계산에 사용하지 않는다.
- 오류의 역사적 원인을 확인할 때만 읽는다.

## 10. 새 holdout 구축 조건

1. 개발 중 보지 않은 광고를 사용한다.
2. 규제목록 v2 SHA와 규칙별 스냅샷을 고정한다.
3. known-positive, exhaustive-reviewed, pooled-reviewed 상태를 구분한다.
4. 규칙 발견, 광고 근거 검색, 적용성, 최종 판정, 부재 판정을 따로 채점한다.
5. 표시의무·금지·양식/절차·시인성·외부자료 규칙을 나눠 분모를 명시한다.
6. 입력 부족과 모델 오류를 미해당 또는 정답으로 치환하지 않는다.
7. 연구원 확정 전에는 silver이며 최종지표에 넣지 않는다.

## 11. 블라인드 평가 실행 계약

- `tools/manage_blind_evaluation.py freeze`로 모델 예측과 규칙·모델·검색 원본 해시를 먼저 봉인한다.
- `packet`은 판정값·사유·confidence·decision trace를 제거하고 규칙 원문·조건 계약만 남긴다.
- 사람 판정은 검수자별 ID·판정·근거·시각을 누적한다. 기본 두 명 미만이거나 최종 결정이 없으면 `HUMAN_REVIEW_IN_PROGRESS`다.
- 불일치는 조정자가 `ADJUDICATION`으로 확정하고, 전 쌍이 완료된 `GOLD_READY`만 예측과 조인한다.
- `BLIND_HOLDOUT`은 미관찰 확인자와 확인 시각이 없으면 생성 자체를 거부한다. 현재 독립 holdout 수는 여전히 0이다.
- 평가 결과는 출력 계약 실패, 규칙 과적용, 적용 규칙 미탐, 과신, 미해결, 판정 반전을 별도 오류유형으로 집계한다.
