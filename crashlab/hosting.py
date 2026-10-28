"""Explicit reverse-proxy origin policy; the application still binds loopback."""

from urllib.parse import urlsplit


def request_allowlist(port: int, public_origin: str | None = None) -> tuple[set[str], set[str]]:
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origins = {f"http://{host}" for host in hosts}
    if public_origin:
        url = urlsplit(public_origin)
        if (url.scheme != "https" or not url.hostname or url.username or url.password
                or url.path not in {"", "/"} or url.query or url.fragment):
            raise ValueError("Public origin must be a single HTTPS origin without credentials or a path.")
        try:
            url.port
        except ValueError:
            raise ValueError("Public origin has an invalid port.") from None
        host = url.netloc.lower()
        if any(c.isspace() for c in host):
            raise ValueError("Public origin contains whitespace.")
        hosts.add(host)
        origins.add(f"https://{host}")
    return hosts, origins
