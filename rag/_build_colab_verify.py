# -*- coding: utf-8 -*-
"""rag/verdict_verify_colab.ipynb — 판정이 맞는지 처음으로 재는 노트북.

지금까지는 판정이 **나오는지**만 봤다. 맞는지는 못 봤다. 심의사례 20건이 있지만
그것은 **고치기 전** 광고 기준이고 우리 광고 파일은 **이미 고쳐진 판본**이라 대조가
성립하지 않았다.

대신 광고 원문에서 **문구 유무를 직접 확인**해 정답표를 만들었다.

    「수신거부(무료) : 0808552100」 문구
      있음  2026_004·006·007·008·009 예금성  →  해당 문항이 OK 여야 한다
      없음  2026_003·005                     →  해당 문항이 NG 여야 한다

같은 문항을 두고 **문구가 있는 광고와 없는 광고의 판정이 갈리는지**를 본다.
한쪽만 보면 「전부 OK 라고 찍는 모델」도 만점이 나오지만, 양쪽을 보면 걸린다.

  python rag/_build_colab_verify.py
"""
import os
import json

MD = "markdown"
PY = "code"

CELLS = []


def add(kind, text):
    CELLS.append((kind, text.strip("\n")))


add(MD, """
# 판정이 맞는지 재기 — 문구 있는 광고 vs 없는 광고

## 무엇을 재나

같은 점검 문항을 두고, **그 문구가 실제로 있는 광고**와 **없는 광고**를 각각
판정시킨다. 제대로 읽고 있다면 판정이 갈려야 한다.

| 점검 문항 | 문구 있는 광고 (OK 기대) | 문구 없는 광고 (NG 기대) |
|---|---|---|
| 수신거부 무료수단 표시 | 004·006·007·008·009 | 003·005 |
| 설명받을 권리 안내 | 004·005·006·007·008·009 | 003 |
| 이자 지급제한 사유 표시 | 004·005·006·008·009 | 003·007 |

광고 7건 × 문항 3개 = **대조점 21개** (OK 기대 16 · NG 기대 5)

**한쪽만 보면 속는다.** 「전부 OK」라고만 답하는 모델도 「문구 있는 광고」에서는
만점이 나온다. 양쪽을 같이 봐야 진짜로 읽는지 알 수 있다.

정답표는 지어낸 것이 아니라 **광고 원문에서 문구를 글자로 찾아** 만들었다.

## 준비

| | |
|---|---|
| **런타임** | A100 권장 (T4 도 되지만 3배 느림) |
| **입력 3개** | `checklist.json` · `ads.jsonl` · `rule_index.jsonl` |
| **출력** | `verify_report.md` · `verify_result.json` |
| **소요** | 예금성 7건 × 약 12분 = **1시간 30분** |

토큰 필요 없음 (Gemma 4 는 Apache 2.0).
""")

add(MD, "## 1. 환경")
add(PY, """
!nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
!pip -q install -U transformers accelerate bitsandbytes 2>&1 | tail -1
""")

add(MD, "## 2. 파일 업로드 — `checklist.json` · `ads.jsonl` · `rule_index.jsonl`")
add(PY, """
from google.colab import files
import os
up = files.upload()
for n in up:
    print(f"{n:22s} {len(up[n])/1e6:6.1f}MB")
need = ["checklist.json", "ads.jsonl", "rule_index.jsonl"]
missing = [n for n in need if not os.path.exists(n)]
assert not missing, f"빠진 파일: {missing}"
""")

add(MD, """
## 3. 정답표 만들기

**광고 원문에 그 문구가 글자로 있는지** 로 정답을 정한다. 띄어쓰기만 무시하고
그대로 찾는다 — 판단이 들어가면 그건 또 하나의 추측이 된다.
""")
add(PY, r"""
import json, re

items = json.load(open("checklist.json", encoding="utf-8"))
ads = {a["광고id"]: a for a in (json.loads(l) for l in open("ads.jsonl", encoding="utf-8"))
       if a.get("판본") != "수정본"}
print(f"체크리스트 {len(items)}문항 · 광고 {len(ads)}건")

# (점검 문항 ID, 광고에서 찾을 문구, 사람이 읽을 이름)
# 문항 ID 는 checklist.json 에서 확인한 것이고, 문구는 심의사례의 「수정후 권고안」에서
# 가져왔다. 즉 **심의팀이 넣으라고 한 바로 그 문구**다.
PROBES = [
    ("CL-034", "수신거부(무료) : 0808552100", "수신거부 무료수단 표시"),
    ("CL-012", "금융소비자보호법에 따른 설명을 받을", "설명받을 권리 안내"),
    # 「계좌에 압류·가압류·질권설정이 있으면 지급이 제한될 수 있음」은 곧
    # 「이자·수익의 지급제한 사유」다 — 문구와 문항이 정확히 맞는다.
    ("CL-008", "계좌에 압류, 가압류, 질권설정", "이자 지급제한 사유 표시"),
]

def has(text, kw):
    return re.sub(r"\s", "", kw) in re.sub(r"\s", "", text)

TARGET = [a for a in ads if a.endswith("예금성")]
GOLD = {}          # (광고id, 문항id) → 기대 판정
for cid, kw, label in PROBES:
    yes = [a for a in TARGET if has(ads[a]["text"], kw)]
    no = [a for a in TARGET if a not in yes]
    for a in yes: GOLD[(a, cid)] = "OK"
    for a in no:  GOLD[(a, cid)] = "NG"
    print(f"\n{label}  ({cid})")
    print(f"  있음(OK 기대) {yes}")
    print(f"  없음(NG 기대) {no}")

print(f"\n검증할 광고 {len(TARGET)}건 · 대조점 {len(GOLD)}개")
""")

