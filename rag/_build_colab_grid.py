# -*- coding: utf-8 -*-
"""rag/grid_colab.ipynb — 검색 조합을 **전부 GPU 에서** 견준다.

로컬에서 30분 넘게 돌려도 안 끝났다. 질의마다 CPU 로 임베딩을 하기 때문이다.
GPU 면 40배 빠르고, 리랭커까지 같이 붙일 수 있다.

    축 1  색인    조 단위 9,335  ·  호 단위 35,961
    축 2  질의    광고 원문 통째 · 규칙기반 질의 · 광고 청크별
    축 3  검색    BM25 · 벡터 · 하이브리드(RRF)
    축 4  필터    없음 · 상품군(스키마 `compliance.product_group`)
    축 5  재정렬   없음 · 리랭커(bge-reranker-v2-m3)

**축 하나만 바꾸고 나머지를 고정한다.** 지금까지 이걸 안 지켜서 「BM25 가 낫다」
같은 결론이 조건을 바꾸면 뒤집혔다.

벡터는 노트북 안에서 만든다 — 올리는 것보다 빠르고, 색인과 어긋날 일이 없다.

  올릴 것   rule_index.jsonl · rule_index_ho.jsonl · ad_gold.json · ads.jsonl
  받을 것   grid_report.md

  python rag/_build_colab_grid.py
"""
import os
import json

MD, PY = "markdown", "code"
CELLS = []


def add(kind, text):
    CELLS.append((kind, text.strip("\n")))


add(MD, """
# 검색 조합 견주기 — 무엇이 이기나

## 왜 하나

지금까지 조합 하나만 돌리고 결론을 냈다. 그래서 조건을 바꾸면 뒤집혔다.

| 언제 | 결론 | 나중에 |
|---|---|---|
| 8/5 | "BM25 단독이 낫다" | 벡터를 켜니 R@10 이 40% → 80% |
| 8/6 | "광고 원문 질의는 못 쓴다" | BM25 로만 재고 버렸다 |
| 8/7 | "상품군 필터는 나중에" | 없으면 예금 광고에 ISA·CMA 규칙이 1·2위 |

**축을 다 세우고 한 표에서 본다.**

## 축

```
색인   조 단위 9,335  ·  호 단위 35,961
질의   원문 통째  ·  규칙기반  ·  광고 청크별
검색   BM25  ·  벡터  ·  하이브리드(RRF k=60)
필터   없음  ·  상품군
재정렬  없음  ·  리랭커
```

## 채점

심의사례 15건. **「걸린 규칙이 정답 조문을 근거로 달고 있나」** 를 센다.
조문만 정답으로 세면 질의의 쌍둥이 규칙이 1위에 와도 오답이 되어 전부 0% 가
나온다 — 실제로 그렇게 나왔다.

| | |
|---|---|
| 런타임 | GPU (A100 권장, T4 도 됨) |
| 올릴 것 | `rule_index.jsonl` · `rule_index_ho.jsonl` · `ad_gold.json` · `ads.jsonl` |
| 받을 것 | `grid_report.md` |
| 소요 | 임베딩 13분 + 격자 10분 |
""")

add(MD, "## 1. 환경")
add(PY, """
!nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
!pip -q install -U sentence-transformers 2>&1 | tail -1
""")

add(MD, """
## 2. 파일 올리기

왼쪽 파일 창에 끌어다 놓아도 된다. 큰 파일 둘(25MB·52MB)이 있어 몇 분 걸린다.
""")
add(PY, """
import os
from google.colab import files
NEED = ["rule_index.jsonl", "rule_index_ho.jsonl", "ad_gold.json", "ads.jsonl"]
miss = [n for n in NEED if not os.path.exists(n)]
if miss:
    print("빠진 것:", miss)
    files.upload()
for n in NEED:
    print(f"{n:24s} {os.path.getsize(n)/1e6:7.1f}MB" if os.path.exists(n)
          else f"{n:24s} 없음")
""")

