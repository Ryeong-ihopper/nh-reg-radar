# -*- coding: utf-8 -*-
"""rag/ho_split_colab.ipynb 를 만든다.

**앞 실험(V3)은 잘못된 층에서 잘랐다.** 항(①②③)으로 나눴는데 우리 정답 조문은
항이 중앙 1개뿐이고 **호(1. 2. 3.)가 중앙 9개**다. 제16조는 항이 2개라 2조각이
됐고 9개 호는 그대로 뭉쳐 있었다 — 가설이 기각된 게 아니라 시험이 틀렸다.

실패 진단에서 두 가지가 나왔고 **뿌리가 같다.**

  ① 정답이 열거형   제16조(의무 표시사항)에 의무 9가지가 나열되고 질의는 그중 하나.
                   조문 전체 임베딩은 9개의 평균이라 특정 호로 안 끌린다.
                   gold 334건 중 120건(36%)이 항 2개 이하 · 호 5개 이상.
  ② 허브 청크      금투협 제2-40조(995자)가 벡터 1위를 16회, 은행 기준 제17조(1006자)가
                   15회 차지. 상위 5개가 62/334(19%). **허브도 전부 긴 열거형이다** —
                   여러 얘기가 섞여 있으니 모든 질의와 두루 가깝다.

호로 자르면 정답은 선명해지고 허브는 쪼개진다. **BM25 도 같이 잰다** — 호 단위가
벡터에만 좋고 BM25 를 깎으면 청킹을 통째로 바꿀 수 없다.

  python rag/_build_colab_nb7.py
"""
import os
import json

MD = "markdown"
PY = "code"

CELLS = []


def add(kind, text):
    CELLS.append((kind, text.strip("\n")))


add(MD, """
# 조문을 호 단위로 자르면 나아지는가 — BGE-M3 + BM25

앞 실험에서 **항(①②③)으로 잘랐는데 우리 정답은 호(1. 2. 3.)가 목록의 층**이었다.
정답 조문의 항은 중앙 **1개**, 호는 중앙 **9개**다. 이번엔 제대로 자른다.

| 변형 | 무엇 |
|---|---|
| **V0 지금** | 조문 통째로 6,565 — 비교 기준 (벡터 R@5 45.2% · BM25 75.1%) |
| **V4 호 단위** | `1. 2. 3.` 경계로 자르고 **조문 제목 + 항 도입부**를 각 조각 앞에 붙임 |
| **V5 호+목** | 위에 더해 `가. 나. 다.` 까지 자름 |
| **V6 호 단위 + 규정명 제거** | V4 에서 본문 첫머리 `[규정명]` 도 뺌 (앞 실험에서 +0.9%p) |

**도입부를 붙이는 이유** — 「3. 계약 체결 전 상품설명서 및 약관 확인을 권유하는 문구」
만 떼면 무슨 조문의 무슨 의무인지 알 수 없다. 「제16조(의무 표시사항) ① 은행은 …
다음 각 호의 사항이 포함되도록」을 앞에 붙여야 뜻이 산다.

**BM25 도 같이 잰다.** 호 단위가 벡터에만 좋고 BM25 를 깎으면 청킹을 통째로 바꿀 수
없다. 둘 다 나아져야 채택한다.

**런타임:** T4 GPU · **입력:** `chunks.jsonl` · `gold.json` · **출력:** `ho_split_report.md`
""")

add(MD, "## 1. 환경")
add(PY, """
!nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || echo "GPU 없음"
!pip -q install -U sentence-transformers 2>&1 | tail -1
""")

add(MD, "## 2. 파일 업로드 — `chunks.jsonl` · `gold.json`")
add(PY, """
from google.colab import files
import os
up = files.upload()
for n in up:
    print(f"{n:20s} {len(up[n])/1e6:6.1f}MB")
assert all(os.path.exists(n) for n in ("chunks.jsonl", "gold.json"))
""")

