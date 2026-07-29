# -*- coding: utf-8 -*-
"""
금융투자협회(KOFIA) 법규정보시스템 어댑터  ── law.kofia.or.kr

법제처와 달리 공식 API가 없지만, 정형화된 서버 엔드포인트로 규정 목록/본문/개정본ID를
얻을 수 있어 사실상 API처럼 사용한다.

  - lawCurrentPartTree.do            : 현행 규정 전체 목록(각 규정의 seq, historySeq 포함)
  - lawFullScreenContent.do?seq&hseq : 규정 본문(HTML, 조문 전문 포함)

변경 감지 키 = historySeq(개정본ID). 개정될 때마다 새 값이 발급된다.

check_updates.py 가 어댑터로 쓰는 인터페이스:
  current_meta(name, kind) / _version_key(meta) / collect(name, kind, want_files, verbose)
"""
import os
import re
import sys
import json
import html as htmllib
import http.client
import time
import file_text
import urllib.error
import urllib.request
from content_hash import sha256_structure

sys.stdout.reconfigure(encoding="utf-8")

SITE = "https://law.kofia.or.kr"
TREE_URL = SITE + "/service/law/lawCurrentPartTree.do"
BODY_URL = SITE + "/service/law/lawFullScreenContent.do"
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "output")
_body_cache = {}


class TruncatedResponse(Exception):
    """응답이 끝까지 오지 않음 (금투협 서버가 종종 중간에 끊는다)."""


def _get(url, retries=6, allow_partial=False, require_end=True):
    """금투협 서버는 3번에 1번꼴로 응답을 ~32KB 에서 끊는다.

    끊긴 응답을 그대로 파싱하면 뒤쪽 조문이 통째로 사라져 '대량 삭제'로
    오탐하므로, 문서 끝(</html>)까지 왔는지 확인하고 아니면 다시 받는다.
    allow_partial=True 는 개정본 번호만 뽑는 연혁 목록처럼 일부만 있어도
    되는 곳에서만 쓴다.
    """
    last_error = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0", "Connection": "close"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                html = r.read().decode("utf-8", errors="replace")
            # 서버가 정상 종료로 끊어도 내용이 잘려 있을 수 있어 끝을 확인한다
            if require_end and not allow_partial and "</html>" not in html[-2000:].lower():
                raise TruncatedResponse(f"{len(html):,}자에서 끊김")
            return html
        except http.client.IncompleteRead as e:
            last_error = e
            if allow_partial and e.partial:
                return e.partial.decode("utf-8", errors="replace")
        except TruncatedResponse as e:
            last_error = e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_error = e
        if attempt + 1 < retries:
            time.sleep(0.4 * (attempt + 1))
    raise last_error


def _safe(name):
    for c in '\\/:*?"<>|':
        name = name.replace(c, "_")
    return name.strip()


def _clean(s):
    s = htmllib.unescape(s).replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", s).strip()


def _text_with_breaks(frag):
    """블록 요소 경계에 줄바꿈을 넣고 태그를 제거해 읽기 좋은 텍스트로."""
    frag = re.sub(r'(?i)<div[^>]*class="(?:hang|ho|dann|none)"', "\n\\g<0>", frag)
    frag = re.sub(r"(?i)<tr[^>]*>", "\n", frag)
    frag = re.sub(r"(?i)<br\s*/?>", "\n", frag)
    frag = re.sub(r"<[^>]+>", "", frag)
    lines = [_clean(x) for x in htmllib.unescape(frag).split("\n")]
    return "\n".join(x for x in lines if x)


