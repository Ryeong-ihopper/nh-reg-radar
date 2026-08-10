# -*- coding: utf-8 -*-
"""랭그래프 껍데기 — DAP 주피터에서 실행할 형태.

**로직은 여기 없다.** `pipeline.py` 의 순수 함수를 노드로 감쌀 뿐이다. 그렇게 나눈
이유는 하나다 — 로직이 그래프 안에 들어가면 **랭그래프 없이는 한 줄도 못 돌려 본다.**
DAP 의 랭그래프 버전이 우리 것과 다를 수 있고, 그때 고칠 곳이 이 파일 하나여야 한다.

**2-hop 구조를 따라간다** (`pipeline.py` 와 같다).

    광고 파서청크 → ① 규칙 검색(ES) → ② 리랭킹(BGE) → ③ 근거 조문(링크) → ④ 판정

전에는 「질의 생성 → 조문 직접 검색」이었는데 그 구조는 측정에서 0.0% 였다.
질의 생성 노드가 사라진 것은 그래서다 — 광고 청크를 그대로 던진다.

랭그래프가 여기서 실제로 해 주는 일:
  · 단계마다 상태를 남긴다 — 어디서 무엇이 비었는지 사후에 볼 수 있다
  · 근거가 없으면 판정을 건너뛰는 분기
  · 체크포인터를 붙이면 광고 수백 건을 돌리다 끊겨도 이어서 돌릴 수 있다

  python rag/graph.py --ad 2026_004_예금성
"""
import os
import sys
import json
import argparse
from typing import TypedDict, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pipeline as P
import twohop2 as T


class State(TypedDict, total=False):
    ad_id: str
    ad: dict
    how: str
    backend: str
    product: Optional[str]
    no_rerank: bool
    no_llm: bool
    queries: list
    candidates: list      # 규칙 행 번호
    ranked: list          # 리랭킹 뒤 규칙 행 번호
    reranker: str
    evidences: list       # (조문행, 걸린규칙, 위치)
    verdict: dict


# 색인은 노드마다 다시 읽으면 안 된다(35,961건 × 광고 수). 모듈 수준에 한 번만.
_TH = None


def _th():
    global _TH
    if _TH is None:
        _TH = T.TwoHop2()
    return _TH


def n_queries(state: State) -> State:
    """질의 = 광고 파서청크. **LLM 을 쓰지 않는다.**"""
    return {"queries": P.ad_queries(state["ad"]),
            "product": state.get("product") or T.product_of(state.get("ad_id", ""))}


def n_retrieve(state: State) -> State:
    cands = P.retrieve_rules(_th(), state["queries"], P.CAND_K,
                             state.get("how", "hybrid"), state.get("product"),
                             state.get("backend", "elasticsearch"))
    return {"candidates": cands}


def n_rerank(state: State) -> State:
    if state.get("no_rerank"):
        return {"ranked": state["candidates"][:P.TOP_K], "reranker": "off"}
    top, src = P.rerank(state["queries"], state["candidates"], _th().rows, P.TOP_K)
    return {"ranked": [i for i, _ in top], "reranker": src}


def n_link(state: State) -> State:
    """hop2 — **검색이 아니라 근거 주소를 따라간다.**"""
    return {"evidences": _th().hop2(state["ranked"])[:P.TOP_K]}


def n_judge(state: State) -> State:
    if state.get("no_llm"):
        return {"verdict": {"판정": None, "사유": "판정을 건너뜀(--no-llm)",
                            "_source": "off"}}
    rows = _th().rows
    ev = [(j, None) for j, _, _ in state["evidences"]]
    return {"verdict": P.judge(state["ad"].get("text", ""), ev, rows)}


def n_no_evidence(state: State) -> State:
    """근거가 하나도 없을 때. **LLM 을 부르지 않는다.**

    근거 없이 판정을 시키면 모델이 상식으로 답을 지어내고, 그게 근거 있는 판정과
    같은 모양으로 나온다. 검색이 실패한 것을 판정 실패로 덮으면 안 된다.
    """
    return {"verdict": {"판정": "확인필요", "사유": "검색된 근거가 없습니다.",
                        "근거": [], "수정제안": "", "_source": "no-evidence"}}


def has_evidence(state: State) -> str:
    return "judge" if state.get("evidences") else "no_evidence"


def build():
    from langgraph.graph import StateGraph, START, END

    g = StateGraph(State)
    g.add_node("queries", n_queries)
    g.add_node("retrieve", n_retrieve)
    g.add_node("rerank", n_rerank)
    g.add_node("link", n_link)
    g.add_node("judge", n_judge)
    g.add_node("no_evidence", n_no_evidence)

    g.add_edge(START, "queries")
    g.add_edge("queries", "retrieve")
    g.add_edge("retrieve", "rerank")
    g.add_edge("rerank", "link")
    g.add_conditional_edges("link", has_evidence,
                            {"judge": "judge", "no_evidence": "no_evidence"})
    g.add_edge("judge", END)
    g.add_edge("no_evidence", END)
    return g.compile()


def to_review_item(state: State):
    """스키마의 review_items / review_item_evidences 모양으로."""
    rows = _th().rows
    return {
        "광고id": state.get("ad_id"),
        "질의수": len(state.get("queries") or []),
        "_질의출처": "광고 파서청크(원문)",
        "_검색": f"{state.get('backend','elasticsearch')}/{state.get('how','hybrid')}",
        "_리랭커": state.get("reranker"),
        "규칙": [{"rank_no": n, "evidence_id": rows[i]["evidence_id"],
                  "title": rows[i].get("title", "")}
                 for n, i in enumerate(state.get("ranked") or [], 1)],
        "근거": [{"evidence_id": rows[j]["evidence_id"],
                  "article_no": rows[j].get("article_no", ""),
                  "title": rows[j].get("title", ""),
                  "위치": p, "걸린규칙": rid}
                for j, rid, p in (state.get("evidences") or [])],
        "판정": state.get("verdict", {}),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ad")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--how", default="hybrid", choices=("bm25", "vector", "hybrid"))
    ap.add_argument("--backend", default="elasticsearch",
                    choices=("elasticsearch", "opensearch", "local"))
    ap.add_argument("--no-rerank", action="store_true")
    ap.add_argument("--no-llm", action="store_true", help="판정 건너뛰기")
    ap.add_argument("--out")
    a = ap.parse_args()

    app = build()
    ads = P.load_ads()
    if a.ad:
        if a.ad not in ads:
            ap.error(f"광고를 못 찾음: {a.ad}")
        targets = [ads[a.ad]]
    elif a.all:
        targets = list(ads.values())
    else:
        targets = list(ads.values())[:1]

    out = []
    for ad in targets:
        st = app.invoke({"ad_id": ad["광고id"], "ad": ad,
                         "how": a.how, "backend": a.backend,
                         "no_rerank": a.no_rerank, "no_llm": a.no_llm})
        item = to_review_item(st)
        out.append(item)
        print("=" * 78)
        print(f"{item['광고id']}  질의 {item['질의수']}개 · 리랭커 {item['_리랭커']}")
        for e in item["근거"]:
            print(f"   [{e['위치']:8s}] {e['article_no'] or '':10s} "
                  f"{e['title'][:40]}  ← {e['걸린규칙']}")
        print(f"   판정: {item['판정'].get('판정') or '—'}")

    if a.out:
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        json.dump(out, open(a.out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"\n저장: {a.out}  ({len(out)}건)")


if __name__ == "__main__":
    main()
