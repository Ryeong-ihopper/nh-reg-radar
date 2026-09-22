# -*- coding: utf-8 -*-
"""**사내 규제목록의 점검항목을 판정 대상으로 만든다** — 규칙 단위에서 항목 단위로.

종전에는 규칙 하나하나를 판정 단위로 썼다. 그래서 결함 하나에 지적이 다섯 건씩
나왔다 — 001_대출성 「중도상환해약금 누락」에 R-0705·R-0893·R-0946·R-1156·
R-1317 이 각각 발행됐다. 심의역은 그걸 한 건으로 읽는다.

사내 규제목록(`NH_광고심의_에이전트_규제목록_v2.xlsx`)은 규칙 763건을 **점검항목
256개**로 이미 묶어 두었고, 우리가 코드로 만들던 것을 칸으로 갖고 있다.

    판정모드   체크리스트(표시의무 전수 순회) / 자유탐지(금지·양식 스캔)
    판정유형   확정 / 보조(사람 확인) / 레이아웃필요 / 절차확인
    입력요건   광고물 / 광고물(원본형식) / 광고물+랜딩캡처
    필요매체   텍스트 / 레이아웃
    적용상품   예금성 · 대출성 · 투자성 · 전체       세부상품 2차 필터
    위반등급   반려 / 보완요청 / 주의

판정 재료는 이 파일의 `실행_점검항목`과 `항목_규칙매핑`만 사용한다. 외부 규칙
원장이나 원문 파일을 추가로 읽지 않는다. 판정보류 항목(H-xxx)은 광고물 밖 기록이
있어야 하는 것이라 판정하지 않고 목록에만 남긴다.

  python rag/build_items.py            # 미리보기
  python rag/build_items.py --write    # output/_rag/items_*.json
"""
import os
import io
import re
import sys
import json
import hashlib
import argparse
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG = os.path.join(ROOT, "output", "_rag")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# **판정 규정의 단일 입력(2026-08-31).** 다른 규칙 파일과 결합하지 않는다.
#   표준_예시문구    템플릿에 실제로 적혀 있는 문구 — 「이렇게 쓰면 충족」
#   표준_기재요령    「볼드체 또는 ※ 로 차별화」 같은 작성 지침
#   템플릿_필수여부  O=반드시 / △=조건부  ← 미해당이 성립하는지를 가른다
#   템플릿_섹션      어느 광고 유형의 어느 자리인가
AGENT = os.environ.get("NH_REGULATION_V2_PATH")


def set_agent_path(path):
    """Set the single regulation-v2 input for the current process.

    Callers running on another PC/DAP/container must inject this path via
    ``--regulation`` or ``NH_REGULATION_V2_PATH``.  The file contents are still
    pinned by SHA-256 in every generated manifest.
    """
    global AGENT
    resolved = os.path.abspath(os.path.expanduser(os.fspath(path)))
    if not os.path.isfile(resolved):
        raise FileNotFoundError(f"규제목록 v2 파일이 없음: {resolved}")
    AGENT = resolved
    return AGENT

# 구분 → 판정 방향. 우리 상태 코드와 잇는다.
KIND = {"표시의무": "PRESENCE", "금지": "PROHIBIT", "양식·절차": "STYLE"}
# 적용상품 → 우리 상품군 이름
PROD = {"예금성": "예금성", "대출성": "대출성", "투자성": "투자성", "전체": None}


def S(v):
    return str(v).strip() if v is not None else ""


def _uniq(values):
    """빈칸을 버리고 입력 순서를 유지해 중복 제거."""
    return list(dict.fromkeys(v for v in values if v))


def _tpl(r, ix, col, dedup=False):
    """템플릿 열 하나. 없거나 「-」면 빈 문자열.

    **같은 문구가 19번씩 들어 있다(2026-08-25).** 「[T-027] - 상품설명서 및
    약관을 반드시 읽어보시기 바랍니다; [T-037] - (같은 문장); [T-047] - …」
    처럼 템플릿 자리마다 한 줄씩 적혀 있어, 조각 19개가 전부 같은 문장인
    항목도 있다(C-050). 판정에 넘길 때는 뜻이 같은 것을 한 번만 넣는다 —
    표준예시·기재요령을 합쳐 23,010자에서 8,736자로 줄어든다(62%).
    자리표(T-번호)는 판정에 쓸 데가 없어 함께 뗀다.
    """
    if col not in ix:
        return ""
    v = S(r[ix[col]])
    if v == "-":
        return ""
    if not dedup:
        return v
    seen = []
    for part in re.split(r";\s*(?=\[T-\d+\])", v):
        t = re.sub(r"^\[T-\d+\]\s*-?\s*", "", part).strip()
        if t and t != "-" and t not in seen:
            seen.append(t)
    return "; ".join(seen)


