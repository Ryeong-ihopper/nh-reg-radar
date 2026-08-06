# -*- coding: utf-8 -*-
"""rag/nori_es_colab.ipynb — Elasticsearch(nori)를 Colab 안에서 띄워 진짜 숫자를 잰다.

Colab 에는 도커 데몬이 없다. 대신 ES tar 를 받아 세션 안에서 직접 실행한다.
ES 는 root 실행을 거부하는데 Colab 은 root 라, 일반 사용자를 만들어 그걸로 띄운다.

**차이를 토크나이저 하나로 좁힌다** — 색인에 넣는 문자열은 로컬 BM25 와 완전히 같고
(title+article_no+content 연결, 부칙 제외 동일), 다른 것은 nori↔한글 바이그램뿐이다.
그래서 점수 차이가 나면 그것은 전부 토크나이저 차이다.

  python rag/_build_colab_nb10.py
"""
import os
import json

MD = "markdown"
PY = "code"

CELLS = []


def add(kind, text):
    CELLS.append((kind, text.strip("\n")))


add(MD, """
# nori 로 잰 진짜 숫자 — Elasticsearch in Colab

DAP 의 벡터 DB 가 Elasticsearch 고 한국어 analyzer(nori)를 쓴다. 우리 로컬 BM25 는
한글 바이그램 토크나이저라 **숫자가 그대로 안 옮겨진다** — 얼마나 달라지는지를
DAP 에 가기 전에 여기서 잰다.

| | |
|---|---|
| **GPU** | 필요 없음 — **CPU 런타임**으로 충분 (A100 세션 아깝게 쓰지 말 것) |
| **입력 2개** | `rule_index.jsonl` · `gold.json` (`output/_rag/`) |
| **출력** | `nori_report.md` |
| **비교 기준** | 로컬 바이그램 BM25 · 통합 색인: R@5 14.4% · R@50 80.2% |

**차이를 토크나이저 하나로 좁혔다.** 색인 문자열은 로컬과 완전히 같다
(title+article_no+content 연결 · 부칙 제외 동일). 점수가 다르면 전부 토크나이저다.
""")

add(MD, """
## 1. Elasticsearch 내려받아 띄우기

- ES 는 **root 실행을 거부**하고 Colab 은 root 다 → `esuser` 를 만들어 그걸로 띄운다
- localhost 에만 바인딩하면 ES 가 개발 모드로 돌아 부트스트랩 검사가 경고로 끝난다
- tar ~600MB, 띄우는 데까지 3분 안팎
""")
add(PY, r"""
import os, subprocess, time, urllib.request

ES_VER = "8.14.3"
ES_DIR = f"/content/elasticsearch-{ES_VER}"

if not os.path.exists(ES_DIR):
    print("내려받는 중 (~600MB)…")
    url = (f"https://artifacts.elastic.co/downloads/elasticsearch/"
           f"elasticsearch-{ES_VER}-linux-x86_64.tar.gz")
    subprocess.run(f"curl -sSL {url} | tar xz -C /content", shell=True, check=True)
    subprocess.run(f"{ES_DIR}/bin/elasticsearch-plugin install --batch analysis-nori",
                   shell=True, check=True)
    with open(f"{ES_DIR}/config/elasticsearch.yml", "a") as f:
        f.write("\ndiscovery.type: single-node\nxpack.security.enabled: false\n")
    # ES 는 root 로 못 띄운다. esuser 를 만들어 소유권을 넘긴다.
    subprocess.run("id -u esuser >/dev/null 2>&1 || useradd -m esuser",
                   shell=True, check=True)
    subprocess.run(f"chown -R esuser:esuser {ES_DIR}", shell=True, check=True)

subprocess.run(
    f'sudo -u esuser ES_JAVA_OPTS="-Xms2g -Xmx2g" {ES_DIR}/bin/elasticsearch -d -p /tmp/es.pid',
    shell=True, check=True)

for i in range(60):
    try:
        with urllib.request.urlopen("http://127.0.0.1:9200/_cluster/health", timeout=2) as r:
            print("ES 기동:", r.read().decode()[:120])
            break
    except Exception:
        time.sleep(3)
else:
    raise RuntimeError("ES 가 60초 안에 안 떴다 — 로그: !tail -30 " + ES_DIR + "/logs/*.log")
""")

