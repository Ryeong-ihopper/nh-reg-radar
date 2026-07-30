# -*- coding: utf-8 -*-
"""수집 결과의 구조·파일 완전성과 선택적 공식 원문 일치 여부를 검증한다."""
import os
import sys

# 파이프라인 모듈은 src/ 에 있다. 이 스크립트는 한 단계 아래 폴더에서 직접 실행되므로
# import 경로에 src/ 를 먼저 넣어 준다.
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import argparse
import json
import os
from datetime import datetime

import content_hash
import law_scraper
import kofia_scraper
import crefia_scraper
import kfb_scraper

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "output")
REPORTS_DIR = os.path.join(OUT_DIR, "_reports")
STATE_PATH = os.path.join(ROOT, "state.json")
TARGETS_PATH = os.path.join(ROOT, "targets.json")

ADAPTERS = {
    "law": law_scraper,
    "admrul": law_scraper,
    "kofia": kofia_scraper,
    "crefia": crefia_scraper,
    "kfb": kfb_scraper,
}


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _stored_hash(record, kind):
    if kind in ("law", "admrul"):
        value = {
            "조문": record.get("조문", []),
            "부칙": record.get("부칙", []),
            "별표": record.get("별표", []),
            "첨부파일": record.get("첨부파일", []) if kind == "admrul" else [],
        }
        return content_hash.sha256_structure(value)
    if kind == "kofia":
        return content_hash.sha256_structure({
            "조문": record.get("조문", []),
            "부칙": record.get("부칙", []),
        })
    return record.get("sha256", "")


def _local_checks(name, kind, state):
    safe = law_scraper._safe(name)
    json_path = os.path.join(OUT_DIR, safe + ".json")
    txt_path = os.path.join(OUT_DIR, safe + ".txt")
    errors, warnings = [], []
    record = None

    if not os.path.isfile(json_path):
        errors.append("JSON 없음")
    else:
        try:
            record = _read_json(json_path)
        except Exception as e:
            errors.append(f"JSON 파싱 실패: {e}")

    if not os.path.isfile(txt_path):
        errors.append("TXT 없음")
    elif os.path.getsize(txt_path) == 0:
        errors.append("TXT가 0바이트")
    else:
        text = open(txt_path, encoding="utf-8").read()
        if name.replace(" ", "") not in text.replace(" ", "")[:500]:
            warnings.append("TXT 머리말에서 규정명 확인 불가")

    stats = (record or {}).get("통계", {})
    if record:
        if kind in ("law", "admrul", "kofia"):
            pairs = [("조문수", "조문"), ("부칙수", "부칙")]
            if kind in ("law", "admrul"):
                pairs.append(("별표수", "별표"))
            if kind == "admrul":
                pairs.append(("첨부수", "첨부파일"))
            for count_key, list_key in pairs:
                if count_key in stats and stats[count_key] != len(record.get(list_key, [])):
                    errors.append(f"{count_key} 불일치")
        else:
            body = record.get("본문", "")
            if not body:
                errors.append("추출 본문 없음")
            if stats.get("본문길이") != len(body):
                errors.append("본문길이 불일치")

    file_dir = os.path.join(OUT_DIR, "files", safe)
    files = []
    if os.path.isdir(file_dir):
        for base, _, names in os.walk(file_dir):
            files += [os.path.join(base, n) for n in names]
    zero_files = [os.path.basename(p) for p in files if os.path.getsize(p) == 0]
    if zero_files:
        errors.append(f"0바이트 첨부 {len(zero_files)}개")
    expected = stats.get("다운로드파일수") if record else None
    if expected is not None and expected != len(files):
        errors.append(f"첨부파일 수 불일치: JSON {expected}, 실제 {len(files)}")
    if kind in ("crefia", "kfb") and not files:
        errors.append("원본 첨부파일 없음")

    stored_hash = _stored_hash(record, kind) if record else ""
    state_row = state.get(name, {})
    official = state_row.get("공식버전키")
    return {
        "법령명": name,
        "종류": kind,
        "상태": "오류" if errors else ("주의" if warnings else "정상"),
        "오류": errors,
        "주의": warnings,
        "JSON크기": os.path.getsize(json_path) if os.path.isfile(json_path) else 0,
        "TXT크기": os.path.getsize(txt_path) if os.path.isfile(txt_path) else 0,
        "첨부파일수": len(files),
        "저장본문해시": stored_hash,
        "저장공식버전키": official,
    }


