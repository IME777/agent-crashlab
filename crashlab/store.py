"""SQLite transactions are checkpoint boundaries, not exactly-once inference."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path
import sqlite3
import uuid


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class RunLimitExceeded(ValueError):
    pass


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "crashlab.sqlite3"
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES runs(id),
                    at TEXT NOT NULL, kind TEXT NOT NULL,
                    message TEXT NOT NULL, detail TEXT NOT NULL);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, task_id: str, provider: str = "fixture", policy: str = "resume",
               fault: str = "none", *, max_live_runs: int | None = None) -> dict:
        from .tasks import get_task
        get_task(task_id)
        if provider not in {"fixture", "nebius"}:
            raise ValueError("provider must be fixture or nebius")
        if policy not in {"resume", "restart"}:
            raise ValueError("policy must be resume or restart")
        if fault not in {"none", "worker_crash_after_patch", "model_429_once"}:
            raise ValueError("Unknown fault profile")
        if max_live_runs is not None and (type(max_live_runs) is not int or max_live_runs < 1):
            raise ValueError("Live run limit must be a positive integer")
        import os
        source_digest = hashlib.sha256()
        for file in sorted(Path(__file__).parent.glob("*.py")):
            source_digest.update(file.name.encode())
            source_digest.update(file.read_bytes())
        task = get_task(task_id)
        run_id = uuid.uuid4().hex[:16]
        data = {
            "id": run_id, "task_id": task_id, "provider": provider,
            "model": os.getenv("NEBIUS_MODEL", "") if provider == "nebius" else "trusted-fixture-v1",
            "policy": policy, "fault": fault, "status": "queued", "phase": "prepare",
            "created_at": now(), "updated_at": now(), "checkpoint": {},
            "fault_triggered": False, "request_pending": False,
            "metrics": {"model_calls": 0, "fixture_calls": 0, "input_tokens": 0,
                        "output_tokens": 0, "elapsed_ms": 0, "restarts": 0,
                        "retries": 0, "unknown_usage_requests": 0},
            "eligibility": {"live_nvidia_model": False, "mode_label":
                            "Offline fixture — no model API calls" if provider == "fixture"
                            else "Nebius live — awaiting verified response"},
            "notes": ["Results apply only to this task and fault profile; not a production reliability guarantee."]
        }
        data["versions"] = {
            "crashlab": "0.1.0",
            "runtime_sha256": source_digest.hexdigest(),
            "task_sha256": hashlib.sha256(json.dumps(task, sort_keys=True).encode()).hexdigest(),
        }
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if provider == "nebius" and max_live_runs is not None:
                count = sum(json.loads(row[0])["provider"] == "nebius"
                            for row in db.execute("SELECT data FROM runs"))
                if count >= max_live_runs:
                    raise RunLimitExceeded("The live demo run allowance has been reached. Existing reports remain available.")
            db.execute("INSERT INTO runs VALUES (?, ?)", (run_id, json.dumps(data)))
            self._event(db, run_id, "created", "Run created", {"provider": provider, "policy": policy})
        return self.get(run_id)

    def _event(self, db, run_id, kind, message, detail=None):
        db.execute("INSERT INTO events(run_id,at,kind,message,detail) VALUES(?,?,?,?,?)",
                   (run_id, now(), kind, message, json.dumps(detail or {})))

    def mutate(self, run_id, change, kind=None, message=None, detail=None):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT data FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            data = json.loads(row[0])
            change(data)
            data["updated_at"] = now()
            db.execute("UPDATE runs SET data=? WHERE id=?", (json.dumps(data), run_id))
            if kind:
                self._event(db, run_id, kind, message or kind, detail)
        return self.get(run_id)

    def event(self, run_id, kind, message, detail=None):
        return self.mutate(run_id, lambda _: None, kind, message, detail)

    def get(self, run_id) -> dict:
        with self.connection() as db:
            db.execute("BEGIN")
            row = db.execute("SELECT data FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            data = json.loads(row[0])
            rows = db.execute("SELECT id,at,kind,message,detail FROM events WHERE run_id=? ORDER BY id",
                              (run_id,)).fetchall()
        data["events"] = [{"id": r[0], "at": r[1], "kind": r[2], "message": r[3],
                           "detail": json.loads(r[4])} for r in rows]
        return data

    def list(self) -> list[dict]:
        with self.connection() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM runs ORDER BY rowid DESC LIMIT 100")]
        return [self.get(run_id) for run_id in ids]
