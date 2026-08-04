# -*- coding: utf-8 -*-
"""BM25 키워드 검색 — 벡터가 못 잡는 '번호로 찾기'를 담당한다.

1차 파일럿에서 벡터 검색이 무엇에 실패했는지가 이 모듈의 설계 근거다.

  「금융투자업규정 제4-11조」  → 부칙·목적 조항만 나옴. 완전 실패
  「제4-13조 기본예탁금」      → 엉뚱한 법의 예탁금 조항
  「별표 5 투자광고」          → 정답 [별표 0005] 가 5위에 겨우

임베딩은 의미가 비슷한 것을 찾지 **번호를 정확히 맞추지 못한다.** 「제4-11조」와
「제4-41조」는 사람 눈에는 다른 조문이지만 벡터 공간에서는 사실상 같은 자리에 있다.

**표기 정규화가 이 모듈의 핵심이다.** 질의는 「별표 5」라고 쓰는데 청크 키는
`[별표 0005]` 다. 그냥 토큰을 쪼개면 `별표`·`5` 와 `별표`·`0005` 가 되어 안 만난다.
그래서 번호를 만나면 **여러 표기를 다 만들어 넣는다**(5 · 05 · 0005).

한국어 형태소 분석기는 쓰지 않는다. 폐쇄망 반입 대상이 하나 늘고, 법령 텍스트는
조사 변형이 심하지 않아 **음절 바이그램**으로 충분하다(「광고를」·「광고는」이
`광고` 바이그램을 공유한다). 실서비스에서는 OpenSearch + Nori 를 쓰지만, 그건
색인 엔진 선택이고 여기서 재려는 것은 '키워드 검색을 붙이면 번호 질의가 살아나는가'다.

  python rag/bm25.py --build                     # 인덱스 만들기
  python rag/bm25.py "금융투자업규정 제4-11조"      # 검색해 보기
  python rag/bm25.py --eval                      # 1차 실패 질의로 회복 확인
"""
import os
import re
import sys
import json
import math
import pickle
import argparse
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHUNKS = os.path.join(ROOT, "output", "_rag", "chunks.jsonl")
INDEX = os.path.join(ROOT, "output", "_rag", "bm25.pkl")

K1, B = 1.2, 0.75          # Okapi BM25 관례값

_HANGUL = re.compile(r"[가-힣]+")
_WORD = re.compile(r"[A-Za-z0-9]+")
# 제4-11조 · 제80조의2 · 제17조제2항  — 조문 번호는 통째로 하나의 토큰이어야 한다
_ART = re.compile(r"제\s*(\d+)\s*(?:-\s*(\d+))?\s*조(?:\s*의\s*(\d+))?")
# 별표 5 · [별표 0005] · 별지 제3호의2
_TBL = re.compile(r"\[?\s*(별표|별지|서식|첨부)\s*(?:제)?\s*0*(\d+)\s*(?:의\s*(\d+))?\s*(?:호)?\s*\]?")
# 번호 없이 종류만 쓴 경우(「은행업감독규정 별표」). 위 정규식은 숫자를 요구해서 못 잡는다.
_TBL_BARE = re.compile(r"(별표|별지|서식|첨부)")


def _art_tokens(m):
    """조문 번호 하나에서 여러 표기를 만든다.

    「제4-11조」는 `조4-11` 로, 「제80조의2」는 `조80의2` 로 정규화한다. 공백·구두점
    차이를 흡수하려는 것이다 — 질의는 「제 4-11 조」처럼 띄어 쓸 수도 있다.
    """
    a, b, c = m.group(1), m.group(2), m.group(3)
    key = f"조{a}" + (f"-{b}" if b else "") + (f"의{c}" if c else "")
    out = [key]
    if b or c:
        out.append(f"조{a}")     # 상위 조문으로도 걸리게 (제4-11조 → 제4조 계열)
    return out


def _tbl_tokens(m):
    """별표 번호의 여러 표기를 전부 만든다.

    질의 「별표 5」와 청크 키 `[별표 0005]` 가 만나야 한다. 어느 쪽이 어떤 자릿수로
    쓸지 모르므로 **양쪽 표기를 다 넣는다** — 색인에도 질의에도 같은 함수를 쓰므로
    한쪽에서만 맞춰도 교집합이 생긴다.

    **종류 자체(`별표`)도 반드시 같이 넣는다.** 번호를 붙인 토큰만 만들면
    「은행업감독규정 별표」처럼 번호 없이 묻는 질의가 아무것도 못 찾는다(실측:
    별표가 97개 있는 규정인데 상위 5개에 하나도 안 나왔다). 번호 있는 쪽은
    원문에서 `별표` 를 지워 버리므로 여기서 되살려 주지 않으면 영영 사라진다.
    """
    kind, num, sub = m.group(1), int(m.group(2)), m.group(3)
    suf = f"의{sub}" if sub else ""
    return [kind, f"{kind}{num}{suf}", f"{kind}{num:04d}{suf}"]


