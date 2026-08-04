# -*- coding: utf-8 -*-
"""rag/embed_colab.ipynb 를 만든다.

노트북 JSON 을 손으로 쓰면 이스케이프에서 반드시 사고가 나서, 셀 내용을 파이썬
문자열로 두고 여기서 조립한다. 노트북을 고칠 일이 있으면 이 파일을 고치고 다시 실행한다.

  python rag/_build_colab_nb.py
"""
import os
import json

MD = "markdown"
PY = "code"

CELLS = []


def add(kind, text):
    CELLS.append((kind, text.strip("\n")))


add(MD, """
# 법령 청크 임베딩 — Qwen3-Embedding-8B (Colab A100)

규정 43건에서 뽑은 청크 **7,862개(500만 자)** 를 임베딩해 FAISS 인덱스를 만들고,
검색이 쓸 만한지 질의 세트로 확인한다.

**런타임을 A100 으로 먼저 바꾼다** — 메뉴 `런타임 → 런타임 유형 변경 → A100 GPU`.
8B 모델이 FP16 으로 약 16GB 라 T4(15GB)에는 안 올라간다.

입력: `chunks.jsonl`, `eval_queries.json` (2번 셀에서 업로드)
출력: `embeddings.f16.npy`, `chunks.faiss`, `search_report.md`
""")

add(MD, "## 1. GPU 확인\n\n`A100-SXM4-40GB` 로 나와야 한다. T4 면 런타임을 바꾸고 다시 실행한다.")
add(PY, """
!nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv
""")

add(MD, """
## 2. 설치

`sentence-transformers` 가 Qwen3-Embedding 계열을 기본 지원한다(마지막 토큰 풀링·
정규화·질의 프롬프트가 모델 설정에 들어 있어 우리가 직접 구현할 게 없다).
설치 후 **런타임 재시작 요구가 뜨면 무시**해도 된다.
""")
add(PY, """
!pip -q install -U "sentence-transformers>=3.3" faiss-cpu
import sentence_transformers, torch
print("sentence-transformers", sentence_transformers.__version__)
print("torch", torch.__version__, "· CUDA", torch.cuda.is_available())
""")

add(MD, """
## 3. 파일 업로드

로컬 프로젝트에서 두 파일을 올린다.

| 파일 | 위치 |
|---|---|
| `chunks.jsonl` | `output/_rag/chunks.jsonl` (13MB) |
| `eval_queries.json` | `rag/eval_queries.json` |

파일 선택 창이 뜨면 **두 개를 한 번에** 고르면 된다.
""")
add(PY, """
from google.colab import files
up = files.upload()
print()
for k, v in up.items():
    print(f"{k:24s} {len(v):>12,} B")
""")

add(MD, """
## 4. 청크 적재

업로드한 청크를 읽고 구성을 확인한다. 임베딩에 넣는 것은 `text` 필드 하나다 —
이미 `[규정명] 제12조(광고)` 형태의 머리글이 앞에 붙어 있어서 따로 가공하지 않는다.
""")
add(PY, """
import json, collections

rows = [json.loads(l) for l in open("chunks.jsonl", encoding="utf-8")]
queries = json.load(open("eval_queries.json", encoding="utf-8"))["질의"]

print(f"청크 {len(rows):,}개 · 총 {sum(r['chars'] for r in rows):,}자")
print("종류별:", collections.Counter(r["type"] for r in rows).most_common())
print("출처별:", collections.Counter(r["kind"] for r in rows).most_common())
print(f"질의 {len(queries)}개:", collections.Counter(q["갈래"] for q in queries).most_common())
print()
print("--- 청크 예시 ---")
print(rows[100]["text"][:300])
""")

add(MD, """
## 5. 모델 적재

`Qwen/Qwen3-Embedding-8B` 를 FP16 으로 올린다(약 16GB, 다운로드 몇 분).

`max_seq_length` 를 **2560** 으로 잡는 근거 — 로컬에서 이 토크나이저로 전체 청크를
실측했을 때 최댓값이 **2,114 토큰**이었다. 8B 의 권장 길이는 4,096 이지만 굳이
길게 잡으면 패딩 연산만 늘어난다. 잘리는 청크는 0개다.
""")
add(PY, """
from sentence_transformers import SentenceTransformer
import torch

model = SentenceTransformer(
    "Qwen/Qwen3-Embedding-8B",
    model_kwargs={"torch_dtype": torch.float16},
    tokenizer_kwargs={"padding_side": "left"},   # 마지막 토큰 풀링이라 왼쪽 패딩이어야 한다
)
model.max_seq_length = 2560

print("차원:", model.get_sentence_embedding_dimension())
print("최대 길이:", model.max_seq_length)
print(f"VRAM 점유: {torch.cuda.memory_allocated()/1e9:.1f} GB")
""")

