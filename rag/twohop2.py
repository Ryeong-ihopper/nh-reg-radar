# -*- coding: utf-8 -*-
"""광고 → 규칙 → 조문. **근거 주소를 항·호·목까지 살려서** 측정한다.

광고를 조문에 바로 던지는 방식은 전부 0% 였다(원문·임의청크·파서청크 × BM25·
벡터·하이브리드 18조합). 광고 말투와 법률 말투가 너무 달라서다.

    광고    "최저 연 4.45% ~ 최대 연 5.45% (2026.06.18. 당행 기준금리…)"
    조문    "나. 이자율의 범위 및 산출기준"

규칙은 그 사이에 있다. **실무 말투로 쓰였고 근거로 조문이 달려 있다.**

    규칙 R-0614  "대출성 의무표시 - 이자율의 범위 및 산출기준(연체이자율 포함)"
      근거 원문   "은행 광고심의 기준 제16조 제1항 제6호 나목"

    ① 광고 청크 → 규칙 검색   말투가 겹친다
    ② 규칙 근거 → 조문       링크를 따라간다. 검색이 아니다

**근거를 조 단위로 자르고 있었다.** `match_rules.py` 가 「제16조 제1항 제5호 나목」을
「제16조」로만 저장해서, 규칙을 정확히 찾아도 §16 의 21조각 중 어느 것인지 몰랐다.
817건이 항·호·목을 갖고 있는데 전부 버렸다. 여기서 원문에서 다시 뽑아 쓴다.

  python rag/twohop2.py --measure
  python rag/twohop2.py --ad 2026_004_예금성
"""
import os
import re
import sys
import json
import math
import time
import argparse
import hashlib
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from es_search import _req, _bulk  # noqa: E402  (ES http 헬퍼 재사용)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG = os.path.join(ROOT, "output", "_rag")
HO = os.path.join(RAG, "rule_index_ho.jsonl")
VECS_HO = os.path.join(RAG, "vectors_ho.f16.npy")
NL = chr(10)
RRF_K = 60
# 청크당 RRF 에 넣기 전 후보 풀 크기. **50 이면 필터가 역효과를 낸다** —
# 상품군으로 거르면 무관한 상품 후보가 이 50자리에서 빠지고 그 자리를
# 관련 상품이지만 원래 순위가 애매하던 후보가 새로 차지해, RRF 합산에서
# 오히려 진짜 정답을 밀어낸다(실측: 대출 광고에서 필터로 정답이 1등→4등).
# 풀을 넉넉히 키우면(규칙 전체 1,744건 대비 여유 있게) 필터 여부와
# 무관하게 상품군 안의 후보가 거의 다 풀에 들어가 이 부작용이 없어진다.
POOL_K = 300

# 로컬 바이그램 BM25·로컬 벡터 검색은 진짜 검색엔진이 아니다 — 스키마 필드
# (product_group 등)를 못 읽고 문자열 하나만 본다. `es_search.py` 가 이미
# 붙여 둔 실제 OpenSearch(nori·knn 플러그인 있음, `docker ps` 로 기동 확인,
# cl-opensearch 컨테이너)를 그대로 쓴다 — 별도 색인(evidences_ho)에 호 단위
# 35,961행 전부(스키마 필드 포함)를 넣는다. --backend es 로 켠다.
ES_INDEX_HO = "evidences_ho"

ALIAS = {
    "은행 광고심의 기준": "은행 광고심의 기준 및 세칙",
    "은행 광고심의기준": "은행 광고심의 기준 및 세칙",
    "은행 광고심의 기준 세칙": "은행 광고심의 기준 및 세칙",
    "금융소비자보호법": "금융소비자 보호에 관한 법률",
    "금소법": "금융소비자 보호에 관한 법률",
    "여신금융상품 광고에 관한 세부지침": "여신전문금융회사 등의 광고에 관한 규정 세부지침",
    "증발공규정": "증권의 발행 및 공시 등에 관한 규정",
    "협회 표준내부통제기준": "금융투자회사 표준내부통제기준",
    "인공지능기본법": "인공지능 발전과 신뢰 기반 조성 등에 관한 기본법",
    "약관법": "약관의 규제에 관한 법률",
    "금융소비자 보호에 관한 금융소비자 보호에 관한 감독규정": "금융소비자 보호에 관한 감독규정",
}
_HANGCH = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"

PRODUCT_MAP = {"예금성": "DEPOSIT", "대출성": "LOAN",
               "투자성": "INVESTMENT", "보장성": "INSURANCE"}