def sheet(path, name):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[name]
    it = ws.iter_rows(values_only=True)
    h = [S(x) for x in next(it)]
    ix = {x: i for i, x in enumerate(h) if x}
    return [r for r in it if r and any(x is not None for x in r)], ix


def build():
    rows, ix = sheet(AGENT, "실행_점검항목")
    maps, mx = sheet(AGENT, "항목_규칙매핑")
    by_item = collections.defaultdict(list)
    for r in maps:
        it_ = S(r[mx["항목ID"]])
        rid = S(r[mx["규칙ID"]])
        if it_ and rid:
            by_item[it_].append({
                "id": rid,
                "대표": S(r[mx["대표여부"]]) == "대표",
                "요약": S(r[mx["규칙 요약"]]),
                "카테고리": S(r[mx["카테고리"]]),
                "출처매뉴얼": S(r[mx["출처 매뉴얼"]]),
                "근거상세": S(r[mx["근거 상세"]]),
            })

    items = []
    for r in rows:
        iid = S(r[ix["항목ID"]])
        if not iid:
            continue
        prods = [x.strip() for x in S(r[ix["적용상품"]]).split(",") if x.strip()]
        rules = by_item.get(iid, [])
        rep = next((x["id"] for x in rules if x["대표"]), None) or S(
            r[ix.get("대표규칙ID", 0)] if "대표규칙ID" in ix else "")
        items.append({
            "id": iid,
            "title": S(r[ix["약칭"]]),
            # 점검문구는 심의역이 실제로 던지는 물음이라 판정에 가장 가깝다
            "question": S(r[ix["점검문구"]]),
            # 판정기준은 「충족/위반」을 구체적으로 적어 둔 것 — LLM 에 그대로
            "criterion": S(r[ix["판정기준"]]),
            "category": KIND.get(S(r[ix["구분"]]), "PRESENCE"),
            "구분": S(r[ix["구분"]]),
            # 체크리스트=전수 순회(미기재) / 자유탐지=스캔(오기재)
            "판정모드": S(r[ix["판정모드"]]),
            # 확정=단독 판정 / 보조=사람 확인 / 레이아웃필요·절차확인=보류
            "판정유형": S(r[ix["판정유형"]]),
            "입력요건": S(r[ix["입력요건"]]),
            "필요매체": S(r[ix["필요매체"]]),
            "적용상품": prods,
            "세부상품": S(r[ix.get("세부상품", 0)]) if "세부상품" in ix else "",
            "위반등급": S(r[ix["위반등급"]]),
            "근거법령": S(r[ix["근거법령"]]),
            "비고": S(r[ix.get("비고", 0)]) if "비고" in ix else "",
            "규칙관계": ([{
                "relation_type": S(r[ix["관계유형"]]),
                "target_item_ids": [
                    value.strip() for value in re.split(r"[,;]", S(r[ix["관계대상ID"]]))
                    if value.strip()
                ],
                "join": (S(r[ix.get("관계결합", 0)]) if "관계결합" in ix else "ANY") or "ANY",
                "description": S(r[ix.get("관계설명", 0)]) if "관계설명" in ix else "",
                "source": "실행_점검항목",
            }] if "관계유형" in ix and S(r[ix["관계유형"]]) else []),
            "대표규칙": rep,
            # 아래 값도 전부 같은 v2 파일의 `항목_규칙매핑`에서 온다.
            "근거규칙": [x["id"] for x in rules],
            "규칙근거": rules,
            "규칙요약": _uniq(x["요약"] for x in rules),
            "규칙카테고리": _uniq(x["카테고리"] for x in rules),
            "출처매뉴얼": _uniq(x["출처매뉴얼"] for x in rules),
            "근거상세": _uniq(x["근거상세"] for x in rules),
            # ── 광고 템플릿에서 온 것(v2) ────────────────────────────
            # 「[T-062] - [방식 ①] 기본금리 연 0.00%(0000.00.00. 기준, 세전)」
            # 처럼 실제 문구가 들어 있다. 0 은 자리를 메우는 자리표다.
            "표준예시": _tpl(r, ix, "표준_예시문구", dedup=True),
            "기재요령": _tpl(r, ix, "표준_기재요령", dedup=True),
            "템플릿필수": _tpl(r, ix, "템플릿_필수여부"),
            "템플릿섹션": _tpl(r, ix, "템플릿_섹션"),
            # 템플릿 필수여부로 「무조건 적용」을 추론하지 않는다. 템플릿은
            # 출처·허용 예시이고 적용 조건은 점검문구·판정기준에서 만든다.
        })

    known_item_ids = {item["id"] for item in items}
    for item in items:
        for relation in item["규칙관계"]:
            if relation["relation_type"] not in {"SATISFIED_IF"}:
                raise ValueError(f"{item['id']}: 지원하지 않는 관계유형 {relation['relation_type']}")
            if relation["join"] not in {"ANY", "ALL"}:
                raise ValueError(f"{item['id']}: 관계결합은 ANY 또는 ALL이어야 함")
            if not relation["target_item_ids"]:
                raise ValueError(f"{item['id']}: 관계대상ID가 비어 있음")
            invalid = [target for target in relation["target_item_ids"]
                       if target not in known_item_ids or target == item["id"]]
            if invalid:
                raise ValueError(f"{item['id']}: 잘못된 관계대상ID {invalid}")

    hold, hx = sheet(AGENT, "판정보류_항목")
    holds = [{
        "id": S(r[hx["항목ID"]]),
        "question": S(r[hx["점검문구"]]),
        "보류사유": S(r[hx["보류사유"]]),
        "적용상품": [x.strip() for x in S(r[hx["적용상품"]]).split(",") if x.strip()],
        "근거법령": S(r[hx["근거법령"]]),
    } for r in hold if S(r[hx["항목ID"]])]
    return items, holds


