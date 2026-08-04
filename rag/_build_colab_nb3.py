# -*- coding: utf-8 -*-
"""rag/pipeline_colab.ipynb 를 만든다 — 벡터+BM25 → RRF → 리랭커 전 과정.

  python rag/_build_colab_nb3.py
"""
import os
import json

MD, PY = "markdown", "code"
CELLS = []


def add(kind, text):
    CELLS.append((kind, text.strip("\n")))


add(MD, """
# 전체 파이프라인 측정 — 벡터 + BM25 → RRF → 리랭커

설계(`docs/SERVING_ARCHITECTURE.md` §4)대로 조회 경로를 끝까지 붙여서 잰다.

```
질의 (B 쟁점질의 · D 광고청킹)
   ├─ 벡터 검색 (Qwen3-Embedding-8B) ── 상위 30
   └─ BM25 (로컬에서 만든 인덱스) ───── 상위 30
        ↓ RRF 병합 → 후보 ~40
        ↓ Qwen3-Reranker-0.6B 재정렬
      최종 상위 10
```

## 이번에 답할 것

앞 회차에서 **업권이 새는 문제**가 나왔다. NH**농협은행** 광고인데 상위 10개의
**52.9%가 여신전문금융(카드·캐피탈) 규정**이었다. 내용은 비슷하지만 은행을
구속하지 않아서, 그대로 인용하면 틀린 근거가 된다.

- 리랭커가 이걸 잡아 주는가? (크로스 인코더는 질의와 문서를 같이 읽으므로 여지가 있다)
- BM25 를 붙이면 번호 질의 말고 일반 질의도 나아지는가?
- 단계마다 업권 분포가 어떻게 변하는가

**런타임을 A100 으로** 바꾸고 시작한다.
""")

add(MD, "## 1. GPU 확인")
add(PY, """
!nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv
""")

add(MD, "## 2. 설치")
add(PY, """
!pip -q install -U "sentence-transformers>=3.3" faiss-cpu
import torch, sentence_transformers
print("CUDA", torch.cuda.is_available(), "· ST", sentence_transformers.__version__)
""")

add(MD, """
## 3. 파일 업로드

여섯 개를 한 번에 고른다. `bm25.py` 는 **토크나이저를 색인 때와 똑같이 쓰기 위해**
올린다 — 노트북에 복사해 넣으면 로컬에서 규칙을 고쳤을 때 조용히 어긋난다.

| 파일 | 위치 |
|---|---|
| `embeddings.f16.npy` | `output/_rag/` |
| `chunks.jsonl` | `output/_rag/` |
| `ad_queries.json` | `output/_rag/` |
| `ad_chunks.jsonl` | `output/_rag/` |
| `bm25.pkl` | `output/_rag/` |
| `bm25.py` | `rag/` |
""")
add(PY, """
from google.colab import files
up = files.upload()
for k, v in up.items():
    print(f"{k:24s} {len(v):>12,} B")
""")

add(MD, """
## 4. 적재
""")
add(PY, """
import json, pickle, numpy as np, faiss, collections, sys
sys.path.insert(0, ".")
import bm25 as BM

rows = [json.loads(l) for l in open("chunks.jsonl", encoding="utf-8")]
ads  = json.load(open("ad_queries.json", encoding="utf-8"))
adcs = [json.loads(l) for l in open("ad_chunks.jsonl", encoding="utf-8")]
bm_idx = pickle.load(open("bm25.pkl", "rb"))

emb = np.load("embeddings.f16.npy").astype(np.float32)
index = faiss.IndexFlatIP(emb.shape[1])
index.add(emb)

assert bm_idx["N"] == len(rows), "BM25 인덱스와 청크 수가 다릅니다 — 같은 chunks.jsonl 로 만들었는지 확인"
print(f"청크 {len(rows):,} · 벡터 {index.ntotal:,} · BM25 문서 {bm_idx['N']:,} · 어휘 {len(bm_idx['idf']):,}")
print(f"광고 {len(ads)}건 · 광고조각 {len(adcs)}개")
""")

