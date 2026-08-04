# -*- coding: utf-8 -*-
"""rag/search_ab_colab.ipynb 를 만든다. (A)원문 · (B)쟁점질의 · (D)광고청킹 · (C)병합 비교용.

노트북 JSON 을 손으로 쓰면 이스케이프에서 사고가 나서, 셀 내용을 파이썬 문자열로
두고 여기서 조립한다. 고칠 일이 있으면 이 파일을 고치고 다시 실행한다.

  python rag/_build_colab_nb2.py
"""
import os
import json

MD, PY = "markdown", "code"
CELLS = []


def add(kind, text):
    CELLS.append((kind, text.strip("\n")))


add(MD, """
# 검색 방식 비교 — (A) 원문 · (B) 쟁점질의 · (D) 광고청킹 · (C) 병합

1차 파일럿에서 쓴 질의는 사람이 던지는 질문(「광고에 반드시 포함해야 하는 필수 표기
사항」)이었는데, **실제 입력은 광고 원문 그대로**다. 마케팅 문구와 법령 문어체는
어휘가 거의 안 겹치고, 광고 하나에 쟁점이 열 개씩 들어 있어 통째로 벡터 하나에
넣으면 뭉개진다. 그래서 세 방식을 나란히 재서 중간 단계(질의 생성)가 값어치가
있는지 실측으로 가린다.

| | 질의 | 만드는 법 | 개수 |
|---|---|---|---|
| **A** | 광고 원문 그대로 | 없음 | 17 |
| **B** | 광고를 읽고 쓴 쟁점 질의 | LLM 이 광고 내용을 보고 작성 · **법령체** | 119 |
| **D** | 광고를 조각낸 것 | 구조 표시(□※▶)로 자름 · **광고 말 그대로** | 182 |
| **C** | A+B+D 를 RRF 로 병합 | — | — |

(B)와 (D)는 같은 "쟁점별로 나눠 던진다"인데 **어휘를 바꾸느냐**가 다르다.
(B)는 어휘 격차를 없애는 대신 LLM 이 필요하고 원문 정보가 일부 날아간다.
(B)는 광고마다 다르다 — 「우대이율 조건이 프로야구단 성적인 경우」처럼 그 광고의
상황을 쓴다. 항목 이름만 나열하면 광고가 달라도 질의가 같아져 비교가 성립하지 않는다.
(D)는 LLM 이 필요 없고 원문이 온전한 대신 마케팅 문구 그대로라 격차가 남는다.

**런타임을 A100 으로** 바꾸고 시작한다.

문서 임베딩은 1차에서 이미 만들어 두었으므로 **다시 계산하지 않는다** —
`embeddings.f16.npy` 를 올려 인덱스만 복원하고, 질의 318개만 새로 임베딩한다.
""")

add(MD, "## 1. GPU 확인")
add(PY, """
!nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv
""")

add(MD, "## 2. 설치")
add(PY, """
!pip -q install -U "sentence-transformers>=3.3" faiss-cpu
import sentence_transformers, torch
print("sentence-transformers", sentence_transformers.__version__,
      "· CUDA", torch.cuda.is_available())
""")

add(MD, """
## 3. 파일 업로드

네 개를 한 번에 고른다.

| 파일 | 위치 | 크기 |
|---|---|---|
| `embeddings.f16.npy` | `output/_rag/` | 62MB |
| `chunks.jsonl` | `output/_rag/` | 13MB |
| `ad_queries.json` | `output/_rag/` | 작음 |
| `ad_chunks.jsonl` | `output/_rag/` | 작음 |

> `chunks.faiss`(123MB)는 **안 올린다.** `embeddings.f16.npy` 로 즉시 복원되므로
> 두 배 크기를 올릴 이유가 없다.
""")
add(PY, """
from google.colab import files
up = files.upload()
for k, v in up.items():
    print(f"{k:26s} {len(v):>12,} B")
""")

add(MD, """
## 4. 적재 · 인덱스 복원

FP16 으로 저장한 벡터를 FP32 로 되돌려 인덱스를 만든다. 저장할 때만 반으로 줄인
것이라 검색 결과는 1차와 같다(정규화된 벡터의 FP16 오차는 코사인 6자리 아래).
""")
add(PY, """
import json, numpy as np, faiss, collections

rows = [json.loads(l) for l in open("chunks.jsonl", encoding="utf-8")]
ads  = json.load(open("ad_queries.json", encoding="utf-8"))
adcs = [json.loads(l) for l in open("ad_chunks.jsonl", encoding="utf-8")]

emb = np.load("embeddings.f16.npy").astype(np.float32)
index = faiss.IndexFlatIP(emb.shape[1])
index.add(emb)

nB = sum(len(a["B_쟁점질의"]) for a in ads)
print(f"청크 {len(rows):,} · 인덱스 {index.ntotal:,} · {emb.shape[1]}차원")
print(f"광고 {len(ads)}건 — (A) {len(ads)} · (B) {nB} · (D) {len(adcs)}개 질의")
print(collections.Counter(a["상품군"] for a in ads).most_common())
""")

