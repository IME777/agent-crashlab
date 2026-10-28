import copy
import unittest

from crashlab.cli import release_checks


class ReleaseTests(unittest.TestCase):
    def run_report(self):
        return {"status": "passed", "provider": "fixture", "fault": "worker_crash_after_patch",
                "fault_triggered": True, "metrics": {"restarts": 1},
                "checkpoint": {"tests": {"passed": True}},
                "events": [{"kind": "worker_exited", "detail": {"returncode": 86}}],
                "eligibility": {"live_nvidia_model": False}}

    def test_successful_artifact_without_actual_crash_cannot_pass_crash_profile(self):
        run = self.run_report()
        run["events"] = []
        self.assertFalse(release_checks(run)["fault_profile_verified"])

    def test_actual_fault_and_independent_acceptance_pass_checks(self):
        self.assertTrue(all(release_checks(self.run_report()).values()))

    def test_live_gate_requires_actual_model_response_evidence(self):
        run = self.run_report()
        run["provider"] = "nebius"
        self.assertFalse(release_checks(run)["provider_evidence_valid"])

    def test_failed_test_cannot_pass_due_to_status_alone(self):
        run = self.run_report()
        run["checkpoint"]["tests"]["passed"] = False
        self.assertFalse(release_checks(run)["acceptance_passed"])
