# -*- coding: utf-8 -*-
"""
규정 변경 감지 엔진 (수동 체크 스크립트)  ── 공통 엔진

동작:
  1) 기본 실행은 공식 버전(법제처·금투협) 또는 파일 해시(여신협·은행연) 확인
     --deep 실행은 법제처·금투협의 본문 구조 해시도 추가 확인
  2) state.json(직전 상태)과 비교 → 신규 / 변경 / 동일 판정
  3) 변경(또는 신규)인 것만:
       - 기존 output 을 output/_versions/<법령명>/<이전버전>/ 로 백업
       - 본문·파일 전체 재수집 (law_scraper.collect)
       - state.json 갱신
  4) 변경 리포트를 output/_reports/ 에 저장하고 요약 출력

  5) 수집 결과·변경 내역·알림을 SQLite(output/regulations.db)에 적재
     (DB가 없거나 실패해도 파일 기반 산출물은 그대로 생성된다)

사용:
  python check_updates.py           # 감지 + 변경분 재수집 + DB 적재
  python check_updates.py --dry     # 감지만 (재수집·백업·DB 적재 안 함)
  python check_updates.py --deep    # 법제처·금투협 본문 구조 해시까지 정밀 검사
  python check_updates.py --no-db   # DB 적재 없이 파일 산출물만
  python check_updates.py --cron    # 실행 이력에 trigger='cron' 으로 기록
  python check_updates.py 은행       # 이름에 '은행'이 들어간 대상만 (실패분 재시도용)

안전장치:
  · 같은 시각 중복 실행 방지(.run.lock) — state.json/DB 동시 쓰기 사고를 막는다
  · state.json 은 임시파일→교체 방식으로 저장하고 직전본을 .bak 으로 남긴다
  · 조회 실패는 리포트뿐 아니라 **알림으로도** 남긴다(놓치면 그 주기 개정을 통째로 놓침)
"""
import os
import sys
import json
import time
import shutil
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")  # 콘솔 한글 깨짐 방지 (제자리 변경)

import law_scraper as lawgo       # 법제처 어댑터 (법령/행정규칙)
import kofia_scraper as kofia     # 금융투자협회 어댑터
import crefia_scraper as crefia   # 여신금융협회 어댑터
import kfb_scraper as kfb         # 전국은행연합회 어댑터
import gov_scraper as gov         # 정부기관 게시판 어댑터 (금융위·금감원)
import diff_report                # 변경 시 조문 단위 diff
import db                         # SQLite 저장소
from applog import get_logger
import store                      # 실행 이력·변경·알림 적재

log = get_logger("check")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "output")
STATE_PATH = os.path.join(ROOT, "state.json")
VERSIONS_DIR = os.path.join(OUT_DIR, "_versions")
REPORTS_DIR = os.path.join(OUT_DIR, "_reports")

# 소스별 어댑터. 협회 어댑터는 여기 추가하면 됨.
#   current_meta(name, kind) -> {name, kind, MST, ID, 시행일자, 버전번호} | None
#   collect(name, kind)      -> 수집 결과 저장
#   version_key(meta)        -> 변경 감지용 문자열 키
ADAPTERS = {
    "law":    lawgo,
    "admrul": lawgo,
    "kofia":  kofia,
    "crefia": crefia,
    "kfb":    kfb,
    "fsc":    gov,     # 금융위 정책마당
    "fss":    gov,     # 금감원 보도자료
}


def _adapter(kind):
    ad = ADAPTERS.get(kind)
    if ad is None:
        raise ValueError(f"'{kind}' 어댑터가 없습니다. ADAPTERS 에 등록하세요.")
    return ad


def load_targets():
    return json.load(open(os.path.join(ROOT, "targets.json"), encoding="utf-8"))


def load_state():
    if os.path.exists(STATE_PATH):
        try:
            return json.load(open(STATE_PATH, encoding="utf-8"))
        except (ValueError, OSError) as e:
            # state.json 이 깨지면 전 규정이 '신규'로 잡혀 전부 재수집된다.
            # 직전 백업이 있으면 그걸로 살린다.
            bak = STATE_PATH + ".bak"
            if os.path.exists(bak):
                log.warning(f"state.json 손상({e}) → 직전 백업으로 복구")
                shutil.copy2(bak, STATE_PATH)
                return json.load(open(STATE_PATH, encoding="utf-8"))
            log.warning(f"state.json 손상({e}) · 백업 없음 → 전부 신규로 처리됨")
    return {}


def save_state(state):
    """임시 파일에 먼저 쓰고 교체한다.
    바로 덮어쓰면 저장 중 중단됐을 때 파일이 깨져 전 규정이 재수집된다."""
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    if os.path.exists(STATE_PATH):
        shutil.copy2(STATE_PATH, STATE_PATH + ".bak")
    os.replace(tmp, STATE_PATH)


