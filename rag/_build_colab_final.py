# -*- coding: utf-8 -*-
"""rag/final_colab.ipynb — **바로잡은 것을 다 넣고 GPU 에서 한 번에** 측정한다.

CPU 로는 리랭커가 광고 13건에 한 시간 넘게 걸려 결과를 못 봤다. GPU 면 몇 분이다.

이 노트북에 들어가는 것 — 오늘 고친 것 전부

    정답    ad_gold4     심의사례 근거규정을 항·호·목까지 따라감 → 정답 1~3행 (앞은 48~140행)
    광고    ads_parsed   파서 DocIR → 청크 190개(중앙) · 글자크기 95% · 표 셀 행·열
    색인    호 단위       35,961 · ho_path 로 「5 나」를 가리킴
    근거    규칙 근거 원문에서 「제16조 제1항 제6호 나목」을 다시 뽑음 (817건이 갖고 있었다)

**두 갈래를 견준다.**

    직접   광고 ──────────────→ 조문     CPU 측정에서 18조합 전부 0.0%
    2-hop  광고 → 규칙 → 조문           CPU 측정에서 R@5 46.2%

리랭커는 **2-hop 의 규칙 후보를 다시 줄 세운다.** 조문이 아니라 규칙을 재정렬하는
것이 요점이다 — 조문은 규칙 링크로 따라가므로 규칙 순서가 곧 조문 순서다.

  올릴 것   rule_index_ho.jsonl · ads_parsed.jsonl · ad_gold4.json
  받을 것   final_report.md

  python rag/_build_colab_final.py
"""
import os
import json

MD, PY = "markdown", "code"
CELLS = []


def add(kind, text):
    CELLS.append((kind, text.strip("\n")))


add(MD, """
# 검색 최종 측정 — 바로잡은 것 전부 + 리랭커

## 오늘 무엇을 고쳤나

| | 앞 | 지금 |
|---|---|---|
| 정답 | 「제16조」 아무 조각 → **48~140행** | 「제16조 [5 나]」 → **1~3행** |
| 광고 | HWP 를 긁은 통짜 1청크 | 파서 청크 **190개**(중앙) · 글자크기 95% |
| 색인 | 조 단위 9,335 | 호 단위 **35,961** |
| 규칙 근거 | 「제16조」로 잘라 저장 | 원문에서 **「제16조 제1항 제6호 나목」** 을 다시 뽑음 |

정답을 조인 것은 **심의사례 엑셀의 근거규정 칸 그대로**다. 추측이 없다.

## CPU 에서 나온 것

```
광고 → 조문 직접     18조합 전부 0.0%   (원문·임의청크·파서청크 × bm25·vector·hybrid)
광고 → 규칙 → 조문   bm25   R@5 46.2%
                    vector R@1 23.1%
                    hybrid R@1 30.8%
리랭커              CPU 로 한 시간 넘게 안 끝나 못 봄   ← 이 노트북이 이걸 본다
```

## 준비

| | |
|---|---|
| 런타임 | GPU (T4 도 됨) |
| 올릴 것 | `rule_index_ho.jsonl` (52MB) · `ads_parsed.jsonl` · `ad_gold4.json` |
| 받을 것 | `final_report.md` |
| 소요 | 임베딩 10분 + 측정 10분 |
""")

add(MD, "## 1. 환경")
add(PY, """
!nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
!pip -q install -U sentence-transformers 2>&1 | tail -1
""")

add(MD, """
## 2. 파일 올리기

왼쪽 파일 창에 끌어다 놓아도 된다. 이 셀을 건너뛰어도 다음 셀이 알아서 읽는다.
""")
add(PY, """
import os
from google.colab import files
NEED = ["rule_index_ho.jsonl", "ads_parsed.jsonl", "ad_gold4.json"]
if [n for n in NEED if not os.path.exists(n)]:
    files.upload()
for n in NEED:
    print(f"{n:26s} {os.path.getsize(n)/1e6:7.1f}MB" if os.path.exists(n)
          else f"{n:26s} 없음")
""")

