# -*- coding: utf-8 -*-
"""rag/pipeline_full_colab.ipynb — 전체 파이프라인을 한 노트북에서 끝까지.

지금까지 노트북을 단계마다 따로 만들었다. 실험이라 그게 맞았지만(하나가 실패해도
나머지 GPU 시간을 안 버린다), **전체가 이어져 돌아가는 것을 한 번도 못 봤다.**
업로드도 모델 적재도 세 번씩이었다.

A100 40GB 면 리랭커(2GB)와 Gemma 27B 4비트(16GB)가 같이 올라간다. 그래서 합친다.

    ① 검색      BM25 → BGE-reranker-v2-m3 → 근거 5건        「왜 걸리나」
    ② 점검      체크리스트 → Gemma 판정                      「무엇이 걸리나」
    ③ 결과      광고별 심의 의견

**①과 ②는 잡는 것이 다르다.** 검색은 광고에 **있는** 표현을 보고 걸리는 규정을
찾고, 체크리스트는 **없는** 것을 찾는다. 누락은 검색으로 원리적으로 못 잡는다 —
광고에 「예금자보호」가 없으면 거기서 나올 질의도 없다.

  python rag/_build_colab_pipeline.py
"""
import os
import json

MD = "markdown"
PY = "code"

CELLS = []


def add(kind, text):
    CELLS.append((kind, text.strip("\n")))


add(MD, """
# 광고 심의 파이프라인 — 전체 실행 (Colab)

```
광고문 ─┬─ ① 검색   BM25 → 리랭커 → 근거 5건        「왜 걸리나」(조문·규칙)
        └─ ② 점검   체크리스트 → Gemma 판정          「무엇이 걸리나」(지적)
                                    ↓
                             ③ 심의 의견
```

**①과 ②는 잡는 것이 다르다.** 검색은 광고에 **있는** 표현에서 걸리는 규정을 찾고,
체크리스트는 **없는** 것을 찾는다. 누락은 검색으로 원리적으로 못 잡는다 — 광고에
「예금자보호」가 없으면 거기서 나올 질의도 없기 때문이다. 그런데 심의 지적의 큰
몫이 누락이다.

| | |
|---|---|
| **입력 4개** | `rule_index.jsonl` · `gold.json` · `checklist.json` · `ads.jsonl` |
| **모델 2개** | `BAAI/bge-reranker-v2-m3` · `google/gemma-4-31B-it` (GPU 보고 자동) |
| **출력** | `pipeline_report.md` · `pipeline_result.json` |

**런타임:** A100 권장. T4 면 Gemma 가 작은 모델로 내려가고 시간이 더 걸린다.
**HF 토큰 필요** — Gemma 는 라이선스 동의가 걸려 있다.
""")

add(MD, """
## 1. 환경

**허깅페이스 토큰이 필요 없다.** Gemma 4 는 Apache 2.0 이라 라이선스 동의 없이
받는다 — Gemma 2 는 동의와 토큰이 필요했다.
""")
add(PY, """
!nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
!pip -q install -U sentence-transformers transformers accelerate bitsandbytes 2>&1 | tail -1
""")

add(MD, """
## 2. 파일 업로드 (4개)

`output/_rag/` 에서 한 번에 고른다 — `rule_index.jsonl` · `gold.json` ·
`checklist.json` · `ads.jsonl`
""")
add(PY, """
from google.colab import files
import os
up = files.upload()
for n in up:
    print(f"{n:22s} {len(up[n])/1e6:6.1f}MB")
need = ["rule_index.jsonl", "gold.json", "checklist.json", "ads.jsonl"]
missing = [n for n in need if not os.path.exists(n)]
assert not missing, f"빠진 파일: {missing}"
""")