add(MD, """
## 5. 모델 적재
""")
add(PY, """
from sentence_transformers import SentenceTransformer
import torch

model = SentenceTransformer(
    "Qwen/Qwen3-Embedding-8B",
    model_kwargs={"torch_dtype": torch.float16},
    tokenizer_kwargs={"padding_side": "left"},
)
model.max_seq_length = 2560          # 광고 최대 2,446자 · 청크 최대 2,114토큰
print("차원:", model.get_sentence_embedding_dimension())
""")

add(MD, """
## 6. 질의 임베딩

**질의에는 `prompt_name="query"` 를 준다.** Qwen3-Embedding 은 질의 쪽에만
`Instruct:` 접두어를 붙이는 비대칭 구조라, 빼먹으면 성능이 눈에 띄게 떨어진다.

광고 원문(A)도 질의 자리에 들어가므로 같은 처리를 한다 — 실제 서비스에서
광고가 질의로 들어가는 것과 같은 조건이어야 비교가 성립한다.
""")
add(PY, """
import numpy as np, time

pos = {a["광고id"]: i for i, a in enumerate(ads)}

qa = [a["A_원문"] for a in ads]
qb, qb_owner = [], []
for i, a in enumerate(ads):
    for q in a["B_쟁점질의"]:
        qb.append(q["q"]); qb_owner.append(i)
qd = [c["text"] for c in adcs]
qd_owner = [pos[c["광고id"]] for c in adcs]

t0 = time.time()
va = model.encode(qa, prompt_name="query", batch_size=4,
                  normalize_embeddings=True, convert_to_numpy=True,
                  show_progress_bar=True).astype(np.float32)
vb = model.encode(qb, prompt_name="query", batch_size=16,
                  normalize_embeddings=True, convert_to_numpy=True,
                  show_progress_bar=True).astype(np.float32)
vd = model.encode(qd, prompt_name="query", batch_size=16,
                  normalize_embeddings=True, convert_to_numpy=True,
                  show_progress_bar=True).astype(np.float32)
print(f"\\nA {va.shape} · B {vb.shape} · D {vd.shape} · {time.time()-t0:.0f}초")
""")

add(MD, """
## 7. 검색 · RRF 병합

**RRF(Reciprocal Rank Fusion)** — 여러 질의의 결과를 합칠 때 점수를 그대로 더하면
질의마다 점수 범위가 달라 한쪽이 판을 지배한다. 순위의 역수(`1/(k+순위)`)를 더하면
점수 척도와 무관해진다. `k=60` 은 관례값이다.

(B)·(D)는 광고당 질의가 여럿이라 각각 RRF 로 합치고, (C)는 그 셋을 다시 RRF 로 합친다.
""")
add(PY, """
K_RRF, TOPK = 60, 20

def topk(vec, k=TOPK):
    s, i = index.search(vec.reshape(1, -1), k)
    return list(zip(i[0].tolist(), s[0].tolist()))

def rrf(rank_lists, k=K_RRF):
    sc = {}
    for lst in rank_lists:
        for rank, (idx, _) in enumerate(lst, 1):
            sc[idx] = sc.get(idx, 0.0) + 1.0 / (k + rank)
    return sorted(sc.items(), key=lambda x: -x[1])

results = []
for i, a in enumerate(ads):
    A = topk(va[i])
    B = rrf([topk(vb[j]) for j in range(len(qb)) if qb_owner[j] == i])[:TOPK]
    D = rrf([topk(vd[j]) for j in range(len(qd)) if qd_owner[j] == i])[:TOPK]
    # 병합은 순위만 쓴다 — A 는 코사인, B/D 는 RRF 점수라 척도가 달라 그대로 더하면 안 된다
    C = rrf([A, [(x, 0) for x, _ in B], [(x, 0) for x, _ in D]])
    results.append({"ad": a, "A": A[:10], "B": B[:10], "D": D[:10], "C": C[:10]})
print(f"완료 — 광고 {len(results)}건")
""")