add(MD, """
## 3. 공통 함수

BM25 토크나이저와 색인 문자열을 **로컬과 글자 하나까지 같게** 둔다. 여기가 다르면
로컬 숫자와 견줄 수 없다.
""")
add(PY, r"""
import json, re, math, time, collections
import numpy as np

NL = chr(10)
RRF_K = 60

rows = [json.loads(l) for l in open("rule_index_ho.jsonl", encoding="utf-8")]
n_rules = sum(1 for r in rows if r["evidence_id"].startswith("R-"))
is_rule = np.array([r["evidence_id"].startswith("R-") for r in rows])
print(f"색인 {len(rows):,} = 규칙 {n_rules:,} + 조문·매뉴얼 {len(rows)-n_rules:,}")

def index_text(r):
    return f"{r.get('title','')} {r.get('article_no') or ''} {r.get('content','')}"

def tokenize(s):
    out = re.findall(r"제\s*\d+조(?:의\s*\d+)?|[A-Za-z]+|\d+", str(s or ""))
    for w in re.findall(r"[가-힣]+", str(s or "")):
        out += [w[i:i+2] for i in range(len(w)-1)] or [w]
    return out

class BM25:
    def __init__(self, rows):
        docs, df = [], collections.Counter()
        for r in rows:
            tf = collections.Counter(tokenize(index_text(r)))
            docs.append(tf); df.update(tf.keys())
        n = len(docs)
        self.idf = {t: math.log(1+(n-c+0.5)/(c+0.5)) for t, c in df.items()}
        self.inv = collections.defaultdict(list)
        for i, d in enumerate(docs):
            for t, f in d.items():
                self.inv[t].append((i, f))
        self.dl = [sum(d.values()) for d in docs]
        self.avgdl = sum(self.dl)/max(n, 1)

    def __call__(self, q, k=50, allow=None):
        K1, B = 1.2, 0.75
        sc = collections.defaultdict(float)
        for t in set(tokenize(q)):
            post = self.inv.get(t)
            if not post:
                continue
            w = self.idf[t]
            for i, f in post:
                if allow is not None and not allow[i]:
                    continue
                sc[i] += w*f*(K1+1)/(f+K1*(1-B+B*self.dl[i]/self.avgdl))
        return [i for i, _ in sorted(sc.items(), key=lambda x: -x[1])[:k]]

def rrf(*rankings, top=50):
    # 점수가 아니라 **순위**를 더한다. BM25 점수와 코사인은 자릿수가 달라
    # 그대로 더하면 한쪽이 묻힌다.
    sc = collections.defaultdict(float)
    for rank in rankings:
        for r, i in enumerate(rank, 1):
            sc[i] += 1.0/(RRF_K+r)
    return [i for i, _ in sorted(sc.items(), key=lambda x: -x[1])[:top]]

BM = BM25(rows)
print("BM25 준비 완료")
""")

add(MD, """
## 4. 임베딩 (GPU)

색인을 새로 임베딩한다. 미리 만든 벡터를 올리는 것보다 빠르고, 색인과 어긋날
일이 없다. **벡터가 색인과 어긋나면 오류가 안 나고 조용히 엉뚱한 결과가 나온다.**
""")
add(PY, """
from sentence_transformers import SentenceTransformer
EMB = SentenceTransformer("BAAI/bge-m3")

t0 = time.time()
V = EMB.encode([index_text(r)[:1200] for r in rows], batch_size=64,
               normalize_embeddings=True, show_progress_bar=True).astype("float32")
print(f"{V.shape} · {time.time()-t0:.0f}초")

norms = np.linalg.norm(V, axis=1)
assert abs(norms.mean() - 1.0) < 1e-3, "정규화가 안 됐다"
print("정규화 확인 완료")
""")

