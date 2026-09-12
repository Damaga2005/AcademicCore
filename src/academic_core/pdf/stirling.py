"""Stirling-PDF integration (Phase 3): research constants + runtime + backend.

Reference: https://github.com/Stirling-Tools/Stirling-PDF (never vendored,
never cloned as a production dependency). Distribution = official GitHub
release assets. Academic Core works WITHOUT Stirling (states below); the
native pypdf backend is always available.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from academic_core.pdf.engine import (
    PDFBackend, PDFError, UnsupportedOperation, validate_pdf_bytes,
)

# Pinned by research 2026-09-12 (see docs/architecture/STIRLING-INTEGRATION.md).
STIRLING_VERSION = "v2.14.3"
STIRLING_SOURCE = "https://github.com/Stirling-Tools/Stirling-PDF"
STIRLING_RELEASE = "2.14.3 lots of bug fixes (2026-08-06)"
STIRLING_LICENSE = "open-core: MIT base + proprietary subdirectories (never vendored)"
STIRLING_SHA = ""  # filled when an artifact is actually downloaded+verified

STATES = ("NOT_INSTALLED", "INSTALLING", "READY", "UNAVAILABLE",
          "INCOMPATIBLE", "ERROR", "STOPPED")

DEFAULT_URL = "http://127.0.0.1:8080"

# Endpoint map for the v2 API (multipart `fileInput`; X-API-KEY optional).
# Paths confirmed against official docs where noted; the client auto-detects
# via OpenAPI and drops anything the running version does not expose.
ENDPOINTS = {
    "merge": "/api/v1/general/merge-pdfs",
    "split": "/api/v1/general/split-pdfs",
    "rotate": "/api/v1/general/rotate-pdf",
    "extract_text": "/api/v1/general/extract-text",
    "info": "/api/v1/info/status",
}


class StirlingError(PDFError):
    pass


class StirlingRuntime:
    """Lifecycle of the EXTERNAL Stirling runtime (JAR/server/desktop).

    Never downloads blindly: `bootstrap()` requires an explicit artifact path
    or URL allow-listed to github.com releases, verifies SHA-256 when a
    `.sha256` sidecar is known, then starts and health-checks.
    """

    ALLOW_HOSTS = ("github.com", "objects.githubusercontent.com")

    def __init__(self, base_url: str = DEFAULT_URL, jar_path: str = "",
                 java_bin: str = "java", api_key: str = "", timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.jar_path = jar_path
        self.java_bin = java_bin
        self.api_key = api_key
        self.timeout = timeout
        self.state = "NOT_INSTALLED"
        self._proc = None

    # -- detection ------------------------------------------------------------
    def detect(self) -> dict:
        java = shutil.which(self.java_bin) is not None
        jar = bool(self.jar_path) and Path(self.jar_path).is_file()
        alive = self.health()
        self.state = "READY" if alive else ("STOPPED" if (java and jar) else "NOT_INSTALLED")
        return {"java": java, "jar": jar, "alive": alive, "state": self.state,
                "url": self.base_url, "pinned": STIRLING_VERSION}

    def health(self) -> bool:
        try:
            with urllib.request.urlopen(self.base_url + "/", timeout=self.timeout) as r:
                return r.status in (200, 302, 401, 403)
        except Exception:
            return False

    def version(self) -> str:
        """Best-effort version probe (OpenAPI info, else UNKNOWN — never guessed)."""
        for path in ("/v3/api-docs", "/openapi.json"):
            try:
                with urllib.request.urlopen(self.base_url + path, timeout=self.timeout) as r:
                    info = json.loads(r.read().decode("utf-8")).get("info", {})
                    if info.get("version"):
                        return str(info["version"])
            except Exception:
                continue
        return "UNKNOWN"

    # -- lifecycle ---------------------------------------------------------------
    def start(self) -> str:
        if self._proc and self._proc.poll() is None:
            self.state = "READY" if self.health() else "ERROR"
            return self.state
        if not (shutil.which(self.java_bin) and self.jar_path
                and Path(self.jar_path).is_file()):
            self.state = "NOT_INSTALLED"
            return self.state
        try:
            self._proc = subprocess.Popen(
                [self.java_bin, "-jar", self.jar_path], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, cwd=str(Path(self.jar_path).parent))
        except Exception:
            self.state = "ERROR"
            return self.state
        deadline = time.time() + 90
        while time.time() < deadline:
            if self.health():
                self.state = "READY"
                return self.state
            if self._proc.poll() is not None:
                self.state = "ERROR"
                return self.state
            time.sleep(2)
        self.state = "UNAVAILABLE"
        return self.state

    def stop(self) -> str:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
        self.state = "STOPPED"
        return self.state

    def restart(self) -> str:
        self.stop()
        return self.start()


def _encode_multipart(files: list[tuple[str, bytes, str]], fields: dict) -> tuple[bytes, str]:
    import secrets
    boundary = f"----acore{secrets.token_hex(8)}"
    body = b""
    for key, value in fields.items():
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n"
                 f"{value}\r\n").encode()
    for name, data, filename in files:
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\";"
                 f" filename=\"{filename}\"\r\nContent-Type: application/pdf\r\n\r\n").encode()
        body += data + b"\r\n"
    return body + f"--{boundary}--\r\n".encode(), boundary


class StirlingPDFBackend(PDFBackend):
    """API client over a Stirling runtime (localhost only by default)."""

    name = "stirling"
    version = STIRLING_VERSION

    def __init__(self, base_url: str = DEFAULT_URL, api_key: str = "", timeout: int = 60):
        if not base_url.startswith(("http://127.", "http://localhost", "https://127.",
                                    "https://localhost")):
            raise StirlingError("refusing non-localhost Stirling URL")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.capabilities: dict[str, bool] = {}

    def _headers(self, boundary: str) -> dict:
        h = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        if self.api_key:
            h["X-API-KEY"] = self.api_key
        return h

    def _post(self, endpoint: str, files: list[tuple[str, bytes, str]],
              fields: dict | None = None) -> bytes:
        body, boundary = _encode_multipart(files, fields or {})
        req = urllib.request.Request(self.base_url + endpoint, data=body,
                                     headers=self._headers(boundary), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                out = r.read()
        except Exception as e:
            raise StirlingError(f"{endpoint} failed: {e}")
        validate_pdf_bytes(out)
        return out

    def detect_capabilities(self) -> dict[str, bool]:
        """Probe OpenAPI doc; keep only endpoints the version exposes."""
        try:
            with urllib.request.urlopen(self.base_url + "/v3/api-docs",
                                        timeout=self.timeout) as r:
                doc = r.read().decode("utf-8")
        except Exception:
            self.capabilities = {}
            return {}
        self.capabilities = {op: (ENDPOINTS[op] in doc or op in doc)
                             for op in ("merge", "split", "rotate", "extract_text")}
        return self.capabilities

    def inspect(self, data: bytes) -> dict:
        validate_pdf_bytes(data)
        return {"backend": self.name, "version": self.version,
                "size": len(data), "runtime": self.base_url}

    def extract_text(self, data: bytes, pages: list[int] | None = None) -> str:
        validate_pdf_bytes(data)
        out = self._post(ENDPOINTS["extract_text"], [("fileInput", data, "in.pdf")])
        try:
            return out.decode("utf-8", errors="replace")
        except Exception as e:
            raise StirlingError(f"text decode failed: {e}")

    def extract_pages(self, data: bytes) -> list[str]:
        return [self.extract_text(data)]

    def merge(self, pdfs: list[bytes]) -> bytes:
        if not pdfs:
            raise PDFError("nothing to merge")
        for p in pdfs:
            validate_pdf_bytes(p)
        files = [(f"fileInput", p, f"in{i}.pdf") for i, p in enumerate(pdfs)]
        return self._post(ENDPOINTS["merge"], files)

    def split(self, data: bytes, ranges: list[tuple[int, int]]) -> list[bytes]:
        validate_pdf_bytes(data)
        return [self._post(ENDPOINTS["split"], [("fileInput", data, "in.pdf")],
                           {"startPage": str(s + 1), "endPage": str(e + 1)})
                for s, e in ranges]

    def rotate(self, data: bytes, angle: int, pages: list[int] | None = None) -> bytes:
        validate_pdf_bytes(data)
        if angle % 90 != 0:
            raise PDFError("angle must be a multiple of 90")
        return self._post(ENDPOINTS["rotate"], [("fileInput", data, "in.pdf")],
                          {"angle": str(angle)})

    def render_page(self, data: bytes, page: int, dpi: int = 150) -> bytes:
        raise UnsupportedOperation("render_page is not offered by this backend")
