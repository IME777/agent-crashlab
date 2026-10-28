from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from crashlab.sandbox import (_container_deadline_wrapper, _execute, cleanup_run_containers,
                             preflight_docker, run_tests, validate_candidate)
from crashlab.tasks import get_task, list_tasks


class AcceptanceRunnerTests(unittest.TestCase):
    def test_all_starters_fail_and_solutions_pass_independent_tests(self):
        for metadata in list_tasks():
            task = get_task(metadata["id"])
            with self.subTest(task=task["id"], source="starter"):
                result = run_tests(task["id"], task["starter"])
                self.assertFalse(result["passed"])
                self.assertEqual(result["returncode"], 1)
                self.assertIn("FAIL", result["stdout"])
            with self.subTest(task=task["id"], source="solution"):
                result = run_tests(task["id"], task["solution"])
                self.assertTrue(result["passed"], result)

    def test_public_metadata_never_contains_solution_or_tests(self):
        for metadata in list_tasks():
            self.assertEqual(set(metadata), {"id", "title", "description"})

    def test_definitions_are_detached(self):
        task = get_task("page-slices")
        task["solution"] = "changed"
        self.assertNotEqual(get_task("page-slices")["solution"], "changed")

    def test_unknown_task_is_reported_without_execution(self):
        with patch("crashlab.sandbox.subprocess.run") as execute:
            result = run_tests("missing", "print('never run')")
            self.assertFalse(result["passed"])
            self.assertIn("Unknown repair task", result["error"])
            execute.assert_not_called()

    def test_fixture_refuses_arbitrary_source_without_execution(self):
        with patch("crashlab.sandbox.subprocess.run") as execute:
            result = run_tests("token-budget", "raise RuntimeError('not trusted')")
            self.assertFalse(result["passed"])
            self.assertIn("only trusted", result["error"])
            execute.assert_not_called()

    def test_source_limit(self):
        result = run_tests("token-budget", "x" * (64 * 1024 + 1))
        self.assertFalse(result["passed"])
        self.assertIn("64 KiB", result["validation_error"])
        self.assertEqual(result["returncode"], 1)
        self.assertNotIn("error", result)

    def test_missing_docker_is_actionable_and_never_pulls(self):
        with patch("crashlab.sandbox.shutil.which", return_value=None):
            with patch("crashlab.sandbox.subprocess.run") as execute:
                result = run_tests("token-budget", "def repair():\n    return 1\n", "docker")
                self.assertFalse(result["passed"])
                self.assertIn("Docker CLI", result["error"])
                execute.assert_not_called()

    def test_docker_runs_independent_tests_without_host_secrets(self):
        with patch("crashlab.sandbox.shutil.which", return_value="/usr/bin/docker"):
            with patch("crashlab.sandbox.subprocess.run", return_value=subprocess.CompletedProcess([], 0)) as inspect:
                with patch("crashlab.sandbox._execute", return_value=(0, "OK", None)) as execute:
                    result = run_tests("token-budget", "def repair():\n    return 1\n", "docker")
                    self.assertTrue(result["passed"])
                    command = execute.call_args.args[0]
                    for flag in ["--pull=never", "--network=none", "--read-only", "--cap-drop=ALL",
                                 "--security-opt=no-new-privileges", "--pids-limit=64", "--memory=256m"]:
                        self.assertIn(flag, command)
                    self.assertIn("--user=65534:65534", command)
                    self.assertRegex(command[command.index("--label") + 1], r"^agent-crashlab.run=[0-9a-f]{16}$")
                    self.assertEqual(command[-4:-1], ["python", "-B", "-c"])
                    self.assertIn("timeout=12", command[-1])
                    self.assertNotIn("-e", command)
                    self.assertEqual(inspect.call_args_list[0].args[0],
                                     ["docker", "image", "inspect", "python:3.12-slim"])
                    self.assertEqual(inspect.call_args_list[-1].args[0][:3], ["docker", "rm", "-f"])

    def test_runner_output_is_bounded(self):
        code, output, error = _execute([sys.executable, "-c", "print('a' * 70000)"], Path.cwd())
        self.assertEqual(code, 124)
        self.assertLessEqual(len(output.encode()), 64 * 1024)
        self.assertIn("output exceeded", error)

    def test_runner_deadline_stops_process(self):
        with patch("crashlab.sandbox.TEST_TIMEOUT_SECONDS", 0.05):
            code, _, error = _execute([sys.executable, "-c", "import time; time.sleep(5)"], Path.cwd())
        self.assertEqual(code, 124)
        self.assertIn("exceeded", error)

    def test_all_fixtures_fit_the_pure_function_domain(self):
        for metadata in list_tasks():
            task = get_task(metadata["id"])
            for field in ("starter", "solution"):
                with self.subTest(task=task["id"], field=field):
                    self.assertIsNone(validate_candidate(task[field]))

    def test_candidate_guard_rejects_harness_tampering_and_indirect_calls(self):
        candidates = [
            "import unittest\ndef repair():\n    return 1\n",
            "def repair():\n    import unittest\n    unittest.TestCase.assertEqual = lambda *args: None\n",
            "def repair():\n    return __builtins__\n",
            "def repair():\n    return (1).__class__\n",
            "def repair(callback):\n    return callback()\n",
            "def repair():\n    return (lambda: 1)()\n",
            "def repair():\n    return eval('1')\n",
            "@staticmethod\ndef repair():\n    return 1\n",
            "def repair():\n    global leaked\n    return 1\n",
            "class Repair:\n    pass\n",
            "def __getattr__(name):\n    return 1\n",
        ]
        for source in candidates:
            with self.subTest(source=source):
                self.assertIsNotNone(validate_candidate(source))

    def test_invalid_candidate_is_failed_without_spending_environment_work(self):
        for source in ["def repair(:", "x" * (64 * 1024 + 1)]:
            with self.subTest(source=source[:30]):
                with patch("crashlab.sandbox.preflight_docker") as preflight:
                    result = run_tests("token-budget", source, "docker")
                    self.assertFalse(result["passed"])
                    self.assertTrue(result["candidate_invalid"])
                    self.assertNotIn("error", result)
                    preflight.assert_not_called()

    def test_preflight_reports_unavailable_image_without_pulling(self):
        with patch("crashlab.sandbox.shutil.which", return_value="/usr/bin/docker"):
            with patch("crashlab.sandbox.subprocess.run", return_value=subprocess.CompletedProcess([], 1)) as execute:
                result = preflight_docker()
                self.assertFalse(result["available"])
                self.assertIn("docker pull", result["error"])
                self.assertEqual(execute.call_args.args[0], ["docker", "image", "inspect", "python:3.12-slim"])

    def test_candidate_resource_exhaustion_is_not_an_environment_blocker(self):
        task = get_task("token-budget")
        with patch("crashlab.sandbox._execute", return_value=(124, "partial output", "time limit exceeded")):
            result = run_tests(task["id"], task["solution"])
            self.assertFalse(result["passed"])
            self.assertTrue(result["resource_exceeded"])
            self.assertTrue(result["candidate_invalid"])
            self.assertNotIn("error", result)

    def test_unavailable_daemon_is_structured_environment_error(self):
        task = get_task("token-budget")
        with patch("crashlab.sandbox.preflight_docker", return_value={"available": False, "error": "Start Docker."}):
            with patch("crashlab.sandbox._execute") as execute:
                result = run_tests(task["id"], task["solution"], "docker")
                self.assertFalse(result["passed"])
                self.assertEqual(result["returncode"], 2)
                self.assertEqual(result["error"], "Start Docker.")
                self.assertNotIn("candidate_invalid", result)
                execute.assert_not_called()

    def test_docker_launch_exit_codes_are_environment_errors(self):
        task = get_task("token-budget")
        for returncode in (125, 126, 127):
            with self.subTest(returncode=returncode):
                with patch("crashlab.sandbox.preflight_docker", return_value={"available": True}):
                    with patch("crashlab.sandbox._execute", return_value=(returncode, "launch detail", None)):
                        with patch("crashlab.sandbox.subprocess.run"):
                            result = run_tests(task["id"], task["solution"], "docker")
                            self.assertEqual(result["returncode"], returncode)
                            self.assertIn("Docker could not launch", result["error"])
                            self.assertNotIn("candidate_invalid", result)

    def test_docker_container_is_labelled_with_its_run(self):
        task = get_task("token-budget")
        with patch("crashlab.sandbox.preflight_docker", return_value={"available": True}):
            with patch("crashlab.sandbox._execute", return_value=(0, "OK", None)) as execute:
                with patch("crashlab.sandbox.subprocess.run"):
                    run_tests(task["id"], task["solution"], "docker", run_id="0123456789abcdef")
        command = execute.call_args.args[0]
        self.assertIn("agent-crashlab.run=0123456789abcdef", command)

    def test_invalid_run_ids_never_reach_docker(self):
        task = get_task("token-budget")
        for invalid_id in ("", "x", "0123456789ABCDEF", "--all", "a" * 17, None):
            with self.subTest(run_id=invalid_id), patch("crashlab.sandbox.subprocess.run") as execute:
                result = cleanup_run_containers(invalid_id)
                self.assertIn("error", result)
                if invalid_id is not None:
                    result = run_tests(task["id"], task["solution"], "docker", run_id=invalid_id)
                    self.assertIn("error", result)
                execute.assert_not_called()

    def test_cleanup_removes_only_ids_returned_by_exact_run_label(self):
        responses = [subprocess.CompletedProcess([], 0, "abcdef012345\n012345abcdef\n", ""),
                     subprocess.CompletedProcess([], 0, "", "")]
        with patch("crashlab.sandbox.shutil.which", return_value="/usr/bin/docker"):
            with patch("crashlab.sandbox.subprocess.run", side_effect=responses) as execute:
                result = cleanup_run_containers("0123456789abcdef")
        self.assertEqual(result["removed"], ["abcdef012345", "012345abcdef"])
        self.assertEqual(execute.call_args_list[0].args[0], [
            "docker", "ps", "--filter", "label=agent-crashlab.run=0123456789abcdef", "--format", "{{.ID}}"])
        self.assertEqual(execute.call_args_list[1].args[0], ["docker", "rm", "-f", "abcdef012345", "012345abcdef"])
        self.assertTrue(all(call.kwargs["timeout"] == 5 for call in execute.call_args_list))

    def test_cleanup_rejects_arbitrary_container_names_or_flags(self):
        for output in ("--all", "unrelated-container", "abcdef012345\n--force", "a" * 11):
            with self.subTest(output=output), patch("crashlab.sandbox.shutil.which", return_value="/usr/bin/docker"):
                with patch("crashlab.sandbox.subprocess.run", return_value=subprocess.CompletedProcess([], 0, output, "")) as execute:
                    result = cleanup_run_containers("0123456789abcdef")
                    self.assertIn("error", result)
                    self.assertEqual(result["removed"], [])
                    self.assertEqual(execute.call_count, 1)

    def test_trusted_container_wrapper_enforces_its_own_deadline(self):
        with tempfile.TemporaryDirectory(prefix="crashlab-wrapper-test-") as directory:
            Path(directory, "test_acceptance.py").write_text("import time\ntime.sleep(10)\n", encoding="utf-8")
            with patch("crashlab.sandbox.TEST_TIMEOUT_SECONDS", 0.05):
                result = subprocess.run([sys.executable, "-c", _container_deadline_wrapper()],
                                        cwd=directory, capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 124)
        self.assertIn("container execution deadline", result.stdout)

    def test_container_side_timeout_is_still_a_candidate_failure(self):
        task = get_task("token-budget")
        with patch("crashlab.sandbox._execute", return_value=(124, "container deadline", None)):
            result = run_tests(task["id"], task["solution"])
            self.assertFalse(result["passed"])
            self.assertTrue(result["candidate_invalid"])
            self.assertNotIn("error", result)


if __name__ == "__main__":
    unittest.main()