add(MD, """
## 5. 근거 주소 — 규칙 → 조문 링크

**`근거` 필드를 그대로 쓴다.** 원천은 엑셀(규칙리스트 v3)의 근거상세 열이고
`match_rules.py` 가 조문지도 246행과 대조까지 마쳐 둔 것이다 — 규칙 1,744건
전부에 이미 채워져 있다. 전에는 이걸 안 보고 `근거상세_원문` 을 정규식으로
다시 파싱해 **355건만** 이었다. 이미 있는 걸 다시 만들다 못 미친 것.

    `근거` 그대로 쓰기        355 →   920
    + 매뉴얼 발췌도 연결      920 → 1,518   (조문이 아닌 근거 438건 중 415건)

`근거` 는 조 단위라, `근거상세_원문` 에서 항·호·목을 더 뽑을 수 있으면
같은 (규정,조) 안에서만 좁힌다.
""")
add(PY, r"""
ALIAS = {"은행 광고심의 기준": "은행 광고심의 기준 및 세칙",
         "은행 광고심의기준": "은행 광고심의 기준 및 세칙",
         "은행 광고심의 기준 세칙": "은행 광고심의 기준 및 세칙",
         "금융소비자보호법": "금융소비자 보호에 관한 법률",
         "금소법": "금융소비자 보호에 관한 법률",
         "여신금융상품 광고에 관한 세부지침": "여신전문금융회사 등의 광고에 관한 규정 세부지침",
         "증발공규정": "증권의 발행 및 공시 등에 관한 규정",
         "협회 표준내부통제기준": "금융투자회사 표준내부통제기준",
         "인공지능기본법": "인공지능 발전과 신뢰 기반 조성 등에 관한 기본법",
         "약관법": "약관의 규제에 관한 법률",
         "금융소비자 보호에 관한 금융소비자 보호에 관한 감독규정": "금융소비자 보호에 관한 감독규정"}

_REF = re.compile(
    r"(?P<name>[가-힣·\s]+?)\s*"
    r"제\s*(?P<jo>\d+(?:-\d+)?)\s*조(?:\s*의\s*(?P<ji>\d+))?"
    r"(?:\s*제\s*(?P<hang>\d+)\s*항)?"
    r"(?:\s*제?\s*(?P<ho>\d+)\s*호)?"
    r"(?:\s*(?P<mok>[가-힣])\s*목)?")

def norm(s):
    return re.sub(r"[\s·ㆍ]", "", str(s or ""))

def wsnorm(s):
    return re.sub(r"\s+", "", str(s or ""))

def parse_basis(text):
    out = []
    for part in re.split(r"[,\n;]", str(text or "")):
        m = _REF.search(part)
        if not m:
            continue
        name = ALIAS.get((m.group("name") or "").strip(" ·,"),
                         (m.group("name") or "").strip(" ·,"))
        if not name:
            continue
        jo = f"제{m.group('jo')}조" + (f"의{m.group('ji')}" if m.group("ji") else "")
        # **항 번호는 경로에 안 넣는다.** 색인의 ho_path 는 조문 첫머리 ①이
        # 도입문으로 흡수돼 「5 나」로 저장된 경우가 많다. 호·목만으로 맞춘다.
        bits = [x for x in (m.group("ho"), m.group("mok")) if x]
        out.append((name, jo, " ".join(bits)))
    return out

BY_ADDR = collections.defaultdict(list)
BY_ARTICLE = collections.defaultdict(list)
BY_MANUAL = collections.defaultdict(list)
for i, r in enumerate(rows):
    eid = r["evidence_id"]
    if eid.startswith("R-"):
        continue
    if eid.startswith("M-"):
        code = (r.get("metadata_json") or {}).get("출처매뉴얼")
        if code:
            BY_MANUAL[code].append((i, wsnorm(r.get("content"))))
        continue
    m = re.match(r"\[([^\]]+)\]", r.get("content") or "")
    if m:
        key = (norm(m.group(1)), re.sub(r"\s", "", r.get("article_no") or ""))
        BY_ADDR[key + ((r.get("metadata_json") or {}).get("ho_path", ""),)].append(i)
        BY_ARTICLE[key].append(i)

def hop2(rule_rows):
    out, seen = [], set()
    for i in rule_rows:
        r = rows[i]
        narrow = parse_basis((r.get("metadata_json") or {}).get("근거상세_원문") or "")
        addrs, seen_addr = [], set()
        for g in (r.get("근거") or []):
            if g.get("유형") == "발췌":
                # 조문이 아니라 매뉴얼 발췌 — 매뉴얼도 색인에 들어 있으니
                # (M-*) 그 발췌 본문을 담은 청크를 찾아 붙인다.
                mm = re.match(r"(M\d+)", g.get("article_no") or "")
                snip = wsnorm(g.get("본문"))[:20]
                if not mm or not snip:
                    continue
                for j, content in BY_MANUAL.get(mm.group(1), []):
                    if snip in content and j not in seen:
                        seen.add(j); out.append(j)
                continue
            if g.get("유형") != "조문":
                continue
            name, jo = norm(g.get("규정") or ""), re.sub(r"\s", "", g.get("article_no") or "")
            if name and jo and (name, jo) not in seen_addr:
                seen_addr.add((name, jo)); addrs.append((name, jo))
        for name, jo in addrs:
            got = None
            for pname, pjo, ppath in narrow:
                if norm(pname) != name or re.sub(r"\s", "", pjo) != jo or not ppath:
                    continue
                for p in (ppath, " ".join(ppath.split()[:-1])):
                    got = BY_ADDR.get((name, jo, p))
                    if got:
                        break
                if got:
                    break
            if not got:
                got = BY_ARTICLE.get((name, jo))
            for j in (got or []):
                if j not in seen:
                    seen.add(j); out.append(j)
    return out

n_addr = sum(1 for i, r in enumerate(rows)
             if r["evidence_id"].startswith("R-") and hop2([i]))
print(f"조문·매뉴얼에 이어진 규칙 {n_addr:,}/{n_rules:,}건")
""")