class _RunLock:
    """같은 시각에 두 번 돌면 state.json·DB 를 서로 덮어쓴다.
    스케줄러 실행 중 수동 실행/API 트리거가 겹치는 것을 막는다."""

    def __init__(self):
        self.path = os.path.join(ROOT, ".run.lock")
        self.fh = None

    def __enter__(self):
        # 죽은 프로세스가 남긴 잠금은 무시(30분 넘은 것)
        if os.path.exists(self.path):
            age = time.time() - os.path.getmtime(self.path)
            if age > 1800:
                os.remove(self.path)
        try:
            self.fh = open(self.path, "x")
        except FileExistsError:
            raise RuntimeError(
                "이미 다른 실행이 진행 중입니다. 끝난 뒤 다시 시도하세요 "
                f"(강제로 풀려면 {os.path.basename(self.path)} 삭제)")
        self.fh.write(f"{os.getpid()} {datetime.now().isoformat()}\n")
        self.fh.flush()
        return self

    def __exit__(self, *exc):
        if self.fh:
            self.fh.close()
        if os.path.exists(self.path):
            os.remove(self.path)


def backup_existing(name, old_version):
    """기존 output/<name>.* 과 파일 폴더를 버전 폴더로 이동(백업)."""
    tag = lawgo._safe(old_version) or "unknown"
    dest = os.path.join(VERSIONS_DIR, lawgo._safe(name), tag)
    os.makedirs(dest, exist_ok=True)
    moved = []
    for ext in (".json", ".txt"):
        src = os.path.join(OUT_DIR, lawgo._safe(name) + ext)
        if os.path.exists(src):
            shutil.move(src, os.path.join(dest, os.path.basename(src)))
            moved.append(os.path.basename(src))
    fdir = os.path.join(OUT_DIR, "files", lawgo._safe(name))
    if os.path.isdir(fdir):
        shutil.move(fdir, os.path.join(dest, "files"))
        moved.append("files/")
    return dest, moved


