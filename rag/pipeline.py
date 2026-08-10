# -*- coding: utf-8 -*-
"""광고 심의 파이프라인 — **되는 구조(2-hop)로 통일했다.**

    광고 파서청크 → ① 규칙 검색 → ② 리랭킹 → ③ 근거 조문(링크) → ④ 판정

**전에는 「직접」 방식이었다** — 광고문을 LLM 이 질의로 바꿔 조문에 바로 던졌다.
그 방식은 측정에서 **12조합 전부 0.0%** 였다. 광고 말투와 법률 말투가 너무 다르다.

    광고    "최저 연 4.45% ~ 최대 연 5.45% (2026.06.18. 당행 기준금리…)"
    조문    "나. 이자율의 범위 및 산출기준"

규칙이 그 사이에 있다 — **실무 말투로 쓰였고 근거로 조문이 달려 있다.**
광고 청크를 규칙에 던지고(말투가 겹친다), 걸린 규칙의 근거 주소를 따라
조문으로 간다(검색이 아니라 링크다). 이 구조가 R@5 60%(n=15) 다.

바뀐 것 — 전부 「가짜였거나 안 돌던」 것들이다.

| | 전 | 지금 |
|---|---|---|
| 검색 | 순수 파이썬 BM25 + numpy 전수내적 | **Elasticsearch(nori) + kNN** — 수요사가 쓰는 것 |
| 리랭커 | `FlagEmbedding` (설치도 안 돼 있어 **항상 건너뜀**) | **BGE-reranker-v2-m3** (CrossEncoder) |
| 질의 | LLM 목(정규식 14개) | **광고 파서청크 원문** — 질의 생성 자체가 불필요 |
| 판정 | 목("판정 못 함") | **Gemma** (GPU) |
| 구조 | 직접(0%) | **2-hop**(R@5 60%) |

  python rag/pipeline.py --ad 2026_001_대출성
  python rag/pipeline.py --all --out output/_rag/review_items.json
  python rag/pipeline.py --all --no-llm      # 근거까지만, 판정은 건너뜀
"""
import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import llm
import twohop2 as T

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG = os.path.join(ROOT, "output", "_rag")
ADS_PARSED = os.path.join(RAG, "ads_parsed.jsonl")

TOP_K = 5           # ADR-0043: 검토항목 하나에 근거 1~5개
CAND_K = 30         # 리랭커에 넘길 규칙 후보 수
N_CHUNKS = 14       # 질의로 쓸 광고 청크 수(긴 것부터)
PER_RULE = 2        # 근거 칸을 규칙 하나가 독식하지 못하게
MIN_CHARS = 50      # 이보다 짧으면 광고가 아니라 파싱 실패다
AD_CHARS = 12000    # 판정에 넣을 광고문 길이

_RR = None


# ── ① 질의 = 광고 파서청크 ─────────────────────────────────────────────────
def ad_queries(ad, n=N_CHUNKS):
    """광고 → 질의. **LLM 을 쓰지 않는다.**

    질의를 LLM 으로 만들던 것을 걷어냈다. 파서가 쪼갠 청크를 그대로 던지는
    쪽이 측정에서 낫고(2-hop R@5 60%), 단계가 하나 줄어 실패 지점도 준다.
    짧은 셀(「가입대상」 같은 한 낱말)은 질의로 값어치가 없어 뺀다.
    """
    cs = [c["text"] for c in (ad.get("청크") or []) if len(c["text"]) >= 15]
    cs.sort(key=len, reverse=True)
    return cs[:n] or [ad.get("text", "")[:500]]


# ── ② 규칙 검색 (hop1) ────────────────────────────────────────────────────
def retrieve_rules(th, queries, k=CAND_K, how="hybrid", product=None,
                   backend="elasticsearch"):
    """광고 청크 → 규칙 후보. 검색은 Elasticsearch 가 한다."""
    if backend == "elasticsearch":
        return th.hop1_elasticsearch(queries, k, how, product=product)
    if backend == "opensearch":
        return th.hop1_opensearch(queries, k, how, product=product)
    return th.hop1(queries, k, how, product=product)