add(MD, "## 6. 광고와 정답")
add(PY, r"""
ads = {}
for l in open("ads_parsed.jsonl", encoding="utf-8"):
    x = json.loads(l); ads.setdefault(x["광고id"], x)
gold = [g for g in json.load(open("ad_gold4.json", encoding="utf-8"))["건"]
        if g.get("정답행") and g["광고id"] in ads]
print(f"광고 {len(ads)}건 · 정답 {len(gold)}건 "
      f"(정답 행수 {min(len(g['정답행']) for g in gold)}~"
      f"{max(len(g['정답행']) for g in gold)}개)")

def chunks_of(aid, n=14):
    cs = [c["text"] for c in (ads[aid].get("청크") or []) if len(c["text"]) >= 15]
    # 긴 것부터 — 「가입대상」 같은 한 낱말 셀은 질의로 값어치가 낮다
    cs.sort(key=len, reverse=True)
    return cs[:n] or [ads[aid]["text"][:500]]

# 상품군 — 규칙 스키마에 이미 있는 product_group 을 그대로 쓴다.
# 빈 리스트(상품 공통)는 항상 통과시킨다.
PRODUCT_MAP = {"예금성": "DEPOSIT", "대출성": "LOAN",
               "투자성": "INVESTMENT", "보장성": "INSURANCE"}
PG = [set(r.get("product_group") or []) for r in rows]

def product_of(aid):
    for kw, code in PRODUCT_MAP.items():
        if kw in str(aid or ""):
            return code
    return None

def product_mask(product):
    if not product:
        return np.ones(len(rows), dtype=bool)
    return np.array([not pg or product in pg for pg in PG])

QC = {}
def qvec(q):
    if q not in QC:
        QC[q] = EMB.encode([q], normalize_embeddings=True).astype("float32")[0]
    return QC[q]

# **POOL_K 는 넉넉해야 한다.** 50 이면 상품군 필터가 역효과를 낸다 —
# 무관한 상품 후보가 그 50자리에서 빠지고, 그 자리를 관련 상품이지만
# 원래 순위가 애매하던 후보가 새로 차지해 오히려 정답을 밀어낸다
# (로컬 실측: 대출 광고에서 필터로 정답이 1등→4등). 넉넉히 잡으면
# 필터 유무와 무관하게 순위가 같아진다(300 에서 확인).
POOL_K = 300

# 이 질의가 만드는 **순위 리스트들**을 그대로 돌려준다(병합 안 함).
#
# 전에는 여기서 청크별로 먼저 RRF 를 하고 바깥에서 또 RRF 를 했다(중첩).
# twohop2.py 는 청크·방식 순위를 전부 모아 **한 번만** RRF 한다(평탄).
# 같은 자료·같은 색인인데 hybrid 만 로컬과 숫자가 달랐던 것이 이 차이였다
# (bm25·vector 단독은 병합할 것이 하나뿐이라 안 갈렸다). **로컬에 맞춘다** —
# 로컬 쪽이 끝까지 측정·검증된 경로다.
def rankings(q, how, mask, k=POOL_K):
    out = []
    if how in ("bm25", "hybrid"):
        out.append(BM(q, k, allow=mask))
    if how in ("vector", "hybrid"):
        s = V @ qvec(q); s[~mask] = -1e9
        out.append(list(np.argsort(-s)[:k]))
    return out
""")

