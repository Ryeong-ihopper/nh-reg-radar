# -*- coding: utf-8 -*-
"""rag/model_eval_colab.ipynb — Qwen3 vs BGE 임베딩·리랭커를 gold 103건으로 비교.

  python rag/_build_colab_nb4.py
"""
import os
import json

MD, PY = "markdown", "code"
CELLS = []


def add(kind, text):
    CELLS.append((kind, text.strip("\n")))


add(MD, """
# 임베딩·리랭커 비교 — Qwen3 vs BGE (gold 103건)

지금까지는 MTEB 점수로 골랐다. 이제 **우리 과제로 직접 잰다.**

준법감시부 체크리스트·심의사례에서 뽑은 gold 103건이 있다. 「이자율·수익률의 범위 및
산출기준을 표시하였는가?」 → 「은행 광고심의 기준 및 세칙 제16조」처럼 질의와 정답
조문이 짝지어져 있고, 사람이 만든 공식 매핑이라 내가 지어낸 정답이 아니다.

## 왜 BGE 를 다시 보는가

| | BGE-M3 | Qwen3-Embedding-8B |
|---|---|---|
| 파라미터 | **568M** | 8B (14배) |
| VRAM | **~2.3GB** | 16GB (FP8 8GB) |
| CPU 서빙 | **현실적** | 사실상 불가 |
| MTEB 다국어 | ~59 | **70.58** |

공유 GPU 라 VRAM 차이가 크고, 기존 `rag_spark` 파이프라인이 이미 BGE 를 쓴다.
**점수가 비슷하게만 나오면 BGE 가 유리하다.** 벤치마크 격차가 우리 과제에서도
그대로인지가 이번에 볼 것이다.

## 기준선

로컬에서 잰 BM25 단독: **R@10 78.6% · MRR 0.474**

**런타임을 A100 으로** 바꾸고 시작한다.
""")

add(MD, "## 1. GPU · 설치")
add(PY, """
!nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv
!pip -q install -U "sentence-transformers>=3.3" faiss-cpu
""")

add(MD, """
## 2. 업로드

| 파일 | 위치 | 비고 |
|---|---|---|
| `chunks.jsonl` | `output/_rag/` | |
| `gold.json` | `output/_rag/` | 정답 103건 |
| `bm25.pkl` | `output/_rag/` | |
| `bm25.py` | `rag/` | 토크나이저를 색인 때와 같게 쓰려고 |
| `evaluate.py` | `rag/` | 지표 계산을 로컬과 같게 쓰려고 |
| `embeddings.f16.npy` | `output/_rag/` | Qwen3-8B 문서벡터 — **다시 안 만든다** |
""")
add(PY, """
from google.colab import files
up = files.upload()
for k, v in up.items():
    print(f"{k:24s} {len(v):>12,} B")
""")

add(MD, "## 3. 적재")
add(PY, """
import json, pickle, sys, numpy as np, faiss, collections
sys.path.insert(0, ".")
import bm25 as BM
import evaluate as EV

rows = [json.loads(l) for l in open("chunks.jsonl", encoding="utf-8")]
gold = json.load(open("gold.json", encoding="utf-8"))
bm_idx = pickle.load(open("bm25.pkl", "rb"))
texts = [r["text"] for r in rows]
queries = [g["q"] for g in gold]

assert bm_idx["N"] == len(rows), "BM25 인덱스와 청크 수 불일치"
print(f"청크 {len(rows):,} · gold {len(gold)} · BM25 어휘 {len(bm_idx['idf']):,}")
print("정답 규정 상위:", collections.Counter(
    a["reg"] for g in gold for a in g["정답"]).most_common(4))
""")

add(MD, """
## 4. BM25 기준선 — 로컬과 같은 값이 나와야 한다

같은 인덱스·같은 코드라 결과가 같아야 정상이다. 다르면 업로드가 어긋난 것이므로
여기서 멈추고 확인한다.
""")
add(PY, """
RANK = {}          # 구성 이름 → {gold_id: [청크번호 …]}
K = 50

RANK["BM25"] = {g["id"]: [i for i, _ in BM.search(g["q"], K, bm_idx)] for g in gold}
_ = EV.report("BM25 단독", gold, RANK["BM25"], (1, 5, 10, 20), show_miss=0)
print("\\n로컬 실측: R@10 78.6% · MRR 0.474  ← 이 값과 같아야 한다")
""")