add(MD, "## 2. 파일 업로드 — `rule_index.jsonl` · `gold.json`")
add(PY, """
from google.colab import files
import os
up = files.upload()
for n in up:
    print(f"{n:22s} {len(up[n])/1e6:6.1f}MB")
assert all(os.path.exists(n) for n in ("rule_index.jsonl", "gold.json"))
""")

add(MD, """
## 3. nori 가 실제로 어떻게 자르는지 먼저 본다

같은 문장을 nori 와 (우리가 로컬에서 쓰는) 바이그램이 각각 어떻게 자르는지.
숫자를 읽기 전에 **무엇이 달라지는지**를 눈으로 봐 두면 결과 해석이 쉬워진다.
""")
add(PY, r"""
import json, urllib.request

def req(method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode() if isinstance(body, (dict, list)) \
        else (body.encode() if isinstance(body, str) else body)
    r = urllib.request.Request(f"http://127.0.0.1:9200{path}", data=data, method=method,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=60) as res:
        return json.loads(res.read().decode())

req("PUT", "/_tmp_analyze", {"settings": {"analysis": {
    "tokenizer": {"korean": {"type": "nori_tokenizer", "decompound_mode": "mixed"}},
    "analyzer": {"korean": {"type": "custom", "tokenizer": "korean",
                             "filter": ["lowercase"]}}}}})

def bigrams(s):
    out = []
    for w in s.split():
        run = "".join(ch for ch in w if "가" <= ch <= "힣")
        out += [run] if len(run) == 1 else [run[i:i+2] for i in range(len(run)-1)]
    return out

for text in ("이자율의 범위 및 산출기준을 표시하였는가",
             "연 최고 7.0% 우대금리 제공"):
    toks = [t["token"] for t in req("POST", "/_tmp_analyze/_analyze",
                                    {"analyzer": "korean", "text": text})["tokens"]]
    print(f"원문     {text}")
    print(f"nori     {toks}")
    print(f"바이그램  {bigrams(text)}")
    print()
req("DELETE", "/_tmp_analyze")
""")

add(MD, """
## 4. 색인 만들기 + 적재

매핑은 `rag/es_search.py`(로컬 도커판)와 같다 — SCHEMA_ISSUES ⑦ 제안 모양.
부칙(is_active=False)은 로컬과 같이 뺀다.
""")
add(PY, r"""
import json

INDEX = "evidences_poc"
rows = [json.loads(l) for l in open("rule_index.jsonl", encoding="utf-8")]
N_RULES = sum(1 for r in rows if r["evidence_id"].startswith("R-"))
print(f"색인 {len(rows):,} (규칙 {N_RULES:,}) · 부칙 제외 "
      f"{sum(1 for r in rows if not r.get('is_active', True)):,}")

try:
    req("DELETE", f"/{INDEX}")
except Exception:
    pass
req("PUT", f"/{INDEX}", {
    "settings": {"analysis": {
        "tokenizer": {"korean": {"type": "nori_tokenizer", "decompound_mode": "mixed"}},
        "analyzer": {"korean": {"type": "custom", "tokenizer": "korean",
                                 "filter": ["lowercase"]}}}},
    "mappings": {"properties": {
        "search_text": {"type": "text", "analyzer": "korean"},
        "article_no": {"type": "text", "analyzer": "korean",
                       "fields": {"keyword": {"type": "keyword"}}},
        "evidence_id": {"type": "keyword"},
        "kind": {"type": "keyword"},
        "row": {"type": "integer"},
    }}})

lines, n = [], 0
for i, r in enumerate(rows):
    if not r.get("is_active", True):
        continue
    doc = {"search_text": f"{r.get('title','')} {r.get('article_no','') or ''} "
                          f"{r.get('content','')}",
           "article_no": r.get("article_no") or "",
           "evidence_id": r["evidence_id"],
           "kind": "rule" if r["evidence_id"].startswith("R-") else "article",
           "row": i}
    lines.append(json.dumps({"index": {"_id": r["evidence_id"]}}, ensure_ascii=False))
    lines.append(json.dumps(doc, ensure_ascii=False))
    n += 1
    if len(lines) >= 2000:
        out = req("POST", "/_bulk", "\n".join(lines) + "\n"); lines = []
        assert not out.get("errors"), "벌크 오류"
if lines:
    out = req("POST", "/_bulk", "\n".join(lines) + "\n")
    assert not out.get("errors"), "벌크 오류"
req("POST", f"/{INDEX}/_refresh")
print(f"적재 {n:,}건 → 색인 {req('GET', f'/{INDEX}/_count')['count']:,}건")
""")

