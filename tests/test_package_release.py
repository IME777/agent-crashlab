import hashlib
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts.package_release import ReleaseError, make_archive, validate_member_path


class PackageReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "source"
        self.root.mkdir()
        self.write("README.md", "Public project\n")
        self.write("LICENSE", "MIT\n")
        self.write("pyproject.toml", '[project]\nname = "agent-crashlab"\nversion = "0.1.0"\n')
        self.write(".env.example", "NEBIUS_API_KEY=\n")
        self.write("crashlab/main.py", "def main():\n    return 0\n")
        self.write("docs/guide.md", "Run the checks.\n")
        self.write("examples/report.json", '{"passed": true}\n')
        self.output = Path(self.temporary.name) / "release.zip"

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)
        return path

    def test_only_source_and_manifest_are_exported_with_no_runtime_or_credentials(self):
        for name in [".env", ".crashlab-live/run.json", ".git/config", "docs/.env", "docs/private-key.pem",
                     "examples/report.json.tmp", "docs/__pycache__/test.pyc", "examples/old.zip",
                     "docs/runtime.sqlite3-wal", "unrelated/personal.txt", "docs/service-account.json"]:
            self.write(name, "must-not-ship")
        result = make_archive(self.root, self.output, secret_values=())
        with zipfile.ZipFile(self.output) as archive:
            names = set(archive.namelist())
            self.assertIn("agent-crashlab/.env.example", names)
            self.assertIn("agent-crashlab/crashlab/main.py", names)
            self.assertFalse(any(b"must-not-ship" in archive.read(name) for name in names))
            manifest = json.loads(archive.read("agent-crashlab/RELEASE-MANIFEST.json"))
            self.assertEqual(manifest["version"], "0.1.0")
            self.assertNotIn(str(self.root), json.dumps(manifest))
            for entry in manifest["files"]:
                content = archive.read("agent-crashlab/" + entry["path"])
                self.assertEqual(entry["sha256"], hashlib.sha256(content).hexdigest())
        self.assertEqual(result["sha256"], hashlib.sha256(self.output.read_bytes()).hexdigest())

    def test_zip_is_reproducible_when_only_filesystem_times_change(self):
        first = make_archive(self.root, self.output, secret_values=())["sha256"]
        os.utime(self.root / "README.md", (1000000000, 1000000000))
        second = make_archive(self.root, self.output, secret_values=())["sha256"]
        self.assertEqual(first, second)

    def test_deploy_and_web_sources_ship_but_nested_runtime_and_env_do_not(self):
        self.write("deploy/Caddyfile", "example.invalid { reverse_proxy localhost:8765 }\n")
        self.write("deploy/systemd/crashlab.service", "[Service]\nExecStart=python -m crashlab serve\n")
        self.write("web-demo/index.html", "<title>CrashLab evidence</title>\n")
        self.write("web-demo/src/app.js", "console.log('public viewer');\n")
        for name in ["deploy/.env", "deploy/.crashlab/data.json", "web-demo/.env.local",
                     "web-demo/.crashlab-live/runtime.json", "web-demo/node_modules/private.txt"]:
            self.write(name, "nested-private-value")
        make_archive(self.root, self.output, secret_values=())
        with zipfile.ZipFile(self.output) as archive:
            names = set(archive.namelist())
            self.assertIn("agent-crashlab/deploy/Caddyfile", names)
            self.assertIn("agent-crashlab/deploy/systemd/crashlab.service", names)
            self.assertIn("agent-crashlab/web-demo/index.html", names)
            self.assertIn("agent-crashlab/web-demo/src/app.js", names)
            self.assertFalse(any(b"nested-private-value" in archive.read(name) for name in names))

    def test_tar_has_relative_regular_members_and_a_manifest(self):
        output = self.output.with_suffix(".tar.gz")
        make_archive(self.root, output, archive_format="tar.gz", secret_values=())
        with tarfile.open(output, "r:gz") as archive:
            members = archive.getmembers()
            self.assertTrue(all(member.isfile() and member.name.startswith("agent-crashlab/") for member in members))
            self.assertTrue(all(member.uid == member.gid == 0 for member in members))
            self.assertIn("agent-crashlab/RELEASE-MANIFEST.json", [member.name for member in members])

    def test_known_secret_in_allowed_content_aborts_without_printing_it(self):
        secret = "not-a-real-key-123456789"
        self.write("docs/accidental.md", f"An accidental value: {secret}\n")
        with patch.dict(os.environ, {"NEBIUS_API_KEY": secret}):
            with self.assertRaises(ReleaseError) as failure:
                make_archive(self.root, self.output)
        self.assertNotIn(secret, str(failure.exception))
        self.assertFalse(self.output.exists())
        self.assertFalse(self.output.with_name(self.output.name + ".sha256").exists())

    def test_file_symlink_cannot_export_an_external_file(self):
        outside = Path(self.temporary.name) / "outside.txt"
        outside.write_text("private")
        (self.root / "docs" / "linked.txt").symlink_to(outside)
        with self.assertRaises(ReleaseError):
            make_archive(self.root, self.output, secret_values=())

    def test_secret_value_in_filename_is_not_exported_or_printed(self):
        secret = "not-a-real-key-filename-1234"
        self.write(f"docs/{secret}.md", "ordinary content")
        with self.assertRaises(ReleaseError) as failure:
            make_archive(self.root, self.output, secret_values=(secret,))
        self.assertNotIn(secret, str(failure.exception))
        self.assertFalse(self.output.exists())

    def test_directory_symlink_cannot_export_an_external_tree(self):
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        (outside / "private.txt").write_text("private")
        (self.root / "docs" / "linked").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ReleaseError):
            make_archive(self.root, self.output, secret_values=())

    def test_archive_paths_reject_traversal_absolute_and_windows_forms(self):
        for path in ["../outside", "/outside", "docs/../../outside", "docs\\..\\outside", "C:/outside", "docs/./file"]:
            with self.subTest(path=path), self.assertRaises(ReleaseError):
                validate_member_path(path)

    def test_packaging_never_requires_or_reads_local_env(self):
        self.write(".env", "This is not a valid environment file; it must never be read.\n")
        with patch("crashlab.config.load_env", side_effect=AssertionError("must not read .env")):
            make_archive(self.root, self.output, secret_values=())
        self.assertTrue(self.output.exists())


if __name__ == "__main__":
    unittest.main()