add(MD, """
## 3. 공통 함수

BM25 는 로컬과 **글자 하나까지 같게** 둔다. 여기가 다르면 로컬 숫자와 비교가
안 된다.
""")
add(PY, r"""
import json, re, math, collections, time
import numpy as np

NL = chr(10)
RRF_K = 60

def index_text(r):
    return f"{r.get('title','')} {r.get('article_no') or ''} {r.get('content','')}"

def tokenize(s):
    out = re.findall(r"제\s*\d+조(?:의\s*\d+)?|[A-Za-z]+|\d+", str(s or ""))
    for w in re.findall(r"[가-힣]+", str(s or "")):
        out += [w[i:i+2] for i in range(len(w)-1)] or [w]
    return out

class BM25:
    def __init__(self, rows):
        docs, df = [], collections.Counter()
        for r in rows:
            tf = collections.Counter(tokenize(index_text(r)))
            docs.append(tf); df.update(tf.keys())
        n = len(docs)
        self.idf = {t: math.log(1+(n-c+0.5)/(c+0.5)) for t, c in df.items()}
        self.inv = collections.defaultdict(list)
        for i, d in enumerate(docs):
            for t, f in d.items():
                self.inv[t].append((i, f))
        self.dl = [sum(d.values()) for d in docs]
        self.avgdl = sum(self.dl)/max(n, 1)

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
    # 점수가 아니라 **순위**를 더한다. BM25 점수와 코사인은 자릿수가 달라
    # 그대로 더하면 한쪽이 묻힌다.
    sc = collections.defaultdict(float)
    for rank in rankings:
        for r, i in enumerate(rank, 1):
            sc[i] += 1.0/(RRF_K+r)
    return [i for i, _ in sorted(sc.items(), key=lambda x: -x[1])[:top]]

def ad_chunks(text, max_chars=500):
    out, buf = [], []
    for line in text.split(NL):
        line = line.strip()
        if not line:
            continue
        buf.append(line)
        if len(NL.join(buf)) >= max_chars:
            out.append(NL.join(buf)); buf = []
    if buf:
        out.append(NL.join(buf))
    return [c for c in out if len(c) >= 25] or [text[:500]]

# 규칙 기반 질의 — 로컬 rag/llm.py 의 것과 같다. **주먹구구라는 것을 알고 쓴다.**
# 광고 말투를 규정 말투로 바꾸는 손으로 쓴 낱말 14개다. 이 격자에서 「이게 정말
# 필요한가」를 다른 방식과 견주려고 넣는다.
TRIG = [
    (r"연\s*최고|최대\s*연|우대금리|우대\s*이율", "이자율의 범위와 산출기준, 우대금리 적용 조건을 표시해야 하는 의무"),
    (r"최저\s*연|금리\s*범위", "대출금리 범위와 기준금리·가산금리 산출기준 표시 의무"),
    (r"한도\s*최대|최대\s*\d+\s*억", "대출한도 표시 시 차감 조건 등 제한사항 표시 의무"),
    (r"세전|세후|이자소득세|비과세", "이자 표시의 세전·세후 구분 표시 의무"),
    (r"연체|기한이익\s*상실|신용평점", "연체이자율과 신용평점 영향 경고 표시 의무"),
    (r"중도상환|해약금|수수료|부대비용", "수수료·중도상환해약금 등 부대비용 발생 사실의 표시 의무"),
    (r"예금자보호|5천만원|1억원", "예금자보호 대상 여부와 보호 한도 표시 의무"),
    (r"심의필|준법감시인", "준법감시인 심의필번호와 유효기간 표시 의무"),
    (r"이벤트|경품|추첨|사은품", "경품·추첨 광고의 당첨확률과 조건 표시 의무"),
    (r"1위|최초|최고의|유일", "1위·최초 등 배타적 표현의 객관적 근거 표시 의무"),
    (r"무료|공짜|0원", "무료·0원 표시의 조건과 제한사항 표시 의무"),
    (r"후기|체험|추천|인플루언서", "추천·보증 광고의 경제적 이해관계 공개 의무"),
    (r"\(광고\)|수신거부", "영리목적 광고성 정보 전송 시 표기 의무"),
    (r"원금\s*손실|투자위험|수익률", "투자광고의 원금손실 가능성 등 투자위험 표시 의무"),
]

def queries(text, mode):
    if mode == "원문":
        return [text[:1500]]
    if mode == "규칙질의":
        out = [q for p, q in TRIG if re.search(p, text)]
        return out[:8] or [text[:300]]
    return ad_chunks(text)[:12]

print("준비 완료")
""")

