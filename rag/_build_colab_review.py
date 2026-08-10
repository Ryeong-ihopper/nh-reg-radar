# -*- coding: utf-8 -*-
"""rag/review_colab.ipynb — **양방향을 한 노트북에서 잇는다.**

지금까지 만든 것이 옆으로 흩어져 있었다. 누락 검출은 `detect.py`, 검색은
`search.py`, 리랭커는 `pipeline.py` 에 있는데 서로 안 부른다. 여기서 하나로 잇고
실물 광고 15건을 심의사례로 채점한다.

    광고 하나 들어옴
      │
      ├─ ① 목록 → 광고    상품군으로 규칙 목록을 조회(검색 아님)
      │                   조건부 규칙은 조건이 맞을 때만
      │                   문구가 있는 규칙 → 룰로 판정
      │                   문구가 없는 규칙 → LLM 에 **규칙 문장 그대로** 좁게 물음
      │                   → 있어야 할 것이 없다 (누락)
      │
      ├─ ② 광고 → 조문    광고에서 질의를 만들어 BM25 검색 → 리랭커로 재정렬
      │                   → 지적마다 근거 조문 원문을 붙인다
      │
      └─ 합쳐서 심의사례 모양으로 출력 → 심의사례 15건으로 채점

**①이 없으면 누락을 못 잡고, ②가 없으면 근거를 못 댄다.** 둘 다 있어야 심의사례
한 줄이 완성된다.

  python rag/_build_colab_review.py
"""
import os
import json

MD, PY = "markdown", "code"
CELLS = []


def add(kind, text):
    CELLS.append((kind, text.strip("\n")))


add(MD, """
# 광고 심의 — 양방향 파이프라인

## 무엇을 하나

```
광고 하나
  ├─ ① 목록 → 광고   상품군으로 규칙을 조회하고 광고에 대조   → 누락
  ├─ ② 광고 → 조문   광고에서 질의를 만들어 검색 + 리랭킹     → 근거
  └─ 합쳐서 심의사례 모양으로
```

**두 방향이 잡는 것이 다르다.** 광고에 예금자보호 문구가 없으면 광고에서 뽑은
어떤 질의도 그 조문을 안 가져온다. 그래서 ①은 광고를 보기 **전에** 요구 목록을
정한다. 반대로 「업계 최고」 같은 표현은 목록에 있어도 광고를 읽어야 발견된다.

## 왜 이번엔 다를 수 있나

앞선 실행에서 LLM 판정이 심의사례 기준 **0/5** 였다. 원인이 둘이었다.

| | 전 | 이번 |
|---|---|---|
| 무엇을 던지나 | 체크리스트 87문항 | **규칙 345~492건** |
| 물음의 넓이 | "이자율·수익률의 범위 및 산출기준을 표시하였는가?" | "「기간별 이율」·「중도해지 이율」·「만기 후 이율」이 각각 표기되어 있는지 확인" |
| 결과 | 광고에 금리 얘기만 있으면 OK | ? |

「만기후이율 누락」 지적에 해당하는 규칙 **R-0610 이 체크리스트에는 아예 없었다.**
안 물었으니 못 잡은 것이다.

## 준비

| | |
|---|---|
| 런타임 | A100 권장 |
| 업로드 | `checks_예금.json` · `checks_대출.json` · `ads.jsonl` · `ad_gold.json` · `rule_index.jsonl` |
| 출력 | `review_report.md` · `review_result.json` |
| 소요 | 예금성 5건 약 50분 · 전체 15건 약 3시간 반 |

**예금성 5건을 먼저 돌린다.** 3번 셀의 `ONLY` 가 그것이다. 결과가 쓸 만하면
`ONLY = None` 으로 바꿔 대출성까지 돌린다. 나쁜데 3시간을 태우면 그 시간은
돌아오지 않는다.
""")

add(MD, "## 1. 환경")
add(PY, """
!nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
!pip -q install -U transformers accelerate sentence-transformers 2>&1 | tail -1
""")

