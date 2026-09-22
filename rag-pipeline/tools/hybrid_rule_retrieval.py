# -*- coding: utf-8 -*-
"""규제항목 ID 없이 적용 규칙을 발견하는 공통 하이브리드 검색 함수.

운영 검색은 예금·대출·투자·전체 범위의 시인성 항목까지 포함한다. 227개 비시인성
범위는 과거 비교용 기본값으로만 유지한다. 표시의무·양식/절차 항목은
상품군 적용성으로 전개하고, 금지 항목은 광고 fine 청크에서 Elasticsearch의
Nori BM25와 BGE-M3 벡터검색으로 찾는다. 규칙을 유발한 광고 청크는 후속
판단의 최초 근거로 보존한다.

예측 함수는 gold·연구원 피드백·사례별 매핑을 입력으로 받지 않는다. 파일 아래의
옛 회귀 CLI는 실행을 막아 두었고, 현행 실행은 별도 데이터셋 래퍼가 담당한다.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import io
import json
import os
import sys
import tempfile
import time
import warnings
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from rag import build_items as v2_source  # noqa: E402
from build_ad_evidence_vectors import (  # noqa: E402
    MODEL_NAME,
)
from dgx_bge_client import validate_embeddings  # noqa: E402


SEARCH_DIR = ROOT / "output" / "_rag" / "search_0902_normalized"
REVIEW_DIR = ROOT / "output" / "_rag" / "review"
SERVICE_DIR = ROOT / "output" / "_rag" / "service_0903"
FINE = SEARCH_DIR / "evidence_fine.jsonl"
COARSE = SEARCH_DIR / "evidence_coarse.jsonl"
RULE_VECTORS = SERVICE_DIR / "v2_rule_vectors.f16.npy"
RULE_META = SERVICE_DIR / "v2_rule_vectors.meta.json"
FINE_VECTORS = SERVICE_DIR / "evidence_fine_vectors.f16.npy"
FINE_META = SERVICE_DIR / "evidence_fine_vectors.meta.json"
OUT = SERVICE_DIR / "service_discovery19_results.json"

DEFAULT_URL = "http://127.0.0.1:19201"
DEFAULT_INDEX = "regulation_v2_0903_v1"
SUPPORTED_POC_PRODUCT_GROUPS = ("예금성", "대출성", "투자성")
CONFIRMED_ROUTING_STATUSES = {"confirmed", "verified", "provided"}
def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def corpus_key(rows: list[dict[str, Any]], text_key: str) -> str:
    value = "\n".join(
        f"{row['doc_id']}\t{row[text_key]}" for row in rows
    ).encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def request(
    base_url: str,
    method: str,
    path: str,
    body: Any | None = None,
    *,
    content_type: str = "application/json",
) -> Any:
    data = None
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(
            body, ensure_ascii=False
        ).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        method=method,
        headers={"Content-Type": content_type},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Elasticsearch HTTP {exc.code}: {detail}") from exc
    return json.loads(raw) if raw else None


def index_exists(base_url: str, index: str) -> bool:
    req = urllib.request.Request(
        base_url.rstrip("/") + "/" + urllib.parse.quote(index, safe=""),
        method="HEAD",
    )
    try:
        with urllib.request.urlopen(req, timeout=30):
            return True
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise


def load_scope(*, include_layout: bool = False) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    items, _ = v2_source.build()
    by_id = {row["id"]: row for row in items}
    scoped = [
        row for row in items
        if (
            "전체" in row["적용상품"]
            or "예금성" in row["적용상품"]
            or "대출성" in row["적용상품"]
            or "투자성" in row["적용상품"]
        )
        and (include_layout or row["판정유형"] != "레이아웃필요")
    ]
    if len(by_id) != len(items):
        raise ValueError("duplicate source rule ID")
    if not include_layout and len(scoped) != 227:
        raise RuntimeError("v2 운영 실행범위가 227개가 아님")
    return scoped, by_id


def _flatten_text(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, dict):
        output: list[str] = []
        for key in ("요약", "근거상세", "summary", "detail"):
            output.extend(_flatten_text(value.get(key)))
        return output
    if isinstance(value, (list, tuple, set)):
        output = []
        for element in value:
            output.extend(_flatten_text(element))
        return output
    text = str(value).strip()
    return [text] if text else []


def item_search_text(item: dict[str, Any], *, variant: str = "core") -> str:
    """Build the rule-search document from regulation-list v2 only.

    ``core`` preserves the previously used fields. ``expanded`` additionally
    indexes v2 rule summaries and basis details.  Keeping both variants makes
    the recall/noise trade-off measurable instead of silently changing the
    production index after looking at known cases.
    """
    if variant not in {"core", "expanded"}:
        raise ValueError(f"unknown rule text variant: {variant}")
    parts = [
        text
        for key in ("title", "question", "criterion")
        for text in _flatten_text(item.get(key))
    ]
    if variant == "expanded":
        for key in ("규칙요약", "근거상세", "규칙근거"):
            parts.extend(_flatten_text(item.get(key)))
    return " ".join(dict.fromkeys(parts))


def rule_docs(
    items: list[dict[str, Any]], *, search_text_variant: str = "core"
) -> list[dict[str, Any]]:
    docs = []
    for item in items:
        docs.append({
            "doc_id": item["id"],
            "item_id": item["id"],
            "category": item["category"],
            "category_label": item["구분"],
            "product_groups": item["적용상품"],
            "product_subtype": item.get("세부상품") or None,
            "title": item["title"],
            "question": item["question"],
            "criterion": item["criterion"],
            "search_text": item_search_text(item, variant=search_text_variant),
            "search_text_variant": search_text_variant,
        })
    return docs


def load_model():
    from dgx_bge_client import DGXSentenceEncoder

    return DGXSentenceEncoder()


def _atomic_cache_write(path: Path, content: bytes) -> None:
    """Unique temp paths prevent parallel jobs from sharing an in-progress file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_or_encode(
    rows: list[dict[str, Any]],
    *,
    text_key: str,
    source: Path,
    vectors_path: Path,
    meta_path: Path,
    model: Any,
    batch_size: int,
    force: bool,
) -> tuple[np.ndarray, bool, float]:
    if len({row["doc_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate embedding doc_id")
    if any(not isinstance(row.get(text_key), str) or not row[text_key].strip() for row in rows):
        raise ValueError("embedding input text must be a nonempty string")
    expected = {
        "cache_contract_version": 2,
        "model": MODEL_NAME,
        "documents": len(rows),
        "source_sha256": sha256(source),
        "corpus_key": corpus_key(rows, text_key),
        "doc_ids": [row["doc_id"] for row in rows],
        "normalize_embeddings": True,
        "max_seq_length": 1024,
    }
    cache_rebuild_reason = "forced" if force else "cache_missing"
    if not force and vectors_path.exists() and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if not isinstance(meta, dict):
                raise ValueError("embedding cache metadata must be an object")
            cache_rebuild_reason = "identity_changed"
            if all(meta.get(k) == v for k, v in expected.items()):
                raw = vectors_path.read_bytes()
                if hashlib.sha256(raw).hexdigest() != meta.get("vectors_sha256"):
                    raise ValueError("embedding cache checksum mismatch")
                matrix = validate_embeddings(
                    np.load(io.BytesIO(raw), allow_pickle=False), len(rows)
                )
                matrix /= np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9
                return matrix, True, 0.0
        except (ValueError, EOFError, OSError) as exc:
            cache_rebuild_reason = f"invalid_cache:{type(exc).__name__}"
            warnings.warn(f"Embedding cache rejected; re-encoding ({exc})", RuntimeWarning)

    started = time.perf_counter()
    # Repeated template wording and repeated ad text still have distinct source
    # IDs. Encode identical text once, then restore every original row/position.
    unique_texts = list(dict.fromkeys(row[text_key] for row in rows))
    text_positions = {text: index for index, text in enumerate(unique_texts)}
    matrix = model.encode(
        unique_texts,
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    matrix = validate_embeddings(matrix, len(unique_texts))
    matrix = matrix[[text_positions[row[text_key]] for row in rows]]
    seconds = time.perf_counter() - started
    vectors_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    # 캐시는 float16으로 저장한다. 첫 실행이 원본 float32를 쓰면 이후 실행과
    # 점수가 미세하게 달라져 근사 동점의 순위가 뒤집힌다. 실측: 규칙 136개 중
    # 14개가 근거 3위와 4위의 점수차 1e-3 미만이고 float16 해상도는 4.9e-4다.
    # 저장할 정밀도를 그대로 돌려주어 첫 실행과 이후 실행을 일치시킨다.
    stored_matrix = matrix.astype("float16")
    buffer = io.BytesIO()
    np.save(buffer, stored_matrix, allow_pickle=False)
    raw = buffer.getvalue()
    _atomic_cache_write(vectors_path, raw)
    matrix = stored_matrix.astype("float32")
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9
    _atomic_cache_write(meta_path, (json.dumps({
        **expected,
        "dimension": int(matrix.shape[1]),
        "dtype": "float16",
        "vectors_sha256": hashlib.sha256(raw).hexdigest(),
        "cache_rebuild_reason": cache_rebuild_reason,
        "unique_texts_encoded": len(unique_texts),
        "embedding_seconds_dgx_cuda": round(seconds, 3),
    }, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return matrix, False, seconds


def index_mapping(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": {
                "tokenizer": {
                    "ko_nori_tokenizer": {
                        "type": "nori_tokenizer",
                        "decompound_mode": "mixed",
                    }
                },
                "analyzer": {
                    "ko_nori": {
                        "type": "custom",
                        "tokenizer": "ko_nori_tokenizer",
                        "filter": ["lowercase", "nori_readingform"],
                    }
                },
            },
        },
        "mappings": {
            "dynamic": "strict",
            "_meta": meta,
            "properties": {
                "item_id": {"type": "keyword"},
                "category": {"type": "keyword"},
                "category_label": {"type": "keyword"},
                "product_groups": {"type": "keyword"},
                "product_subtype": {"type": "keyword"},
                "title": {"type": "keyword", "index": False},
                "question": {"type": "keyword", "index": False},
                "criterion": {"type": "keyword", "index": False},
                "search_text_variant": {"type": "keyword"},
                "search_text": {"type": "text", "analyzer": "ko_nori"},
                "text_vector": {
                    "type": "dense_vector",
                    "dims": int(meta["dimension"]),
                    "index": True,
                    "similarity": "cosine",
                },
            },
        },
    }


def rule_index_fingerprint(docs: list[dict[str, Any]], vectors: np.ndarray) -> str:
    digest = hashlib.sha256(json.dumps(docs, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    digest.update(np.asarray(vectors, dtype="<f4").tobytes())
    return digest.hexdigest()


def versioned_rule_index(
    base: str,
    docs: list[dict[str, Any]],
    vectors: np.ndarray,
    *,
    source_sha: str | None = None,
) -> str:
    """Do not mutate an index used by an already-running review."""
    fingerprint = rule_index_fingerprint(docs, vectors)
    if source_sha:
        fingerprint = hashlib.sha256(f"{source_sha}:{fingerprint}".encode()).hexdigest()
    return f"{base}-catalog-{fingerprint[:16]}"


def ensure_rule_index(
    base_url: str,
    index: str,
    docs: list[dict[str, Any]],
    vectors: np.ndarray,
    *,
    source_sha: str,
) -> str:
    validate_embeddings(vectors, len(docs))
    if len({row["item_id"] for row in docs}) != len(docs):
        raise ValueError("duplicate index item_id")
    encoded = urllib.parse.quote(index, safe="")
    expected_meta = {
        "schema_version": "regulation-v2-es-index-v2",
        "source_file": str(v2_source.AGENT),
        "source_sha256": source_sha,
        "scope": "explicit supplied source catalog; applicability is checked downstream",
        "corpus_vectors_sha256": rule_index_fingerprint(docs, vectors),
        "documents": len(docs),
        "embedding_model": MODEL_NAME,
        "dimension": int(vectors.shape[1]),
        "search_text_variant": docs[0].get("search_text_variant", "core") if docs else "core",
        "search_fields": (
            ["약칭", "점검문구", "판정기준"]
            if not docs or docs[0].get("search_text_variant", "core") == "core"
            else ["약칭", "점검문구", "판정기준", "규칙요약", "근거상세"]
        ),
    }
    if index_exists(base_url, index):
        mapping = request(base_url, "GET", f"/{encoded}/_mapping")
        actual = mapping[index]["mappings"].get("_meta", {})
        keys = (
            "schema_version", "source_sha256", "documents", "dimension",
            "search_text_variant", "corpus_vectors_sha256", "embedding_model",
        )
        if all(actual.get(key) == expected_meta.get(key) for key in keys):
            if request(base_url, "GET", f"/{encoded}/_count")["count"] != len(docs):
                raise RuntimeError("규칙 인덱스 일부 적재/유실: metadata와 실제 문서 수 불일치")
            return "valid_existing_index"
        raise RuntimeError(
            f"동명 규칙 인덱스가 현재 v2와 다름: index={index}, meta={actual}"
        )

    request(base_url, "PUT", f"/{encoded}", index_mapping(expected_meta))
    lines: list[str] = []
    for doc, vector in zip(docs, vectors):
        lines.append(json.dumps(
            {"index": {"_index": index, "_id": doc["item_id"]}},
            ensure_ascii=False,
        ))
        lines.append(json.dumps({
            **{key: value for key, value in doc.items() if key != "doc_id"},
            "text_vector": vector.astype("float32").tolist(),
        }, ensure_ascii=False))
    result = request(
        base_url,
        "POST",
        "/_bulk?refresh=true",
        ("\n".join(lines) + "\n").encode("utf-8"),
        content_type="application/x-ndjson",
    )
    if result.get("errors"):
        failures = [x for x in result["items"] if x["index"].get("error")]
        raise RuntimeError(f"규칙 인덱스 적재 실패: {failures[:3]}")
    count = request(base_url, "GET", f"/{encoded}/_count")["count"]
    if count != len(docs):
        raise RuntimeError(f"규칙 인덱스 수 불일치: {count} != {len(docs)}")
    return "created"


SOURCE_FIELDS = [
    "item_id", "category", "category_label", "product_groups",
    "product_subtype", "title", "question", "criterion", "search_text_variant",
]


def _normalize_product_groups(product_groups: str | Iterable[str]) -> list[str]:
    values = [product_groups] if isinstance(product_groups, str) else list(product_groups)
    normalized = [str(value).strip() for value in values if str(value).strip()]
    if not normalized:
        raise ValueError("검색 상품군 후보가 비어 있음")
    invalid = set(normalized) - set(SUPPORTED_POC_PRODUCT_GROUPS)
    if invalid:
        raise ValueError(f"지원하지 않는 PoC 상품군: {sorted(invalid)}")
    return list(dict.fromkeys(normalized))


def semantic_rule_filter(
    product_group: str | Iterable[str],
    deterministic_item_ids: set[str],
    categories: Iterable[str] | None = None,
    allowed_item_ids: set[str] | None = None,
) -> dict[str, Any]:
    category_values = list(dict.fromkeys(categories or ["PROHIBIT"]))
    result: dict[str, Any] = {
        "filter": [
            {"terms": {"category": category_values}},
            {"terms": {"product_groups": ["전체", *_normalize_product_groups(product_group)]}},
        ]
    }
    if allowed_item_ids is not None:
        if not allowed_item_ids:
            raise ValueError("allowed_item_ids cannot be empty")
        result["filter"].append({"terms": {"item_id": sorted(allowed_item_ids)}})
    if deterministic_item_ids:
        result["must_not"] = [
            {"terms": {"item_id": sorted(deterministic_item_ids)}}
        ]
    return {"bool": result}


def bm25_hits(
    base_url: str,
    index: str,
    query: str,
    product_group: str,
    deterministic_item_ids: set[str],
    k: int,
) -> list[dict[str, Any]]:
    rule_filter = semantic_rule_filter(product_group, deterministic_item_ids)["bool"]
    body = {
        "size": k,
        "_source": SOURCE_FIELDS,
        "query": {"bool": {
            "filter": rule_filter["filter"],
            "must_not": rule_filter.get("must_not", []),
            "must": [{"match": {"search_text": {"query": query}}}],
        }},
        "sort": [{"_score": "desc"}, {"item_id": "asc"}],
    }
    return request(base_url, "POST", f"/{index}/_search", body)["hits"]["hits"]


def exact_vector_query(vector: np.ndarray, rule_filter: dict[str, Any]) -> dict[str, Any]:
    """Exact cosine is affordable for the small source-rule catalog (not ad corpus)."""
    validate_embeddings(np.asarray(vector)[None, :], 1)
    return {"script_score": {
        "query": rule_filter,
        "script": {"source": "(cosineSimilarity(params.q, 'text_vector') + 1.0) / 2.0",
                   "params": {"q": np.asarray(vector, dtype="float32").tolist()}},
    }}


def vector_hits(
    base_url: str,
    index: str,
    query_vector: np.ndarray,
    product_group: str,
    deterministic_item_ids: set[str],
    k: int,
) -> list[dict[str, Any]]:
    body = {
        "size": k,
        "_source": SOURCE_FIELDS,
        "query": exact_vector_query(query_vector, semantic_rule_filter(product_group, deterministic_item_ids)),
        "sort": [{"_score": "desc"}, {"item_id": "asc"}],
    }
    return request(base_url, "POST", f"/{index}/_search", body)["hits"]["hits"]


def validate_search_response(response: dict[str, Any]) -> None:
    if response.get("error") or response.get("timed_out") or (response.get("_shards") or {}).get("failed", 0):
        raise RuntimeError("Elasticsearch search failed or returned partial results")


def hybrid_hits_batch(
    base_url: str,
    index: str,
    fine_rows: list[dict[str, Any]],
    fine_vector_by_id: dict[str, np.ndarray],
    product_group: str,
    deterministic_item_ids: set[str],
    k: int,
    categories: Iterable[str] | None = None,
    allowed_item_ids: set[str] | None = None,
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """한 광고의 fine→규칙 검색을 Elasticsearch 한 번의 msearch로 묶는다."""
    searchable = [
        row for row in fine_rows
        if len(str(row.get("text_search") or row.get("text_canonical") or "").strip()) >= 2
    ]
    if not searchable:
        return {}
    category_values = list(dict.fromkeys(categories or ["PROHIBIT"]))
    unique_queries, representative = {}, {}
    for fine in searchable:
        query = str(fine.get("text_search") or fine.get("text_canonical") or "").strip()
        key = (query, np.asarray(fine_vector_by_id[fine["doc_id"]], dtype="<f4").tobytes())
        unique_queries.setdefault(key, fine)
        representative[fine["doc_id"]] = unique_queries[key]["doc_id"]
    plans = [(fine, category) for fine in unique_queries.values() for category in category_values]
    ndjson: list[str] = []
    for fine, category in plans:
        rule_filter = semantic_rule_filter(
            product_group, deterministic_item_ids, [category], allowed_item_ids
        )["bool"]
        query = str(fine.get("text_search") or fine.get("text_canonical") or "").strip()
        vector = fine_vector_by_id[fine["doc_id"]]
        ndjson.extend([
            json.dumps({"index": index}, ensure_ascii=False),
            json.dumps({
                "size": k,
                "_source": SOURCE_FIELDS,
                "query": {"bool": {
                    "filter": rule_filter["filter"],
                    "must_not": rule_filter.get("must_not", []),
                    "must": [{"match": {"search_text": {"query": query}}}],
                }},
                "sort": [{"_score": "desc"}, {"item_id": "asc"}],
            }, ensure_ascii=False),
            json.dumps({"index": index}, ensure_ascii=False),
            json.dumps({
                "size": k,
                "_source": SOURCE_FIELDS,
                "query": exact_vector_query(vector, semantic_rule_filter(
                    product_group, deterministic_item_ids, [category], allowed_item_ids)),
                "sort": [{"_score": "desc"}, {"item_id": "asc"}],
            }, ensure_ascii=False),
        ])
    payload = ("\n".join(ndjson) + "\n").encode("utf-8")
    result = request(
        base_url,
        "POST",
        "/_msearch",
        payload,
        content_type="application/x-ndjson",
    )
    responses = result.get("responses") or []
    expected = len(plans) * 2
    if len(responses) != expected:
        raise RuntimeError(f"msearch 응답 수 불일치: expected={expected}, actual={len(responses)}")
    output: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for offset, (fine, category) in enumerate(plans):
        bm25_response = responses[offset * 2]
        vector_response = responses[offset * 2 + 1]
        for channel, response in (
            ("bm25_nori", bm25_response),
            ("bge_m3_exact_cosine", vector_response),
        ):
            try:
                validate_search_response(response)
            except RuntimeError as exc:
                raise RuntimeError(
                    f"msearch incomplete doc_id={fine['doc_id']} channel={channel}"
                ) from exc
        row = output.setdefault(fine["doc_id"], {"bm25_nori": [], "bge_m3_exact_cosine": []})
        row["bm25_nori"].extend(bm25_response["hits"]["hits"])
        row["bge_m3_exact_cosine"].extend(vector_response["hits"]["hits"])
    for row in output.values():
        for hits in row.values():
            hits.sort(key=lambda hit: (-float(hit["_score"]), hit["_source"]["item_id"]))
    return {row["doc_id"]: output[representative[row["doc_id"]]] for row in searchable}


def routing_scope(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Resolve a fail-open rule-candidate scope from evidence metadata.

    Only a single, conflict-free *confirmed* observation may remove the other
    PoC product family.  Parser/filename inference, missing values and
    conflicting observations are useful ranking hints, never exclusion gates.
    """
    observations: list[dict[str, Any]] = []
    for row in rows:
        field = ((row.get("routing_metadata") or {}).get("product_group") or {})
        value = str(field.get("value") or "").strip() or None
        status = str(field.get("status") or "unknown").strip().lower()
        source = field.get("source")
        observations.append({"value": value, "status": status, "source": source})

    value_counts = collections.Counter(
        row["value"] for row in observations
        if row["value"] in SUPPORTED_POC_PRODUCT_GROUPS
    )
    confirmed = {
        row["value"] for row in observations
        if row["value"] in SUPPORTED_POC_PRODUCT_GROUPS
        and row["status"] in CONFIRMED_ROUTING_STATUSES
    }
    all_supported_values = set(value_counts)
    hard_route = len(confirmed) == 1 and all_supported_values == confirmed
    if hard_route:
        candidate_groups = sorted(confirmed)
        status = "confirmed"
        reason = "single conflict-free confirmed product-group observation"
    else:
        candidate_groups = list(SUPPORTED_POC_PRODUCT_GROUPS)
        status = "routing_provisional"
        if not value_counts:
            reason = "missing or unsupported product-group observation"
        elif len(all_supported_values) > 1:
            reason = "conflicting product-group observations"
        else:
            reason = "product group is inferred/unverified and cannot exclude rules"
    return {
        "candidate_product_groups": candidate_groups,
        "observed_values": dict(value_counts),
        "observations": observations,
        "status": status,
        "routing_provisional": not hard_route,
        "reason": reason,
        "policy": (
            "confirmed 단일값만 하드 필터; inferred/review/unknown/충돌은 "
            "예금성·대출성·투자성 합집합 전개"
        ),
    }


def product_for_ad(rows: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    """Backward-compatible display value; do not use it as an exclusion gate."""
    scope = routing_scope(rows)
    observed = collections.Counter(scope["observed_values"])
    value = observed.most_common(1)[0][0] if observed else scope["candidate_product_groups"][0]
    return value, {**scope, "value": value}


def applicable(item: dict[str, Any], product_group: str) -> bool:
    allowed = set(item["적용상품"])
    return "전체" in allowed or product_group in allowed


def applicable_to_any(
    item: dict[str, Any], product_groups: str | Iterable[str]
) -> bool:
    return any(applicable(item, group) for group in _normalize_product_groups(product_groups))


def trigger_doc(fine: dict[str, Any]) -> dict[str, Any]:
    return {
        "doc_id": fine["doc_id"],
        "parent_chunk_id": fine["parent_chunk_id"],
        "page_no": fine["page_no"],
        "region_id": fine["region_id"],
        "line_refs": fine["line_refs"],
        "text": fine["text_canonical"],
    }


def discover_prohibitions(
    ad_fine: list[dict[str, Any]],
    fine_vector_by_id: dict[str, np.ndarray],
    product_group: str | Iterable[str],
    *,
    base_url: str,
    index: str,
    per_chunk_k: int,
    rrf_k: int,
    deterministic_item_ids: set[str],
    categories: Iterable[str] | None = None,
    allowed_item_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    events: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    rule_source: dict[str, dict[str, Any]] = {}
    batched_hits = hybrid_hits_batch(
        base_url,
        index,
        ad_fine,
        fine_vector_by_id,
        product_group,
        deterministic_item_ids,
        per_chunk_k,
        categories,
        allowed_item_ids,
    )
    for fine in ad_fine:
        query = str(fine.get("text_search") or fine.get("text_canonical") or "").strip()
        if len(query) < 2:
            continue
        channels = batched_hits[fine["doc_id"]]
        for channel, hits in channels.items():
            for rank, hit in enumerate(hits, start=1):
                source = hit["_source"]
                item_id = source["item_id"]
                rule_source[item_id] = source
                for member in fine.get("_query_members") or [fine]:
                    event = {
                        "channel": channel,
                        "rank_within_chunk": rank,
                        "raw_score": round(float(hit["_score"]), 6),
                        "rrf_contribution": round(1.0 / (rrf_k + rank), 8),
                        "trigger": trigger_doc(member),
                    }
                    if fine.get("_query_members"):
                        event["trigger"]["query_context_doc_ids"] = [row["doc_id"] for row in fine["_query_members"]]
                    events[item_id].append(event)

    # 여러 광고 청크 중 우연히 한 번 채널 1위가 된 것만으로 모든 규칙이
    # 동점이 되는 것을 막는다. 광고 전체에서 규칙별 최고 원점수를 먼저
    # 고른 뒤 채널별 규칙 순위를 만들고, 그 두 순위만 RRF로 결합한다.
    best_event: dict[str, dict[str, dict[str, Any]]] = collections.defaultdict(dict)
    for item_id, item_events in events.items():
        for event in item_events:
            channel = event["channel"]
            old = best_event[item_id].get(channel)
            candidate_key = (
                event["raw_score"], -event["rank_within_chunk"],
                event["trigger"]["doc_id"],
            )
            old_key = (
                old["raw_score"], -old["rank_within_chunk"],
                old["trigger"]["doc_id"],
            ) if old else None
            if old is None or candidate_key > old_key:
                best_event[item_id][channel] = event

    aggregate_rank: dict[str, dict[str, int]] = collections.defaultdict(dict)
    for channel in ("bm25_nori", "bge_m3_exact_cosine"):
        ordered = sorted(
            (
                (item_id, channels[channel])
                for item_id, channels in best_event.items()
                if channel in channels
            ),
            key=lambda pair: (
                -pair[1]["raw_score"], pair[1]["rank_within_chunk"], pair[0]
            ),
        )
        for rank, (item_id, _) in enumerate(ordered, start=1):
            aggregate_rank[item_id][channel] = rank

    rows = []
    for item_id, source in rule_source.items():
        channel_ranks = aggregate_rank[item_id]
        score = sum(1.0 / (rrf_k + rank) for rank in channel_ranks.values())
        channel_max = {
            channel: event["raw_score"]
            for channel, event in best_event[item_id].items()
        }
        by_trigger: dict[str, dict[str, Any]] = {}
        for event in events[item_id]:
            doc_id = event["trigger"]["doc_id"]
            trigger_row = by_trigger.setdefault(doc_id, {
                "trigger": event["trigger"],
                "normalized_score": 0.0,
                "channel_hits": {},
            })
            if event["trigger"].get("query_context_doc_ids"):
                trigger_row["trigger"]["query_context_doc_ids"] = list(dict.fromkeys(
                    (trigger_row["trigger"].get("query_context_doc_ids") or []) +
                    event["trigger"]["query_context_doc_ids"]))
            channel = event["channel"]
            old = trigger_row["channel_hits"].get(channel)
            if old is None or event["raw_score"] > old["raw_score"]:
                trigger_row["channel_hits"][channel] = {
                    "rank_within_chunk": event["rank_within_chunk"],
                    "raw_score": event["raw_score"],
                }
        for trigger_row in by_trigger.values():
            trigger_row["normalized_score"] = round(sum(
                hit["raw_score"] / max(channel_max[channel], 1e-9)
                for channel, hit in trigger_row["channel_hits"].items()
            ), 8)
        unique_triggers = sorted(
            by_trigger.values(),
            key=lambda x: (-x["normalized_score"], x["trigger"]["doc_id"]),
        )[:10]
        rows.append({
            "item_id": item_id,
            "title": source["title"],
            "product_groups": source["product_groups"],
            "discovery_method": "ad_fine_to_rule_hybrid",
            "score": round(score, 8),
            "best_channel_ranks": channel_ranks,
            "best_channel_scores": {
                channel: round(event["raw_score"], 6)
                for channel, event in best_event[item_id].items()
            },
            "trigger_evidence": unique_triggers,
        })
    rows.sort(key=lambda x: (
        -x["score"], min(x["best_channel_ranks"].values()), x["item_id"]
    ))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


def evidence_group_hit(
    candidate: dict[str, Any] | None,
    refs: set[str],
    k: int,
) -> bool:
    if not candidate:
        return False
    for event in candidate.get("trigger_evidence", [])[:k]:
        if refs.intersection(event["trigger"]["line_refs"]):
            return True
    return False


def evaluate(
    service_ads: list[dict[str, Any]],
    item_by_id: dict[str, dict[str, Any]],
    gold: list[dict[str, Any]],
    exclusions: dict[str, str] | None = None,
) -> dict[str, Any]:
    exclusions = exclusions or {}
    by_ad = {row["ad_id"]: row for row in service_ads}
    rows = []
    for case in gold:
        item = item_by_id[case["item_id"]]
        service = by_ad[case["ad_id"]]
        excluded = case["key"] in exclusions
        deterministic = next(
            (row for row in service["deterministic_rule_scans"]
             if row["item_id"] == case["item_id"]),
            None,
        )
        if deterministic is not None:
            candidate = deterministic
            rank = None
            method = "deterministic_route_enumeration"
            covered = True
        elif item["category"] == "PROHIBIT":
            candidates = service["prohibition_discovery"]
            candidate = next(
                (row for row in candidates if row["item_id"] == case["item_id"]),
                None,
            )
            rank = candidate["rank"] if candidate else None
            method = "semantic_discovery"
            covered = candidate is not None
        else:
            candidates = service["applicability_enumeration"]
            candidate = next(
                (row for row in candidates if row["item_id"] == case["item_id"]),
                None,
            )
            rank = None
            method = "applicability_enumeration"
            covered = candidate is not None
        groups = []
        if method == "semantic_discovery" and case.get("required_groups"):
            for group in case["required_groups"]:
                groups.append({
                    "label": group["label"],
                    "trigger_hit@1": evidence_group_hit(
                        candidate, set(group["line_refs"]), 1
                    ),
                    "trigger_hit@3": evidence_group_hit(
                        candidate, set(group["line_refs"]), 3
                    ),
                    "trigger_hit@5": evidence_group_hit(
                        candidate, set(group["line_refs"]), 5
                    ),
                })
        rows.append({
            "case_id": case["key"],
            "ad_id": case["ad_id"],
            "gold_item_id": case["item_id"],
            "category": item["category"],
            "method": method,
            "candidate_covered": covered,
            "semantic_rank": rank,
            "metric_eligible": not excluded,
            "exclusion_reason": exclusions.get(case["key"]),
            "trigger_groups": groups,
        })

    eligible = [row for row in rows if row["metric_eligible"]]
    semantic = [row for row in eligible if row["method"] == "semantic_discovery"]
    deterministic = [
        row for row in eligible
        if row["method"] == "deterministic_route_enumeration"
    ]
    enumerated = [row for row in eligible if row["method"] == "applicability_enumeration"]
    trigger_groups = [
        group for row in semantic for group in row["trigger_groups"]
    ]
    metrics: dict[str, Any] = {
        "eligible_gold_cases": len(eligible),
        "excluded_cases": len(rows) - len(eligible),
        "overall_candidate_coverage": round(
            sum(row["candidate_covered"] for row in eligible) / max(1, len(eligible)), 6
        ),
        "applicability_enumeration": {
            "cases": len(enumerated),
            "coverage": round(
                sum(row["candidate_covered"] for row in enumerated)
                / max(1, len(enumerated)), 6
            ),
            "note": "부재 가능한 표시의무·양식 규칙은 순위 검색이 아니라 적용성 전개",
        },
        "deterministic_route_enumeration": {
            "cases": len(deterministic),
            "coverage": round(
                sum(row["candidate_covered"] for row in deterministic)
                / max(1, len(deterministic)), 6
            ),
            "note": "자동확정 가능 금지 규칙은 의미검색으로 버리지 않고 직접 검사",
        },
        "prohibition_rule_discovery": {"cases": len(semantic)},
        "prohibition_trigger_evidence": {
            "groups": len(trigger_groups),
        },
    }
    for k in (1, 3, 5, 10, 20):
        metrics["prohibition_rule_discovery"][f"recall@{k}"] = round(
            sum(row["semantic_rank"] is not None and row["semantic_rank"] <= k
                for row in semantic) / max(1, len(semantic)),
            6,
        )
    for k in (1, 3, 5):
        metrics["prohibition_trigger_evidence"][f"group_recall@{k}"] = round(
            sum(group[f"trigger_hit@{k}"] for group in trigger_groups)
            / max(1, len(trigger_groups)),
            6,
        )
    return {
        "schema_version": "service-discovery19-eval-v1",
        "status": "smoke_regression_not_final_performance",
        "warning": "이미 관찰한 사례의 회귀 진단일 뿐 일반화 성능이 아님",
        "metrics": metrics,
        "rows": rows,
    }


def main() -> None:
    raise SystemExit(
        "옛 19건 CLI는 비활성화되었습니다. 현행 데이터셋 래퍼를 사용하세요."
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--index", default=DEFAULT_INDEX)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--per-chunk-k", type=int, default=5)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--force-reembed", action="store_true")
    parser.add_argument("--regression-gold", type=Path)
    parser.add_argument("--eval-output", type=Path)
    args = parser.parse_args()

    SERVICE_DIR.mkdir(parents=True, exist_ok=True)
    items, item_by_id = load_scope()
    deterministic_prohibit_ids: set[str] = set()
    rules = rule_docs(items)
    fine = read_jsonl(FINE)
    fine.sort(key=lambda row: row["doc_id"])
    coarse = read_jsonl(COARSE)
    coarse_by_ad: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    fine_by_ad: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in coarse:
        coarse_by_ad[row["ad_id"]].append(row)
    for row in fine:
        fine_by_ad[row["ad_id"]].append(row)
    if set(coarse_by_ad) != set(fine_by_ad) or len(coarse_by_ad) != 19:
        raise RuntimeError("운영형 입력 광고가 coarse/fine 공통 19건이 아님")

    model = load_model()
    rule_matrix, rule_cache, rule_seconds = load_or_encode(
        rules,
        text_key="search_text",
        source=Path(v2_source.AGENT),
        vectors_path=RULE_VECTORS,
        meta_path=RULE_META,
        model=model,
        batch_size=args.batch_size,
        force=args.force_reembed,
    )
    fine_matrix, fine_cache, fine_seconds = load_or_encode(
        fine,
        text_key="text_search",
        source=FINE,
        vectors_path=FINE_VECTORS,
        meta_path=FINE_META,
        model=model,
        batch_size=args.batch_size,
        force=args.force_reembed,
    )
    index_status = ensure_rule_index(
        args.url,
        args.index,
        rules,
        rule_matrix,
        source_sha=sha256(Path(v2_source.AGENT)),
    )
    fine_vector_by_id = {
        row["doc_id"]: vector for row, vector in zip(fine, fine_matrix)
    }

    service_ads = []
    for ad_no, ad_id in enumerate(sorted(coarse_by_ad), start=1):
        product_group, routing = product_for_ad(coarse_by_ad[ad_id])
        enumerated = [
            {
                "item_id": item["id"],
                "title": item["title"],
                "category": item["category"],
                "category_label": item["구분"],
                "product_groups": item["적용상품"],
                "discovery_method": "applicability_enumeration",
                "trigger_evidence": [],
                "evidence_completion_required": True,
            }
            for item in items
            if item["category"] != "PROHIBIT" and applicable(item, product_group)
        ]
        deterministic_scans = [
            {
                "item_id": item["id"],
                "title": item["title"],
                "category": item["category"],
                "category_label": item["구분"],
                "product_groups": item["적용상품"],
                "discovery_method": "deterministic_route_enumeration",
                "trigger_evidence": [],
                "evidence_completion_required": True,
            }
            for item in items
            if item["id"] in deterministic_prohibit_ids
            and applicable(item, product_group)
        ]
        prohibitions = discover_prohibitions(
            fine_by_ad[ad_id], fine_vector_by_id, product_group,
            base_url=args.url,
            index=args.index,
            per_chunk_k=args.per_chunk_k,
            rrf_k=args.rrf_k,
            deterministic_item_ids=deterministic_prohibit_ids,
        )
        service_ads.append({
            "ad_id": ad_id,
            "input_ordinal": ad_no,
            "routing": {"product_group": routing},
            "input_counts": {
                "coarse_chunks": len(coarse_by_ad[ad_id]),
                "fine_chunks": len(fine_by_ad[ad_id]),
            },
            "applicability_enumeration": enumerated,
            "deterministic_rule_scans": deterministic_scans,
            "prohibition_discovery": prohibitions,
        })
        print(json.dumps({
            "progress": f"{ad_no}/19",
            "ad_id": ad_id,
            "product_group": product_group,
            "enumerated": len(enumerated),
            "deterministic_scans": len(deterministic_scans),
            "prohibition_candidates": len(prohibitions),
        }, ensure_ascii=False), flush=True)

    payload = {
        "schema_version": "service-discovery19-results-v1",
        "status": "operational_shape_smoke",
        "input_contract": {
            "provided": ["광고 evidence coarse/fine", "규제목록 v2"],
            "hidden": ["gold item_id", "reviewer reason", "gold line_refs"],
        },
        "sources": {
            "regulation": {
                "file": str(v2_source.AGENT),
                "sha256": sha256(Path(v2_source.AGENT)),
                "scope": "v2 운영 비시인성 실행경로 227개",
            },
            "advertisement": {
                "coarse": str(COARSE),
                "coarse_sha256": sha256(COARSE),
                "fine": str(FINE),
                "fine_sha256": sha256(FINE),
            },
        },
        "environment": {
            "elasticsearch": args.url,
            "rule_index": args.index,
            "rule_index_status": index_status,
            "bm25_analyzer": "nori/mixed",
            "embedding_model": MODEL_NAME,
            "fusion": "best-per-channel RRF; repeated chunks do not accumulate",
            "rule_vector_cache_hit": rule_cache,
            "fine_vector_cache_hit": fine_cache,
            "embedding_seconds": round(rule_seconds + fine_seconds, 3),
        },
        "policy": {
            "presence_and_style": "상품군 적용 항목 전개; 의미검색으로 제외하지 않음",
            "prohibition": "광고 fine 청크→금지 규칙 BM25+벡터 검색",
            "deterministic_prohibition": "자동확정 가능 규칙은 상품군 적용 시 직접 검사하고 의미검색 제외",
            "trigger": "규칙 발견을 유발한 fine 청크를 최초 판단 근거로 보존",
            "evidence_completion": "전개 규칙·다중요건·부재 판정에만 규칙→광고 보강검색",
            "product_filter": "전체 또는 광고 상품군; 세부상품·매체 unknown은 제외 게이트로 쓰지 않음",
            "template_and_gubun": "저장 신호일 뿐 규칙 제외 게이트로 사용하지 않음",
        },
        "counts": {
            "ads": len(service_ads),
            "rules": len(items),
            "fine_chunks": len(fine),
        },
        "ads": service_ads,
    }
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report: dict[str, Any] = {"results": str(OUT)}
    if args.regression_gold:
        if not args.eval_output:
            raise RuntimeError("--regression-gold 사용 시 --eval-output이 필요함")
        gold_rows = json.loads(args.regression_gold.read_text(encoding="utf-8"))["rows"]
        evaluation = evaluate(service_ads, item_by_id, gold_rows)
        args.eval_output.write_text(
            json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        report.update({
            "regression_evaluation": str(args.eval_output),
            "metrics": evaluation["metrics"],
            "metric_scope": "known-case regression only",
        })
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
