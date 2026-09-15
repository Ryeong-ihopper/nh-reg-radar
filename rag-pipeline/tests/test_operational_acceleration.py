"""Canonical GPU/Elasticsearch runtime configuration checks."""
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_embedding_cache_returns_identical_first_and_cached_vectors() -> None:
    import numpy as np
    from hybrid_rule_retrieval import load_or_encode

    class Model:
        def encode(self, *args, **kwargs):
            matrix = np.zeros((1, 1024), dtype="float32")
            matrix[0, :3] = [0.123456, 0.234567, 0.963456]
            return matrix / np.linalg.norm(matrix, axis=1, keepdims=True)

    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        source = root / "source.txt"
        source.write_text("cache regression", encoding="utf-8")
        args = dict(text_key="text", source=source, vectors_path=root / "v.npy",
                    meta_path=root / "meta.json", model=Model(), batch_size=1, force=False)
        rows = [{"doc_id": "generic", "text": "cache regression"}]
        first, hit_first, _ = load_or_encode(rows, **args)
        cached, hit_cached, _ = load_or_encode(rows, **args)
        assert not hit_first and hit_cached
        np.testing.assert_array_equal(first, cached)


def test_embedding_boundary_rejects_invalid_vectors_and_service_settings() -> None:
    import io
    import unittest
    from unittest.mock import patch
    import numpy as np
    import dgx_bge_client as client

    case = unittest.TestCase()
    valid = np.zeros((1, 1024), dtype="float32")
    valid[0, 0] = 1
    invalid = [valid[:, :3], valid[0], np.zeros_like(valid), valid * 2,
               np.full_like(valid, np.nan), np.full_like(valid, np.inf)]
    for matrix in invalid:
        raw = io.BytesIO()
        np.save(raw, matrix, allow_pickle=False)
        with patch.object(client, "_call", return_value=raw.getvalue()):
            with case.assertRaises(ValueError):
                client.encode(["generic source text"])
    service = {"device": "cuda", "embedding_model": "BAAI/bge-m3",
               "embedding_dimension": 1024, "max_seq_length": 1024}
    for key in ("embedding_dimension", "max_seq_length"):
        for value in (512, None):
            with patch.object(client, "health", return_value={**service, key: value}):
                with case.assertRaises(RuntimeError):
                    client.GPUSentenceEncoder()
    with patch.object(client, "health", return_value=service) as health:
        from hybrid_rule_retrieval import load_model
        load_model()
        health.assert_called_once()
    with patch.object(client, "_call", return_value=b'{"scores":[NaN]}'):
        with case.assertRaises(ValueError):
            client.rerank([["query", "document"]])


def test_duplicate_text_is_encoded_once_without_losing_source_rows() -> None:
    from unittest.mock import Mock
    import numpy as np
    from hybrid_rule_retrieval import load_or_encode

    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        source = root / "source.txt"
        source.write_text("generic", encoding="utf-8")
        rows = [{"doc_id": str(index), "text": text}
                for index, text in enumerate(["same", "other", "same"])]
        model = Mock()
        model.encode.return_value = np.eye(2, 1024, dtype="float32")
        result, _, _ = load_or_encode(
            rows, text_key="text", source=source, vectors_path=root / "v.npy",
            meta_path=root / "meta.json", model=model, batch_size=4, force=False)
        assert model.encode.call_args.args[0] == ["same", "other"]
        assert result.shape == (3, 1024)
        np.testing.assert_array_equal(result[0], result[2])
        assert not np.array_equal(result[0], result[1])
        meta = json.loads((root / "meta.json").read_text())
        assert meta["doc_ids"] == ["0", "1", "2"]
        assert meta["unique_texts_encoded"] == 2