add(MD, "## 2. 업로드")
add(PY, """
from google.colab import files
import os
up = files.upload()
need = ["checks_예금.json", "checks_대출.json", "ads.jsonl", "ad_gold.json",
        "rule_index.jsonl"]
missing = [n for n in need if not os.path.exists(n)]
assert not missing, f"빠진 파일: {missing}"
for n in need:
    print(f"{n:22s} {os.path.getsize(n)/1e6:6.1f}MB")
""")

add(MD, """
## 3. 무엇을 얼마나 던질지 먼저 센다

규칙이 광고당 345~492건이다. 그대로 던지면 광고 하나에 배치 20개가 넘고 15건이면
GPU 를 하루 쓴다. **줄일 수 있는 것을 먼저 줄이고, 남은 양을 보고 시작한다.**

줄이는 방법 둘:

- **조건부 규칙** — 「환율·주가연동예금을 광고하는 경우」처럼 조건이 붙은 규칙은
  조건 낱말이 광고에 없으면 애초에 해당이 안 된다. 던질 이유가 없다
- **문구가 있는 규칙** — 룰로 판정한다. LLM 을 부르지 않는다
""")
add(PY, r"""
import json, re, collections

CHECKS = {p: json.load(open(f"checks_{p}.json", encoding="utf-8"))["checks"]
          for p in ("예금", "대출")}
ads = {}
for l in open("ads.jsonl", encoding="utf-8"):
    x = json.loads(l)
    ads.setdefault(x["광고id"], x)
gold = json.load(open("ad_gold.json", encoding="utf-8"))["건"]

# **한 번에 다 돌리지 않는다.** 15건 전부면 LLM 호출 309회, 3시간 반이다.
# 예금성 5건(약 50분)을 먼저 보고, 쓸 만하면 ONLY 를 바꿔 대출성을 돌린다.
# 결과가 나쁜데 3시간을 태우면 그 시간은 돌아오지 않는다.
ONLY = "예금성"          # None 이면 전부
gold = [g for g in gold if not ONLY or ONLY in g["광고id"]]
TARGET = [g["광고id"] for g in gold]
print(f"규칙 예금 {len(CHECKS['예금'])} · 대출 {len(CHECKS['대출'])}")
print(f"채점 대상 광고 {len(TARGET)}건 (심의사례 정답이 있는 것)")

def norm(s):
    return re.sub(r"[\s·ㆍ]", "", str(s or ""))

# 이 광고에 던질 규칙. **조건이 안 맞는 것만 뺀다** — 내용이 없다고 빼면 누락을 못 잡는다.
def applicable(checks, ad_text):
    out = []
    for c in checks:
        cond = c.get("condition") or []
        if cond and not any(norm(w) in norm(ad_text) for w in cond):
            continue
        out.append(c)
    return out

BATCH = 20
total = 0
for aid in TARGET:
    p = "예금" if "예금성" in aid else "대출"
    sel = applicable(CHECKS[p], ads[aid]["text"])
    llm = [c for c in sel if c["kind"] == "LLM"]
    total += -(-len(llm) // BATCH)
    print(f"  {aid:18s} 적용 {len(sel):3d} · 룰 {len(sel)-len(llm):2d} · "
          f"LLM {len(llm):3d} → 배치 {-(-len(llm)//BATCH)}")
print(f"\nLLM 호출 총 {total}회 · 한 번 40초로 잡으면 약 {total*40/60:.0f}분")
""")

add(MD, """
## 4. 방향 ① — 목록에서 출발 (룰)

문구가 있는 규칙은 LLM 없이 판정한다. **글자가 있느냐 없느냐는 판단이 아니라
사실**이라 모델에게 물을 이유가 없다.
""")
add(PY, r"""
import re, datetime

TODAY = datetime.date(2026, 8, 7)

# 룰 판정. 못 정하면 None 을 준다 — 억지로 정하면 근거 없는 지적이 된다.
def judge_rule(c, ad_text):
    p = c.get("params") or {}
    pat = p.get("pattern")
    if not pat:
        return None
    if isinstance(pat, str):                      # 정규식
        return "OK" if re.search(pat, ad_text) else "NG"
    A = norm(ad_text)
    # 긴 문구는 광고마다 말이 조금씩 다르다 — 낱말 70% 겹치면 있는 것으로 본다
    def has(x):
        if len(norm(x)) < 8:
            return norm(x) in A
        ws = [w for w in re.split(r"[^가-힣A-Za-z0-9]+", x) if len(w) >= 2]
        return ws and sum(1 for w in ws if norm(w) in A) / len(ws) >= 0.7
    found = [x for x in pat if has(x)]
    if c["kind"] == "PROHIBIT":
        return "NG" if found else "OK"
    return "OK" if len(found) == len(pat) else "NG"

rule_out = {}
for aid in TARGET:
    p = "예금" if "예금성" in aid else "대출"
    t = ads[aid]["text"]
    fs = []
    for c in applicable(CHECKS[p], t):
        v = judge_rule(c, t)
        if v == "NG":
            fs.append({"규칙": c["id"], "제목": c["title"], "판정": "NG",
                       "근거규정": c["article_no"], "개선안": c["recommendation"],
                       "판정근거": "RULE"})
    rule_out[aid] = fs
    print(f"  {aid:18s} 룰 지적 {len(fs)}건  " +
          ", ".join(x["규칙"] for x in fs[:5]))
""")

