# -*- coding: utf-8 -*-
"""광고 하나 → 심의 지적 목록. **판정 규칙은 코드가 아니라 데이터에서 읽는다.**

    광고        NH농협은행-2026_019-예금성
    지적유형     missing_deposit_protection
    근거규정     은행 광고심의 기준 §16① 5 라
    사유        예금성 상품인데 예금자보호 관련 표시가 없음
    위치        p001_s004  bbox [80,1360,1042,1820]
    개선안       예금자보호법에 따른 부보 내용과 보호 한도를 표시하세요.

**누락을 어떻게 잡는가** — 여기가 이 파일의 핵심이다.

광고문에서 출발해 검색하면 누락은 원리적으로 못 잡는다. 광고에 예금자보호
문구가 없으면 광고에서 뽑은 어떤 질의도 그 조문을 안 가져온다.

그래서 방향이 둘이다.

    목록 → 광고   "예금성이면 예금자보호를 표시해야 한다"
                  광고를 보기 전에 요구가 정해진다 → **없는 것이 드러난다**
                  요구 목록은 검색이 아니라 조회로 나온다
                      SELECT * FROM compliance
                       WHERE (product_group IS NULL OR product_group = :상품군)
                         AND is_active AND effective_date <= now()

    광고 → 목록   "업계 최고 연 3.75%"
                  목록에 있어도 광고를 읽어야 발견된다 → **쓰면 안 될 것을 썼다**
                  여기가 검색(RAG)이 필요한 자리다

**판정 규칙을 코드에 두지 않는다.** `output/_rag/checks.json` 에서 읽는다. 규칙이
402건인데 코드에 7개를 박아 두면 늘릴 때마다 배포해야 하고 담당자가 못 고친다.
그 파일의 자리는 `compliance` 테이블이다(파일 안 _대상테이블 참고).

  python rag/detect.py                          # 목데이터 19건 판정 + 라벨 채점
  python rag/detect.py --ad NH농협은행-2026_017-예금성
  python rag/detect.py --real                   # 실물 광고 18건
"""
import os
import re
import sys
import json
import argparse
import datetime
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ad_input as AI

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG = os.path.join(ROOT, "output", "_rag")

# **상품군별 규칙 파일을 쓴다.** 전에는 `checks.json`(7건)을 읽었는데, 그건
# 목데이터 라벨 7종에 맞춰 만든 것이라 **실물 심의사례 지적 15건을 하나도 못
# 잡았다**(build_checks.py 참고). 실물용은 상품군별로 나뉘어 있다.
CHECKS_BY_PRODUCT = {"예금": os.path.join(RAG, "checks_예금.json"),
                     "대출": os.path.join(RAG, "checks_대출.json")}
CHECKS_MOCK = os.path.join(RAG, "checks.json")   # 목데이터 채점 재현용

# 목데이터 라벨이 만들어진 날. 라벨은 그날 기준으로 만료 여부를 정했으므로
# **목데이터를 채점할 때만** 이 날짜를 쓴다. 실제 판정은 오늘 날짜다 —
# 기준일을 박아 두면 만료된 심의필을 통과시킨다.
REFERENCE_DATE = datetime.date(2026, 7, 9)


def today():
    return datetime.date.today()


def load_checks(path=None, product=None):
    """판정 규칙을 읽는다. product 를 주면 그 상품군 것만, 없으면 전부."""
    if path:
        return json.load(open(path, encoding="utf-8"))["checks"]
    paths = ([CHECKS_BY_PRODUCT[product]] if product in CHECKS_BY_PRODUCT
             else list(CHECKS_BY_PRODUCT.values()))
    out = []
    for p in paths:
        if os.path.exists(p):
            out += json.load(open(p, encoding="utf-8"))["checks"]
    if not out:
        raise FileNotFoundError(
            f"판정 규칙 파일이 없다: {paths}\n"
            f"  python rag/build_checks.py 로 만든다")
    return out


def applies(chk, ad):
    """이 광고에 이 규칙이 적용되나. **광고 내용이 아니라 속성으로 정한다** —
    내용을 보고 정하면 「내용이 없어서 적용 안 됨」이 되어 누락을 놓친다."""
    pg = chk.get("product_group")
    return pg is None or pg == ad.product