def test_invalid_embedding_cache_rebuilds_but_invalid_service_output_is_not_saved() -> None:
    import hashlib
    import unittest
    import warnings
    import numpy as np
    from hybrid_rule_retrieval import load_or_encode

    class Model:
        calls = 0
        invalid = False

        def encode(self, *args, **kwargs):
            self.calls += 1
            matrix = np.zeros((1, 1024), dtype="float32")
            matrix[0, 0] = np.nan if self.invalid else 1
            return matrix

    case = unittest.TestCase()
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        source = root / "source.txt"
        source.write_text("generic", encoding="utf-8")
        model = Model()
        args = dict(text_key="text", source=source, vectors_path=root / "v.npy",
                    meta_path=root / "meta.json", model=model, batch_size=1, force=False)
        rows = [{"doc_id": "a", "text": "generic"}]
        load_or_encode(rows, **args)
        for corruption in ("checksum", "nan", "metadata", "truncated"):
            if corruption == "metadata":
                args["meta_path"].write_text("[]", encoding="utf-8")
            else:
                if corruption == "nan":
                    np.save(args["vectors_path"], np.full((1, 1024), np.nan))
                else:
                    args["vectors_path"].write_bytes(b"incomplete")
                if corruption != "checksum":
                    meta = json.loads(args["meta_path"].read_text(encoding="utf-8"))
                    meta["vectors_sha256"] = hashlib.sha256(args["vectors_path"].read_bytes()).hexdigest()
                    args["meta_path"].write_text(json.dumps(meta), encoding="utf-8")
            with warnings.catch_warnings(record=True) as recorded:
                _, hit, _ = load_or_encode(rows, **args)
            assert not hit and recorded
            assert json.loads(args["meta_path"].read_text())["cache_rebuild_reason"].startswith("invalid_cache:")
        before = args["vectors_path"].read_bytes()
        model.invalid = True
        with case.assertRaises(ValueError):
            load_or_encode(rows, **{**args, "force": True})
        assert args["vectors_path"].read_bytes() == before
        for bad_rows in ([*rows, *rows], [{"doc_id": "a", "text": " "}]):
            calls = model.calls
            with case.assertRaises(ValueError):
                load_or_encode(bad_rows, **args)
            assert model.calls == calls

MODEL_PATHS = (
    ROOT / "tools/build_ad_evidence_vectors.py",
    ROOT / "tools/hybrid_rule_retrieval.py",
    ROOT / "tools/run_operational_e2e.py",
    ROOT / "rag/api/service.py",
)
CONNECTION_PATHS = (
    ROOT / "tools/dgx_bge_client.py",
    ROOT / "tools/dgx_openai_client.py",
    ROOT / "tools/run_gemma_exhaustive_dgx.py",
    ROOT / "tools/run_operational_e2e.py",
    ROOT / "tools/start_runtime_tunnels.ps1",
    ROOT / "rag/api/service.py",
    ROOT / "tools/serve_operational_api.py",
)


def test_runtime_does_not_force_cpu() -> None:
    for path in MODEL_PATHS:
        text = path.read_text(encoding="utf-8")
        assert 'device="cpu"' not in text, path
        assert "embedding_seconds_cpu" not in text, path


def test_connection_defaults_contain_no_internal_host_or_personal_key() -> None:
    import re

    forbidden = re.compile(
        r"\b(?:10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)\b"
        r"|C:[\\/]Users[\\/](?!REPLACE_USER|example|user)[^\\/\s]+",
        re.IGNORECASE,
    )
    for path in CONNECTION_PATHS:
        text = path.read_text(encoding="utf-8")
        assert not forbidden.search(text), path


def test_elasticsearch_uses_dedicated_configurable_endpoint() -> None:
    text = (ROOT / "tools/run_operational_e2e.py").read_text(encoding="utf-8")
    assert "NH_RAG_ES_URL" in text
    assert "127.0.0.1:19201" in text
    assert "127.0.0.1:9201" not in text


def test_dgx_and_h200_profiles_share_generic_gpu_contract() -> None:
    config_dir = ROOT / "config"
    dgx = json.loads((config_dir / "runtime.dgx.example.json").read_text(encoding="utf-8"))
    h200 = json.loads(
        (config_dir / "runtime.h200.example.json").read_text(encoding="utf-8")
    )
    required = {
        "NH_GPU_BGE_ENDPOINT",
        "NH_GPU_GEMMA_ENDPOINT",
        "NH_GPU_GEMMA_MODEL",
    }
    assert set(dgx["model_env"]) == required
    assert set(h200["model_env"]) == required
    assert dgx["runtime_profile"] == "dgx-interim"
    assert h200["runtime_profile"] == "h200-final"
    assert "dgx_host" in dgx and "dgx_host" not in h200