# ── ③ 리랭킹 — BGE-reranker-v2-m3 ─────────────────────────────────────────
def rerank(queries, cands, rows, k=TOP_K, model="BAAI/bge-reranker-v2-m3"):
    """교차 인코더로 규칙 후보를 다시 줄 세운다.

    **광고 전문을 넘기지 않는다.** 전에 전문 1,000자를 통째로 넘겨 R@5 를
    3분의 1로 떨어뜨린 적이 있다. 청크마다 따로 재정렬해 후보별 **최고점**을
    쓴다 — 광고의 한 대목만 걸려도 그 규칙은 살아야 하므로 평균이 아니다.

    전에는 `FlagEmbedding` 을 import 했는데 **설치된 적이 없어 항상 조용히
    건너뛰었다**(실측: review_items 7건 전부 `skipped(모듈 없음)`).
    저장소의 다른 모든 곳이 쓰는 `sentence_transformers.CrossEncoder` 로 맞춘다.
    """
    if not cands:
        return [], "none"
    global _RR
    if _RR is None:
        from sentence_transformers import CrossEncoder
        _RR = CrossEncoder(model, max_length=512)
    pairs = [[q, T.index_text(rows[i])[:600]] for i in cands for q in queries]
    scores = _RR.predict(pairs)
    best, p = {}, 0
    for i in cands:
        for _ in queries:
            best[i] = max(best.get(i, -1e9), float(scores[p]))
            p += 1
    order = sorted(cands, key=lambda i: -best[i])[:k]
    return [(i, best[i]) for i in order], model


# ── ④ 판정 ────────────────────────────────────────────────────────────────
_JUDGE = """당신은 금융광고 심의 담당자입니다. 아래 광고문이 제시된 규정에
맞는지 판정하세요.

판정은 다음 셋 중 하나입니다.
- 적합: 규정 위반이 없음
- 부적합: 규정 위반이 있음
- 확인필요: 광고문만으로는 판단할 수 없음

규칙:
- 광고문에 실제로 있는 표현만 근거로 삼을 것. 없는 내용을 지어내지 말 것
- 부적합이면 광고문에서 문제가 된 대목을 그대로 인용할 것

반드시 아래 JSON 형식으로만 답하세요.
{{"판정": "적합|부적합|확인필요", "사유": "...", "인용": "...",
  "근거": ["evidence_id", ...], "수정제안": "..."}}

규정:
{evidences}

광고문:
{ad}"""


def judge(ad_text, evidences, rows):
    """근거 묶음으로 판정. **목이 없다** — LLM 을 못 부르면 예외가 올라간다."""
    if not evidences:
        return {"판정": "확인필요", "사유": "검색된 근거가 없습니다.",
                "근거": [], "수정제안": "", "_source": "no-evidence"}
    body = "\n\n".join(
        f"[{rows[i]['evidence_id']}] {rows[i].get('title','')}\n"
        f"{(rows[i].get('content') or '')[:600]}" for i, _ in evidences)
    got = llm.chat([{"role": "user",
                     "content": _JUDGE.format(evidences=body, ad=ad_text[:AD_CHARS])}],
                   max_tokens=1024, json_mode=True)
    try:
        out = llm.extract_json(got)
    except (json.JSONDecodeError, ValueError):
        # **파싱 실패를 판정으로 바꾸지 않는다.** 「확인필요」로 뭉개면 모델이
        # 형식을 못 지킨 것과 진짜 애매한 광고가 구분되지 않는다.
        return {"판정": None, "사유": "LLM 응답을 JSON 으로 읽지 못했습니다.",
                "근거": [], "수정제안": "", "_source": "parse-error",
                "_raw": (got or "")[:500]}
    out["_source"] = "llm"
    return out


# ── 전체 ──────────────────────────────────────────────────────────────────
def pick_evidences(th, rule_rows, k=TOP_K, per_rule=PER_RULE):
    """규칙 근거 → 조문. **규칙 하나가 근거 칸을 독식하지 못하게 한다.**

    `hop2(top)[:k]` 로 자르면 1등 규칙이 항·호를 10개 뱉을 때 5칸을 혼자 다
    먹고 나머지 규칙은 근거에 못 들어간다 — 실측에서 광고 18건 중 8건이
    규칙 1개에서만 근거가 나왔고, 정답 조문이 근거에 든 광고는 3/15 였다
    (검색 자체는 R@5 53% 인데도).
    """
    by_rule = {}
    for j, rid, p in th.hop2(rule_rows):
        by_rule.setdefault(rid, []).append((j, rid, p))
    out, seen = [], set()
    for r in range(per_rule):                 # 규칙마다 1개씩 돌아가며
        for lst in by_rule.values():
            if len(out) >= k:
                break
            if r < len(lst) and lst[r][0] not in seen:
                seen.add(lst[r][0])
                out.append(lst[r])
        if len(out) >= k:
            break
    return out[:k]


