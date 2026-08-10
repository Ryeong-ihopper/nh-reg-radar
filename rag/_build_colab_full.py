# -*- coding: utf-8 -*-
"""rag/full_colab.ipynb — **전체 파이프라인을 진짜로 한 번에 돌린다.**

지금까지 노트북은 조각조각이었고, 납품 경로(`pipeline.py`)는 셋 다 가짜였다.

    검색     순수 파이썬 BM25 + numpy 전수내적   ← 수요사는 Elasticsearch 를 쓴다
    리랭커   FlagEmbedding (설치된 적 없음)      ← 항상 조용히 건너뜀
    판정     목("판정 못 함")                    ← 산출물엔 정상처럼 저장됨

이 노트북은 넷을 **전부 실물로** 돌린다. 코랩 GPU 환경은 수요사 H200 과
구조가 같다(모델을 GPU 에 직접 올리고, ES 를 옆에 띄운다).

    검색     Elasticsearch 8.14 + analysis-nori + dense_vector kNN
    임베딩   BAAI/bge-m3            (DAP 가 주는 둘 중 하나)
    리랭커   BAAI/bge-reranker-v2-m3 (수요사 지정)
    판정     google/gemma-4-12B-it   (GPU 메모리 보고 자동 선택)

구조는 측정에서 되는 쪽만 쓴다.

    광고 파서청크 → ① 규칙 검색(ES) → ② 리랭킹(BGE) → ③ 근거 조문(링크) → ④ 판정(Gemma)

    「직접」(광고→조문 바로) 은 12조합 전부 0.0% 였다. 안 쓴다.
    질의 생성 LLM 도 안 쓴다 — 파서 청크를 그대로 던지는 쪽이 낫다.

  올릴 것   rule_index_ho.jsonl · ads_parsed.jsonl · ad_gold4.json
            checks_예금.json · checks_대출.json
  받을 것   full_report.md · full_result.json

  python rag/_build_colab_full.py
"""
import os
import json

MD, PY = "markdown", "code"
CELLS = []


def _merge_source():
    """`rag/merge.py` 의 두 함수를 원문 그대로 읽어 온다.

    노트북에 손으로 옮겨 적으면 반드시 갈라진다 — 이 저장소는 이미
    `twohop2.py` 와 노트북이 서로 다른 RRF 를 쓰다가 hybrid 숫자가 안 맞아
    한참을 헤맸다. 한 곳에서만 고치도록 파일에서 읽는다.
    """
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "merge.py")
    src = open(p, encoding="utf-8").read()
    return src.split("# MERGE_BEGIN")[1].split("# MERGE_END")[0].strip("\n")


_MERGE_SRC = _merge_source()


def add(kind, text):
    CELLS.append((kind, text.strip("\n")))


add(MD, """
# 전체 파이프라인 — 실물 한 번에

## 무엇이 달라졌나

| | 전 | 지금 |
|---|---|---|
| 검색 | 순수 파이썬 BM25 + numpy | **Elasticsearch 8.14 + nori + kNN** |
| 리랭커 | `FlagEmbedding` — 설치된 적 없어 **항상 건너뜀** | **BAAI/bge-reranker-v2-m3** |
| 판정 | 목("판정 못 함")이 정상 산출물로 저장됨 | **Gemma** (GPU) |
| 구조 | 직접(광고→조문) — 측정 **0.0%** | **2-hop**(광고→규칙→조문) — R@5 60% |
| 질의 | LLM 목(정규식 14개) | **광고 파서청크 원문** |
| 규칙 | `checks.json` 7건(목데이터 과적합) | **상품군별 837건** |

## 준비

| | |
|---|---|
| 런타임 | **GPU** (T4 면 Gemma 는 E4B 로 내려감 · A100 이면 12B) |
| 올릴 것 | `rule_index_ho.jsonl` · `ads_parsed.jsonl` · `ad_gold4.json` · `checks_예금.json` · `checks_대출.json` |
| 받을 것 | `full_report.md` · `full_result.json` |
| 소요 | ES 기동 3분 + 임베딩 10분 + 판정 10~30분 |
""")

add(MD, "## 1. 환경")
add(PY, """
!nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
!pip -q install -U sentence-transformers accelerate bitsandbytes 2>&1 | tail -1
""")

add(MD, """
## 2. 파일 올리기
""")
add(PY, """
import os
from google.colab import files
NEED = ["rule_index_ho.jsonl", "ads_parsed.jsonl", "ad_gold4.json",
        "checks_예금.json", "checks_대출.json"]
if [n for n in NEED if not os.path.exists(n)]:
    files.upload()
for n in NEED:
    print(f"{n:24s} {os.path.getsize(n)/1e6:7.1f}MB" if os.path.exists(n)
          else f"{n:24s} 없음  ← 이게 없으면 그 단계는 못 돈다")
""")

