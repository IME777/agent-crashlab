"""Local control-plane API. No user-supplied filesystem paths or commands."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlparse

from .config import public_config
from .manager import Manager
from .store import RunLimitExceeded, Store
from .hosting import request_allowlist
from .tasks import list_tasks


STATIC = Path(__file__).parent / "static"


def serve(root, host="127.0.0.1", port=8765, public_origin=None, max_live_runs=None):
    # TLS and judge authentication are supplied by the bundled reverse proxy.
    # Do not expose this process directly on a public interface.
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("The control plane must bind loopback behind the HTTPS reverse proxy.")
    request_allowlist(port, public_origin)
    if max_live_runs is not None and (type(max_live_runs) is not int or max_live_runs < 1):
        raise ValueError("Live run limit must be a positive integer")
    store = Store(root)
    manager = Manager(store)

    class Handler(BaseHTTPRequestHandler):
        server_version = "CrashLab/0.1"

        def log_message(self, fmt, *args):
            # Do not log request bodies, keys, model responses, or candidate source.
            pass

        def _send(self, payload, status=200, download=False):
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if download:
                self.send_header("Content-Disposition", 'attachment; filename="crashlab-report.json"')
            self.end_headers()
            self.wfile.write(body)

        def _trusted_request(self):
            hosts, origins = request_allowlist(self.server.server_port, public_origin)
            host_header = self.headers.get("Host", "")
            if host_header.lower() not in hosts:
                self._send({"error": "Host is outside the configured control-plane allowlist."}, 403)
                return False
            origin = self.headers.get("Origin")
            if origin and origin not in origins:
                self._send({"error": "Cross-origin requests are not allowed."}, 403)
                return False
            return True

        def do_GET(self):
            if not self._trusted_request():
                return
            path = urlparse(self.path).path
            try:
                if path == "/healthz":
                    return self._send({"status": "ok", "version": "0.1.0"})
                if path == "/api/config":
                    config = public_config()
                    config["max_live_runs"] = max_live_runs
                    return self._send(config)
                if path == "/api/tasks":
                    return self._send(list_tasks())
                if path == "/api/runs":
                    return self._send(store.list())
                parts = path.strip("/").split("/")
                if len(parts) in {3, 4} and parts[:2] == ["api", "runs"]:
                    if len(parts) == 4 and parts[3] != "report":
                        raise KeyError(path)
                    return self._send(store.get(parts[2]), download=len(parts) == 4)
                file = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css",
                        "/static/app.js": "app.js", "/static/style.css": "style.css"}.get(path)
                if not file:
                    return self._send({"error": "Not found"}, 404)
                body = (STATIC / file).read_bytes()
                content_type = {"html": "text/html", "js": "text/javascript", "css": "text/css"}[file.rsplit(".", 1)[1]]
                self.send_response(200)
                self.send_header("Content-Type", content_type + "; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")
                self.end_headers()
                self.wfile.write(body)
            except KeyError:
                self._send({"error": "Run or route not found"}, 404)

        def do_POST(self):
            if not self._trusted_request():
                return
            if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
                return self._send({"error": "Use application/json"}, 415)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > 8192:
                    return self._send({"error": "Request body exceeds the 8 KiB limit"}, 413)
                payload = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(payload, dict):
                    raise ValueError("Expected a JSON object")
                path = urlparse(self.path).path
                if path == "/api/runs":
                    unknown = set(payload) - {"task_id", "provider", "policy", "fault"}
                    if unknown:
                        raise ValueError("Unknown run options")
                    if not isinstance(payload.get("task_id"), str):
                        raise ValueError("Select a task_id")
                    return self._send(store.create(**payload, max_live_runs=max_live_runs), 201)
                parts = path.strip("/").split("/")
                if len(parts) == 4 and parts[:2] == ["api", "runs"]:
                    run_id, action = parts[2:]
                    if action == "start":
                        return self._send(manager.start(run_id))
                    if action == "resume":
                        return self._send(manager.start(run_id, resume=True))
                    if action == "crash":
                        return self._send(manager.crash(run_id))
                self._send({"error": "Not found"}, 404)
            except RunLimitExceeded as error:
                self._send({"error": str(error)}, 429)
            except (ValueError, TypeError, json.JSONDecodeError):
                self._send({"error": "Invalid run options or run state. Check the selected run and try again."}, 400)
            except KeyError:
                self._send({"error": "Task or run not found"}, 404)

    try:
        server = ThreadingHTTPServer((host, port), Handler)
    except OSError:
        manager.close()
        raise
    print(f"Agent CrashLab: http://{host}:{server.server_port}", flush=True)
    print("Local development control plane. Fixture runs make no model API calls.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        manager.close()