add(MD, """
## 5. gold 334 로 측정

로컬 바이그램과 **완전히 같은 조건**(같은 문자열·같은 제외·같은 채점)이므로
차이는 전부 토크나이저다.
""")
add(PY, r"""
import json, time

gold = json.load(open("gold.json", encoding="utf-8"))
KS = (1, 3, 5, 10, 20, 50)

def search(q, k=50):
    hits = req("POST", f"/{INDEX}/_search",
               {"size": k, "_source": ["row"],
                "query": {"match": {"search_text": q}}})["hits"]["hits"]
    return [h["_source"]["row"] for h in hits]

hit = {k: 0 for k in KS}; mrr = 0.0; t0 = time.time()
for j, g in enumerate(gold):
    ans = {c + N_RULES for c in g["정답청크"]}
    got = search(g["q"], max(KS))
    p = next((r for r, d in enumerate(got, 1) if d in ans), None)
    for k in KS:
        if p and p <= k: hit[k] += 1
    mrr += 1/p if p else 0
    if (j+1) % 100 == 0: print(f"  {j+1}/{len(gold)}  {time.time()-t0:.0f}초")

n = len(gold)
NORI = {f"R@{k}": hit[k]/n for k in KS} | {"MRR": mrr/n}
print("\nES(nori)   " + " · ".join(f"R@{k} {NORI[f'R@{k}']*100:5.1f}%" for k in KS)
      + f" · MRR {NORI['MRR']:.3f}")
print("바이그램    R@1   0.0% · R@3   6.3% · R@5  14.4% · R@10  42.5% · "
      "R@20  67.4% · R@50  80.2% · MRR 0.106")
""")

add(MD, "## 6. 보고서")
add(PY, """
import json

BASE = {"R@1": 0.0, "R@3": 6.3, "R@5": 14.4, "R@10": 42.5, "R@20": 67.4, "R@50": 80.2}
lines = ["# nori vs 한글 바이그램 — 같은 색인, 토크나이저만 다름", "",
         f"통합 색인(규칙 {N_RULES:,} + 조문, 부칙 제외) · gold {len(gold)}건 · "
         "색인 문자열 동일", "",
         "| 토크나이저 | " + " | ".join(f"R@{k}" for k in KS) + " | MRR |",
         "|---|" + "---:|" * (len(KS) + 1)]
lines.append("| nori (ES) | " + " | ".join(f"{NORI[f'R@{k}']*100:.1f}%" for k in KS)
             + f" | {NORI['MRR']:.3f} |")
lines.append("| 바이그램 (로컬) | " + " | ".join(f"{BASE[f'R@{k}']:.1f}%" for k in KS)
             + " | 0.106 |")
lines += ["", "색인에 넣은 문자열이 완전히 같으므로(title+article_no+content, 부칙 제외)",
          "**차이는 전부 토크나이저다.** 이 숫자가 DAP 이식 후 기대치가 된다.", "",
          "매핑: nori_tokenizer(decompound_mode=mixed) + lowercase · "
          "article_no 는 text+keyword 멀티필드 (SCHEMA_ISSUES ⑦ 제안과 동일)"]
open("nori_report.md", "w", encoding="utf-8").write("\\n".join(lines))
print("\\n".join(lines))

from google.colab import files
files.download("nori_report.md")
""")


def main():
    nb = {
        "cells": [
            {"cell_type": k, "metadata": {},
             **({"outputs": [], "execution_count": None} if k == PY else {}),
             "source": t.splitlines(keepends=True)}
            for k, t in CELLS
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "name": "python3"},
            "language_info": {"name": "python"},
            "colab": {"provenance": []},
        },
        "nbformat": 4, "nbformat_minor": 0,
    }
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "nori_es_colab.ipynb")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(nb, f, ensure_ascii=False, indent=1)
    print(f"셀 {len(CELLS)}개 → {out}")


if __name__ == "__main__":
    main()