add(MD, """
## 3. 색인과 BM25

`rag/bm25.py` 원문 그대로다. 비슷하게 다시 쓰면 나중에 「Colab 이 좋았던 건지
토크나이저가 달랐던 건지」를 못 가린다.

**부칙은 뺀다** — 시행일·경과조치라 광고심의 근거가 될 수 없고, gold 334건과 규칙
1,744건이 한 번도 인용하지 않았다(청크의 20%). `is_active` 로 꺼져 있다.
""")
add(PY, r"""
import json, re, math, collections

index = [json.loads(l) for l in open("rule_index.jsonl", encoding="utf-8")]
gold = json.load(open("gold.json", encoding="utf-8"))
items = json.load(open("checklist.json", encoding="utf-8"))
ads = [json.loads(l) for l in open("ads.jsonl", encoding="utf-8")]
N_RULES = sum(1 for r in index if r["evidence_id"].startswith("R-"))
ACTIVE = [i for i, r in enumerate(index) if r.get("is_active", True)]
print(f"색인 {len(index):,} (규칙 {N_RULES:,} + 조문 {len(index)-N_RULES:,}) · "
      f"검색 대상 {len(ACTIVE):,}")
print(f"체크리스트 {len(items)}문항 · 광고 {len(ads)}건 · gold {len(gold)}건")

def text_of(r):
    return f"{r.get('title','')} {r.get('article_no','')} {r.get('content','')}"

_HANGUL = re.compile(r"[가-힣]+"); _WORD = re.compile(r"[A-Za-z0-9]+")
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
_docs, _df = [], collections.Counter()
for i in ACTIVE:
    tf = collections.Counter(tokenize(text_of(index[i]))); _docs.append(tf); _df.update(tf.keys())
_n = len(_docs)
_idf = {t: math.log(1 + (_n - c + 0.5) / (c + 0.5)) for t, c in _df.items()}
_inv = collections.defaultdict(list)
for j, d in enumerate(_docs):
    for t, f in d.items(): _inv[t].append((j, f))
_dl = [sum(d.values()) for d in _docs]; _avg = sum(_dl) / max(_n, 1)

def bm25(q, k=50):
    sc = collections.defaultdict(float)
    for t in set(tokenize(q)):
        post = _inv.get(t)
        if not post: continue
        w = _idf[t]
        for j, f in post:
            sc[j] += w * f * (K1+1) / (f + K1*(1 - B + B*_dl[j]/_avg))
    return [ACTIVE[j] for j, _ in sorted(sc.items(), key=lambda x: -x[1])[:k]]

print("BM25 준비 완료")
""")

add(MD, """
## 4. 리랭커 — 먼저 값어치를 확인한다

**정답은 이미 후보 안에 있고 순위만 틀렸다.** 실측:

| | R@5 | R@10 | R@20 | R@50 |
|---|---:|---:|---:|---:|
| BM25 | 14.4% | 43.4% | 67.7% | **80.2%** |

R@5 가 낮은 것은 **규칙이 상위를 79~86% 차지해 조문이 밀려서**다(전체에서 규칙
비중은 21%). 리랭커가 이걸 고치는지 gold 334건으로 먼저 재고, 값어치가 있으면
파이프라인에 넣는다. **안 재고 넣으면 나중에 무엇이 기여했는지 모른다.**
""")
add(PY, """
import torch, time
from sentence_transformers import CrossEncoder

dev = "cuda" if torch.cuda.is_available() else "cpu"
ce = CrossEncoder("BAAI/bge-reranker-v2-m3", device=dev, max_length=1024)

def rerank(q, cand, bs=64):
    pairs = [[q[:512], text_of(index[i])[:2000]] for i in cand]
    sc = ce.predict(pairs, batch_size=bs, show_progress_bar=False)
    return [i for i, _ in sorted(zip(cand, sc), key=lambda x: -x[1])]

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

def rule_share(rankings, k=5):
    tot = rn = 0
    for r in rankings:
        for d in r[:k]:
            tot += 1
            if d < N_RULES: rn += 1
    return rn / max(tot, 1)

CAND = [bm25(g["q"], 50) for g in gold]
t0 = time.time()
RR = []
for j, g in enumerate(gold):
    RR.append(rerank(g["q"], CAND[j]))
    if (j+1) % 80 == 0: print(f"  리랭킹 {j+1:>3}/{len(gold)}  {time.time()-t0:5.0f}초")

MEASURE = [("BM25 (후보 50)", score(CAND), rule_share(CAND)),
           ("+ 리랭커", score(RR), rule_share(RR))]
print()
for label, s, sh in MEASURE:
    print(f"{label:16s} " + " · ".join(f"R@{k} {s[f'R@{k}']*100:5.1f}%" for k in KS)
          + f" · MRR {s['MRR']:.3f} · 상위5 규칙비율 {sh*100:.0f}% (전체 21%)")

USE_RERANK = MEASURE[1][1]["R@5"] > MEASURE[0][1]["R@5"]
print(f"\\n→ 파이프라인에 리랭커를 {'쓴다' if USE_RERANK else '안 쓴다'}")
""")

