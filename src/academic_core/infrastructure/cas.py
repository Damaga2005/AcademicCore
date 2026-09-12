"""FileBlobStore: SHA-256 CAS, streaming, atomic, integrity-checked.

Layout: <root>/<hh>/<hh>/<hex> (same as Phase 0 convention, hardened).
- Writes stream in 1 MiB chunks to `<root>/tmp/<rand>` then atomic os.replace.
- Reads stream-hash the file and compare: corrupt blobs raise CorruptBlob,
  they are never silently returned.
- Paths derive ONLY from validated hex: no traversal possible by construction.
- Blobs are immutable: put is idempotent, overwrite cannot happen, delete is
  explicit and reports absence.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
from pathlib import Path

CHUNK = 1 << 20
_HEX = re.compile(r"^[0-9a-f]{64}$")


class CorruptBlob(ValueError):
    pass


class BlobNotFound(KeyError):
    pass


def _check_hash(content_hash: str) -> str:
    h = content_hash.lower()
    if not _HEX.match(h):
        raise ValueError(f"not a sha256 hex: {content_hash!r}")
    return h


class FileBlobStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        (self.root / "tmp").mkdir(parents=True, exist_ok=True)

    def _path(self, content_hash: str) -> Path:
        h = _check_hash(content_hash)
        return self.root / h[0:2] / h[2:4] / h

    def put_bytes(self, data: bytes) -> str:
        return self.put_stream([data])

    def put_stream(self, chunks) -> str:
        tmp = self.root / "tmp" / f"ink-{secrets.token_hex(8)}"
        digest = hashlib.sha256()
        size = 0
        with open(tmp, "wb") as f:
            for chunk in chunks:
                if not chunk:
                    continue
                digest.update(chunk)
                size += len(chunk)
                f.write(chunk)
        h = digest.digest().hex()
        final = self._path(h)
        final.parent.mkdir(parents=True, exist_ok=True)
        if final.exists():
            tmp.unlink(missing_ok=True)  # dedup: identical bytes, one blob
        else:
            os.replace(tmp, final)  # atomic publish
        return h

    def put_file(self, path: str | Path, max_bytes: int) -> tuple[str, int]:
        """Stream a filesystem file with an enforced cap (no 2x RAM copies)."""
        size = 0

        def gen():
            nonlocal size
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(CHUNK)
                    if not chunk:
                        return
                    size += len(chunk)
                    if size > max_bytes:
                        raise TooLarge(f"{path} exceeds {max_bytes} bytes")
                    yield chunk

        tmp = self.root / "tmp" / f"ink-{secrets.token_hex(8)}"
        digest = hashlib.sha256()
        try:
            with open(tmp, "wb") as f:
                for chunk in gen():
                    digest.update(chunk)
                    f.write(chunk)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        h = digest.digest().hex()
        final = self._path(h)
        final.parent.mkdir(parents=True, exist_ok=True)
        if final.exists():
            tmp.unlink(missing_ok=True)
        else:
            os.replace(tmp, final)
        return h, size

    def get_bytes(self, content_hash: str) -> bytes:
        p = self._path(content_hash)
        if not p.is_file():
            raise BlobNotFound(content_hash)
        digest = hashlib.sha256()
        parts: list[bytes] = []
        with open(p, "rb") as f:
            while True:
                chunk = f.read(CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
                parts.append(chunk)
        if digest.hexdigest() != _check_hash(content_hash):
            raise CorruptBlob(content_hash)
        return b"".join(parts)

    def exists(self, content_hash: str) -> bool:
        try:
            return self._path(content_hash).is_file()
        except ValueError:
            return False

    def delete(self, content_hash: str) -> bool:
        try:
            self._path(content_hash).unlink()
            return True
        except FileNotFoundError:
            return False


class TooLarge(ValueError):
    pass
