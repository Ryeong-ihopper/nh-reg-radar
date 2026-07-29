# -*- coding: utf-8 -*-
"""
HWP → PDF 변환 (검수 화면에서 원본을 눈으로 보기 위한 용도).

브라우저는 HWP 를 못 그린다. 여신협·은행연 규정은 원본이 HWP 뿐이라
변환하지 않으면 화면 대조가 불가능하다.

필요한 것 (둘 다 있어야 동작)
  1. LibreOffice          winget install TheDocumentFoundation.LibreOffice
  2. H2Orestart 확장       LibreOffice 기본 HWP 필터는 **HWP 3.0 전용**이라
                          HWP 5.x(현재 배포되는 형식)를 못 읽는다. 이 확장이 5.x 를 처리한다.
                          https://github.com/ebandal/H2Orestart/releases → .oxt
                          설치:  unopkg add --shared H2Orestart.oxt

변환 결과는 output/_review/_pdf/ 에 캐시한다(원본이 바뀌지 않으면 재변환 안 함).
"""
import os
import sys
import glob
import shutil
import hashlib
import subprocess

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, "output", "_review", "_pdf")

_CANDIDATES = [
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/usr/bin/soffice", "/usr/bin/libreoffice",
]


def soffice():
    """LibreOffice 실행 파일 경로. 없으면 None."""
    for p in _CANDIDATES:
        if os.path.exists(p):
            return p
    return shutil.which("soffice") or shutil.which("libreoffice")


def available():
    return soffice() is not None


def _key(path):
    """원본 파일 내용 기준 캐시 키(파일이 바뀌면 다시 변환)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def to_pdf(hwp_path, timeout=180, verbose=False):
    """HWP → PDF. 변환된 PDF 경로 반환. 실패하면 None."""
    exe = soffice()
    if not exe or not os.path.exists(hwp_path):
        return None
    os.makedirs(CACHE, exist_ok=True)
    out = os.path.join(CACHE, _key(hwp_path) + ".pdf")
    if os.path.exists(out) and os.path.getsize(out) > 1024:
        return out

    # 한글 파일명·대괄호가 변환기에서 문제를 일으켜 임시 이름으로 복사해 처리한다
    work = os.path.join(CACHE, "_work")
    os.makedirs(work, exist_ok=True)
    tmp = os.path.join(work, "src" + os.path.splitext(hwp_path)[1].lower())
    shutil.copy2(hwp_path, tmp)
    try:
        subprocess.run([exe, "--headless", "--norestore", "--convert-to", "pdf",
                        "--outdir", work, tmp],
                       timeout=timeout, capture_output=True)
        made = os.path.join(work, "src.pdf")
        if os.path.exists(made) and os.path.getsize(made) > 1024:
            shutil.move(made, out)
            return out
        if verbose:
            print(f"    ! 변환 실패: {os.path.basename(hwp_path)}")
        return None
    except subprocess.TimeoutExpired:
        if verbose:
            print(f"    ! 변환 시간초과: {os.path.basename(hwp_path)}")
        return None
    finally:
        shutil.rmtree(work, ignore_errors=True)


def convert_targets(patterns=("output/files/*/*.hwp", "output/files/*/*.hwpx"),
                    limit=None, verbose=True):
    """수집해둔 HWP 를 일괄 변환. (변환수, 실패수) 반환."""
    if not available():
        print("LibreOffice 가 없어 건너뜁니다. 설치: winget install TheDocumentFoundation.LibreOffice")
        return 0, 0
    files = []
    for p in patterns:
        files += glob.glob(os.path.join(ROOT, p))
    files = sorted(set(files))[:limit]
    ok = ng = 0
    for i, f in enumerate(files, 1):
        r = to_pdf(f, verbose=verbose)
        ok += bool(r)
        ng += not r
        if verbose and i % 10 == 0:
            print(f"  {i}/{len(files)} …")
    if verbose:
        print(f"HWP→PDF 변환: 성공 {ok} · 실패 {ng} (캐시: {os.path.relpath(CACHE, ROOT)})")
    return ok, ng


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not available():
        print("LibreOffice 를 찾을 수 없습니다.")
        sys.exit(1)
    print("LibreOffice:", soffice())
    if args:
        for a in args:
            print(a, "→", to_pdf(a, verbose=True))
    else:
        convert_targets(limit=None if "--all" in sys.argv else 5)