add(MD, """
## 6. 임베딩 (본 작업)

7,862개를 배치로 돈다. A100 기준 **15~25분** 예상.

`encode()` 가 길이순 정렬을 알아서 해줘서 패딩 낭비가 적다. OOM 이 나면
`batch_size` 를 4 로 낮춘다.

> **문서 쪽에는 프롬프트를 붙이지 않는다.** Qwen3-Embedding 은 질의에만
> `Instruct: ...` 접두어를 붙이는 비대칭 구조다. 문서에 같이 붙이면 오히려 나빠진다.
""")
add(PY, """
import numpy as np, time, os

texts = [r["text"] for r in rows]
t0 = time.time()

emb = model.encode(
    texts,
    batch_size=8,
    normalize_embeddings=True,      # 코사인 = 내적
    show_progress_bar=True,
    convert_to_numpy=True,
)

dt = time.time() - t0
print(f"\\n완료: {emb.shape} · {dt/60:.1f}분 · 청크당 {dt/len(texts)*1000:.0f}ms")

np.save("embeddings.f16.npy", emb.astype(np.float16))
print(f"저장: embeddings.f16.npy ({os.path.getsize('embeddings.f16.npy')/1e6:.0f}MB)")
""")

add(MD, """
## 7. FAISS 인덱스

7,862개는 작아서 **정확 검색(IndexFlatIP)** 으로 충분하다. 근사 인덱스(IVF/HNSW)는
수십만 건부터 의미가 있고, 지금 쓰면 정확도만 잃는다.

벡터를 정규화해 두었으므로 내적이 곧 코사인 유사도다.
""")
add(PY, """
import faiss, numpy as np

x = emb.astype(np.float32)
index = faiss.IndexFlatIP(x.shape[1])
index.add(x)
faiss.write_index(index, "chunks.faiss")
print(f"인덱스 {index.ntotal:,}개 · {x.shape[1]}차원")
""")

add(MD, """
## 8. 검색 테스트

질의 22개를 돌려 상위 5개를 본다. 질의에는 **반드시 `prompt_name="query"`** 를 준다 —
이게 Qwen3-Embedding 의 비대칭 구조에서 질의 쪽 접두어를 붙여준다. 빼먹으면 성능이
눈에 띄게 떨어진다.

결과는 `search_report.md` 로도 저장해서 로컬에서 천천히 판정한다.
""")
add(PY, """
import numpy as np

def search(q, k=5):
    v = model.encode([q], prompt_name="query", normalize_embeddings=True,
                     convert_to_numpy=True).astype(np.float32)
    score, idx = index.search(v, k)
    return [(float(s), rows[i]) for s, i in zip(score[0], idx[0])]

out = ["# 검색 파일럿 결과 — Qwen3-Embedding-8B 단독(벡터만)", "",
       f"청크 {len(rows):,}개 · 질의 {len(queries)}개 · 상위 5개", ""]

for q in queries:
    head = f"## [{q['갈래']}] {q['q']}"
    print("\\n" + "=" * 78); print(head); print(f"  ({q['메모']})")
    out += [head, "", f"> {q['메모']}", ""]
    for rank, (s, r) in enumerate(search(q["q"]), 1):
        line = f"{rank}. `{s:.3f}` **{r['reg']}** — {r['key']} {r['title']}".rstrip()
        print(f"  {rank}. {s:.3f}  {r['reg']} — {r['key']} {r['title']}"[:150])
        out += [line, "", f"   {r['text'][:200].replace(chr(10), ' ')}...", ""]
    out.append("")

open("search_report.md", "w", encoding="utf-8").write("\\n".join(out))
print("\\n\\n저장: search_report.md")
""")

add(MD, """
## 9. 결과 내려받기

`embeddings.f16.npy`(64MB)와 인덱스·리포트를 받는다. 용량이 있어 시간이 좀 걸린다.

받은 파일은 로컬 `output/_rag/` 에 둔다. 이 벡터는 **H200 에서도 그대로 쓸 수 있다** —
임베딩 결과는 float 배열일 뿐이라 GPU 아키텍처에 매이지 않는다(Gemma 의 NVFP4 처럼
포맷이 특정 세대에 묶이는 문제가 없다).
""")
add(PY, """
from google.colab import files
for f in ["search_report.md", "chunks.faiss", "embeddings.f16.npy"]:
    files.download(f)
""")

add(MD, """
---

## 다음 (로컬에서)

1. `search_report.md` 를 눈으로 판정 — 갈래별로 보는 것이 다르다
   - **번호지정**: 못 찾으면 예상대로다. BM25 하이브리드 필요성이 실측으로 확인된 것
   - **의미검색**: 여기서 못 찾으면 청킹이나 모델 쪽에 문제가 있다는 신호
   - **상품군**: 태그 없이도 잘 갈리면 3단계에서 보류한 상품군 태그 작업이 불필요
2. BM25 인덱스는 GPU 가 필요 없어 로컬에서 만든다 → RRF 로 합쳐 재측정
3. 두 결과 차이로 3단계 보류 2건(광고심의 무관 별표 제외·상품군 태그)을 판정
""")


def main():
    nb = {
        "cells": [
            {"cell_type": k, "metadata": {},
             **({"source": t.splitlines(keepends=True), "outputs": [], "execution_count": None}
                if k == PY else {"source": t.splitlines(keepends=True)})}
            for k, t in CELLS
        ],
        "metadata": {
            "colab": {"provenance": [], "gpuType": "A100"},
            "accelerator": "GPU",
            "kernelspec": {"name": "python3", "display_name": "Python 3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4, "nbformat_minor": 0,
    }
    dest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "embed_colab.ipynb")
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(nb, f, ensure_ascii=False, indent=1)
    print(f"생성: {dest}  (셀 {len(CELLS)}개)")


if __name__ == "__main__":
    main()
