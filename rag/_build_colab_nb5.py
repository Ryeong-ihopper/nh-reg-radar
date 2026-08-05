# -*- coding: utf-8 -*-
"""rag/index_ab_colab.ipynb 를 만든다.

**재는 것은 하나다 — 규칙과 조문을 한 색인에 넣어도 되는가.**

인덱스를 합치자고 정했지만 합친 상태로는 한 번도 재지 않았다. 지금 기준선
(BM25 R@5 75.1%)은 조문 6,565개만 놓고 잰 것이다. 합치면 이런 일이 생길 수 있다.

  규칙  68자     「홈쇼핑 투자광고는 녹화방송이어야」
  조문  1,100자  제2-39조의2 (홈쇼핑·전광판·SNS 규정이 한 덩어리)

BM25 도 벡터도 길이에 민감해서 **6,565개 조문이 1,744개 규칙을 상위권에서 밀어낼 수
있다.** 밀어내는지 아닌지는 재야 안다.

임베딩 모델은 **BGE-M3** 를 쓴다. 성능이 제일 좋아서가 아니라 **DAP 가 주는 것이
BGE-M3 와 ME5 둘뿐**이기 때문이다. 여기서 Qwen3-8B 로 좋은 숫자를 받아 봐야 옮길 수
없다. 옮길 수 없는 성능은 성능이 아니다.

  python rag/_build_colab_nb5.py
"""
import os
import json

MD = "markdown"
PY = "code"

CELLS = []


def add(kind, text):
    CELLS.append((kind, text.strip("\n")))


add(MD, """
# 규칙·조문 색인 A/B — BGE-M3 (Colab T4 이상)

**정하려는 것 하나:** 규칙 1,744건과 조문 6,565건을 한 색인에 넣어도 되는가.

| | 색인 대상 | 무엇을 보나 |
|---|---|---|
| **A. 조문만** | 6,565 | 지금 기준선(BM25 R@5 75.1%)과 직접 비교 |
| **B. 규칙만** | 1,744 | 규칙이 검색되기는 하는가 |
| **C. 합친 것** | 8,309 | 조문이 규칙을 밀어내는가 |

각각 **BM25 · 벡터 · 하이브리드(RRF)** 세 방식으로 잰다.

**모델은 BGE-M3 로 고정한다.** DAP 가 주는 임베딩이 BGE-M3 와 ME5 둘뿐이라,
더 좋은 모델로 좋은 숫자를 받아도 옮길 수 없다.

**런타임:** `런타임 → 런타임 유형 변경 → T4 GPU` 면 충분하다(BGE-M3 는 2.2GB).

**입력 3개** — 2번 셀에서 업로드
`chunks.jsonl` · `rule_index.jsonl` · `gold.json`

**출력** — `index_ab_report.md`
""")

add(MD, "## 1. 환경\n\nGPU 이름이 찍히면 된다. CPU 로도 돌지만 20분쯤 걸린다.")
add(PY, """
!nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || echo "GPU 없음 — CPU 로 진행"
!pip -q install FlagEmbedding==1.3.4 2>&1 | tail -2
""")

add(MD, """
## 2. 파일 업로드

`output/_rag/` 에서 셋을 고른다. 한 번에 여러 개 고를 수 있다.

  `chunks.jsonl`  `rule_index.jsonl`  `gold.json`
""")
add(PY, """
from google.colab import files
import os, json

up = files.upload()
for n in up:
    print(f"{n:24s} {len(up[n])/1e6:6.1f}MB")

need = ["chunks.jsonl", "rule_index.jsonl", "gold.json"]
missing = [n for n in need if not os.path.exists(n)]
assert not missing, f"빠진 파일: {missing}"
""")

