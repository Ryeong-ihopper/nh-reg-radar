# -*- coding: utf-8 -*-
"""rag/gemma_audit_colab.ipynb 를 만든다.

**목으로는 판정이 안 된다.** 낱말 겹침으로는 「표시했는가」의 O/X 를 못 가린다 —
「연 최고 3.5%」라고만 쓰고 최저이율을 빼도 「이자율」이라는 말은 나온다. 그래서
지금까지 파이프라인의 판정 자리가 비어 있었다.

농협 Gemma 엔드포인트를 아직 못 받았으므로 **Colab 에서 Gemma 를 직접 올려** 판정을
받아 본다. 모델이 같지는 않아도 「프롬프트가 먹히는가 · 형식을 지키는가 · 판정이
사람 눈에 맞는가」는 여기서 확인된다. 엔드포인트가 열리면 `rag/llm.py` 의 주소만
바꾸면 되도록 프롬프트를 그대로 쓴다.

  python rag/_build_colab_nb8.py
"""
import os
import json

MD = "markdown"
PY = "code"

CELLS = []


def add(kind, text):
    CELLS.append((kind, text.strip("\n")))


add(MD, """
# 광고 심의 판정 — Gemma (Colab)

체크리스트를 광고에 대조해 **실제 판정**을 받는다. 지금까지는 목(mock)이라
「낱말이 있다/없다」까지만 봤고 판정 자리가 비어 있었다.

| | 무엇 |
|---|---|
| **입력** | `checklist.json` (339문항) · `ads.jsonl` (광고 18건) |
| **모델** | `google/gemma-2-9b-it` — T4 에 4비트로 올린다 |
| **출력** | `gemma_audit.json` · `gemma_audit_report.md` |

**농협 Gemma 와 같은 모델은 아니다.** 여기서 확인하는 것은 성능 수치가 아니라
**프롬프트가 먹히는가 · JSON 형식을 지키는가 · 판정이 사람 눈에 맞는가** 셋이다.
엔드포인트가 열리면 `rag/llm.py` 의 주소만 바꾸고 프롬프트는 그대로 쓴다.

**런타임:** `런타임 → 런타임 유형 변경 → T4 GPU`
**허깅페이스 토큰이 필요하다** — Gemma 는 라이선스 동의가 걸린 모델이다.
""")

add(MD, """
## 1. 환경과 토큰

Gemma 는 [huggingface.co/google/gemma-2-9b-it](https://huggingface.co/google/gemma-2-9b-it)
에서 **라이선스에 동의해야** 내려받을 수 있다. 동의한 계정의 토큰을 Colab 비밀
(`🔑` 아이콘 → `HF_TOKEN`)에 넣어 두면 아래 셀이 알아서 읽는다.
""")
add(PY, """
!nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
!pip -q install -U "transformers>=4.44" accelerate bitsandbytes 2>&1 | tail -1

import os
try:
    from google.colab import userdata
    os.environ["HF_TOKEN"] = userdata.get("HF_TOKEN")
    print("HF_TOKEN 읽음")
except Exception as e:
    print("HF_TOKEN 을 Colab 비밀에 넣어 주세요 —", e)
""")

add(MD, "## 2. 파일 업로드 — `checklist.json` · `ads.jsonl` (`output/_rag/`)")
add(PY, """
from google.colab import files
import os
up = files.upload()
for n in up:
    print(f"{n:20s} {len(up[n])/1e3:7.1f}KB")
assert all(os.path.exists(n) for n in ("checklist.json", "ads.jsonl"))
""")

add(MD, """
## 3. 점검 목록 만들기

`rag/checklist.py` 의 `for_ad()` 와 **같은 규칙**이다. 로컬과 다르게 고르면 여기서
좋은 결과가 나와도 옮길 수 없다.

- 해당 상품 + 「전체」
- 같은 질문은 하나로 묶고 근거는 합친다
- 조건부 문항은 표시해 둔다 (조건이 **대분류에만** 있는 것도 있다)
- 「전체」로 분류됐지만 투자성 전용인 문항은 뺀다 (근거 법령·질문 낱말로 가름)
""")
add(PY, r"""
import json, re

items = json.load(open("checklist.json", encoding="utf-8"))
ads = [json.loads(l) for l in open("ads.jsonl", encoding="utf-8")]
print(f"체크리스트 {len(items)}문항 · 광고 {len(ads)}건")

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
    if x["상품"] != "전체" or x["방향"] != "REQUIRE":
        return False
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
        y = dict(x, 조건부=is_conditional(x))
        seen[key] = y; merged.append(y)
    return merged

for p in ("예금성", "대출성", "투자성"):
    s = for_ad(p)
    print(f"  {p} {len(s):>4}문항 "
          f"(필수 {sum(1 for x in s if x['방향']=='REQUIRE')} · "
          f"금지 {sum(1 for x in s if x['방향']=='PROHIBIT')})")
""")