# ── 목록/버전 조회 ──────────────────────────────────────────────────────
def _find_in_tree(name):
    """규정 트리에서 이름이 일치하는 항목의 (규정명, seq, historySeq) 반환."""
    html = _get(TREE_URL)
    key = name.replace(" ", "")
    for m in re.finditer(r"gotoLawList\(([^)]*)\)", html):
        args = [a.strip().strip("'\"") for a in m.group(1).split(",")]
        if len(args) < 3:
            continue
        title = args[2]
        if title.replace(" ", "") == key:
            seq = args[0]
            hseq = args[-2] if args[-1] == "" else args[-1]  # 끝 빈값 앞이 historySeq
            return title, seq, hseq
    # 정확 일치 없으면 부분 일치
    for m in re.finditer(r"gotoLawList\(([^)]*)\)", html):
        args = [a.strip().strip("'\"") for a in m.group(1).split(",")]
        if len(args) >= 3 and key in args[2].replace(" ", ""):
            return args[2], args[0], (args[-2] if args[-1] == "" else args[-1])
    return None


def current_meta(name, kind="kofia", deep=False):
    found = _find_in_tree(name)
    if not found:
        return None
    title, seq, hseq = found
    meta = {"name": title, "kind": "kofia", "MST": str(hseq), "ID": str(seq),
            "시행일자": "", "버전번호": str(hseq)}
    if deep:
        url = f"{BODY_URL}?seq={seq}&historySeq={hseq}"
        html = _get(url)
        articles, addenda, last_date = _parse_body(html)
        _body_cache[(str(seq), str(hseq))] = (html, articles, addenda, last_date)
        meta["시행일자"] = last_date
        meta["content_hash"] = sha256_structure({"조문": articles, "부칙": addenda})
    return meta


def _official_version_key(meta):
    return f"{meta['ID']}|{meta['MST']}"   # seq|historySeq


def _version_key(meta):
    official = _official_version_key(meta)
    content_hash = meta.get("content_hash")
    return f"{official}|sha256:{content_hash}" if content_hash else official


# ── 본문 파싱 ───────────────────────────────────────────────────────────
# 페이지 맨 아래 별표/서식 첨부 목록의 시작 지점.
# 이 아래는 조문·부칙 본문이 아니라 다운로드 링크 목록이므로 잘라낸다.
# 안 자르면 목록 50줄이 **마지막 부칙 본문 안으로 딸려 들어가**, 그 부칙이 신설될 때
# 별표가 통째로 새로 생긴 것처럼 보인다(실제로 그렇게 오표시된 적 있음).
_ATTACH_ANCHOR = re.compile(r'(?i)<a\s+name="inclosure"|\[\s*별표\s*/\s*서식\s*파일\s*\]')


def _strip_attachment_block(html):
    m = _ATTACH_ANCHOR.search(html)
    return html[:m.start()] if m else html