add(MD, """
## 3. Elasticsearch 띄우기 (nori + kNN)

**수요사가 쓰는 그 엔진이다.** 로컬 파이썬 BM25 로 잰 숫자는 토크나이저가 달라
그대로 안 옮겨진다.

- ES 는 root 실행을 거부하고 코랩은 root 다 → `esuser` 를 만들어 그걸로 띄운다
- tar ~600MB, 띄우는 데까지 3분 안팎
""")
add(PY, r"""
import os, glob, json, subprocess, time, urllib.request

ES_VER = "8.14.3"
ES_DIR = f"/content/elasticsearch-{ES_VER}"
ES_LOG = "/content/es_start.log"
TMPDIR = "/content/es_tmp"

def es_up():
    try:
        with urllib.request.urlopen("http://127.0.0.1:9200/", timeout=2) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None

if not os.path.exists(ES_DIR):
    print("내려받는 중 (~600MB)…")
    url = (f"https://artifacts.elastic.co/downloads/elasticsearch/"
           f"elasticsearch-{ES_VER}-linux-x86_64.tar.gz")
    subprocess.run(f"curl -sSL {url} | tar xz -C /content", shell=True, check=True)
    subprocess.run(f"{ES_DIR}/bin/elasticsearch-plugin install --batch analysis-nori",
                   shell=True, check=True)
    subprocess.run("id -u esuser >/dev/null 2>&1 || useradd -m esuser",
                   shell=True, check=True)

# **설정은 매번 다시 쓴다.** 내려받기 블록 안에만 두면, 설정을 고쳐도 이미
# 받아 둔 세션에서는 반영이 안 된다(고쳤는데 그대로 죽는다).
#
# **지울 때는 「키」로 지운다.** 마커 기준으로만 잘라내면, 마커 없이 append 된
# 옛 줄이 남아 `Duplicate field 'discovery.type'` 로 ES 가 아예 안 뜬다.
SETTINGS = {
    "discovery.type": "single-node",
    "xpack.security.enabled": "false",
    "xpack.security.http.ssl.enabled": "false",
    "network.host": "127.0.0.1",
    "bootstrap.memory_lock": "false",
    # **ML 을 끈다.** 코랩에서 ES 가 죽던 진짜 이유다 — ML 플러그인이 기동 중
    # OsProbe 로 cgroup CPU 통계를 읽는데, 코랩은 `jupyter-children` cgroup
    # 안이라 자바 SecurityManager 가 그 파일 읽기를 막는다.
    #   AccessControlException: /sys/fs/cgroup/../../jupyter-children/cpu.stat
    # 우리는 ML 을 안 쓴다(BM25·kNN 만 쓴다).
    "xpack.ml.enabled": "false",
    "xpack.monitoring.collection.enabled": "false",
}
MARK = "# --- 노트북이 넣은 설정 ---"
YML = f"{ES_DIR}/config/elasticsearch.yml"
keep = [l for l in open(YML, encoding="utf-8").read().splitlines()
        if l.strip().split(":")[0].strip() not in SETTINGS and not l.startswith(MARK)]
open(YML, "w", encoding="utf-8").write(
    "\n".join(keep).rstrip() + "\n" + MARK + "\n"
    + "\n".join(f"{k}: {v}" for k, v in SETTINGS.items()) + "\n")
print("설정:", ", ".join(SETTINGS))

# **소유권은 매번 맞춘다.** 셀을 다시 돌릴 때 data/logs 가 root 로 새로 생겨
# 있으면 esuser 가 못 써서 조용히 안 뜬다.
subprocess.run(f"mkdir -p {ES_DIR}/data {ES_DIR}/logs {TMPDIR}", shell=True, check=True)
subprocess.run(f"chown -R esuser:esuser {ES_DIR} {TMPDIR}", shell=True, check=True)
subprocess.run("sysctl -w vm.max_map_count=262144 >/dev/null 2>&1 || true", shell=True)

info = es_up()
if info:
    print("이미 떠 있다:", info["version"]["number"])
else:
    # **`-d`(데몬)로 띄우지 않는다.** 그러면 기동 실패 원인이 로그에만 남고
    # 셀에는 「exit status 1」만 뜬다. nohup 으로 띄우고 출력을 파일로 받아,
    # 안 뜨면 그 파일을 그대로 보여 준다.
    # `-Des.cgroups.hierarchy.override=/` — cgroup 경로를 「/」로 못 박는다.
    # 코랩의 cgroup 이름(`../../jupyter-children`)을 그대로 따라가면 못 읽는다.
    subprocess.run(
        f'nohup sudo -u esuser env '
        f'ES_JAVA_OPTS="-Xms2g -Xmx2g -Des.cgroups.hierarchy.override=/" '
        f'ES_TMPDIR={TMPDIR} {ES_DIR}/bin/elasticsearch > {ES_LOG} 2>&1 &',
        shell=True)
    for i in range(100):                       # 최대 5분
        info = es_up()
        if info:
            print("ES 기동:", info["version"]["number"])
            break
        time.sleep(3)
    else:
        print("=== 기동 실패 · 시작 로그 ===")
        if os.path.exists(ES_LOG):
            print(open(ES_LOG, encoding="utf-8", errors="replace").read()[-3000:])
        for f in glob.glob(f"{ES_DIR}/logs/*.log"):
            print(f"=== {f} ===")
            print(open(f, encoding="utf-8", errors="replace").read()[-2000:])
        raise RuntimeError("ES 가 5분 안에 안 떴다 — 위 로그를 볼 것")
""")

add(MD, """
## 4. 공통 함수

`rag/twohop2.py` 와 **글자 하나까지 같게** 둔다. 여기가 다르면 로컬 숫자와 견줄 수 없다.
""")
add(PY, r"""
import json, re, math, time, collections
import numpy as np
import urllib.request

NL = chr(10)
RRF_K = 60
POOL_K = 300          # 50 이면 상품군 필터가 정답을 밀어낸다(로컬 실측)
ES = "http://127.0.0.1:9200"
INDEX = "evidences_ho"

rows = [json.loads(l) for l in open("rule_index_ho.jsonl", encoding="utf-8")]
n_rules = sum(1 for r in rows if r["evidence_id"].startswith("R-"))
print(f"색인 {len(rows):,} = 규칙 {n_rules:,} + 조문·매뉴얼 {len(rows)-n_rules:,}")

def index_text(r):
    return f"{r.get('title','')} {r.get('article_no') or ''} {r.get('content','')}"

def norm(s):    return re.sub(r"[\s·ㆍ]", "", str(s or ""))
def wsnorm(s):  return re.sub(r"\s+", "", str(s or ""))

def req(method, path, body=None):
    data = body
    if isinstance(body, (dict, list)):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    elif isinstance(body, str):
        data = body.encode("utf-8")
    r = urllib.request.Request(f"{ES}{path}", data=data, method=method,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=120) as res:
        return json.loads(res.read().decode("utf-8"))

def rrf(*rankings, top=50):
    # 점수가 아니라 **순위**를 더한다. BM25 점수와 코사인은 자릿수가 달라
    # 그대로 더하면 한쪽이 묻힌다.
    sc = collections.defaultdict(float)
    for rank in rankings:
        for r, i in enumerate(rank, 1):
            sc[i] += 1.0/(RRF_K+r)
    return [i for i, _ in sorted(sc.items(), key=lambda x: -x[1])[:top]]

PRODUCT_MAP = {"예금성": "DEPOSIT", "대출성": "LOAN",
               "투자성": "INVESTMENT", "보장성": "INSURANCE"}
def product_of(aid):
    for kw, code in PRODUCT_MAP.items():
        if kw in str(aid or ""):
            return code
    return None
""")

