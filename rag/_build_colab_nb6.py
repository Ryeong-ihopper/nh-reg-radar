# -*- coding: utf-8 -*-
"""rag/vector_text_colab.ipynb 를 만든다.

**재는 것 하나 — 벡터 검색이 왜 BM25 에 30%p 지는가.**

2026-08-06 Colab 실측:

    BM25    R@5 75.1%
    BGE-M3  R@5 45.2%      ← 30%p 차이
    ME5     R@5 36.2%
    하이브리드 R@5 59.6%      ← BM25 단독보다 나쁘다

**모델을 바꿔도 똑같이 나쁘니 모델 문제가 아니다.** 우리가 임베딩에 넣는 텍스트를
봐야 한다. 후보 둘:

  ① 머리 중복 — 청크 6,565개가 **전부** `[규정명] 제N조(제목)` 으로 시작하고,
                거기에 title·article_no 를 앞에 또 붙여 넣고 있다.
                한 규정의 모든 청크가 같은 글자로 시작하면 임베딩이 서로 가까워진다.
  ② 청크가 큼 — 중앙 496자·p90 1,165자. **절반(49%)이 항을 2개 이상 담는다.**
                조문 하나에 의무표시사항 8개가 섞여 있으면 특정 항목 질의와 안 가깝다.

BM25 는 IDF 가 흔한 말의 무게를 낮춰 주므로 ①에 둔감하고, 단어가 하나만 겹쳐도
잡히므로 ②에도 둔감하다. 벡터는 둘 다 정통으로 맞는다.

  python rag/_build_colab_nb6.py
"""
import os
import json

MD = "markdown"
PY = "code"

CELLS = []


def add(kind, text):
    CELLS.append((kind, text.strip("\n")))


add(MD, """
# 벡터 검색이 왜 지는가 — 텍스트 변형 A/B (BGE-M3)

지난 실험에서 벡터가 BM25 에 **30%p** 졌다. 모델을 바꿔도(ME5) 마찬가지였으니
**모델이 아니라 우리가 넣는 텍스트가 문제**다. 후보 둘을 한 번에 잰다.

| 변형 | 무엇을 바꾸나 |
|---|---|
| **V0 지금** | `title + article_no + 본문` — 지금 쓰는 것. 45.2% 가 나왔던 것 |
| **V1 본문만** | 앞에 덧붙인 title·article_no 를 뺀다 (본문 첫 줄에 이미 있다) |
| **V2 규정명 제거** | 본문 첫머리의 `[규정명]` 까지 뺀다. 6,565개가 **전부** 이걸로 시작한다 |
| **V3 항 단위 분할** | 조문을 `①②③` 경계로 쪼개 각각 임베딩. 절반(49%)이 항 2개 이상 |

V3 는 조각으로 찾되 **원래 조문이 맞으면 맞은 것**으로 센다 — 사람은 조문을 찾는
것이지 조각을 찾는 것이 아니다.

**런타임:** `런타임 → 런타임 유형 변경 → T4 GPU`
**입력 2개:** `chunks.jsonl` · `gold.json`
**출력:** `vector_text_report.md`
""")

add(MD, "## 1. 환경")
add(PY, """
!nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || echo "GPU 없음"
!pip -q install -U sentence-transformers 2>&1 | tail -1
""")

add(MD, "## 2. 파일 업로드 — `chunks.jsonl` · `gold.json`")
add(PY, """
from google.colab import files
import os, json, re
up = files.upload()
for n in up:
    print(f"{n:20s} {len(up[n])/1e6:6.1f}MB")
assert all(os.path.exists(n) for n in ("chunks.jsonl", "gold.json"))
""")

add(MD, """
## 3. 변형 만들기

V3 의 분할 규칙: 항 기호(`①`~`⑮`)가 **2개 이상**일 때만 쪼갠다. 하나뿐이면 쪼개도
의미가 없고 조각만 늘어난다. 조각 앞에는 조문 제목을 붙여 맥락을 남긴다 —
「② 제2항 내용」만으로는 무슨 조문의 항인지 알 수 없다.
""")
add(PY, r"""
# 셀마다 필요한 것을 직접 가져온다. 업로드 셀(2번)은 파일이 이미 있으면 건너뛰게
# 되는 자리라, 거기 있는 import 에 기대면 NameError 로 죽는다.
import json, re

chunks = [json.loads(l) for l in open("chunks.jsonl", encoding="utf-8")]
gold = json.load(open("gold.json", encoding="utf-8"))
print(f"청크 {len(chunks):,} · gold {len(gold)}건")

_HEAD = re.compile(r"^\[[^\]]{1,60}\]\s*")     # 「[금융투자회사의 …] 」
_HANG = re.compile(r"(?=[①-⑮])")

def v0(c):  # 지금 쓰는 것
    return f"{c['reg']} {c.get('key','')} {c.get('title','')} {c['text']}"

def v1(c):  # 본문만
    return c["text"]

def v2(c):  # 본문 첫머리의 [규정명] 까지 제거
    return _HEAD.sub("", c["text"], count=1)

def v3_parts(c):
    # (조각 텍스트 목록). 항이 2개 이상일 때만 쪼갠다.
    body = _HEAD.sub("", c["text"], count=1)
    if len(re.findall(r"[①-⑮]", body)) < 2:
        return [body]
    head, *rest = _HANG.split(body)
    lead = f"{c.get('title','')} {c.get('key','')}".strip()
    out = []
    if head.strip():
        out.append(head.strip())
    # 조각마다 조문 제목을 붙인다. 「② …」만으로는 무슨 조문인지 알 수 없다.
    out += [f"{lead} {p.strip()}" for p in rest if p.strip()]
    return out

VARIANTS = {}
for name, fn in (("V0 지금", v0), ("V1 본문만", v1), ("V2 규정명 제거", v2)):
    VARIANTS[name] = {"text": [fn(c) for c in chunks],
                      "owner": list(range(len(chunks)))}   # 조각 → 원래 청크 번호

txt, owner = [], []
for i, c in enumerate(chunks):
    for p in v3_parts(c):
        txt.append(p); owner.append(i)
VARIANTS["V3 항 단위"] = {"text": txt, "owner": owner}

for k, v in VARIANTS.items():
    L = sorted(len(t) for t in v["text"])
    print(f"  {k:12s} {len(v['text']):>6,}조각 · 길이 중앙 {L[len(L)//2]:>5} · "
          f"p90 {L[int(len(L)*.9)]:>5}")
""")

