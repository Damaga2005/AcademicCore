"""Image extraction ADAPTED from Conversor-HTML-A-MD (CONVERSOR-REUSE-MAP.md).

Provenance: `conversor_html_notebooklm.py` L359–371 + L640–662, MIT © 2026
Damaga2005, adapted 2026-09-12: destination is the CAS (injected
put-callable) instead of `assets/`; returns records instead of a count.
"""

from __future__ import annotations

import base64
import re


def _ext_for(raw_ext: str) -> str:
    raw = raw_ext.lower().replace("svg+xml", "svg").replace("jpeg", "jpg")
    if "png" in raw:
        return "png"
    if "jpg" in raw:
        return "jpg"
    if "svg" in raw:
        return "svg"
    if "gif" in raw:
        return "gif"
    if "webp" in raw:
        return "webp"
    return "png"


def harvest_figs_from_scripts(soup) -> dict[str, str]:
    """FIGS/data-URI dicts embedded in page JS (regex over text — never executed)."""
    figs: dict[str, str] = {}
    for script in soup.find_all("script"):
        st = script.get_text()
        if "data:image/" in st:
            for m in re.finditer(
                    r'["\']([a-zA-Z0-9_\.-]+)["\']\s*:\s*["\'](data:image/[^"\']+)["\']', st):
                figs[m.group(1)] = m.group(2)
    if figs:
        for img in soup.find_all("img"):
            key = img.get("data-fig") or img.get("id")
            if key and key in figs and (not img.get("src") or img.get("src").startswith("#")):
                img["src"] = figs[key]
    return figs


def extract_images(soup, put) -> list[dict]:
    """Route every <img> to CAS. Returns [{src_after, content_hash|None, ext,
    alt, note}]. data-URIs are decoded; remote URLs are recorded, never fetched."""
    out = []
    for i, img in enumerate(soup.find_all("img")):
        src = (img.get("src", "") or "").strip()
        alt = img.get("alt", "")
        if src.startswith("data:image/"):
            m = re.match(r"data:image/([a-zA-Z0-9+_-]+);base64,(.+)", src, flags=re.DOTALL)
            if not m:
                out.append({"src_after": "", "content_hash": None, "note": "unparsable-data-uri"})
                img.decompose()
                continue
            try:
                data = base64.b64decode(re.sub(r"\s+", "", m.group(2)))
            except Exception:
                out.append({"src_after": "", "content_hash": None, "note": "bad-base64"})
                img.decompose()
                continue
            ext = _ext_for(m.group(1))
            h = put(data)
            ref = f"cas:{h}"
            img["src"] = ref
            out.append({"src_after": ref, "content_hash": h, "ext": ext,
                        "alt": alt, "note": "cas"})
        elif re.match(r"https?://", src):
            out.append({"src_after": src, "content_hash": None, "alt": alt, "note": "remote-not-fetched"})
        elif src:
            out.append({"src_after": src, "content_hash": None, "alt": alt, "note": "relative-kept"})
        else:
            out.append({"src_after": "", "content_hash": None, "alt": alt, "note": "empty-src"})
            img.decompose()
    return out