add(MD, """
## 5. 임베딩 (BGE-M3, GPU)

색인을 새로 임베딩한다. **미리 만든 벡터를 올리는 것보다 안전하다** — 벡터가
색인과 어긋나면 오류가 안 나고 조용히 엉뚱한 결과가 나온다.
""")
add(PY, """
from sentence_transformers import SentenceTransformer
EMB = SentenceTransformer("BAAI/bge-m3")

t0 = time.time()
V = EMB.encode([index_text(r)[:1200] for r in rows], batch_size=64,
               normalize_embeddings=True, show_progress_bar=True).astype("float32")
print(f"{V.shape} · {time.time()-t0:.0f}초")
assert abs(np.linalg.norm(V, axis=1).mean() - 1.0) < 1e-3, "정규화가 안 됐다"
""")

add(MD, """
## 6. ES 색인 적재

**스키마 필드를 그대로 넣는다** — `product_group` 을 파이썬 리스트로 후처리하지
않고 ES term 필터로 거른다. 이게 수요사 환경에서 도는 모양이다.
""")
add(PY, r"""
MAPPING = {
  "settings": {"analysis": {
      "tokenizer": {"korean": {"type": "nori_tokenizer", "decompound_mode": "mixed"}},
      "analyzer": {"korean": {"type": "custom", "tokenizer": "korean",
                              "filter": ["lowercase"]}}}},
  "mappings": {"properties": {
      "search_text": {"type": "text", "analyzer": "korean"},
      "title":       {"type": "text", "analyzer": "korean"},
      "article_no":  {"type": "text", "analyzer": "korean",
                      "fields": {"keyword": {"type": "keyword"}}},
      "evidence_id": {"type": "keyword"},
      "kind":        {"type": "keyword"},
      "product_group": {"type": "keyword"},
      "medium":      {"type": "keyword"},
      "row":         {"type": "integer"},
      "vector":      {"type": "dense_vector", "dims": 1024,
                      "index": True, "similarity": "cosine"}}}}

KIND = {"R": "rule", "C": "article", "M": "manual"}
try:    req("DELETE", f"/{INDEX}")
except Exception: pass
req("PUT", f"/{INDEX}", MAPPING)

def bulk(lines):
    out = req("POST", "/_bulk", "\n".join(lines) + "\n")
    if out.get("errors"):
        bad = [x for x in out["items"] if x.get("index", {}).get("error")][:2]
        raise RuntimeError(json.dumps(bad, ensure_ascii=False)[:400])

lines, t0 = [], time.time()
for i, r in enumerate(rows):
    doc = {"search_text": index_text(r), "title": r.get("title", ""),
           "article_no": r.get("article_no") or "",
           "evidence_id": r["evidence_id"], "kind": KIND.get(r["evidence_id"][0], "?"),
           "product_group": r.get("product_group") or [],
           "medium": r.get("medium") or [], "row": i, "vector": V[i].tolist()}
    lines += [json.dumps({"index": {"_index": INDEX, "_id": r["evidence_id"]}}),
              json.dumps(doc, ensure_ascii=False)]
    if len(lines) >= 1000:
        bulk(lines); lines = []
        print(f"  {i+1:,}/{len(rows):,} ({time.time()-t0:.0f}초)", end="\r")
if lines: bulk(lines)
req("POST", f"/{INDEX}/_refresh")
print(f"\n적재 {req('GET', f'/{INDEX}/_count')['count']:,}건 ({time.time()-t0:.0f}초)")
""")

