"""The real HTTP client behind `ciao-sun fetch`, against a server on localhost."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from ciao_sun.fetch import TransportError, UrllibClient


class _Handler(BaseHTTPRequestHandler):
    body = b"0123456789" * 30

    def do_GET(self) -> None:
        if self.path == "/moved":
            self.send_response(302)
            self.send_header("Location", "/file")
            self.end_headers()
        elif self.path == "/file":
            start = int((self.headers.get("Range") or "bytes=0-")[6:-1])
            self.send_response(206 if start else 200)
            self.send_header("Content-Length", str(len(self.body) - start))
            self.end_headers()
            self.wfile.write(self.body[start:])
        elif self.path == "/cut-short":
            self.send_response(200)
            self.send_header("Content-Length", str(len(self.body)))
            self.end_headers()
            self.wfile.write(self.body[:50])
        else:
            self.send_response(int(self.path.strip("/")))
            self.send_header("Content-Length", "0")
            self.end_headers()

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def local_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def test_statuses_are_reported_not_raised(local_server):
    client = UrllibClient(timeout_s=5)
    assert client.get(f"{local_server}/403", {}).status == 403
    assert client.get(f"{local_server}/404", {}).status == 404


def test_redirects_are_followed_and_range_is_passed_through(local_server):
    client = UrllibClient(timeout_s=5)
    whole = client.get(f"{local_server}/moved", {})
    assert (whole.status, b"".join(whole.chunks)) == (200, _Handler.body)
    rest = client.get(f"{local_server}/moved", {"Range": "bytes=290-"})
    assert (rest.status, b"".join(rest.chunks)) == (206, b"0123456789")


def test_a_body_cut_short_is_a_transport_error(local_server):
    response = UrllibClient(timeout_s=5).get(f"{local_server}/cut-short", {})
    with pytest.raises(TransportError):
        b"".join(response.chunks)


def test_a_refused_connection_is_a_transport_error():
    with pytest.raises(TransportError):
        UrllibClient(timeout_s=5).get("http://127.0.0.1:1/nothing-listens-here", {})
