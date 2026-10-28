import tempfile
import unittest
from unittest.mock import patch

from crashlab.hosting import request_allowlist
from crashlab.provider import ProviderError
from crashlab.store import RunLimitExceeded, Store
from crashlab.worker import execute


class HostingTests(unittest.TestCase):
    def test_reverse_proxy_origin_adds_one_explicit_origin(self):
        hosts, origins = request_allowlist(8765, "https://crashlab.example.com")
        self.assertIn("crashlab.example.com", hosts)
        self.assertIn("https://crashlab.example.com", origins)
        self.assertNotIn("https://other.example.com", origins)
        self.assertIn("127.0.0.1:8765", hosts)

    def test_invalid_public_origins_do_not_relax_host_checks(self):
        for value in ["http://example.com", "https://u:p@example.com", "https://example.com/path",
                      "https://example.com?query=1", "https://example.com#fragment",
                      "https://example.com:bad", "https://example .com"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                request_allowlist(8765, value)

    def test_live_allowance_is_persistent_and_does_not_hide_reports(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            run = store.create("page-slices", "nebius", max_live_runs=1)
            with self.assertRaises(RunLimitExceeded):
                Store(root).create("page-slices", "nebius", max_live_runs=1)
            self.assertEqual(store.get(run["id"])["status"], "queued")
            self.assertEqual(store.create("page-slices", max_live_runs=1)["provider"], "fixture")

    def test_six_request_limit_survives_resume_and_prevents_remote_call(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            run = store.create("page-slices", "nebius")
            def spent(r):
                r.update(model="nvidia/test", phase="model")
                r["metrics"]["model_calls"] = 6
            store.mutate(run["id"], spent)
            with patch.dict("os.environ", {"NEBIUS_API_KEY": "not-a-real-key"}), \
                    patch("crashlab.worker.preflight_docker", return_value={"available": True}), \
                    patch("crashlab.worker.submit_patch") as provider:
                with self.assertRaises(ProviderError):
                    execute(store, run["id"])
            provider.assert_not_called()
            self.assertEqual(store.get(run["id"])["metrics"]["model_calls"], 6)