def product_of(ad_id):
    """광고id(「2026_003_예금성」)에서 상품군을 읽는다. rule 의 product_group
    스키마 값(DEPOSIT/LOAN/INVESTMENT/INSURANCE)과 맞춘다."""
    for kw, code in PRODUCT_MAP.items():
        if kw in str(ad_id or ""):
            return code
    return None

# 「은행 광고심의 기준 제16조 제1항 제5호 나목」·「… 제2-38조 제1항」 을 읽는다.
_REF = re.compile(
    r"(?P<name>[가-힣·\s]+?)\s*"
    r"제\s*(?P<jo>\d+(?:-\d+)?)\s*조(?:\s*의\s*(?P<ji>\d+))?"
    r"(?:\s*제\s*(?P<hang>\d+)\s*항)?"
    r"(?:\s*제?\s*(?P<ho>\d+)\s*호)?"
    r"(?:\s*(?P<mok>[가-힣])\s*목)?")


def parse_basis(text):
    """근거 원문 → [(규정, 조, 경로)]. 경로는 ho_path 와 같은 모양(「5 나」)."""
    out = []
    for part in re.split(r"[,\n;]", str(text or "")):
        m = _REF.search(part)
        if not m:
            continue
        name = (m.group("name") or "").strip(" ·,")
        name = ALIAS.get(name, name)
        if not name:
            continue
        jo = f"제{m.group('jo')}조"
        if m.group("ji"):
            jo += f"의{m.group('ji')}"
        # **항 번호는 경로에 안 넣는다.** 색인의 ho_path 는 조문 첫머리 ①이
        # 도입문으로 흡수돼 「5 나」로 저장된 경우가 많다. 호·목만으로 맞춘다.
        bits = [x for x in (m.group("ho"), m.group("mok")) if x]
        out.append((name, jo, " ".join(bits)))
    return out


def norm(s):
    return re.sub(r"[\s·ㆍ]", "", str(s or ""))


def _wsnorm(s):
    """공백만 지운다(매뉴얼 발췌 대조용) — 개행·들여쓰기가 저장본마다 달라서."""
    return re.sub(r"\s+", "", str(s or ""))


def tokenize(s):
    out = re.findall(r"제\s*\d+조(?:의\s*\d+)?|[A-Za-z]+|\d+", str(s or ""))
    for w in re.findall(r"[가-힣]+", str(s or "")):
        out += [w[i:i+2] for i in range(len(w)-1)] or [w]
    return out


def index_text(r):
    return f"{r.get('title','')} {r.get('article_no') or ''} {r.get('content','')}"


class BM25:
    def __init__(self, rows, only=None):
        docs, df = [], collections.Counter()
        for r in rows:
            tf = collections.Counter(tokenize(index_text(r)))
            docs.append(tf)
            df.update(tf.keys())
        n = len(docs)
        self.idf = {t: math.log(1+(n-c+0.5)/(c+0.5)) for t, c in df.items()}
        self.inv = collections.defaultdict(list)
        for i, d in enumerate(docs):
            for t, f in d.items():
                self.inv[t].append((i, f))
        self.dl = [sum(d.values()) for d in docs]
        self.avgdl = sum(self.dl)/max(n, 1)
        self.only = only

    def __call__(self, q, k=50, allow=None):
        K1, B = 1.2, 0.75
        sc = collections.defaultdict(float)
        for t in set(tokenize(q)):
            post = self.inv.get(t)
            if not post:
                continue
            w = self.idf[t]
            for i, f in post:
                if allow is not None and not allow[i]:
                    continue
                sc[i] += w*f*(K1+1)/(f+K1*(1-B+B*self.dl[i]/self.avgdl))
        return [i for i, _ in sorted(sc.items(), key=lambda x: -x[1])[:k]]


def rrf(*rankings, top=50):
    sc = collections.defaultdict(float)
    for rank in rankings:
        for r, i in enumerate(rank, 1):
            sc[i] += 1.0/(RRF_K+r)
    return [i for i, _ in sorted(sc.items(), key=lambda x: -x[1])[:top]]