add(MD, """
## 7. 검색 — hop1(ES) · hop2(링크)

**hop2 에는 검색이 없다.** 규칙의 `근거` 필드가 가리키는 주소로 조문을 직접
꺼낸다. `근거` 는 규칙리스트 엑셀에서 온 것이고 조문지도와 대조까지 마친 것이라,
정규식으로 다시 파싱하던 옛 방식(355건)보다 훨씬 많이 이어진다(**1,518건**).
""")
add(PY, r"""
ALIAS = {"은행 광고심의 기준": "은행 광고심의 기준 및 세칙",
         "은행 광고심의기준": "은행 광고심의 기준 및 세칙",
         "은행 광고심의 기준 세칙": "은행 광고심의 기준 및 세칙",
         "금융소비자보호법": "금융소비자 보호에 관한 법률",
         "금소법": "금융소비자 보호에 관한 법률",
         "여신금융상품 광고에 관한 세부지침": "여신전문금융회사 등의 광고에 관한 규정 세부지침",
         "증발공규정": "증권의 발행 및 공시 등에 관한 규정",
         "협회 표준내부통제기준": "금융투자회사 표준내부통제기준",
         "인공지능기본법": "인공지능 발전과 신뢰 기반 조성 등에 관한 기본법",
         "약관법": "약관의 규제에 관한 법률",
         "금융소비자 보호에 관한 금융소비자 보호에 관한 감독규정": "금융소비자 보호에 관한 감독규정"}

_REF = re.compile(
    r"(?P<name>[가-힣·\s]+?)\s*"
    r"제\s*(?P<jo>\d+(?:-\d+)?)\s*조(?:\s*의\s*(?P<ji>\d+))?"
    r"(?:\s*제\s*(?P<hang>\d+)\s*항)?"
    r"(?:\s*제?\s*(?P<ho>\d+)\s*호)?"
    r"(?:\s*(?P<mok>[가-힣])\s*목)?")

def parse_basis(text):
    out = []
    for part in re.split(r"[,\n;]", str(text or "")):
        m = _REF.search(part)
        if not m: continue
        nm = (m.group("name") or "").strip(" ·,")
        nm = ALIAS.get(nm, nm)
        if not nm: continue
        jo = f"제{m.group('jo')}조" + (f"의{m.group('ji')}" if m.group("ji") else "")
        bits = [x for x in (m.group("ho"), m.group("mok")) if x]
        out.append((nm, jo, " ".join(bits)))
    return out

BY_ADDR, BY_ARTICLE, BY_MANUAL = (collections.defaultdict(list),
                                  collections.defaultdict(list),
                                  collections.defaultdict(list))
for i, r in enumerate(rows):
    eid = r["evidence_id"]
    if eid.startswith("R-"): continue
    if eid.startswith("M-"):
        code = (r.get("metadata_json") or {}).get("출처매뉴얼")
        if code: BY_MANUAL[code].append((i, wsnorm(r.get("content"))))
        continue
    m = re.match(r"\[([^\]]+)\]", r.get("content") or "")
    if m:
        key = (norm(m.group(1)), re.sub(r"\s", "", r.get("article_no") or ""))
        BY_ADDR[key + ((r.get("metadata_json") or {}).get("ho_path", ""),)].append(i)
        BY_ARTICLE[key].append(i)

def hop2(rule_rows):
    out, seen = [], set()
    for i in rule_rows:
        r = rows[i]
        narrow = parse_basis((r.get("metadata_json") or {}).get("근거상세_원문") or "")
        addrs, seen_addr = [], set()
        for g in (r.get("근거") or []):
            if g.get("유형") == "발췌":
                mm = re.match(r"(M\d+)", g.get("article_no") or "")
                snip = wsnorm(g.get("본문"))[:20]
                if not mm or not snip: continue
                for j, content in BY_MANUAL.get(mm.group(1), []):
                    if snip in content and j not in seen:
                        seen.add(j); out.append((j, r["evidence_id"], "매뉴얼 발췌"))
                continue
            if g.get("유형") != "조문": continue
            nm, jo = norm(g.get("규정") or ""), re.sub(r"\s", "", g.get("article_no") or "")
            if nm and jo and (nm, jo) not in seen_addr:
                seen_addr.add((nm, jo)); addrs.append((nm, jo))
        for nm, jo in addrs:
            got, label = None, "조 전체"
            for pn, pj, pp in narrow:
                if norm(pn) != nm or re.sub(r"\s", "", pj) != jo or not pp: continue
                for p in (pp, " ".join(pp.split()[:-1])):
                    got = BY_ADDR.get((nm, jo, p))
                    if got: label = p; break
                if got: break
            if not got: got = BY_ARTICLE.get((nm, jo))
            for j in (got or []):
                if j not in seen:
                    seen.add(j); out.append((j, r["evidence_id"], label))
    return out

def es_filter(kind, product):
    f = [{"term": {"kind": kind}}]
    if product:
        f.append({"bool": {"should": [
            {"term": {"product_group": product}},
            {"bool": {"must_not": {"exists": {"field": "product_group"}}}}]}})
    return f

def hop1(queries, k=30, how="vector", product=None):
    ranks = []
    for q in queries:
        if how in ("bm25", "hybrid"):
            body = {"size": POOL_K, "_source": ["row"],
                    "query": {"bool": {"must": {"match": {"search_text": q}},
                                       "filter": es_filter("rule", product)}}}
            ranks.append([h["_source"]["row"]
                          for h in req("POST", f"/{INDEX}/_search", body)["hits"]["hits"]])
        if how in ("vector", "hybrid"):
            qv = EMB.encode([q], normalize_embeddings=True).astype("float32")[0].tolist()
            body = {"size": POOL_K, "_source": ["row"],
                    "knn": {"field": "vector", "query_vector": qv, "k": POOL_K,
                            "num_candidates": POOL_K*3,
                            "filter": {"bool": {"filter": es_filter("rule", product)}}}}
            ranks.append([h["_source"]["row"]
                          for h in req("POST", f"/{INDEX}/_search", body)["hits"]["hits"]])
    return rrf(*ranks, top=k) if len(ranks) > 1 else (ranks[0][:k] if ranks else [])

linked = sum(1 for i, r in enumerate(rows)
             if r["evidence_id"].startswith("R-") and hop2([i]))
print(f"조문·매뉴얼에 이어진 규칙 {linked:,}/{n_rules:,}건")
""")

add(MD, """
## 8. 리랭커 (BGE-reranker-v2-m3)

**광고 전문을 넘기지 않는다.** 전에 전문 1,000자를 통째로 넘겨 R@5 를 3분의 1로
떨어뜨린 적이 있다(「광고 전문은 질의로 안 쓴다」고 정해 놓고 어겼다).
청크마다 재정렬해 후보별 **최고점**을 쓴다 — 한 대목만 걸려도 그 규칙은 살아야 한다.
""")
add(PY, r"""
from sentence_transformers import CrossEncoder
RR = CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=512)

def rerank(queries, cand, k=5):
    if not cand: return []
    pairs = [[q, index_text(rows[i])[:600]] for i in cand for q in queries]
    sc = RR.predict(pairs)
    best, p = {}, 0
    for i in cand:
        for _ in queries:
            best[i] = max(best.get(i, -1e9), float(sc[p])); p += 1
    return sorted(cand, key=lambda i: -best[i])[:k]

print("리랭커 준비 완료")
""")