add(MD, """
## 7. 리랭커
""")
add(PY, """
from sentence_transformers import CrossEncoder
RR = CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=512)
print("리랭커 준비 완료")
""")

add(MD, """
## 8. 측정 — 두 갈래 × 세 검색 × 리랭커 유무

**직접**은 광고 청크를 조문에 바로 던진다. **2-hop** 은 규칙에 던지고 근거 링크를
따라간다. 리랭커는 **규칙 후보를 다시 줄 세운다** — 조문은 링크로 따라가므로
규칙 순서가 곧 조문 순서다.
""")
add(PY, r"""
KL = [1, 3, 5, 10, 20]
RESULT = []
not_rule = ~is_rule

for way in ("직접", "2-hop"):
    for how in ("bm25", "vector", "hybrid"):
        for use_rr in (False, True):
            hit = {k: 0 for k in KL}; n = 0
            t0 = time.time()
            for g in gold:
                ans = set(g["정답행"]); n += 1
                qs = chunks_of(g["광고id"])
                # 상품군 필터 — 예금 광고에 투자 규칙이 후보를 먹지 않게.
                # 스키마에 이미 있는 필드라 새로 만들 것이 없다.
                mask = (is_rule if way == "2-hop" else not_rule) \
                       & product_mask(product_of(g["광고id"]))
                # 청크×방식 순위를 전부 모아 **한 번만** RRF (로컬과 같게)
                ranks = [r for q in qs for r in rankings(q, how, mask)]
                cand = rrf(*ranks, top=60 if use_rr else max(KL))
                if use_rr:
                    # **광고 전문을 통째로 넘기지 않는다.** 「광고 전문은
                    # 질의로 안 쓴다」(측정 0%)고 정해 놓고 여기서 어겨
                    # R@5 를 3분의 1로 떨어뜨렸다. 청크마다 따로 재정렬해
                    # 후보별 최고점만 취한다(한 대목만 맞아도 그 후보는
                    # 살아야 하므로 평균이 아니라 최댓값).
                    pairs = [[q, index_text(rows[i])[:600]] for i in cand for q in qs]
                    scores = RR.predict(pairs)
                    best, p = {}, 0
                    for i in cand:
                        for _ in qs:
                            best[i] = max(best.get(i, -1e9), scores[p]); p += 1
                    cand = sorted(cand, key=lambda i: -best[i])[:max(KL)]
                # **rank = 후보(규칙/조문) 순위, hop2 가 뱉은 행 개수가
                # 아니다.** 조 하나를 못 좁혀 항·호·목 여러 행을 통째로
                # 낸 규칙이 있으면, `hop2(cand)` 를 평탄화해 그 자리를
                # 그대로 순위로 쓰던 이전 방식은 뒤 규칙의 정답을 그만큼
                # 밀어낸다(로컬 실측: 이 버그 하나로 hybrid R@5 33%→7%로
                # 떨어졌었다). 후보 자체의 순위로 센다.
                if way == "2-hop":
                    pos = next((r for r, i in enumerate(cand[:max(KL)], 1)
                                if any(j in ans for j in hop2([i]))), None)
                else:
                    pos = next((r for r, i in enumerate(cand[:max(KL)], 1)
                                if i in ans), None)
                for k in KL:
                    if pos and pos <= k:
                        hit[k] += 1
            row = {"갈래": way, "검색": how, "리랭커": "O" if use_rr else "-",
                   "n": n, "초": round(time.time()-t0),
                   **{f"R@{k}": round(hit[k]/max(n,1)*100, 1) for k in KL}}
            RESULT.append(row)
            print(f"{way:6s} {how:7s} 리랭커{row['리랭커']} " +
                  " ".join(f"{row[f'R@{k}']:5.1f}%" for k in KL) +
                  f"  {row['초']:4d}초")
""")