add(MD, """
## 5. 임베딩 두 종으로 문서·질의 벡터 만들기

Qwen3-8B 는 이미 만들어 둔 것을 쓰고, BGE-M3 만 새로 만든다.

**질의 처리 방식이 다르다.** Qwen3 는 질의에만 `Instruct:` 접두어를 붙이는 비대칭
구조라 `prompt_name="query"` 가 필요하고, BGE-M3 는 대칭이라 그냥 넣는다.
여기를 맞추지 않으면 한쪽에 불리하게 재게 된다.
""")
add(PY, """
from sentence_transformers import SentenceTransformer
import torch, gc, time

def index_of(mat):
    x = mat.astype(np.float32)
    ix = faiss.IndexFlatIP(x.shape[1]); ix.add(x)
    return ix

VEC = {}     # 이름 → (문서인덱스, 질의벡터)

# ── Qwen3-Embedding-8B : 문서벡터는 재사용, 질의만 새로 ──────────────
q8 = SentenceTransformer("Qwen/Qwen3-Embedding-8B",
                         model_kwargs={"torch_dtype": torch.float16},
                         tokenizer_kwargs={"padding_side": "left"})
q8.max_seq_length = 2560
qv = q8.encode(queries, prompt_name="query", batch_size=8,
               normalize_embeddings=True, convert_to_numpy=True,
               show_progress_bar=True).astype(np.float32)
VEC["Qwen3-8B"] = (index_of(np.load("embeddings.f16.npy")), qv)
del q8; gc.collect(); torch.cuda.empty_cache()
print("Qwen3-8B 준비 · 여유 "
      f"{(torch.cuda.get_device_properties(0).total_memory - torch.cuda.memory_allocated())/1e9:.1f}GB")

# ── BGE-M3 : 문서·질의 모두 새로 (568M 이라 금방 끝난다) ─────────────
t0 = time.time()
bge = SentenceTransformer("BAAI/bge-m3", model_kwargs={"torch_dtype": torch.float16})
bge.max_seq_length = 2560
dv = bge.encode(texts, batch_size=64, normalize_embeddings=True,
                convert_to_numpy=True, show_progress_bar=True).astype(np.float32)
qv2 = bge.encode(queries, batch_size=64, normalize_embeddings=True,
                 convert_to_numpy=True).astype(np.float32)
VEC["BGE-M3"] = (index_of(dv), qv2)
np.save("bge_m3.f16.npy", dv.astype(np.float16))
del bge; gc.collect(); torch.cuda.empty_cache()
print(f"BGE-M3 준비 · {time.time()-t0:.0f}초 · 차원 {dv.shape[1]}")
""")

add(MD, """
## 6. 벡터 단독 · 하이브리드(+BM25)

RRF 로 합친다. 점수 척도가 달라(코사인 vs BM25 점수) 그대로 더하면 안 되고,
순위의 역수를 더한다.
""")
add(PY, """
def rrf(lists, k=60):
    sc = {}
    for lst in lists:
        for rank, i in enumerate(lst, 1):
            sc[i] = sc.get(i, 0.0) + 1.0 / (k + rank)
    return [i for i, _ in sorted(sc.items(), key=lambda x: -x[1])]

for name, (ix, qv) in VEC.items():
    _, I = ix.search(qv, K)
    RANK[name] = {g["id"]: I[n].tolist() for n, g in enumerate(gold)}
    RANK[f"{name}+BM25"] = {g["id"]: rrf([RANK[name][g["id"]], RANK["BM25"][g["id"]]])[:K]
                            for g in gold}

for n in ("Qwen3-8B", "Qwen3-8B+BM25", "BGE-M3", "BGE-M3+BM25"):
    EV.report(n, gold, RANK[n], (1, 5, 10, 20), show_miss=0)
""")