def _finding(chk, chunk, reason=None):
    return {
        "check_id": chk["id"],
        "지적유형": chk["verdict_code"],
        "근거규정": chk["article_no"],
        "사유": reason or chk["reason"],
        "위치": (chunk or {}).get("chunk_id"),
        "bbox": (chunk or {}).get("bbox"),
        "인용": ((chunk or {}).get("text") or "")[:80] or None,
        "개선안": chk["recommendation"],
        "판정근거": "RULE",
    }


def _rx(pattern):
    """규칙의 pattern → 정규식 문자열.

    `build_checks.py` 가 만든 규칙은 pattern 이 **문자열 목록**이다 —
    「이 중 하나라도 있으면 통과」라는 뜻이고, 안의 내용은 정규식이 아니라
    **그대로 찾을 문구**다(`(광고)` 의 괄호를 정규식 그룹으로 읽으면 안 된다).
    손으로 쓴 옛 규칙은 진짜 정규식 문자열이라 그건 그대로 쓴다.
    """
    if pattern is None:
        return None
    if isinstance(pattern, (list, tuple)):
        return "|".join(re.escape(str(x)) for x in pattern if str(x).strip())
    return pattern


def _locate(ad, pattern):
    pattern = _rx(pattern)
    if not pattern:
        return None
    hit = ad.find(pattern)
    return hit[0][0] if hit else None


def run_check(chk, ad, today):
    """규칙 하나 → 지적 목록. 적용 안 되면 빈 목록."""
    if not applies(chk, ad):
        return []
    p = chk.get("params") or {}
    kind = chk["kind"]
    text = ad.text

    if kind == "PRESENCE":
        pat = _rx(p.get("pattern"))
        if not pat:
            return []
        hits = ad.find(pat)
        neg = _rx(p.get("not_pattern"))
        if neg:
            rx = re.compile(neg)
            hits = [(c, m) for c, m in hits if not rx.search(c.get("text") or "")]
        # 청크가 굵으면(실물처럼 전문이 한 덩어리) 청크 수로는 몇 번 나왔는지 모른다.
        # 「※ 가 2줄 이상」 같은 조건은 전문에서 세야 한다.
        need = p.get("min_matches")
        if need and len(re.findall(pat, text)) >= need:
            hits = hits or [(ad.chunks[0], None)] if ad.chunks else hits
        if not hits:
            # 못 찾았을 때 **비슷한 자리라도 짚어 준다** — 「어디에 넣어야 하나」를
            # 사람이 찾게 두면 지적이 쓸모가 준다.
            near = _locate(ad, neg) if neg else None
            return [_finding(chk, near)]
        return []

    if kind == "FORMAT":
        if re.search(_rx(p["pattern"]), text):
            return []
        return [_finding(chk, _locate(ad, p.get("locate")))]

    if kind == "PROHIBIT":
        return [_finding(chk, c, f"{chk['reason']}: 「{m.group(0)}」")
                for c, m in ad.find(_rx(p["pattern"]))]

    if kind == "DATE":
        m = re.search(_rx(p["pattern"]), text)
        if not m:
            return []                       # 표기 자체가 없는 것은 PRESENCE 규칙 몫
        y, mo, d = (int(m.group(g)) for g in p["end_groups"])
        end = datetime.date(y, mo, d)
        if end >= today:
            return []
        return [_finding(chk, _locate(ad, p.get("locate")),
                         f"{chk['reason']} — {end} 만료 (기준일 {today})")]

    if kind == "STYLE":
        body = ad.body_size()
        if not body:
            return []                       # 크기 정보가 없으면 판정하지 않는다
        for c, s in ad.styled():
            if s and s < body * p["min_ratio"]:
                return [_finding(chk, c,
                                 f"{chk['reason']} — {s}pt (본문 {body}pt 의 "
                                 f"{s/body*100:.0f}%)")]
        return []

    if kind == "LLM":
        # 자연어 기준(criterion)이라 정규식으로 못 푼다. `judge_llm_checks` 가
        # 묶어서 한 번에 묻는다 — 여기서 한 건씩 부르면 광고 하나에 수백 번이다.
        return []

    raise ValueError(f"모르는 판정 종류: {kind}")