add(MD, """
## 9. Gemma (판정)
""")
add(PY, r"""
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

free = torch.cuda.get_device_properties(0).total_memory/1e9 if torch.cuda.is_available() else 0
gname = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
# 12B bf16 을 먼저 본다 — 31B 4bit 는 한 건에 20~30분이라 못 쓴다.
if free >= 26:   MODEL, FOURBIT = "google/gemma-4-12B-it", False
elif free >= 14: MODEL, FOURBIT = "google/gemma-4-12B-it", True
else:            MODEL, FOURBIT = "google/gemma-4-E4B-it", False
print(f"{gname} {free:.0f}GB → {MODEL} ({'4bit' if FOURBIT else 'bf16'})")

kw = dict(device_map="auto")
if FOURBIT:
    kw["quantization_config"] = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True)
else:
    kw["torch_dtype"] = torch.bfloat16

tok = AutoTokenizer.from_pretrained(MODEL)
gemma = AutoModelForCausalLM.from_pretrained(MODEL, **kw); gemma.eval()
print(f"{MODEL} · {gemma.get_memory_footprint()/1e9:.1f}GB")

def ask(prompt, max_new=2048):
    # return_dict=True 를 명시한다 — 최신 transformers 는 BatchEncoding 을 준다.
    enc = tok.apply_chat_template([{"role": "user", "content": prompt}],
                                  add_generation_prompt=True, return_dict=True,
                                  return_tensors="pt").to(gemma.device)
    with torch.no_grad():
        out = gemma.generate(**enc, max_new_tokens=max_new, do_sample=False,
                             pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][enc["input_ids"].shape[-1]:], skip_special_tokens=True)

# 모델 응답에서 JSON 을 꺼낸다. ```json 울타리와 앞뒤 군말을 걷어낸다.
#
# **p[:1] in "{[" 로 쓰면 안 된다** — 빈 문자열은 모든 문자열의 부분문자열이라
# ("" in "{[") 가 True 다. 울타리를 split 하면 첫 조각이 빈 문자열인데 그게
# 걸려서 s 가 빈 문자열이 되고, 판정이 전부
# `Expecting value: line 1 column 1 (char 0)` 로 죽는다(실측).
def as_json(text):
    s = (text or "").strip()
    if "```" in s:
        for p in s.split("```"):
            p = p.strip()
            if p.startswith("json"):
                p = p[4:].strip()
            if p.startswith("{") or p.startswith("["):
                s = p
                break
    starts = [x for x in (s.find("{"), s.find("[")) if x >= 0]
    i, j = (min(starts) if starts else -1), max(s.rfind("}"), s.rfind("]"))
    if i >= 0 and j > i:
        s = s[i:j+1]
    if not s.strip():
        raise ValueError(f"모델 응답에서 JSON 을 못 찾음: {(text or '')[:200]!r}")
    return json.loads(s)

print(ask("한 문장으로 자기소개해 주세요.")[:100])
""")

add(MD, """
## 10. 광고 · 규칙 읽기
""")
add(PY, r"""
ads = {}
for l in open("ads_parsed.jsonl", encoding="utf-8"):
    x = json.loads(l); ads.setdefault(x["광고id"], x)
gold = {g["광고id"]: g for g in json.load(open("ad_gold4.json", encoding="utf-8"))["건"]
        if g.get("정답행")}

CHECKS = []
for f in ("checks_예금.json", "checks_대출.json"):
    if os.path.exists(f):
        CHECKS += json.load(open(f, encoding="utf-8"))["checks"]
print(f"광고 {len(ads)}건 · 정답 {len(gold)}건 · 판정규칙 {len(CHECKS)}건 "
      f"{collections.Counter(c['kind'] for c in CHECKS)}")

def chunks_of(aid, n=14):
    cs = [c["text"] for c in (ads[aid].get("청크") or []) if len(c["text"]) >= 15]
    cs.sort(key=len, reverse=True)
    return cs[:n] or [ads[aid]["text"][:500]]
""")

add(MD, """
## 11. 검색 성능 — 정답 15건

로컬(`rag/twohop2.py --backend elasticsearch`)과 **같은 알고리즘**이다. 숫자가
크게 갈리면 둘 중 하나가 틀린 것이니 먼저 그걸 찾아야 한다.
""")
add(PY, r"""
KL = [1, 3, 5, 10, 20]
RETR = []
for how in ("bm25", "vector", "hybrid"):
    for use_rr in (False, True):
        hit = {k: 0 for k in KL}; n = 0; t0 = time.time()
        for aid, g in gold.items():
            if aid not in ads: continue
            ans = set(g["정답행"]); n += 1
            qs = chunks_of(aid)
            cand = hop1(qs, 60 if use_rr else max(KL), how, product_of(aid))
            if use_rr: cand = rerank(qs, cand, max(KL))
            pos = next((r for r, i in enumerate(cand[:max(KL)], 1)
                        if any(j in ans for j, _, _ in hop2([i]))), None)
            for k in KL:
                if pos and pos <= k: hit[k] += 1
        row = {"검색": how, "리랭커": "O" if use_rr else "-", "n": n,
               "초": round(time.time()-t0),
               **{f"R@{k}": round(hit[k]/max(n,1)*100, 1) for k in KL}}
        RETR.append(row)
        print(f"{how:7s} 리랭커{row['리랭커']} " +
              " ".join(f"{row[f'R@{k}']:5.1f}%" for k in KL) + f"  {row['초']:4d}초")
""")