add(MD, """
## 3. 자료 읽기

**정답 번호를 색인마다 옮겨야 한다.** gold 의 `정답청크` 는 `chunks.jsonl` 의
줄 번호다. 합친 색인에서는 규칙 1,744건이 앞에 오므로 **1744 를 더해야** 같은
조문을 가리킨다. 이걸 안 맞추면 C 만 0% 가 나오고 「합치면 망한다」는 틀린 결론이
나온다.

규칙에는 정답이 없다 — gold 는 조문을 정답으로 적은 표다. 그래서 **B(규칙만)는
Recall 을 잴 수 없고**, 대신 「규칙이 상위에 오기는 하는가」를 다른 방식으로 본다.
""")
add(PY, """
import json, numpy as np

chunks = [json.loads(l) for l in open("chunks.jsonl", encoding="utf-8")]
index  = [json.loads(l) for l in open("rule_index.jsonl", encoding="utf-8")]
gold   = json.load(open("gold.json", encoding="utf-8"))

rules    = [r for r in index if r["evidence_id"].startswith("R-")]
art_rows = [r for r in index if r["evidence_id"].startswith("C-")]
OFFSET   = len(rules)          # 합친 색인에서 조문이 시작하는 자리

assert len(art_rows) == len(chunks), (len(art_rows), len(chunks))
print(f"조문 {len(chunks):,} · 규칙 {len(rules):,} · 합계 {len(index):,} · 오프셋 {OFFSET}")
print(f"gold {len(gold)}건")

# 색인 3종. text 는 검색에 넣을 문자열, gold_shift 는 정답 번호에 더할 값.
def txt_chunk(c):  return f"{c['reg']} {c.get('key','')} {c.get('title','')} {c['text']}"
def txt_index(r):  return f"{r.get('title','')} {r.get('article_no','')} {r.get('content','')}"

CONFIGS = {
    "A. 조문만":  {"text": [txt_chunk(c) for c in chunks],           "shift": 0},
    "B. 규칙만":  {"text": [txt_index(r) for r in rules],            "shift": None},
    "C. 합친 것": {"text": [txt_index(r) for r in index],            "shift": OFFSET},
}
for k, v in CONFIGS.items():
    n = len(v["text"])
    ln = sorted(len(t) for t in v["text"])
    print(f"  {k:10s} {n:>6,}건 · 길이 중앙 {ln[n//2]:>5} · p90 {ln[int(n*.9)]:>5}")
""")

add(MD, """
### 3-1. D. 인용된 조문만 — 나머지는 잡음인가

로컬 실측: **청크 6,565개 중 규칙이 실제로 짚은 것은 177개(3%)** 다. 자본시장법
시행령은 1,114개 중 5개, 소득세법은 568개 중 1개만 인용된다.

그런데 gold 334건 중 **304건(91%)은 정답이 그 177개 안에 다 들어 있다.** 규칙리스트
(매뉴얼 출처)와 체크리스트(다른 출처)가 독립적으로 만들어졌는데도 겹치는 것이다.

**즉 6,388개는 어느 쪽에서도 정답이 된 적이 없다.** 빼면 정밀도가 오를 수 있고,
반대로 규칙리스트가 92% 「임시」라 아직 안 짚은 조문을 버리는 위험도 있다.
**논쟁하지 말고 재자.**
""")
add(PY, """
# 규칙이 짚은 (규정, 조문키). rule_index 의 `근거` 는 한글 키를 쓴다.
cited, whole = set(), set()
for r in rules:
    for h in (r.get("근거") or []):
        if not isinstance(h, dict) or not h.get("규정"):
            continue
        if h.get("article_no"):
            cited.add((h["규정"], h["article_no"]))
        else:
            # 조문 구조가 없는 심사지침류는 「규정 전체」가 근거다. 조문키로만
            # 거르면 통째로 사라지므로 그런 규정은 전부 남긴다.
            whole.add(h["규정"])

keep = sorted({i for i, c in enumerate(chunks)
               if (c["reg"], c.get("key", "")) in cited or c["reg"] in whole})
remap = {old: new for new, old in enumerate(keep)}      # 옛 번호 → 새 번호

print(f"인용된 조문만: {len(chunks):,} → {len(keep):,}건")
print(f"  조문 단위 인용 {len(cited)}곳 · 규정 전체 인용 {len(whole)}종")

full = sum(1 for g in gold if all(c in remap for c in g["정답청크"]))
part = sum(1 for g in gold if any(c in remap for c in g["정답청크"])) - full
print(f"gold {len(gold)}건 — 정답이 전부 살아남음 {full} · 일부 {part} · "
      f"전멸 {len(gold)-full-part}")
print("  전멸한 문항은 D 에서 절대 못 맞힌다. 이 손해가 정밀도 이득보다 크면 안 쓴다.")

CONFIGS["D. 인용된 조문만"] = {
    "text": [txt_chunk(chunks[i]) for i in keep],
    "shift": 0, "remap": remap,
}
""")

