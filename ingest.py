# -*- coding: utf-8 -*-
"""
수집 결과(collect() 레코드) → DB 적재.

소스마다 레코드 모양이 달라서(법제처는 조>항>호>목, 금투협은 장/절/조, 여신협·은행연은
평문 텍스트) 여기서 공통 '섹션(section)' 단위로 정규화한 뒤 넣는다.
섹션 = 조문 1개 / 부칙 1개 / 별표 1개 — 조문 단위 diff와 조회의 기본 단위.
"""
import os
import re
import json
import hashlib

import db
from diff_report import split_articles

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "output")

_ARTNO = re.compile(r"제\s*\d+(?:-\d+)?조(?:의\s*\d+)?")
# 금투협 원문에 '조'가 빠진 제목이 일부 있다(예: "제7-33(채권거래전용시스템의 지원 범위)").
# 원문 오타지만 조번호는 유효하므로 키로 살려 쓴다.
_ARTNO_LOOSE = re.compile(r"제\s*\d+-\d+(?:의\s*\d+)?(?=\s*\()")


def _h(s):
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()


def _law_article_key(a, i):
    """법제처 법령: 조문번호(+가지번호) → '제12조의2'."""
    no = str(a.get("조문번호") or "").strip()
    branch = str(a.get("조문가지번호") or "").strip()
    if no:
        return f"제{no}조" + (f"의{branch}" if branch and branch not in ("0", "00") else "")
    m = _ARTNO.search(a.get("조문내용") or "")
    return m.group(0).replace(" ", "") if m else f"조문{i:04d}"


def _law_article_text(a):
    """조>항>호>목 계층을 들여쓰기 텍스트 한 덩어리로."""
    lines = []
    if a.get("조문내용"):
        lines.append(a["조문내용"])
    for h in a.get("항", []):
        if h.get("항내용"):
            lines.append("  " + h["항내용"])
        for ho in h.get("호", []):
            if ho.get("호내용"):
                lines.append("    " + ho["호내용"])
            for m in ho.get("목", []):
                lines.append("      " + m)
    return "\n".join(lines).strip()


def sections_from_record(record, kind):
    """레코드 → [{section_key, section_type, parent_key, sequence_no, title,
    content, content_hash, metadata}] (등장 순서)."""
    out = []
    seq = 0

    def add(key, stype, content, title=None, parent=None, meta=None):
        nonlocal seq
        content = (content or "").strip()
        if not content:
            return
        seq += 1
        # 같은 키가 두 번 나오면(삭제 조문 등) 접미로 구분해 UNIQUE 충돌 방지
        base, n = key, 2
        existing = {s["section_key"] for s in out}
        while key in existing:
            key = f"{base}#{n}"; n += 1
        out.append({
            "section_key": key, "section_type": stype, "parent_key": parent,
            "sequence_no": seq, "title": title, "content": content,
            "content_hash": _h(content), "metadata": json.dumps(meta or {}, ensure_ascii=False),
        })

    if kind in ("law", "admrul"):
        for i, a in enumerate(record.get("조문", []), 1):
            add(_law_article_key(a, i), "조문", _law_article_text(a),
                title=a.get("조문제목") or None)
        for i, ad in enumerate(record.get("부칙", []), 1):
            add(f"부칙{i}", "부칙", ad.get("내용"),
                title=f"부칙 {ad.get('공포일자','')} 제{ad.get('공포번호','')}호".strip(),
                meta={"공포일자": ad.get("공포일자"), "공포번호": ad.get("공포번호")})
        for t in record.get("별표", []):
            no = str(t.get("별표번호") or "").strip()
            branch = str(t.get("별표가지번호") or "").strip()
            key = f"[{t.get('구분') or '별표'}{no}" + (f"의{branch}" if branch and branch not in ("0", "00") else "") + "]"
            files = [f for f in (t.get("저장PDF"), t.get("저장HWP")) if f]
            body = t.get("내용") or ("(본문 텍스트 없음 · 원본 파일: "
                                   + (" / ".join(files) or "없음") + ")")
            add(key, "별표", body, title=t.get("제목"),
                meta={"원본파일": files,
                      "PDF파일명": t.get("PDF파일명"), "HWP파일명": t.get("HWP파일명")})

    elif kind == "kofia":
        for i, a in enumerate(record.get("조문", []), 1):
            t = a.get("조제목") or ""
            m = _ARTNO.search(t) or _ARTNO_LOOSE.search(t)
            # 위치 기반 키(조문0007)는 조문이 하나만 삽입돼도 뒤가 전부 밀려
            # 가짜 변경이 쏟아지므로, 조번호를 최대한 살려 안정적인 키를 만든다
            key = m.group(0).replace(" ", "") if m else f"조문{i:04d}"
            body = "\n".join(x for x in [a.get("조제목"), a.get("조내용")] if x)
            add(key, "조문", body, title=a.get("조제목"),
                meta={"장": a.get("장"), "절": a.get("절")})
        for i, ad in enumerate(record.get("부칙", []), 1):
            add(f"부칙{i}", "부칙", ad.get("내용"), title=ad.get("부칙명"))
        # 금투협 별표·별지는 본문이 아니라 HWP 첨부로만 제공된다.
        # 본문 텍스트가 없으므로 파일명을 내용으로 삼아 '무엇이 있었는지'를 남긴다.
        for t in record.get("별표", []):
            key = f"[{t.get('구분','별표')}{t.get('번호','')}]"
            body = (f"(첨부 파일: {t.get('파일명','')})"
                    + (" · 삭제됨" if t.get("삭제여부") else ""))
            add(key, "별표", body, title=t.get("파일명"),
                meta={"원본파일": [t.get("저장파일")] if t.get("저장파일") else [],
                      "링크": t.get("링크"), "삭제여부": bool(t.get("삭제여부"))})

    else:   # crefia / kfb : 원본이 평문 텍스트뿐 → 조문 헤더로 쪼갠다
        arts, order = split_articles(record.get("본문", ""))
        for key in order:
            body = "\n".join(arts[key]).strip()
            stype = "부칙" if key.startswith("부칙") else ("별표" if key.startswith("[별표") else
                                                       ("머리말" if key == "머리말" else "조문"))
            add(key, stype, body)

    return out


