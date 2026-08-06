# -*- coding: utf-8 -*-
"""rag/rerank_colab.ipynb 를 만든다.

**정답은 후보 안에 이미 있고 순위만 틀렸다.** 통합 색인에서 BM25 를 재 보면

    R@5   14.4%      ← 규칙이 상위를 차지해 조문이 밀린다
    R@50  80.2%      ← 정답은 상위 50 안에 들어 있다

리랭커는 바로 이 상황을 위한 것이다. 검색기가 후보를 넉넉히 뽑고(recall), 교차
인코더가 질의와 문서를 **함께 읽어** 다시 매긴다(precision). BM25 는 낱말이 겹치는지만
보고 벡터는 각각을 따로 임베딩하지만, 교차 인코더는 둘을 한 번에 넣어 관계를 본다.

**DAP 가 BGE-reranker-v2 를 준다.** 그래서 이걸로 잰다 — 옮길 수 없는 성능은 성능이
아니다.

  python rag/_build_colab_nb9.py
"""
import os
import json

MD = "markdown"
PY = "code"

CELLS = []


def add(kind, text):
    CELLS.append((kind, text.strip("\n")))


add(MD, """
# 리랭커가 순위를 고치는가 — BGE-reranker-v2-m3

**정답은 이미 후보 안에 있다.** 통합 색인(규칙 1,744 + 조문 6,565)에서 BM25 를 재면

| | R@1 | R@5 | R@10 | R@20 | R@50 | R@100 |
|---|---:|---:|---:|---:|---:|---:|
| BM25 | 0.0% | **14.4%** | 43.4% | 67.7% | **80.2%** | 84.7% |

R@5 가 14.4% 인 것은 **규칙이 상위를 79~86% 차지해 조문이 밀려나기** 때문이다.
그런데 R@50 은 80.2% — 정답 조문이 후보 안에는 들어 있다. **순위만 고치면 된다.**

리랭커는 이럴 때 쓴다. BM25 는 낱말이 겹치는지만 보고 벡터는 질의와 문서를 각각
따로 임베딩하지만, **교차 인코더는 둘을 한 번에 넣어 관계를 읽는다.** 느린 대신
정확해서, 후보를 좁힌 뒤에만 쓴다.

| 재는 것 | |
|---|---|
| 후보 깊이 | 20 / 50 / 100 개를 각각 다시 매겨 본다 |
| 비교 | BM25 그대로 vs 리랭킹 후 |
| 부수 확인 | 상위 5개의 **규칙:조문 비율** — 리랭커가 조문을 되살리는가 |

**런타임:** T4 로도 되지만 A100 이면 5분이면 끝난다.
**입력:** `rule_index.jsonl` · `gold.json` · **출력:** `rerank_report.md`
""")

add(MD, "## 1. 환경")
add(PY, """
!nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || echo "GPU 없음"
!pip -q install -U sentence-transformers 2>&1 | tail -1
""")

add(MD, "## 2. 파일 업로드 — `rule_index.jsonl` · `gold.json` (`output/_rag/`)")
add(PY, """
from google.colab import files
import os
up = files.upload()
for n in up:
    print(f"{n:22s} {len(up[n])/1e6:6.1f}MB")
assert all(os.path.exists(n) for n in ("rule_index.jsonl", "gold.json"))
""")

