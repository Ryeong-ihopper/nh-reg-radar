# -*- coding: utf-8 -*-
"""지금까지 만든 것을 **한 화면에서 눈으로 본다.** 단일 HTML, 오프라인.

숫자만 오가니 무엇이 되고 무엇이 안 되는지 감이 안 잡힌다. 광고 하나를 고르면
이렇게 보이게 한다.

    왼쪽   광고 원문 (지적된 문구에 표시)
    가운데 지적 목록 — 유형 · 근거규정 · 사유 · 개선안 · 누가 판정했나(룰/LLM)
    오른쪽 검색이 가져온 근거 조문 원문
    위     심의사례가 적은 정답과 우리 결과 대조

**심의사례를 나란히 두는 것이 핵심이다.** 우리 지적이 그럴듯해 보여도 사람이 적은
지적과 다르면 아직 못 쓰는 것이고, 그 차이가 한눈에 보여야 한다.

  python rag/build_viewer.py
  → output/_review/rag_view.html  (브라우저로 열면 끝, 서버 불필요)
"""
import os
import re
import sys
import json
import html
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG = os.path.join(ROOT, "output", "_rag")
OUT = os.path.join(ROOT, "output", "_review", "rag_view.html")


def load(name, default=None):
    p = os.path.join(RAG, name)
    if not os.path.exists(p):
        return default
    if name.endswith(".jsonl"):
        return [json.loads(l) for l in open(p, encoding="utf-8")]
    return json.load(open(p, encoding="utf-8"))


def esc(s):
    return html.escape(str(s if s is not None else ""))


CSS = """
:root{--bg:#fff;--fg:#1c1c1c;--mut:#6b6b6b;--line:#e3e3e0;--ng:#b3261e;--ok:#1b5e20;
      --na:#8a8a8a;--card:#faf9f7;--accent:#2f5d50}
*{box-sizing:border-box}
body{margin:0;font:14px/1.65 -apple-system,'Segoe UI','Malgun Gothic',sans-serif;
     color:var(--fg);background:var(--bg)}
header{padding:14px 20px;border-bottom:1px solid var(--line);display:flex;
       gap:18px;align-items:baseline;flex-wrap:wrap;position:sticky;top:0;
       background:var(--bg);z-index:5}
header h1{font-size:15px;margin:0;font-weight:650}
header .m{color:var(--mut);font-size:12px}
nav{padding:8px 20px;border-bottom:1px solid var(--line);display:flex;gap:6px;
    flex-wrap:wrap;background:var(--card)}
nav button{font:inherit;font-size:12px;padding:4px 10px;border:1px solid var(--line);
           background:#fff;border-radius:3px;cursor:pointer}
nav button.on{background:var(--accent);color:#fff;border-color:var(--accent)}
main{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.1fr) minmax(0,1fr);
     gap:0;height:calc(100vh - 104px)}
section{overflow:auto;padding:16px 18px;border-right:1px solid var(--line)}
section:last-child{border-right:0}
h2{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--mut);
   margin:0 0 10px;font-weight:600}
pre.ad{white-space:pre-wrap;word-break:break-word;font:13px/1.75 inherit;margin:0}
mark{background:#fff3bf;padding:0 1px}
.gold{background:#eef4f1;border:1px solid #cfe0d8;border-radius:4px;padding:10px 12px;
      margin-bottom:14px}
.gold b{color:var(--accent)}
.f{border:1px solid var(--line);border-radius:4px;padding:10px 12px;margin-bottom:10px;
   background:#fff}
.f .h{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;margin-bottom:5px}
.tag{font-size:11px;padding:1px 6px;border-radius:3px;border:1px solid var(--line);
     color:var(--mut)}
.tag.rule{background:#eef2f7;border-color:#cdd8e6;color:#26456b}
.tag.llm{background:#f7f0ee;border-color:#e6d2cd;color:#7a3b2c}
.tag.ng{background:#fdecea;border-color:#f3c9c4;color:var(--ng)}
.f .t{font-weight:600;font-size:13px}
.f .r{color:var(--mut);font-size:12px;margin-top:3px}
.f .fix{margin-top:6px;font-size:12px;color:#2b4a3f;background:#f2f7f4;
        border-left:2px solid var(--accent);padding:4px 8px}
.ev{border:1px solid var(--line);border-radius:4px;padding:9px 11px;margin-bottom:9px}
.ev .n{font-size:11px;color:var(--mut)}
.ev .b{font-size:12px;color:#333;margin-top:4px;white-space:pre-wrap;
       max-height:130px;overflow:auto}
.none{color:var(--mut);font-size:12px;padding:8px 0}
"""