add(MD, "## 9. 보고서")
add(PY, r"""
best = max(RESULT, key=lambda x: (x["R@5"], x["R@1"]))
lines = ["# 검색 최종 측정", "",
         f"정답 {len(gold)}건 (심의사례 · 정답 1~3행) · 색인 {len(rows):,} "
         f"(규칙 {n_rules:,})", "",
         f"**가장 나은 조합 — {best['갈래']} · {best['검색']} · "
         f"리랭커 {best['리랭커']} · R@5 {best['R@5']}%**", "",
         "| 갈래 | 검색 | 리랭커 | " + " | ".join(f"R@{k}" for k in KL) + " | 초 |",
         "|---|---|---|" + "---:|"*len(KL) + "---:|"]
for r in sorted(RESULT, key=lambda x: (-x["R@5"], -x["R@1"])):
    lines.append(f"| {r['갈래']} | {r['검색']} | {r['리랭커']} | "
                 + " | ".join(f"{r[f'R@{k}']}%" for k in KL) + f" | {r['초']} |")

lines += ["", "## 읽는 법", "",
          "- **정답이 광고당 1~3행뿐이다.** 「제16조 아무 조각」이 아니라 「제16조 [5 나]」 그 조각을 맞혀야 한다.",
          "  앞서 낸 R@10 85.7% 는 정답이 48~140행이던 때의 숫자라 못 쓴다.",
          f"- 표본이 {len(gold)}건이라 광고 한 건이 {100/len(gold):.1f}%p 를 움직인다. 방식 차이를 단정하지 말 것.",
          "- 보고 지표인 `EVIDENCE_PRECISION`(근거 매칭 적정성, 목표 85%)은 **정밀도**라 여기서 재는 회수와 방향이 반대다.",
          "  사람이 근거를 O/X 로 봐줘야 나온다.", "",
          "## 갈래 설명", "",
          "```",
          "직접    광고 청크 ──────────────→ 조문",
          "        광고 말투와 법률 말투가 달라 잘 안 걸린다",
          "",
          "2-hop   광고 청크 ──→ 규칙 ──→ 조문",
          "                   말투가 겹침   근거 링크(검색 아님)",
          "```"]

open("final_report.md", "w", encoding="utf-8").write(NL.join(lines))
print(NL.join(lines[:24]))
from google.colab import files
files.download("final_report.md")
""")


def main():
    nb = {"cells": [{"cell_type": k, "metadata": {},
                     **({"outputs": [], "execution_count": None} if k == PY else {}),
                     "source": t.splitlines(keepends=True)} for k, t in CELLS],
          "metadata": {"kernelspec": {"display_name": "Python 3", "name": "python3"},
                       "language_info": {"name": "python"},
                       "accelerator": "GPU", "colab": {"provenance": []}},
          "nbformat": 4, "nbformat_minor": 0}
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "final_colab.ipynb")
    json.dump(nb, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"셀 {len(CELLS)}개 → {out}")


if __name__ == "__main__":
    main()
