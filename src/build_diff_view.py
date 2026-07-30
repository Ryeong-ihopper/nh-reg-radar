# -*- coding: utf-8 -*-
"""
변경 내역 색상 뷰어 생성기 → output/_review/diff.html

DB(regulation_section_changes)에 쌓인 실제 변경을 읽어 조문별로 보여준다.

핵심은 '어디가 바뀌었는지 좁게 짚어주는 것':
  · 줄 단위로만 표시하면 120자 줄에서 3글자 바뀌어도 줄 전체가 빨갛게 된다.
  · 그래서 줄을 짝지은 뒤(pair_changed_lines) 줄 안에서 실제 바뀐 글자만
    진하게 칠한다(inline_diff). 안 바뀐 줄은 접어서 숨긴다.
"""
import os
import sys
import json
import html

sys.stdout.reconfigure(encoding="utf-8")

import db
from diff_report import inline_diff, changed_ratio, pair_changed_lines

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REVIEW_DIR = os.path.join(ROOT, "output", "_review")

CONTEXT = 1        # 변경 줄 앞뒤로 보여줄 문맥 줄 수


def _segs(a, b):
    """두 줄 → (구 버전 조각들, 신 버전 조각들). 조각 = {op, text}"""
    o, n = inline_diff(a or "", b or "")
    return ([{"op": op, "t": t} for op, t in o],
            [{"op": op, "t": t} for op, t in n])


def build_section_view(old_content, new_content):
    """조문 하나의 변경을 화면용 구조로. 안 바뀐 줄은 접는다."""
    old_lines = (old_content or "").splitlines()
    new_lines = (new_content or "").splitlines()
    pairs = pair_changed_lines(old_lines, new_lines)

    rows = []
    for kind, o, n in pairs:
        if kind == "modified":
            os_, ns_ = _segs(o, n)
            rows.append({"kind": "modified", "old": os_, "new": ns_,
                         "ratio": round(changed_ratio(o, n) * 100, 1),
                         "len": len(n)})
        elif kind == "removed":
            rows.append({"kind": "removed", "old": [{"op": "diff", "t": o}],
                         "new": [], "ratio": 100.0, "len": len(o or "")})
        else:
            rows.append({"kind": "added", "old": [],
                         "new": [{"op": "diff", "t": n}], "ratio": 100.0,
                         "len": len(n or "")})
    # 삭제분과 추가분을 더해 버리면 조문이 크게 줄어든 경우 100%를 넘는다
    # (예: 1,100자를 81자로 줄이면 1,112/81 = 1372%). 양쪽 중 큰 쪽을 '바뀐 양'으로,
    # 이전·현재 중 긴 쪽을 분모로 삼아 0~100% 범위에 들어오게 한다.
    deleted = sum(sum(len(s["t"]) for s in r["old"] if s["op"] == "diff") for r in rows)
    inserted = sum(sum(len(s["t"]) for s in r["new"] if s["op"] == "diff") for r in rows)
    changed_chars = max(deleted, inserted)
    total = max(len(old_content or ""), len(new_content or ""), 1)
    return {"rows": rows, "changed_chars": changed_chars, "total_chars": total,
            "deleted_chars": deleted, "inserted_chars": inserted,
            "ratio": round(min(changed_chars / total, 1.0) * 100, 1)}


def collect_changes(con):
    out = []
    q = """SELECT c.change_id, c.created_at, c.change_reason, c.summary,
                  c.added_section_count, c.removed_section_count, c.changed_section_count,
                  r.name AS regulation_name, s.source_name,
                  ov.official_version_key AS old_key, ov.effective_at AS old_eff,
                  ov.promulgated_at AS old_prom, ov.promulgation_no AS old_no,
                  nv.official_version_key AS new_key, nv.effective_at AS new_eff,
                  nv.promulgated_at AS new_prom, nv.promulgation_no AS new_no
           FROM regulation_changes c
           JOIN regulations r USING(regulation_id)
           JOIN regulation_sources s USING(source_id)
           LEFT JOIN regulation_versions ov ON ov.version_id=c.old_version_id
           LEFT JOIN regulation_versions nv ON nv.version_id=c.new_version_id
           ORDER BY c.change_id DESC"""
    for ch in con.execute(q):
        secs = con.execute(
            "SELECT section_key, change_type, old_content, new_content"
            " FROM regulation_section_changes WHERE change_id=?"
            " ORDER BY section_change_id", (ch["change_id"],)).fetchall()
        if not secs:
            continue          # '최초 수집'처럼 비교 대상이 없는 건은 뷰어에 넣지 않는다
        items = []
        for s in secs:
            v = build_section_view(s["old_content"], s["new_content"])
            items.append({"key": s["section_key"], "type": s["change_type"], **v})
        out.append({**{k: ch[k] for k in ch.keys()}, "sections": items})
    return out