add(MD, """
## 3. 호 단위로 자르기

**자르는 규칙**

- 호(`1.`~`99.`)가 **3개 이상**일 때만 자른다. 둘 이하면 잘라도 조각만 늘고 뜻이 없다
- 각 조각 앞에 **조문 제목 + 그 호가 속한 항의 도입부**를 붙인다
- 도입부는 200자로 자른다 — 길면 조각마다 같은 글자가 반복돼 다시 뭉개진다
""")
add(PY, r"""
import json, re

chunks = [json.loads(l) for l in open("chunks.jsonl", encoding="utf-8")]
gold = json.load(open("gold.json", encoding="utf-8"))
print(f"청크 {len(chunks):,} · gold {len(gold)}건")

_HEAD = re.compile(r"^\[[^\]]{1,60}\]\s*")           # 「[금융투자회사의 …] 」
_HO = re.compile(r"^\s*(\d{1,2})\.\s", re.M)         # 줄 앞의 「3. 」
_MOK = re.compile(r"^\s*([가-힣])\.\s", re.M)         # 줄 앞의 「나. 」
_HANG = re.compile(r"[①-⑮]")

def _pieces(text, pat, min_n):
    # 경계 위치로 나눈다. 첫 덩어리는 도입부다.
    marks = [m.start() for m in pat.finditer(text)]
    if len(marks) < min_n:
        return None
    lead = text[:marks[0]].strip()
    parts = [text[a:b].strip() for a, b in zip(marks, marks[1:] + [len(text)])]
    return lead, [p for p in parts if p]

def split_ho(c, with_mok=False, drop_reg=False):
    body = _HEAD.sub("", c["text"], count=1) if drop_reg else c["text"]
    got = _pieces(body, _HO, 3)
    if not got:
        return [body]
    lead, parts = got
    # 도입부가 길면 조각마다 같은 글자가 반복돼 임베딩이 다시 뭉개진다
    lead = lead[:200]
    out = []
    for p in parts:
        if with_mok:
            sub = _pieces(p, _MOK, 3)
            if sub:
                head2, mok = sub
                out += [f"{lead} {head2} {x}".strip() for x in mok]
                continue
        out.append(f"{lead} {p}".strip())
    return out

def whole(c, drop_reg=False):
    return [_HEAD.sub("", c["text"], count=1) if drop_reg else c["text"]]

SPECS = {
    "V0 지금":            lambda c: [f"{c['reg']} {c.get('key','')} {c.get('title','')} {c['text']}"],
    "V4 호 단위":          lambda c: split_ho(c),
    "V5 호+목":           lambda c: split_ho(c, with_mok=True),
    "V6 호+규정명제거":      lambda c: split_ho(c, drop_reg=True),
}

VARIANTS = {}
for name, fn in SPECS.items():
    txt, owner = [], []
    for i, c in enumerate(chunks):
        for p in fn(c):
            txt.append(p); owner.append(i)
    VARIANTS[name] = {"text": txt, "owner": owner}
    L = sorted(len(t) for t in txt)
    print(f"  {name:16s} {len(txt):>6,}조각 · 길이 중앙 {L[len(L)//2]:>4} · p90 {L[int(len(L)*.9)]:>5}")

# 잘 잘렸는지 눈으로 — 은행 광고심의 기준 제16조
tgt = next(i for i, c in enumerate(chunks)
           if c["reg"].startswith("은행 광고") and c.get("key") == "제16조")
print("\n제16조가 V4 에서 나뉜 모습:")
for p in split_ho(chunks[tgt])[:3]:
    print(f"   {p[:110]!r}")
""")

add(MD, """
## 4. BM25 — 먼저 벡터 없이

`rag/bm25.py` 원문 그대로. **조각으로 찾되 원래 조문 번호로 접어서** 센다.
""")
add(PY, r"""
import re, math, collections

_HANGUL = re.compile(r"[가-힣]+")
_WORD = re.compile(r"[A-Za-z0-9]+")
_ART = re.compile(r"제\s*(\d+)\s*(?:-\s*(\d+))?\s*조(?:\s*의\s*(\d+))?")
_TBL = re.compile(r"\[?\s*(별표|별지|서식|첨부)\s*(?:제)?\s*0*(\d+)\s*(?:의\s*(\d+))?\s*(?:호)?\s*\]?")
_TBL_BARE = re.compile(r"(별표|별지|서식|첨부)")

def _art_tokens(m):
    a, b, c = m.group(1), m.group(2), m.group(3)
    key = f"조{a}" + (f"-{b}" if b else "") + (f"의{c}" if c else "")
    return [key] + ([f"조{a}"] if (b or c) else [])

def _tbl_tokens(m):
    kind, num, sub = m.group(1), int(m.group(2)), m.group(3)
    suf = f"의{sub}" if sub else ""
    return [kind, f"{kind}{num}{suf}", f"{kind}{num:04d}{suf}"]

def tokenize(text):
    toks = []
    for m in _ART.finditer(text): toks += _art_tokens(m)
    for m in _TBL.finditer(text): toks += _tbl_tokens(m)
    rest = _TBL.sub(" ", _ART.sub(" ", text))
    for m in _TBL_BARE.finditer(rest): toks.append(m.group(1))
    rest = _TBL_BARE.sub(" ", rest)
    toks += [w.lower() for w in _WORD.findall(rest)]
    for run in _HANGUL.findall(rest):
        toks += [run] if len(run) == 1 else [run[i:i+2] for i in range(len(run)-1)]
    return toks

K1, B = 1.2, 0.75

def bm25_rank(texts, queries, top=400):
    docs, df = [], collections.Counter()
    for t in texts:
        tf = collections.Counter(tokenize(t)); docs.append(tf); df.update(tf.keys())
    N = len(docs)
    idf = {t: math.log(1 + (N - n + 0.5) / (n + 0.5)) for t, n in df.items()}
    inv = collections.defaultdict(list)
    for i, d in enumerate(docs):
        for t, f in d.items(): inv[t].append((i, f))
    dl = [sum(d.values()) for d in docs]; avg = sum(dl) / max(N, 1)
    out = []
    for q in queries:
        sc = collections.defaultdict(float)
        for t in set(tokenize(q)):
            post = inv.get(t)
            if not post: continue
            w = idf[t]
            for i, f in post:
                sc[i] += w * f * (K1+1) / (f + K1*(1 - B + B*dl[i]/avg))
        out.append([i for i, _ in sorted(sc.items(), key=lambda x: -x[1])[:top]])
    return out
""")

