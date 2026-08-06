# -*- coding: utf-8 -*-
"""OpenSearch/Elasticsearch(nori) 색인·검색·측정 — DAP 로 가기 전 리허설.

**공용 레포(nh-ad-compliance)의 개발 환경을 그대로 쓴다.** compose.dev.yml 이
OpenSearch 2.15 를 9200 에 띄우고 analysis-nori 도 이미 깔려 있다. 따로 컨테이너를
만들 이유가 없고, **실제로 팀이 쓰는 환경에서 재는 것이 더 정확하다.**
OpenSearch 는 Elasticsearch 에서 갈라져 나온 것이라 BM25·nori 동작이 같다.

**로컬 BM25 와 무엇이 다른가를 하나로 좁힌다.** 색인에 넣는 문자열은 로컬과 완전히
같게 두고(`title + article_no + content` 연결) **토크나이저만 다르다** — 로컬은 한글
바이그램, 여기는 nori 형태소. 그래서 점수 차이가 나면 그것은 토크나이저 차이다.
문자열까지 다르게 하면 무엇 때문에 달라졌는지 못 가린다.

ES 는 5.0부터 기본 유사도가 BM25 라 공식은 로컬과 같다.

  docker compose -f ../nh-ad-compliance/compose.dev.yml up -d opensearch
  python rag/es_search.py --setup            # 색인 생성 + 적재
  python rag/es_search.py --measure          # gold 334 로 측정
  python rag/es_search.py --query "연 최고 7.0% 우대금리"
"""
import os
import sys
import json
import time
import argparse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG = os.path.join(ROOT, "output", "_rag")
ES = os.environ.get("ES_URL", "http://127.0.0.1:9200")
INDEX = "evidences_poc"


def _req(method, path, body=None):
    data = None
    if body is not None:
        data = (body if isinstance(body, (bytes, str)) else json.dumps(body, ensure_ascii=False))
        if isinstance(data, str):
            data = data.encode("utf-8")
    req = urllib.request.Request(f"{ES}{path}", data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path} → {e.code}: {e.read().decode('utf-8')[:300]}")
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"ES 에 연결 못 함 ({ES}) — Docker Desktop 을 켜고\n"
            f"  docker compose -f rag/es/compose.yml up -d --build\n원인: {e.reason}")


# 매핑. 공용 레포 제안(§SCHEMA_ISSUES ⑦)과 같은 모양으로 둔다 — 여기서 검증되면
# 그대로 DAP 제안서에 쓴다.
#   search_text   nori 분석. 로컬 BM25 와 같은 연결 문자열
#   article_no    text + keyword 멀티필드 — 「제16조」 정확 일치는 keyword 로
MAPPING = {
    "settings": {
        "analysis": {
            "tokenizer": {
                # mixed: 복합어를 쪼개면서 원형도 남긴다. 「금융투자업」이
                # 「금융+투자+업」과 원형 둘 다로 걸리게 — 회수율에 유리하다.
                "korean": {"type": "nori_tokenizer", "decompound_mode": "mixed"},
            },
            "analyzer": {
                "korean": {"type": "custom", "tokenizer": "korean",
                            "filter": ["lowercase"]},
            },
        },
    },
    "mappings": {
        "properties": {
            "search_text": {"type": "text", "analyzer": "korean"},
            "title": {"type": "text", "analyzer": "korean"},
            "article_no": {"type": "text", "analyzer": "korean",
                           "fields": {"keyword": {"type": "keyword"}}},
            "evidence_id": {"type": "keyword"},
            "kind": {"type": "keyword"},           # rule / article
            "evidence_type": {"type": "keyword"},
            "rule_type": {"type": "keyword"},
            "product_group": {"type": "keyword"},
            "medium": {"type": "keyword"},
            "row": {"type": "integer"},            # rule_index.jsonl 줄번호 — gold 대조용
        },
    },
}


def load_rows():
    rows = [json.loads(l) for l in open(os.path.join(RAG, "rule_index.jsonl"),
                                        encoding="utf-8")]
    n_rules = sum(1 for r in rows if r["evidence_id"].startswith("R-"))
    return rows, n_rules


def _exists():
    try:
        _req("GET", f"/{INDEX}")
        return True
    except RuntimeError:
        return False


