# Elasticsearch + nori 형태소 분석기.
#
# 공식 이미지에는 nori 가 없다 — 한국어 분석기인데 플러그인이다. DAP 의 ES 가
# 한국어 analyzer 를 쓴다고 했으므로(ADR-0071) 로컬도 같은 조건으로 맞춘다.
FROM docker.elastic.co/elasticsearch/elasticsearch:8.14.3
RUN bin/elasticsearch-plugin install --batch analysis-nori