add(MD, """
## 4. Gemma 올리기

**GPU 를 보고 알아서 고른다.** 양자화는 메모리가 모자랄 때 어쩔 수 없이 하는 것이지
좋아서 하는 게 아니다 — 품질이 깎이고 오히려 느려질 수도 있다(역양자화 비용).

| GPU | 고르는 것 | 왜 |
|---|---|---|
| A100 40GB | **27B 4비트** (~16GB) | 실서비스에 쓸 만한 크기. 판정 품질이 9B 와 확연히 다르다 |
| L4 24GB | 9B fp16 (~18GB) | 양자화 없이 온전한 품질 |
| T4 15GB | 9B 4비트 (~6GB) | 들어가는 것이 이것뿐 |

`MODEL` 을 직접 적으면 그대로 쓴다.
""")
add(PY, """
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

MODEL = None        # 직접 고르려면 "google/gemma-2-27b-it" 처럼 적는다
FOURBIT = None      # 직접 고르려면 True/False

free = torch.cuda.get_device_properties(0).total_memory / 1e9 if torch.cuda.is_available() else 0
name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
if MODEL is None:
    if free >= 38:      MODEL, FOURBIT = "google/gemma-2-27b-it", True
    elif free >= 22:    MODEL, FOURBIT = "google/gemma-2-9b-it", False
    else:               MODEL, FOURBIT = "google/gemma-2-9b-it", True
print(f"{name} {free:.0f}GB → {MODEL} ({'4bit' if FOURBIT else 'fp16'})")

kw = dict(device_map="auto")
if FOURBIT:
    kw["quantization_config"] = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True)
else:
    kw["torch_dtype"] = torch.bfloat16

tok = AutoTokenizer.from_pretrained(MODEL)
model = AutoModelForCausalLM.from_pretrained(MODEL, **kw)
model.eval()
print(f"{MODEL} 올림 · {model.get_memory_footprint()/1e9:.1f}GB")

def ask(prompt, max_new=1536):
    msgs = [{"role": "user", "content": prompt}]
    ids = tok.apply_chat_template(msgs, add_generation_prompt=True,
                                  return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(ids, max_new_tokens=max_new, do_sample=False,
                             pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids.shape[-1]:], skip_special_tokens=True)

print(ask("한 문장으로 자기소개해 주세요.")[:200])
""")

add(MD, """
## 5. 판정

프롬프트는 `rag/audit.py` 의 `_PROMPT` 를 그대로 옮긴 것이다. 여기서 손보면 로컬과
갈라져서, 엔드포인트가 열렸을 때 어느 쪽이 검증된 것인지 알 수 없게 된다.

한 번에 **12문항씩** 묶어 던진다. 문항마다 부르면 광고 하나에 87번을 불러야 한다.
""")
add(PY, r"""
import json, re, time

BATCH = 12
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
        return [{"id": x["id"], "판정": None, "사유": "JSON 배열을 못 찾음",
                 "근거문구": ""} for x in chunk]
    try:
        got = json.loads(m.group(0))
    except json.JSONDecodeError:
        return [{"id": x["id"], "판정": None, "사유": "JSON 파싱 실패",
                 "근거문구": ""} for x in chunk]
    by = {str(g.get("id")): g for g in got if isinstance(g, dict)}
    return [{"id": x["id"],
             "판정": (by.get(x["id"]) or {}).get("판정"),
             "사유": (by.get(x["id"]) or {}).get("사유", "LLM 이 빠뜨림"),
             "근거문구": (by.get(x["id"]) or {}).get("근거문구", "")}
            for x in chunk]

def audit(ad):
    sel = for_ad(ad.get("상품군"))
    verdicts = []
    t0 = time.time()
    for s in range(0, len(sel), BATCH):
        chunk = sel[s:s+BATCH]
        body = "\n".join(
            f'{x["id"]} [{"있어야 함" if x["방향"]=="REQUIRE" else "없어야 함"}] {x["질문"]}'
            for x in chunk)
        verdicts += parse(ask(PROMPT.format(items=body, ad=ad["text"][:6000])), chunk)
        print(f"    {min(s+BATCH, len(sel)):>3}/{len(sel)}  {time.time()-t0:5.0f}초")
    return sel, verdicts
""")

