# -*- coding: utf-8 -*-
"""① 누락·금지 점검 — 체크리스트를 광고 전문에 대조한다. 검색을 쓰지 않는다.

**검색은 있는 것만 찾는다.** 광고에 「예금자보호」가 없으면 거기서 나올 질의도 없어서
누락은 영영 안 잡힌다. 그래서 이 단계는 광고에서 질의를 만들지 않고, **해당 상품의
점검 문항을 통째로 광고에 던진다.** 문항 목록이 고정이므로 빠짐이 없다.

문항이 134개(예금성)라 하나씩 부르면 비싸다. **묶어서 던진다** — 한 번에 12개씩,
LLM 은 문항 번호마다 O/X/해당없음만 답한다.

  python rag/audit.py --ad 2026_005_예금성
  python rag/audit.py --all --out output/_rag/audit.json
"""
import os
import re
import sys
import json
import argparse
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import llm
import checklist as CL

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG = os.path.join(ROOT, "output", "_rag")
ADS = os.path.join(RAG, "ads.jsonl")

BATCH = 12          # 한 번에 던질 문항 수


_PROMPT = """당신은 금융광고 심의 담당자입니다. 아래 광고문을 읽고, 점검 문항마다
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
{ad}"""


# 질문 어투에만 쓰이는 말. 단서에서 뺀다 — 광고문에도 흔해서 남겨 두면 무엇이든
# 「낱말이 있다」가 되어 버린다.
# 조사·어미를 떼고 낱말만 남긴다. **이걸 안 하면 전부 「없음」이 된다** — 질문의
# 「은행의」와 광고의 「NH농협은행」은 글자로는 안 맞는다(실측: 대출성 광고 11건
# 전부에서 「광고 주체인 은행의 명칭」이 누락으로 잘못 잡혔다).
_JOSA = re.compile(
    r"(?:으로서|에서의|에게서|으로|에서|에게|이나|하는|한|인|을|를|이|가|은|는|의|"
    r"에|와|과|로|도|만|및|께|랑|나|든|나마)$")
_TAIL = re.compile(r"(?:하였는가|않았는가|있는가|없는가|하는가|인가|하여|하고|한다)$")


def _terms(text):
    out = []
    for w in re.findall(r"[가-힣A-Za-z0-9]{2,}", str(text or "")):
        w = _TAIL.sub("", w)
        w = _JOSA.sub("", w)
        if len(w) >= 2:
            out.append(w)
    return out


_STOP = {"표시", "기재", "하였는가", "않았는가", "경우", "관련", "사항", "내용",
         "포함", "해당", "여부", "있는", "하는", "대한", "따른", "등의", "및",
         "또는", "이상", "이하", "그리고", "위한", "되는", "한다", "하지", "아니",
         "다음", "각의", "모두", "일부", "함께", "명확", "구체", "객관"}


def _mock(items, ad_text):
    """Gemma 가 없을 때. **판정을 지어내지 않고, 기계로 확인되는 것만 말한다.**

    한쪽 방향만 확인할 수 있다.

      핵심 낱말이 **하나도** 없다  →  누락 의심. 사실 진술이므로 말해도 된다
      낱말이 있다                 →  제대로 표시했는지는 문맥 판단. LLM 몫

    반대로 「낱말이 있으니 OK」라고 하면 그건 판정을 지어내는 것이다 — 「연 최고
    3.5%」라고만 쓰고 최저이율을 안 적어도 「이자율」이라는 말은 나온다.

    **어휘가 달라 생기는 거짓 의심이 있다.** 질문은 법령체(「이자율의 범위 및
    산출기준」)고 광고는 마케팅 문구(「연 최고 3.5%」)라 겹치는 낱말이 없을 수 있다.
    그래서 「의심」이지 지적이 아니다.
    """
    out = []
    for x in items:
        words = [w for w in _terms(x["질문"]) if w not in _STOP]
        hit = [w for w in words if w in ad_text]
        if x["방향"] == "REQUIRE" and words and not hit:
            # **조건부 문항은 지적으로 올리지 않는다.** 「(통계수치·도표 인용 시)
            # 출처를 표시하였는가」는 인용을 안 했으면 해당 없음이지 위반이 아니다.
            # 낱말이 없다는 사실만으로는 둘을 못 가른다.
            cond = x.get("조건부")
            out.append({
                "id": x["id"], "판정": "N/A?" if cond else "NG",
                "사유": ("[목] 조건부 문항이고 핵심 낱말도 없음 — 조건 자체가 성립하지"
                         " 않는 것으로 보이나 확인 필요"
                         if cond else
                         f"[목·누락의심] 핵심 낱말이 광고문에 하나도 없음 "
                         f"({', '.join(words[:4])}). 어휘가 달라서일 수 있어 확인 필요"),
                "근거문구": ""})
        else:
            out.append({
                "id": x["id"], "판정": None,
                "사유": (f"[목] 낱말 {len(hit)}/{len(words)}개 나옴"
                         f"{': ' + ', '.join(hit[:4]) if hit else ''} — "
                         f"제대로 표시했는지는 Gemma 가 있어야 판정 가능"),
                "근거문구": ""})
    return out