add(MD, """
## 5. Gemma
""")
add(PY, """
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

free = torch.cuda.get_device_properties(0).total_memory/1e9 if torch.cuda.is_available() else 0
MODEL = "google/gemma-4-12B-it" if free >= 26 else "google/gemma-4-E4B-it"
print(f"{torch.cuda.get_device_name(0) if free else 'CPU'} {free:.0f}GB → {MODEL}")

tok = AutoTokenizer.from_pretrained(MODEL)
gemma = AutoModelForCausalLM.from_pretrained(MODEL, device_map="auto",
                                             torch_dtype=torch.bfloat16)
gemma.eval()

def ask(prompt, max_new=3072):
    enc = tok.apply_chat_template([{"role": "user", "content": prompt}],
                                  add_generation_prompt=True, return_dict=True,
                                  return_tensors="pt").to(gemma.device)
    with torch.no_grad():
        out = gemma.generate(**enc, max_new_tokens=max_new, do_sample=False,
                             pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][enc["input_ids"].shape[-1]:], skip_special_tokens=True)

print(ask("한 문장으로 자기소개해 주세요.")[:100])
""")

add(MD, """
## 6. 방향 ① — 목록에서 출발 (LLM)

**규칙 문장을 그대로 넘긴다.** 요약하거나 다시 쓰지 않는다 — 앞선 실패가 물음을
넓게 만든 데서 왔다.

프롬프트에 못 박는 것 셋:

1. 광고문에 **실제로 있는 문장만** 근거로 삼을 것
2. 근거 문구는 **광고문에서 그대로 복사**할 것 (지어내면 뒤에서 걸러진다)
3. 규칙이 요구하는 것이 **여러 개면 하나라도 빠지면 NG**
""")
add(PY, r"""
import json, re, time

PROMPT = '''당신은 금융광고 심의 담당자입니다. 아래 광고문을 읽고, 규칙마다 판정하세요.

판정 값은 셋 중 하나입니다.
- OK  : 규칙이 요구하는 것이 광고에 모두 있음
- NG  : 요구하는 것 중 하나라도 빠졌거나, 금지된 표현이 있음
- N/A : 이 광고에 해당하지 않는 규칙

규칙을 **글자 그대로** 보세요. 비슷한 내용이 있다고 넘어가지 마세요.
예: 「기간별 이율·중도해지 이율·만기 후 이율이 각각 표기」를 요구하는데
    광고에 기본이율만 있으면 NG 입니다.

근거문구는 **광고문에 있는 문장을 그대로 복사**하세요. 없으면 빈 문자열로 두세요.

아래 JSON 배열로만 답하세요.
[{{"id": "R-0001", "판정": "OK|NG|N/A", "사유": "...", "근거문구": "광고문에서 그대로"}}]

## 규칙
{items}

## 광고문
{ad}'''

def parse(text, chunk):
    m = re.search(r"\[.*\]", text or "", re.S)
    if not m:
        return [{"id": c["id"], "판정": None, "사유": "JSON 못 찾음", "근거문구": ""} for c in chunk]
    try:
        got = json.loads(m.group(0))
    except json.JSONDecodeError:
        return [{"id": c["id"], "판정": None, "사유": "JSON 파싱 실패", "근거문구": ""} for c in chunk]
    by = {str(g.get("id")): g for g in got if isinstance(g, dict)}
    return [{"id": c["id"],
             "판정": (by.get(c["id"]) or {}).get("판정"),
             "사유": (by.get(c["id"]) or {}).get("사유", "LLM 이 빠뜨림"),
             "근거문구": (by.get(c["id"]) or {}).get("근거문구", "")} for c in chunk]

def ask_batch(chunk, ad_text):
    body = "\n".join(f'{c["id"]} [{c["kind"]}] {c["criterion"] or c["title"]}'
                     for c in chunk)
    got = parse(ask(PROMPT.format(items=body, ad=ad_text[:6000])), chunk)
    if all(g["판정"] is None for g in got) and len(chunk) > 5:
        mid = len(chunk) // 2
        return ask_batch(chunk[:mid], ad_text) + ask_batch(chunk[mid:], ad_text)
    return got

try:
    LLM_OUT
except NameError:
    LLM_OUT = {}

t0 = time.time()
for i, aid in enumerate(TARGET, 1):
    if aid in LLM_OUT:
        continue
    p = "예금" if "예금성" in aid else "대출"
    t = ads[aid]["text"]
    sel = [c for c in applicable(CHECKS[p], t) if c["kind"] == "LLM"]
    v = []
    for s in range(0, len(sel), BATCH):
        v += ask_batch(sel[s:s+BATCH], t)
        print(f"  [{i}/{len(TARGET)}] {aid} {min(s+BATCH,len(sel))}/{len(sel)} "
              f"{time.time()-t0:5.0f}초")
    LLM_OUT[aid] = v
    json.dump({k: [{"id": x["id"], "판정": x["판정"]} for x in vs]
               for k, vs in LLM_OUT.items()},
              open("review_result.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
print(f"완료 {len(LLM_OUT)}/{len(TARGET)}")
""")