add(MD, "## 4. 색인 읽고 임베딩 (GPU)")
add(PY, """
from sentence_transformers import SentenceTransformer
EMB = SentenceTransformer("BAAI/bge-m3")

IDX = {}
for name, path in (("조단위", "rule_index.jsonl"), ("호단위", "rule_index_ho.jsonl")):
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    t0 = time.time()
    V = EMB.encode([index_text(r)[:1200] for r in rows], batch_size=64,
                   normalize_embeddings=True, show_progress_bar=True).astype("float32")
    n_rules = sum(1 for r in rows if r["evidence_id"].startswith("R-"))
    IDX[name] = {"rows": rows, "V": V, "bm": BM25(rows), "n_rules": n_rules}
    print(f"{name}  {len(rows):,}건 · 규칙 {n_rules:,} · 임베딩 {time.time()-t0:.0f}초")
""")

add(MD, """
## 5. 격자

**질의 임베딩을 한 번만 만들어 돌려 쓴다.** 벡터·하이브리드가 같은 질의를 쓰는데
방식마다 다시 만들면 세 배 걸린다.
""")
add(PY, r"""
gold = json.load(open("ad_gold.json", encoding="utf-8"))["건"]
ads = {}
for l in open("ads.jsonl", encoding="utf-8"):
    x = json.loads(l); ads.setdefault(x["광고id"], x)

PG = {"예금성": "DEPOSIT", "대출성": "LOAN", "투자성": "INVESTMENT"}

def want_refs(g):
    return {(str(x[0]), re.sub(r"\s", "", str(x[1])))
            for x in (g.get("정답") or [])
            if isinstance(x, (list, tuple)) and len(x) >= 2
            and not str(x[0]).startswith("?")}

def refs_of(row):
    out = set()
    for b in (row.get("근거") or []):
        out.add((str(b.get("규정") or "").strip(),
                 re.sub(r"\s", "", str(b.get("article_no") or ""))))
    m = re.match(r"\[([^\]]+)\]\s*(제\s*\d+(?:-\d+)?\s*조(?:\s*의\s*\d+)?)",
                 row.get("content") or "")
    if m:
        out.add((m.group(1).strip(), re.sub(r"\s", "", m.group(2))))
    return out

# 질의 임베딩 캐시
QCACHE = {}
def qvec(q):
    if q not in QCACHE:
        QCACHE[q] = EMB.encode([q], normalize_embeddings=True).astype("float32")[0]
    return QCACHE[q]

KL = [1, 3, 5, 10]
RESULT = []

for iname, D in IDX.items():
    rows, V, bm, n_rules = D["rows"], D["V"], D["bm"], D["n_rules"]
    # 정답 행 미리 계산 — 조합마다 다시 하면 낭비다
    ansrow = {}
    for g in gold:
        w = want_refs(g)
        ansrow[g["광고id"]] = {i for i, r in enumerate(rows) if refs_of(r) & w} if w else set()

    for use_filter in (False, True):
        # 상품군 필터. 스키마 compliance.product_group 이 조인 키다.
        # 빈 것은 「전체」라 통과시킨다 — 빼면 금소법 공통 의무가 사라진다.
        allow_of = {}
        for pg_name, code in PG.items():
            m = np.ones(len(rows), dtype=bool)
            if use_filter:
                for i, r in enumerate(rows):
                    p = r.get("product_group") or []
                    if p and code not in p:
                        m[i] = False
            allow_of[pg_name] = m

        for qm in ("원문", "규칙질의", "청크별"):
            for how in ("bm25", "vector", "hybrid"):
                hit = {k: 0 for k in KL}; n = 0
                t0 = time.time()
                for g in gold:
                    ans = ansrow[g["광고id"]]
                    if not ans:
                        continue
                    n += 1
                    aid = g["광고id"]
                    pg = "예금성" if "예금성" in aid else "대출성" if "대출성" in aid else None
                    mask = allow_of.get(pg, np.ones(len(rows), dtype=bool))
                    qs = queries(ads[aid]["text"], qm)
                    ranks = []
                    for q in qs:
                        if how in ("bm25", "hybrid"):
                            ranks.append(bm(q, 50, allow=mask))
                        if how in ("vector", "hybrid"):
                            s = V @ qvec(q)
                            s[~mask] = -1e9
                            ranks.append(list(np.argsort(-s)[:50]))
                    merged = rrf(*ranks, top=50) if len(ranks) > 1 else ranks[0]
                    pos = next((r for r, i in enumerate(merged[:max(KL)], 1)
                                if i in ans), None)
                    for k in KL:
                        if pos and pos <= k:
                            hit[k] += 1
                row = {"색인": iname, "필터": "상품군" if use_filter else "없음",
                       "질의": qm, "검색": how, "n": n, "초": round(time.time()-t0),
                       **{f"R@{k}": round(hit[k]/max(n,1)*100, 1) for k in KL}}
                RESULT.append(row)
                print(f"{iname:5s} {row['필터']:4s} {qm:5s} {how:7s} " +
                      " ".join(f"{row[f'R@{k}']:5.1f}%" for k in KL) + f"  {row['초']:3d}초")
print(f"\n조합 {len(RESULT)}개 끝")
""")

