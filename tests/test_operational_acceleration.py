"""Canonical GPU/Elasticsearch runtime configuration checks."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODEL_PATHS = (
    ROOT / "tools/build_ad_evidence_vectors.py",
    ROOT / "tools/hybrid_rule_retrieval.py",
    ROOT / "tools/run_operational_e2e.py",
)
CONNECTION_PATHS = (
    ROOT / "tools/dgx_bge_client.py",
    ROOT / "tools/dgx_openai_client.py",
    ROOT / "tools/run_gemma_exhaustive_dgx.py",
    ROOT / "tools/run_operational_e2e.py",
    ROOT / "tools/start_runtime_tunnels.ps1",
)


def test_runtime_does_not_force_cpu() -> None:
    for path in MODEL_PATHS:
        text = path.read_text(encoding="utf-8")
        assert 'device="cpu"' not in text, path
        assert "embedding_seconds_cpu" not in text, path


def test_connection_defaults_contain_no_internal_host_or_personal_key() -> None:
    forbidden = ("10.90.0.103", "babie0511", "spark_auto", "C:\\Users\\babie")
    for path in CONNECTION_PATHS:
        text = path.read_text(encoding="utf-8")
        assert not [value for value in forbidden if value in text], path


def test_elasticsearch_uses_dedicated_configurable_endpoint() -> None:
    text = (ROOT / "tools/run_operational_e2e.py").read_text(encoding="utf-8")
    assert "NH_RAG_ES_URL" in text
    assert "127.0.0.1:19201" in text
    assert "127.0.0.1:9201" not in text
