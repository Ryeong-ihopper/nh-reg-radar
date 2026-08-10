# -*- coding: utf-8 -*-
"""rag/embed_index_colab.ipynb — 색인 전체를 임베딩한다. 이것만 한다.

CPU 로는 9,335건에 7시간, 늘어난 1,026건만 해도 45분이다. A100 이면 2~3분이다.

**늘어난 것만 이어 붙이지 않고 전체를 다시 만든다.** 이어 붙이면 앞부분과 뒷부분이
같은 모델·같은 설정으로 만들어졌는지 확인할 방법이 파일 안에 없다. 전체를 한 번에
만들면 그 의심이 사라지고, 어차피 A100 에서 몇 분이다.

  올릴 것    rule_index.jsonl  (약 25MB)
  받을 것    vectors.f16.npy   (9,335 × 1024 × 2byte ≈ 19MB)
             vectors.meta.json

  python rag/_build_colab_embed.py
"""
import os
import json

MD, PY = "markdown", "code"
CELLS = []


def add(kind, text):
    CELLS.append((kind, text.strip("\n")))


add(MD, """
# 색인 임베딩 — BGE-M3

색인 9,335건을 벡터로 만든다. **이 노트북은 이것만 한다.**

| | |
|---|---|
| 런타임 | GPU 아무거나 (T4 도 됨, A100 이면 2~3분) |
| 올릴 것 | `rule_index.jsonl` |
| 받을 것 | `vectors.f16.npy` · `vectors.meta.json` |

## 왜 전체를 다시 만드나

매뉴얼 1,026건이 색인에 새로 들어가 8,309 → 9,335 가 됐다. 늘어난 부분만 이어
붙일 수도 있지만, 그러면 **앞부분과 뒷부분이 같은 설정으로 만들어졌는지 파일만
보고는 확인할 수 없다.** 전체를 한 번에 만들면 그 의심이 없어지고 몇 분이면 된다.

## 색인에 넣는 문자열을 로컬과 똑같이 맞춘다

    title + article_no + content

**여기가 다르면 검색이 조용히 나빠진다.** 벡터는 어긋나도 오류가 안 나고 그냥
엉뚱한 것을 가져오는데, 그게 성능 문제로 보인다.
""")

add(MD, "## 1. 환경")
add(PY, """
!nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
!pip -q install -U sentence-transformers 2>&1 | tail -1
""")

add(MD, """
## 2. `rule_index.jsonl` 올리기

왼쪽 파일 창에 끌어다 놓아도 된다. 그 경우 이 셀은 건너뛰어도 3번 셀이 알아서 읽는다.
""")
add(PY, """
from google.colab import files
import os, json
if not os.path.exists("rule_index.jsonl"):
    up = files.upload()
assert os.path.exists("rule_index.jsonl"), "rule_index.jsonl 이 필요합니다"
rows = [json.loads(l) for l in open("rule_index.jsonl", encoding="utf-8")]
n_rules = sum(1 for r in rows if r["evidence_id"].startswith("R-"))
n_man = sum(1 for r in rows if r["evidence_id"].startswith("M-"))
print(f"색인 {len(rows):,} = 규칙 {n_rules:,} + 조문 {len(rows)-n_rules-n_man:,} "
      f"+ 매뉴얼 {n_man:,}")
""")