def _parse_body(html):
    """규정 본문 HTML → (조문 리스트, 부칙 리스트, 최근부칙일자)."""
    html = _strip_attachment_block(html)
    # 본칙 / 부칙 경계 = 첫 addenda
    first_add = re.search(r'<div class="addenda"', html)
    boncheok = html[:first_add.start()] if first_add else html
    buchik_html = html[first_add.start():] if first_add else ""

    # 본칙: chapter/section/JO 시작 마커를 순서대로 훑는다
    articles = []
    cur_chapter = cur_section = ""
    marks = list(re.finditer(r'<div class="(chapter|section|JO)"[^>]*>', boncheok))
    for i, mk in enumerate(marks):
        mtype = mk.group(1)
        seg = boncheok[mk.start():marks[i + 1].start() if i + 1 < len(marks) else len(boncheok)]
        if mtype == "chapter":
            t = _clean(re.sub(r"<[^>]+>", "", seg))
            if t and not t.startswith("<") and "제목개정" not in t:
                cur_chapter, cur_section = t, ""
        elif mtype == "section":
            t = _clean(re.sub(r"<[^>]+>", "", seg))
            if t and not t.startswith("<") and "제목개정" not in t:
                cur_section = t
        else:  # JO
            # 조제목 셀 찾기. 개정 이력이 있는 조문은 제목 앞에 '연혁보기' 아이콘 칸이
            # 하나 더 붙으므로, 무조건 첫 <td>를 쓰면 빈 제목이 된다(316개 중 34개).
            # 조번호(제2-5조 / 제2-5조의2)가 들어있는 칸을 우선 고르고, 없으면 첫 비어있지
            # 않은 칸을 쓴다.
            head = re.search(r'class="article".*?</table>', seg, re.S)
            tds = re.findall(r"<td[^>]*>(.*?)</td>", head.group(0), re.S) if head else []
            cands = [_clean(re.sub(r"<[^>]+>", "", td)) for td in tds]
            cands = [c for c in cands if c]
            title = next((c for c in cands if re.match(r"제\s*\d+(?:-\d+)?조", c)),
                         cands[0] if cands else "")
            # 표준내부통제기준처럼 제1편 앞에 안내문 블록이 하나 오는 규정이 있다.
            # 조번호가 없으므로 그대로 두면 diff 키가 잡히지 않아 가짜 변경이 난다.
            if not title and not articles:
                title = "머리말"
            body_html = re.sub(r'<div class="article">.*?</table>\s*</div>', "", seg,
                               count=1, flags=re.S)
            body = _text_with_breaks(body_html)
            if title or body:
                articles.append({"장": cur_chapter, "절": cur_section,
                                 "조제목": title, "조내용": body})

    # 부칙: addenda 마다 하나
    addenda = []
    parts = re.split(r'(?=<div class="addenda")', buchik_html)
    for p in parts:
        if 'class="addenda"' not in p:
            continue
        hm = re.search(r'<div class="addenda"[^>]*>(.*?)</div>', p, re.S)
        header = _clean(re.sub(r"<[^>]+>", "", hm.group(1))) if hm else ""
        rest = p[hm.end():] if hm else p
        body = _text_with_breaks(rest)
        addenda.append({"부칙명": header, "내용": body})

    last_date = ""
    if addenda:
        dm = re.search(r"(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})", addenda[-1]["부칙명"])
        if dm:
            last_date = f"{dm.group(1)}{int(dm.group(2)):02d}{int(dm.group(3)):02d}"
    return articles, addenda, last_date


# ── 별표·별지 첨부 ──────────────────────────────────────────────────────
# 금투협 규정 본문 아래에 별표/별지가 HWP 첨부로 달려 있다(이 규정은 50개).
# 법제처와 달리 조문 JSON 안에 별표가 없어서, 본문 HTML 의 첨부 링크를 긁어야 한다.
_ATTACH = re.compile(
    r'href="(/download\.do\?gubun=\d+&(?:amp;)?seq=\d+)"[^>]*>\s*([^<]{3,120}?)\s*<')
# 표시명 "12. 0011_(별표 8-2).hwp" → 순번과 실제 이름 분리
_ATTACH_NAME = re.compile(r"^\s*\d+\.\s*(.+?)\s*$")


def parse_attachments(html):
    """[{순번, 파일명, 링크, 구분, 번호}] — 등장 순서."""
    out, seen = [], set()
    for i, (href, label) in enumerate(_ATTACH.findall(html), 1):
        href = href.replace("&amp;", "&")
        if href in seen:
            continue
        seen.add(href)
        m = _ATTACH_NAME.match(label)
        fname = (m.group(1) if m else label).strip()
        # "(별표 8-2)" / "(별지 제10-1호)" 에서 구분과 번호를 뽑아 안정적인 키로 쓴다
        km = re.search(r"\((별[표지])\s*(?:제)?\s*([\d\-]+)\s*(?:호)?\)", fname)
        out.append({
            "순번": i, "파일명": fname, "링크": SITE + href,
            "구분": km.group(1) if km else "첨부",
            "번호": km.group(2) if km else str(i),
            "삭제여부": "삭제" in fname,
        })
    return out


