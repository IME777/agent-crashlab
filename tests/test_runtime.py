import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from crashlab.manager import Manager
from crashlab.store import Store
from crashlab.tasks import list_tasks


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.manager = Manager(self.store)

    def tearDown(self):
        self.manager.close()
        self.temp.cleanup()

    def run_to_stop(self, **options):
        run = self.store.create("capped-backoff", **options)
        self.manager.start(run["id"])
        return self.manager.wait(run["id"], timeout=20)

    def test_all_tasks_deliver_passing_independent_artifacts(self):
        for task in list_tasks():
            with self.subTest(task=task["id"]):
                run = self.store.create(task["id"])
                self.manager.start(run["id"])
                report = self.manager.wait(run["id"])
                self.assertEqual(report["status"], "passed")
                self.assertTrue(report["checkpoint"]["tests"]["passed"])
                self.assertFalse(report["eligibility"]["live_nvidia_model"])
                self.assertEqual(report["metrics"]["model_calls"], 0)
                self.assertEqual(report["metrics"]["fixture_calls"], 1)

    def test_real_process_crash_recovery_reuses_committed_patch(self):
        report = self.run_to_stop(fault="worker_crash_after_patch", policy="resume")
        self.assertEqual(report["status"], "crashed")
        self.assertEqual(report["phase"], "validate")
        self.assertTrue(any(e["detail"].get("returncode") == 86 for e in report["events"]))
        original_source = report["checkpoint"]["source"]
        self.manager.start(report["id"], resume=True)
        recovered = self.manager.wait(report["id"])
        self.assertEqual(recovered["status"], "passed")
        self.assertEqual(recovered["checkpoint"]["source"], original_source)
        self.assertEqual(recovered["metrics"]["fixture_calls"], 1)
        self.assertEqual(recovered["metrics"]["restarts"], 1)
        self.assertEqual((Path(self.temp.name) / "workspaces" / report["id"] / "solution.py").read_text(), original_source)

    def test_restart_baseline_repeats_generation_and_preserves_counters(self):
        report = self.run_to_stop(fault="worker_crash_after_patch", policy="restart")
        self.manager.start(report["id"], resume=True)
        recovered = self.manager.wait(report["id"])
        self.assertEqual(recovered["status"], "passed")
        self.assertEqual(recovered["metrics"]["fixture_calls"], 2)
        self.assertTrue(recovered["fault_triggered"])

    def test_synthetic_throttle_does_not_count_as_a_live_request(self):
        report = self.run_to_stop(fault="model_429_once")
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["metrics"]["retries"], 1)
        self.assertEqual(report["metrics"]["model_calls"], 0)
        self.assertTrue(any(e["detail"].get("synthetic") for e in report["events"]))

    def test_restart_control_plane_keeps_durable_run(self):
        report = self.run_to_stop(fault="worker_crash_after_patch")
        self.manager.close()
        self.store = Store(self.temp.name)
        self.manager = Manager(self.store)
        self.manager.start(report["id"], resume=True)
        recovered = self.manager.wait(report["id"])
        self.assertEqual(recovered["status"], "passed")
        self.assertEqual(recovered["metrics"]["fixture_calls"], 1)

    def test_single_control_plane_lease(self):
        with self.assertRaises(ValueError):
            Manager(self.store)

    def test_live_mode_without_credentials_is_blocked_not_faked(self):
        with patch.dict(os.environ, {"NEBIUS_API_KEY": "", "NEBIUS_MODEL": ""}):
            report = self.run_to_stop(provider="nebius")
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["metrics"]["model_calls"], 0)
        self.assertEqual(report["metrics"]["fixture_calls"], 0)
        self.assertFalse(report["eligibility"]["live_nvidia_model"])

    def test_interrupted_request_is_unknown_before_any_resume(self):
        run = self.store.create("capped-backoff", provider="nebius")
        def in_flight(r):
            r.update(status="running", request_pending=True)
            r["metrics"]["model_calls"] = 1
        self.store.mutate(run["id"], in_flight)
        process = object()
        self.manager.processes[run["id"]] = (process, time.monotonic())
        with patch("crashlab.sandbox.cleanup_run_containers"):
            self.manager._finish(run["id"], process, -9)
        report = self.store.get(run["id"])
        self.assertEqual(report["status"], "crashed")
        self.assertEqual(report["metrics"]["unknown_usage_requests"], 1)
        self.assertFalse(report["request_pending"])

    def test_docker_preflight_prevents_spending_tokens_when_unavailable(self):
        from crashlab.provider import ProviderError
        from crashlab.worker import execute
        run = self.store.create("capped-backoff", provider="nebius")
        with patch.dict(os.environ, {"NEBIUS_API_KEY": "test-key", "NEBIUS_MODEL": "nvidia/test"}), \
                patch("crashlab.worker.preflight_docker", return_value={"available": False, "error": "Docker unavailable"}), \
                patch("crashlab.worker.submit_patch") as provider:
            with self.assertRaises(ProviderError):
                execute(self.store, run["id"])
        provider.assert_not_called()
        self.assertEqual(self.store.get(run["id"])["metrics"]["model_calls"], 0)


if __name__ == "__main__":
    unittest.main()