add(MD, """
## 6. 리랭커 — 이긴 조합에만

리랭커는 상위 30개를 다시 줄 세운다. 모든 조합에 붙이면 시간이 서른 배가 되므로
**R@10 이 가장 높은 조합 셋에만** 붙여 본다.
""")
add(PY, r"""
from sentence_transformers import CrossEncoder
RR = CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=512)

best = sorted(RESULT, key=lambda x: -x["R@10"])[:3]
print("리랭커를 붙일 조합:")
for b in best:
    print(f"  {b['색인']} {b['필터']} {b['질의']} {b['검색']}  R@10 {b['R@10']}%")

RERANKED = []
for b in best:
    D = IDX[b["색인"]]
    rows, V, bm = D["rows"], D["V"], D["bm"]
    ansrow = {}
    for g in gold:
        w = want_refs(g)
        ansrow[g["광고id"]] = {i for i, r in enumerate(rows) if refs_of(r) & w} if w else set()
    hit = {k: 0 for k in KL}; n = 0
    for g in gold:
        ans = ansrow[g["광고id"]]
        if not ans:
            continue
        n += 1
        aid = g["광고id"]
        pg = "예금성" if "예금성" in aid else "대출성" if "대출성" in aid else None
        mask = np.ones(len(rows), dtype=bool)
        if b["필터"] == "상품군" and pg:
            code = PG[pg]
            for i, r in enumerate(rows):
                p = r.get("product_group") or []
                if p and code not in p:
                    mask[i] = False
        qs = queries(ads[aid]["text"], b["질의"])
        ranks = []
        for q in qs:
            if b["검색"] in ("bm25", "hybrid"):
                ranks.append(bm(q, 50, allow=mask))
            if b["검색"] in ("vector", "hybrid"):
                s = V @ qvec(q); s[~mask] = -1e9
                ranks.append(list(np.argsort(-s)[:50]))
        merged = rrf(*ranks, top=50) if len(ranks) > 1 else ranks[0]
        cand = merged[:30]
        # 리랭커에 넘길 질의는 **광고 전문**이다. 조각 질의로 재정렬하면
        # 그 조각에만 맞는 것이 위로 온다.
        pairs = [[ads[aid]["text"][:1000], index_text(rows[i])[:900]] for i in cand]
        order = [i for i, _ in sorted(zip(cand, RR.predict(pairs)), key=lambda x: -x[1])]
        pos = next((r for r, i in enumerate(order[:max(KL)], 1) if i in ans), None)
        for k in KL:
            if pos and pos <= k:
                hit[k] += 1
    row = dict(b, 재정렬="리랭커",
               **{f"R@{k}": round(hit[k]/max(n,1)*100, 1) for k in KL})
    RERANKED.append(row)
    print(f"\n{b['색인']} {b['필터']} {b['질의']} {b['검색']} + 리랭커")
    print("  " + " ".join(f"R@{k} {row[f'R@{k}']:5.1f}%" for k in KL) +
          f"   (전 {b['R@10']}%)")
""")