add(MD, """
## 4. Gemma 올리기
""")
add(PY, """
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

MODEL = None; FOURBIT = None      # 직접 고르려면 여기에 적는다
free = torch.cuda.get_device_properties(0).total_memory/1e9 if torch.cuda.is_available() else 0
gname = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
if MODEL is None:
    # 12B 를 먼저 본다 — 31B 4bit 는 한 건에 20~30분이라 7건이면 하루가 간다.
    # 12B bf16 은 역양자화가 없어 5~10배 빠르고, 형식 준수도 실측에서 문제없었다.
    if free >= 26:   MODEL, FOURBIT = "google/gemma-4-12B-it", False
    elif free >= 14: MODEL, FOURBIT = "google/gemma-4-12B-it", True
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
    # return_dict=True 를 명시한다 — 최신 transformers 는 텐서가 아니라
    # BatchEncoding 을 주는데, 텐서인 줄 알고 .shape 를 부르면 죽는다.
    enc = tok.apply_chat_template([{"role": "user", "content": prompt}],
                                  add_generation_prompt=True, return_dict=True,
                                  return_tensors="pt").to(gemma.device)
    with torch.no_grad():
        out = gemma.generate(**enc, max_new_tokens=max_new, do_sample=False,
                             pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][enc["input_ids"].shape[-1]:], skip_special_tokens=True)

print(ask("한 문장으로 자기소개해 주세요.")[:120])
""")

add(MD, """
## 5. 점검 목록 · 판정

`rag/checklist.py`·`rag/audit.py` 와 같은 규칙이다. 로컬과 다르게 하면 여기서
좋은 결과가 나와도 옮길 수 없다.

**배치가 통째로 깨지면 반으로 쪼개 재시도한다** — 전날 실행에서 24문항이 한꺼번에
유실됐다. 출력이 절반이면 JSON 이 깨질 확률도 내려간다.
""")
add(PY, r"""
import json, re, time, collections

BATCH = 24
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
            m["_묶임"].append(x["id"])
            continue
        y = dict(x, _묶임=[x["id"]], 조건부=is_conditional(x))
        seen[key] = y; merged.append(y)
    return merged

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

def _ask_batch(chunk, ad_text):
    body = "\n".join(
        f'{x["id"]} [{"있어야 함" if x["방향"]=="REQUIRE" else "없어야 함"}] {x["질문"]}'
        for x in chunk)
    got = parse(ask(PROMPT.format(items=body, ad=ad_text)), chunk)
    if all(g["판정"] is None for g in got) and len(chunk) > 6:
        mid = len(chunk) // 2
        return _ask_batch(chunk[:mid], ad_text) + _ask_batch(chunk[mid:], ad_text)
    return got

def audit(ad):
    sel = for_ad(ad.get("상품군"))
    v, t0 = [], time.time()
    for s in range(0, len(sel), BATCH):
        v += _ask_batch(sel[s:s+BATCH], ad["text"][:6000])
        print(f"    {min(s+BATCH, len(sel))}/{len(sel)}문항  {time.time()-t0:5.0f}초")
    return sel, v

print("준비 완료")
""")

add(MD, """
## 6. 한 건만 먼저

7건을 다 돌리고 나서 형식이 깨진 걸 발견하면 GPU 시간을 통째로 버린다.
**「못읽음」이 0 인지** 먼저 확인한다.
""")
add(PY, """
import collections

aid = TARGET[0]
sel, v = audit(ads[aid])
print(f"\\n{aid} · {collections.Counter(str(x['판정']) for x in v).most_common()}")
bad = sum(1 for x in v if x["판정"] is None)
print("못읽음 0 — 진행해도 좋음" if bad == 0 else f"★ 못읽음 {bad}건 — 배치를 줄여야 함")
""")

add(MD, """
## 7. 예금성 7건 전부

한 건에 12분 안팎. 광고마다 저장하므로 중간에 끊겨도 완료분은 남는다.
""")
add(PY, """
import json, time, collections

try:
    RESULTS
except NameError:
    RESULTS = {}

t0 = time.time()
for i, aid in enumerate(TARGET, 1):
    if aid in RESULTS:
        continue
    print(f"\\n[{i}/{len(TARGET)}] {aid}")
    sel, v = audit(ads[aid])
    RESULTS[aid] = {"문항": {x["id"]: x for x in sel}, "판정": v}
    json.dump({k: {"판정": x["판정"]} for k, x in RESULTS.items()},
              open("verify_result.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"  → {collections.Counter(str(x['판정']) for x in v).most_common()}"
          f"  누적 {time.time()-t0:.0f}초")

print(f"\\n완료 {len(RESULTS)}/{len(TARGET)}건")
""")