add(MD, """
## 6. 돌리기

**먼저 한 건만** 돌려 형식이 맞는지 눈으로 본다. 18건을 다 돌리고 나서 형식이
틀린 걸 발견하면 GPU 시간을 통째로 버린다.
""")
add(PY, """
import collections

ad = next(a for a in ads if a["광고id"] == "2026_005_예금성")
sel, verdicts = audit(ad)
by = {x["id"]: x for x in sel}
print(f"\\n{ad['광고id']} · {collections.Counter(str(v['판정']) for v in verdicts).most_common()}")
for v in verdicts:
    if v["판정"] == "NG":
        print(f"  NG  {by[v['id']]['질문'][:56]}")
        print(f"      사유 {str(v['사유'])[:70]}")
""")

add(MD, """
## 7. 전체 18건

한 건에 87~248문항이라 8~20분씩 걸린다. **투자성 광고는 없으므로** 예금성 7 +
대출성 11 = 18건, 대략 2시간 안팎이다. 오래 걸리면 `ads[:6]` 으로 줄여도 된다.
""")
add(PY, """
import json, collections

results = []
for i, ad in enumerate(ads, 1):
    print(f"\\n[{i}/{len(ads)}] {ad['광고id']} ({ad.get('상품군')})")
    sel, verdicts = audit(ad)
    by = {x["id"]: x for x in sel}
    ng = [v for v in verdicts if v["판정"] == "NG"]
    results.append({
        "광고id": ad["광고id"], "판본": ad.get("판본"), "상품군": ad.get("상품군"),
        "문항수": len(sel),
        "요약": collections.Counter(str(v["판정"]) for v in verdicts).most_common(),
        "지적": [{"id": v["id"], "방향": by[v["id"]]["방향"],
                 "질문": by[v["id"]]["질문"],
                 "근거": by[v["id"]]["근거"] or "(근거 없음)",
                 "조건부": by[v["id"]]["조건부"],
                 "사유": v["사유"], "근거문구": v["근거문구"]} for v in ng],
        "전체": verdicts,
    })
    print(f"  → {results[-1]['요약']}  지적 {len(ng)}건")

json.dump(results, open("gemma_audit.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\\n저장: gemma_audit.json")
""")

add(MD, "## 8. 보고서")
add(PY, """
import json, collections

lines = ["# Gemma 광고 심의 판정", "",
         f"광고 {len(results)}건 · 모델 {MODEL} (4bit)", "",
         "| 광고 | 상품군 | 문항 | OK | NG | N/A | 못읽음 |",
         "|---|---|---:|---:|---:|---:|---:|"]
for r in results:
    d = dict(r["요약"])
    lines.append(f"| {r['광고id']} | {r['상품군']} | {r['문항수']} | "
                 f"{d.get('OK',0)} | {d.get('NG',0)} | {d.get('N/A',0)} | "
                 f"{d.get('None',0)} |")

lines += ["", "## 지적 사항", ""]
for r in results:
    if not r["지적"]:
        continue
    lines += [f"### {r['광고id']} ({r['상품군']})", ""]
    for g in r["지적"]:
        cond = " · 조건부" if g["조건부"] else ""
        lines += [f"- **[{g['방향']}{cond}] {g['질문']}**",
                  f"  - 근거: {g['근거']}",
                  f"  - 사유: {g['사유']}"]
        if g["근거문구"]:
            lines.append(f"  - 광고문: 「{g['근거문구']}」")
    lines.append("")

# 못 읽은 응답이 많으면 프롬프트나 max_new_tokens 를 손봐야 한다는 신호다
bad = sum(dict(r["요약"]).get("None", 0) for r in results)
tot = sum(r["문항수"] for r in results)
lines += ["## 형식 준수", "",
          f"응답을 못 읽은 문항 {bad}/{tot} ({bad/max(tot,1)*100:.1f}%)", "",
          "이 값이 크면 판정 품질 이전에 **형식**이 문제다 — 배치 크기를 줄이거나",
          "max_new_tokens 를 늘려야 한다."]

open("gemma_audit_report.md", "w", encoding="utf-8").write("\\n".join(lines))
print("\\n".join(lines[:40]))

from google.colab import files
files.download("gemma_audit_report.md")
files.download("gemma_audit.json")
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
                       "gemma_audit_colab.ipynb")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(nb, f, ensure_ascii=False, indent=1)
    print(f"셀 {len(CELLS)}개 → {out}")


if __name__ == "__main__":
    main()
