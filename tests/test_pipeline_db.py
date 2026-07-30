# -*- coding: utf-8 -*-
"""
DB 파이프라인 변경 경로 테스트 (네트워크 없이).

실제 수집 결과를 복사해 조문을 인위적으로 신설/삭제/수정한 '가짜 새 버전'을 만들고,
임시 DB 에 적재 → 변경 감지 → 섹션 diff → 알림까지 이어지는지 검증한다.
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
import shutil
import tempfile

sys.stdout.reconfigure(encoding="utf-8")

import db
import ingest
import store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "output", "금융소비자 보호에 관한 법률.json")


def main():
    tmpdir = tempfile.mkdtemp(prefix="regtest_")
    tmpdb = os.path.join(tmpdir, "test.db")
    ok = True
    try:
        con = db.init(tmpdb)
        base = json.load(open(SRC, encoding="utf-8"))
        name, kind, safe = base["법령명"], "law", "금융소비자 보호에 관한 법률"

        # ── 1차: 최초 수집 ──────────────────────────────────────────────
        run1 = store.start_run(con, "normal", "test")
        with con:
            cid = store.record_collection(con, run1, base, kind, safe, "신규", "최초 수집", None)
        v1 = store.current_version_id(con, name, kind)
        n1 = con.execute("SELECT COUNT(*) c FROM regulation_sections WHERE version_id=?",
                         (v1,)).fetchone()["c"]
        print(f"1차 적재: version {v1}, 섹션 {n1}, change_id={cid}")
        # 최초 수집도 변경 피드에는 뜨지만, 전 조문을 '신설'로 쏟아내면 안 된다
        assert cid, "최초 수집이 변경 피드에 기록되지 않음"
        n_sc = con.execute("SELECT COUNT(*) c FROM regulation_section_changes WHERE change_id=?",
                           (cid,)).fetchone()["c"]
        assert n_sc == 0, f"최초 수집인데 섹션 변경이 {n_sc}건 생성됨(노이즈)"

        # ── 2차: 조문 하나 수정 + 하나 삭제 + 하나 신설 ─────────────────
        new = json.loads(json.dumps(base, ensure_ascii=False))
        new["조문"][0]["조문내용"] = base["조문"][0]["조문내용"] + " <테스트 개정 문구 추가>"
        removed_key = ingest._law_article_key(new["조문"][5], 6)
        del new["조문"][5]
        new["조문"].append({"조문번호": "999", "조문가지번호": "", "조문제목": "테스트신설",
                            "조문내용": "제999조(테스트신설) 테스트용으로 새로 만든 조문이다.",
                            "항": []})
        new["본문해시"] = "테스트해시_v2"
        new["공식버전키"] = base.get("공식버전키", "") + "|v2"

        run2 = store.start_run(con, "normal", "test")
        old_vid = store.current_version_id(con, name, kind)
        with con:
            cid2 = store.record_collection(con, run2, new, kind, safe, "변경",
                                           "공식 버전키 변경", old_vid)
        print(f"2차 적재: change_id={cid2}")
        assert cid2, "변경인데 change 가 기록되지 않음"

        ch = con.execute("SELECT * FROM regulation_changes WHERE change_id=?", (cid2,)).fetchone()
        print(f"  변경 요약: {ch['summary']} (사유: {ch['change_reason']})")
        assert ch["added_section_count"] == 1, f"신설 1 기대, 실제 {ch['added_section_count']}"
        assert ch["removed_section_count"] == 1, f"삭제 1 기대, 실제 {ch['removed_section_count']}"
        assert ch["changed_section_count"] == 1, f"변경 1 기대, 실제 {ch['changed_section_count']}"

        secs = {r["change_type"]: r for r in con.execute(
            "SELECT * FROM regulation_section_changes WHERE change_id=?", (cid2,))}
        print(f"  신설: {secs['added']['section_key']} / 삭제: {secs['removed']['section_key']}"
              f" / 수정: {secs['modified']['section_key']}")
        assert secs["added"]["section_key"] == "제999조"
        assert secs["removed"]["section_key"] == removed_key
        assert "<테스트 개정 문구 추가>" in (secs["modified"]["diff"] or "")

        # ── 현재본 전환 확인 ────────────────────────────────────────────
        cur_v = store.current_version_id(con, name, kind)
        assert cur_v != old_vid, "현재본이 새 버전으로 전환되지 않음"
        n_cur = con.execute("SELECT COUNT(*) c FROM regulation_versions WHERE regulation_id="
                            "(SELECT regulation_id FROM regulation_versions WHERE version_id=?)"
                            " AND is_current=1", (cur_v,)).fetchone()["c"]
        assert n_cur == 1, f"현재본이 {n_cur}개 (1개여야 함)"
        print(f"  현재본 전환: v{old_vid} → v{cur_v} (is_current=1 인 버전 {n_cur}개)")

        # ── 알림 생성 확인 ──────────────────────────────────────────────
        notis = con.execute(
            "SELECT n.*, p.name pname FROM notifications n"
            " JOIN watch_profiles p USING(profile_id) WHERE change_id=?", (cid2,)).fetchall()
        print(f"  알림 {len(notis)}건: " + ", ".join(
            f"[{n['pname']}] {n['title']} — {n['body']} (읽음={n['is_read']})" for n in notis))
        assert notis, "알림이 생성되지 않음"
        assert notis[0]["is_read"] == 0

        # ── 과거 버전 보존 확인 ─────────────────────────────────────────
        vers = con.execute(
            "SELECT version_id, is_current FROM regulation_versions ORDER BY version_id").fetchall()
        print(f"  보관된 버전: {[(v['version_id'], v['is_current']) for v in vers]}")
        assert len(vers) == 2, "과거 버전이 사라짐 (이력 보존 실패)"

        store.finish_run(con, run2, {"전체": 1, "변경": 1, "신규": 0, "동일": 0, "에러": 0}, {})
        con.commit()
        con.close()
        print("\n전부 통과")
    except AssertionError as e:
        ok = False
        print(f"\n실패: {e}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
