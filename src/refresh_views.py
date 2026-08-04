# -*- coding: utf-8 -*-
"""수집 결과에서 파생되는 산출물을 **한 번에** 다시 만든다.

왜 따로 두는가 — 예전에는 check_updates.py 가 diff.html 만 다시 만들고 review.html 은
건드리지 않았다. 그래서 수집을 돌리면 변경 내역 화면은 최신인데 검수 뷰어는 옛날
숫자를 그대로 달고 있는 상태가 됐다(실측: 뷰어 탭 뱃지가 14 인데 DB 는 15). 파일이
완결형이라 열어 봐도 낡았다는 표시가 없어서, 사람이 우연히 숫자를 대조하기 전까지는
아무도 모른다.

**부분 성공을 성공으로 보고하지 않는다.** 하나라도 실패하면 무엇이 낡은 채로 남았는지
이름을 대고 알린다. "뭐는 되어 있고 뭐는 안 되어 있는" 상태가 조용히 유지되는 것이
이 모듈이 막으려는 것이다.

  python src/refresh_views.py            # 전부 다시 만든다
  python src/refresh_views.py --check    # 낡았는지만 본다(만들지 않음)
  python src/refresh_views.py --only diff
"""
import os
import sys
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db
from applog import get_logger

log = get_logger("refresh_views")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REVIEW_DIR = os.path.join(ROOT, "output", "_review")

# 이름 → (산출 파일, 만드는 함수 이름). 새 산출물이 생기면 여기에만 추가하면
# check_updates 든 수동 실행이든 같이 따라온다.
VIEWS = [
    ("diff",   "diff.html",   "build_diff_view"),
    ("review", "review.html", "build_review"),
]


def db_mtime():
    """DB 에 마지막으로 무언가 기록된 시각(epoch). 없으면 None."""
    try:
        con = db.connect()
        try:
            row = con.execute(
                "SELECT MAX(t) t FROM (SELECT MAX(created_at) t FROM regulation_changes"
                " UNION ALL SELECT MAX(finished_at) FROM collection_runs)").fetchone()
        finally:
            con.close()
        if not row or not row["t"]:
            return None
        # ISO 문자열 → epoch. 초 단위까지만 쓴다(파일 mtime 과 비교용).
        return time.mktime(time.strptime(row["t"][:19], "%Y-%m-%dT%H:%M:%S"))
    except Exception as e:
        log.warning(f"DB 시각을 읽지 못했습니다: {e}")
        return None


def stale(names=None):
    """DB 보다 낡은 산출물 이름 목록. 파일이 아예 없어도 낡은 것으로 본다."""
    ref = db_mtime()
    out = []
    for name, fname, _ in VIEWS:
        if names and name not in names:
            continue
        p = os.path.join(REVIEW_DIR, fname)
        if not os.path.exists(p):
            out.append((name, fname, "없음"))
        elif ref and os.path.getmtime(p) < ref - 1:      # 1초 여유(파일시스템 반올림)
            age = (ref - os.path.getmtime(p)) / 3600
            out.append((name, fname, f"{age:.1f}시간 낡음"))
    return out


def refresh(names=None, quiet=False):
    """산출물을 다시 만든다. (성공 목록, 실패 목록) 반환.

    실패해도 나머지는 계속 만든다 — 하나가 깨졌다고 전부 낡은 채로 두면 더 나쁘다.
    대신 무엇이 실패했는지 반드시 호출부로 돌려준다.
    """
    ok, bad = [], []
    for name, fname, mod in VIEWS:
        if names and name not in names:
            continue
        t0 = time.time()
        try:
            m = __import__(mod)
            m.build()
            ok.append(name)
            if not quiet:
                log.info(f"  ✓ {fname} ({time.time()-t0:.0f}초)")
        except Exception as e:
            bad.append((name, fname, str(e)[:120]))
            log.warning(f"  ✗ {fname} 생성 실패 — {str(e)[:120]}")
    if bad:
        # 부분 성공을 성공처럼 넘기지 않는다. 낡은 채로 남은 것을 이름으로 알린다.
        log.warning("⚠ 일부 화면이 낡은 채로 남았습니다: "
                    + ", ".join(f"{f}" for _, f, _ in bad)
                    + "  →  python src/refresh_views.py 로 다시 시도하세요")
    return ok, bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="낡았는지만 확인(생성 안 함)")
    ap.add_argument("--only", nargs="*", help=f"대상 지정: {[v[0] for v in VIEWS]}")
    a = ap.parse_args()

    st = stale(a.only)
    if a.check:
        if not st:
            log.info("모든 화면이 최신입니다.")
            return 0
        log.warning(f"낡은 화면 {len(st)}개:")
        for _, f, why in st:
            log.warning(f"  - {f} ({why})")
        return 1

    if not st:
        log.info("이미 최신입니다. 그래도 다시 만들려면 --only 로 지정하세요.")
        if not a.only:
            return 0
    log.info("화면 다시 만드는 중…")
    ok, bad = refresh(a.only)
    log.info(f"완료 — 성공 {len(ok)} · 실패 {len(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