add(MD, """
## 4. BM25 — 벡터 없이 먼저

한국어는 공백 분리만으로는 「제16조」와 「제16조제1항」이 안 걸린다.

**아래는 `rag/bm25.py` 에서 그대로 옮긴 것이다.** 비슷하게 다시 쓰면 안 된다 —
토크나이저가 조금만 달라도 로컬 기준선(R@5 75.1%)과 비교가 성립하지 않고,
그러면 「합쳐서 떨어진 건지 토크나이저가 달라서 떨어진 건지」를 가릴 수 없다.
""")
add(PY, r"""
import re, math, collections

# ── 여기부터 rag/bm25.py 원문 ──────────────────────────────────────────
_HANGUL = re.compile(r"[가-힣]+")
_WORD = re.compile(r"[A-Za-z0-9]+")
_ART = re.compile(r"제\s*(\d+)\s*(?:-\s*(\d+))?\s*조(?:\s*의\s*(\d+))?")
_TBL = re.compile(r"\[?\s*(별표|별지|서식|첨부)\s*(?:제)?\s*0*(\d+)\s*(?:의\s*(\d+))?\s*(?:호)?\s*\]?")
_TBL_BARE = re.compile(r"(별표|별지|서식|첨부)")

def _art_tokens(m):
    a, b, c = m.group(1), m.group(2), m.group(3)
    key = f"조{a}" + (f"-{b}" if b else "") + (f"의{c}" if c else "")
    out = [key]
    if b or c:
        out.append(f"조{a}")
    return out

def _tbl_tokens(m):
    kind, num, sub = m.group(1), int(m.group(2)), m.group(3)
    suf = f"의{sub}" if sub else ""
    return [kind, f"{kind}{num}{suf}", f"{kind}{num:04d}{suf}"]

def tokenize(text):
    toks = []
    for m in _ART.finditer(text):
        toks += _art_tokens(m)
    for m in _TBL.finditer(text):
        toks += _tbl_tokens(m)
    rest = _TBL.sub(" ", _ART.sub(" ", text))
    for m in _TBL_BARE.finditer(rest):
        toks.append(m.group(1))
    rest = _TBL_BARE.sub(" ", rest)
    toks += [w.lower() for w in _WORD.findall(rest)]
    for run in _HANGUL.findall(rest):
        if len(run) == 1:
            toks.append(run)
        else:
            toks += [run[i:i + 2] for i in range(len(run) - 1)]
    return toks
# ── 여기까지 원문 ─────────────────────────────────────────────────────

K1, B = 1.2, 0.75

def bm25_build(texts):
    docs, df = [], collections.Counter()
    for t in texts:
        tf = collections.Counter(tokenize(t))
        docs.append(tf); df.update(tf.keys())
    N = len(docs)
    idf = {t: math.log(1 + (N - n + 0.5) / (n + 0.5)) for t, n in df.items()}
    inv = collections.defaultdict(list)
    for i, d in enumerate(docs):
        for t, f in d.items():
            inv[t].append((i, f))
    dl = [sum(d.values()) for d in docs]
    return {"inv": dict(inv), "idf": idf, "dl": dl,
            "avgdl": sum(dl)/max(N,1), "N": N}

def bm25_search(q, idx, k=50):
    sc = collections.defaultdict(float)
    for t in set(tokenize(q)):
        post = idx["inv"].get(t)
        if not post: continue
        w = idx["idf"][t]
        for i, f in post:
            sc[i] += w * f * (K1+1) / (f + K1*(1 - B + B*idx["dl"][i]/idx["avgdl"]))
    return sorted(sc.items(), key=lambda x: -x[1])[:k]

for name, cfg in CONFIGS.items():
    cfg["bm25"] = bm25_build(cfg["text"])
    print(f"{name:10s} 어휘 {len(cfg['bm25']['idf']):,}")
""")