add(MD, """
## 4. 임베딩

BGE-M3 로 통일한다(지난 실험에서 ME5 보다 전 항목 우세). 조각 수가 변형마다 다르니
합계는 3만 안팎, T4 로 15분쯤 걸린다.
""")
add(PY, """
import numpy as np, torch, gc
from sentence_transformers import SentenceTransformer

dev = "cuda" if torch.cuda.is_available() else "cpu"
m = SentenceTransformer("BAAI/bge-m3", device=dev)
m.max_seq_length = 1024

import time

def embed(texts, bs=64, tag=""):
    # **진행바를 끈다.** 조각이 3만 7천 개라 tqdm 이 출력을 쏟아내면 브라우저가
    # 렉에 걸린다 — 계산이 느린 게 아니라 화면이 못 따라가는 것이다.
    # 대신 2,000개마다 한 줄만 찍는다.
    out, t0, step = [], time.time(), 2000
    for s in range(0, len(texts), step):
        out.append(m.encode(texts[s:s+step], batch_size=bs,
                            convert_to_numpy=True, show_progress_bar=False))
        done = min(s + step, len(texts))
        print(f"  {tag} {done:>6,}/{len(texts):,}  {time.time()-t0:5.0f}초")
    v = np.vstack(out).astype("float32")
    return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)

qvec = embed([g["q"] for g in gold], tag="질의")
for name, v in VARIANTS.items():
    print(f"\\n{name} — {len(v['text']):,}조각")
    v["vec"] = embed(v["text"], tag=name)
    gc.collect(); torch.cuda.empty_cache()
""")

add(MD, """
## 5. 채점

조각으로 찾되 **원래 청크 번호로 환산해서** 센다. V3 는 한 조문이 여러 조각으로
나뉘므로 조각 순위를 청크 순위로 접어야 다른 변형과 비교가 성립한다 — 같은 조문의
조각이 1·2·3위를 차지했다면 그 조문은 1위 하나로 센다.
""")
add(PY, """
import numpy as np

KS = (1, 3, 5, 10)

def score(v):
    owner = np.asarray(v["owner"])
    sim = qvec @ v["vec"].T                 # (질의, 조각)
    hit = {k: 0 for k in KS}; mrr = 0.0
    for j, g in enumerate(gold):
        ans = set(g["정답청크"])
        seen, ranked = set(), []
        for d in np.argsort(-sim[j])[:400]:  # 조각을 넉넉히 보고 청크로 접는다
            o = int(owner[d])
            if o not in seen:
                seen.add(o); ranked.append(o)
            if len(ranked) >= 20:
                break
        p = next((r for r, o in enumerate(ranked, 1) if o in ans), None)
        for k in KS:
            if p and p <= k: hit[k] += 1
        mrr += 1/p if p else 0
    n = len(gold)
    return {f"R@{k}": hit[k]/n for k in KS} | {"MRR": mrr/n}

rows = []
for name, v in VARIANTS.items():
    s = score(v)
    rows.append((name, len(v["text"]), s))
    print(f"{name:12s} {len(v['text']):>6,}조각  " +
          " · ".join(f"R@{k} {s[f'R@{k}']*100:5.1f}%" for k in KS) +
          f" · MRR {s['MRR']:.3f}")
""")

add(MD, """
## 6. 보고서

**BM25 가 R@5 75.1% 다.** 어느 변형도 이걸 못 넘으면 벡터는 당분간 안 쓰는 게 맞고,
넘거나 근접하면 하이브리드를 되살릴 값어치가 있다.
""")
add(PY, """
import json

lines = ["# 벡터 검색 텍스트 변형 A/B — BGE-M3", "",
         f"청크 {len(chunks):,} · gold {len(gold)}건", "",
         "| 변형 | 조각 수 | R@1 | R@3 | R@5 | R@10 | MRR |",
         "|---|---:|---:|---:|---:|---:|---:|"]
for name, n, s in rows:
    lines.append(f"| {name} | {n:,} | " +
                 " | ".join(f"{s[f'R@{k}']*100:.1f}%" for k in KS) +
                 f" | {s['MRR']:.3f} |")
lines += ["", "## 비교 기준", "",
          "| | R@1 | R@5 | R@10 | MRR |", "|---|---:|---:|---:|---:|",
          "| BM25 (조문만) | 34.4% | 75.1% | 79.0% | 0.515 |",
          "| 벡터 V0 (지난 실험) | 24.3% | 45.2% | 56.3% | 0.336 |", "",
          "V0 가 45.2% 근처로 재현되어야 조건이 같다는 뜻이다."]
open("vector_text_report.md", "w", encoding="utf-8").write("\\n".join(lines))
print("\\n".join(lines))

from google.colab import files
files.download("vector_text_report.md")
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
                       "vector_text_colab.ipynb")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(nb, f, ensure_ascii=False, indent=1)
    print(f"셀 {len(CELLS)}개 → {out}")


if __name__ == "__main__":
    main()
