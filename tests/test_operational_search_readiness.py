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
        self.bridge.lock = threading.RLock()
        self.bridge.stopping = Mock()
        self.bridge.stopping.wait.return_value = False
        self.bridge.persist = Mock()
        self.bundle = SimpleNamespace(job=SimpleNamespace(status="RUNNING", current_step="CHECK"),
                                      steps=[SimpleNamespace(step_code="CHECK", step_name="Check")])

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
