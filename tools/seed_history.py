# -*- coding: utf-8 -*-
"""
과거 버전(연혁)을 받아 DB에 실제 개정 이력을 만든다.

변경 감지 파이프라인은 '지금부터' 감시하므로, 수집을 시작한 뒤 개정이 없으면
변경 피드가 비어 있다. 법제처·금투협은 과거 개정본을 그대로 제공하므로,
[과거본 → 현재본] 순으로 적재하면 실제와 동일한 변경 이력이 생긴다.
diff 로직 검증과 화면 확인에 쓴다.

  python seed_history.py                # 연혁을 제공하는 전 타깃에 직전 버전 적재
  python seed_history.py "금융소비자 보호에 관한 법률"        # 특정 규정만
  python seed_history.py "금융소비자 보호에 관한 법률" 252409  # 특정 과거 버전 지정

연혁 제공 여부
  · 법률/시행령(law)  : 제공 (lawSearch target=eflaw)
  · 행정규칙(admrul)  : 미제공 — 검색이 현행만 돌려줌
  · 금투협(kofia)     : 제공 (lawHistoryList.do)
  · 여신협·은행연     : 미제공 — 현재 첨부파일만 게시됨
"""
import os
import sys

# 파이프라인 모듈은 src/ 에 있다. 이 스크립트는 한 단계 아래 폴더에서 직접 실행되므로
# import 경로에 src/ 를 먼저 넣어 준다.
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import os
import sys
import json
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

import db
import store
import law_scraper as L
import kofia_scraper as K

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "output")
SUPPORTED = ("law", "kofia")


# ── 연혁 조회 ───────────────────────────────────────────────────────────
def history_law(name):
    """[{MST, 시행일자, 공포일자, 공포번호, 제개정}] 최신순. 현행 포함."""
    url = (f"{L.BASE}/lawSearch.do?OC={L.OC}&target=eflaw&type=JSON"
           f"&query={urllib.parse.quote(name)}&display=50")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data = json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))
    items = data.get("LawSearch", {}).get("law", [])
    items = items if isinstance(items, list) else [items]
    key = name.replace(" ", "")
    out, seen = [], set()
    for it in items:
        if it.get("법령명한글", "").replace(" ", "") != key:
            continue
        mst = str(it.get("법령일련번호", ""))
        if not mst or mst in seen:
            continue
        seen.add(mst)
        out.append({"MST": mst, "시행일자": str(it.get("시행일자", "")),
                    "공포일자": str(it.get("공포일자", "")),
                    "공포번호": str(it.get("공포번호", "")),
                    "제개정": it.get("제개정구분명", "")})
    return sorted(out, key=lambda x: x["시행일자"], reverse=True)


def history_kofia(name):
    found = K._find_in_tree(name)
    if not found:
        return []
    _title, seq, _hseq = found
    return [{"seq": seq, "historySeq": h} for h in K.history(seq)]


# ── 과거본 레코드 만들기 ────────────────────────────────────────────────
def record_law(name, kind, mst):
    meta = {"name": name, "kind": kind, "MST": str(mst), "ID": "",
            "시행일자": "", "버전번호": ""}
    body = L.fetch_body(meta)
    info = body.get("기본정보") or body.get("행정규칙기본정보") or {}
    meta["시행일자"] = str(info.get("시행일자", ""))
    meta["버전번호"] = str(info.get("공포번호") or info.get("발령번호") or "")
    meta["ID"] = str(info.get("법령ID") or info.get("행정규칙ID") or "")
    공포일 = str(info.get("공포일자") or info.get("발령일자") or "")
    제개정 = L._content(info.get("제개정구분")) or info.get("제개정구분명", "")

    articles = (L.parse_articles_law(body) if kind == "law"
                else L.parse_articles_admrul(body))
    addenda, tables = L.parse_addenda(body), L.parse_tables(body)
    attachments = L.parse_attachments(body) if kind == "admrul" else []
    meta["content_hash"] = L._body_content_hash(body, kind)

    법종 = L._content(info.get("법종구분")) or info.get("행정규칙종류", "")
    dept = L._content(info.get("소관부처")) or info.get("소관부처명", "")
    header = (f"{name}\n[{법종}] 공포 {공포일 or '?'} · 시행 {meta['시행일자']} · "
              f"버전 {meta['버전번호']}" + (f" ({제개정})" if 제개정 else "") + f" · 소관 {dept}")
    plain = L.to_text(header, articles, addenda, tables, attachments)
    return {
        "법령명": name, "종류": kind, "법종구분": 법종, "소관부처": dept,
        "ID": meta["ID"], "MST": meta["MST"], "시행일자": meta["시행일자"],
        "공포일자": 공포일, "제개정구분": 제개정, "버전번호": meta["버전번호"],
        "버전키": L._version_key(meta), "공식버전키": L._official_version_key(meta),
        "본문해시": meta["content_hash"],
        "통계": {"조문수": len(articles), "부칙수": len(addenda),
                "별표수": len(tables), "첨부수": len(attachments)},
        "조문": articles, "부칙": addenda, "별표": tables, "첨부파일": attachments,
    }, plain