add(MD, """
## 5. 체크리스트 — 광고에 던질 문항 고르기

`rag/checklist.py` 의 `for_ad()` 와 같은 규칙이다. 같은 질문은 묶고, 조건부 문항은
표시하고, 「전체」로 분류됐지만 투자성 전용인 것은 뺀다.

**출처 매뉴얼로 가르면 안 된다** — M12·전체·필수 40건 중 21건이 금소법 계열(모든
상품 공통)이라, 출처로 자르면 「수수료 부과기준」 같은 공통 의무가 통째로 사라진다.
근거 법령과 질문 낱말로 가른다.
""")
add(PY, r"""
import re

PRODUCT = {"예금성": "예금", "대출성": "대출", "투자성": "투자"}
_COND = re.compile(r"^\s*[(（]([^)）]{2,40})[)）]")
_COND_TAIL = re.compile(r"(?:하는|인|있는|받는)\s*경우|시\s|때\s")
_INV_BASIS = re.compile(r"협회규정|금투업규정|증발공|자본시장|투자광고")
_INV_WORD = re.compile(
    r"투자원금|금융투자상품|공모증권|투자설명서|집합투자|수익증권|파생결합|"
    r"랩\s?어카운트|투자자문|투자일임|퇴직연금|월지급식|펀드|신탁|"
    r"ELS|DLS|ELB|DLB|ELF|ETF|ETN|ELW|IMA|CMA|CFD")

def is_conditional(x):
    q, big = str(x.get("질문") or ""), str(x.get("대분류") or "")
    return bool(_COND.match(q) or _COND_TAIL.search(q[:40])
                or _COND_TAIL.search(big) or "시 " in big or big.endswith("시"))

def investment_only(x):
    if x["상품"] != "전체" or x["방향"] != "REQUIRE": return False
    return bool(_INV_BASIS.search(x.get("근거") or "")
                or _INV_WORD.search(x.get("질문") or ""))

def for_ad(product):
    want = {PRODUCT.get(product, product), "전체"}
    sel = [x for x in items if x["상품"] in want]
    if PRODUCT.get(product) != "투자":
        sel = [x for x in sel if not investment_only(x)]
    merged, seen = [], {}
    for x in sel:
        key = re.sub(r"\s+", "", x["질문"])
        if key in seen:
            m = seen[key]
            if x["근거"] and x["근거"] not in m["근거"]:
                m["근거"] = (m["근거"] + " / " + x["근거"]).strip(" /")
            continue
        y = dict(x, 조건부=is_conditional(x)); seen[key] = y; merged.append(y)
    return merged

for p in ("예금성", "대출성", "투자성"):
    s = for_ad(p)
    print(f"  {p} {len(s):>4}문항 (필수 {sum(1 for x in s if x['방향']=='REQUIRE')} · "
          f"금지 {sum(1 for x in s if x['방향']=='PROHIBIT')})")
""")

