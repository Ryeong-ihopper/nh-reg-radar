# -*- coding: utf-8 -*-
"""
PDF / HWP 파일 → 텍스트 추출 유틸.

- PDF : pypdf 로 페이지별 텍스트 추출
- HWP : HWP 5.x(OLE 복합문서)를 olefile 로 열어 BodyText 섹션을 zlib 해제 후
        HWPTAG_PARA_TEXT(0x43) 레코드에서 UTF-16LE 텍스트를 뽑는다.
        (한글과컴퓨터 HWP 5.0 파일 구조 규격 기반)

extract(path) 가 확장자를 보고 알아서 분기한다. 실패 시 빈 문자열 반환.
"""
import os
import zlib
import struct

# ── PDF ─────────────────────────────────────────────────────────────────
def extract_pdf(path):
    """pdfplumber 우선(한글 단어 공백 보존 우수). 실패 시 pypdf 폴백."""
    try:
        import pdfplumber
        parts = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                parts.append(page.extract_text() or "")
        text = "\n".join(parts).strip()
        if text:
            return text
    except Exception:
        pass
    from pypdf import PdfReader
    reader = PdfReader(path)
    out = []
    for page in reader.pages:
        try:
            out.append(page.extract_text() or "")
        except Exception:
            out.append("")
    return "\n".join(out).strip()


# ── HWP 5.x ──────────────────────────────────────────────────────────────
# HWPTAG_PARA_TEXT 파싱 시 제어문자 분류 (WCHAR=2byte 단위)
_SKIP16 = {1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23}


def _para_text(data):
    """HWPTAG_PARA_TEXT 레코드 바이트 → 문자열."""
    out = []
    i, n = 0, len(data)
    while i + 1 < n:
        ch = data[i] | (data[i + 1] << 8)
        if ch in _SKIP16:          # 인라인/확장 컨트롤: 8 WCHAR(16byte) 차지
            i += 16
        elif ch == 13:             # 문단 끝
            out.append("\n")
            i += 2
        elif ch in (0, 10, 24, 25, 26, 27, 28, 29, 30, 31):  # 기타 문자 컨트롤 1 WCHAR
            i += 2
        elif 0xD800 <= ch <= 0xDBFF and i + 3 < n:
            # 서로게이트 쌍(BMP 밖 문자, 희귀 한자 등): 상위+하위를 합쳐 실제 코드포인트로.
            # 그냥 chr(ch) 하면 단독 서로게이트가 생겨 UTF-8 인코딩 시 에러가 난다.
            lo = data[i + 2] | (data[i + 3] << 8)
            if 0xDC00 <= lo <= 0xDFFF:
                out.append(chr(0x10000 + ((ch - 0xD800) << 10) + (lo - 0xDC00)))
                i += 4
            else:
                i += 2   # 짝 없는 서로게이트: 깨진 데이터로 보고 스킵
        else:
            out.append(chr(ch))
            i += 2
    return "".join(out)


def _records(buf):
    """HWP 레코드 스트림 → (tag_id, level, payload) 제너레이터."""
    i, n = 0, len(buf)
    while i + 4 <= n:
        header = struct.unpack_from("<I", buf, i)[0]
        i += 4
        tag = header & 0x3FF
        level = (header >> 10) & 0x3FF
        size = (header >> 20) & 0xFFF
        if size == 0xFFF:          # 확장 크기: 다음 4byte
            size = struct.unpack_from("<I", buf, i)[0]
            i += 4
        payload = buf[i:i + size]
        i += size
        yield tag, level, payload