add(MD, """
## 5. 채점 — 조각 순위를 조문 순위로 접는다

같은 조문의 조각이 1·2·3위를 차지했다면 그 조문은 **1위 하나**로 센다. 안 그러면
잘게 자른 변형이 자동으로 유리해져 비교가 성립하지 않는다.
""")
add(PY, """
import numpy as np

KS = (1, 3, 5, 10)

def fold(order, owner, k=20):
    seen, out = set(), []
    for d in order:
        o = int(owner[d])
        if o not in seen:
            seen.add(o); out.append(o)
        if len(out) >= k: break
    return out

def score(orders, owner):
    hit = {k: 0 for k in KS}; mrr = 0.0
    for j, g in enumerate(gold):
        ans = set(g["정답청크"])
        ranked = fold(orders[j], owner)
        p = next((r for r, o in enumerate(ranked, 1) if o in ans), None)
        for k in KS:
            if p and p <= k: hit[k] += 1
        mrr += 1/p if p else 0
    n = len(gold)
    return {f"R@{k}": hit[k]/n for k in KS} | {"MRR": mrr/n}

qs = [g["q"] for g in gold]
ROWS = []
for name, v in VARIANTS.items():
    s = score(bm25_rank(v["text"], qs), v["owner"])
    ROWS.append((name, "BM25", len(v["text"]), s))
    print(f"{name:16s} BM25  " + " · ".join(f"R@{k} {s[f'R@{k}']*100:5.1f}%" for k in KS)
          + f" · MRR {s['MRR']:.3f}")
""")

add(MD, "## 6. 벡터 — BGE-M3")
add(PY, """
import numpy as np, torch, gc, time
from sentence_transformers import SentenceTransformer

m = SentenceTransformer("BAAI/bge-m3",
                        device="cuda" if torch.cuda.is_available() else "cpu")
m.max_seq_length = 1024

def embed(texts, bs=64, tag=""):
    # 진행바를 끄고 2,000개마다 한 줄만 — tqdm 이 출력을 쏟으면 브라우저가 렉에 걸린다
    out, t0 = [], time.time()
    for s in range(0, len(texts), 2000):
        out.append(m.encode(texts[s:s+2000], batch_size=bs,
                            convert_to_numpy=True, show_progress_bar=False))
        print(f"  {tag} {min(s+2000, len(texts)):>6,}/{len(texts):,}  {time.time()-t0:5.0f}초")
    v = np.vstack(out).astype("float32")
    return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)

qvec = embed(qs, tag="질의")
for name, v in VARIANTS.items():
    print(f"\\n{name} — {len(v['text']):,}조각")
    vec = embed(v["text"], tag=name)
    sim = qvec @ vec.T
    orders = [np.argsort(-sim[j])[:400].tolist() for j in range(len(gold))]
    s = score(orders, v["owner"])
    ROWS.append((name, "벡터", len(v["text"]), s))
    print(f"{name:16s} 벡터  " + " · ".join(f"R@{k} {s[f'R@{k}']*100:5.1f}%" for k in KS)
          + f" · MRR {s['MRR']:.3f}")
    del vec, sim; gc.collect(); torch.cuda.empty_cache()
""")

add(MD, """
## 7. 보고서

**둘 다 나아져야 채택한다.** 벡터만 좋아지고 BM25 가 깎이면 지금 쓰는 검색이
나빠지는 것이라 바꿀 수 없다.
""")
add(PY, """
import json

lines = ["# 조문 호 단위 분할 A/B — BGE-M3 + BM25", "",
         f"청크 {len(chunks):,} · gold {len(gold)}건", "",
         "| 변형 | 방식 | 조각 수 | R@1 | R@3 | R@5 | R@10 | MRR |",
         "|---|---|---:|---:|---:|---:|---:|---:|"]
for name, how, n, s in ROWS:
    lines.append(f"| {name} | {how} | {n:,} | " +
                 " | ".join(f"{s[f'R@{k}']*100:.1f}%" for k in KS) + f" | {s['MRR']:.3f} |")
lines += ["", "## 기준 (조문 통째, 2026-08-06 실측)", "",
          "| 방식 | R@1 | R@5 | R@10 | MRR |", "|---|---:|---:|---:|---:|",
          "| BM25 | 34.4% | 75.1% | 79.0% | 0.515 |",
          "| 벡터 | 24.3% | 45.2% | 56.3% | 0.336 |", "",
          "V0 가 이 값 근처로 재현되어야 조건이 같다."]
open("ho_split_report.md", "w", encoding="utf-8").write("\\n".join(lines))
print("\\n".join(lines))

from google.colab import files
files.download("ho_split_report.md")
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
            "accelerator": "GPU",
            "colab": {"provenance": []},
        },
        "nbformat": 4, "nbformat_minor": 0,
    }
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "ho_split_colab.ipynb")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(nb, f, ensure_ascii=False, indent=1)
    print(f"셀 {len(CELLS)}개 → {out}")


if __name__ == "__main__":
    main()
