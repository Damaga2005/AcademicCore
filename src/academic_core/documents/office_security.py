# SPDX-License-Identifier: MIT
"""Office/OOXML import boundaries (F3.1 §28/44): ZIP + XML hardening.

Domain sees only validation helpers + safe open. Never executes macros.
"""

from __future__ import annotations

import io
import zipfile

from academic_core.documents import limits as L
from academic_core.errors import AdapterError, ValidationError


def validate_office_bytes(data: bytes, *, kind: str = "office") -> None:
    if not data:
        raise ValidationError(f"EMPTY_{kind.upper()}: no bytes", code="AC-VAL-230")
    if len(data) > L.MAX_ZIP_MEMBER_BYTES * 4:
        raise AdapterError(f"TRACE_LIMIT: {kind} exceeds byte budget",
                           code="AC-ADP-230")
    if not data.startswith(b"PK"):
        raise ValidationError(f"MALFORMED_{kind.upper()}: missing ZIP magic",
                              code="AC-VAL-231")


def safe_open_zip(data: bytes, *, kind: str = "office") -> zipfile.ZipFile:
    """Open a ZIP archive with Slip/Bomb/symlink guards (caller must close)."""
    validate_office_bytes(data, kind=kind)
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise ValidationError(f"MALFORMED_{kind.upper()}: bad zip ({e})",
                              code="AC-VAL-232") from None
    infos = zf.infolist()
    if len(infos) > L.MAX_ZIP_FILES:
        zf.close()
        raise AdapterError(f"TRACE_LIMIT: {kind} has too many members",
                           code="AC-ADP-231")
    total = 0
    for info in infos:
        name = info.filename
        if name.startswith(("/", "\\")) or ".." in name.split("/"):
            zf.close()
            raise AdapterError(f"SECURITY: {kind} path traversal ({name[:60]})",
                               code="AC-ADP-232")
        if info.is_dir():
            continue
        if info.file_size > L.MAX_ZIP_MEMBER_BYTES:
            zf.close()
            raise AdapterError(f"TRACE_LIMIT: {kind} member too large",
                               code="AC-ADP-233")
        total += info.file_size
        if total > L.MAX_TOTAL_DECOMPRESSED_BYTES:
            zf.close()
            raise AdapterError(f"TRACE_LIMIT: {kind} decompressed budget exceeded",
                               code="AC-ADP-234")
        if info.external_attr >> 28 == 0xA:  # symlink bit
            zf.close()
            raise AdapterError(f"SECURITY: {kind} symlink rejected",
                               code="AC-ADP-235")
    return zf


def read_zip_member(zf: zipfile.ZipFile, name: str) -> bytes:
    try:
        with zf.open(name) as fh:
            return fh.read(L.MAX_ZIP_MEMBER_BYTES + 1)
    except KeyError as e:
        raise ValidationError(f"MALFORMED: missing {name} ({e})",
                              code="AC-VAL-233") from None
