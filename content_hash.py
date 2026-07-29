# -*- coding: utf-8 -*-
"""규정 본문 구조를 결정적으로 직렬화해 해싱하는 공통 유틸리티."""
import hashlib
import json


def sha256_structure(value):
    """키 순서만 고정하고 문자열 내용은 원문 그대로 반영한 SHA-256."""
    canonical = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