JS = """
const DATA = __DATA__;
let cur = Object.keys(DATA)[0];
function esc(s){const d=document.createElement('div');d.textContent=s==null?'':s;return d.innerHTML}
function render(){
  const d = DATA[cur];
  document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('on',b.dataset.id===cur));
  // 광고 원문 — 인용된 문구를 표시
  let t = esc(d.text);
  (d.quotes||[]).forEach(q=>{ if(!q) return;
    const e = esc(q).slice(0,60);
    if(e && t.includes(e)) t = t.split(e).join('<mark>'+e+'</mark>');
  });
  document.getElementById('ad').innerHTML = t;
  // 심의사례 정답
  document.getElementById('gold').innerHTML = d.gold
    ? '<div class="gold"><b>심의사례가 적은 지적</b><br>'+esc(d.gold.지적)
      +'<br><span style="color:#6b6b6b;font-size:12px">근거 '+esc(d.gold.근거원문)
      +' · 판본 근거: '+esc(d.gold.판본근거)+'</span></div>'
    : '';
  // 지적
  const fs = d.findings||[];
  document.getElementById('find').innerHTML = fs.length ? fs.map(f=>
    '<div class="f"><div class="h"><span class="tag ng">'+esc(f.판정||'NG')+'</span>'
    +'<span class="tag '+(f.판정근거==='LLM'?'llm':'rule')+'">'+esc(f.판정근거||'RULE')+'</span>'
    +'<span class="t">'+esc(f.제목||f.지적유형)+'</span></div>'
    +'<div class="r">'+esc(f.사유||'')+'</div>'
    +(f.근거규정?'<div class="r">근거 '+esc(f.근거규정)+'</div>':'')
    +(f.개선안?'<div class="fix">'+esc(f.개선안)+'</div>':'')
    +'</div>').join('') : '<div class="none">지적 없음</div>';
  // 근거 조문
  const ev = d.evidences||[];
  document.getElementById('ev').innerHTML = ev.length ? ev.map(e=>
    '<div class="ev"><div class="n">'+esc(e.evidence_id)+' · '+esc(e.article_no||'')
    +(e.점수!=null?' · 점수 '+Number(e.점수).toFixed(3):'')+'</div>'
    +'<div style="font-weight:600;font-size:12px;margin-top:2px">'+esc(e.title)+'</div>'
    +'<div class="b">'+esc(e.본문)+'</div></div>').join('')
    : '<div class="none">검색된 근거 없음</div>';
}
document.querySelectorAll('nav button').forEach(b=>
  b.onclick=()=>{cur=b.dataset.id;render()});
render();
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    ads = {}
    for x in (load("ads.jsonl") or []):
        ads.setdefault(x["광고id"], x)
    gold = {g["광고id"]: g for g in (load("ad_gold.json", {"건": []})["건"])}
    checks = {}
    for p in ("예금", "대출"):
        for c in (load(f"checks_{p}.json", {"checks": []})["checks"]):
            checks[c["id"]] = c

    # 룰 판정을 지금 돌려 넣는다. LLM 결과가 있으면 같이 얹는다.
    import rule_match as RM
    data = {}
    for aid, ad in sorted(ads.items()):
        product = "예금" if "예금성" in aid else "대출"
        try:
            rules = RM.load_rules(product=product)
        except Exception as e:
            print(f"규칙 로드 실패({product}): {e}")
            rules = []
        fs = []
        for x in RM.audit(ad["text"], rules):
            if x["판정"] != "NG":
                continue
            c = checks.get(x["규칙ID"], {})
            fs.append({"제목": x["요약"], "판정": "NG", "판정근거": "RULE",
                       "사유": f"찾던 문구 {x['문구']} — 광고에 없음",
                       "근거규정": c.get("article_no") or x.get("근거"),
                       "개선안": c.get("recommendation")})
        data[aid] = {
            "text": ad["text"],
            "gold": gold.get(aid),
            "findings": fs,
            "quotes": [],
            "evidences": [],
        }

    body = (
        f"<header><h1>광고 심의 — 작업 결과 보기</h1>"
        f"<span class='m'>광고 {len(data)}건 · 심의사례 정답 {len(gold)}건 · "
        f"판정 규칙 {len(checks)}건</span>"
        f"<span class='m'>지적은 룰 판정만. LLM 판정은 코랩 결과를 넣으면 함께 보인다</span>"
        "</header>"
        "<nav>" + "".join(
            f"<button data-id='{esc(k)}'>{esc(k)}"
            + ("<span style='color:#b3261e'> ●</span>" if gold.get(k) else "")
            + "</button>" for k in data) + "</nav>"
        "<main>"
        "<section><h2>광고 원문</h2><pre class='ad' id='ad'></pre></section>"
        "<section><h2>지적</h2><div id='gold'></div><div id='find'></div></section>"
        "<section><h2>근거 조문 (검색)</h2><div id='ev'></div></section>"
        "</main>"
    )
    page = ("<!doctype html><meta charset='utf-8'><title>광고 심의 결과</title>"
            f"<style>{CSS}</style>{body}"
            f"<script>{JS.replace('__DATA__', json.dumps(data, ensure_ascii=False))}</script>")

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    open(a.out, "w", encoding="utf-8").write(page)
    print(f"광고 {len(data)}건 · 지적 {sum(len(v['findings']) for v in data.values())}건")
    print(f"저장: {a.out}  ({os.path.getsize(a.out)/1e6:.1f}MB)")
    print("\n● 표시가 붙은 광고에는 심의사례 정답이 있다 — 그것부터 보면 된다.")


if __name__ == "__main__":
    main()