def _write_latest_markdown(report):
    summary = report["요약"]
    lines = [
        "# 규정 변경 감지 최신 결과", "",
        f"- 실행시각: {report['실행시각']}",
        f"- 실행모드: {'dry-run' if report['dry_run'] else '정상 실행'}",
        f"- 전체 {summary['전체']} · 동일 {summary['동일']} · 신규 {summary['신규']} · "
        f"변경 {summary['변경']} · 오류 {summary['에러']} · 검색실패 {summary['검색실패']}",
        "",
        "| 규정 | 종류 | 상태 | 시행일자 | 버전 | 변경 사유 |",
        "|---|---|---:|---:|---:|---|",
    ]
    for row in report["상세"]:
        lines.append(
            f"| {row['법령명']} | {row.get('종류', '-')} | {row['상태']} | "
            f"{row.get('시행일자', '-')} | {row.get('버전번호', '-')} | "
            f"{row.get('변경사유', row.get('메시지', ''))} |"
        )
    with open(os.path.join(REPORTS_DIR, "latest_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def run(dry=False, deep=False, use_db=True, trigger="manual", only=None):
    targets = load_targets()
    if only:   # 실패한 것만 다시 돌릴 때 (전체 재실행은 외부 사이트에 부담)
        keys = [o.replace(" ", "") for o in only]
        targets = [t for t in targets
                   if any(k in t["name"].replace(" ", "") for k in keys)]
        if not targets:
            log.info(f"'{', '.join(only)}' 에 해당하는 대상이 targets.json 에 없습니다.")
            return
    state = load_state()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    changes = []   # 리포트용

    # DB는 있으면 쓰고, 없거나 실패하면 파일 기반으로 계속 진행한다
    con = run_id = None
    if use_db and not dry:
        try:
            con = db.init()
            run_id = store.start_run(con, "deep" if deep else "normal", trigger)
            con.commit()
        except Exception as e:
            log.warning(f"DB 초기화 실패 — 파일 기반으로만 진행합니다: {e}")
            con = None

    log.info(f"규정 변경 감지  ({now}){'  [DRY-RUN]' if dry else ''}"
          f"{f'  [run #{run_id}]' if run_id else ''}")
    log.info("=" * 60)

    for t in targets:
        name, kind = t["name"], t["kind"]
        ad = _adapter(kind)
        try:
            if kind in ("law", "admrul", "kofia"):
                meta = ad.current_meta(name, kind, deep=deep)
            else:
                meta = ad.current_meta(name, kind)
        except Exception as e:
            log.error(f"{name}: {e}")
            changes.append({"법령명": name, "종류": kind, "상태": "에러",
                            "변경사유": "조회 오류", "메시지": str(e)})
            continue
        if not meta:
            log.info(f"[없음] {name} — 검색 결과 없음")
            changes.append({"법령명": name, "종류": kind, "상태": "검색실패",
                            "변경사유": "공식 소스 검색 결과 없음"})
            continue

        new_key = ad._version_key(meta)
        official_key = (ad._official_version_key(meta)
                        if hasattr(ad, "_official_version_key") else new_key)
        content_hash = meta.get("content_hash") or meta.get("sha256")
        prev = state.get(name)
        prev_key = prev.get("버전키") if prev else None
        prev_official = prev.get("공식버전키", prev_key) if prev else None
        prev_hash = prev.get("본문해시") if prev else None
        baseline_hash = False

        change_reason = ""
        if prev_key is None:
            status = "신규"
            change_reason = "최초 수집"
        elif prev_official != official_key:
            status = "변경"
            change_reason = "공식 버전키 변경"
        elif content_hash and not prev_hash:
            # 기존 state.json에는 본문 해시가 없으므로 공식 버전이 같으면
            # 가짜 변경으로 처리하지 않고 첫 정상 실행에서 해시 기준만 등록한다.
            status = "동일"
            baseline_hash = True
        elif content_hash and prev_hash != content_hash:
            status = "변경"
            change_reason = "본문/파일 해시 변경"
        else:
            status = "동일"

        log.info(f"[{status}] {name}")
        log.info(f"        시행 {meta['시행일자']} · 버전 {meta['버전번호']} · MST {meta['MST']}")
        if content_hash:
            log.info(f"        본문해시 {content_hash[:12]}")
        if baseline_hash:
            log.info("        ↳ 기존 공식 버전 유지 · 본문 해시 기준 등록 필요")
        if status == "변경":
            log.info(f"        이전: {prev_key}")
            log.info(f"        현재: {new_key}")

        entry = {"법령명": name, "종류": kind, "상태": status,
                 "이전버전키": prev_official, "현재버전키": official_key,
                 "이전본문해시": prev_hash, "현재본문해시": content_hash,
                 "시행일자": meta["시행일자"], "버전번호": meta["버전번호"],
                 "변경사유": change_reason}

        if status == "동일":
            if baseline_hash and not dry:
                prev["버전키"] = new_key
                prev["공식버전키"] = official_key
                prev["본문해시"] = content_hash
                log.info("        ↳ 본문 해시 기준 등록 완료")
            changes.append(entry)
            continue

        if not dry:
            # 변경이면 기존 버전 백업 후 재수집
            old_txt_path = None
            if status == "변경" and prev:
                dest, moved = backup_existing(name, prev.get("버전키", "prev"))
                log.info(f"        ↳ 이전 버전 백업: {os.path.relpath(dest, ROOT)} ({', '.join(moved) or '없음'})")
                entry["백업경로"] = os.path.relpath(dest, ROOT)
                cand = os.path.join(dest, lawgo._safe(name) + ".txt")
                old_txt_path = cand if os.path.exists(cand) else None
            old_vid = None
            if con is not None:
                try:
                    old_vid = store.current_version_id(con, name, kind)
                except Exception as e:
                    log.error(f"        ↳ DB 현재본 조회 실패: {e}")
            collected = ad.collect(name, kind, want_files=True, verbose=True)
            collected_hash = ((collected or {}).get("본문해시")
                              or (collected or {}).get("sha256")
                              or content_hash)
            # DB 적재 (버전/섹션/원본파일 + 변경이면 섹션 diff·알림까지)
            if con is not None and collected:
                try:
                    with con:
                        cid = store.record_collection(
                            con, run_id, collected, kind, lawgo._safe(name),
                            status, change_reason, old_vid)
                    if cid:
                        row = con.execute("SELECT summary FROM regulation_changes"
                                          " WHERE change_id=?", (cid,)).fetchone()
                        log.info(f"        ↳ DB 기록: change #{cid} · 섹션 {row['summary']}")
                    else:
                        log.info("        ↳ DB 기록: 버전 적재 완료(동일 버전이라 변경 미기록)")
                    entry["change_id"] = cid
                except Exception as e:
                    log.error(f"        ↳ DB 적재 실패(파일 저장은 정상): {e}")
            final_key = (f"{official_key}|sha256:{collected_hash}"
                         if collected_hash and hasattr(ad, "_official_version_key")
                         else new_key)
            state[name] = {"버전키": final_key, "공식버전키": official_key,
                           "본문해시": collected_hash,
                           "MST": meta["MST"], "ID": meta["ID"],
                           "시행일자": meta["시행일자"], "버전번호": meta["버전번호"],
                           "최종수집": now}
            # 조문 단위 diff (변경 건만)
            if status == "변경" and old_txt_path:
                new_txt_path = os.path.join(OUT_DIR, lawgo._safe(name) + ".txt")
                try:
                    old_t = open(old_txt_path, encoding="utf-8").read()
                    new_t = open(new_txt_path, encoding="utf-8").read()
                    d = diff_report.diff_texts(old_t, new_t)
                    entry["조문변경"] = {"요약": d["요약"], "신설": d["신설"],
                                     "삭제": d["삭제"],
                                     "변경조문": [c["조문"] for c in d["변경"]]}
                    log.info("        ↳ " + d["요약"])
                    # 상세 diff 를 별도 파일로
                    dpath = os.path.join(REPORTS_DIR, f"diff_{lawgo._safe(name)}_"
                                         f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
                    os.makedirs(REPORTS_DIR, exist_ok=True)
                    with open(dpath, "w", encoding="utf-8") as f:
                        f.write(diff_report.format_report(name, d))
                    entry["diff리포트"] = os.path.relpath(dpath, ROOT)
                except Exception as e:
                    log.error(f"        ↳ diff 실패: {e}")
        changes.append(entry)

    if not dry:
        save_state(state)

    # 리포트 저장
    changed = [c for c in changes if c.get("상태") in ("신규", "변경")]
    os.makedirs(REPORTS_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {"실행시각": now, "dry_run": dry,
              "요약": {"전체": len(targets),
                     "변경": sum(c["상태"] == "변경" for c in changes),
                     "신규": sum(c["상태"] == "신규" for c in changes),
                     "동일": sum(c["상태"] == "동일" for c in changes),
                     "에러": sum(c["상태"] == "에러" for c in changes),
                     "검색실패": sum(c["상태"] == "검색실패" for c in changes)},
              "상세": changes}
    with open(os.path.join(REPORTS_DIR, f"report_{stamp}.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    _write_latest_markdown(report)

    if con is not None:
        try:
            failed = [c for c in changes if c.get("상태") in ("에러", "검색실패")]
            with con:
                store.finish_run(con, run_id, report["요약"], report,
                                 "success" if report["요약"]["에러"] == 0 else "partial")
                # 실패를 조용히 넘기면 그 규정의 개정을 다음 실행까지 놓친다
                if failed:
                    store.notify_failures(con, run_id, failed)
                    log.warning(f"  ⚠ 조회 실패 {len(failed)}건 — 알림 생성됨: "
                          + ", ".join(c["법령명"] for c in failed))
            log.info(f"DB: run #{run_id} 기록 완료 ({db.DB_PATH})")
        except Exception as e:
            log.warning(f"실행 이력 마감 실패: {e}")
        finally:
            con.close()
    # 수집 품질 자동 점검 — '에러 없이 잘못된 결과'를 규칙으로 잡는다
    if not dry:
        try:
            import quality_check
            names = [c["법령명"] for c in changes if c.get("상태") in ("신규", "변경")]
            log.info("-" * 60)
            high = quality_check.run(names or None, live=False)
            if high:
                log.warning(f"품질 점검에서 심각 항목 {high}건 — "
                            f"output/_reports/quality_latest.md 확인")
        except Exception as e:
            log.warning(f"품질 점검 실패: {e}")

    if con is not None:
        # 변경이 있었으면 색상 diff 뷰어를 새로 만들어 둔다(브라우저로 바로 확인용)
        if changed:
            try:
                import build_diff_view
                build_diff_view.build()
            except Exception as e:
                log.warning(f"diff 뷰어 생성 실패: {e}")

    log.info("=" * 60)
    log.info(f"요약: 변경 {report['요약']['변경']} · 신규 {report['요약']['신규']} · "
          f"동일 {report['요약']['동일']} · 오류 {report['요약']['에러']} · "
          f"검색실패 {report['요약']['검색실패']} / 전체 {len(targets)}")
    if changed and not dry:
        log.info("변경·신규 항목:")
        for c in changed:
            log.info(f"  - [{c['상태']}] {c['법령명']} (시행 {c['시행일자']})")
    log.info(f"리포트: output/_reports/report_{stamp}.json")


if __name__ == "__main__":
    args = sys.argv[1:]
    only = [a for a in args if not a.startswith("--")] or None
    dry = "--dry" in args
    try:
        if dry:      # 조회만 하므로 잠금 불필요
            run(dry=True, deep="--deep" in args, use_db=False, only=only)
        else:
            with _RunLock():
                run(dry=False, deep="--deep" in args, use_db="--no-db" not in args,
                    trigger="cron" if "--cron" in args else "manual", only=only)
    except RuntimeError as e:
        log.info(f"[중단] {e}")
        sys.exit(2)
