from pathlib import Path
import tempfile
import unittest

from deploy.activate import validate
from deploy.seed_demo import seed
from crashlab.store import Store


ROOT = Path(__file__).resolve().parents[1]


class DeploymentTests(unittest.TestCase):
    def test_configuration_requires_matching_https_origin_and_judge_hash(self):
        runtime = {"CRASHLAB_PUBLIC_ORIGIN": "https://demo.example.com", "NEBIUS_API_KEY": "test-placeholder-key",
                   "NEBIUS_MODEL": "nvidia/test", "CRASHLAB_MAX_LIVE_RUNS": "30"}
        proxy = {"CRASHLAB_DEMO_HOST": "demo.example.com", "CRASHLAB_JUDGE_PASSWORD_HASH": "$2b$" + "a" * 56}
        validate(runtime, proxy)
        proxy["CRASHLAB_DEMO_HOST"] = "wrong.example.com"
        with self.assertRaises(ValueError):
            validate(runtime, proxy)

    def test_seed_is_idempotent_and_explicitly_recorded(self):
        with tempfile.TemporaryDirectory() as root:
            report = ROOT / "examples/live-check.json"
            self.assertEqual(seed(Path(root), [report]), 2)
            self.assertEqual(seed(Path(root), [report]), 0)
            runs = Store(root).list()
            self.assertEqual(len(runs), 2)
            for run in runs:
                self.assertIn("imported_evidence", run)
                self.assertEqual(run["events"][-1]["kind"], "recorded_evidence_imported")
                self.assertEqual(run["metrics"]["fixture_calls"], 0)