def build():
    con = db.connect()
    try:
        changes = collect_changes(con)
    finally:
        con.close()

    os.makedirs(REVIEW_DIR, exist_ok=True)
    data = json.dumps(changes, ensure_ascii=False).replace("</", "<\\/")
    html_out = (TEMPLATE.replace("__DIFF_CSS__", DIFF_CSS)
                .replace("__DIFF_JS__", DIFF_JS).replace("__DATA__", data))
    out = os.path.join(REVIEW_DIR, "diff.html")
    with open(out, "wb") as f:
        f.write(html_out.encode("utf-8", "replace"))

    print(f"변경 건수: {len(changes)}")
    for c in changes:
        print(f"  #{c['change_id']} {c['regulation_name']} — {c['summary']}")
        for s in c["sections"]:
            print(f"      {s['type']:9} {s['key']:8} 바뀐 글자 "
                  f"{s['changed_chars']}/{s['total_chars']}자 ({s['ratio']}%)")
    print(f"\n생성됨: {os.path.relpath(out, ROOT)}")


# ── 아래 CSS/JS 는 review.html('변경 내역' 탭)에서도 그대로 재사용한다 ─────────
DIFF_CSS = r"""
  .diff-scope { --del-bg:#ffeaea; --del-hi:#ffb3b3; --del-tx:#8a1f1f;
                --ins-bg:#e8f7ec; --ins-hi:#9fe3b0; --ins-tx:#14612c; --mod-bg:#fff2cc; --mod-tx:#7a5b00; }
  @media (prefers-color-scheme: dark) {
    .diff-scope { --del-bg:#3a1f22; --del-hi:#7d2b31; --del-tx:#ffb4b4;
                  --ins-bg:#16301f; --ins-hi:#2e6b41; --ins-tx:#a7e8bb;
                  --mod-bg:#4a3a12; --mod-tx:#ffdd8a; }
  }
  .diff-wrap { max-width:1100px; margin:0 auto; padding:20px; }
  .change { background:var(--panel); border:1px solid var(--border); border-radius:10px;
            margin-bottom:20px; overflow:hidden; }
  .change > h2 { font-size:15px; margin:0; padding:14px 18px;
                 border-bottom:1px solid var(--border); }
  /* 검수용 가상 이력은 진짜 개정과 확실히 구분되게 표시한다 */
  .change.sim { border-style:dashed; opacity:.93; }
  .simtag, .realtag { font-size:11px; padding:2px 8px; border-radius:999px;
                      font-weight:700; margin-left:8px; vertical-align:middle; }
  .simtag  { background:var(--mod-bg); color:var(--mod-tx); }
  .realtag { background:var(--ins-bg); color:var(--ins-tx); }
  .change .meta { font-size:12.5px; color:var(--sub); font-weight:400; margin-top:5px; }
  .vtab { margin-top:10px; border-collapse:collapse; font-size:12.5px; font-weight:400; }
  .vtab th, .vtab td { padding:4px 14px 4px 0; text-align:left; color:var(--text); }
  .vtab th { color:var(--sub); font-weight:600; font-size:11.5px; }
  .vtab td:first-child { color:var(--sub); }
  .vtab .hint { color:var(--sub); font-size:11px; opacity:.85; }
  .sec { border-bottom:1px solid var(--border); }
  .sec:last-child { border-bottom:none; }
  .sec-head { padding:10px 18px; display:flex; align-items:center; gap:10px;
              cursor:pointer; user-select:none; font-size:13.5px; }
  .sec-head:hover { background:var(--bg); }
  .tag { font-size:11px; padding:2px 8px; border-radius:999px; font-weight:600; }
  .tag.modified { background:var(--mod-bg); color:var(--mod-tx); }
  .tag.added    { background:var(--ins-bg); color:var(--ins-tx); }
  .tag.removed  { background:var(--del-bg); color:var(--del-tx); }
  .ratio { margin-left:auto; font-size:12px; color:var(--sub); }
  .bar { display:inline-block; width:70px; height:6px; border-radius:3px;
         background:var(--border); overflow:hidden; vertical-align:middle; margin-left:8px; }
  .bar i { display:block; height:100%; background:var(--accent); }
  .sec .body { display:none; padding:4px 18px 16px; }
  .sec.open .body { display:block; }
  .line { font-family:"Consolas","D2Coding",monospace; font-size:13px; line-height:1.65;
          white-space:pre-wrap; word-break:break-word; padding:3px 10px 3px 26px;
          border-radius:5px; position:relative; margin:2px 0; }
  .line::before { position:absolute; left:8px; color:var(--sub); font-weight:700; }
  .line.del { background:var(--del-bg); color:var(--del-tx); }
  .line.del::before { content:"−"; }
  .line.ins { background:var(--ins-bg); color:var(--ins-tx); }
  .line.ins::before { content:"+"; }
  .line .hi { border-radius:3px; padding:1px 0; font-weight:700; }
  .line.del .hi { background:var(--del-hi); }
  .line.ins .hi { background:var(--ins-hi); }
  .empty { padding:40px; text-align:center; color:var(--sub); }
  .legend { font-size:12px; color:var(--sub); }
  .legend .hi { padding:1px 5px; border-radius:3px; font-weight:700; }
  .legend .d { background:var(--del-hi); color:var(--del-tx); }
  .legend .i { background:var(--ins-hi); color:var(--ins-tx); }
"""