add(MD, "## 7. 보고서")
add(PY, r"""
lines = ["# 검색 조합 견주기", "",
         f"심의사례 {len(gold)}건 · 색인 조단위 {len(IDX['조단위']['rows']):,} · "
         f"호단위 {len(IDX['호단위']['rows']):,}", "",
         "## 전체", "",
         "| 색인 | 필터 | 질의 | 검색 | R@1 | R@3 | R@5 | R@10 | 초 |",
         "|---|---|---|---|---:|---:|---:|---:|---:|"]
for r in sorted(RESULT, key=lambda x: -x["R@10"]):
    lines.append(f"| {r['색인']} | {r['필터']} | {r['질의']} | {r['검색']} | "
                 + " | ".join(f"{r[f'R@{k}']}%" for k in KL) + f" | {r['초']} |")

lines += ["", "## 리랭커를 붙였을 때", "",
          "| 색인 | 필터 | 질의 | 검색 | R@1 | R@3 | R@5 | R@10 |",
          "|---|---|---|---|---:|---:|---:|---:|"]
for r in RERANKED:
    lines.append(f"| {r['색인']} | {r['필터']} | {r['질의']} | {r['검색']} | "
                 + " | ".join(f"{r[f'R@{k}']}%" for k in KL) + " |")

lines += ["", "## 읽는 법", "",
          "- 축 하나만 바꾸고 나머지는 고정했다. 두 개를 같이 바꾸면 어느 쪽 때문인지 못 가린다.",
          "- 정답이 광고당 1건뿐이라 **회수만** 잰다. 정답에 없는 근거가 나왔다고 틀린 게 아니다.",
          "- 보고 지표인 `EVIDENCE_PRECISION`(근거 매칭 적정성, 목표 85%)은 사람이 근거를 O/X 로 봐줘야 나온다.",
          "- 「걸린 규칙이 정답 조문을 근거로 달고 있나」를 셌다. 조문만 정답으로 세면 전부 0% 가 나온다."]

open("grid_report.md", "w", encoding="utf-8").write(NL.join(lines))
print(NL.join(lines[:30]))
from google.colab import files
files.download("grid_report.md")
""")


def main():
    nb = {"cells": [{"cell_type": k, "metadata": {},
                     **({"outputs": [], "execution_count": None} if k == PY else {}),
                     "source": t.splitlines(keepends=True)} for k, t in CELLS],
          "metadata": {"kernelspec": {"display_name": "Python 3", "name": "python3"},
                       "language_info": {"name": "python"},
                       "accelerator": "GPU", "colab": {"provenance": []}},
          "nbformat": 4, "nbformat_minor": 0}
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "grid_colab.ipynb")
    json.dump(nb, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"셀 {len(CELLS)}개 → {out}")


if __name__ == "__main__":
    main()