def for_product(items, prod):
    """이 상품군 광고에 로드할 항목. 「전체」는 다 로드한다."""
    out = []
    for x in items:
        p = x["적용상품"]
        if not p or "전체" in p or prod in p:
            out.append(x)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument(
        "--regulation",
        default=AGENT,
        required=AGENT is None,
        help="규제목록 v2 경로 (또는 NH_REGULATION_V2_PATH)",
    )
    a = ap.parse_args()
    set_agent_path(a.regulation)
    items, holds = build()

    print(f"점검항목 {len(items)}개 · 판정보류 항목 {len(holds)}개")
    for col in ("구분", "판정모드", "판정유형", "입력요건", "필요매체", "위반등급"):
        c = collections.Counter(x[col] for x in items)
        print(f"   {col:6s} {dict(c.most_common())}")
    n = sum(len(x["근거규칙"]) for x in items)
    print(f"   v2 항목↔규칙 연결 {n}건 · 근거상세 "
          f"{sum(1 for x in items if x['근거상세'])}항목")
    print()
    for prod in ("예금성", "대출성", "투자성"):
        sub = for_product(items, prod)
        c = collections.Counter(x["판정유형"] for x in sub)
        print(f"   {prod} 광고에 로드할 항목 {len(sub):3d}개  {dict(c)}")

    if a.write:
        with open(AGENT, "rb") as source_file:
            source_sha256 = hashlib.sha256(source_file.read()).hexdigest()
        for prod in ("예금성", "대출성", "투자성"):
            sub = for_product(items, prod)
            p = os.path.join(RAG, f"items_{prod[:2]}.json")
            json.dump({
                "_설명": f"{prod} 광고 판정 점검항목. 사내 규제목록 v2에서 생성.",
                "_생성": "python rag/build_items.py --write",
                "_규제목록": {
                    "파일": os.path.basename(AGENT),
                    "sha256": source_sha256,
                    "점검항목시트": "실행_점검항목",
                    "규칙매핑시트": "항목_규칙매핑",
                },
                "_템플릿정책": (
                    "표준예시·기재요령·템플릿필수·템플릿섹션은 출처/보조자료다. "
                    "적용조건이나 위반조건으로 직접 사용하지 않는다."
                ),
                "_입력정책": "판정 재료는 규제목록 v2 한 파일만 사용한다.",
                "items": sub, "보류": holds,
            }, io.open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"저장: {p} ({len(sub)}개)")


if __name__ == "__main__":
    main()