add(MD, """
## 5. 모델 적재 — 임베딩 + 리랭커

**Qwen3-Reranker 는 임베딩 모델과 쓰는 법이 다르다.** 인과 LM 구조라 「이 문서가
질의를 만족하는가」를 yes/no 로 묻고 그 두 토큰의 로짓 차이를 점수로 쓴다.
`SentenceTransformer` 로 불러오면 안 되고 `AutoModelForCausalLM` 이어야 한다.
""")
add(PY, """
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

embed = SentenceTransformer(
    "Qwen/Qwen3-Embedding-8B",
    model_kwargs={"torch_dtype": torch.float16},
    tokenizer_kwargs={"padding_side": "left"})
embed.max_seq_length = 2560

rr_tok = AutoTokenizer.from_pretrained("Qwen/Qwen3-Reranker-0.6B", padding_side="left")
rr = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen3-Reranker-0.6B", torch_dtype=torch.float16).cuda().eval()

TRUE_ID  = rr_tok.convert_tokens_to_ids("yes")
FALSE_ID = rr_tok.convert_tokens_to_ids("no")
RR_MAX = 1024

# 마지막 토큰의 로짓만 계산하도록 넘길 인자 이름(transformers 버전마다 다르다).
# 기본값은 **모든 위치**의 로짓을 만든다 — 배치16 × 2048토큰 × 어휘152k × 2B ≈ 9.5GB
# 라서 A100 40GB 에서도 OOM 이 났다(실측: 301질의 중 200번째에서 터짐).
# yes/no 판정에는 마지막 한 자리면 된다.
import inspect
_p = inspect.signature(rr.forward).parameters
KEEP = ("logits_to_keep" if "logits_to_keep" in _p
        else "num_logits_to_keep" if "num_logits_to_keep" in _p else None)
print("로짓 절약 인자:", KEEP or "미지원 — 배치를 줄여야 함")

PREFIX = ('<|im_start|>system\\nJudge whether the Document meets the requirements '
          'based on the Query and the Instruct provided. Note that the answer can '
          'only be "yes" or "no".<|im_end|>\\n<|im_start|>user\\n')
SUFFIX = '<|im_end|>\\n<|im_start|>assistant\\n<think>\\n\\n</think>\\n\\n'
PRE_IDS = rr_tok.encode(PREFIX, add_special_tokens=False)
SUF_IDS = rr_tok.encode(SUFFIX, add_special_tokens=False)

# 지시문에 **업권**을 명시한다. 앞 회차에서 은행 광고에 여신전문금융 규정이
# 절반 넘게 올라온 것이 문제였는데, 리랭커는 질의와 문서를 같이 읽으므로
# 여기서 "어느 업권에 적용되는 규정인가"를 판단 기준으로 넣어 줄 수 있다.
INSTRUCT = ("주어진 은행 광고 심의 질의에 대해, 그 광고에 실제로 적용되는 "
            "법령·규정 조문인지 판단하라. 내용이 비슷해도 다른 업권(카드·캐피탈 등)에만 "
            "적용되는 규정이면 적합하지 않다.")

print("리랭커 yes/no 토큰:", TRUE_ID, FALSE_ID)
print(f"임베딩 VRAM {torch.cuda.memory_allocated()/1e9:.1f}GB")
""")

add(MD, """
## 6. 검색 함수 — 벡터 · BM25 · RRF · 리랭커
""")
add(PY, """
import numpy as np, torch

K_RRF = 60
TOP_EACH = 30      # 벡터·BM25 각각 상위 몇 개를 후보로 볼지
RERANK_N = 30      # 리랭커에 넣을 후보 수(비용이 여기서 결정된다)

def rrf(lists, k=K_RRF):
    sc = {}
    for lst in lists:
        for rank, i in enumerate(lst, 1):
            sc[i] = sc.get(i, 0.0) + 1.0 / (k + rank)
    return [i for i, _ in sorted(sc.items(), key=lambda x: -x[1])]

def vec_search(vecs, k=TOP_EACH):
    _, I = index.search(vecs, k)
    return I.tolist()

def bm_search(q, k=TOP_EACH):
    return [i for i, _ in BM.search(q, k, bm_idx)]

@torch.no_grad()
def rerank(query, cand_idx, batch=16):
    \"\"\"(문서번호, 점수) 를 점수 내림차순으로. 점수는 yes 확률.\"\"\"
    pairs = [f"<Instruct>: {INSTRUCT}\\n<Query>: {query}\\n<Document>: {rows[i]['text']}"
             for i in cand_idx]
    out = []
    for s in range(0, len(pairs), batch):
        chunk = pairs[s:s + batch]
        enc = rr_tok(chunk, padding=False, truncation="longest_first",
                     return_attention_mask=False,
                     max_length=RR_MAX - len(PRE_IDS) - len(SUF_IDS))
        enc["input_ids"] = [PRE_IDS + e + SUF_IDS for e in enc["input_ids"]]
        enc = rr_tok.pad(enc, padding=True, return_tensors="pt")
        enc = {k: v.to(rr.device) for k, v in enc.items()}
        logits = rr(**enc, **({KEEP: 1} if KEEP else {})).logits[:, -1, :]
        two = torch.stack([logits[:, FALSE_ID], logits[:, TRUE_ID]], dim=1)
        out += torch.nn.functional.log_softmax(two, dim=1)[:, 1].exp().tolist()
        del enc, logits, two
    return sorted(zip(cand_idx, out), key=lambda x: -x[1])

print("준비 완료")
""")

