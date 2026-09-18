import io
import threading
import unittest
import urllib.error
from types import SimpleNamespace
from unittest.mock import Mock, patch

from operational_web_bridge import ExecutionBridge, ReviewCanceled


class SearchReadinessTests(unittest.TestCase):
    def setUp(self):
        self.bridge = ExecutionBridge.__new__(ExecutionBridge)
        self.bridge.config = {"es_url": "http://search.invalid"}
        self.bridge.rag = SimpleNamespace(config=SimpleNamespace(source_policy="template-plus-v2"))
        self.bridge.lock = threading.RLock()
        self.bridge.stopping = Mock()
        self.bridge.stopping.wait.return_value = False
        self.bridge.persist = Mock()
        self.bundle = SimpleNamespace(job=SimpleNamespace(status="RUNNING", current_step="CHECK"),
                                      steps=[SimpleNamespace(step_code="CHECK", step_name="Check")])

    def test_template_only_does_not_require_v2_search(self):
        self.bridge.rag.config.source_policy = "template-only"
        with patch("operational_web_bridge.urllib.request.urlopen") as request:
            self.bridge.wait_for_search_backend(self.bundle)
        request.assert_not_called()

    def test_connection_recovers_without_failing_review(self):
        ready = io.BytesIO(b'{"cluster_name":"test","version":{"number":"8"}}')
        with patch("operational_web_bridge.urllib.request.urlopen", side_effect=[urllib.error.URLError("offline"), ready]):
            self.bridge.wait_for_search_backend(self.bundle)
        self.bridge.stopping.wait.assert_called_once_with(2)
        self.assertEqual(self.bundle.steps[0].step_name, "Check")
        self.assertEqual(self.bundle.job.status, "RUNNING")

    def test_wrong_service_is_not_accepted(self):
        with patch("operational_web_bridge.urllib.request.urlopen", return_value=io.BytesIO(b'{}')):
            with self.assertRaisesRegex(RuntimeError, "SEARCH_ENDPOINT_INVALID"):
                self.bridge.wait_for_search_backend(self.bundle)

    def test_wait_is_bounded_and_cancellable(self):
        with patch("operational_web_bridge.time.monotonic", side_effect=[0, 301]), patch(
            "operational_web_bridge.urllib.request.urlopen", side_effect=urllib.error.URLError("offline")
        ):
            with self.assertRaisesRegex(RuntimeError, "SEARCH_CONNECTION_UNAVAILABLE"):
                self.bridge.wait_for_search_backend(self.bundle)
        self.bundle.job.status = "CANCELED"
        with patch("operational_web_bridge.urllib.request.urlopen") as request:
            with self.assertRaises(ReviewCanceled):
                self.bridge.wait_for_search_backend(self.bundle)
            request.assert_not_called()

    def test_bge_and_gemma_must_be_ready_before_work_starts(self):
        self.bridge.config["model_env"] = {
            "NH_GPU_BGE_ENDPOINT": "http://bge.invalid",
            "NH_GPU_GEMMA_ENDPOINT": "http://gemma.invalid/v1/chat/completions",
        }
        self.bridge.config["model"] = "model"
        bge = io.BytesIO(
            b'{"device":"cuda","embedding_model":"BAAI/bge-m3",'
            b'"embedding_dimension":1024,"max_seq_length":1024}'
        )
        gemma = io.BytesIO(b'{"data":[{"id":"model"}]}')
        with patch(
            "operational_web_bridge.urllib.request.urlopen",
            side_effect=[bge, gemma],
        ) as request:
            self.bridge.wait_for_judgment_backends(self.bundle)
        self.assertEqual(
            [call.args[0] for call in request.call_args_list],
            ["http://bge.invalid/health", "http://gemma.invalid/v1/models"],
        )

    def test_model_wait_is_bounded_without_running_inference(self):
        self.bridge.config["model_env"] = {
            "NH_GPU_BGE_ENDPOINT": "http://bge.invalid",
        }
        with patch(
            "operational_web_bridge.time.monotonic", side_effect=[0, 301]
        ), patch(
            "operational_web_bridge.urllib.request.urlopen",
            side_effect=urllib.error.URLError("offline"),
        ):
            with self.assertRaisesRegex(RuntimeError, "EMBEDDING_CONNECTION_UNAVAILABLE"):
                self.bridge.wait_for_judgment_backends(self.bundle)

    def test_ssh_fallback_profile_checks_remote_services(self):
        self.bridge.config.update({
            "model_env": {},
            "model": "judge-model",
            "dgx_host": "user@spark.invalid",
            "dgx_key": "key-file",
        })
        bge = {
            "device": "cuda",
            "embedding_model": "BAAI/bge-m3",
            "embedding_dimension": 1024,
            "max_seq_length": 1024,
        }
        gemma = {"data": [{"id": "judge-model"}]}
        with patch.object(
            self.bridge, "_read_ssh_json", side_effect=[bge, gemma]
        ) as request:
            self.bridge.wait_for_judgment_backends(self.bundle)
        self.assertEqual(
            [call.args[0] for call in request.call_args_list],
            [
                "http://127.0.0.1:8103/health",
                "http://127.0.0.1:8102/v1/models",
            ],
        )