def download_attachments(attachments, name, verbose=True):
    """첨부를 output/files/<규정명>/ 에 저장. 저장한 파일명을 각 항목에 기록."""
    if not attachments:
        return 0
    d = os.path.join(OUT_DIR, "files", _safe(name))
    os.makedirs(d, exist_ok=True)
    n = 0
    for a in attachments:
        try:
            data = _get_binary(a["링크"])
        except Exception as e:
            if verbose:
                print(f"    ! 첨부 실패 {a['파일명']}: {e}")
            a["저장파일"] = ""
            continue
        a["저장파일"] = _safe(a["파일명"])
        fpath = os.path.join(d, a["저장파일"])
        with open(fpath, "wb") as f:
            f.write(data)
        # 법제처는 별표 본문을 API 가 텍스트로 주지만, 금투협은 **HWP 첨부로만** 준다.
        # 파일만 받아 두면 별표 내용이 텍스트로는 존재하지 않게 되어
        # 검색도 안 되고 개정돼도 변경 감지가 못 잡는다(143개·68만 자가 그 상태였다).
        # 그래서 여기서 바로 추출해 '내용' 에 채운다. 이미지도 같이 딸려 온다.
        try:
            a["내용"] = file_text.extract(fpath)
        except Exception as e:
            a["내용"] = ""
            a["추출오류"] = str(e)[:150]
            if verbose:
                print(f"    ! 첨부 추출 실패 {a['파일명']}: {str(e)[:80]}")
        n += 1
    return n


def _get_binary(url, retries=10):
    """첨부 다운로드. 본문과 마찬가지로 응답이 중간에 끊기는 일이 잦아
    **Content-Length 만큼 다 받았는지 확인**하고 아니면 다시 받는다.
    잘린 HWP 를 저장하면 나중에 파싱만 실패하고 원인을 찾기 어렵다."""
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0", "Referer": BODY_URL, "Connection": "close"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                expect = r.headers.get("Content-Length")
                data = r.read()
            if expect and len(data) != int(expect):
                raise TruncatedResponse(f"{len(data):,}/{int(expect):,} bytes")
            if not data:
                raise TruncatedResponse("빈 응답")
            return data
        except http.client.IncompleteRead as e:
            last = e
        except TruncatedResponse as e:
            last = e
        except Exception as e:
            last = e
        if attempt + 1 < retries:
            time.sleep(0.4 * (attempt + 1))
    raise last


# ── 개정 이력 ───────────────────────────────────────────────────────────
HISTORY_URL = SITE + "/service/law/lawHistoryList.do"


def history(seq):
    """규정의 개정본 목록(historySeq)을 최신순으로 반환.
    과거 버전을 받아 실제 개정 diff 를 만들 때 쓴다."""
    # 이 엔드포인트는 응답이 자주 중간에 끊긴다. 개정본 번호만 뽑으면 되므로
    # 받은 만큼으로 진행한다(최신 개정본은 앞쪽에 나온다).
    html = _get(f"{HISTORY_URL}?seq={seq}", allow_partial=True)
    seen, out = set(), []
    for m in re.finditer(r"(?:historySeq|hseq)[^0-9]{0,6}(\d{3,6})", html):
        v = m.group(1)
        if v not in seen:
            seen.add(v)
            out.append(v)
    return sorted(out, key=int, reverse=True)