add(MD, """
## 7. 질의 임베딩
""")
add(PY, """
import time
pos = {a["광고id"]: i for i, a in enumerate(ads)}

qb, qb_owner = [], []
for i, a in enumerate(ads):
    for q in a["B_쟁점질의"]:
        qb.append(q["q"]); qb_owner.append(i)
qd = [c["text"] for c in adcs]
qd_owner = [pos[c["광고id"]] for c in adcs]

t0 = time.time()
vb = embed.encode(qb, prompt_name="query", batch_size=16, normalize_embeddings=True,
                  convert_to_numpy=True, show_progress_bar=True).astype(np.float32)
vd = embed.encode(qd, prompt_name="query", batch_size=16, normalize_embeddings=True,
                  convert_to_numpy=True, show_progress_bar=True).astype(np.float32)
print(f"\\nB {vb.shape} · D {vd.shape} · {time.time()-t0:.0f}초")

# 임베딩 모델을 내린다 — 질의 벡터는 vb/vd 에 numpy 로 남으므로 더 쓸 일이 없다.
# 8B FP16 이 16GB 를 물고 있어서, 그대로 두면 리랭커 쪽에서 자리가 모자란다.
import gc
del embed
gc.collect(); torch.cuda.empty_cache()
free = (torch.cuda.get_device_properties(0).total_memory
        - torch.cuda.memory_allocated()) / 1e9
print(f"임베딩 모델 해제 · 여유 {free:.1f}GB")
""")

add(MD, """
## 8. 3단계 실행

질의마다 세 결과를 남긴다.

| 단계 | 내용 |
|---|---|
| `vec` | 벡터만 (앞 회차와 같은 조건 — 비교 기준선) |
| `hyb` | 벡터 + BM25 를 RRF 로 병합 |
| `rr`  | 위 후보를 리랭커로 재정렬 |

시간이 걸리는 것은 리랭커다. 질의 약 300개 × 후보 30개 = 9,000쌍.
""")
add(PY, """
import time
t0 = time.time()
Vb, Vd = vec_search(vb), vec_search(vd)
per_q = []           # (owner, vec, hyb, rr)

allq = [(qb[i], qb_owner[i], Vb[i]) for i in range(len(qb))] + \\
       [(qd[i], qd_owner[i], Vd[i]) for i in range(len(qd))]

for n, (q, owner, v) in enumerate(allq, 1):
    b = bm_search(q)
    hyb = rrf([v, b])
    rr_out = rerank(q, hyb[:RERANK_N])
    per_q.append((owner, v, hyb, [i for i, _ in rr_out]))
    if n % 50 == 0:
        print(f"  {n}/{len(allq)}  ({time.time()-t0:.0f}초)")

print(f"완료 {len(allq)}질의 · {time.time()-t0:.0f}초")
""")

