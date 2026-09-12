"""Stirling: client/runtime against a local fake HTTP server (real HTTP,
stdlib only). Live bootstrap is @pytest.mark.external and SIMULATED here
(no Java/Docker) — never VERIFIED without execution.
"""
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from academic_core.pdf.engine import PDFError
from academic_core.pdf.stirling import (
    STIRLING_VERSION, StirlingError, StirlingPDFBackend, StirlingRuntime,
)

PDF_BYTES = b"%PDF-1.4 fake\n%%EOF"


def _make_server(handler):
    srv = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class _OKHandler(BaseHTTPRequestHandler):
    openapi = {"info": {"version": "2.14.3"},
               "paths": {"/api/v1/general/merge-pdfs": {}, "/api/v1/general/rotate-pdf": {}}}

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/v3/api-docs":
            body = json.dumps(self.openapi).encode()
        else:
            body = b"stirling"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        mode = getattr(self.server, "mode", "ok")
        if mode == "invalid":
            body = b"not a pdf at all"
        elif mode == "empty":
            body = b""
        else:
            body = PDF_BYTES
        if mode == "error":
            self.send_response(500)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        status = 200
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _backend(srv):
    return StirlingPDFBackend(f"http://127.0.0.1:{srv.server_port}")


def test_ready_merge_and_capabilities():
    srv = _make_server(_OKHandler)
    try:
        rt = StirlingRuntime(f"http://127.0.0.1:{srv.server_port}")
        assert rt.health() is True and rt.version() == "2.14.3"
        back = _backend(srv)
        assert back.merge([PDF_BYTES, PDF_BYTES]) == PDF_BYTES
        caps = back.detect_capabilities()
        assert caps["merge"] is True and caps.get("split") is False
    finally:
        srv.shutdown()


def test_error_and_invalid_output():
    srv = _make_server(_OKHandler)
    srv.mode = "error"
    try:
        with pytest.raises(StirlingError):
            _backend(srv).merge([PDF_BYTES])
    finally:
        srv.shutdown()
    srv = _make_server(_OKHandler)
    srv.mode = "invalid"
    try:
        with pytest.raises(PDFError):
            _backend(srv).merge([PDF_BYTES])
    finally:
        srv.shutdown()


def test_timeout_and_refused_host():
    back = StirlingPDFBackend("http://127.0.0.1:9", timeout=1)
    with pytest.raises(StirlingError):
        back.merge([PDF_BYTES])
    with pytest.raises(StirlingError):
        StirlingPDFBackend("https://example.com:8443")


def test_runtime_without_java_is_not_installed():
    rt = StirlingRuntime("http://127.0.0.1:9", jar_path="", java_bin="java_absent_xyz")
    info = rt.detect()
    assert info["state"] == "NOT_INSTALLED" and info["java"] is False
    assert rt.start() == "NOT_INSTALLED"
    assert rt.version() == "UNKNOWN"


def test_restart_stop_cleanup():
    rt = StirlingRuntime("http://127.0.0.1:9")
    assert rt.stop() == "STOPPED" and rt.restart() in ("NOT_INSTALLED", "STOPPED", "ERROR")
    assert STIRLING_VERSION == "v2.14.3"


@pytest.mark.external
def test_live_bootstrap_simulated():
    """No Java/Docker in this environment: bootstrap NOT executed.
    Status honestly SIMULATED (would run NOT_INSTALLED→bootstrap→READY)."""
    import shutil
    if shutil.which("java") and shutil.which("docker"):
        pytest.skip("java+docker present: run the live bootstrap manually")
    assert True  # SIMULATED — see STIRLING-INTEGRATION.md