add(MD, """
## 12. 전체 파이프라인 실행 — 광고마다 근거 + 판정

검색·리랭킹·근거·판정을 **끝까지** 돈다. 여기서 나오는 `full_result.json` 이
`review_items` 에 해당하는 진짜 산출물이다(전에는 이 자리가 목이었다).
""")
add(PY, r"""
_JUDGE = """ + '"""' + r"""당신은 금융광고 심의 담당자입니다. 아래 광고문이 제시된 규정에
맞는지 판정하세요.

판정은 셋 중 하나입니다.
- 적합: 규정 위반이 없음
- 부적합: 규정 위반이 있음
- 확인필요: 광고문만으로는 판단할 수 없음

규칙:
- 광고문에 실제로 있는 표현만 근거로 삼을 것. 없는 내용을 지어내지 말 것
- 부적합이면 광고문에서 문제가 된 대목을 그대로 인용할 것

반드시 아래 JSON 으로만 답하세요.
{{"판정": "적합|부적합|확인필요", "사유": "...", "인용": "...",
  "근거": ["evidence_id", ...], "수정제안": "..."}}

규정:
{evidences}

광고문:
{ad}""" + '"""' + r"""

TOP_K = 5
MIN_CHARS = 50      # 이보다 짧으면 광고가 아니라 파싱 실패다
AD_CHARS = 12000    # 광고문을 판정에 넣을 때 자르는 길이
USE_RERANK = False  # 측정에서 두 번 다 손해였다(아래 참고)
# **vector 를 쓴다.** 광고 파싱을 제대로 된 것으로 바꾼 뒤 재측정하니
# vector R@5 60.0% > hybrid 46.7% > bm25 6.7% 였다. 전에는 hybrid 가
# 나아 보였는데, 그건 광고에 같은 문구가 5~7회 중복돼 BM25 점수를
# 떠받치고 있었기 때문이다 — 중복을 걷으니 BM25 가 무너졌다.
HOW = "vector"

# **빈 광고를 걸러낸다.** `2026_001_예금성` 은 이미지 PDF 라 파싱이 안 돼
# 글자수가 0 이다. 그대로 판정에 넣었더니 모델이 아무것도 못 만들어
# 규칙 595건이 전부 실패하고 재시도로 625초를 썼다. OCR 이 붙기 전까지는
# **판정 대상이 아니라고 말하고 건너뛴다**(조용히 빼면 결과가 왜 없는지 모른다).
SKIP = {a: len((v.get("text") or "").strip())
        for a, v in ads.items() if len((v.get("text") or "").strip()) < MIN_CHARS}
if SKIP:
    print(f"※ 텍스트가 없어 건너뛰는 광고 {len(SKIP)}건 (OCR 필요): "
          + ", ".join(f"{a}({n}자)" for a, n in SKIP.items()))

def pick_evidences(top, k=TOP_K, per_rule=2):
    # **규칙 하나가 근거 칸을 독식하지 못하게 한다.** `hop2(top)[:k]` 로 자르면
    # 1등 규칙이 항·호를 10개 뱉을 때 5칸을 혼자 다 먹고, 나머지 4개 규칙은
    # 근거에 아예 못 들어간다(실측: 18건 중 8건이 규칙 1개에서만 나왔다).
    by_rule = {}
    for j, rid, p in hop2(top):
        by_rule.setdefault(rid, []).append((j, rid, p))
    out, seen = [], set()
    for r in range(per_rule):                 # 규칙마다 1개씩 돌아가며
        for rid, lst in by_rule.items():
            if len(out) >= k:
                break
            if r < len(lst) and lst[r][0] not in seen:
                seen.add(lst[r][0])
                out.append(lst[r])
        if len(out) >= k:
            break
    return out[:k]

RESULT = []
t0 = time.time()
for aid, ad in ads.items():
    if aid in SKIP:
        RESULT.append({"광고id": aid, "규칙": [], "근거": [],
                       "판정": {"판정": None, "사유": "광고 텍스트가 없다(OCR 필요)",
                                "_source": "no-text"}})
        continue
    qs = chunks_of(aid)
    cand = hop1(qs, 30, HOW, product_of(aid))
    top = rerank(qs, cand, TOP_K) if USE_RERANK else cand[:TOP_K]
    arts = pick_evidences(top)
    body = "\n\n".join(f"[{rows[j]['evidence_id']}] {rows[j].get('title','')}\n"
                       f"{(rows[j].get('content') or '')[:600]}" for j, _, _ in arts)
    verdict = {"판정": "확인필요", "사유": "검색된 근거가 없습니다.", "_source": "no-evidence"}
    if arts:
        # **4,000자로 자르면 안 된다.** 대출성 광고가 9,000~10,000자라
        # 절반 이상(유의사항·부대비용이 몰린 뒷부분)을 안 보고 판정했다.
        raw = ask(_JUDGE.format(evidences=body, ad=ad["text"][:AD_CHARS]))
        try:
            verdict = as_json(raw)
            verdict["_source"] = "gemma"
        except Exception as e:
            # **모델이 뭐라고 했는지 남긴다.** 안 남기면 파싱이 틀린 건지
            # 모델이 거절한 건지 형식을 어긴 건지 가릴 수가 없다.
            verdict = {"판정": None, "사유": f"판정 파싱 실패: {e}",
                       "_source": "parse-error", "_raw": (raw or "")[:600]}
    RESULT.append({
        "광고id": aid,
        "규칙": [{"rank_no": n, "evidence_id": rows[i]["evidence_id"],
                  "title": rows[i].get("title", "")} for n, i in enumerate(top, 1)],
        "근거": [{"evidence_id": rows[j]["evidence_id"],
                  "article_no": rows[j].get("article_no", ""),
                  "위치": p, "걸린규칙": rid,
                  "title": rows[j].get("title", "")} for j, rid, p in arts],
        "판정": verdict})
    v = verdict.get("판정")
    print(f"{aid:20s} 근거 {len(arts)}건 · 판정 {v or '—'} · {str(verdict.get('사유'))[:50]}")
print(f"\n{len(RESULT)}건 · {time.time()-t0:.0f}초")
""")