def _plain_text(record, name):
    """비교·검색용 전체 텍스트. 사람이 읽는 .txt 를 정본으로 쓴다."""
    p = os.path.join(OUT_DIR, name + ".txt")
    if os.path.exists(p):
        return open(p, encoding="utf-8").read()
    return record.get("본문", "")


def _artifacts(name):
    """다운로드해둔 원본 파일(별표 PDF/HWP, 협회 첨부) 목록."""
    d = os.path.join(OUT_DIR, "files", name)
    if not os.path.isdir(d):
        return []
    out = []
    for f in sorted(os.listdir(d)):
        p = os.path.join(d, f)
        if not os.path.isfile(p):
            continue
        with open(p, "rb") as fh:
            data = fh.read()
        out.append({
            "artifact_type": os.path.splitext(f)[1].lstrip(".").lower() or "bin",
            "file_name": f, "storage_path": os.path.relpath(p, ROOT),
            "file_hash": hashlib.sha256(data).hexdigest(), "file_size": len(data),
        })
    return out


def upsert_regulation(con, name, kind, external_id):
    sid = db.source_id(con, kind)
    con.execute(
        "INSERT INTO regulations (source_id, external_id, name, document_type)"
        " VALUES (?,?,?,?) ON CONFLICT(source_id, name) DO UPDATE SET"
        " external_id=COALESCE(excluded.external_id, regulations.external_id)",
        (sid, external_id, name, db.DOCUMENT_TYPE[kind]))
    return con.execute("SELECT regulation_id FROM regulations WHERE source_id=? AND name=?",
                       (sid, name)).fetchone()["regulation_id"]


def ingest_version(con, record, kind, safe_name):
    """레코드 1건 → regulation_versions + sections + artifacts 적재.
    (version_id, is_new) 반환. 이미 같은 버전이 있으면 is_new=False."""
    name = record.get("법령명") or safe_name
    external_id = str(record.get("ID") or record.get("seq") or record.get("게시물idx") or "")
    rid = upsert_regulation(con, name, kind, external_id)

    official = record.get("공식버전키") or record.get("버전키") or ""
    chash = record.get("본문해시") or record.get("sha256") or ""
    effective = record.get("시행일자") or record.get("최근개정일") or ""
    plain = _plain_text(record, safe_name)

    exist = con.execute(
        "SELECT version_id FROM regulation_versions WHERE regulation_id=?"
        " AND official_version_key=? AND content_hash=?", (rid, official, chash)).fetchone()
    if exist:
        return exist["version_id"], False

    # 공포일(관보 게재 = 실제로 바뀐 날)과 시행일(효력 발생일)은 다르다. 둘 다 저장한다.
    promulgated = record.get("공포일자") or ""
    cur = con.execute(
        "INSERT INTO regulation_versions (regulation_id, official_version_key, content_hash,"
        " promulgation_no, promulgated_at, effective_at, collected_at, raw_format, source_url,"
        " parsed_content, plain_text, is_current, validation_status)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,0,'pending')",
        (rid, official, chash, str(record.get("버전번호") or ""), promulgated, effective,
         db.now_iso(), "json" if kind in ("law", "admrul", "kofia") else "file",
         record.get("출처"), json.dumps(record, ensure_ascii=False), plain))
    vid = cur.lastrowid

    for s in sections_from_record(record, kind):
        con.execute(
            "INSERT INTO regulation_sections (version_id, section_key, section_type,"
            " parent_key, sequence_no, title, content, content_hash, metadata)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (vid, s["section_key"], s["section_type"], s["parent_key"], s["sequence_no"],
             s["title"], s["content"], s["content_hash"], s["metadata"]))

    for a in _artifacts(safe_name):
        con.execute(
            "INSERT INTO regulation_artifacts (version_id, artifact_type, file_name,"
            " storage_path, file_hash, file_size) VALUES (?,?,?,?,?,?)",
            (vid, a["artifact_type"], a["file_name"], a["storage_path"],
             a["file_hash"], a["file_size"]))

    # 현재본 전환 (부분 유니크 인덱스 때문에 기존 것을 먼저 내려야 한다)
    con.execute("UPDATE regulation_versions SET is_current=0 WHERE regulation_id=?", (rid,))
    con.execute("UPDATE regulation_versions SET is_current=1 WHERE version_id=?", (vid,))
    con.execute("UPDATE regulations SET current_version_id=? WHERE regulation_id=?", (vid, rid))
    return vid, True


