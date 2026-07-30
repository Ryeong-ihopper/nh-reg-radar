# -*- coding: utf-8 -*-
"""API 엔드포인트 동작 검증 (실제 DB 대상, 서버 기동 없이 TestClient 사용)."""
import os
import sys

# 파이프라인 모듈은 src/ 에 있다. 이 스크립트는 한 단계 아래 폴더에서 직접 실행되므로
# import 경로에 src/ 를 먼저 넣어 준다.
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import sys
import json
import warnings

sys.stdout.reconfigure(encoding="utf-8")
warnings.filterwarnings("ignore")

from fastapi.testclient import TestClient
import api

c = TestClient(api.app)
fails = []


def check(label, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}{(' — ' + detail) if detail else ''}")
    if not cond:
        fails.append(label)


print("[health]")
# 대상 수는 targets.json 이 늘면 같이 늘어난다 — 하드코딩하지 않는다
N_TARGETS = len(json.load(open("targets.json", encoding="utf-8")))
h = c.get("/api/health").json()
check("status ok", h["status"] == "ok", str(h["counts"]))
check(f"규정 {N_TARGETS}건", h["counts"]["regulations"] == N_TARGETS,
      str(h["counts"]["regulations"]))

print("[규정 목록]")
regs = c.get("/api/regulations").json()["items"]
check(f"{N_TARGETS}건 반환", len(regs) == N_TARGETS, f"{len(regs)}건")
check("현재본 연결됨", all(r["current_version_id"] for r in regs))
check("섹션수 있음", all(r["section_count"] > 0 for r in regs))
srcs = sorted({r["source_code"] for r in regs})
check("4개 출처", srcs == ["crefia", "kfb", "kofia", "lawgo"], str(srcs))

print("[출처 필터]")
# 건수를 상수로 박으면 대상이 늘 때마다 테스트가 깨진다(실측: 금투협 시행세칙 추가로 깨짐).
# targets.json 을 기준으로 센다.
N_KOFIA = sum(1 for t in json.load(open("targets.json", encoding="utf-8"))
              if t["kind"] == "kofia")
kofia = c.get("/api/regulations?source_code=kofia").json()["items"]
check(f"kofia {N_KOFIA}건", len(kofia) == N_KOFIA, str([r["name"] for r in kofia]))

print("[규정 상세 + 버전 이력]")
rid = regs[0]["regulation_id"]
d = c.get(f"/api/regulations/{rid}").json()
check("버전 이력 포함", len(d["versions"]) >= 1)
check("현재본 표시", any(v["is_current"] for v in d["versions"]))
check("없는 규정 404", c.get("/api/regulations/99999").status_code == 404)

print("[조문 목록]")
vid = regs[0]["current_version_id"]
secs = c.get(f"/api/versions/{vid}/sections").json()
check("조문 반환", secs["count"] > 0, f"{secs['count']}개")
check("순서 유지", [s["sequence_no"] for s in secs["items"]] ==
      sorted(s["sequence_no"] for s in secs["items"]))
only = c.get(f"/api/versions/{vid}/sections?section_type=부칙").json()
check("타입 필터", all(s["section_type"] == "부칙" for s in only["items"]),
      f"부칙 {only['count']}개")

print("[변경 피드]")
ch = c.get("/api/regulation-changes?limit=100").json()
# 건수는 DB 상태(과거 버전 적재 여부 등)에 따라 달라지므로 규정 수 이상인지만 본다
check("규정 수 이상의 변경 기록", ch["total"] >= len(regs), f"{ch['total']}건")
check("페이지네이션 필드", {"total", "limit", "offset", "items"} <= set(ch))
first = ch["items"][0]
check("규정명 조인", bool(first["regulation_name"]))
check("요약 있음", bool(first["summary"]), first["summary"])
p1 = c.get("/api/regulation-changes?limit=3&offset=0").json()["items"]
p2 = c.get("/api/regulation-changes?limit=3&offset=3").json()["items"]
check("offset 동작", {x["change_id"] for x in p1} & {x["change_id"] for x in p2} == set())