add(MD, """
## 6. Gemma 올리기

**Gemma 4 를 쓴다**(2026-04 공개). Gemma 2 보다 우리 쓰임새에 세 가지가 낫다.

| | Gemma 2 | Gemma 4 |
|---|---|---|
| 라이선스 | 동의 필요 · HF 토큰 필요 | **Apache 2.0** — 토큰 없이 받는다 |
| 컨텍스트 | 8K | **256K** — 87문항을 한 번에 넣어도 들어간다 |
| 언어 | 제한적 | **140개 이상** |

**GPU 를 보고 고른다.** 양자화는 메모리가 모자랄 때 어쩔 수 없이 하는 것이지 좋아서
하는 게 아니지만, 31B 4비트가 12B bf16 보다는 낫다 — 모델 크기 차이가 양자화 손실보다
크다.

| GPU | 고르는 것 |
|---|---|
| A100 40GB | `gemma-4-31B-it` 4비트 (~18GB) |
| L4 24GB | `gemma-4-12B-Unified-it` 4비트 (~7GB) |
| T4 15GB | `gemma-4-E4B-it` bf16 (~9GB) |
""")
add(PY, """
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

MODEL = None; FOURBIT = None      # 직접 고르려면 여기에 적는다
free = torch.cuda.get_device_properties(0).total_memory/1e9 if torch.cuda.is_available() else 0
gname = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
if MODEL is None:
    if free >= 36:   MODEL, FOURBIT = "google/gemma-4-31B-it", True
    elif free >= 22: MODEL, FOURBIT = "google/gemma-4-12B-Unified-it", True
    else:            MODEL, FOURBIT = "google/gemma-4-E4B-it", False
print(f"{gname} {free:.0f}GB → {MODEL} ({'4bit' if FOURBIT else 'bf16'})")

kw = dict(device_map="auto")
if FOURBIT:
    kw["quantization_config"] = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True)
else:
    kw["torch_dtype"] = torch.bfloat16

tok = AutoTokenizer.from_pretrained(MODEL)
gemma = AutoModelForCausalLM.from_pretrained(MODEL, **kw)
gemma.eval()
print(f"{MODEL} · {gemma.get_memory_footprint()/1e9:.1f}GB")

def ask(prompt, max_new=4096):
    # return_dict=True 를 명시한다. transformers 최신 버전은 apply_chat_template 가
    # 텐서가 아니라 BatchEncoding 을 주는데, 텐서인 줄 알고 .shape 를 부르면
    # AttributeError 로 죽는다(실측). **enc 로 넘기면 attention_mask 까지 같이
    # 들어가 구버전·신버전 양쪽에서 돈다.
    enc = tok.apply_chat_template([{"role": "user", "content": prompt}],
                                  add_generation_prompt=True,
                                  return_dict=True,
                                  return_tensors="pt").to(gemma.device)
    with torch.no_grad():
        out = gemma.generate(**enc, max_new_tokens=max_new, do_sample=False,
                             pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][enc["input_ids"].shape[-1]:], skip_special_tokens=True)

print(ask("한 문장으로 자기소개해 주세요.")[:160])
""")