def extract_hwp(path):
    import olefile
    if not olefile.isOleFile(path):
        return ""   # HWPX(zip/xml) 등은 미지원
    ole = olefile.OleFileIO(path)
    try:
        # 압축 여부: FileHeader 스트림 flags(0x24) bit0
        compressed = True
        if ole.exists("FileHeader"):
            fh = ole.openstream("FileHeader").read()
            if len(fh) >= 40:
                compressed = bool(struct.unpack_from("<I", fh, 36)[0] & 0x01)
        # BodyText/Section* 순서대로
        sections = sorted(
            ("/".join(e) for e in ole.listdir()
             if len(e) >= 2 and e[0] == "BodyText" and e[1].startswith("Section")),
            key=lambda s: int(s.rsplit("Section", 1)[1]),
        )
        texts = []
        for name in sections:
            raw = ole.openstream(name).read()
            buf = zlib.decompress(raw, -15) if compressed else raw
            for tag, _lvl, payload in _records(buf):
                if tag == 0x43:    # HWPTAG_PARA_TEXT
                    texts.append(_para_text(payload))
        return "\n".join(t for t in texts if t.strip()).strip()
    finally:
        ole.close()


# ── document-processor (표 구조 복원) ────────────────────────────────────
def _table_lines(t):
    """TableIR(cells=행들의 리스트) → 파이프 표 텍스트."""
    lines = []
    for row in t.cells:
        cells = [(getattr(c, "text", "") or "").strip().replace("\n", " ") for c in row]
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def _find_tables(node, depth=0):
    found = []
    if depth > 8:
        return found
    if "TableIR" in type(node).__name__:
        return [node]
    for attr in ("content", "children", "runs"):
        v = getattr(node, attr, None)
        if isinstance(v, list):
            for x in v:
                found.extend(_find_tables(x, depth + 1))
    return found


# 이미지는 텍스트로 바꿀 수 없다(OCR 미지원). 그렇다고 버리면 규정에 그림으로 들어간
# 표시 예시·도표가 흔적 없이 사라지고, 개정으로 그림이 바뀌어도 변경 감지가 못 잡는다.
# 그래서 **파일로 뽑아 두고, 본문에는 내용 해시가 박힌 한 줄을 남긴다** —
# 그림이 바뀌면 해시가 바뀌므로 기존 조문 diff 가 그대로 잡아낸다.
_IMG_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
            "image/bmp": ".bmp", "image/tiff": ".tif", "image/webp": ".webp"}


def _images_from(ir, out_dir=None):
    """DocIR → [{id, sha, ext, bytes}]. out_dir 을 주면 `<sha12><ext>` 로 저장."""
    import base64
    import hashlib
    out = []
    for img_id, asset in (getattr(ir, "assets", None) or {}).items():
        b64 = getattr(asset, "data_base64", None)
        if not b64:
            continue
        data = base64.b64decode(b64)
        sha = hashlib.sha256(data).hexdigest()[:12]
        ext = _IMG_EXT.get(getattr(asset, "mime_type", ""), ".bin")
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            fp = os.path.join(out_dir, sha + ext)
            if not os.path.exists(fp):      # 같은 그림은 한 번만 저장
                with open(fp, "wb") as f:
                    f.write(data)
        out.append({"id": str(img_id), "sha": sha, "ext": ext, "bytes": len(data)})
    return out


def extract_images(path, out_dir=None):
    """문서 안 이미지를 파일로 뽑는다. [{id, sha, ext, bytes}]"""
    from document_processor import DocIR
    return _images_from(DocIR.from_file(path), out_dir)


def _image_lines(imgs):
    """본문 끝에 붙일 이미지 목록. id 에 위치정보가 들어 있다
    (예: odl-img-p4.tbl1.tr2.tc1.p1 = 4쪽 표1 2행 1열)."""
    lines = [f"[이미지 {len(imgs)}개 — 본문에 그림으로 들어간 부분]"]
    for i, m in enumerate(imgs, 1):
        lines.append(f"  이미지{i:03d}  {m['sha']}{m['ext']}  ({m['id']})")
    return lines


