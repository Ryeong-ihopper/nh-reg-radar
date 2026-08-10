# -*- coding: utf-8 -*-
"""LLM 호출 — Gemma. **GPU 로컬 로딩이 기본이고, 목은 없다.**

수요사는 온프렘 GPU(H200)에 모델을 직접 올린다. 코랩도 같은 모양이라
`transformers` 로 직접 얹는 경로를 기본으로 둔다. OpenAI 호환 HTTP 서버를
쓰는 곳이면 `GEMMA_BASE_URL` 만 넣으면 그쪽으로 간다.

    backend=local   transformers 로 GPU 에 직접 (코랩·DAP·H200)   ← 기본
    backend=http    OpenAI 호환 /chat/completions                 GEMMA_BASE_URL

**목(mock)을 걷어냈다.** 전에는 엔드포인트가 없으면 목 판정이 나갔는데, 그
결과가 `audit.json`·`review_items.json` 에 정상 산출물과 같은 모양으로 쌓였다
(실측: audit 18건·review 7건 전부 `_source=mock`). 성능처럼 보이는 가짜가
파일에 남는 것이 LLM 이 없는 것보다 위험하다. 이제 못 부르면 **바로 죽는다.**

  python rag/pipeline.py --ad 2026_001_대출성          # 로컬 GPU 에 Gemma 를 올린다
  GEMMA_BASE_URL=http://… python rag/pipeline.py …     # HTTP 서버를 쓴다
"""
import os
import json

BASE_URL = os.environ.get("GEMMA_BASE_URL", "").rstrip("/")
API_KEY = os.environ.get("GEMMA_API_KEY", "not-needed")
TIMEOUT = float(os.environ.get("GEMMA_TIMEOUT", "300"))

# 모델 ID 는 노트북에서 실제로 돌려 본 것만 쓴다. 「gemma-4-12B-Unified-it」
# 처럼 없는 ID 를 적었다가 한 번 깨진 적이 있다(커밋 ee7ce6c).
MODEL = os.environ.get("GEMMA_MODEL", "")
_MODELS = [(26, "google/gemma-4-12B-it", False),   # bf16 — 4bit 보다 5~10배 빠르다
           (14, "google/gemma-4-12B-it", True),    # 4bit
           (0,  "google/gemma-4-E4B-it", False)]

_M = None          # (tokenizer, model)


class LLMUnavailable(RuntimeError):
    """LLM 을 못 부른다. **삼키지 말 것** — 판정을 만들면 안 된다."""


def pick_model():
    """GPU 메모리를 보고 모델을 고른다. (모델ID, 4bit여부)"""
    if MODEL:
        return MODEL, os.environ.get("GEMMA_4BIT", "") == "1"
    try:
        import torch
        free = (torch.cuda.get_device_properties(0).total_memory / 1e9
                if torch.cuda.is_available() else 0)
    except Exception:
        free = 0
    for need, name, fourbit in _MODELS:
        if free >= need:
            return name, fourbit
    return _MODELS[-1][1], False


def load(model=None, fourbit=None, verbose=True):
    """Gemma 를 GPU 에 올린다. 두 번째 호출부터는 올려 둔 것을 쓴다."""
    global _M
    if _M is not None:
        return _M
    import torch
    from transformers import (AutoTokenizer, AutoModelForCausalLM,
                              BitsAndBytesConfig)
    if model is None:
        model, auto4 = pick_model()
        fourbit = auto4 if fourbit is None else fourbit
    kw = {"device_map": "auto"}
    if fourbit:
        kw["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True)
    else:
        kw["torch_dtype"] = torch.bfloat16
    tok = AutoTokenizer.from_pretrained(model)
    m = AutoModelForCausalLM.from_pretrained(model, **kw)
    m.eval()
    if verbose:
        print(f"Gemma {model} ({'4bit' if fourbit else 'bf16'}) · "
              f"{m.get_memory_footprint()/1e9:.1f}GB")
    _M = (tok, m)
    return _M


def backend():
    if BASE_URL:
        return "http"
    try:
        import torch
        import transformers  # noqa: F401
        return "local" if torch.cuda.is_available() else "local-cpu"
    except ImportError:
        return None


def available():
    return backend() is not None


def _chat_local(messages, max_tokens):
    import torch
    tok, m = load()
    # return_dict=True 를 명시한다 — 최신 transformers 는 텐서가 아니라
    # BatchEncoding 을 준다. 텐서인 줄 알고 .shape 를 부르면 죽는다(커밋 c06f5d5).
    enc = tok.apply_chat_template(messages, add_generation_prompt=True,
                                  return_dict=True, return_tensors="pt").to(m.device)
    with torch.no_grad():
        out = m.generate(**enc, max_new_tokens=max_tokens, do_sample=False,
                         pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][enc["input_ids"].shape[-1]:], skip_special_tokens=True)


def _chat_http(messages, temperature, max_tokens, json_mode):
    import urllib.request
    body = {"model": MODEL or "gemma", "messages": messages,
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


def chat(messages, temperature=0.0, max_tokens=1024, json_mode=False):
    """Gemma 에 묻는다. **못 부르면 예외를 낸다** — None 을 주지 않는다."""
    b = backend()
    if b is None:
        raise LLMUnavailable(
            "Gemma 를 못 부른다. 둘 중 하나가 필요하다 —\n"
            "  ① GPU + transformers (코랩·DAP): pip install transformers torch\n"
            "  ② OpenAI 호환 서버: GEMMA_BASE_URL=http://…")
    if b == "http":
        return _chat_http(messages, temperature, max_tokens, json_mode)
    return _chat_local(messages, max_tokens)


# ── 규칙 기반 질의 (실험 기준선) ──────────────────────────────────────────
# **이건 목이 아니라 비교 대상이다.** 「LLM 이 만든 질의」와 「규칙으로 만든 질의」
# 중 어느 쪽이 나은지 재려면 후자가 있어야 한다(`grid.py`·`measure.py`).
# 다만 **납품 경로에서는 안 쓴다** — 측정 결과 광고 청크를 그대로 던지는 쪽이
# 나아서 `pipeline.py` 는 질의 생성 단계 자체를 없앴다.
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


def rule_queries(ad_text, k=8):
    """광고문 → 쟁점 질의(규칙 기반). 걸린 것이 없으면 광고문 앞부분을 쓴다."""
    import re
    out = []
    for pat, q in _TRIGGERS:
        if re.search(pat, ad_text) and q not in out:
            out.append(q)
    if not out:
        # **빈 목록을 주면 안 된다.** 검색이 아무것도 못 받아 파이프라인이 조용히
        # 빈 결과를 내고, 그게 「걸린 규칙 없음」으로 보인다.
        out = [ad_text[:300]]
    return out[:k]


mock_queries = rule_queries      # 옛 이름(실험 스크립트 3개가 쓴다)


def extract_json(text):
    """모델 응답에서 JSON 을 꺼낸다. ```json 울타리와 앞뒤 군말을 걷어낸다."""
    s = (text or "").strip()
    if "```" in s:
        parts = s.split("```")
        for p in parts:
            p = p.strip()
            if p.startswith("json"):
                p = p[4:].strip()
            if p.startswith("{") or p.startswith("["):
                s = p
                break
    i, j = s.find("{"), s.rfind("}")
    if i >= 0 and j > i:
        s = s[i:j+1]
    return json.loads(s)
