"""A small forward proxy that pins browser requests to validated public IPs."""

from __future__ import annotations

import select
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from app.security.ssrf import SSRFError, ValidatedURL, validate_url_for_fetch


class SafeBrowserProxy(ThreadingHTTPServer):
    """Proxy browser traffic while validating and pinning every destination."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _ProxyHandler)
        self._validated: dict[tuple[str, str, int], ValidatedURL] = {}
        self._validated_lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> SafeBrowserProxy:
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.shutdown()
        self.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"

    def validate_destination(self, url: str) -> tuple[ValidatedURL, int]:
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise SSRFError("invalid_url", "Only http and https destinations are allowed")
        request_target = validate_url_for_fetch(url, resolve_dns=False)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        key = (parsed.scheme, request_target.hostname.lower().rstrip("."), port)
        with self._validated_lock:
            validated = self._validated.get(key)
            if validated is None:
                validated = validate_url_for_fetch(url)
                self._validated[key] = validated
        return validated, port

    def connect_destination(self, url: str) -> socket.socket:
        target, port = self.validate_destination(url)
        last_error: OSError | None = None
        for ip in target.resolved_ips:
            try:
                return socket.create_connection((ip, port), timeout=30)
            except OSError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise OSError("No validated address available")


class _ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: SafeBrowserProxy

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_CONNECT(self) -> None:
        try:
            parsed = urlsplit(f"//{self.path}")
            if not parsed.hostname:
                raise SSRFError("invalid_url", "Invalid CONNECT destination")
            upstream = self.server.connect_destination(f"https://{self.path}/")
        except (SSRFError, OSError, ValueError):
            self.send_error(502, "Destination blocked or unavailable")
            return

        try:
            self.wfile.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            self.wfile.flush()
            self._tunnel(upstream)
        finally:
            upstream.close()
            self.close_connection = True

    def do_GET(self) -> None:
        self._forward_http()

    def do_HEAD(self) -> None:
        self._forward_http()

    def do_POST(self) -> None:
        self._forward_http()

    def do_PUT(self) -> None:
        self._forward_http()

    def do_PATCH(self) -> None:
        self._forward_http()

    def do_DELETE(self) -> None:
        self._forward_http()

    def do_OPTIONS(self) -> None:
        self._forward_http()

    def _forward_http(self) -> None:
        try:
            parsed = urlsplit(self.path)
            if parsed.scheme != "http" or not parsed.hostname:
                raise SSRFError("invalid_url", "Expected an absolute HTTP URL")
            upstream = self.server.connect_destination(self.path)
        except (SSRFError, OSError, ValueError):
            self.send_error(502, "Destination blocked or unavailable")
            return

        request_target = parsed.path or "/"
        if parsed.query:
            request_target += f"?{parsed.query}"
        try:
            upstream.sendall(f"{self.command} {request_target} HTTP/1.1\r\n".encode("ascii"))
            has_host = False
            for name, value in self.headers.items():
                lowered = name.lower()
                if lowered in {"connection", "proxy-connection", "proxy-authorization"}:
                    continue
                has_host = has_host or lowered == "host"
                upstream.sendall(f"{name}: {value}\r\n".encode("latin-1"))
            if not has_host:
                upstream.sendall(f"Host: {parsed.netloc}\r\n".encode("latin-1"))
            upstream.sendall(b"Connection: close\r\n\r\n")

            transfer_encoding = self.headers.get("Transfer-Encoding", "").lower()
            if "chunked" in transfer_encoding:
                self._forward_chunked_body(upstream)
            else:
                remaining = int(self.headers.get("Content-Length", "0"))
                while remaining:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        break
                    upstream.sendall(chunk)
                    remaining -= len(chunk)

            while chunk := upstream.recv(65536):
                self.connection.sendall(chunk)
        except (OSError, ValueError):
            pass
        finally:
            upstream.close()
            self.close_connection = True

    def _forward_chunked_body(self, upstream: socket.socket) -> None:
        while True:
            line = self.rfile.readline()
            if not line:
                return
            upstream.sendall(line)
            try:
                size = int(line.split(b";", 1)[0].strip(), 16)
            except ValueError:
                return
            if size == 0:
                while trailer := self.rfile.readline():
                    upstream.sendall(trailer)
                    if trailer in (b"\r\n", b"\n"):
                        return
            body = self.rfile.read(size + 2)
            if not body:
                return
            upstream.sendall(body)

    def _tunnel(self, upstream: socket.socket) -> None:
        sockets = (self.connection, upstream)
        while True:
            readable, _, exceptional = select.select(sockets, (), sockets, 60)
            if exceptional or not readable:
                return
            for source in readable:
                data = source.recv(65536)
                if not data:
                    return
                destination = upstream if source is self.connection else self.connection
                destination.sendall(data)