add(MD, """
## 5. 임베딩 — BGE-M3 / ME5 둘 다

**DAP 가 주는 임베딩이 이 둘뿐이다.** 어느 쪽이 나은지가 실제로 골라야 하는 선택이라
같이 잰다. 여기서 Qwen3-8B 로 좋은 숫자를 받아 봐야 옮길 수 없다.

아래 `MODEL` 을 바꿔 가며 5~9번 셀을 **두 번 돌린다.** 결과는 `ALL_ROWS` 에 쌓이고
9번 셀이 둘을 함께 표로 낸다.

    MODEL = "bge-m3"     ← 먼저 이걸로 5~8번 실행
    MODEL = "me5"        ← 그다음 이걸로 바꿔 5~8번 다시 실행, 마지막에 9번

한 모델당 T4 에서 12분쯤. 최대 길이는 **1,024 로 자른다** — 청크가 p90 1,167자라 거의
안 잘리고 속도가 3배 빨라진다.
""")
add(PY, """
MODEL = "bge-m3"      # ← 두 번째 실행 때 "me5" 로 바꾼다

import numpy as np, torch, gc
try:
    ALL_ROWS
except NameError:
    ALL_ROWS, SHARES = [], {}   # 두 모델 결과를 쌓는다(다시 실행해도 안 지워지게)

if MODEL == "bge-m3":
    from FlagEmbedding import BGEM3FlagModel
    _m = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
    MODEL_NAME = "BGE-M3"
    def embed(texts, bs=32, maxlen=1024, is_query=False):
        v = _m.encode(texts, batch_size=bs, max_length=maxlen)["dense_vecs"]
        return np.asarray(v, dtype="float32")
else:
    from sentence_transformers import SentenceTransformer
    _m = SentenceTransformer("intfloat/multilingual-e5-large", device="cuda")
    _m.max_seq_length = 512          # ME5 는 512 가 상한이다
    MODEL_NAME = "ME5-large"
    def embed(texts, bs=32, maxlen=None, is_query=False):
        # **ME5 는 접두어가 필수다.** query:/passage: 를 안 붙이면 성능이 크게
        # 떨어지는데, 에러가 나지 않아 조용히 나쁜 숫자가 나온다.
        pre = "query: " if is_query else "passage: "
        return _m.encode([pre + t for t in texts], batch_size=bs,
                         convert_to_numpy=True, show_progress_bar=True)

for name, cfg in CONFIGS.items():
    print(f"\\n{MODEL_NAME} · {name} — {len(cfg['text']):,}건")
    v = embed(cfg["text"])
    v /= (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)   # 코사인용 정규화
    cfg["vec"] = v
    print(f"  {v.shape} · {v.nbytes/1e6:.0f}MB")
    gc.collect(); torch.cuda.empty_cache()

qvec = embed([g["q"] for g in gold], is_query=True)
qvec /= (np.linalg.norm(qvec, axis=1, keepdims=True) + 1e-9)
print(f"\\n질의 {qvec.shape}")
""")

add(MD, """
## 6. 세 방식으로 순위 만들기

**하이브리드는 RRF(Reciprocal Rank Fusion)** 로 합친다. 점수를 더하지 않고 **순위**를
더하는 방식이라, BM25 점수(0~30)와 코사인(0~1)처럼 **자릿수가 다른 것을 억지로 맞출
필요가 없다.** k=60 은 관례값이다.

    RRF(d) = Σ 1 / (60 + rank_i(d))
""")
add(PY, """
def rrf(*rankings, k=60, top=50):
    sc = collections.defaultdict(float)
    for r in rankings:
        for pos, d in enumerate(r, 1):
            sc[d] += 1.0 / (k + pos)
    return [d for d, _ in sorted(sc.items(), key=lambda x: -x[1])[:top]]

def rank_all(cfg, top=50):
    \"\"\"{방식: {gold_id: [색인번호 순위]}}\"\"\"
    bm, vec = cfg["bm25"], cfg["vec"]
    out = {"BM25": {}, "벡터": {}, "하이브리드": {}}
    sim_all = qvec @ vec.T                    # (질의, 문서)
    for i, g in enumerate(gold):
        b = [d for d, _ in bm25_search(g["q"], bm, top)]
        v = np.argsort(-sim_all[i])[:top].tolist()
        out["BM25"][g["id"]] = b
        out["벡터"][g["id"]] = v
        out["하이브리드"][g["id"]] = rrf(b, v, top=top)
    return out

for name, cfg in CONFIGS.items():
    cfg["rank"] = rank_all(cfg)
    print(f"{name} 순위 완료")
""")

