"""PDF Engine (Phase 3): interface + native backend + Stirling backend.

Domain sees only `PDFEngine` over a `PDFBackend`. Native backend uses pypdf
(BSD-3, audited: maintained, Windows-safe, pure Python). `render_page` is
honestly unsupported natively (pypdf cannot rasterize) — Stirling or a later
phase covers it. PyMuPDF deliberately NOT added (AGPL; see ADR-0015).
"""

from __future__ import annotations

import io
from abc import ABC, abstractmethod

from academic_core.documents import ast as A


class PDFError(ValueError):
    pass


class UnsupportedOperation(NotImplementedError):
    pass


def validate_pdf_bytes(data: bytes, max_bytes: int = 100 * 1024 * 1024) -> None:
    if not data:
        raise PDFError("empty pdf")
    if len(data) > max_bytes:
        raise PDFError(f"pdf exceeds {max_bytes} bytes")
    if not data.startswith(b"%PDF"):
        raise PDFError("not a pdf (missing %PDF magic)")


class PDFBackend(ABC):
    name: str = ""
    version: str = ""

    @abstractmethod
    def inspect(self, data: bytes) -> dict: ...
    @abstractmethod
    def extract_text(self, data: bytes, pages: list[int] | None = None) -> str: ...
    @abstractmethod
    def extract_pages(self, data: bytes) -> list[str]: ...
    @abstractmethod
    def merge(self, pdfs: list[bytes]) -> bytes: ...
    @abstractmethod
    def split(self, data: bytes, ranges: list[tuple[int, int]]) -> list[bytes]: ...
    @abstractmethod
    def rotate(self, data: bytes, angle: int, pages: list[int] | None = None) -> bytes: ...
    def render_page(self, data: bytes, page: int, dpi: int = 150) -> bytes:
        raise UnsupportedOperation(f"{self.name} cannot rasterize pages")


class NativePDFBackend(PDFBackend):
    name = "native"
    version = "pypdf"

    def _reader(self, data: bytes):
        from pypdf import PdfReader
        validate_pdf_bytes(data)
        try:
            return PdfReader(io.BytesIO(data))
        except Exception as e:
            raise PDFError(f"unreadable pdf: {e}")

    def inspect(self, data: bytes) -> dict:
        r = self._reader(data)
        info = dict(r.metadata or {})
        return {"backend": self.name, "pages": len(r.pages),
                "encrypted": r.is_encrypted,
                "metadata": {str(k).lstrip("/"): str(v) for k, v in info.items()},
                "size": len(data)}

    def extract_text(self, data: bytes, pages: list[int] | None = None) -> str:
        r = self._reader(data)
        idx = range(len(r.pages)) if pages is None else pages
        return "\n".join((r.pages[p].extract_text() or "") for p in idx
                         if 0 <= p < len(r.pages))

    def extract_pages(self, data: bytes) -> list[str]:
        r = self._reader(data)
        return [(r.pages[p].extract_text() or "") for p in range(len(r.pages))]

    def merge(self, pdfs: list[bytes]) -> bytes:
        from pypdf import PdfWriter
        if not pdfs:
            raise PDFError("nothing to merge")
        w = PdfWriter()
        for data in pdfs:
            r = self._reader(data)
            for page in r.pages:
                w.add_page(page)
        buf = io.BytesIO()
        w.write(buf)
        return buf.getvalue()

    def split(self, data: bytes, ranges: list[tuple[int, int]]) -> list[bytes]:
        from pypdf import PdfWriter
        r = self._reader(data)
        out = []
        for start, end in ranges:
            if not (0 <= start <= end < len(r.pages)):
                raise PDFError(f"range out of bounds: {(start, end)}")
            w = PdfWriter()
            for p in range(start, end + 1):
                w.add_page(r.pages[p])
            buf = io.BytesIO()
            w.write(buf)
            out.append(buf.getvalue())
        return out

    def rotate(self, data: bytes, angle: int, pages: list[int] | None = None) -> bytes:
        from pypdf import PdfReader, PdfWriter
        if angle % 90 != 0:
            raise PDFError("angle must be a multiple of 90")
        r = self._reader(data)
        w = PdfWriter()
        idx = set(range(len(r.pages)) if pages is None else pages)
        for p, page in enumerate(r.pages):
            if p in idx:
                w.add_page(page)
                w.pages[-1].rotate(angle)
            else:
                w.add_page(page)
        _ = PdfReader  # keep import explicit for linters
        buf = io.BytesIO()
        w.write(buf)
        return buf.getvalue()


class PDFEngine:
    """Backend-agnostic operations + PDF→Document derivation."""

    def __init__(self, backend: PDFBackend):
        self.backend = backend

    def inspect(self, data: bytes) -> dict:
        return self.backend.inspect(data)

    def merge(self, pdfs: list[bytes]) -> bytes:
        out = self.backend.merge(pdfs)
        validate_pdf_bytes(out)
        return out

    def to_document(self, data: bytes, resource_id: str = "",
                    resource_version: int = 0) -> A.Document:
        """One section per page; text-only (scanned pages yield warnings)."""
        info = self.backend.inspect(data)
        pages = self.backend.extract_pages(data)
        blocks: list = []
        empty = 0
        for i, text in enumerate(pages):
            kids = [A.text(text.strip())] if text.strip() else []
            if not kids:
                empty += 1
                continue
            blocks.append(A.section(f"Page {i + 1}", (A.paragraph(kids),)))
        history = [{"parser": f"pdf-{self.backend.name}", "version": self.backend.version,
                    "source": resource_id, "source_version": resource_version,
                    "pages": info.get("pages", 0),
                    "warnings": ["some pages without extractable text (scanned?)"]
                    if empty else []}]
        title = (info.get("metadata", {}) or {}).get("Title", "")
        return A.Document(A.Metadata(title=title, origin="pdf"), tuple(history), tuple(blocks))