add(MD, """
## 13. 규칙 판정 (checks 837건) — LLM 항목 포함

`kind=LLM` 항목은 자연어 기준이라 정규식으로 못 푼다. **묶어서** 묻는다
(한 건씩 부르면 광고 하나에 수백 번이다). 묶음이 깨지면 반으로 쪼개 재시도한다.

**NG 인 것만 답하게 한다.** 전에는 항목마다 OK/NG/해당없음을 다 쓰게 해 놓고
받아서는 NG 만 남기고 버렸다 — 토큰의 9할을 버리면서 광고 하나에 20분이 걸렸다.
어차피 안 쓸 것을 생성시키지 않는다.

**진행을 찍는다.** 무출력으로 20분이 지나면 죽은 것과 구별이 안 된다.
""")
add(PY, r"""
_BATCH = """ + '"""' + r"""당신은 금융광고 심의 담당자입니다. 아래 광고문을 읽고,
점검항목 중 **광고가 어긴 것(NG)만** 골라내세요.

- NG: 요구된 표시가 빠졌거나 잘못됨
- 지킨 항목, 이 광고에 해당 없는 항목은 **답에 넣지 마세요**

규칙:
- 광고문에 실제로 있는 표현만 근거로 삼을 것. 없는 내용을 지어내지 말 것
- 무엇이 빠졌거나 잘못됐는지 한 문장으로 쓸 것

반드시 아래 JSON 배열로만 답하세요. **어긴 것이 없으면 [] 만 쓰세요.**
[{{"id": "...", "사유": "...", "인용": "..."}}]

점검항목:
{items}

광고문:
{ad}""" + '"""' + r"""

PG_KO = {"DEPOSIT": "예금성", "LOAN": "대출성",
         "INVESTMENT": "투자성", "INSURANCE": "보장성"}

MAX_DEPTH = 2      # 20 → 10,10 → 5,5,5,5 까지만. 그 아래로는 안 쪼갠다.
FAILED = []        # 판정을 못 받은 항목 id

def judge_batch(ad_text, items, depth=0):
    if not items: return []
    body = "\n".join(f'- id={c["id"]} : {c.get("criterion") or c["title"]}' for c in items)
    try:
        # NG 만 받으므로 출력이 짧다. 1024 면 넉넉하다.
        got = as_json(ask(_BATCH.format(items=body, ad=ad_text[:6000]), max_new=1024))
        if not isinstance(got, list): raise ValueError("배열이 아님")
    except Exception as e:
        # **깊이를 막는다.** 안 막으면 한 묶음이 1→2→4→8→16 으로 번져
        # 20개짜리가 31번 호출이 된다. 모델이 이 광고에서 계속 형식을 어기면
        # 광고 하나에 몇 시간이 간다(실측: 2번째 광고가 13분 넘게 안 끝남).
        if len(items) == 1 or depth >= MAX_DEPTH:
            # **못 한 것을 「지적 없음」으로 넘기지 않는다.** 그러면 판정 실패가
            # 「위반 없음」으로 보인다.
            FAILED.extend(c["id"] for c in items)
            return []
        h = len(items)//2
        return (judge_batch(ad_text, items[:h], depth+1)
                + judge_batch(ad_text, items[h:], depth+1))
    by = {c["id"]: c for c in items}
    return [{"check_id": g.get("id"), "지적유형": by[str(g["id"])]["verdict_code"],
             "근거규정": by[str(g["id"])]["article_no"], "사유": g.get("사유"),
             "인용": g.get("인용"), "판정근거": "LLM"}
            for g in got if str(g.get("id")) in by]

BATCH = 20
N_ADS = 2          # 전체 18건을 돌리려면 len(ads) 로 바꾼다
RULE_RESULT, RULE_FAILED = {}, {}

TARGETS = [a for a in ads if a not in SKIP][:N_ADS]   # 빈 광고는 뺀다
if SKIP:
    print(f"※ 텍스트 없어 건너뜀: {', '.join(SKIP)}")

for aid in TARGETS:
    pg = PG_KO.get(product_of(aid))
    items = [c for c in CHECKS if c["kind"] == "LLM"
             and (c.get("product_group") in (None, pg))]
    nb = (len(items) + BATCH - 1)//BATCH
    t0, fs = time.time(), []
    FAILED.clear()
    for n, s in enumerate(range(0, len(items), BATCH), 1):
        fs += judge_batch(ads[aid]["text"], items[s:s+BATCH])
        el = time.time()-t0
        print(f"  {aid} {n:3d}/{nb}묶음 · 지적 {len(fs):3d} · 실패 {len(FAILED):3d} · "
              f"{el:5.0f}초 (남은 {el/n*(nb-n):5.0f}초)   ", end="\r", flush=True)
    RULE_RESULT[aid], RULE_FAILED[aid] = fs, list(FAILED)
    print(f"{aid:20s} 항목 {len(items):4d} → 지적 {len(fs):3d}건 "
          f"· 판정실패 {len(FAILED):3d}건 ({time.time()-t0:.0f}초){' '*15}")
    for f in fs[:5]:
        print(f"    [{f['지적유형']}] {str(f['사유'])[:64]}")
""")