# renderChanges(data, rootEl) 와 토글 두 개(전부 펼치기 / 줄 전체 강조)를 제공한다
DIFF_JS = r"""
let __wholeLine = false;
function __esc(s){ return String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }
function __segs(segs){
  // 줄 전체 강조 모드면 전부, 아니면 실제 바뀐 조각만 진하게
  return segs.map(s => (s.op === 'diff' || __wholeLine)
    ? `<span class="hi">${__esc(s.t)}</span>` : __esc(s.t)).join('');
}
const __LABEL = {modified:'수정', added:'신설', removed:'삭제'};

function __d(s){   // 20260102 → 2026-01-02
  s = String(s || '');
  return /^\d{8}$/.test(s) ? `${s.slice(0,4)}-${s.slice(4,6)}-${s.slice(6)}` : (s || '—');
}
function __dt(s){  // ISO 시각 → 2026-07-27 14:51
  if (!s) return '—';
  return String(s).replace('T', ' ').slice(0, 16);
}
function __versionTable(c){
  // 날짜가 셋이라 헷갈리기 쉽다. 무엇이 '바뀐 날'인지 명확히 갈라 놓는다.
  return `<table class="vtab">
    <tr><th></th><th>이전</th><th>이후</th></tr>
    <tr><td>공포일 <span class="hint">(관보 게재 = 실제 개정된 날)</span></td>
        <td>${__d(c.old_prom)}</td><td><b>${__d(c.new_prom)}</b></td></tr>
    <tr><td>시행일 <span class="hint">(효력이 생기는 날)</span></td>
        <td>${__d(c.old_eff)}</td><td><b>${__d(c.new_eff)}</b></td></tr>
    <tr><td>공포번호</td><td>${__esc(c.old_no||'—')}</td><td>${__esc(c.new_no||'—')}</td></tr>
    <tr><td>감지 시각 <span class="hint">(우리 시스템이 발견한 때)</span></td>
        <td colspan="2">${__dt(c.created_at)}</td></tr>
  </table>`;
}
function __section(sec){
  const rows = sec.rows.map(r => {
    if (r.kind === 'modified')
      return `<div class="line del">${__segs(r.old)}</div><div class="line ins">${__segs(r.new)}</div>`;
    if (r.kind === 'removed') return `<div class="line del">${__segs(r.old)}</div>`;
    return `<div class="line ins">${__segs(r.new)}</div>`;
  }).join('');
  return `<div class="sec"><div class="sec-head">
      <span class="tag ${sec.type}">${__LABEL[sec.type] || sec.type}</span>
      <b>${__esc(sec.key)}</b>
      <span class="ratio">바뀐 글자 ${sec.changed_chars.toLocaleString()} / ${sec.total_chars.toLocaleString()}자 (${sec.ratio}%)
        <span class="bar"><i style="width:${Math.min(100, sec.ratio)}%"></i></span></span>
    </div><div class="body">${rows}</div></div>`;
}
function renderChanges(data, root){
  if (!data.length) {
    root.innerHTML = `<div class="empty">아직 감지된 개정이 없습니다.<br>
      실제 개정이 발생하면 바뀐 조문이 여기에 쌓입니다.</div>`;
    return;
  }
  root.innerHTML = data.map(c => {
    const sim = /시뮬레이션/.test(c.change_reason || '');
    return `<div class="change${sim ? ' sim' : ''}">
      <h2>${__esc(c.regulation_name)}
        ${sim ? '<span class="simtag">시뮬레이션</span>' : '<span class="realtag">실제 개정</span>'}
        <div class="meta">${__esc(c.source_name)} · ${__esc(c.summary||'')} · ${__esc(c.change_reason||'')}</div>
        ${__versionTable(c)}
      </h2>${c.sections.map(__section).join('')}</div>`;
  }).join('');
  root.querySelectorAll('.sec-head').forEach(h =>
    h.onclick = () => h.parentElement.classList.toggle('open'));
  root.querySelectorAll('.sec').forEach((s,i) => { if (i < 3) s.classList.add('open'); });
}
function bindDiffToggles(expandBtn, wholeBtn, data, root){
  expandBtn.onclick = () => {
    const secs = root.querySelectorAll('.sec');
    const allOpen = [...secs].every(s => s.classList.contains('open'));
    secs.forEach(s => s.classList.toggle('open', !allOpen));
    expandBtn.textContent = allOpen ? '전부 펼치기' : '전부 접기';
  };
  wholeBtn.onclick = () => {
    __wholeLine = !__wholeLine;
    wholeBtn.textContent = __wholeLine ? '바뀐 글자만 강조' : '줄 전체 강조로 보기';
    const opened = [...root.querySelectorAll('.sec')].map(s => s.classList.contains('open'));
    renderChanges(data, root);
    root.querySelectorAll('.sec').forEach((s,i) => s.classList.toggle('open', opened[i]));
  };
}
"""