add(MD, """
## 7. 인용 검증 — 지어낸 근거를 거른다

LLM 이 「있다」고 하면서 든 근거 문구가 **광고문에 실제로 있는지** 글자로 확인한다.
없으면 그 OK 는 못 믿는다.

앞선 실행에서는 인용이 진짜였는데도 판정이 틀렸다(물음이 넓어서). 그래도 이
검사는 남긴다 — 넓은 물음 문제를 고친 뒤에도 지어내기는 따로 생길 수 있다.
""")
add(PY, r"""
def cited(q, ad_text):
    q = re.sub(r"\s", "", str(q or ""))
    return bool(q) and q[:20] in re.sub(r"\s", "", ad_text)

bad = 0
for aid, vs in LLM_OUT.items():
    t = ads[aid]["text"]
    for x in vs:
        if x["판정"] == "OK" and x["근거문구"] and not cited(x["근거문구"], t):
            x["판정"] = "확인필요"
            x["사유"] = "근거 문구가 광고문에 없음 — " + str(x["사유"])[:60]
            bad += 1
print(f"인용이 광고문에 없어 「확인필요」로 내린 것 {bad}건")
""")

add(MD, """
## 8. 방향 ② — RAG Engine (하이브리드 + RRF + 리랭커)

지적마다 근거 조문 **원문**을 달아야 심의사례 한 줄이 완성된다. 규칙에 붙어 있는
것은 「기준 §16① 5 나」 같은 **문자열**이라, 실제 조문을 가져오려면 색인을 뒤져야
한다. 이것이 판단엔진 넷 중 **RAG Engine** 의 일이다(ADR-0013).

확정된 방식대로 **다 붙인다** — 지금까지는 BM25 만 쓰고 있었다.

```
키워드(BM25, 바이그램+조문번호)  ─┐
                                 ├─ RRF(k=60) ─→ 상위 30 ─→ 리랭커 ─→ 상위 3
벡터(BGE-M3, 코사인)            ─┘
```

**BM25 단독으로 정했던 것을 되돌린다.** 그때 측정은 벡터를 리랭커 없이 단독으로
견준 것이라 조건이 좁았다. 여기서는 셋을 같은 조건으로 견주고 숫자를 남긴다.

지표는 `EVIDENCE_PRECISION`(근거 매칭 적정성, 목표 85%) 이다 — 우리가 내놓은 근거
중 관련 있는 것의 비율이다. Recall@k 가 아니다.
""")
add(PY, r"""
import math, collections
import numpy as np

rows = [json.loads(l) for l in open("rule_index.jsonl", encoding="utf-8")]
n_rules = sum(1 for r in rows if r["evidence_id"].startswith("R-"))
print(f"색인 {len(rows):,}건 (규칙 {n_rules} + 조문 {len(rows)-n_rules})")

def tokenize(s):
    s = re.sub(r"\s+", " ", str(s or ""))
    out = re.findall(r"제\s*\d+조(?:의\s*\d+)?|[A-Za-z]+|\d+", s)
    for w in re.findall(r"[가-힣]+", s):
        out += [w[i:i+2] for i in range(len(w)-1)] or [w]
    return out

def index_text(r):
    return f"{r.get('title','')} {r.get('article_no','') or ''} {r.get('content','')}"

docs, df = [], collections.Counter()
for r in rows:
    tf = collections.Counter(tokenize(index_text(r)))
    docs.append(tf); df.update(tf.keys())
N = len(docs)
IDF = {t: math.log(1+(N-n+0.5)/(n+0.5)) for t, n in df.items()}
INV = collections.defaultdict(list)
for i, d in enumerate(docs):
    for t, f in d.items():
        INV[t].append((i, f))
DL = [sum(d.values()) for d in docs]
AVGDL = sum(DL)/N

# 근거는 조문이어야 한다 — 규칙을 근거로 내밀면 「우리 규칙이 근거」가 되어 순환이다
ARTICLE = np.array([i >= n_rules for i in range(len(rows))])

def bm25(q, k=50):
    K1, B = 1.2, 0.75
    sc = collections.defaultdict(float)
    for t in set(tokenize(q)):
        post = INV.get(t)
        if not post:
            continue
        w = IDF[t]
        for i, f in post:
            if i < n_rules:
                continue
            sc[i] += w*f*(K1+1)/(f+K1*(1-B+B*DL[i]/AVGDL))
    return [i for i, _ in sorted(sc.items(), key=lambda x: -x[1])[:k]]
print("BM25 준비 완료")
""")