add(MD, """
## 7. 리랭커 두 종

같은 계열끼리만 붙인다(Qwen3 임베딩 → Qwen3 리랭커, BGE → BGE).
**두 리랭커는 쓰는 법이 완전히 다르다.**

- **Qwen3-Reranker** — 인과 LM. 「만족하는가」를 yes/no 로 묻고 두 토큰의 로짓으로
  점수를 낸다. 마지막 토큰 로짓만 계산하지 않으면 어휘 152k × 전 위치라 OOM 이 난다
  (실측: A100 40GB 에서 터졌다).
- **bge-reranker-v2-m3** — 일반 크로스 인코더. `CrossEncoder.predict()` 한 줄.

하이브리드 상위 30개를 재정렬한다.
""")
add(PY, """
from transformers import AutoTokenizer, AutoModelForCausalLM
from sentence_transformers import CrossEncoder
import inspect, torch, gc

RR_N = 30

def apply_rr(base, fn, tag):
    out = {}
    for n, g in enumerate(gold):
        cand = RANK[base][g["id"]][:RR_N]
        sc = fn(g["q"], cand)
        out[g["id"]] = [i for i, _ in sorted(zip(cand, sc), key=lambda x: -x[1])]
        if (n + 1) % 40 == 0:
            print(f"  {tag} {n+1}/{len(gold)}")
    return out

# ── Qwen3-Reranker-0.6B ────────────────────────────────────────────
rt = AutoTokenizer.from_pretrained("Qwen/Qwen3-Reranker-0.6B", padding_side="left")
rm = AutoModelForCausalLM.from_pretrained("Qwen/Qwen3-Reranker-0.6B",
                                          torch_dtype=torch.float16).cuda().eval()
YES, NO = rt.convert_tokens_to_ids("yes"), rt.convert_tokens_to_ids("no")
PRE = rt.encode('<|im_start|>system\\nJudge whether the Document meets the requirements '
                'based on the Query and the Instruct provided. Note that the answer can '
                'only be "yes" or "no".<|im_end|>\\n<|im_start|>user\\n',
                add_special_tokens=False)
SUF = rt.encode('<|im_end|>\\n<|im_start|>assistant\\n<think>\\n\\n</think>\\n\\n',
                add_special_tokens=False)
_p = inspect.signature(rm.forward).parameters
KEEP = ("logits_to_keep" if "logits_to_keep" in _p
        else "num_logits_to_keep" if "num_logits_to_keep" in _p else None)
INSTRUCT = ("은행 광고 심의 점검항목에 대해, 그 점검의 근거가 되는 법령·규정 조문인지 "
            "판단하라. 내용이 비슷해도 다른 업권에만 적용되는 규정이면 적합하지 않다.")

@torch.no_grad()
def qwen_rr(q, cand, batch=16):
    pairs = [f"<Instruct>: {INSTRUCT}\\n<Query>: {q}\\n<Document>: {rows[i]['text']}"
             for i in cand]
    out = []
    for s in range(0, len(pairs), batch):
        e = rt(pairs[s:s+batch], padding=False, truncation="longest_first",
               return_attention_mask=False, max_length=1024 - len(PRE) - len(SUF))
        e["input_ids"] = [PRE + x + SUF for x in e["input_ids"]]
        e = rt.pad(e, padding=True, return_tensors="pt")
        e = {k: v.to(rm.device) for k, v in e.items()}
        lg = rm(**e, **({KEEP: 1} if KEEP else {})).logits[:, -1, :]
        two = torch.stack([lg[:, NO], lg[:, YES]], dim=1)
        out += torch.nn.functional.log_softmax(two, dim=1)[:, 1].exp().tolist()
        del e, lg, two
    return out

# 같은 계열끼리만 — 교차 조합은 재지 않는다(BGE 채택이 사실상 확정이라
# "Qwen 임베딩 + BGE 리랭커" 같은 조합은 쓸 일이 없다). 리랭커 실행이 4회→2회로 준다.
RANK["Qwen3-8B+BM25+QwenRR"] = apply_rr("Qwen3-8B+BM25", qwen_rr, "QwenRR")
del rm; gc.collect(); torch.cuda.empty_cache()

# ── bge-reranker-v2-m3 ─────────────────────────────────────────────
ce = CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=1024, device="cuda")
def bge_rr(q, cand):
    return ce.predict([(q, rows[i]["text"]) for i in cand], batch_size=32).tolist()

RANK["BGE-M3+BM25+BgeRR"] = apply_rr("BGE-M3+BM25", bge_rr, "BgeRR")
del ce; gc.collect(); torch.cuda.empty_cache()
print("리랭킹 완료")
""")