add(MD, """
## 7. 채점

**정답 번호를 색인마다 옮긴다** — 3번 셀에서 말한 오프셋. `shift` 가 `None` 인
B(규칙만)는 gold 에 정답이 없으므로 Recall 대신 따로 본다.

**정답은 조문뿐이다.** 규칙도 정답으로 쳐 보려고 「같은 조문을 근거로 든 규칙은 다
정답」을 붙였다가 뺐다 — 조문 하나에 규칙이 너무 많이 달린다.

    금투협 규정 제2-38조 → 규칙 161개 · 금소법 제22조 → 103개
    문항당 정답규칙 중앙 48개

8,309개 중 161개가 정답이면 상위 5개에 드는 것은 거의 자동이라 채점이 무의미해진다.
실제로 「은행의 명칭을 표시하였는가?」에 「예금성 의무표시 - 이자율의 범위 및
산출기준」이 정답으로 잡혔다 — 둘 다 제16조를 근거로 들 뿐 항·호는 서로 다르다.

**그래서 C(합친 것)의 숫자는 낮게 나온다.** 규칙이 상위를 차지하는데 규칙은 정답으로
안 세기 때문이다. C 를 A 와 직접 비교하면 안 되고, **8번 셀의 「규칙이 차지하는
자리」와 그 표본을 눈으로 봐야** 한다. 규칙 단위 정답표는 사람이 붙여야 한다.

같은 조문이 여러 조각으로 잘렸으면 **어느 조각이든 맞으면 맞은 것**으로 센다.
""")
add(PY, """
KS = (1, 3, 5, 10)

def answers(g, cfg):
    shift, remap = cfg["shift"], cfg.get("remap")
    # D 는 청크를 걸러 번호가 다시 매겨졌다. 옮기지 않으면 0% 가 나오고
    # 「거르면 망한다」는 틀린 결론이 나온다.
    return ({remap[c] for c in g["정답청크"] if c in remap} if remap
            else {c + shift for c in g["정답청크"]})

def score(ranking, cfg):
    hit = {k: 0 for k in KS}; mrr = 0.0; n = 0
    for g in gold:
        r = ranking.get(g["id"])
        if r is None: continue
        n += 1
        ans = answers(g, cfg)
        if not ans:
            continue                       # 정답이 통째로 걸러진 문항 — 0점 처리
        pos = next((i for i, d in enumerate(r, 1) if d in ans), None)
        for k in KS:
            if pos and pos <= k: hit[k] += 1
        mrr += 1.0/pos if pos else 0.0
    return {f"R@{k}": hit[k]/n for k in KS} | {"MRR": mrr/n, "n": n}

rows = []
for name, cfg in CONFIGS.items():
    if cfg["shift"] is None:
        continue
    for how, ranking in cfg["rank"].items():
        m = score(ranking, cfg)
        rows.append((MODEL_NAME, name, how, m))
        print(f"{MODEL_NAME:8s} {name:14s} {how:6s}  " +
              " · ".join(f"R@{k} {m[f'R@{k}']*100:5.1f}%" for k in KS) +
              f" · MRR {m['MRR']:.3f}")

""")

add(MD, """
## 8. 조문이 규칙을 밀어내는가 — 이게 핵심

C(합친 것)의 상위 10개에 **규칙이 몇 개나 들어오는지** 센다.

  · 규칙이 20% 는 되어야 「합쳐도 규칙이 산다」고 볼 수 있다(8,309 중 1,744 = 21%).
  · 5% 밑으로 떨어지면 **조문이 규칙을 밀어낸 것**이고, 색인을 나누거나
    검색 단계에서 종류별 할당을 줘야 한다.
""")
add(PY, """
cfg = CONFIGS["C. 합친 것"]
print(f"{'방식':8s} {'상위10 중 규칙 비율':>18s}   기대치 21.0%")
share = {}
for how, ranking in cfg["rank"].items():
    tot = rule_n = 0
    for g in gold:
        for d in ranking[g["id"]][:10]:
            tot += 1
            if d < OFFSET: rule_n += 1
    share[how] = rule_n / max(tot, 1)
    flag = "밀려남" if share[how] < 0.05 else ("낮음" if share[how] < 0.15 else "정상")
    print(f"{how:8s} {share[how]*100:>17.1f}%   {flag}")

print("\\n규칙이 1위로 온 질의 표본:")
shown = 0
for g in gold:
    top1 = cfg["rank"]["하이브리드"][g["id"]][0]
    if top1 < OFFSET and shown < 6:
        print(f"  {g['q'][:52]}")
        print(f"    → {rules[top1]['title'][:60]}")
        shown += 1
""")