TEMPLATE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>규정 변경 내역</title>
<style>
  :root { --bg:#f6f7f9; --panel:#fff; --border:#dde1e6; --text:#1b2026; --sub:#6b7480; --accent:#2563eb; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#14171c; --panel:#1b1f26; --border:#2c323b; --text:#e6e9ee; --sub:#8b93a1; --accent:#6ea8ff; }
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font-family:-apple-system,"Malgun Gothic","Segoe UI",sans-serif; }
  header { position:sticky; top:0; z-index:5; background:var(--panel);
           border-bottom:1px solid var(--border); padding:12px 20px;
           display:flex; align-items:center; gap:14px; flex-wrap:wrap; }
  h1 { font-size:16px; margin:0; }
  button.toggle { background:var(--bg); color:var(--text); border:1px solid var(--border);
                  border-radius:6px; padding:6px 10px; font-size:12.5px; cursor:pointer; }
  button.toggle:hover { border-color:var(--accent); }
__DIFF_CSS__
</style>
</head>
<body class="diff-scope">
<header>
  <h1>🔍 규정 변경 내역</h1>
  <button class="toggle" id="expandAll">전부 펼치기</button>
  <button class="toggle" id="wholeLine">줄 전체 강조로 보기</button>
  <span class="legend" style="margin-left:auto">바뀐 글자만
    <span class="hi d">삭제</span> <span class="hi i">추가</span> 로 진하게 표시</span>
</header>
<div class="diff-wrap" id="root"></div>
<script>
const DATA = __DATA__;
__DIFF_JS__
const root = document.getElementById('root');
renderChanges(DATA, root);
bindDiffToggles(document.getElementById('expandAll'),
                document.getElementById('wholeLine'), DATA, root);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    build()
