"""Bounded single-worker supervisor. Only children it starts can be killed."""

import os
import fcntl
from pathlib import Path
import subprocess
import sys
import threading
import time

from .store import Store


def finalize_pending_request(run):
    if run["request_pending"]:
        run["metrics"]["unknown_usage_requests"] += 1
        run["request_pending"] = False
        run["notes"].append("Worker stopped before inference usage was committed; billing for that request is unknown.")


class Manager:
    def __init__(self, store: Store):
        self.store = store
        self.processes = {}
        self.lock = threading.RLock()
        self.lease = (store.root / "control-plane.lock").open("a+")
        try:
            fcntl.flock(self.lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lease.close()
            raise ValueError("Another CrashLab control plane is using this data directory.") from None
        for old in store.list():
            if old["status"] == "running":
                def orphaned(r):
                    finalize_pending_request(r)
                    r["status"] = "crashed"
                store.mutate(old["id"], orphaned,
                             "supervisor_restarted", "Previous control plane ended; run requires explicit recovery")

    def start(self, run_id, resume=False):
        with self.lock:
            for old_id, (old_process, _) in list(self.processes.items()):
                if old_process.poll() is not None:
                    self._finish(old_id, old_process, old_process.returncode)
            if self.processes:
                raise ValueError("One worker at a time in this MVP. Wait for or stop the current run.")
            run = self.store.get(run_id)
            allowed = {"crashed", "blocked"} if resume else {"queued"}
            if run["status"] not in allowed:
                raise ValueError(f"Cannot {'resume' if resume else 'start'} a {run['status']} run.")
            def claim(r):
                if resume:
                    r["metrics"]["restarts"] += 1
                    if r["request_pending"]:
                        r["metrics"]["unknown_usage_requests"] += 1
                        r["request_pending"] = False
                        r["notes"].append("A worker stopped during inference; provider billing for that request is unknown.")
                    if r["policy"] == "restart":
                        r["checkpoint"] = {}
                        r["phase"] = "prepare"
                if r["provider"] == "nebius" and not r["model"]:
                    r["model"] = os.getenv("NEBIUS_MODEL", "")
                r["status"] = "running"
            self.store.mutate(run_id, claim, "resumed" if resume else "started",
                              "Run resumed from checkpoint" if resume and run["policy"] == "resume"
                              else "Run started from the beginning")
            try:
                process = subprocess.Popen(
                    [sys.executable, "-m", "crashlab.worker", "--data", str(self.store.root), "--run", run_id,
                     "--parent", str(os.getpid())],
                    cwd=Path(__file__).resolve().parent.parent,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    env=os.environ.copy(), start_new_session=True)
            except OSError:
                self.store.mutate(run_id, lambda r: r.update(status="blocked"), "blocked", "Could not launch worker process")
                raise ValueError("Could not launch worker process") from None
            self.processes[run_id] = (process, time.monotonic())
            threading.Thread(target=self._watch, args=(run_id, process), daemon=True).start()
            return self.store.get(run_id)

    def _finish(self, run_id, process, returncode):
        with self.lock:
            entry = self.processes.get(run_id)
            if entry is None or entry[0] is not process:
                return
            duration = round((time.monotonic() - entry[1]) * 1000)
            def finish(r):
                r["metrics"]["elapsed_ms"] += duration
                finalize_pending_request(r)
                if r["status"] == "running":
                    r["status"] = "crashed"
            self.store.mutate(run_id, finish, "worker_exited", "Worker process exited",
                              {"returncode": returncode, "active_ms": duration})
            del self.processes[run_id]
            if returncode != 0 and self.store.get(run_id)["provider"] == "nebius":
                from .sandbox import cleanup_run_containers
                cleanup_run_containers(run_id)

    def _watch(self, run_id, process):
        self._finish(run_id, process, process.wait())

    def crash(self, run_id):
        with self.lock:
            entry = self.processes.get(run_id)
            if entry is None:
                raise ValueError("No active worker owned by this control plane for that run.")
            process = entry[0]
            if process.poll() is not None:
                self._finish(run_id, process, process.returncode)
                raise ValueError("The worker already exited.")
            self.store.event(run_id, "manual_crash", "User requested a real worker process kill")
            process.kill()
            code = process.wait(timeout=5)
            self._finish(run_id, process, code)
            return self.store.get(run_id)

    def wait(self, run_id, timeout=180):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.lock:
                active = run_id in self.processes
            if not active:
                return self.store.get(run_id)
            time.sleep(0.05)
        raise TimeoutError("Worker exceeded supervisor wait deadline")

    def close(self):
        with self.lock:
            ids = list(self.processes)
        for run_id in ids:
            try:
                self.crash(run_id)
            except ValueError:
                pass
        if not self.lease.closed:
            fcntl.flock(self.lease.fileno(), fcntl.LOCK_UN)
            self.lease.close()
