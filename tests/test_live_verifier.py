"""Pure helper tests with synthetic reports; no credentials or remote calls."""

import unittest

from scripts.verify_live import case_checks, recovery_checks, source_digest


class LiveVerifierTests(unittest.TestCase):
    def report(self):
        return {
            "id": "synthetic-only", "provider": "nebius", "model": "nvidia/mock",
            "status": "passed", "phase": "done", "fault_triggered": True,
            "checkpoint": {"source": "def repair():\n    return 1\n",
                           "tests": {"mode": "docker", "passed": True}},
            "metrics": {"model_calls": 1, "fixture_calls": 0, "input_tokens": 100,
                        "output_tokens": 25, "restarts": 1, "unknown_usage_requests": 0},
            "eligibility": {"live_nvidia_model": True},
            "events": [{"kind": "worker_exited", "detail": {"returncode": 86}}],
        }

    def before(self):
        result = self.report()
        result.update(status="crashed", phase="validate")
        result["metrics"]["restarts"] = 0
        result["checkpoint"].pop("tests")
        return result

    def test_live_case_requires_actual_evidence_not_success_status_alone(self):
        result = self.report()
        self.assertTrue(all(case_checks(result, "nvidia/mock").values()))
        result["eligibility"]["live_nvidia_model"] = False
        self.assertFalse(case_checks(result, "nvidia/mock")["live_nvidia_response"])

    def test_fixture_or_host_acceptance_cannot_pass_live_case(self):
        result = self.report()
        result["checkpoint"]["tests"]["mode"] = "fixture"
        result["metrics"]["fixture_calls"] = 1
        checks = case_checks(result, "nvidia/mock")
        self.assertFalse(checks["docker_acceptance"])
        self.assertFalse(checks["no_fixture_steps"])

    def test_recovery_requires_observed_real_crash_and_unchanged_candidate(self):
        before, after = self.before(), self.report()
        self.assertTrue(all(recovery_checks(before, after, "nvidia/mock").values()))
        before["events"] = []
        self.assertFalse(recovery_checks(before, after, "nvidia/mock")["real_worker_exit_86"])

    def test_extra_generation_is_not_claimed_as_checkpoint_reuse(self):
        before, after = self.before(), self.report()
        after["metrics"]["model_calls"] = 2
        after["checkpoint"]["source"] += "\n"
        checks = recovery_checks(before, after, "nvidia/mock")
        self.assertFalse(checks["no_additional_model_requests_after_resume"])
        self.assertFalse(checks["same_saved_candidate"])

    def test_model_and_token_changes_are_visible(self):
        before, after = self.before(), self.report()
        after["model"] = "nvidia/other"
        after["metrics"]["output_tokens"] += 1
        checks = recovery_checks(before, after, "nvidia/mock")
        self.assertFalse(checks["model_unchanged_on_resume"])
        self.assertFalse(checks["known_token_totals_unchanged_on_resume"])

    def test_source_hash_is_derived_not_trusted_from_report(self):
        result = self.report()
        result["checkpoint"]["source_sha256"] = "forged"
        self.assertEqual(len(source_digest(result)), 64)
        self.assertNotEqual(source_digest(result), "forged")


if __name__ == "__main__":
    unittest.main()
