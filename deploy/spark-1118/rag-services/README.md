# spark-1118 RAG services

fc87의 NH 광고심의 검색 계약을 spark-1118에서 재현한다.

- Elasticsearch 8.15.0 + analysis-nori: loopback `9201`
- BAAI/bge-m3 + bge-reranker-v2-m3: loopback `8103`
- 모델 캐시는 기존 `nh-ai`의 Hugging Face 캐시를 공유한다.
- Gemma `8102`와 PaddleX `8081`은 spark-1118의 기존 `nh-ai` Compose를 사용한다.

최초 1회:

```bash
docker compose build
docker compose --profile setup run --rm bge-model-sync
docker compose up -d elasticsearch bge
docker compose ps
```

규칙 인덱스는 운영 RAG가 정본 규제목록과 BGE 벡터의 해시로 버전명을 만든 뒤
`ensure_rule_index`로 재구축한다. fc87의 오래된 인덱스 볼륨을 복제하지 않는다.

2026-09-22 구축 확인:

- BGE와 Elasticsearch 컨테이너 기동 및 health 통과
- Nori 플러그인 8.15.0 확인
- 정본 규칙 인덱스 `nh-rules-v2-operational-20260909-catalog-7cf03bfa0b506eb8`
  256문서 생성 확인
- 운영 웹 이미지는 `infra/operational`의 Python 3.11 + 파서 Python 3.13 분리 구조로
  다시 패키징해 배포한다. 기존 상태 디렉터리는 복사·해시 확인 전까지 전환하지 않는다.
