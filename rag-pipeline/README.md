# NH 광고심의 RAG 정본

파서 결과를 광고 근거 청크로 변환하고, 규제목록 v2에서 적용 규칙을 검색한 뒤
Gemma 구조화 판정을 수행하는 독립 실행 코드입니다.

전체 입력 계약, 실행 순서, 데이터·평가 경계는
[RAG_PIPELINE.md](RAG_PIPELINE.md)를 참조하십시오.

## 빠른 확인

```bash
python tools/run_rag_ci.py
python tools/prepare_operational_inputs.py --help
python tools/run_operational_e2e.py --help
python tools/serve_operational_api.py --help
```

운영 서비스는 파서 이후의 `nh-ad-review-integrated-input-v1` 한 건과 수요사 또는
접수 시스템이 확인한 상품군을 받아 비동기 작업으로 처리한다. `POST /v1/reviews`는
즉시 작업 ID를 반환하고 상태·결과는 별도 조회한다. 모델 confidence는 자동 승인에
사용하지 않으며 위반·판단불가는 항상 연구원 검토 대상으로 남는다.

## 포함 범위

- 파서 P1/P3 동일성 검증과 통합 입력 생성
- coarse/fine 광고 근거 청킹
- 규제목록 v2 C/D/T 후보 검색
- Elasticsearch BM25와 BGE-M3 벡터 검색의 RRF 결합
- Gemma 구조화 판정과 결과 계약 검증
- 운영 코드와 답지·연구원 피드백의 누수 방지 검사

원본 광고, 규제목록 파일, 답지, 연구원 검수표와 실행 결과는 저장소에 포함하지 않습니다.