add(MD, """
## 7. 판정 · 검색

프롬프트는 `rag/audit.py` 의 `_PROMPT` 를 글자 그대로 옮긴 것이다. 여기서 손보면
로컬과 갈라져서, 엔드포인트가 열렸을 때 어느 쪽이 검증된 것인지 알 수 없게 된다.

**파싱 실패를 판정으로 바꾸지 않는다.** 「확인필요」로 뭉개면 모델이 형식을 못 지킨
것과 진짜 애매한 광고가 구분되지 않는다.
""")
add(PY, r"""
import json, re

BATCH = 24
PROMPT = '''당신은 금융광고 심의 담당자입니다. 아래 광고문을 읽고, 점검 문항마다
판정하세요.

판정 값은 셋 중 하나입니다.
- OK    : 문항이 요구하는 바를 광고가 충족함
- NG    : 충족하지 않음 (표시할 것을 안 했거나, 하지 말아야 할 표현을 씀)
- N/A   : 이 광고에 해당하지 않는 문항 (예: 예금 광고에 대출 관련 문항)

**광고문에 실제로 있는 내용만 근거로 삼으세요.** 없는 것을 있다고 하거나, 짐작으로
채우지 마세요. 애매하면 N/A 가 아니라 NG 로 두고 사유에 「확인 필요」라고 쓰세요.

반드시 아래 JSON 배열 형식으로만 답하세요. 다른 말은 쓰지 마세요.
[{{"id": "CL-001", "판정": "OK|NG|N/A", "사유": "...", "근거문구": "광고문에서 인용"}}]

## 점검 문항
{items}

## 광고문
{ad}'''

def parse(text, chunk):
    m = re.search(r"\[.*\]", text or "", re.S)
    if not m:
        return [{"id": x["id"], "판정": None, "사유": "JSON 배열을 못 찾음", "근거문구": ""} for x in chunk]
    try:
        got = json.loads(m.group(0))
    except json.JSONDecodeError:
        return [{"id": x["id"], "판정": None, "사유": "JSON 파싱 실패", "근거문구": ""} for x in chunk]
    by = {str(g.get("id")): g for g in got if isinstance(g, dict)}
    return [{"id": x["id"],
             "판정": (by.get(x["id"]) or {}).get("판정"),
             "사유": (by.get(x["id"]) or {}).get("사유", "LLM 이 빠뜨림"),
             "근거문구": (by.get(x["id"]) or {}).get("근거문구", "")} for x in chunk]

def audit(ad):
    sel = for_ad(ad.get("상품군"))
    v = []
    for s in range(0, len(sel), BATCH):
        chunk = sel[s:s+BATCH]
        body = "\n".join(
            f'{x["id"]} [{"있어야 함" if x["방향"]=="REQUIRE" else "없어야 함"}] {x["질문"]}'
            for x in chunk)
        v += parse(ask(PROMPT.format(items=body, ad=ad["text"][:6000])), chunk)
    return sel, v

def evidences(ad, k=5):
    # 광고 전문을 질의로. 청크로 쪼개 각각 검색한 뒤 합치는 것이 낫지만, 여기서는
    # 파이프라인이 이어지는지를 보는 것이 목적이라 단순하게 둔다.
    cand = bm25(ad["text"][:2000], 50)
    order = rerank(ad["text"][:2000], cand) if USE_RERANK else cand
    return [{"evidence_id": index[i]["evidence_id"],
             "kind": "규칙" if i < N_RULES else "조문",
             "title": index[i].get("title", ""),
             "article_no": index[i].get("article_no", "")} for i in order[:k]]
""")

add(MD, """
## 8. 한 건만 먼저

18건을 다 돌리고 나서 형식이 틀린 걸 발견하면 GPU 시간을 통째로 버린다.
""")
add(PY, """
import collections

ad = next(a for a in ads if a["광고id"] == "2026_005_예금성")
sel, v = audit(ad)
by = {x["id"]: x for x in sel}
print(f"{ad['광고id']} · {collections.Counter(str(x['판정']) for x in v).most_common()}\\n")
for x in v:
    if x["판정"] == "NG":
        print(f"  NG  {by[x['id']]['질문'][:56]}")
        print(f"      {str(x['사유'])[:76]}")
print("\\n근거:")
for e in evidences(ad):
    print(f"  [{e['kind']}] {e['evidence_id']} {e['title'][:48]}")
""")