def previous_version(name, kind, current_key):
    """현재본 바로 직전 버전을 찾아 (레코드, 텍스트, 설명) 반환."""
    if kind == "law":
        hist = history_law(name)
        cur_mst = current_key.split("|")[0]
        older = [h for h in hist if h["MST"] != cur_mst]
        if not older:
            return None
        h = older[0]
        rec, plain = record_law(name, kind, h["MST"])
        return rec, plain, f"MST {h['MST']} · 공포 {h['공포일자']} · 시행 {h['시행일자']} ({h['제개정']})"
    if kind == "kofia":
        hist = history_kofia(name)
        cur_h = current_key.split("|")[-1]
        older = [h for h in hist if h["historySeq"] != cur_h]
        if not older:
            return None
        h = older[0]
        rec, plain = K.build_record(name, h["seq"], h["historySeq"])
        return rec, plain, f"개정본 {h['historySeq']} · 최근개정 {rec['최근개정일']}"
    return None


# ── 적재 ────────────────────────────────────────────────────────────────
def seed_one(con, run_id, name, kind, explicit_mst=None):
    safe = L._safe(name)
    cur_path = os.path.join(OUT_DIR, safe + ".json")
    if not os.path.exists(cur_path):
        print(f"  건너뜀 — 현재본 수집 결과가 없음")
        return False
    new_rec = json.load(open(cur_path, encoding="utf-8"))

    if explicit_mst:
        old_rec, old_plain = record_law(name, kind, explicit_mst)
        desc = f"MST {explicit_mst} · 공포 {old_rec['공포일자']} · 시행 {old_rec['시행일자']}"
        prev = (old_rec, old_plain, desc)
    else:
        prev = previous_version(name, kind, new_rec.get("공식버전키", ""))
    if not prev:
        print("  건너뜀 — 직전 버전을 찾지 못함(연혁 없음)")
        return False
    old_rec, old_plain, desc = prev
    if old_rec.get("공식버전키") == new_rec.get("공식버전키"):
        print("  건너뜀 — 직전 버전이 현재본과 같음")
        return False
    print(f"  직전 버전: {desc}")

    sid = db.source_id(con, kind)
    row = con.execute("SELECT regulation_id FROM regulations WHERE source_id=? AND name=?",
                      (sid, name)).fetchone()
    if row:   # 이 규정의 기존 적재분을 지우고 [과거 → 현재] 순서로 다시 넣는다
        rid = row["regulation_id"]
        con.execute("UPDATE regulations SET current_version_id=NULL WHERE regulation_id=?", (rid,))
        con.execute("DELETE FROM regulation_section_changes WHERE change_id IN"
                    " (SELECT change_id FROM regulation_changes WHERE regulation_id=?)", (rid,))
        con.execute("DELETE FROM regulation_changes WHERE regulation_id=?", (rid,))
        con.execute("DELETE FROM regulation_versions WHERE regulation_id=?", (rid,))

    # 과거본은 plain_text 를 파일에서 읽으므로 임시 파일로 넘겨준다
    tmp_name = safe + ".__old__"
    tmp = os.path.join(OUT_DIR, tmp_name + ".txt")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(old_plain)
    try:
        old_rec_named = dict(old_rec, 법령명=name)
        store.record_collection(con, run_id, old_rec_named, kind, tmp_name,
                                "신규", "과거 버전 적재", None)
    finally:
        os.remove(tmp)

    old_vid = store.current_version_id(con, name, kind)
    cid = store.record_collection(con, run_id, new_rec, kind, safe,
                                  "변경", "공식 버전키 변경", old_vid)
    if not cid:
        print("  변경이 감지되지 않음")
        return False
    ch = con.execute("SELECT summary FROM regulation_changes WHERE change_id=?",
                     (cid,)).fetchone()
    print(f"  → change #{cid} · {ch['summary']}")
    return True


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    targets = json.load(open(os.path.join(ROOT, "targets.json"), encoding="utf-8"))
    if args:
        targets = [t for t in targets if t["name"] == args[0]]
        if not targets:
            print(f"'{args[0]}' 는 targets.json 에 없습니다.")
            return 1
    explicit = args[1] if len(args) > 1 else None

    con = db.init()
    run_id = store.start_run(con, "history-seed", "manual")
    n = 0
    with con:
        for t in targets:
            print(f"[{t['kind']}] {t['name']}")
            if t["kind"] not in SUPPORTED:
                print("  건너뜀 — 이 소스는 과거 버전을 제공하지 않음")
                continue
            try:
                n += seed_one(con, run_id, t["name"], t["kind"], explicit)
            except Exception as e:
                print(f"  실패: {e}")
        store.finish_run(con, run_id, {"전체": len(targets), "변경": n, "신규": 0,
                                       "동일": len(targets) - n, "에러": 0}, {})
    con.close()
    print(f"\n실제 개정 이력 {n}건 생성")
    return 0


if __name__ == "__main__":
    sys.exit(main())