add(MD, """
## 9. 보고서

**두 모델을 다 돌린 뒤에 실행한다.** `MODEL` 을 바꿔 5~8번을 두 번 돌렸으면
`ALL_ROWS` 에 양쪽이 다 들어 있다.

이 숫자로 정할 것 셋:

1. **색인을 합칠까 나눌까** — C 가 A 보다 나쁘면 나눈다
2. **인용 안 된 조문을 버릴까** — D 가 A 보다 나으면 버린다
3. **BGE-M3 냐 ME5 냐** — DAP 에서 골라야 하는 것
""")
add(PY, """
ALL_ROWS += rows          # 이번 모델 결과를 누적
SHARES[MODEL_NAME] = share

lines = ["# 규칙·조문 색인 A/B", ""]
lines += [f"조문 {len(chunks):,} · 규칙 {len(rules):,} · 합계 {len(index):,} · "
          f"인용된 조문만 {len(CONFIGS['D. 인용된 조문만']['text']):,} · gold {len(gold)}건", ""]
lines += ["| 모델 | 색인 | 방식 | R@1 | R@3 | R@5 | R@10 | MRR |",
          "|---|---|---|---:|---:|---:|---:|---:|"]
for mdl, name, how, m in ALL_ROWS:
    lines.append(f"| {mdl} | {name} | {how} | " +
                 " | ".join(f"{m[f'R@{k}']*100:.1f}%" for k in KS) +
                 f" | {m['MRR']:.3f} |")
lines += ["", "## 합친 색인에서 규칙이 차지하는 자리 (상위 10)", "",
          "| 모델 | 방식 | 규칙 비율 | 기대치 |", "|---|---|---:|---:|"]
for mdl, sh in SHARES.items():
    for how, v in sh.items():
        lines.append(f"| {mdl} | {how} | {v*100:.1f}% | 21.0% |")
lines += ["", "## 로컬 기준선", "",
          "BM25 · 조문만 · R@1 34.4% · R@3 64.7% · R@5 75.1% · R@10 79.0%",
          "", "A-BM25 가 이와 다르면 토크나이저나 자료가 어긋난 것이다 —",
          "먼저 그것부터 맞추고 나머지 숫자를 읽어야 한다."]

open("index_ab_report.md", "w", encoding="utf-8").write("\\n".join(lines))
print("\\n".join(lines))

from google.colab import files
files.download("index_ab_report.md")
""")

add(MD, """
## 10. 벡터 내려받기 — 파이프라인이 쓸 물건

**점수만 재고 끝내면 안 된다.** 임베딩을 안 받아 두면 로컬에서 벡터 검색을 못 돌려
코랩을 또 켜야 한다. 6,565 × 1024 = 27MB 라 fp16 으로 받으면 13MB 다.

받아 두면 **이후 검색은 로컬 CPU 로 충분하다** — 코사인 유사도는 행렬 곱 한 번이다.
GPU 가 다시 필요한 것은 리랭커와 Gemma 뿐이다.

한 모델만 저장한다. 9번 표를 보고 **이길 모델로 이 셀을 돌린다** — `MODEL` 을
그 모델로 두고 5번 셀부터 다시 실행한 뒤 여기로 온다.

**낡은 벡터를 쓰는 사고를 막으려고 `meta.json` 을 함께 낸다.** 청크 수와 모델명이
로컬 코퍼스와 다르면 로컬에서 멈추게 한다 — 예전에 코퍼스를 43종에서 줄이고도
옛 임베딩(7,862×4096)이 남아 있었다.
""")
add(PY, """
import numpy as np, json

cfg = CONFIGS["C. 합친 것"]        # 파이프라인이 쓰는 것은 합친 색인이다
np.save("vectors.f16.npy", cfg["vec"].astype("float16"))
np.save("qvectors.f16.npy", qvec.astype("float16"))

meta = {"model": MODEL_NAME, "dim": int(cfg["vec"].shape[1]),
        "n": int(cfg["vec"].shape[0]),
        "n_rules": len(rules), "n_chunks": len(chunks),
        "index": "rule_index.jsonl", "normalized": True}
open("vectors.meta.json", "w", encoding="utf-8").write(
    json.dumps(meta, ensure_ascii=False, indent=1))
print(json.dumps(meta, ensure_ascii=False, indent=1))

from google.colab import files
files.download("vectors.f16.npy")
files.download("vectors.meta.json")
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
                       "index_ab_colab.ipynb")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(nb, f, ensure_ascii=False, indent=1)
    print(f"셀 {len(CELLS)}개 → {out}")


if __name__ == "__main__":
    main()