add(MD, """
## 3. 자료 · BM25

`rag/bm25.py` 원문 그대로다. 비슷하게 다시 쓰면 「리랭커가 올린 건지 토크나이저가
달라서인지」를 못 가린다.

**부칙은 검색에서 뺀다** — 시행일·경과조치라 광고심의 근거가 될 수 없고, gold 334건과
규칙 1,744건이 **한 번도** 인용하지 않았다(청크의 20%). `is_active` 로 꺼져 있다.
""")
add(PY, r"""
import json, re, math, collections

index = [json.loads(l) for l in open("rule_index.jsonl", encoding="utf-8")]
gold = json.load(open("gold.json", encoding="utf-8"))
N_RULES = sum(1 for r in index if r["evidence_id"].startswith("R-"))
print(f"색인 {len(index):,} (규칙 {N_RULES:,} + 조문 {len(index)-N_RULES:,}) · gold {len(gold)}건")

def text_of(r):
    return f"{r.get('title','')} {r.get('article_no','')} {r.get('content','')}"

ACTIVE = [i for i, r in enumerate(index) if r.get("is_active", True)]
print(f"검색 대상 {len(ACTIVE):,} (부칙 {len(index)-len(ACTIVE):,}개 제외)")

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
docs, df = [], collections.Counter()
for i in ACTIVE:
    tf = collections.Counter(tokenize(text_of(index[i]))); docs.append(tf); df.update(tf.keys())
n = len(docs)
idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
inv = collections.defaultdict(list)
for j, d in enumerate(docs):
    for t, f in d.items(): inv[t].append((j, f))
dl = [sum(d.values()) for d in docs]; avgdl = sum(dl) / max(n, 1)

def bm25(q, k=100):
    sc = collections.defaultdict(float)
    for t in set(tokenize(q)):
        post = inv.get(t)
        if not post: continue
        w = idf[t]
        for j, f in post:
            sc[j] += w * f * (K1+1) / (f + K1*(1 - B + B*dl[j]/avgdl))
    return [ACTIVE[j] for j, _ in sorted(sc.items(), key=lambda x: -x[1])[:k]]

CAND = [bm25(g["q"], 100) for g in gold]
print(f"후보 뽑음 · 평균 {sum(len(c) for c in CAND)/len(CAND):.0f}개")
""")

add(MD, """
## 4. 기준선

리랭킹 **전** 숫자. 이게 안 맞으면 뒤 숫자도 못 믿는다.
""")
add(PY, """
KS = (1, 3, 5, 10)

def score(rankings):
    hit = {k: 0 for k in KS}; mrr = 0.0
    for j, g in enumerate(gold):
        ans = {c + N_RULES for c in g["정답청크"]}
        p = next((r for r, d in enumerate(rankings[j], 1) if d in ans), None)
        for k in KS:
            if p and p <= k: hit[k] += 1
        mrr += 1/p if p else 0
    m = len(gold)
    return {f"R@{k}": hit[k]/m for k in KS} | {"MRR": mrr/m}

def show(label, s, extra=""):
    print(f"{label:26s} " + " · ".join(f"R@{k} {s[f'R@{k}']*100:5.1f}%" for k in KS)
          + f" · MRR {s['MRR']:.3f} {extra}")

ROWS = []
base = score(CAND)
ROWS.append(("BM25 (리랭킹 없음)", 0, base))
show("BM25 (리랭킹 없음)", base)

for depth in (20, 50, 100):
    s = score([c[:depth] for c in CAND])
    print(f"   후보 {depth:>3}개 안의 정답 비율(천장) R@{depth} "
          f"{sum(1 for j,g in enumerate(gold) if set(c+N_RULES for c in g['정답청크']) & set(CAND[j][:depth]))/len(gold)*100:5.1f}%")
""")

add(MD, """
## 5. 리랭커

`BAAI/bge-reranker-v2-m3` — DAP 가 주는 것이다. 교차 인코더라 (질의, 문서) 쌍마다
한 번씩 돌려야 해서 느리다. 후보 100개 × 334질의 = 33,400쌍이다.

**질의와 문서를 자른다.** 문서가 2,000자를 넘으면 뒤가 잘리는데, 조문은 앞에 제목과
조번호가 오므로 앞쪽이 더 중요하다.
""")
add(PY, """
import torch, time
from sentence_transformers import CrossEncoder

dev = "cuda" if torch.cuda.is_available() else "cpu"
ce = CrossEncoder("BAAI/bge-reranker-v2-m3", device=dev, max_length=1024)
print(f"리랭커 올림 · {dev}")

def rerank(depth, bs=64):
    out, t0 = [], time.time()
    for j, g in enumerate(gold):
        cand = CAND[j][:depth]
        pairs = [[g["q"][:512], text_of(index[i])[:2000]] for i in cand]
        sc = ce.predict(pairs, batch_size=bs, show_progress_bar=False)
        out.append([i for i, _ in sorted(zip(cand, sc), key=lambda x: -x[1])])
        if (j+1) % 80 == 0:
            print(f"   깊이{depth}  {j+1:>3}/{len(gold)}  {time.time()-t0:5.0f}초")
    return out

RERANKED = {}
for depth in (20, 50, 100):
    RERANKED[depth] = rerank(depth)
    s = score(RERANKED[depth])
    ROWS.append((f"+ 리랭커 (후보 {depth})", depth, s))
    show(f"+ 리랭커 (후보 {depth})", s)
""")