add(MD, """
## 14. 두 방향 합치기 — 여기가 핵심이다

    광고 → 조문 (12번)   **쓰면 안 될 것을 썼다**   오기·오표기
    조문 → 광고 (13번)   **써야 할 것을 안 썼다**   누락

정답셋 15건을 지적 사유로 갈라 보면 **누락형이 9건, 오기형이 6건**이다.
누락은 광고에 그 문구가 없으니 광고에서 뽑은 어떤 질의로도 그 조문을 못
가져온다 — 12번 방향만으로는 **원리적으로** 상한이 6/15 다(실측 4/15).

여기서 둘을 합쳐, 방향별로 몇 건을 잡는지 처음으로 잰다.

> 아래 두 함수는 `rag/merge.py` 원문을 그대로 넣은 것이다. 두 벌로 갈라져
> 서로 달라지는 것을 막으려고 노트북 생성기가 파일에서 읽어다 넣는다.
""")
add(PY, r"""
""" + _MERGE_SRC + r"""

# 13번 셀은 광고 일부만 돌렸을 수 있다(N_ADS). 안 돈 광고는 **누락 방향이
# 없는 것**이라 그대로 세면 「누락을 못 잡았다」로 보인다 — 구분해 둔다.
JUDGED = set(RULE_RESULT)
MERGED = [merge_findings(it, RULE_RESULT.get(it["광고id"]))
          for it in RESULT if it["광고id"] not in SKIP]

byid = {r["evidence_id"]: i for i, r in enumerate(rows)}
_rule_rows = {}
def rows_of_rule(rid):
    if rid not in _rule_rows:
        i = byid.get(rid)
        _rule_rows[rid] = {j for j, _, _ in hop2([i])} if i is not None else set()
    return _rule_rows[rid]

gold_list = [g for g in json.load(open("ad_gold4.json", encoding="utf-8"))["건"]
             if g.get("정답행")]
full = [g for g in gold_list if g["광고id"] in JUDGED]

S_ALL = score(MERGED, gold_list, rows_of_rule, lambda e: byid.get(e))
S_FULL = score([m for m in MERGED if m["광고id"] in JUDGED],
               full, rows_of_rule, lambda e: byid.get(e))

print(f"규칙 판정을 돌린 광고 {len(JUDGED)}건 / 전체 {len(MERGED)}건")
for name, s in (("양방향(규칙 판정 돌린 광고만)", S_FULL), ("전체", S_ALL)):
    if not s["정답"]:
        continue
    print(f"\n[{name}] 정답 {s['정답']}건 중 **{s['잡음']}건**")
    print(f"   광고→조문만 {s['광고→조문만']} · 조문→광고만 {s['조문→광고만']} "
          f"· 둘 다 {s['둘 다']}")
for aid, a, b, why in S_FULL["상세"]:
    mark = "O" if (a or b) else "X"
    src = ("양쪽" if a and b else "오기" if a else "누락" if b else "-")
    print(f"  {mark} {aid:18s} [{src:4s}] {why}")
""")

add(MD, "## 15. 보고서")
add(PY, r"""
best = max(RETR, key=lambda x: (x["R@5"], x["R@1"]))
judged = collections.Counter(r["판정"].get("_source") for r in RESULT)
verdicts = collections.Counter(r["판정"].get("판정") for r in RESULT)

lines = ["# 전체 파이프라인 — 실물 실행", "",
         f"색인 {len(rows):,} (규칙 {n_rules:,}) · 광고 {len(ads)}건 · 정답 {len(gold)}건",
         f"규칙→조문 이어짐 {linked:,}/{n_rules:,}건", "",
         "## 무엇이 실물인가", "",
         "| 단계 | 무엇 |", "|---|---|",
         f"| 검색 | Elasticsearch {req('GET','/')['version']['number']} + nori + dense_vector kNN |",
         "| 임베딩 | BAAI/bge-m3 |",
         "| 리랭커 | BAAI/bge-reranker-v2-m3 |",
         f"| 판정 | {MODEL} ({'4bit' if FOURBIT else 'bf16'}) |",
         "| 구조 | 2-hop (광고→규칙→조문) |", "",
         "## 검색 성능", "",
         "| 검색 | 리랭커 | " + " | ".join(f"R@{k}" for k in KL) + " | 초 |",
         "|---|---|" + "---:|"*len(KL) + "---:|"]
for r in sorted(RETR, key=lambda x: (-x["R@5"], -x["R@1"])):
    lines.append(f"| {r['검색']} | {r['리랭커']} | "
                 + " | ".join(f"{r[f'R@{k}']}%" for k in KL) + f" | {r['초']} |")
lines += ["", f"가장 나은 조합 — **{best['검색']} · 리랭커 {best['리랭커']} · R@5 {best['R@5']}%**", "",
          "## 판정", "", f"- 판정 출처: {dict(judged)}", f"- 판정 분포: {dict(verdicts)}", "",
          "## 읽는 법", "",
          f"- 정답이 {len(gold)}건이고 **실제 광고물은 6종뿐**이다(위풍당당적금 4·공무원신용대출 4·전세대출 4).",
          "  광고 하나가 최대 26.7%p 를 움직인다. 방식 차이를 단정하지 말 것.",
          "- 투자성 정답이 **0건**이다. 규칙 1,744건 중 975건(56%)이 투자성인데 그 성능은 안 재고 있다.",
          "- 보고 지표 `EVIDENCE_PRECISION`(목표 85%)은 **정밀도**라 여기 회수와 방향이 반대다. 사람이 O/X 로 봐야 나온다."]

open("full_report.md", "w", encoding="utf-8").write(NL.join(lines))
json.dump(RESULT, open("full_result.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(NL.join(lines[:30]))
from google.colab import files
files.download("full_report.md"); files.download("full_result.json")
""")


def main():
    nb = {"cells": [{"cell_type": k, "metadata": {},
                     **({"outputs": [], "execution_count": None} if k == PY else {}),
                     "source": t.splitlines(keepends=True)} for k, t in CELLS],
          "metadata": {"kernelspec": {"display_name": "Python 3", "name": "python3"},
                       "language_info": {"name": "python"},
                       "accelerator": "GPU", "colab": {"provenance": []}},
          "nbformat": 4, "nbformat_minor": 0}
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "full_colab.ipynb")
    json.dump(nb, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"셀 {len(CELLS)}개 → {out}")


if __name__ == "__main__":
    main()