add(MD, """
### 벡터 — BGE-M3

색인 전체를 임베딩한다. 8,309건이라 A100 에서 3~5분이면 끝난다.
**미리 만들어 둔 `vectors.f16.npy` 를 안 쓰는 이유** — 그 파일이 지금 색인과 같은
순서인지 확인할 방법이 노트북 안에 없다. 어긋난 벡터로 검색하면 조용히 엉뚱한
결과가 나오고, 그게 성능 문제로 보인다.
""")
add(PY, """
from sentence_transformers import SentenceTransformer
import numpy as np

EMB = SentenceTransformer("BAAI/bge-m3")
texts = [index_text(r)[:1200] for r in rows]
V = EMB.encode(texts, batch_size=64, normalize_embeddings=True,
               show_progress_bar=True).astype("float32")
print("벡터", V.shape)

def vec(q, k=50):
    qv = EMB.encode([q], normalize_embeddings=True).astype("float32")[0]
    s = V @ qv
    s[~ARTICLE] = -1e9                      # 조문만
    return list(np.argsort(-s)[:k])
""")

add(MD, """
### RRF 로 합치고 리랭커로 줄 세운다

RRF 는 점수가 아니라 **순위**를 더한다. BM25 점수와 코사인 유사도는 자릿수가 달라
그대로 더하면 한쪽이 묻힌다.

리랭커는 질의와 문서를 **같이 읽는다**(교차 인코더). 벡터처럼 각자 따로 압축한 뒤
견주는 게 아니라, 둘을 한 번에 보고 관련성을 매긴다. 느린 대신 정확해서 상위
30개만 다시 줄 세우는 데 쓴다.

**리랭커를 실제로 붙이는 것은 이번이 처음이다.**
""")
add(PY, """
from sentence_transformers import CrossEncoder
RR = CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=512)

RRF_K = 60

def rrf(*rankings, top=30):
    sc = collections.defaultdict(float)
    for rank in rankings:
        for r, i in enumerate(rank, 1):
            sc[i] += 1.0/(RRF_K+r)
    return [i for i, _ in sorted(sc.items(), key=lambda x: -x[1])[:top]]

def evidences(query, k=3, how="hybrid"):
    if how == "bm25":
        cand = bm25(query, 30)
    elif how == "vector":
        cand = vec(query, 30)
    else:
        cand = rrf(bm25(query, 50), vec(query, 50), top=30)
    if not cand:
        return []
    pairs = [[query, index_text(rows[i])[:900]] for i in cand]
    order = sorted(zip(cand, RR.predict(pairs)), key=lambda x: -x[1])[:k]
    return [{"evidence_id": rows[i]["evidence_id"], "title": rows[i].get("title",""),
             "article_no": rows[i].get("article_no"),
             "본문": (rows[i].get("content") or "")[:400],
             "점수": float(s)} for i, s in order]

q = "예금 이율 기간별 중도해지 만기후 이율 표기"
for how in ("bm25", "vector", "hybrid"):
    e = evidences(q, 1, how)
    print(f"{how:8s} {e[0]['title'][:40] if e else '-'}  {e[0]['점수']:.3f}" if e else how)
""")