add(MD, """
## 8. 전체 비교표

**교차 조합(Qwen3 임베딩 + BGE 리랭커 등)은 재지 않는다.** BGE 채택이 사실상
확정이라 실제로 쓸 일이 없고, 설계 문서의 「임베딩과 리랭커를 같은 계열로 묶는다」는
원칙과도 어긋난다. Qwen3 줄은 **비교 기준으로만** 남긴다 — 무엇을 포기하는지
숫자로 남겨 두어야 나중에 되짚을 수 있다.
""")
add(PY, """
order = ["BM25",
         "Qwen3-8B", "Qwen3-8B+BM25", "Qwen3-8B+BM25+QwenRR",
         "BGE-M3", "BGE-M3+BM25", "BGE-M3+BM25+BgeRR"]
res = {}
for n in order:
    if n in RANK:
        res[n], _ = EV.score(gold, RANK[n], (1, 5, 10, 20))

hdr = f"{'구성':30s} {'R@1':>7s} {'R@5':>7s} {'R@10':>7s} {'R@20':>7s} {'MRR':>7s}"
print(hdr); print("-" * len(hdr))
lines = ["| 구성 | R@1 | R@5 | R@10 | R@20 | MRR |", "|---|---|---|---|---|---|"]
for n, m in res.items():
    print(f"{n:30s} {m['R@1']*100:6.1f}% {m['R@5']*100:6.1f}% "
          f"{m['R@10']*100:6.1f}% {m['R@20']*100:6.1f}% {m['MRR']:7.3f}")
    lines.append(f"| {n} | {m['R@1']*100:.1f}% | {m['R@5']*100:.1f}% | "
                 f"{m['R@10']*100:.1f}% | {m['R@20']*100:.1f}% | {m['MRR']:.3f} |")

open("model_eval_report.md", "w", encoding="utf-8").write(
    "# 임베딩·리랭커 비교 (gold 103건)\\n\\n" + "\\n".join(lines) + "\\n")
print("\\n저장: model_eval_report.md")
""")

add(MD, "## 9. 내려받기")
add(PY, """
from google.colab import files
files.download("model_eval_report.md")
files.download("bge_m3.f16.npy")     # BGE 가 이기면 그대로 쓴다
""")

add(MD, """
---

## 읽는 법

- **BGE-M3 가 Qwen3-8B 에 근접하면 BGE 로 간다.** VRAM 7분의 1, sparse 내장(BM25 를
  따로 안 만들어도 된다), 기존 `rag_spark` 와 연속성 — 점수가 같다면 전부 BGE 쪽 이점이다
- **격차가 크면 Qwen3 를 유지한다.** MTEB 격차(70.58 vs ~59)가 우리 과제에도
  그대로라는 뜻이다
- **리랭커가 MRR 만 올리고 R@10 은 그대로면** 정상이다. 순서를 고치는 단계라
  후보에 없던 것을 만들어 내지는 못한다
""")


def main():
    nb = {"cells": [{"cell_type": k, "metadata": {},
                     **({"source": t.splitlines(keepends=True), "outputs": [],
                         "execution_count": None} if k == PY else
                        {"source": t.splitlines(keepends=True)})}
                    for k, t in CELLS],
          "metadata": {"colab": {"provenance": [], "gpuType": "A100"},
                       "accelerator": "GPU",
                       "kernelspec": {"name": "python3", "display_name": "Python 3"},
                       "language_info": {"name": "python"}},
          "nbformat": 4, "nbformat_minor": 0}
    dest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model_eval_colab.ipynb")
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(nb, f, ensure_ascii=False, indent=1)
    print(f"생성: {dest}  (셀 {len(CELLS)}개)")


if __name__ == "__main__":
    main()