_LLM_BATCH = """당신은 금융광고 심의 담당자입니다. 아래 광고문을 읽고,
점검항목마다 광고가 그 기준을 지켰는지 판정하세요.

판정은 셋 중 하나입니다.
- OK: 기준을 지켰음
- NG: 기준을 어겼음(표시가 빠졌거나 잘못됨)
- 해당없음: 이 광고에 적용되지 않는 항목

규칙:
- 광고문에 실제로 있는 표현만 근거로 삼을 것. 없는 내용을 지어내지 말 것
- NG 면 무엇이 빠졌거나 잘못됐는지 한 문장으로 쓸 것
- OK 면 근거가 된 광고문 대목을 그대로 인용할 것

반드시 아래 JSON 배열로만 답하세요. 항목 수와 순서를 그대로 지키세요.
[{{"id": "...", "판정": "OK|NG|해당없음", "사유": "...", "인용": "..."}}]

점검항목:
{items}

광고문:
{ad}"""


def judge_llm_checks(ad, checks, batch=20, verbose=False):
    """`kind=LLM` 규칙들을 **묶어서** Gemma 에 묻는다.

    광고 하나에 적용되는 LLM 항목이 수백 개라 한 건씩 부르면 못 쓴다.
    묶음이 깨지면 반으로 쪼개 다시 묻는다(코랩 실행에서 87문항 중 24개가
    JSON 깨짐으로 통째 유실된 적이 있다 — 커밋 ceb6543).
    """
    import llm
    items = [c for c in checks if c["kind"] == "LLM" and applies(c, ad)]
    out = []
    for s in range(0, len(items), batch):
        out += _judge_batch(ad, items[s:s+batch], llm, verbose)
    return out


def _judge_batch(ad, items, llm, verbose=False):
    if not items:
        return []
    body = "\n".join(f'- id={c["id"]} : {c.get("criterion") or c["title"]}'
                     for c in items)
    try:
        got = llm.chat([{"role": "user",
                         "content": _LLM_BATCH.format(items=body,
                                                      ad=ad.text[:6000])}],
                       max_tokens=4096, json_mode=True)
        got = llm.extract_json(got)
        if not isinstance(got, list):
            raise ValueError("배열이 아님")
    except Exception as e:
        if len(items) == 1:
            if verbose:
                print(f"    ! {items[0]['id']} 판정 실패: {e}")
            return []
        half = len(items) // 2
        return (_judge_batch(ad, items[:half], llm, verbose)
                + _judge_batch(ad, items[half:], llm, verbose))

    by_id = {c["id"]: c for c in items}
    res = []
    for g in got:
        chk = by_id.get(str(g.get("id")))
        if not chk or str(g.get("판정")).upper() not in ("NG",):
            continue
        f = _finding(chk, None, g.get("사유") or chk["reason"])
        f["인용"] = g.get("인용") or None
        f["판정근거"] = "LLM"
        res.append(f)
    return res


def detect(ad, checks=None, on=None, use_llm=False, verbose=False):
    """광고 하나를 판정한다. `on` 은 기준일 — 안 주면 **오늘**이다.

    기본값을 고정 날짜로 두면 만료된 심의필을 통과시킨다. 목데이터 채점처럼
    그날을 재현해야 하는 경우에만 `on=REFERENCE_DATE` 를 넘긴다.

    `use_llm=True` 면 `kind=LLM` 항목도 Gemma 로 판정한다. 끄면 그 항목들은
    **안 돈다** — 몇 건이 안 돌았는지는 `pending_llm()` 으로 센다.
    """
    checks = checks if checks is not None else load_checks()
    on = on or today()
    out = []
    for chk in checks:
        out += run_check(chk, ad, on)
    if use_llm:
        out += judge_llm_checks(ad, checks, verbose=verbose)
    return out


def pending_llm(ad, checks):
    """이 광고에 적용되지만 **LLM 없이는 못 도는** 항목 수."""
    return sum(1 for c in checks if c["kind"] == "LLM" and applies(c, ad))


