# -*- coding: utf-8 -*-
"""LLM 호출 — Gemma. OpenAI 호환 인터페이스 하나로 감싼다.

**엔드포인트를 아직 모른다.** 그래서 주소를 환경변수로 두고, 없으면 목(mock)으로
돈다. 나중에 주소만 넣으면 나머지는 그대로다.

  GEMMA_BASE_URL=http://... GEMMA_MODEL=gemma-3-27b-it python rag/pipeline.py

목이 있는 이유는 편의가 아니다. **LLM 없이도 검색·리랭킹·조립을 끝까지 돌려 봐야**
엔드포인트가 열렸을 때 고칠 곳이 LLM 호출부 하나로 좁혀진다. 목이 없으면 파이프라인
전체가 「돌려본 적 없는 코드」로 남는다.

목은 **그럴듯한 가짜를 만들지 않는다.** 판정문을 지어내면 사람이 그걸 성능으로 착각한다.
질의 생성은 규칙 기반으로 실제로 쓸 만한 것을 내고, 판정은 「목이라 판정 못 함」을
분명히 말한다.
"""
import os
import re
import json

BASE_URL = os.environ.get("GEMMA_BASE_URL", "").rstrip("/")
MODEL = os.environ.get("GEMMA_MODEL", "gemma-3-27b-it")
API_KEY = os.environ.get("GEMMA_API_KEY", "not-needed")
TIMEOUT = float(os.environ.get("GEMMA_TIMEOUT", "120"))


def available():
    return bool(BASE_URL)


def chat(messages, temperature=0.0, max_tokens=1024, json_mode=False):
    """OpenAI 호환 /chat/completions. 주소가 없으면 None 을 준다(호출부가 목으로 간다)."""
    if not BASE_URL:
        return None
    import urllib.request

    body = {"model": MODEL, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {API_KEY}"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        out = json.loads(r.read().decode("utf-8"))
    return out["choices"][0]["message"]["content"]


# ── 목 ────────────────────────────────────────────────────────────────────
# 광고문에서 실제로 쟁점이 되는 표현을 잡아 질의로 만든다. 규칙리스트의 카테고리와
# 같은 말을 쓰도록 골랐다 — 검색이 걸리는지 보려면 질의가 그 어휘를 써야 한다.
_TRIGGERS = [
    (r"연\s*최고|최대\s*연|우대금리|우대\s*이율",
     "이자율의 범위와 산출기준, 우대금리 적용 조건을 표시해야 하는 의무"),
    (r"최저\s*연|금리\s*범위|연\s*\d+(\.\d+)?%\s*[~∼-]",
     "대출금리 범위와 기준금리·가산금리 산출기준 표시 의무"),
    (r"한도\s*최대|최대\s*\d+\s*억|최대\s*\d+\s*만원",
     "대출한도 표시 시 차감 조건 등 제한사항을 함께 표시하는 의무"),
    (r"세전|세후|이자소득세|비과세", "이자 표시의 세전·세후 구분 표시 의무"),
    (r"연체|기한이익\s*상실|신용평점",
     "연체이자율과 과도한 차입의 신용평점 영향 경고 표시 의무"),
    (r"중도상환|해약금|수수료|부대비용",
     "수수료·중도상환해약금 등 부대비용 발생 사실의 표시 의무"),
    (r"예금자보호|보호\s*한도|5천만원", "예금자보호 대상 여부와 보호 한도 표시 의무"),
    (r"심의필|준법감시인", "준법감시인 심의필번호와 유효기간 표시 의무"),
    (r"이벤트|경품|추첨|사은품", "경품·추첨 광고의 당첨확률과 조건 표시 의무"),
    (r"1위|최초|최고의|유일|가장\s*높은",
     "1위·최초 등 배타적 표현의 객관적 근거 표시 의무"),
    (r"무료|공짜|0원", "무료·0원 표시의 조건과 제한사항 표시 의무"),
    (r"후기|체험|추천|인플루언서", "추천·보증 광고의 경제적 이해관계 공개 의무"),
    (r"\(광고\)|광고\s*문자|수신거부", "영리목적 광고성 정보 전송 시 표기 의무"),
    (r"원금\s*손실|투자위험|수익률",
     "투자광고의 원금손실 가능성 등 투자위험 표시 의무"),
]


def mock_queries(ad_text, k=8):
    """광고문 → 쟁점 질의. 걸린 것이 없으면 광고문 자체를 질의로 쓴다."""
    out = []
    for pat, q in _TRIGGERS:
        if re.search(pat, ad_text) and q not in out:
            out.append(q)
    if not out:
        # **빈 목록을 주면 안 된다.** 검색이 아무것도 못 받아 파이프라인이 조용히
        # 빈 결과를 내고, 그게 「걸린 규칙 없음」으로 보인다. 광고문을 그대로 쓴다.
        out = [ad_text[:300]]
    return out[:k]


MOCK_VERDICT = ("[목] Gemma 엔드포인트가 없어 판정을 생성하지 않았습니다. "
                "GEMMA_BASE_URL 을 넣으면 이 자리에 판정과 사유가 들어갑니다.")