# ── 레코드 생성 / 수집 ──────────────────────────────────────────────────
def build_record(name, seq, hseq, tables=None):
    """특정 개정본(seq, historySeq)의 레코드와 사람이 읽는 텍스트를 만든다.
    현재본 수집과 과거본 적재가 같은 코드를 쓰도록 분리해 둔 것.

    tables 를 주면 첨부 목록을 다시 긁지 않고 그대로 쓴다. 첨부를 내려받아
    '내용' 을 채운 뒤 TXT 를 다시 만들 때 쓴다(안 주면 별표가 제목만 남는다).
    """
    url = f"{BODY_URL}?seq={seq}&historySeq={hseq}"
    cached = _body_cache.get((str(seq), str(hseq)))
    if cached:
        html, articles, addenda, last_date = cached
    else:
        html = _get(url)
        articles, addenda, last_date = _parse_body(html)
    if tables is None:
        tables = parse_attachments(html)   # 별표·별지 (본문 JSON 이 아니라 HTML 첨부로 제공)
    meta = {"name": name, "kind": "kofia", "MST": str(hseq), "ID": str(seq),
            "시행일자": last_date, "버전번호": str(hseq),
            "content_hash": sha256_structure(
                {"조문": articles, "부칙": addenda,
                 "별표": [{k: t[k] for k in ("구분", "번호", "파일명")} for t in tables]})}
    record = {
        "법령명": name, "종류": "kofia_규정", "발행기관": "금융투자협회",
        "seq": meta["ID"], "historySeq": meta["MST"], "버전키": _version_key(meta),
        "공식버전키": _official_version_key(meta), "본문해시": meta["content_hash"],
        "최근개정일": last_date, "시행일자": last_date, "출처": url,
        "통계": {"조문수": len(articles), "부칙수": len(addenda), "별표수": len(tables)},
        "조문": articles, "부칙": addenda, "별표": tables,
    }

    lines = [name, f"[금융투자협회 자율규제규정] 최근개정 {last_date or '?'} · "
             f"seq {meta['ID']} · 개정본 {meta['MST']}", "=" * 70, ""]
    cur_ch = cur_se = ""
    for a in articles:
        if a["장"] and a["장"] != cur_ch:
            cur_ch = a["장"]; lines += ["", "■ " + cur_ch]
        if a["절"] and a["절"] != cur_se:
            cur_se = a["절"]; lines += ["  ● " + cur_se]
        lines.append(a["조제목"])
        if a["조내용"]:
            lines.append(a["조내용"])
        lines.append("")
    if addenda:
        lines += ["", "─" * 70, "부   칙", "─" * 70, ""]
        for ad in addenda:
            lines += ["[" + ad["부칙명"] + "]", ad["내용"], ""]
    if tables:
        lines += ["", "─" * 70, "별표 / 별지", "─" * 70, ""]
        for t in tables:
            # 번호를 4자리로 채운다(법제처 형식과 통일). 화면의 별표 목록이
            # 본문 안 인용("[별표 1의2]")과 구분되도록 하기 위함.
            m = re.match(r"(\d+)(?:-(\d+))?$", str(t["번호"]))
            no = (f"{int(m.group(1)):04d}" + (f"의{int(m.group(2))}" if m.group(2) else "")
                  if m else str(t["번호"]))
            lines.append(f"[{t['구분']} {no}]"
                         + (" 삭제" if t["삭제여부"] else "")
                         + f"  (원본 파일: {t['파일명']})")
            # 첨부에서 뽑은 본문을 이어 붙인다. 이게 없으면 별표는 제목만 남는다.
            body = (t.get("내용") or "").strip()
            if body:
                lines.append(body)
            elif t.get("추출오류"):
                lines.append(f"  ! 내용 추출 실패: {t['추출오류']}")
            lines.append("")
    return record, "\n".join(lines)


def collect(name, kind="kofia", want_files=True, verbose=True):
    meta = current_meta(name, kind)
    if not meta:
        if verbose:
            print(f"  → '{name}' KOFIA 목록에서 못 찾음")
        return None
    record, text = build_record(meta["name"], meta["ID"], meta["MST"])
    if want_files and record["별표"]:
        n = download_attachments(record["별표"], meta["name"], verbose)
        if verbose:
            print(f"  → 별표/별지 파일 {n}/{len(record['별표'])}개 다운로드")
        # 별표 본문은 첨부를 받아 봐야 채워진다. TXT 는 그 뒤에 다시 만들어야
        # 별표 내용이 들어간다(안 그러면 제목만 남는다).
        record, text = build_record(meta["name"], meta["ID"], meta["MST"],
                                    tables=record["별표"])
    if verbose:
        print(f"  → 조문 {record['통계']['조문수']} · 부칙 {record['통계']['부칙수']} · "
              f"별표 {record['통계']['별표수']} · 최근개정 {record['최근개정일'] or '?'}")

    os.makedirs(OUT_DIR, exist_ok=True)
    base = _safe(meta["name"])
    with open(os.path.join(OUT_DIR, base + ".json"), "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT_DIR, base + ".txt"), "w", encoding="utf-8") as f:
        f.write(text)
    if verbose:
        print(f"  → 저장: output/{base}.json, output/{base}.txt")
    return record


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "금융투자회사의 영업 및 업무에 관한 규정"
    print(f"[KOFIA] {target}")
    collect(target)