def _parse(text, items):
    """LLM 응답 → 판정 목록. 못 읽으면 **판정을 비워 둔다.**

    파싱 실패를 「확인필요」로 뭉개면 모델이 형식을 못 지킨 것과 진짜 애매한 광고가
    구분되지 않는다.
    """
    m = re.search(r"\[.*\]", text or "", re.S)
    if not m:
        return [{"id": x["id"], "판정": None,
                 "사유": "LLM 응답에서 JSON 배열을 못 찾았습니다.",
                 "근거문구": ""} for x in items]
    try:
        got = json.loads(m.group(0))
    except json.JSONDecodeError:
        return [{"id": x["id"], "판정": None,
                 "사유": "LLM 응답을 JSON 으로 못 읽었습니다.",
                 "근거문구": ""} for x in items]
    by = {str(g.get("id")): g for g in got if isinstance(g, dict)}
    out = []
    for x in items:
        g = by.get(x["id"])
        out.append({"id": x["id"],
                    "판정": (g or {}).get("판정"),
                    "사유": (g or {}).get("사유", "LLM 이 이 문항을 빠뜨렸습니다."),
                    "근거문구": (g or {}).get("근거문구", "")})
    return out


def audit(ad_text, items, batch=BATCH):
    """체크리스트 전량 점검. (판정 목록, 출처)"""
    verdicts, src = [], "llm"
    for s in range(0, len(items), batch):
        chunk = items[s:s + batch]
        body = "\n".join(
            f'{x["id"]} [{"있어야 함" if x["방향"]=="REQUIRE" else "없어야 함"}] '
            f'{x["질문"]}' for x in chunk)
        got = llm.chat([{"role": "user",
                         "content": _PROMPT.format(items=body, ad=ad_text[:6000])}],
                       max_tokens=2048)
        if got is None:
            verdicts += _mock(chunk, ad_text)
            src = "mock"
        else:
            verdicts += _parse(got, chunk)
    return verdicts, src


def review(ad, items):
    sel = CL.for_ad(items, ad.get("상품군"))
    verdicts, src = audit(ad["text"], sel)
    by = {x["id"]: x for x in sel}
    ng = [v for v in verdicts if v["판정"] == "NG"]
    return {
        "광고id": ad["광고id"], "상품군": ad.get("상품군"),
        "_판정출처": src, "문항수": len(sel),
        "요약": collections.Counter(str(v["판정"]) for v in verdicts).most_common(),
        "지적": [{
            "id": v["id"],
            "방향": by[v["id"]]["방향"],
            "질문": by[v["id"]]["질문"],
            "근거": by[v["id"]]["근거"] or "(근거 없음 — 사람 확인 필요)",
            "사유": v["사유"], "근거문구": v["근거문구"],
        } for v in ng],
        "전체": verdicts,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ad")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()

    items = CL.load()
    ads = [json.loads(l) for l in open(ADS, encoding="utf-8")]
    if a.ad:
        ads = [x for x in ads if x["광고id"] == a.ad]
        if not ads:
            ap.error(f"광고를 못 찾음: {a.ad}")
    elif not a.all:
        ads = ads[:1]

    print(f"체크리스트 {len(items)}문항 · "
          f"Gemma {'연결됨' if llm.available() else '없음(목)'}\n")
    out = []
    for ad in ads:
        r = review(ad, items)
        out.append(r)
        print("=" * 78)
        print(f"{r['광고id']}  ({r['상품군']})  문항 {r['문항수']}개 "
              f"[{r['_판정출처']}]  {r['요약']}")
        for g in r["지적"][:8]:
            print(f"   NG [{g['방향']}] {g['질문'][:58]}")
            print(f"        근거 {g['근거'][:58]}")

    if a.out:
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        json.dump(out, open(a.out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"\n저장: {a.out} ({len(out)}건)")


if __name__ == "__main__":
    main()