def review(ad, th=None, how="hybrid", k=TOP_K, backend="elasticsearch",
           use_llm=True, use_rerank=False):
    """광고 하나 → 검토 결과. review_items 한 건에 해당한다.

    `use_rerank` 기본값이 **꺼짐**이다 — 리랭커를 켜면 두 번의 측정에서 모두
    R@5 가 떨어졌다(53.3% → 40.0%). 켜고 끄고를 비교할 수 있게 남겨는 둔다.
    """
    th = th or T.TwoHop2()
    rows = th.rows
    text = (ad.get("text") or "").strip()
    if len(text) < MIN_CHARS:
        # **빈 광고를 조용히 넘기지 않는다.** 이미지 PDF 라 파싱이 안 된 건이
        # 있는데(2026_001_예금성 0자), 그대로 판정에 넣으면 규칙 595건이 전부
        # 실패하고 재시도로 시간만 쓴다. 왜 결과가 없는지 말해 준다.
        return {"광고id": ad.get("광고id"), "규칙": [], "근거": [],
                "_질의출처": "-", "_검색": "-", "_리랭커": "-",
                "판정": {"판정": None, "_source": "no-text",
                         "사유": f"광고 텍스트가 없다({len(text)}자) — OCR 필요"}}
    queries = ad_queries(ad)
    product = T.product_of(ad.get("광고id", ""))
    cands = retrieve_rules(th, queries, CAND_K if use_rerank else k, how,
                           product, backend)
    if use_rerank:
        top, rrsrc = rerank(queries, cands, rows, k)
    else:
        top, rrsrc = [(i, None) for i in cands[:k]], "off"

    # hop2 — 검색이 아니라 근거 주소를 따라간다
    arts = pick_evidences(th, [i for i, _ in top], k)
    evidences = []
    for j, rid, path in arts[:k]:
        r = rows[j]
        evidences.append({
            "evidence_id": r["evidence_id"],
            "kind": "매뉴얼" if r["evidence_id"].startswith("M-") else "조문",
            "title": r.get("title", ""),
            "article_no": r.get("article_no", ""),
            "위치": path,
            "걸린규칙": rid,
        })

    out = {
        "광고id": ad.get("광고id"),
        "질의수": len(queries),
        "_질의출처": "광고 파서청크(원문)",
        "_검색": f"{backend}/{how}",
        "_리랭커": rrsrc,
        "규칙": [{"rank_no": n, "evidence_id": rows[i]["evidence_id"],
                  "title": rows[i].get("title", ""),
                  "score": (round(s, 4) if s is not None else None)}
                 for n, (i, s) in enumerate(top, 1)],
        "근거": evidences,
    }
    if use_llm:
        out["판정"] = judge(ad.get("text", ""),
                            [(j, None) for j, _, _ in arts[:k]], rows)
    return out


def load_ads():
    ads = {}
    for l in open(ADS_PARSED, encoding="utf-8"):
        x = json.loads(l)
        ads.setdefault(x["광고id"], x)
    return ads


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ad", help="광고id (ads_parsed.jsonl)")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--how", default="hybrid", choices=("bm25", "vector", "hybrid"))
    ap.add_argument("--backend", default="elasticsearch",
                    choices=("elasticsearch", "opensearch", "local"),
                    help="검색엔진. 수요사 환경은 elasticsearch")
    ap.add_argument("--no-llm", action="store_true", help="판정 건너뛰기")
    ap.add_argument("--rerank", action="store_true",
                    help="리랭커 켜기(측정에선 손해였다)")
    ap.add_argument("-k", type=int, default=TOP_K)
    ap.add_argument("--out")
    a = ap.parse_args()

    ads = load_ads()
    th = T.TwoHop2()
    print(f"색인 {len(th.rows):,}건 · 규칙 {th.n_rules:,} · 검색 {a.backend}/{a.how}"
          f" · 리랭커 {'BGE-reranker-v2-m3' if a.rerank else 'off'}"
          f" · 판정 {'off' if a.no_llm else llm.backend()}\n")

    if a.all:
        targets = list(ads.values())
    elif a.ad:
        if a.ad not in ads:
            ap.error(f"광고를 못 찾음: {a.ad}")
        targets = [ads[a.ad]]
    else:
        ap.error("--ad 또는 --all 이 필요합니다")

    out = []
    for ad in targets:
        r = review(ad, th, a.how, a.k, a.backend,
                   use_llm=not a.no_llm, use_rerank=a.rerank)
        out.append(r)
        print("=" * 78)
        print(f"{r['광고id']}  질의 {r['질의수']}개 · 리랭커 {r['_리랭커']}")
        for e in r["규칙"][:5]:
            print(f"   규칙 {e['rank_no']}. {e['evidence_id']} {e['title'][:52]}")
        for e in r["근거"][:5]:
            print(f"   근거 [{e['위치']:8s}] {e['article_no'] or '':10s} "
                  f"{e['title'][:40]}  ← {e['걸린규칙']}")
        if "판정" in r:
            v = r["판정"]
            print(f"   판정: {v.get('판정') or '—'} · {str(v.get('사유'))[:70]}")

    if a.out:
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        json.dump(out, open(a.out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"\n저장: {a.out}  ({len(out)}건)")


if __name__ == "__main__":
    main()