add(MD, """
## 9. 전체 18건

한 건에 87~94문항이라 A100 27B 기준 3~5분씩, 전체 1시간 안팎이다. 오래 걸리면
`ads[:6]` 으로 줄여도 된다.
""")
add(PY, """
import json, time, collections

results = []
t0 = time.time()
for i, ad in enumerate(ads, 1):
    sel, v = audit(ad)
    by = {x["id"]: x for x in sel}
    ng = [x for x in v if x["판정"] == "NG"]
    results.append({
        "광고id": ad["광고id"], "판본": ad.get("판본"), "상품군": ad.get("상품군"),
        "문항수": len(sel),
        "요약": collections.Counter(str(x["판정"]) for x in v).most_common(),
        "지적": [{"질문": by[x["id"]]["질문"], "방향": by[x["id"]]["방향"],
                 "조건부": by[x["id"]]["조건부"],
                 "근거": by[x["id"]]["근거"] or "(근거 없음)",
                 "사유": x["사유"], "근거문구": x["근거문구"]} for x in ng],
        "검색근거": evidences(ad),
        "전체": v,
    })
    print(f"[{i}/{len(ads)}] {ad['광고id']:20s} 지적 {len(ng):>2}건  "
          f"{results[-1]['요약']}  {time.time()-t0:5.0f}초")

json.dump(results, open("pipeline_result.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\\n저장: pipeline_result.json")
""")

add(MD, "## 10. 보고서")
add(PY, """
lines = ["# 광고 심의 파이프라인 실행 결과", "",
         f"광고 {len(results)}건 · 판정 {MODEL} ({'4bit' if FOURBIT else 'bf16'}) · "
         f"리랭커 {'사용' if USE_RERANK else '미사용'}", "",
         "## 검색 성능 (gold 334건)", "",
         "| 방식 | R@1 | R@3 | R@5 | R@10 | MRR | 상위5 규칙비율 |",
         "|---|---:|---:|---:|---:|---:|---:|"]
for label, s, sh in MEASURE:
    lines.append(f"| {label} | " + " | ".join(f"{s[f'R@{k}']*100:.1f}%" for k in KS)
                 + f" | {s['MRR']:.3f} | {sh*100:.0f}% |")
lines += ["", "전체에서 규칙이 차지하는 비중은 21.0% 다. 상위5 규칙비율이 여기 가까울수록",
          "종류에 안 치우치고 내용으로 매긴다는 뜻이다.", "",
          "## 광고별 판정", "",
          "| 광고 | 상품군 | 문항 | OK | NG | N/A | 못읽음 |",
          "|---|---|---:|---:|---:|---:|---:|"]
for r in results:
    d = dict(r["요약"])
    lines.append(f"| {r['광고id']} | {r['상품군']} | {r['문항수']} | {d.get('OK',0)} | "
                 f"{d.get('NG',0)} | {d.get('N/A',0)} | {d.get('None',0)} |")

lines += ["", "## 지적 사항", ""]
for r in results:
    if not r["지적"]:
        continue
    lines += [f"### {r['광고id']} ({r['상품군']})", ""]
    for g in r["지적"]:
        cond = " · 조건부" if g["조건부"] else ""
        lines += [f"- **[{g['방향']}{cond}] {g['질문']}**",
                  f"  - 근거: {g['근거']}", f"  - 사유: {g['사유']}"]
        if g["근거문구"]:
            lines.append(f"  - 광고문: 「{g['근거문구']}」")
    lines += ["", "  검색으로 찾은 관련 규정:"]
    for e in r["검색근거"]:
        lines.append(f"  - [{e['kind']}] {e['evidence_id']} {e['title']}")
    lines.append("")

bad = sum(dict(r["요약"]).get("None", 0) for r in results)
tot = sum(r["문항수"] for r in results)
lines += ["## 형식 준수", "",
          f"응답을 못 읽은 문항 {bad}/{tot} ({bad/max(tot,1)*100:.1f}%)", "",
          "이 값이 크면 판정 품질 이전에 **형식**이 문제다 — 배치 크기를 줄이거나",
          "max_new_tokens 를 늘려야 한다."]

open("pipeline_report.md", "w", encoding="utf-8").write("\\n".join(lines))
print("\\n".join(lines[:44]))

from google.colab import files
files.download("pipeline_report.md")
files.download("pipeline_result.json")
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
                       "pipeline_full_colab.ipynb")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(nb, f, ensure_ascii=False, indent=1)
    print(f"셀 {len(CELLS)}개 → {out}")


if __name__ == "__main__":
    main()