add(MD, """
### 세 방식을 같은 조건으로 견준다

`ad_gold` 15건에 심의사례가 적어 놓은 근거 조문이 있다. 광고에 걸린 지적의 근거를
셋 중 무엇이 잘 찾는지 본다. **리랭커를 셋 다에 붙여** 조건을 맞춘다 — 전에는
리랭커 없이 견줘서 벡터가 불리했다.
""")
add(PY, r"""
gold_by_ad = {g["광고id"]: g for g in gold}
KL = (1, 3, 5)
print(f"{'방식':10s} " + " ".join(f"R@{k}" for k in KL))
for how in ("bm25", "vector", "hybrid"):
    hit = {k: 0 for k in KL}
    n = 0
    for g in gold:
        ans = set(g["정답청크"])
        if not ans:
            continue
        n += 1
        got = evidences(g["체크항목"], max(KL), how)
        idx = [i for i, r in enumerate(rows) if False]     # 자리표시
        pos = None
        for r, e in enumerate(got, 1):
            j = next((i for i, x in enumerate(rows) if x["evidence_id"] == e["evidence_id"]), None)
            if j is not None and (j - n_rules) in ans:
                pos = r; break
        for k in KL:
            if pos and pos <= k:
                hit[k] += 1
    print(f"{how:10s} " + " ".join(f"{hit[k]/n*100:5.1f}%" for k in KL) + f"  (n={n})")
""")

add(MD, """
## 9. 두 방향을 합친다 — 심의사례 모양으로
""")
add(PY, r"""
CK = {c["id"]: c for p in CHECKS for c in CHECKS[p]}

REPORT = {}
for aid in TARGET:
    fs = list(rule_out.get(aid, []))
    for x in LLM_OUT.get(aid, []):
        if x["판정"] not in ("NG", "확인필요"):
            continue
        c = CK.get(x["id"], {})
        fs.append({"규칙": x["id"], "제목": c.get("title", ""), "판정": x["판정"],
                   "근거규정": c.get("article_no"), "사유": x["사유"],
                   "인용": x["근거문구"], "개선안": c.get("recommendation"),
                   "판정근거": "LLM"})
    # 지적마다 근거 조문 원문을 붙인다 — 방향 ②
    for f in fs:
        f["근거조문"] = evidences(f["제목"] or f["규칙"])
    REPORT[aid] = fs
    print(f"  {aid:18s} 지적 {len(fs):3d}건 "
          f"(룰 {sum(1 for f in fs if f['판정근거']=='RULE')} / "
          f"LLM {sum(1 for f in fs if f['판정근거']=='LLM')})")
""")