# ── 실제 OpenSearch(nori) 색인 — 호 단위, 스키마 필드 그대로 ────────────
ES_MAPPING_HO = {
    "settings": {
        "index": {"knn": True},
        "analysis": {
            "tokenizer": {"korean": {"type": "nori_tokenizer",
                                      "decompound_mode": "mixed"}},
            "analyzer": {"korean": {"type": "custom", "tokenizer": "korean",
                                    "filter": ["lowercase"]}},
        },
    },
    "mappings": {
        "properties": {
            "search_text": {"type": "text", "analyzer": "korean"},
            "title": {"type": "text", "analyzer": "korean"},
            "article_no": {"type": "text", "analyzer": "korean",
                           "fields": {"keyword": {"type": "keyword"}}},
            "evidence_id": {"type": "keyword"},
            "kind": {"type": "keyword"},            # rule / article / manual
            "evidence_type": {"type": "keyword"},
            "rule_type": {"type": "keyword"},
            "product_group": {"type": "keyword"},   # 스키마 그대로 — 필터로 씀
            "medium": {"type": "keyword"},
            "row": {"type": "integer"},             # rule_index_ho.jsonl 줄번호
            "vector": {"type": "knn_vector", "dimension": 1024,
                       "method": {"name": "hnsw", "engine": "lucene",
                                  "space_type": "cosinesimil"}},
        },
    },
}


def _kind_of(evidence_id):
    return {"R": "rule", "C": "article", "M": "manual"}.get(evidence_id[0], "?")


def setup_es_ho():
    """rule_index_ho.jsonl(35,961행) + vectors_ho.f16.npy 를 OpenSearch 에
    실제로 적재한다. 로컬 파이썬 색인은 스키마를 못 읽어 product_group 같은
    필터를 따로 손으로 붙여야 했다 — 여기서는 그 필드를 진짜 색인 필드로 넣어
    ES 가 직접 거르게 한다."""
    import numpy as np
    rows = [json.loads(l) for l in open(HO, encoding="utf-8")]
    V = np.load(VECS_HO).astype("float32")
    assert V.shape[0] == len(rows), f"벡터 {V.shape[0]} != 행 {len(rows)}"

    info = _req("GET", "/")
    plugins = _req("GET", "/_cat/plugins?format=json")
    if not any("nori" in p.get("component", "") for p in plugins):
        raise RuntimeError("analysis-nori 없음")
    print(f"ES {info['version']['number']} · nori 있음 · knn 있음")

    try:
        _req("DELETE", f"/{ES_INDEX_HO}")
    except RuntimeError:
        pass
    _req("PUT", f"/{ES_INDEX_HO}", ES_MAPPING_HO)

    lines, n = [], 0
    t0 = time.time()
    for i, r in enumerate(rows):
        doc = {
            "search_text": index_text(r),
            "title": r.get("title", ""),
            "article_no": r.get("article_no") or "",
            "evidence_id": r["evidence_id"],
            "kind": _kind_of(r["evidence_id"]),
            "evidence_type": r.get("evidence_type", ""),
            "rule_type": r.get("rule_type", ""),
            "product_group": r.get("product_group") or [],
            "medium": r.get("medium") or [],
            "row": i,
            "vector": V[i].tolist(),
        }
        lines.append(json.dumps({"index": {"_index": ES_INDEX_HO, "_id": r["evidence_id"]}},
                                ensure_ascii=False))
        lines.append(json.dumps(doc, ensure_ascii=False))
        n += 1
        if len(lines) >= 1000:
            _bulk(lines)
            lines = []
            print(f"  {n:,}/{len(rows):,} ({time.time()-t0:.0f}초)", end="\r")
    if lines:
        _bulk(lines)
    _req("POST", f"/{ES_INDEX_HO}/_refresh")
    got = _req("GET", f"/{ES_INDEX_HO}/_count")["count"]
    print(f"\n적재 {n:,}건 → 색인 {got:,}건 ({time.time()-t0:.0f}초)"
          + ("" if got == n else "  ← 어긋남!"))


def _es_filter(kind, product):
    f = [{"term": {"kind": kind}}]
    if product:
        f.append({"bool": {"should": [
            {"term": {"product_group": product}},
            {"bool": {"must_not": {"exists": {"field": "product_group"}}}},
        ]}})
    return f


def _es_bm25(text, k, kind, product):
    body = {"size": k, "_source": ["row"],
            "query": {"bool": {"must": {"match": {"search_text": text}},
                               "filter": _es_filter(kind, product)}}}
    hits = _req("POST", f"/{ES_INDEX_HO}/_search", body)["hits"]["hits"]
    return [h["_source"]["row"] for h in hits]


def _es_knn(vec, k, kind, product):
    body = {"size": k, "_source": ["row"],
            "query": {"knn": {"vector": {"vector": vec, "k": k,
                              "filter": {"bool": {"filter": _es_filter(kind, product)}}}}}}
    hits = _req("POST", f"/{ES_INDEX_HO}/_search", body)["hits"]["hits"]
    return [h["_source"]["row"] for h in hits]


