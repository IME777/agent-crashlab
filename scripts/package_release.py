"""Create an allowlisted, deterministic source archive with a checksum manifest.

No credentials are required. --scan-local-env is an explicit owner-only option
to check locally configured secret values without adding .env to the archive.
"""

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import tarfile
import tempfile
import tomllib
import zipfile


ROOT_FILES = frozenset({
    "README.md", "LICENSE", "pyproject.toml", ".gitignore", ".env.example",
    "CONTRIBUTING.md", "SECURITY.md", ".dockerignore", "Dockerfile",
    "compose.yaml", "compose.yml", "docker-compose.yml", "Procfile",
    "render.yaml", "fly.toml", "Makefile",
})
ROOT_DIRS = frozenset({"crashlab", "docs", "examples", "scripts", "tests", ".github", "deploy", "web-demo"})
BLOCKED_DIRS = frozenset({
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache",
    "node_modules", "dist", "build", ".cache",
})
BLOCKED_SUFFIXES = (".pyc", ".pyo", ".sqlite", ".sqlite3", ".db", ".db-shm", ".db-wal",
                    ".zip", ".tar", ".tar.gz", ".tgz", ".gz", ".7z", ".pem", ".key",
                    ".p12", ".pfx", ".log", ".tmp", ".bak", "~")
CREDENTIAL_NAME = re.compile(r"(^|[-_.])(credentials?|secrets?|private[-_]?key|service[-_]?account)([-_.]|$)", re.I)
SECRET_ENV_NAME = re.compile(r"(^|_)(API_KEY|TOKEN|PASSWORD|PRIVATE_KEY|SECRET_ACCESS_KEY|CLIENT_SECRET)$")
PREFIX = "agent-crashlab"
MANIFEST_NAME = "RELEASE-MANIFEST.json"


class ReleaseError(ValueError):
    pass


def validate_member_path(name: str) -> str:
    """Archive consumers must never receive absolute or traversal paths."""
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or "\\" in name or
            any(part in {"", ".", ".."} for part in name.split("/")) or
            any(ord(character) < 32 for character in name) or ":" in name):
        raise ReleaseError("Unsafe source archive member path.")
    return path.as_posix()


def excluded(relative: Path) -> bool:
    parts = relative.parts
    for index, part in enumerate(parts):
        root_exception = index == 0 and len(parts) == 1 and part in ROOT_FILES
        if part in BLOCKED_DIRS or part.startswith(".crashlab") or part.endswith(".egg-info"):
            return True
        if part.startswith(".env") and not (root_exception and part == ".env.example"):
            return True
        if part.startswith(".") and not (index == 0 and part == ".github") and not root_exception:
            return True
        if CREDENTIAL_NAME.search(part):
            return True
    return relative.name.endswith(BLOCKED_SUFFIXES) or ".sqlite3" in relative.name or relative.name == ".DS_Store"


def source_files(root: Path) -> list[Path]:
    root = root.resolve()
    selected = []
    for name in sorted(ROOT_FILES | ROOT_DIRS):
        path = root / name
        if not path.exists() and not path.is_symlink():
            continue
        if path.is_symlink():
            raise ReleaseError(f"Symlink is not allowed in source package: {name}")
        if name in ROOT_FILES:
            if not path.is_file():
                raise ReleaseError(f"Expected a regular source file: {name}")
            selected.append(path)
            continue
        if not path.is_dir():
            raise ReleaseError(f"Expected a source directory: {name}")
        for directory, directories, filenames in os.walk(path, followlinks=False):
            directory_path = Path(directory)
            kept = []
            for child in directories:
                candidate = directory_path / child
                relative = candidate.relative_to(root)
                if excluded(relative):
                    continue
                if candidate.is_symlink():
                    raise ReleaseError(f"Symlink is not allowed in source package: {relative.as_posix()}")
                kept.append(child)
            directories[:] = sorted(kept)
            for child in sorted(filenames):
                candidate = directory_path / child
                relative = candidate.relative_to(root)
                if excluded(relative):
                    continue
                if candidate.is_symlink():
                    raise ReleaseError(f"Symlink is not allowed in source package: {relative.as_posix()}")
                if not candidate.is_file():
                    raise ReleaseError(f"Non-regular source file: {relative.as_posix()}")
                validate_member_path(relative.as_posix())
                selected.append(candidate)
    return sorted(selected, key=lambda file: file.relative_to(root).as_posix())