add(MD, """
## 9. 광고 단위로 모으고 업권 분포 측정

**업권 판정은 규정 이름으로 한다.** 우리 광고는 전부 NH농협은행 것이라,
「여신전문금융…」이 붙은 규정은 카드·캐피탈에 적용되는 것이고 은행을 구속하지 않는다.
""")
add(PY, """
import re, collections

def sector(name):
    if "여신전문금융" in name: return "여신(카드·캐피탈)"
    if "은행" in name:        return "은행"
    if "자본시장" in name or "금융투자" in name: return "금융투자"
    if "보험업" in name:      return "보험"
    if "금융소비자" in name:  return "공통(금소법)"
    if "표시" in name and "광고" in name: return "공통(공정위)"
    return "기타"

AD_RE = re.compile(r"광고|표시")

stage_ids = {"vec": 1, "hyb": 2, "rr": 3}
final = {k: {} for k in stage_ids}
for owner, v, h, r in per_q:
    for k, lst in (("vec", v), ("hyb", h), ("rr", r)):
        final[k].setdefault(owner, []).append(lst[:10])
for k in final:
    final[k] = {o: rrf(ls)[:10] for o, ls in final[k].items()}

print(f"{'단계':6s} {'1위 광고관련':>12s} {'상위10 광고관련':>15s} {'여신 비중':>10s} {'은행 비중':>10s}")
summary = {}
for k in ("vec", "hyb", "rr"):
    top1 = tot = adhit = ad1 = 0
    sec = collections.Counter()
    for o, lst in final[k].items():
        for n, i in enumerate(lst):
            nm = rows[i]["reg"]; sec[sector(nm)] += 1; tot += 1
            if AD_RE.search(nm + rows[i].get("title", "")): adhit += 1
            if n == 0:
                top1 += 1
                if AD_RE.search(nm + rows[i].get("title", "")): ad1 += 1
    summary[k] = (ad1, top1, adhit, tot, sec)
    print(f"{k:6s} {ad1:>5}/{top1:<4}({ad1/top1*100:>3.0f}%) "
          f"{adhit:>6}/{tot:<5}({adhit/tot*100:>3.0f}%) "
          f"{sec['여신(카드·캐피탈)']/tot*100:>8.1f}% {sec['은행']/tot*100:>9.1f}%")
""")

add(MD, "## 10. 리포트 저장 · 내려받기")
add(PY, """
def label(i):
    r = rows[i]
    return f"{r['reg']} — {r.get('key','')} {(r.get('title') or '')}".rstrip()

out = ["# 전체 파이프라인 — 벡터 · +BM25 · +리랭커", ""]
out += ["| 단계 | 1위 광고관련 | 상위10 광고관련 | 여신 비중 | 은행 비중 |", "|---|---|---|---|---|"]
for k in ("vec", "hyb", "rr"):
    a1, t1, ah, tt, sec = summary[k]
    out.append(f"| {k} | {a1}/{t1} ({a1/t1*100:.0f}%) | {ah}/{tt} ({ah/tt*100:.0f}%) "
               f"| {sec['여신(카드·캐피탈)']/tt*100:.1f}% | {sec['은행']/tt*100:.1f}% |")
out.append("")

for o, a in enumerate(ads):
    out += [f"## {a['광고id']} ({a['상품군']})", "",
            "| # | 벡터만 | +BM25 | +리랭커 |", "|---|---|---|---|"]
    for n in range(10):
        c = lambda k: label(final[k][o][n]) if o in final[k] and n < len(final[k][o]) else ""
        out.append(f"| {n+1} | {c('vec')} | {c('hyb')} | {c('rr')} |")
    out.append("")

open("pipeline_report.md", "w", encoding="utf-8").write("\\n".join(out))
from google.colab import files
files.download("pipeline_report.md")
""")

add(MD, """
---

## 읽는 법

- **여신 비중이 리랭커 단계에서 크게 떨어지면** → 업권 필터를 따로 만들 필요가 없다.
  지시문에 업권을 써 준 것만으로 해결된 것
- **거의 그대로면** → 리랭커도 못 가린다. 후보 단계에서 업권으로 걸러야 한다
  (규정별 적용 업권 표를 만들어 필터링)
- **hyb 가 vec 보다 나쁘면** → BM25 가 노이즈를 넣고 있다. 번호 질의에만 켜는 식으로
  조건부 적용을 검토
- 광고별 표에서 **같은 줄의 세 칸이 다 다르면** 단계마다 결과가 뒤집힌다는 뜻이다.
  그 경우 어느 것이 맞는지는 사람이 판정해야 한다
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
    dest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pipeline_colab.ipynb")
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(nb, f, ensure_ascii=False, indent=1)
    print(f"생성: {dest}  (셀 {len(CELLS)}개)")


if __name__ == "__main__":
    main()