add(MD, """
## 8. 리포트

네 방식이 **서로 다른 것을 찾아오는지**가 핵심이다. 특히 **B∩D** 를 봐야 한다 —
둘 다 "쟁점별로 나눠 던진다"인데, 겹침이 크면 **LLM 으로 법령체 변환을 할 이유가
없다**(구조로 자르는 (D)는 공짜다). 겹침이 작아야 어휘 변환이 값어치를 한다.
""")
add(PY, """
def label(i):
    r = rows[i]
    return f"{r['reg']} — {r['key']} {r['title']}".rstrip()

out = ["# 검색 방식 비교 — (A) 원문 · (B) 쟁점질의 · (D) 광고청킹 · (C) 병합", ""]
ov = {"A∩B": [], "A∩D": [], "B∩D": []}

for res in results:
    a = res["ad"]
    A = [i for i, _ in res["A"]]; B = [i for i, _ in res["B"]]
    D = [i for i, _ in res["D"]]; C = [i for i, _ in res["C"]]
    def pct(x, y):
        return len(set(x) & set(y)) / 10 * 100
    for k, v in (("A∩B", pct(A, B)), ("A∩D", pct(A, D)), ("B∩D", pct(B, D))):
        ov[k].append(v)

    out += [f"## {a['광고id']} ({a['상품군']}, {a['chars']:,}자)", "",
            f"쟁점질의 {len(a['B_쟁점질의'])}개 · 겹침 A∩B {pct(A,B):.0f}% · "
            f"A∩D {pct(A,D):.0f}% · B∩D {pct(B,D):.0f}%", ""]
    out += ["| # | (A) 원문 | (B) 쟁점질의 | (D) 광고청킹 | (C) 병합 |",
            "|---|---|---|---|---|"]
    for n in range(10):
        def cell(L):
            return label(L[n]) if n < len(L) else ""
        out.append(f"| {n+1} | {cell(A)} | {cell(B)} | {cell(D)} | {cell(C)} |")
    out.append("")
    miss = [k for k, v in a["감지"].items() if not v]
    if miss:
        out += [f"> 미검출 항목(누락 의심): {', '.join(miss)}", ""]

    print(f"{a['광고id']:20s} A∩B {pct(A,B):>3.0f}%  A∩D {pct(A,D):>3.0f}%  "
          f"B∩D {pct(B,D):>3.0f}%   A1: {label(A[0])[:36]}")

avg = {k: sum(v) / len(v) for k, v in ov.items()}
hdr = ["", "전체 평균 겹침 — " + " · ".join(f"**{k} {v:.0f}%**" for k, v in avg.items()), ""]
open("search_ab_report.md", "w", encoding="utf-8").write("\\n".join(out[:2] + hdr + out[2:]))
print("\\n평균 겹침 — " + " · ".join(f"{k} {v:.0f}%" for k, v in avg.items()))
print("저장: search_ab_report.md")
""")

add(MD, "## 9. 내려받기")
add(PY, """
from google.colab import files
files.download("search_ab_report.md")
""")

add(MD, """
---

## 읽는 법

- **A∩B·A∩D 가 낮다** → 원문 통짜로는 못 찾는 근거가 있다. 쟁점별로 나눠 던지는
  단계가 필요하다
- **A∩B·A∩D 가 높다(70%+)** → 나누는 수고가 낭비. 원문만으로 충분
- **B∩D 가 높다** → **LLM 을 부를 이유가 없다.** 공짜인 (D)가 같은 결과를 내면
  (B)는 비용만 늘린다
- **B∩D 가 낮다** → 법령체 변환이 실제로 다른 근거를 끌어온다. 그때만 LLM 이 값어치
- **(A) 1위가 엉뚱한데 (B)/(D) 1위가 정확하다** → 뭉개짐이 실재한다는 직접 증거
- 각 광고 아래 `미검출 항목`은 **광고에 없는 문구**다. 심의에서 걸리는 것은 대개
  '쓴 것'이 아니라 '안 쓴 것'이라 여기가 실제 지적 후보다
""")


def main():
    nb = {
        "cells": [
            {"cell_type": k, "metadata": {},
             **({"source": t.splitlines(keepends=True), "outputs": [],
                 "execution_count": None} if k == PY else
                {"source": t.splitlines(keepends=True)})}
            for k, t in CELLS],
        "metadata": {"colab": {"provenance": [], "gpuType": "A100"},
                     "accelerator": "GPU",
                     "kernelspec": {"name": "python3", "display_name": "Python 3"},
                     "language_info": {"name": "python"}},
        "nbformat": 4, "nbformat_minor": 0,
    }
    dest = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "search_ab_colab.ipynb")
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(nb, f, ensure_ascii=False, indent=1)
    print(f"생성: {dest}  (셀 {len(CELLS)}개)")


if __name__ == "__main__":
    main()