def environment_secrets(environ=None) -> tuple[bytes, ...]:
    """Short placeholders are ignored; supplied actual values are never printed."""
    environ = os.environ if environ is None else environ
    return tuple({value.encode() for name, value in environ.items()
                  if SECRET_ENV_NAME.search(name.upper()) and isinstance(value, str) and len(value) >= 8})


def build_contents(root: Path, *, secret_values=None, epoch=0) -> dict[str, bytes]:
    root = root.resolve()
    if epoch < 0:
        raise ReleaseError("SOURCE_DATE_EPOCH must not be negative.")
    secrets = environment_secrets() if secret_values is None else tuple(
        value.encode() if isinstance(value, str) else value for value in secret_values if value)
    contents = {}
    entries = []
    for path in source_files(root):
        relative = validate_member_path(path.relative_to(root).as_posix())
        data = path.read_bytes()
        if any(secret in data or secret in relative.encode() for secret in secrets):
            raise ReleaseError("A configured secret value was found in source content or a filename; no archive was written.")
        contents[relative] = data
        entries.append({"path": relative, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    if not {"README.md", "LICENSE", "pyproject.toml"}.issubset(contents):
        raise ReleaseError("Source package requires README.md, LICENSE and pyproject.toml.")
    try:
        version = tomllib.loads(contents["pyproject.toml"].decode())["project"]["version"]
    except (ValueError, KeyError, UnicodeError):
        raise ReleaseError("Cannot read the project version from pyproject.toml.") from None
    manifest = {"schema_version": 1, "project": PREFIX, "version": version,
                "source_date_epoch": epoch, "files": entries,
                "notes": ["Paths are relative to the source root.",
                          "The manifest lists package files, excluding its own self-referential checksum.",
                          "Runtime state, credentials, caches and previous archives are excluded."]}
    contents[MANIFEST_NAME] = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    return contents


def make_archive(root: Path, output: Path, *, archive_format="zip", secret_values=None, epoch=0) -> dict:
    if archive_format not in {"zip", "tar.gz"}:
        raise ReleaseError("Archive format must be zip or tar.gz.")
    root = root.resolve()
    output = output.resolve()
    expected_suffix = ".zip" if archive_format == "zip" else ".tar.gz"
    if not output.name.endswith(expected_suffix):
        raise ReleaseError(f"Output name must end in {expected_suffix}.")
    contents = build_contents(root, secret_values=secret_values, epoch=epoch)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="crashlab-release-") as temporary:
        target = Path(temporary) / output.name
        if archive_format == "zip":
            with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as archive:
                for name, data in sorted(contents.items()):
                    member = zipfile.ZipInfo(f"{PREFIX}/{validate_member_path(name)}", date_time=(1980, 1, 1, 0, 0, 0))
                    member.external_attr = 0o100644 << 16
                    member.create_system = 3
                    archive.writestr(member, data)
        else:
            with target.open("wb") as destination:
                with gzip.GzipFile(filename="", fileobj=destination, mode="wb", mtime=epoch) as compressed:
                    with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                        for name, data in sorted(contents.items()):
                            member = tarfile.TarInfo(f"{PREFIX}/{validate_member_path(name)}")
                            member.size = len(data)
                            member.mode = 0o644
                            member.mtime = epoch
                            member.uid = member.gid = 0
                            member.uname = member.gname = ""
                            archive.addfile(member, io.BytesIO(data))
        archive_bytes = target.read_bytes()
        digest = hashlib.sha256(archive_bytes).hexdigest()
        staged = output.with_name(output.name + ".tmp")
        staged.write_bytes(archive_bytes)
        staged.replace(output)
    checksum = output.with_name(output.name + ".sha256")
    checksum.write_text(f"{digest}  {output.name}\n")
    return {"archive": str(output), "sha256": digest, "bytes": output.stat().st_size,
            "files": len(contents), "checksum_file": str(checksum)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("dist/agent-crashlab-source.zip"))
    parser.add_argument("--format", choices=["zip", "tar.gz"], default="zip")
    parser.add_argument("--scan-local-env", action="store_true",
                        help="Owner-only: load .env into memory for a configured-secret scan; never package it")
    args = parser.parse_args()
    try:
        if args.scan_local_env:
            from crashlab.config import load_env
            load_env(args.root / ".env")
        epoch = int(os.getenv("SOURCE_DATE_EPOCH", "0"))
        result = make_archive(args.root, args.output, archive_format=args.format, epoch=epoch)
    except (ReleaseError, OSError, ValueError) as error:
        # Errors never contain file contents or configured secret values.
        print(json.dumps({"packaged": False, "error": str(error)}))
        return 1
    print(json.dumps({"packaged": True, **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