def extract_docproc(path, image_dir=None):
    """document-processor 로 문단+표(구조 보존)를 문서 순서대로 텍스트화.
    표는 파이프(|) 표로 렌더링. HWP/HWPX/PDF/DOCX 지원(Java 런타임 필요).

    이미지가 있으면 본문 끝에 목록을 덧붙이고, image_dir 을 주면 파일로도 저장한다."""
    from document_processor import DocIR
    ir = DocIR.from_file(path)
    out = []
    for p in ir.paragraphs:
        tables = _find_tables(p)
        if tables:
            for t in tables:
                out.extend(_table_lines(t))
        else:
            txt = (getattr(p, "text", "") or "").strip()
            if txt:
                out.append(txt)
    imgs = _images_from(ir, image_dir)
    if imgs:
        out.append("")
        out.extend(_image_lines(imgs))
    return "\n".join(out).strip()


# ── 추출 진입점 ───────────────────────────────────────────────────────────
SUPPORTED = (".pdf", ".hwp", ".hwpx", ".docx", ".doc")


class ExtractionError(RuntimeError):
    """문서 추출 실패. **폴백하지 않고 실패로 끝낸다.**

    예전에는 document-processor 가 실패하면 경량 추출기로 조용히 넘어갔는데,
    경량 추출기는 표를 한 줄로 뭉갠다(규정 문서는 표 비중이 크다).
    그러면 자바가 없는 환경에서 "잘 돌아간다"고 착각한 채 품질이 깨진 데이터를
    쌓게 된다. 차라리 즉시 실패해서 환경 문제를 드러내는 편이 낫다.
    """


def require_docproc():
    """document-processor 와 자바 런타임이 실제로 동작하는지 확인."""
    try:
        from document_processor import DocIR   # noqa: F401
    except Exception as e:
        raise ExtractionError(
            "document-processor 를 불러올 수 없습니다. 설치가 필요합니다:\n"
            "  pip install git+https://github.com/CGINSIDE-ROOKIES/document-processor.git"
        ) from e
    try:
        import jpype
        jpype.getDefaultJVMPath()
    except Exception as e:
        raise ExtractionError(
            "자바 런타임(JRE 17+)을 찾을 수 없습니다. document-processor 는 자바 기반이라 "
            "자바 없이는 표 구조를 복원할 수 없습니다.\n"
            "  JRE 설치 후 JAVA_HOME 을 설정하세요 (예: Eclipse Temurin)."
        ) from e
    return True


def extract(path):
    """PDF/HWP/HWPX/DOCX → 텍스트(표 구조 보존). 실패하면 예외를 던진다.

    표를 살리는 경로는 document-processor 하나뿐이므로 폴백하지 않는다.
    extract_pdf / extract_hwp 는 남겨두었지만 **교차검증 용도로만** 직접 호출한다
    (검수 뷰어가 두 파서 결과를 비교할 때 쓴다).
    """
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED:
        raise ExtractionError(f"지원하지 않는 형식입니다: {ext} ({os.path.basename(path)})")
    require_docproc()
    # 이미지는 원본 파일 옆 _img/ 에 모아 둔다(같은 그림은 해시가 같아 한 번만 저장)
    image_dir = os.path.join(os.path.dirname(os.path.abspath(path)), "_img")
    try:
        text = extract_docproc(path, image_dir=image_dir)
    except Exception as e:
        raise ExtractionError(f"{os.path.basename(path)} 추출 실패: {e}") from e
    if not text.strip():
        raise ExtractionError(
            f"{os.path.basename(path)} 에서 텍스트를 얻지 못했습니다. "
            "스캔 이미지 PDF 이거나 파일이 손상됐을 수 있습니다(OCR 미지원).")
    return text


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    if not sys.argv[1:]:
        require_docproc()
        print("document-processor / 자바 런타임 정상")
    for p in sys.argv[1:]:
        t = extract(p)
        print(f"### {os.path.basename(p)}  ({len(t)}자)")
        print(t[:600])
        print("-" * 60)
