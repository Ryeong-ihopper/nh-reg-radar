# -*- coding: utf-8 -*-
"""법제처의 실제 두 MST를 격리 비교하여 조문 diff 파이프라인을 검증한다."""
import os
import sys

# 파이프라인 모듈은 src/ 에 있다. 이 스크립트는 한 단계 아래 폴더에서 직접 실행되므로
# import 경로에 src/ 를 먼저 넣어 준다.
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import argparse
import json
import os
import tempfile
from datetime import datetime

import check_updates
import diff_report
import law_scraper

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS_DIR = os.path.join(ROOT, "output", "_reports")


def _parsed(meta):
    body = law_scraper.fetch_body(meta)
    articles = law_scraper.parse_articles_law(body)
    addenda = law_scraper.parse_addenda(body)
    tables = law_scraper.parse_tables(body)
    text = law_scraper.to_text(meta["name"], articles, addenda, tables, [])
    info = body.get("기본정보", {})
    return {
        "본문": text,
        "조문수": len(articles),
        "부칙수": len(addenda),
        "별표수": len(tables),
        "공포일자": str(info.get("공포일자", "")),
        "공포번호": str(info.get("공포번호", "")),
        "시행일자": str(info.get("시행일자", "")),
    }


def run(name, old_mst, new_mst):
    old = _parsed({"name": name, "kind": "law", "MST": str(old_mst), "ID": ""})
    new = _parsed({"name": name, "kind": "law", "MST": str(new_mst), "ID": ""})
    result = diff_report.diff_texts(old["본문"], new["본문"], max_lines=20)
    if not (result["신설"] or result["삭제"] or result["변경"]):
        raise RuntimeError("실제 두 버전 사이에서 조문 변경을 찾지 못했습니다.")

    # 운영 디렉터리와 분리된 임시 환경에서 백업→재수집 결과 저장→diff 전체 흐름 검증
    with tempfile.TemporaryDirectory() as temp_root:
        old_out, old_versions = check_updates.OUT_DIR, check_updates.VERSIONS_DIR
        try:
            check_updates.OUT_DIR = os.path.join(temp_root, "output")
            check_updates.VERSIONS_DIR = os.path.join(check_updates.OUT_DIR, "_versions")
            os.makedirs(check_updates.OUT_DIR, exist_ok=True)
            safe = law_scraper._safe(name)
            old_txt = os.path.join(check_updates.OUT_DIR, safe + ".txt")
            old_json = os.path.join(check_updates.OUT_DIR, safe + ".json")
            with open(old_txt, "w", encoding="utf-8") as f:
                f.write(old["본문"])
            with open(old_json, "w", encoding="utf-8") as f:
                json.dump({"MST": str(old_mst)}, f)
            backup_dir, moved = check_updates.backup_existing(name, str(old_mst))
            backed_up_txt = os.path.join(backup_dir, safe + ".txt")
            if not os.path.isfile(backed_up_txt) or safe + ".txt" not in moved:
                raise RuntimeError("격리 백업 검증 실패")
            with open(os.path.join(check_updates.OUT_DIR, safe + ".txt"),
                      "w", encoding="utf-8") as f:
                f.write(new["본문"])
            with open(backed_up_txt, encoding="utf-8") as f:
                old_from_backup = f.read()
            with open(os.path.join(check_updates.OUT_DIR, safe + ".txt"),
                      encoding="utf-8") as f:
                new_from_collect = f.read()
            pipeline_diff = diff_report.diff_texts(old_from_backup, new_from_collect)
            if pipeline_diff["요약"] != result["요약"]:
                raise RuntimeError("백업본 기반 diff 결과 불일치")
            pipeline_validation = {
                "이전본백업": True,
                "현재본저장": True,
                "백업본기반조문diff": True,
            }
        finally:
            check_updates.OUT_DIR = old_out
            check_updates.VERSIONS_DIR = old_versions

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = law_scraper._safe(name)
    base = f"historical_diff_{safe}_{old_mst}_{new_mst}_{stamp}"
    os.makedirs(REPORTS_DIR, exist_ok=True)
    txt_path = os.path.join(REPORTS_DIR, base + ".txt")
    json_path = os.path.join(REPORTS_DIR, base + ".json")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(diff_report.format_report(name, result))
    payload = {
        "검증종류": "법제처 실제 과거 버전 격리 비교",
        "법령명": name,
        "이전": {"MST": str(old_mst), **{k: v for k, v in old.items() if k != "본문"}},
        "현재": {"MST": str(new_mst), **{k: v for k, v in new.items() if k != "본문"}},
        "조문변경": {
            "요약": result["요약"],
            "신설": result["신설"],
            "삭제": result["삭제"],
            "변경조문": [x["조문"] for x in result["변경"]],
        },
        "상세리포트": os.path.relpath(txt_path, ROOT),
        "파이프라인검증": pipeline_validation,
        "운영데이터변경": False,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("old_mst")
    parser.add_argument("new_mst")
    args = parser.parse_args()
    run(args.name, args.old_mst, args.new_mst)