def do_setup():
    rows, n_rules = load_rows()
    info = _req("GET", "/")
    plugins = _req("GET", "/_cat/plugins?format=json")
    has_nori = any("nori" in p.get("component", "") for p in plugins)
    if not has_nori:
        raise RuntimeError("analysis-nori 플러그인이 없다 — compose 가 Dockerfile 로 "
                           "빌드됐는지 확인 (--build)")
    print(f"ES {info['version']['number']} · nori 있음")

    if _exists():
        _req("DELETE", f"/{INDEX}")
    _req("PUT", f"/{INDEX}", MAPPING)

    # 벌크 적재. **부칙(is_active=False)은 안 넣는다** — 로컬과 같은 조건.
    lines, n = [], 0
    for i, r in enumerate(rows):
        if not r.get("is_active", True):
            continue
        doc = {
            "search_text": f"{r.get('title','')} {r.get('article_no','') or ''} "
                           f"{r.get('content','')}",
            "title": r.get("title", ""),
            "article_no": r.get("article_no") or "",
            "evidence_id": r["evidence_id"],
            "kind": "rule" if r["evidence_id"].startswith("R-") else "article",
            "evidence_type": r.get("evidence_type", ""),
            "rule_type": r.get("rule_type", ""),
            "product_group": r.get("product_group") or [],
            "medium": r.get("medium") or [],
            "row": i,
        }
        # _bulk 를 인덱스 없는 경로(/_bulk)로 보내므로 줄마다 _index 를 적어야 한다.
        # 안 적으면 400 "index is missing" 이 난다.
        lines.append(json.dumps({"index": {"_index": INDEX, "_id": r["evidence_id"]}},
                                ensure_ascii=False))
        lines.append(json.dumps(doc, ensure_ascii=False))
        n += 1
        if len(lines) >= 2000:
            _bulk(lines); lines = []
    if lines:
        _bulk(lines)
    _req("POST", f"/{INDEX}/_refresh")
    got = _req("GET", f"/{INDEX}/_count")["count"]
    print(f"적재 {n:,}건 → 색인 {got:,}건" + ("" if got == n else "  ← 어긋남!"))


def _bulk(lines):
    out = _req("POST", "/_bulk", "\n".join(lines) + "\n")
    if out.get("errors"):
        bad = [x for x in out["items"] if x["index"].get("error")][:3]
        raise RuntimeError(f"벌크 오류: {json.dumps(bad, ensure_ascii=False)[:400]}")


def search(query, k=100, kind=None):
    """search_text 하나에 match — 로컬 BM25 와 같은 조건(문자열 하나, BM25 점수)."""
    body = {"size": k, "_source": ["row", "evidence_id", "kind", "title", "article_no"],
            "query": {"match": {"search_text": query}}}
    if kind:
        body["query"] = {"bool": {"must": body["query"],
                                  "filter": [{"term": {"kind": kind}}]}}
    hits = _req("POST", f"/{INDEX}/_search", body)["hits"]["hits"]
    return [h["_source"] for h in hits]


def measure(k_list=(1, 3, 5, 10, 20, 50)):
    rows, n_rules = load_rows()
    gold = json.load(open(os.path.join(RAG, "gold.json"), encoding="utf-8"))
    hit = {k: 0 for k in k_list}
    mrr = 0.0
    t0 = time.time()
    for g in gold:
        ans = {c + n_rules for c in g["정답청크"]}
        got = search(g["q"], max(k_list))
        p = next((r for r, h in enumerate(got, 1) if h["row"] in ans), None)
        for k in k_list:
            if p and p <= k:
                hit[k] += 1
        mrr += 1 / p if p else 0
    n = len(gold)
    print(f"\nES(nori) · gold {n}건 · {time.time()-t0:.0f}초")
    print("  " + " · ".join(f"R@{k} {hit[k]/n*100:5.1f}%" for k in k_list)
          + f" · MRR {mrr/n:.3f}")
    print("\n비교 — 로컬 BM25(바이그램), 같은 색인·같은 문자열:")
    print("  R@1 0.0% · R@5 14.4% · R@10 42.5% · R@20 67.4% · R@50 80.2% · MRR 0.106")
    print("\n색인에 넣은 문자열이 같으므로 차이는 전부 토크나이저(nori↔바이그램)다.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--measure", action="store_true")
    ap.add_argument("--query")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--kind", choices=("rule", "article"))
    a = ap.parse_args()

    if a.setup:
        do_setup()
    if a.measure:
        measure()
    if a.query:
        for r, h in enumerate(search(a.query, a.k, a.kind), 1):
            print(f"{r}. [{h['kind']}] {h['evidence_id']} {h['article_no'] or '':10s} "
                  f"{h['title'][:56]}")
    if not (a.setup or a.measure or a.query):
        ap.error("--setup · --measure · --query 중 하나는 필요합니다")


if __name__ == "__main__":
    main()
