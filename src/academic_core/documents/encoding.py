"""Encoding detection REUSED DIRECTLY from Conversor-HTML-A-MD.

Provenance: `read_html_file_safely` L1691–1718, MIT © 2026 Damaga2005,
reused verbatim in behavior (BOM → meta charset → utf-8 → cp1252 → replace).
"""

from __future__ import annotations

import re


def read_html_bytes(raw: bytes) -> tuple[str, str]:
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig"), "utf-8-sig"
    head = raw[:2048].decode("ascii", errors="ignore")
    m = re.search(r'<meta[^>]+charset=["\']?([a-zA-Z0-9_-]+)', head, re.I)
    if not m:
        m = re.search(r'content=["\'][^"\']*charset=([a-zA-Z0-9_-]+)', head, re.I)
    if m:
        encoding = m.group(1).lower()
        if encoding in ("utf8", "utf-8"):
            encoding = "utf-8"
        try:
            return raw.decode(encoding), encoding
        except Exception:
            pass
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("cp1252"), "cp1252 (Windows-1252)"
    except Exception:
        return raw.decode("utf-8", errors="replace"), "utf-8 (fallback)"