add(MD, """
## 6. 리랭커가 조문을 되살리는가

R@5 가 낮았던 원인은 **규칙이 상위를 79~86% 차지해서**였다(전체에서 규칙 비중은
21%). 리랭커를 거친 뒤 그 비율이 어떻게 되는지 본다. 21% 에 가까워지면 리랭커가
종류에 치우치지 않고 내용으로 매긴다는 뜻이다.
""")
add(PY, """
def rule_share(rankings, k=5):
    tot = rn = 0
    for r in rankings:
        for d in r[:k]:
            tot += 1
            if d < N_RULES: rn += 1
    return rn / max(tot, 1)

SHARE = [("BM25 (리랭킹 없음)", rule_share(CAND))]
for depth in (20, 50, 100):
    SHARE.append((f"+ 리랭커 (후보 {depth})", rule_share(RERANKED[depth])))
print(f"{'':26s} 상위5 중 규칙 비율   (전체 비중 21.0%)")
for label, v in SHARE:
    print(f"{label:26s} {v*100:5.1f}%")
""")

add(MD, "## 7. 보고서")
add(PY, """
import json

lines = ["# 리랭커 A/B — BGE-reranker-v2-m3", "",
         f"색인 {len(index):,} (규칙 {N_RULES:,} + 조문 {len(index)-N_RULES:,}) · "
         f"검색 대상 {len(ACTIVE):,} · gold {len(gold)}건", "",
         "| 방식 | 후보 | R@1 | R@3 | R@5 | R@10 | MRR |",
         "|---|---:|---:|---:|---:|---:|---:|"]
for label, depth, s in ROWS:
    lines.append(f"| {label} | {depth or '-'} | " +
                 " | ".join(f"{s[f'R@{k}']*100:.1f}%" for k in KS) + f" | {s['MRR']:.3f} |")
lines += ["", "## 상위 5개의 규칙 비율", "",
          "R@5 가 낮았던 원인은 규칙이 상위를 독차지해 조문이 밀려서였다.",
          "전체에서 규칙 비중은 21.0% 다 — 여기에 가까울수록 종류에 안 치우친다.", "",
          "| 방식 | 규칙 비율 |", "|---|---:|"]
for label, v in SHARE:
    lines.append(f"| {label} | {v*100:.1f}% |")
lines += ["", "## 천장 (2026-08-06 실측)", "",
          "| | R@5 | R@10 | R@20 | R@50 | R@100 |", "|---|---:|---:|---:|---:|---:|",
          "| BM25 | 14.4% | 43.4% | 67.7% | 80.2% | 84.7% |", "",
          "후보 50개를 다시 매기면 R@5 가 최대 80.2% 까지 오를 수 있다.",
          "리랭킹 후 R@5 가 이 값에 얼마나 다가갔는지가 리랭커의 성적이다."]
open("rerank_report.md", "w", encoding="utf-8").write("\\n".join(lines))
print("\\n".join(lines))

from google.colab import files
files.download("rerank_report.md")
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
                       "rerank_colab.ipynb")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(nb, f, ensure_ascii=False, indent=1)
    print(f"셀 {len(CELLS)}개 → {out}")


if __name__ == "__main__":
    main()