add(MD, """
## 10. 채점 — 심의사례가 적은 지적을 잡았나

심의사례 15건은 **사람이 독립적으로 만든 정답**이다. 다만 광고마다 지적이 1건뿐이라
**회수만 잴 수 있고 정밀도는 못 잰다** — 정답에 없는 지적이 나왔다고 틀린 게 아니다.
심의사례는 걸린 것만 적지 안 걸린 것을 적지 않는다.
""")
add(PY, r"""
import difflib

def sim(a, b):
    n = lambda s: re.sub(r"[\s()「」·]", "", str(s or ""))
    return difflib.SequenceMatcher(None, n(a), n(b)).ratio()

hit, rows_out = 0, []
for g in gold:
    aid = g["광고id"]
    fs = REPORT.get(aid, [])
    # 심의사례의 「체크항목 + 지적」과 가장 비슷한 지적을 찾는다
    best, score = None, 0.0
    for f in fs:
        s = max(sim(g["체크항목"], f["제목"]), sim(g["지적"], f["제목"]))
        if s > score:
            best, score = f, s
    got = score >= 0.45
    hit += got
    rows_out.append((aid, g["지적"], best, score, got))
    print(f"  {'○' if got else '✕'} {aid:18s} {g['지적'][:30]:30s} "
          f"→ {(best or {}).get('규칙','-')} {(best or {}).get('제목','')[:26]} ({score:.2f})")

print(f"\n심의사례 {len(gold)}건 중 잡음 {hit} ({hit/len(gold)*100:.0f}%)")
print("비교: 체크리스트 87문항 + LLM 으로 했을 때는 예금성 5건 중 0건이었다.")
""")

add(MD, "## 11. 보고서")
add(PY, r"""
lines = ["# 광고 심의 — 양방향 파이프라인 결과", "",
         f"모델 {MODEL} · 광고 {len(REPORT)}건 · 규칙 예금 {len(CHECKS['예금'])} / "
         f"대출 {len(CHECKS['대출'])}", "",
         f"**심의사례 {len(gold)}건 중 잡음 {hit} ({hit/len(gold)*100:.0f}%)**", "",
         "| 광고 | 심의사례 지적 | 우리 지적 | 유사도 | |", "|---|---|---|---:|---|"]
for aid, 지적, best, score, got in rows_out:
    lines.append(f"| {aid} | {지적[:30]} | {(best or {}).get('규칙','-')} "
                 f"{(best or {}).get('제목','')[:26]} | {score:.2f} | "
                 f"{'○' if got else '✕'} |")

lines += ["", "## 광고별 지적", ""]
for aid, fs in REPORT.items():
    lines += [f"### {aid}  — 지적 {len(fs)}건", ""]
    for f in fs[:12]:
        lines += [f"- **{f['규칙']}** {f['제목']}  `{f['판정']}` ({f['판정근거']})",
                  f"  - 사유: {str(f.get('사유') or '')[:100]}",
                  f"  - 개선안: {f.get('개선안')}"]
        for e in (f.get("근거조문") or [])[:2]:
            lines.append(f"  - 근거: {e['title']} {e['article_no'] or ''} "
                         f"(점수 {e['점수']:.2f})")
    if len(fs) > 12:
        lines.append(f"- … 외 {len(fs)-12}건")
    lines.append("")

lines += ["## 이 숫자를 읽는 법", "",
          "심의사례는 **걸린 것만** 적는다. 정답에 없는 지적이 나왔다고 틀린 게 아니라",
          "사람이 봐야 한다. 그래서 여기서 재는 것은 **회수**이지 정밀도가 아니다.", "",
          "지적이 광고당 수십 건 나오면 회수가 높아도 쓸모가 없다. **광고별 지적 수**를",
          "같이 봐야 한다."]

open("review_report.md", "w", encoding="utf-8").write("\n".join(lines))
print("\n".join(lines[:30]))

json.dump(REPORT, open("review_result.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
from google.colab import files
files.download("review_report.md")
files.download("review_result.json")
""")


def main():
    nb = {
        "cells": [{"cell_type": k, "metadata": {},
                   **({"outputs": [], "execution_count": None} if k == PY else {}),
                   "source": t.splitlines(keepends=True)} for k, t in CELLS],
        "metadata": {"kernelspec": {"display_name": "Python 3", "name": "python3"},
                     "language_info": {"name": "python"},
                     "accelerator": "GPU", "colab": {"provenance": []}},
        "nbformat": 4, "nbformat_minor": 0,
    }
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "review_colab.ipynb")
    json.dump(nb, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"셀 {len(CELLS)}개 → {out}")


if __name__ == "__main__":
    main()