def _live_check(result):
    name, kind = result["법령명"], result["종류"]
    ad = ADAPTERS[kind]
    try:
        if kind in ("law", "admrul", "kofia"):
            meta = ad.current_meta(name, kind, deep=True)
        else:
            meta = ad.current_meta(name, kind)
        if not meta:
            raise RuntimeError("공식 원문 검색 결과 없음")
        live_hash = meta.get("content_hash") or meta.get("sha256", "")
        live_official = (ad._official_version_key(meta)
                         if hasattr(ad, "_official_version_key")
                         else ad._version_key(meta))
        result["현재본문해시"] = live_hash
        result["현재공식버전키"] = live_official
        if result["저장본문해시"] and live_hash != result["저장본문해시"]:
            result["오류"].append("저장 본문과 공식 원문 해시 불일치")
        if result["저장공식버전키"] and live_official != result["저장공식버전키"]:
            result["오류"].append("저장 공식 버전키와 현재 버전키 불일치")
        result["원문대조"] = "불일치" if result["오류"] else "일치"
    except Exception as e:
        result["원문대조"] = "확인실패"
        result["주의"].append(f"공식 원문 조회 실패: {e}")
    result["상태"] = ("오류" if result["오류"]
                    else "주의" if result["주의"] else "정상")


def _markdown(report):
    summary = report["요약"]
    lines = [
        "# 수집 결과 검증 보고서", "",
        f"- 실행시각: {report['실행시각']}",
        f"- 공식 원문 대조: {'포함' if report['live'] else '미포함'}",
        f"- 결과: 정상 {summary['정상']} · 주의 {summary['주의']} · 오류 {summary['오류']}",
        "",
        "| 규정 | 종류 | 로컬 상태 | 원문 대조 | JSON | TXT | 첨부 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for r in report["상세"]:
        lines.append(
            f"| {r['법령명']} | {r['종류']} | {r['상태']} | "
            f"{r.get('원문대조', '-')} | {r['JSON크기']} | {r['TXT크기']} | "
            f"{r['첨부파일수']} |"
        )
    issues = [r for r in report["상세"] if r["오류"] or r["주의"]]
    if issues:
        lines += ["", "## 확인할 사항", ""]
        for r in issues:
            lines.append(f"### {r['법령명']}")
            lines += [f"- 오류: {x}" for x in r["오류"]]
            lines += [f"- 주의: {x}" for x in r["주의"]]
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def run(live=False):
    targets = _read_json(TARGETS_PATH)
    state = _read_json(STATE_PATH) if os.path.exists(STATE_PATH) else {}
    results = []
    for target in targets:
        result = _local_checks(target["name"], target["kind"], state)
        if live:
            _live_check(result)
        results.append(result)
    report = {
        "실행시각": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "live": live,
        "요약": {
            "전체": len(results),
            "정상": sum(r["상태"] == "정상" for r in results),
            "주의": sum(r["상태"] == "주의" for r in results),
            "오류": sum(r["상태"] == "오류" for r in results),
        },
        "상세": results,
    }
    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(os.path.join(REPORTS_DIR, "validation_latest.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(os.path.join(REPORTS_DIR, "validation_latest.md"), "w", encoding="utf-8") as f:
        f.write(_markdown(report))
    print(_markdown(report))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="공식 사이트 현재 원문까지 대조")
    args = parser.parse_args()
    run(live=args.live)
