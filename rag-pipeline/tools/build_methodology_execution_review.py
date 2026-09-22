"""Produce source correspondence and executable local plans from extracts only."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from rag.templates.deposit_methodology_plan import compile_deposit_plans
from rag.templates.structured_methodology import (
    SOURCE_SPECS, _compile_row, _manifest_index, _structured_rows, _verify_extract,
)


EXTRACT_HASHES = (
    "7d9d167b8e2fdecef31be4e8af43080adacf2e51eaad3dd701a4fd5def080cc3",
    "6bdfc466f7535a9f94a5f7b3a1524d10bbc8eee5de714535c854e5e5b44a49aa",
    "020223afd7b338bde74d6ec416ade21c72a919a2472f40cde7b972c3e63c2d04",
    "83d0d4034fab51d2f6db0d6173e295ae16668d48072944eb7398da6c9ed77f55",
    "df4ae6eb17e6853d32afee00167758f0edcfd9a5743ea0bcf4610a65ba37835d",
)
OLD_HASH = "43d8905255cb2d6dcd25203c437f9f07bfa43ee291405ee073023cb3d3ef341b"


def build_review(extract_root: Path, old_csv: Path) -> dict:
    # Exact snapshots bind the manually inspected row correspondence. No name search.
    if hashlib.sha256(old_csv.read_bytes()).hexdigest() != OLD_HASH:
        raise ValueError("old template snapshot changed; re-review correspondence")
    with old_csv.open(encoding="utf-8-sig", newline="") as stream:
        old = {int(r["번호"]): r for r in csv.DictReader(stream)}
    manifest = _manifest_index(extract_root)
    rules = []
    for spec, expected in zip(SOURCE_SPECS, EXTRACT_HASHES, strict=True):
        path, data = _verify_extract(extract_root, spec["relative_path"], manifest)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("extract changed; re-review authored plans and correspondence")
        rules.extend(_compile_row(spec, data, sheet, row)
                     for sheet, row in _structured_rows(data))
    mapping = {f"MTH-LOAN-NAMED-R{n:02}": n - 3 for n in range(4, 32)}
    deposit_old = [58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 67, 68, 69, 70, 71, 72]
    mapping.update({f"MTH-DEPOSIT-DEMAND-R{n:02}": value
                    for n, value in zip(range(4, 20), deposit_old, strict=True)})
    mapping.update({f"MTH-RETIREMENT-R{n:02}": value for n, value in
                    {4: 255, 5: 256, 6: 257, 7: 258, 8: 259, 9: 260, 10: 261,
                     13: 262, 14: 263}.items()})
    correspondence = []
    for rule in rules:
        old_id = mapping.get(rule["rule_id"])
        relation = "CORRESPONDING_SUBJECT_REVIEW_CHANGED_CRITERIA" if old_id else "ADDED_IN_THIS_SCOPE"
        if old_id == 67:
            relation = "SPLIT_OLD_COMBINED_OBLIGATION"
        correspondence.append({"new_rule_id": rule["rule_id"], "old_physical_id": old_id,
                               "label": rule["label"], "relation": relation,
                               "source": rule["source"], "old_source_fields": old.get(old_id),
                               "new_outcomes": rule["outcomes"],
                               "new_semantic_reference": rule["display_example"],
                               "automatic_merge": False})
    plans = compile_deposit_plans(rules)
    return {"schema_version": "methodology-execution-review-v1",
            "operationally_connected": False, "answer_documents_read": False,
            "original_files_read": False, "correspondence": correspondence, "plans": plans,
            "counts": {"new_source_rows": len(rules), "corresponding_new_rows": len(mapping),
                       "distinct_old_rows": len(set(mapping.values())),
                       "added_rows_in_selected_scopes": len(rules) - len(mapping),
                       "deposit_source_rows": 16, "deposit_local_plans": len(plans)},
            "limits": ["대응은 같은 검사 주제이며 판정조건의 동일성을 보장하지 않음",
                       "305개 구조화·운영 연결 완료가 아님",
                       "LLM·추출기의 의미 판단 정확도는 계산기에서 검증하지 못함"]}


def report(document: dict) -> str:
    lines = ["# 신규 심의방법 대응 및 조건 계산 검토", "",
             "77개 신규 행 전체의 대응을 기록했습니다. 같은 검사 주제라는 뜻이며 기준까지 동일하다는 뜻은 아닙니다.",
             "53개 신규 행은 기존 52개 행에 대응합니다(기존 지급제한 1행 → 신규 2행).",
             "나머지 24행은 퇴직연금 신규 2행·퇴직연금 내 ETF 13행·ELB 9행입니다.",
             "예금 16행은 금리 방식 3행을 묶은 14개 로컬 계산 계획으로 작성했습니다.",
             "운영 미연결이며 LLM 의미판단·광고 파싱 성능을 측정한 결과가 아닙니다.", "",
             "| 신규 항목 | 구분 | 기존 물리 번호 | 관계 |", "| --- | --- | ---: | --- |"]
    relation = {"CORRESPONDING_SUBJECT_REVIEW_CHANGED_CRITERIA": "대응 주제·최신 기준 대조",
                "SPLIT_OLD_COMBINED_OBLIGATION": "기존 복합 행의 의무 분리",
                "ADDED_IN_THIS_SCOPE": "해당 템플릿 범위에 추가"}
    for row in document["correspondence"]:
        label = row['label'].replace('\n', ' ')
        lines.append(f"| {row['new_rule_id']} | {label} | {row['old_physical_id'] or '—'} | {relation[row['relation']]} |")
    lines += ["", "## 예금 조건 계산", "",
              "- 금리: 연/12개월·세전·기준일은 공통. 방식2는 기본금리와 최고금리 적용한도, 방식3은 적용한도가 필요합니다.",
              "- 우대금리: 상품에 우대금리가 없고 방식1이면 생략 가능. 있으면 합계 비교 또는 n개 조건 충족 방식으로 검사합니다.",
              "- 한도: 방식2/3에서는 중복 표기를 생략할 수 있지만 금리 항목의 한도 의무는 남습니다.",
              "- 예금자보호: LMS·링크 없음은 로고만 면제하며 보호 문구는 검사합니다. 일반 매체는 로고를 사람이 확인합니다.",
              "- 회사명·AI 안내 누락은 확인필요이며 자동 위반으로 바꾸지 않습니다.",
              "- 이자지급제한 두 문장은 별도 의무입니다. 한 문장 충족으로 다른 문장을 덮지 않습니다.", "",
              "## 해석 보류(전체 행을 버리지 않고 해당 조건만 보류)", "",
              "| 위치 | 보류 이유 | 나머지 검사 |", "| --- | --- | --- |",
              "| 가입대상 R06 | 기존 무제한 가입대상 생략 예외와 신규 누락 부적정의 버전 우선순위 | 가입대상 표시 확인 |",
              "| 금리 R07–09 | 기존 30일과 신규 한 달을 임의로 동일시하지 않음 | 연·세전·기준일·방식별 표시 |",
              "| 보호 R15 | LMS+링크에서 부적정 기준과 랜딩페이지 확인 지시가 겹침 | 보호 문구 및 링크 없는 LMS 예외 |",
              "| 유의사항 R16–17 | 예금 기준에 대출 유의사항 줄바꿈 조건이 기재됨 | 각 텍스트 의무 |", "",
              "조건을 모르면 추측하지 않습니다. 다만 독립된 필수 의무의 확정 미충족은 다른 의무가 미확정이어도 보존합니다.",
              "로컬 계산 입력은 광고·상품·버전·검토범위와 증거 위치가 일치해야 하며 검색 실패만으로 누락 위반을 만들지 않습니다.",
              "JSON에는 대응 전후 원문 열·출처 해시·계산식·입력 담당이 함께 있습니다. 원본·답지 파일은 읽지 않습니다."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extract-root", type=Path, required=True)
    parser.add_argument("--old-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("output directory exists; preserve earlier review artifacts")
    document = build_review(args.extract_root, args.old_csv)
    args.output_dir.mkdir(parents=True)
    (args.output_dir / "methodology-execution-review.json").write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "methodology-execution-review.md").write_text(report(document), encoding="utf-8")
    print(json.dumps(document["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