add(MD, """
## 3. 임베딩

`normalize_embeddings=True` 로 만든다. 정규화해 두면 검색할 때 코사인 유사도를
**내적 한 번**으로 구할 수 있다 — 9,335 × 1024 행렬 곱 하나면 끝난다.

`float16` 으로 저장한다. `float32` 면 38MB, `float16` 이면 19MB 인데 검색 결과는
같다. 내려받는 시간이 절반이다.
""")
add(PY, r"""
import os, json, numpy as np, time
from sentence_transformers import SentenceTransformer

# **이 셀만 따로 돌려도 되게 한다.** 앞 셀에서 만든 변수에 기대면, 런타임이 끊기거나
# 파일을 드래그로 올린 경우 NameError 로 죽는다. 파일에서 다시 읽는 편이 안전하다.
assert os.path.exists("rule_index.jsonl"),     "rule_index.jsonl 이 없다 — 왼쪽 파일 창에 올리거나 2번 셀을 돌려라"
rows = [json.loads(l) for l in open("rule_index.jsonl", encoding="utf-8")]
n_rules = sum(1 for r in rows if r["evidence_id"].startswith("R-"))
n_man = sum(1 for r in rows if r["evidence_id"].startswith("M-"))
print(f"색인 {len(rows):,} = 규칙 {n_rules:,} + 조문 {len(rows)-n_rules-n_man:,} "
      f"+ 매뉴얼 {n_man:,}")

def index_text(r):
    # **로컬 rag/measure.py 의 index_text 와 글자 하나까지 같아야 한다.**
    return f"{r.get('title','')} {r.get('article_no') or ''} {r.get('content','')}"

m = SentenceTransformer("BAAI/bge-m3")
texts = [index_text(r)[:1200] for r in rows]
print(f"글자수 중앙 {sorted(len(t) for t in texts)[len(texts)//2]}")

t0 = time.time()
V = m.encode(texts, batch_size=64, normalize_embeddings=True,
             show_progress_bar=True).astype("float32")
print(f"\n{V.shape} · {time.time()-t0:.0f}초")

# 정규화가 실제로 됐는지 확인한다. 안 됐으면 검색 점수가 길이에 휘둘린다.
norms = np.linalg.norm(V, axis=1)
print(f"노름 최소 {norms.min():.4f} 최대 {norms.max():.4f}  (1.0 이어야 함)")
assert abs(norms.mean() - 1.0) < 1e-3, "정규화가 안 됐다"
""")

add(MD, """
## 4. 제대로 만들어졌는지 확인

**저장하기 전에 본다.** 벡터가 잘못돼도 오류가 안 나기 때문에, 눈으로 확인할
표본을 하나 만든다. 「예금 만기후이율」로 찾았을 때 관련 조문이 위에 와야 한다.
""")
add(PY, """
q = m.encode(["예금 이율 기간별 중도해지 만기후 이율 표기"],
             normalize_embeddings=True).astype("float32")[0]
top = np.argsort(-(V @ q))[:5]
for r_, i in enumerate(top, 1):
    kind = "규칙" if i < n_rules else ("매뉴얼" if rows[i]["evidence_id"].startswith("M-") else "조문")
    print(f"{r_}. [{kind}] {rows[i].get('title','')[:46]}  "
          f"{rows[i].get('article_no') or ''}")
""")

add(MD, "## 5. 내려받기")
add(PY, """
import json
np.save("vectors.f16.npy", V.astype("float16"))
json.dump({"model": "BGE-M3", "dim": int(V.shape[1]), "n": int(V.shape[0]),
           "n_rules": n_rules, "n_manual": n_man,
           "index": "rule_index.jsonl", "normalized": True,
           "index_text": "title + article_no + content, 1200자 자름"},
          open("vectors.meta.json", "w", encoding="utf-8"), ensure_ascii=False)
print("vectors.f16.npy", os.path.getsize("vectors.f16.npy")/1e6, "MB")

files.download("vectors.f16.npy")
files.download("vectors.meta.json")
""")

add(MD, """
## 받은 뒤 로컬에서

```
output/_rag/ 에 두 파일을 덮어쓰고
python rag/measure.py            # 벡터·하이브리드가 자동으로 켜진다
python rag/measure.py --rerank   # 리랭커까지 (CPU 로 30분쯤)
```

`measure.py` 는 **벡터 개수와 색인 줄 수가 다르면 벡터 검색을 건너뛰고 그 사실을
말한다.** 조용히 틀린 결과를 내지 않는다.
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
                       "embed_index_colab.ipynb")
    json.dump(nb, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"셀 {len(CELLS)}개 → {out}")


if __name__ == "__main__":
    main()
