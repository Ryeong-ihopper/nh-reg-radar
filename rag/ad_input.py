# -*- coding: utf-8 -*-
"""광고를 **파서가 주는 모양 그대로** 받는다. 지금까지의 입력이 틀렸다.

지금까지 `ads.jsonl` 은 HWP 를 통째로 긁어 한 덩어리 문자열로 갖고 있었다.
실제 입력은 그게 아니다. document-processor 가 이렇게 준다.

    chunk_id  p001_s004
    page      1
    modality  image | text
    bbox      [80, 1360, 1042, 1820]
    text      "상품 유의사항  이 예금은 예금자보호법에 따라 …"
    quality.style.font_size_pt   8.0
    quality.style.font_weight    normal

**한 덩어리로 만들면서 버린 것이 판정에 꼭 필요한 것들이었다.**

  글자 크기   「유의사항 문구 글자크기 작음」 지적은 font_size_pt 없이 판정 불가
  좌표        어디가 문제인지 화면에 표시하려면 bbox 가 있어야 한다
  페이지·구획  「본문과 유의사항의 크기 비율」 같은 것은 구획이 나뉘어야 본다
  modality    이미지 영역은 OCR 신뢰도가 다르다. 같이 취급하면 안 된다

청킹은 **우리 일이 아니다.** 파서가 이미 나눠서 준다. 법령 청킹은 우리가 하지만
광고 청킹은 받는 것이다.

  python rag/ad_input.py                 # 목데이터 훑기
  python rag/ad_input.py --ad NH농협은행-2026_017-예금성
"""
import os
import re
import json
import glob
import argparse
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 목데이터(다른 저장소에 있다). **실물 판정에는 안 쓴다** — `--real` 을 볼 것.
MOCK = os.environ.get(
    "AD_MOCK_DIR",
    os.path.join(os.path.dirname(ROOT), "cg_ocr_vlm", "cloud_local", "mock_data"))


class Ad:
    """광고 하나. 파서 출력의 얇은 껍데기 — 값을 바꾸지 않는다.

    원문을 손대면 「광고에 이렇게 써 있다」는 근거가 흔들린다. 정규화가 필요하면
    비교하는 쪽에서 하고 여기 담긴 text 는 파서가 준 그대로 둔다.
    """

    def __init__(self, raw):
        self.raw = raw
        self.id = raw["document_id"]
        self.ad_id = raw.get("advertisement_id")
        self.chunks = raw.get("chunks") or []
        self.product = ("예금성" if "예금성" in self.id else
                        "대출성" if "대출성" in self.id else
                        "투자성" if "투자성" in self.id else None)

    @property
    def text(self):
        """전문. **판정의 기본 단위가 아니다** — 문구가 있나 없나만 볼 때 쓴다."""
        return "\n".join(c.get("text") or "" for c in self.chunks)

    def styled(self):
        """(청크, 글자크기). 크기가 없는 청크는 빼지 않고 None 으로 둔다 —
        빼 버리면 「크기 정보가 없어서 판정 못 함」과 「작지 않음」이 섞인다."""
        out = []
        for c in self.chunks:
            st = ((c.get("quality") or {}).get("style") or {})
            out.append((c, st.get("font_size_pt")))
        return out

    def body_size(self):
        """본문 글자 크기 = 가장 흔한 크기. 유의사항이 이것보다 많이 작으면 문제다."""
        sizes = [s for _, s in self.styled() if s]
        if not sizes:
            return None
        return collections.Counter(sizes).most_common(1)[0][0]

    def find(self, pattern):
        """정규식에 걸리는 청크 목록. **어느 청크에서 걸렸는지 남긴다** —
        전문에서 찾으면 화면에 표시할 좌표를 잃는다."""
        rx = re.compile(pattern)
        return [(c, m) for c in self.chunks
                if (m := rx.search(c.get("text") or ""))]


def load(path=MOCK):
    out = []
    for f in sorted(glob.glob(os.path.join(path, "ad_*.json"))):
        out.append(Ad(json.load(open(f, encoding="utf-8"))))
    return out


def labels(path=MOCK):
    f = os.path.join(path, "_labels.json")
    if not os.path.exists(f):
        return {}
    d = json.load(open(f, encoding="utf-8"))["advertisements"]
    return {k: (v.get("planted_violations") or []) for k, v in d.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=MOCK)
    ap.add_argument("--ad")
    a = ap.parse_args()

    ads = load(a.path)
    lab = labels(a.path)
    print(f"광고 {len(ads)}건 · 라벨 있는 것 {sum(1 for v in lab.values() if v)}건\n")

    kinds = collections.Counter(v for vs in lab.values() for v in vs)
    print("심어 놓은 위반 유형:")
    for k, v in kinds.most_common():
        print(f"  {v:2d}  {k}")

    print("\n광고별:")
    for ad in ads:
        md = collections.Counter(c["modality"] for c in ad.chunks)
        sz = [s for _, s in ad.styled() if s]
        print(f"  {ad.id:26s} {ad.product or '-':4s} 청크{len(ad.chunks):3d} "
              f"{dict(md)} 크기 {min(sz) if sz else '-'}~{max(sz) if sz else '-'} "
              f"본문 {ad.body_size() or '-'}  {lab.get(ad.id) or ''}")

    if a.ad:
        ad = next(x for x in ads if x.id == a.ad)
        print(f"\n== {ad.id} ==")
        for c, s in ad.styled():
            print(f"  {c['chunk_id']:12s} {c['modality']:6s} {str(s or '-'):>5} "
                  f"bbox={c['bbox']}  {(c['text'] or '')[:56]}")


if __name__ == "__main__":
    main()
