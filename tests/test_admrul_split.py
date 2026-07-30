# -*- coding: utf-8 -*-
"""
행정규칙 조문 줄바꿈 삽입기 검증.

핵심 안전조건: **내용은 한 글자도 바뀌면 안 되고, 줄바꿈만 늘어야 한다.**
그 위에서 diff 정밀도가 실제로 좋아지는지, 오분할(날짜·문장끝 '다.')이 없는지 본다.
"""
import os
import sys

# 파이프라인 모듈은 src/ 에 있다. 이 스크립트는 한 단계 아래 폴더에서 직접 실행되므로
# import 경로에 src/ 를 먼저 넣어 준다.
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import re
import os
import sys
import json
import difflib

sys.stdout.reconfigure(encoding="utf-8")

from law_scraper import split_admrul_body

def _need_output(*names):
    """수집 결과가 있어야 돌 수 있는 테스트. 없으면 안내하고 건너뛴다."""
    missing = [n for n in names if not os.path.exists(f"output/{n}.json")]
    if missing:
        print("건너뜀 — 수집 결과가 없습니다. 먼저 실행하세요:")
        print("    python check_updates.py")
        print(f"  (필요 파일: {', '.join(missing)})")
        sys.exit(0)

_need_output("금융소비자 보호에 관한 감독규정", "금융소비자보호에 관한 감독규정 시행세칙")

fails = []


def check(label, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}{(' — ' + detail) if detail else ''}")
    if not cond:
        fails.append(label)


# ── 1. 무손실: 줄바꿈만 제거하면 원문과 완전히 같아야 한다 ──────────────
print("[무손실 검증] 실제 감독규정·시행세칙 전 조문")
srcs = []
for f in ("금융소비자 보호에 관한 감독규정", "금융소비자보호에 관한 감독규정 시행세칙"):
    d = json.load(open(f"output/{f}.json", encoding="utf-8"))
    srcs += [a["조문내용"] for a in d["조문"]]
print(f"  대상 조문 {len(srcs)}개")

# 저장된 결과는 이미 분할본일 수 있으므로 줄바꿈을 없앤 '통짜 원문'을 복원해 입력으로 쓴다
lossless = True
for raw in srcs:
    flat = raw.replace("\n", "")
    out = split_admrul_body(flat)
    if out.replace("\n", "") != flat.strip():
        lossless = False
        a, b = flat.strip(), out.replace("\n", "")
        i = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        print(f"    차이 발생 @{i}: {a[max(0,i-30):i+30]!r} vs {b[max(0,i-30):i+30]!r}")
        break
check("줄바꿈 외 내용 변경 없음", lossless)

# ── 2. 오분할 검증 ──────────────────────────────────────────────────────
print("[오분할 검증]")
bad_date = bad_mok = 0
for raw in srcs:
    for line in split_admrul_body(raw.replace("\n", "")).split("\n"):
        # 연도로 시작하는 줄 = <개정 2025.2.13> 같은 날짜를 호로 잘못 자른 것
        if re.match(r"^\d{4}\.", line):
            bad_date += 1
        # '다.'로 시작하는데 뒤가 목 내용이 아니라 문장 이어짐 = '…한다.' 오분할 의심
        if re.match(r"^다\.\s*$", line):
            bad_mok += 1
check("날짜를 호로 오분할하지 않음", bad_date == 0, f"{bad_date}건")
check("문장끝 '다.'를 목으로 오분할하지 않음", bad_mok == 0, f"{bad_mok}건")

# ── 3. diff 정밀도 개선 확인 ────────────────────────────────────────────
print("[diff 정밀도] 4,901자 조문에서 한 단어(3글자)만 개정된 경우")
target = max(srcs, key=len).replace("\n", "")
before_n = len(target)


def diff_size(a, b):
    lines = [l for l in difflib.unified_diff(a.splitlines(), b.splitlines(),
                                             lineterm="", n=0)
             if l and l[0] in "+-" and not l.startswith(("+++", "---"))]
    return sum(len(l) for l in lines), len(lines)


flat_new = target.replace("금융위원회", "금융감독원", 1)
old_chars, old_lines = diff_size(target, flat_new)

split_old = split_admrul_body(target)
split_new = split_admrul_body(flat_new)
new_chars, new_lines = diff_size(split_old, split_new)

print(f"  분할 전: diff {old_lines}줄 / {old_chars:,}자 출력")
print(f"  분할 후: diff {new_lines}줄 / {new_chars:,}자 출력")
check("diff 출력량이 크게 줄어듦", new_chars < old_chars / 5,
      f"{old_chars:,}자 → {new_chars:,}자 ({new_chars/old_chars*100:.1f}%)")
check("분할 후에도 변경 지점을 정확히 포함", "금융감독원" in "\n".join(
    l for l in difflib.unified_diff(split_old.splitlines(), split_new.splitlines(),
                                    lineterm="", n=0)))

# ── 4. 줄 길이 분포 ─────────────────────────────────────────────────────
print("[가독성] 줄 길이 분포")
lens = [len(l) for raw in srcs for l in split_admrul_body(raw.replace("\n", "")).split("\n")]
lens.sort()
print(f"  줄 수 {len(lens)} · 중앙 {lens[len(lens)//2]}자 · 최대 {lens[-1]}자")
check("한 줄 최대 길이가 조문 통짜(4,901자)보다 훨씬 짧음", lens[-1] < 1500, f"{lens[-1]}자")

print()
if fails:
    print(f"실패 {len(fails)}건: {', '.join(fails)}")
    sys.exit(1)
print("전부 통과")