def tokenize(text):
    """법령/질의 공통 토크나이저. 색인과 질의에 반드시 같은 것을 써야 한다."""
    toks = []
    # 1) 번호부터 뽑고 원문에서 지운다 — 남겨 두면 '조'·'별표' 가 따로 쪼개져 노이즈가 된다
    for m in _ART.finditer(text):
        toks += _art_tokens(m)
    for m in _TBL.finditer(text):
        toks += _tbl_tokens(m)
    rest = _TBL.sub(" ", _ART.sub(" ", text))
    # 번호 없이 남은 「별표」·「별지」도 종류 토큰으로 잡는다(위에서 번호 붙은 것은
    # 이미 지워졌으므로 중복 계산되지 않는다)
    for m in _TBL_BARE.finditer(rest):
        toks.append(m.group(1))
    rest = _TBL_BARE.sub(" ", rest)
    # 2) 영숫자는 그대로 (ELD, KOSPI200, 7.0 등)
    toks += [w.lower() for w in _WORD.findall(rest)]
    # 3) 한글은 음절 바이그램 — 조사 변형을 견딘다
    for run in _HANGUL.findall(rest):
        if len(run) == 1:
            toks.append(run)
        else:
            toks += [run[i:i + 2] for i in range(len(run) - 1)]
    return toks


def build(src=CHUNKS, dest=INDEX, verbose=True):
    rows = [json.loads(l) for l in open(src, encoding="utf-8")]
    df = collections.Counter()
    docs = []
    for r in rows:
        # 키·제목도 본문과 함께 색인한다. 「[별표 0005]」는 key 에만 있고 본문에는
        # 다른 형태로 나오는 경우가 있어, 키를 빼면 번호 질의가 안 걸린다.
        text = f"{r['reg']} {r.get('key','')} {r.get('title','')} {r['text']}"
        tf = collections.Counter(tokenize(text))
        docs.append(tf)
        df.update(tf.keys())

    N = len(docs)
    avgdl = sum(sum(d.values()) for d in docs) / max(N, 1)
    idf = {t: math.log(1 + (N - n + 0.5) / (n + 0.5)) for t, n in df.items()}

    # 역색인: 토큰 → [(문서번호, tf), ...]
    inv = collections.defaultdict(list)
    for i, d in enumerate(docs):
        for t, f in d.items():
            inv[t].append((i, f))

    idx = {"inv": dict(inv), "idf": idf, "dl": [sum(d.values()) for d in docs],
           "avgdl": avgdl, "N": N}
    with open(dest, "wb") as f:
        pickle.dump(idx, f, protocol=4)
    if verbose:
        print(f"문서 {N:,} · 어휘 {len(idf):,} · 평균 길이 {avgdl:.0f} 토큰")
        print(f"저장: {dest} ({os.path.getsize(dest)/1e6:.1f}MB)")
    return idx


_cache = {}


def load(path=INDEX):
    if path not in _cache:
        with open(path, "rb") as f:
            _cache[path] = pickle.load(f)
    return _cache[path]


def search(query, k=50, idx=None):
    """(문서번호, 점수) 상위 k개."""
    idx = idx or load()
    inv, idf, dl, avgdl = idx["inv"], idx["idf"], idx["dl"], idx["avgdl"]
    sc = collections.defaultdict(float)
    for t in set(tokenize(query)):
        post = inv.get(t)
        if not post:
            continue
        w = idf[t]
        for i, f in post:
            sc[i] += w * f * (K1 + 1) / (f + K1 * (1 - B + B * dl[i] / avgdl))
    return sorted(sc.items(), key=lambda x: -x[1])[:k]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="*")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--eval", action="store_true", help="1차에서 실패한 번호 질의로 확인")
    ap.add_argument("-k", type=int, default=5)
    a = ap.parse_args()

    if a.build:
        build()
        return

    rows = [json.loads(l) for l in open(CHUNKS, encoding="utf-8")]

    def show(q):
        print(f"\n■ {q}")
        for rank, (i, s) in enumerate(search(q, a.k), 1):
            r = rows[i]
            print(f"  {rank}. {s:6.2f}  {r['reg'][:30]:30s} {r.get('key','')} "
                  f"{(r.get('title') or '')[:30]}")

    if a.eval:
        # 1차 파일럿에서 벡터가 못 잡은 것들 — 여기서 살아나야 하이브리드가 값어치가 있다
        for q in ["금융투자업규정 제4-11조",
                  "금융투자회사의 영업 및 업무에 관한 규정 제4-13조 기본예탁금",
                  "별표 5 투자광고",
                  "금융소비자 보호에 관한 법률 제22조 광고 규제",
                  "자본시장법 제57조",
                  "은행업감독규정 별표"]:
            show(q)
        return

    if not a.query:
        ap.error("질의를 주거나 --build / --eval 을 쓰세요")
    show(" ".join(a.query))


if __name__ == "__main__":
    main()