# ── 진짜 Elasticsearch — **수요사(DAP)가 실제로 쓰는 게 이거다**
# (`STACK.md` "수요사는 Elasticsearch 만 쓴다", `SCHEMA_ISSUES.md` "벡터 DB가
# Elasticsearch 하나로 정해졌다"). 위 OpenSearch 는 공용 레포 dev 환경에 이미
# 떠 있어 먼저 붙였지만, 최종 타깃이 아니다 — 로컬에 별도로 실제 Elasticsearch
# (+ nori 플러그인) 를 띄워 그걸 쓴다. 매핑·쿼리 문법이 OpenSearch 와 달라
# (dense_vector/knn 최상위 절) 따로 둔다. `docker compose -f rag/es/compose.yml
# up -d --build` 로 기동(포트 9201, OpenSearch 의 9200 과 겹치지 않게).
REAL_ES_URL = os.environ.get("REAL_ES_URL", "http://127.0.0.1:9201")
REAL_ES_INDEX = "evidences_ho"

REAL_ES_MAPPING = {
    "settings": {
        "analysis": {
            "tokenizer": {"korean": {"type": "nori_tokenizer",
                                      "decompound_mode": "mixed"}},
            "analyzer": {"korean": {"type": "custom", "tokenizer": "korean",
                                    "filter": ["lowercase"]}},
        },
    },
    "mappings": {
        "properties": {
            "search_text": {"type": "text", "analyzer": "korean"},
            "title": {"type": "text", "analyzer": "korean"},
            "article_no": {"type": "text", "analyzer": "korean",
                           "fields": {"keyword": {"type": "keyword"}}},
            "evidence_id": {"type": "keyword"},
            "kind": {"type": "keyword"},
            "evidence_type": {"type": "keyword"},
            "rule_type": {"type": "keyword"},
            "product_group": {"type": "keyword"},
            "medium": {"type": "keyword"},
            "row": {"type": "integer"},
            "vector": {"type": "dense_vector", "dims": 1024,
                       "index": True, "similarity": "cosine"},
        },
    },
}


def _ereq(method, path, body=None):
    import urllib.request
    import urllib.error
    data = None
    if body is not None:
        data = body if isinstance(body, (bytes, str)) else json.dumps(body, ensure_ascii=False)
        if isinstance(data, str):
            data = data.encode("utf-8")
    req = urllib.request.Request(f"{REAL_ES_URL}{path}", data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path} → {e.code}: {e.read().decode('utf-8')[:400]}")
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Elasticsearch 에 연결 못 함({REAL_ES_URL}) — "
            f"docker compose -f rag/es/compose.yml up -d --build 필요\n원인: {e.reason}")


def _ebulk(lines):
    out = _ereq("POST", "/_bulk", "\n".join(lines) + "\n")
    if out.get("errors"):
        bad = [x for x in out["items"] if x.get("index", {}).get("error")][:3]
        raise RuntimeError(f"벌크 오류: {json.dumps(bad, ensure_ascii=False)[:400]}")


def setup_real_es_ho():
    import numpy as np
    rows = [json.loads(l) for l in open(HO, encoding="utf-8")]
    V = np.load(VECS_HO).astype("float32")
    assert V.shape[0] == len(rows), f"벡터 {V.shape[0]} != 행 {len(rows)}"

    info = _ereq("GET", "/")
    plugins = _ereq("GET", "/_cat/plugins?format=json")
    if not any("analysis-nori" in p.get("component", "") for p in plugins):
        raise RuntimeError("analysis-nori 플러그인 없음 — rag/es/Dockerfile 확인")
    print(f"Elasticsearch {info['version']['number']} · nori 있음")

    try:
        _ereq("DELETE", f"/{REAL_ES_INDEX}")
    except RuntimeError:
        pass
    _ereq("PUT", f"/{REAL_ES_INDEX}", REAL_ES_MAPPING)

    lines, n = [], 0
    t0 = time.time()
    for i, r in enumerate(rows):
        doc = {
            "search_text": index_text(r),
            "title": r.get("title", ""),
            "article_no": r.get("article_no") or "",
            "evidence_id": r["evidence_id"],
            "kind": _kind_of(r["evidence_id"]),
            "evidence_type": r.get("evidence_type", ""),
            "rule_type": r.get("rule_type", ""),
            "product_group": r.get("product_group") or [],
            "medium": r.get("medium") or [],
            "row": i,
            "vector": V[i].tolist(),
        }
        lines.append(json.dumps({"index": {"_index": REAL_ES_INDEX, "_id": r["evidence_id"]}},
                                ensure_ascii=False))
        lines.append(json.dumps(doc, ensure_ascii=False))
        n += 1
        if len(lines) >= 1000:
            _ebulk(lines)
            lines = []
            print(f"  {n:,}/{len(rows):,} ({time.time()-t0:.0f}초)", end="\r")
    if lines:
        _ebulk(lines)
    _ereq("POST", f"/{REAL_ES_INDEX}/_refresh")
    got = _ereq("GET", f"/{REAL_ES_INDEX}/_count")["count"]
    print(f"\n적재 {n:,}건 → 색인 {got:,}건 ({time.time()-t0:.0f}초)"
          + ("" if got == n else "  ← 어긋남!"))