def load_real():
    """실물 광고(씨지인사이드 샘플). **목데이터와 번호 체계가 같으니 섞으면 안 된다.**
    파서를 안 거쳐 청크·글자크기가 없다 — STYLE 판정은 여기서 돌지 않는다."""
    out = []
    seen = set()
    for l in open(os.path.join(RAG, "ads.jsonl"), encoding="utf-8"):
        x = json.loads(l)
        if x["광고id"] in seen:
            continue
        seen.add(x["광고id"])
        out.append(AI.Ad({
            "document_id": x["광고id"],
            "advertisement_id": x["광고id"],
            "chunks": [{"chunk_id": "raw", "page": 1, "modality": "text",
                        "text": x["text"], "bbox": None, "quality": {"style": {}}}],
        }))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ad")
    ap.add_argument("--real", action="store_true")
    ap.add_argument("--path", default=AI.MOCK)
    ap.add_argument("--product", choices=sorted(CHECKS_BY_PRODUCT),
                    help="상품군 규칙만 쓴다(안 주면 전부)")
    ap.add_argument("--mock-checks", action="store_true",
                    help="목데이터용 7건짜리 checks.json 으로 채점 재현")
    ap.add_argument("--llm", action="store_true",
                    help="kind=LLM 항목도 Gemma 로 판정(GPU 필요)")
    a = ap.parse_args()

    # 목데이터 채점은 그 라벨을 만든 규칙·날짜를 그대로 써야 재현된다.
    checks = (load_checks(path=CHECKS_MOCK) if a.mock_checks
              else load_checks(product=a.product))
    on = REFERENCE_DATE if a.mock_checks else today()
    print(f"판정 규칙 {len(checks)}건 · 기준일 {on}  "
          f"{collections.Counter(c['kind'] for c in checks)}\n")

    if a.real:
        skipped = 0
        for ad in load_real():
            fs = detect(ad, checks, on=on, use_llm=a.llm, verbose=True)
            pend = 0 if a.llm else pending_llm(ad, checks)
            skipped += pend
            print(f"{ad.id:20s} 지적 {len(fs)}건  "
                  f"{', '.join(sorted({f['지적유형'] for f in fs})) or '없음'}"
                  + (f"   (LLM 미판정 {pend}건)" if pend else ""))
        print("\n※ 실물은 파서를 안 거쳐 글자크기·좌표가 없다. STYLE 판정은 안 돈다.")
        if skipped:
            # **안 돈 것을 조용히 넘기지 않는다.** 규칙 837건 중 819건이 LLM
            # 종류라, 이걸 안 세면 「지적 3건」이 다 본 결과처럼 보인다.
            print(f"※ LLM 판정을 안 돌려 총 {skipped:,}건이 미판정이다. "
                  f"--llm 을 붙이면 Gemma 로 판정한다.")
        return

    ads = AI.load(a.path)
    lab = AI.labels(a.path)

    if a.ad:
        ad = next(x for x in ads if x.id == a.ad)
        print(f"== {ad.id} ==  라벨 {lab.get(ad.id)}")
        for f in detect(ad, checks):
            print(f"\n  [{f['지적유형']}]  {f['check_id']} · {f['근거규정']}")
            print(f"    사유   {f['사유']}")
            print(f"    위치   {f['위치']}  {f['bbox']}")
            print(f"    인용   {f['인용']}")
            print(f"    개선안 {f['개선안']}")
        return

    # 채점. **「라벨에 없다」와 「틀렸다」를 가른다** — 목데이터 라벨은 심어 놓은
    # 위반만 적은 것이라, 라벨 밖 검출이 곧 오답은 아니다. 사람이 봐야 한다.
    tp = fn = 0
    extra = []
    for ad in ads:
        want = set(lab.get(ad.id) or [])
        got = {f["지적유형"] for f in detect(ad, checks)}
        tp += len(want & got)
        fn += len(want - got)
        for k in sorted(got - want):
            extra.append((ad.id, k))
        mark = "○" if want <= got else "✕"
        print(f"{mark} {ad.id[-16:]:20s} 라벨 {','.join(sorted(want)) or '-':42s} "
              f"검출 {','.join(sorted(got)) or '-'}")

    print(f"\n라벨 {tp+fn}건 중 잡음 {tp} · 놓침 {fn}  "
          f"→ 재현율 {tp/max(tp+fn,1)*100:.0f}%")
    print(f"라벨 밖 검출 {len(extra)}건 — **오답이 아니라 확인 대상**:")
    for aid, k in extra:
        print(f"   {aid[-16:]:20s} {k}")


if __name__ == "__main__":
    main()
