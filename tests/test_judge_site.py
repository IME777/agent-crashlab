from copy import deepcopy
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts.build_judge_site import ROOT, build_site, validate_evidence


class JudgeSiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "source"
        self.output = Path(self.temp.name) / "built"
        shutil.copytree(ROOT / "web-demo", self.root / "web-demo")
        (self.root / "examples").mkdir()
        for name in ("live-check.json", "live-check-initial.json", "offline-check.json"):
            shutil.copyfile(ROOT / "examples" / name, self.root / "examples" / name)

    def tearDown(self):
        self.temp.cleanup()

    def data(self):
        return [json.loads((self.root / "examples" / name).read_text())
                for name in ("live-check.json", "live-check-initial.json", "offline-check.json")]

    def test_build_is_a_positive_allowlist_without_runtime_data_or_keys(self):
        (self.root / ".env").write_text("NEBIUS_API_KEY=never-publish-this\n")
        (self.root / ".crashlab-live").mkdir()
        (self.root / ".crashlab-live" / "private.sqlite3").write_text("private state")
        manifest = build_site(self.output, root=self.root)
        files = {path.relative_to(self.output).as_posix() for path in self.output.rglob("*") if path.is_file()}
        self.assertEqual(files, set(manifest["files"]) | {"build-manifest.json"})
        self.assertNotIn(".env", files)
        self.assertFalse(any(".crashlab" in item for item in files))
        self.assertFalse(any(b"never-publish-this" in path.read_bytes() for path in self.output.rglob("*") if path.is_file()))
        config = json.loads((self.output / "site-config.json").read_text())
        self.assertFalse(config["new_inference"])
        self.assertFalse(config["hosted_worker"])
        self.assertIsNone(config["repository_url"])

    def test_summary_is_derived_from_all_actual_attempts(self):
        manifest = build_site(self.output, root=self.root)
        summary = manifest["evidence_summary"]
        self.assertEqual(summary["final"]["model_requests"], 2)
        self.assertEqual(summary["all_attempts"], {"model_requests": 6, "input_tokens": 3606,
                                                  "output_tokens": 1697, "unknown_usage_requests": 0})

    def test_claimed_pass_is_rejected_when_underlying_recovery_counts_change(self):
        final, initial, offline = self.data()
        recovery = next(case for case in final["cases"] if case["name"] == "worker_crash_and_resume")
        recovery["report"]["metrics"]["model_calls"] += 1
        with self.assertRaises(ValueError):
            validate_evidence(final, initial, offline)

    def test_private_fields_and_local_paths_block_publication(self):
        for value in ({"api_key": "must-not-publish"}, {"note": "/Users/private/person/file"}):
            with self.subTest(value=list(value)):
                data = self.data()
                data[0]["private_metadata"] = value
                with self.assertRaises(ValueError):
                    validate_evidence(*data)

    def test_preserved_initial_failure_cannot_be_relabelled_without_evidence(self):
        final, initial, offline = self.data()
        recovery = next(case for case in initial["cases"] if case["name"] == "worker_crash_and_resume")
        recovery["report"]["metrics"]["model_calls"] = recovery["before_resume"]["metrics"]["model_calls"]
        with self.assertRaises(ValueError):
            validate_evidence(final, initial, offline)

    def test_only_exact_github_repository_links_are_allowed(self):
        build_site(self.output, root=self.root, repository_url="https://github.com/example/agent-crashlab")
        self.assertEqual(json.loads((self.output / "site-config.json").read_text())["repository_url"],
                         "https://github.com/example/agent-crashlab")
        for value in ("https://token@github.com/example/repo", "javascript:alert(1)", "https://github.com/example/repo?token=secret"):
            with self.subTest(url=value), self.assertRaises(ValueError):
                build_site(self.output, root=self.root, repository_url=value)

    def test_unmanaged_output_cannot_silently_become_public(self):
        self.output.mkdir()
        (self.output / ".env").write_text("private")
        with self.assertRaises(ValueError):
            build_site(self.output, root=self.root)
        self.assertTrue((self.output / ".env").exists())

    def test_optional_archive_rejects_credential_paths_and_traversal(self):
        archive = Path(self.temp.name) / "source.zip"
        for name in ("project/.env", "../escape.py", "project/.crashlab-live/state.sqlite3"):
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr(name, "private")
            with self.subTest(name=name), self.assertRaises(ValueError):
                build_site(self.output, root=self.root, source_archive=archive)

    def test_optional_archive_and_configured_secret_are_checked_without_env_file(self):
        archive = Path(self.temp.name) / "source.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr("project/README.md", "public source")
        build_site(self.output, root=self.root, source_archive=archive)
        self.assertTrue((self.output / "downloads" / "agent-crashlab-source.zip").is_file())
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr("project/README.md", "accidentally leaked test-configured-key")
        with patch.dict(os.environ, {"NEBIUS_API_KEY": "test-configured-key"}):
            with self.assertRaises(ValueError):
                build_site(self.output, root=self.root, source_archive=archive)

    def test_source_archive_symlink_cannot_be_published(self):
        archive = Path(self.temp.name) / "source.zip"
        member = zipfile.ZipInfo("project/linked-file")
        member.create_system = 3
        member.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr(member, "/private/file")
        with self.assertRaises(ValueError):
            build_site(self.output, root=self.root, source_archive=archive)

    def test_local_asset_and_data_links_exist_and_no_api_endpoint_is_used(self):
        build_site(self.output, root=self.root)
        html = (self.output / "index.html").read_text()
        for item in re.findall(r'(?:href|src)="([^"#]+)"', html):
            if item.startswith(("http", "data:")):
                continue
            self.assertTrue((self.output / item).is_file(), item)
        js = (self.output / "app.js").read_text()
        self.assertNotIn("/api/", js)
        self.assertNotIn("innerHTML", js)
        self.assertIn("no model API calls", html)


if __name__ == "__main__":
    unittest.main()