def _real_es_bm25(text, k, kind, product):
    body = {"size": k, "_source": ["row"],
            "query": {"bool": {"must": {"match": {"search_text": text}},
                               "filter": _es_filter(kind, product)}}}
    hits = _ereq("POST", f"/{REAL_ES_INDEX}/_search", body)["hits"]["hits"]
    return [h["_source"]["row"] for h in hits]


def _real_es_knn(vec, k, kind, product):
    body = {"size": k, "_source": ["row"],
            "knn": {"field": "vector", "query_vector": vec, "k": k,
                    "num_candidates": max(k*5, 100),
                    "filter": {"bool": {"filter": _es_filter(kind, product)}}}}
    hits = _ereq("POST", f"/{REAL_ES_INDEX}/_search", body)["hits"]["hits"]
    return [h["_source"]["row"] for h in hits]


class TwoHop2:
    def __init__(self):
        import numpy as np
        self.rows = [json.loads(l) for l in open(HO, encoding="utf-8")]
        self.n_rules = sum(1 for r in self.rows
                           if r["evidence_id"].startswith("R-"))
        self.bm = BM25(self.rows)
        self.V = None
        if os.path.exists(VECS_HO):
            self.V = self._load_vectors(np)
        self.EMB = None
        self.is_rule = np.array([r["evidence_id"].startswith("R-")
                                 for r in self.rows])
        # product_group 은 규칙 스키마에 이미 있다(DEPOSIT/LOAN/INVESTMENT/
        # INSURANCE, 빈 리스트=상품 공통). 새로 만들 것 없이 그대로 쓴다.
        self.product_group = [frozenset(r.get("product_group") or [])
                               for r in self.rows]

        # (규정, 조, 경로) → 조문 행. **호·목까지 살린다.**
        idx = collections.defaultdict(list)
        by_article = collections.defaultdict(list)
        for i, r in enumerate(self.rows):
            if r["evidence_id"].startswith("R-"):
                continue
            m = re.match(r"\[([^\]]+)\]", r.get("content") or "")
            if not m:
                continue
            key = (norm(m.group(1)), re.sub(r"\s", "", r.get("article_no") or ""))
            idx[key + ((r.get("metadata_json") or {}).get("ho_path", ""),)].append(i)
            by_article[key].append(i)
        self.by_addr = idx
        self.by_article = by_article

        # 매뉴얼 코드(M01…) → [(행, 공백 제거 본문)]. 규칙 근거가 매뉴얼
        # 발췌(조문이 없음)를 가리키면, 이미 색인된 매뉴얼 청크(M-*, 1,026개)
        # 중 그 발췌 본문을 담은 행을 찾아 붙인다.
        by_manual = collections.defaultdict(list)
        for i, r in enumerate(self.rows):
            if not r["evidence_id"].startswith("M-"):
                continue
            code = (r.get("metadata_json") or {}).get("출처매뉴얼")
            if code:
                by_manual[code].append((i, _wsnorm(r.get("content"))))
        self.by_manual = by_manual

    def _load_vectors(self, np):
        """벡터를 싣기 전에 **무엇으로 만든 것인지 대조한다.**

        전에는 행 수만 맞으면 실었다. 그러면 다른 모델·다른 색인으로 만든
        벡터가 조용히 얹혀 결과만 나빠진다 — 실제로 4096차원 임베딩이
        1024차원 코퍼스에 남아 있던 적이 있다(SCHEMA_ISSUES ⑦).
        `search.py` 는 이미 meta 대조로 막아 뒀는데 여기만 안 막혀 있었다.
        """
        V = np.load(VECS_HO).astype("float32")
        if V.shape[0] != len(self.rows):
            raise RuntimeError(
                f"벡터 {V.shape[0]:,}행 != 색인 {len(self.rows):,}행 — "
                f"{os.path.basename(VECS_HO)} 를 다시 만들어야 한다")
        meta_path = VECS_HO.replace(".f16.npy", ".meta.json")
        if not os.path.exists(meta_path):
            raise RuntimeError(
                f"{os.path.basename(meta_path)} 가 없다. 이 벡터가 어느 모델·어느"
                f" 색인으로 만들어졌는지 알 수 없어 싣지 않는다.")
        meta = json.load(open(meta_path, encoding="utf-8"))
        if int(meta.get("dim", 0)) != V.shape[1]:
            raise RuntimeError(f"차원 불일치: meta {meta.get('dim')} != 파일 {V.shape[1]}")
        want = meta.get("corpus_sha256")
        if want:
            h = hashlib.sha256()
            for r in self.rows:
                h.update(index_text(r)[:1200].encode("utf-8"))
            if h.hexdigest()[:len(want)] != want:
                raise RuntimeError(
                    "색인이 벡터를 만든 뒤에 바뀌었다 — 벡터를 다시 만들어야 한다\n"
                    f"  meta {want} != 지금 {h.hexdigest()[:len(want)]}")
        return V

    def _emb(self):
        if self.EMB is None:
            import torch
            torch.set_num_threads(os.cpu_count() or 4)
            from sentence_transformers import SentenceTransformer
            self.EMB = SentenceTransformer("BAAI/bge-m3")
        return self.EMB

    def hop1(self, chunks, k=20, how="hybrid", allow=None, product=None):
        """광고 청크 → 규칙. 규칙만 본다.

        product 를 주면 상품군이 안 맞는 규칙(예금 광고에 투자 규칙 등)을
        후보에서 제외한다. product_group 이 빈 규칙(상품 공통)은 항상 통과."""
        import numpy as np
        mask = self.is_rule.copy()
        if allow is not None:
            mask &= allow
        if product:
            mask &= np.array([not pg or product in pg for pg in self.product_group])
        ranks = []
        for c in chunks:
            if how in ("bm25", "hybrid"):
                ranks.append(self.bm(c, POOL_K, allow=mask))
            if how in ("vector", "hybrid") and self.V is not None:
                qv = self._emb().encode([c], normalize_embeddings=True
                                        ).astype("float32")[0]
                s = self.V @ qv
                s[~mask] = -1e9
                ranks.append(list(np.argsort(-s)[:POOL_K]))
        merged = rrf(*ranks, top=k) if len(ranks) > 1 else (ranks[0][:k] if ranks else [])
        return merged

    def hop1_opensearch(self, chunks, k=20, how="hybrid", product=None):
        """hop1 과 같은 일을 로컬 흉내가 아니라 OpenSearch(nori)로 한다.
        **다만 이건 리허설 — 수요사(DAP)는 Elasticsearch 만 쓴다
        (`STACK.md`). 최종 타깃은 `hop1_elasticsearch`.** 공용 레포 dev
        환경에 이미 떠 있어 먼저 붙여 본 것.
        질의 임베딩은 로컬 BGE-M3 로 만든다(의도한 kure-v1 임베딩 서비스는
        포트 8001 이 열려는 있는데 응답이 안 와 — Docker Desktop 네트워킹
        문제로 보임, 8/10 확인. 재현되면 거기로 바꾸면 됨)."""
        ranks = []
        for c in chunks:
            if how in ("bm25", "hybrid"):
                ranks.append(_es_bm25(c, POOL_K, "rule", product))
            if how in ("vector", "hybrid"):
                qv = self._emb().encode([c], normalize_embeddings=True
                                        ).astype("float32")[0].tolist()
                ranks.append(_es_knn(qv, POOL_K, "rule", product))
        merged = rrf(*ranks, top=k) if len(ranks) > 1 else (ranks[0][:k] if ranks else [])
        return merged

    def hop1_elasticsearch(self, chunks, k=20, how="hybrid", product=None):
        """**진짜 타깃.** 로컬에 별도로 띄운 real Elasticsearch(+nori,
        `rag/es/`)로 검색한다. 스키마 필터(product_group)는 로컬 배열이
        아니라 term 필터로 진짜 걸러진다."""
        ranks = []
        for c in chunks:
            if how in ("bm25", "hybrid"):
                ranks.append(_real_es_bm25(c, POOL_K, "rule", product))
            if how in ("vector", "hybrid"):
                qv = self._emb().encode([c], normalize_embeddings=True
                                        ).astype("float32")[0].tolist()
                ranks.append(_real_es_knn(qv, POOL_K, "rule", product))
        merged = rrf(*ranks, top=k) if len(ranks) > 1 else (ranks[0][:k] if ranks else [])
        return merged

    def hop2(self, rule_rows):
        """규칙 근거 → 조문 행.

        **`근거` 필드(match_rules.py 가 이미 만들어 둔 것)를 그대로 쓴다.**
        원천은 엑셀(중요_NH_광고심의_규칙리스트_v3.xlsx)의 근거상세 열이고,
        조문지도 246행과 대조까지 마친 상태 — 규칙 1,744건 전부(근거상세_원문이
        "-" 인 375건 포함) 이미 채워져 있다. 전엔 이걸 안 보고 근거상세_원문을
        직접 정규식으로 재파싱해 397건만 붙었다(이미 있는 걸 다시 만들다 못
        미친 것).

        `근거`는 조 단위(항·호·목 없음)라, `근거상세_원문`에서 항·호·목을
        더 뽑을 수 있으면(`parse_basis`) 같은 (규정,조) 안에서만 좁힌다 —
        전체를 대표 행으로 메우는 시도는 R@5 를 떨어뜨려(33%→27%, 8/10 실측)
        폐기했으므로, 좁히기 실패 시엔 그 조 전체 행을 붙인다(이번엔 「없던
        것」이 아니라 「원래도 있던 것」을 못 좁힌 경우라 값어치가 다르다).
        """
        out, seen = [], set()
        for i in rule_rows:
            r = self.rows[i]
            raw = (r.get("metadata_json") or {}).get("근거상세_원문") or ""
            narrow = parse_basis(raw)
            addrs = []
            seen_addr = set()
            for g in (r.get("근거") or []):
                if g.get("유형") == "발췌":
                    # 조문이 아니라 매뉴얼 발췌 — 이미 매뉴얼을 색인해 뒀으니
                    # (add_manuals.py, M-* 1,026개) 「없는 걸 찾지」 말고 그
                    # 발췌 본문을 담은 매뉴얼 청크를 찾아 그대로 붙인다.
                    m = re.match(r"(M\d+)", g.get("article_no") or "")
                    snippet = _wsnorm(g.get("본문"))[:20]
                    if not m or not snippet:
                        continue
                    for j, content in self.by_manual.get(m.group(1), []):
                        if snippet in content and j not in seen:
                            seen.add(j)
                            out.append((j, r["evidence_id"], "매뉴얼 발췌"))
                    continue
                if g.get("유형") != "조문":
                    continue
                name = norm(g.get("규정") or "")
                jo = re.sub(r"\s", "", g.get("article_no") or "")
                if not name or not jo or (name, jo) in seen_addr:
                    continue
                seen_addr.add((name, jo))
                addrs.append((name, jo))
            for name, jo in addrs:
                got, label = None, "조 전체"
                for pname, pjo, ppath in narrow:
                    if norm(pname) != name or re.sub(r"\s", "", pjo) != jo or not ppath:
                        continue
                    for p in (ppath, " ".join(ppath.split()[:-1])):
                        got = self.by_addr.get((name, jo, p))
                        if got:
                            label = p
                            break
                    if got:
                        break
                if not got:
                    got = self.by_article.get((name, jo))
                if got:
                    for j in got:
                        if j not in seen:
                            seen.add(j)
                            out.append((j, r["evidence_id"], label))
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ad")
    ap.add_argument("--measure", action="store_true")
    ap.add_argument("--how", default="hybrid")
    ap.add_argument("--rerank", action="store_true",
                    help="hop1 이 뽑은 규칙을 리랭커로 다시 줄 세운다")
    ap.add_argument("--no-product", action="store_true",
                    help="상품군 필터 끄기(비교용)")
    ap.add_argument("--backend", choices=("local", "opensearch", "elasticsearch"),
                    default="local",
                    help="local=로컬 바이그램 BM25+벡터(문자열만 봄) · "
                         "opensearch=리허설(공용 레포 dev 환경, 이미 떠 있음) · "
                         "elasticsearch=진짜 타깃(수요사 DAP), 로컬에 별도 기동 필요")
    ap.add_argument("--es-setup", action="store_true",
                    help="선택한 backend 의 색인(evidences_ho) 새로 만들어 35,961행 적재")
    ap.add_argument("-k", type=int, nargs="*", default=[1, 3, 5, 10, 20])
    a = ap.parse_args()

    if a.es_setup:
        if a.backend == "elasticsearch":
            setup_real_es_ho()
        else:
            setup_es_ho()
        return

    th = TwoHop2()
    if a.rerank:
        from sentence_transformers import CrossEncoder
        th.RR = CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=512)
    else:
        th.RR = None
    print(f"색인 {len(th.rows):,} · 규칙 {th.n_rules:,} · "
          f"벡터 {'있음' if th.V is not None else '없음'}")

    ads = {}
    for l in open(os.path.join(RAG, "ads_parsed.jsonl"), encoding="utf-8"):
        x = json.loads(l)
        ads.setdefault(x["광고id"], x)

    def chunks_of(aid, n=14):
        cs = [c["text"] for c in (ads[aid].get("청크") or [])
              if len(c["text"]) >= 15]
        cs.sort(key=len, reverse=True)
        return cs[:n] or [ads[aid]["text"][:500]]

    def search1(chunks, k, how, product):
        if a.backend == "elasticsearch":
            return th.hop1_elasticsearch(chunks, k, how, product=product)
        if a.backend == "opensearch":
            return th.hop1_opensearch(chunks, k, how, product=product)
        return th.hop1(chunks, k, how, product=product)

    if a.ad:
        product = None if a.no_product else product_of(a.ad)
        rr = search1(chunks_of(a.ad), 10, a.how, product)
        arts = th.hop2(rr)
        print(f"\n== {a.ad} ==\n걸린 규칙:")
        for n, i in enumerate(rr, 1):
            print(f"  {n:2d}. {th.rows[i]['evidence_id']} "
                  f"{th.rows[i].get('title','')[:54]}")
        print("\n근거 조문(근거 주소를 따라감):")
        for j, rid, p in arts[:10]:
            r = th.rows[j]
            print(f"  [{p:8s}] {r.get('article_no') or '':10s} "
                  f"{(r.get('content') or '')[:56].replace(NL,' | ')}   ← {rid}")

    if a.measure:
        gold = [g for g in json.load(open(os.path.join(RAG, "ad_gold4.json"),
                                          encoding="utf-8"))["건"]
                if g.get("정답행") and g["광고id"] in ads]
        KL = a.k
        print(f"\n정답 {len(gold)}건 (ad_gold4 · 호 단위 주소)")
        print(f"{'검색':10s} " + "  ".join(f"R@{k:<4d}" for k in KL))
        for how in ("bm25", "vector", "hybrid"):
            if a.backend == "local" and how != "bm25" and th.V is None:
                continue
            hit = {k: 0 for k in KL}
            n = 0
            t0 = time.time()
            for g in gold:
                ans = set(g["정답행"])
                n += 1
                # 리랭커는 **hop1 이 뽑은 규칙 후보를 다시 줄 세운다.** 조문이
                # 아니라 규칙을 재정렬하는 것이 요점이다 — 어차피 조문은 규칙
                # 링크로 따라가므로, 규칙 순서가 곧 조문 순서다.
                product = None if a.no_product else product_of(g["광고id"])
                cand = search1(chunks_of(g["광고id"]),
                               60 if th.RR else max(KL), how, product)
                if th.RR:
                    # **광고 전문을 통째로 넘기지 않는다.** 코랩판(_build_
                    # colab_final.py 8번 셀)이 이렇게 해서 R@5 를 3분의 1로
                    # 떨어뜨렸다(HANDOFF §2) — 광고 청크마다 따로 재정렬해
                    # 후보별 최고점만 취한다(어느 한 대목만 맞아도 그 후보는
                    # 살아야 하므로 평균이 아니라 최댓값).
                    rq_chunks = chunks_of(g["광고id"])
                    pairs = [[c, index_text(th.rows[i])[:600]]
                             for i in cand for c in rq_chunks]
                    scores = th.RR.predict(pairs)
                    best = {}
                    p = 0
                    for i in cand:
                        for _ in rq_chunks:
                            best[i] = max(best.get(i, -1e9), scores[p])
                            p += 1
                    cand = sorted(cand, key=lambda i: -best[i])[:max(KL)]
                rr = cand
                # **rank = 규칙 순위, 행 개수 아님.** 한 규칙이 조문 하나를
                # 못 좁혀 여러 행(항·호·목)을 통째로 낸다고 그 규칙이 늦게
                # 잡힌 걸로 치면 안 된다 — 뒤 규칙의 정답이 그만큼 밀려
                # R@k 가 떨어진다(실측: 상품군 없이 커버리지만 늘렸더니
                # hybrid R@5 33%→7% 로 떨어짐, 8/10). 규칙 단위로 먼저
                # 맞는 게 나오는 순위를 센다.
                pos = None
                for rank, i in enumerate(rr, 1):
                    if any(j in ans for j, _, _ in th.hop2([i])):
                        pos = rank
                        break
                for k in KL:
                    if pos and pos <= k:
                        hit[k] += 1
            print(f"{how:10s} " +
                  "  ".join(f"{hit[k]/max(n,1)*100:5.1f}%" for k in KL) +
                  f"  {time.time()-t0:4.0f}초 n={n}")
        print("\n※ 광고를 조문에 바로 던진 18조합은 전부 0.0% 였다.")


if __name__ == "__main__":
    main()