print("[변경 상세]")
cd = c.get(f"/api/regulation-changes/{first['change_id']}").json()
check("sections 필드", "sections" in cd)
# 최초 수집은 비교 대상이 없으므로 전 조문을 '신설'로 쏟아내면 안 된다
초 = next((x for x in ch["items"] if "최초" in (x["summary"] or "")), None)
if 초:
    d0 = c.get(f"/api/regulation-changes/{초['change_id']}").json()
    check("최초 수집은 섹션 diff 없음", len(d0["sections"]) == 0, f"{len(d0['sections'])}건")
# 실제 개정 건이 있으면 섹션 diff가 채워져 있어야 한다
실 = next((x for x in ch["items"] if x["changed_section_count"]
           or x["added_section_count"] or x["removed_section_count"]), None)
if 실:
    d1 = c.get(f"/api/regulation-changes/{실['change_id']}").json()
    check("실제 개정 건은 섹션 diff 존재", len(d1["sections"]) > 0, f"{len(d1['sections'])}건")
    mod = [s for s in d1["sections"] if s["change_type"] == "modified"]
    check("수정 섹션에 이전·현재 본문 모두 있음",
          all(s["old_content"] and s["new_content"] for s in mod), f"수정 {len(mod)}건")
check("없는 변경 404", c.get("/api/regulation-changes/99999").status_code == 404)

print("[실행 이력]")
runs = c.get("/api/runs").json()["items"]
check("실행 이력 있음", len(runs) >= 1, f"{len(runs)}건")
check("완료 상태", runs[0]["status"] in ("success", "partial"), runs[0]["status"])
rd = c.get(f"/api/runs/{runs[0]['run_id']}").json()
check("실행 상세 changes", isinstance(rd["changes"], list), f"{len(rd['changes'])}건")

print("[알림]")
# 반복 실행해도 같은 결과가 나오도록 읽음 상태를 초기화한다
_con = api.db.connect()
with _con:
    _con.execute("UPDATE notifications SET is_read=0")
_con.close()
un = c.get("/api/notifications?is_read=false").json()
check("변경 건수만큼 알림 생성", un["total"] == ch["total"], f"알림 {un['total']} / 변경 {ch['total']}")
nid = un["items"][0]["notification_id"]
check("읽음 처리", c.post(f"/api/notifications/{nid}/read").status_code == 200)
after = c.get("/api/notifications?is_read=false").json()
check("미읽음 1건 감소", after["total"] == un["total"] - 1, f"{after['total']}건")
check("없는 알림 404", c.post("/api/notifications/99999/read").status_code == 404)

print("[감시 프로파일]")
prof = c.post("/api/watch-profiles", json={"name": "테스트_은행권",
                                           "source_codes": ["kfb", "crefia"]})
check("생성 201", prof.status_code == 201, str(prof.status_code))
check("중복 409", c.post("/api/watch-profiles",
                        json={"name": "테스트_은행권"}).status_code == 409)

print("[검색]")
s = c.get("/api/search?q=광고").json()
check("검색 결과 있음", s["count"] > 0, f"{s['count']}건")
missing = [x["section_key"] for x in s["items"] if "광고" not in (x["snippet"] or "")]
check("스니펫이 매치 위치를 보여줌", not missing, f"누락 {missing[:3]}")
check("짧은 질의 422", c.get("/api/search?q=가").status_code == 422)

print("[동시 감지 차단]")
api._detect_lock.acquire()
try:
    check("이미 실행 중이면 409",
          c.post("/api/regulation-changes/detect", json={"dry": True}).status_code == 409)
finally:
    api._detect_lock.release()

# 테스트가 만든 프로파일 정리
con = api.db.connect()
with con:
    con.execute("DELETE FROM watch_profiles WHERE name='테스트_은행권'")
con.close()

print()
if fails:
    print(f"실패 {len(fails)}건: {', '.join(fails)}")
    sys.exit(1)
print("전부 통과")