add(MD, """
## 8. 채점 — 문구 있는 광고와 없는 광고가 갈리는가

**두 방향을 따로 센다.**

- 문구가 **있는데** NG 라고 하면 → 과잉 지적 (있는 걸 못 봄)
- 문구가 **없는데** OK 라고 하면 → 놓침 (없는 걸 있다고 함)

놓침이 더 위험하다 — 심의에서 안 걸러진 광고가 나가는 것이다.
""")
add(PY, """
import collections

rows, wrong = [], []
for (aid, cid), want in sorted(GOLD.items()):
    r = RESULTS.get(aid)
    if not r:
        continue
    got = next((x["판정"] for x in r["판정"] if x["id"] == cid), None)
    ok = (got == want)
    rows.append((aid, cid, want, got, ok))
    if not ok:
        v = next((x for x in r["판정"] if x["id"] == cid), {})
        wrong.append((aid, cid, want, got, str(v.get("사유", ""))[:70]))

n = len(rows)
right = sum(1 for *_, ok in rows if ok)
print(f"대조점 {n}개 중 맞음 {right} ({right/max(n,1)*100:.0f}%)\\n")

for label, want in (("문구 있음 → OK 여야 함", "OK"), ("문구 없음 → NG 여야 함", "NG")):
    sub = [r for r in rows if r[2] == want]
    hit = sum(1 for *_, ok in sub if ok)
    print(f"  {label:24s} {hit}/{len(sub)}")

if wrong:
    print("\\n틀린 것:")
    for aid, cid, want, got, why in wrong:
        print(f"  {aid} {cid}  기대 {want} → 실제 {got}")
        print(f"      사유: {why}")
""")

add(MD, "## 9. 보고서")
add(PY, """
import json, collections

lines = ["# 판정 검증 — 문구 유무와 판정이 갈리는가", "",
         f"모델 {MODEL} ({'4bit' if FOURBIT else 'bf16'}) · 광고 {len(RESULTS)}건 · "
         f"대조점 {n}개", "",
         f"**맞음 {right}/{n} ({right/max(n,1)*100:.0f}%)**", "",
         "| 방향 | 맞음 | 전체 |", "|---|---:|---:|"]
for label, want in (("문구 있음 → OK", "OK"), ("문구 없음 → NG", "NG")):
    sub = [r for r in rows if r[2] == want]
    lines.append(f"| {label} | {sum(1 for *_, ok in sub if ok)} | {len(sub)} |")

lines += ["", "## 대조점 전체", "",
          "| 광고 | 문항 | 기대 | 실제 | |", "|---|---|---|---|---|"]
for aid, cid, want, got, ok in rows:
    lines.append(f"| {aid} | {cid} | {want} | {got} | {'○' if ok else '✕'} |")

if wrong:
    lines += ["", "## 틀린 것", ""]
    for aid, cid, want, got, why in wrong:
        lines += [f"- **{aid} · {cid}** — 기대 {want}, 실제 {got}", f"  - 사유: {why}"]

lines += ["", "## 광고별 판정 분포", "",
          "| 광고 | 문항수 | OK | NG | N/A | 못읽음 |", "|---|---:|---:|---:|---:|---:|"]
for aid, r in RESULTS.items():
    c = collections.Counter(str(x["판정"]) for x in r["판정"])
    lines.append(f"| {aid} | {len(r['판정'])} | {c.get('OK',0)} | {c.get('NG',0)} | "
                 f"{c.get('N/A',0)} | {c.get('None',0)} |")

lines += ["", "## 이 숫자를 읽는 법", "",
          "정답표는 광고 원문에서 **문구를 글자로 찾아** 만든 것이라 판단이 안 들어갔다.",
          "「문구 없음 → NG」쪽이 낮으면 **없는 것을 있다고 하는 것**이라 더 위험하다 —",
          "심의에서 안 걸러진 광고가 그대로 나간다."]

open("verify_report.md", "w", encoding="utf-8").write("\\n".join(lines))
print("\\n".join(lines[:36]))

from google.colab import files
files.download("verify_report.md")

full = {aid: {"판정": r["판정"],
              "문항": {k: {"질문": v["질문"], "근거": v["근거"]} for k, v in r["문항"].items()}}
        for aid, r in RESULTS.items()}
json.dump(full, open("verify_result.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
files.download("verify_result.json")
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
                       "verdict_verify_colab.ipynb")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(nb, f, ensure_ascii=False, indent=1)
    print(f"셀 {len(CELLS)}개 → {out}")


if __name__ == "__main__":
    main()