def backfill(verbose=True):
    """이미 수집해둔 output/<name>.json 들을 DB 로 적재(최초 1회용).
    실행 이력·변경 피드·알림까지 정상 실행과 동일한 경로로 남긴다."""
    import law_scraper
    import store   # store 가 ingest 를 쓰므로 순환 import 회피용 지역 import

    con = db.init()
    targets = json.load(open(os.path.join(ROOT, "targets.json"), encoding="utf-8"))
    run_id = store.start_run(con, "backfill", "manual")
    n_new = 0
    with con:
        for t in targets:
            safe = law_scraper._safe(t["name"])
            p = os.path.join(OUT_DIR, safe + ".json")
            if not os.path.exists(p):
                if verbose:
                    print(f"  건너뜀(수집 결과 없음): {t['name']}")
                continue
            record = json.load(open(p, encoding="utf-8"))
            old_vid = store.current_version_id(con, t["name"], t["kind"])
            cid = store.record_collection(con, run_id, record, t["kind"], safe,
                                          "신규" if old_vid is None else "변경",
                                          "최초 적재" if old_vid is None else "재적재", old_vid)
            vid = store.current_version_id(con, t["name"], t["kind"])
            n_new += bool(cid)
            if verbose:
                cnt = con.execute("SELECT COUNT(*) c FROM regulation_sections WHERE version_id=?",
                                  (vid,)).fetchone()["c"]
                print(f"  [{'신규' if cid else '기존'}] {t['name']} — version {vid}, 섹션 {cnt}")
        store.finish_run(con, run_id, {"전체": len(targets), "신규": n_new,
                                       "변경": 0, "동일": len(targets) - n_new, "에러": 0}, {})
    return n_new


def record_section_diff(con, change_id, old_vid, new_vid):
    """두 버전의 섹션을 비교해 regulation_section_changes 적재.
    (added, removed, modified) 개수 반환."""
    def load(vid):
        if not vid:
            return {}
        return {r["section_key"]: r["content"] for r in con.execute(
            "SELECT section_key, content FROM regulation_sections WHERE version_id=?"
            " ORDER BY sequence_no", (vid,))}

    old, new = load(old_vid), load(new_vid)
    added = [k for k in new if k not in old]
    removed = [k for k in old if k not in new]
    modified = [k for k in new if k in old and old[k] != new[k]]

    import difflib
    for k in added:
        con.execute("INSERT INTO regulation_section_changes (change_id, section_key,"
                    " change_type, old_content, new_content) VALUES (?,?,'added',NULL,?)",
                    (change_id, k, new[k]))
    for k in removed:
        con.execute("INSERT INTO regulation_section_changes (change_id, section_key,"
                    " change_type, old_content, new_content) VALUES (?,?,'removed',?,NULL)",
                    (change_id, k, old[k]))
    for k in modified:
        d = "\n".join(l for l in difflib.unified_diff(
            old[k].splitlines(), new[k].splitlines(), lineterm="", n=1)
            if not l.startswith(("+++", "---")))
        con.execute("INSERT INTO regulation_section_changes (change_id, section_key,"
                    " change_type, old_content, new_content, diff) VALUES (?,?,'modified',?,?,?)",
                    (change_id, k, old[k], new[k], d))
    return len(added), len(removed), len(modified)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print("기존 수집 결과 → DB 적재")
    n = backfill()
    print(f"완료: 신규 버전 {n}건")
