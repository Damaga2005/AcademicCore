"""Resource adapters (Phase 2): stdlib-only, no JS, no network, no Stirling.

Each adapter declares support and extracts indexable text WITHOUT mutating
the canonical blob. PDF text is best-effort with graceful degradation
(status deferred/failed, never a silent empty index presented as complete).
ZIP and other containers are explicitly UNSUPPORTED in F2 (boundary pending,
see docs + test) — never partially extracted.
"""

from __future__ import annotations

from html.parser import HTMLParser

from academic_core.domain.ports import ExtractedContent, ResourceExtractor

MAX_INDEX_CHARS = 200_000

TEXT_EXTENSIONS = {".txt": "text", ".md": "markdown", ".markdown": "markdown"}
HTML_EXTENSIONS = {".html", ".htm"}
PDF_EXTENSIONS = {".pdf"}
# Explicitly refused in F2 (Zip Slip surface, deferred to a later phase).
REFUSED_EXTENSIONS = {".zip", ".7z", ".rar", ".exe", ".msi", ".bat", ".ps1", ".js"}


class UnsupportedType(ValueError):
    pass


def detect_kind(filename: str, head: bytes) -> str:
    """Extension-first, magic-second. Raises UnsupportedType for refused kinds."""
    lower = filename.lower()
    for ext in REFUSED_EXTENSIONS:
        if lower.endswith(ext):
            raise UnsupportedType(f"F2 does not ingest {ext} (deferred boundary)")
    for ext, kind in TEXT_EXTENSIONS.items():
        if lower.endswith(ext):
            return kind
    if any(lower.endswith(e) for e in HTML_EXTENSIONS):
        return "html"
    if any(lower.endswith(e) for e in PDF_EXTENSIONS) or head.startswith(b"%PDF"):
        return "pdf"
    return "file"


class LocalFileAdapter(ResourceExtractor):
    kind = "file"
    name = "local-file"
    version = "1"

    def supports(self, kind: str, filename: str) -> bool:
        return kind == "file"

    def extract(self, data: bytes, filename: str) -> ExtractedContent:
        if b"\x00" in data[:8192]:
            return ExtractedContent(is_binary=True, metadata={"size": len(data)},
                                    warnings=("binary content: not indexed",))
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return ExtractedContent(is_binary=True, metadata={"size": len(data)},
                                    warnings=("non-utf8 bytes: not indexed",))
        if len(text) > MAX_INDEX_CHARS:
            return ExtractedContent(text[:MAX_INDEX_CHARS], truncated=True,
                                    metadata={"size": len(data)},
                                    warnings=("truncated to 200k chars",))
        return ExtractedContent(text=text, metadata={"size": len(data)})


class MarkdownAdapter(ResourceExtractor):
    kind = "markdown"
    name = "markdown"
    version = "1"

    def supports(self, kind: str, filename: str) -> bool:
        return kind in ("markdown", "text")

    def extract(self, data: bytes, filename: str) -> ExtractedContent:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return ExtractedContent(status="failed", metadata={"size": len(data)},
                                    warnings=("markdown must be utf-8",))
        title = ""
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("#"):
                title = s.lstrip("#").strip()
                break
        body = text if len(text) <= MAX_INDEX_CHARS else text[:MAX_INDEX_CHARS]
        return ExtractedContent(text=body, truncated=len(text) > MAX_INDEX_CHARS,
                                metadata={"size": len(data), "title": title})


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self._in_title = False
        self._skip = 0  # script/style depth (collected never, executed never)

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title_parts.append(data)
        else:
            self.parts.append(data)


class HtmlAdapter(ResourceExtractor):
    kind = "html"
    name = "html"
    version = "1"

    def supports(self, kind: str, filename: str) -> bool:
        return kind == "html"

    def extract(self, data: bytes, filename: str) -> ExtractedContent:
        try:
            html = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            html = data.decode("utf-8", errors="replace")
        parser = _TextParser()
        try:
            # No JS execution, no remote fetch: pure stdlib tokenizing.
            parser.feed(html[:1_000_000])
        except Exception as e:  # malformed markup degrades, never crashes ingest
            return ExtractedContent(status="failed", metadata={"size": len(data)},
                                    warnings=(f"html parse failed: {e}",))
        text = " ".join(" ".join(parser.parts).split())
        title = " ".join(" ".join(parser.title_parts).split())
        if len(text) > MAX_INDEX_CHARS:
            text, trunc = text[:MAX_INDEX_CHARS], True
        else:
            trunc = False
        return ExtractedContent(text=text, truncated=trunc,
                                metadata={"size": len(data), "title": title})


class PdfAdapter(ResourceExtractor):
    kind = "pdf"
    name = "pdf"
    version = "1"

    def supports(self, kind: str, filename: str) -> bool:
        return kind == "pdf"

    def extract(self, data: bytes, filename: str) -> ExtractedContent:
        try:
            from pypdf import PdfReader  # lazy: pypdf is optional in F2
        except ImportError:
            return ExtractedContent(status="deferred", metadata={"size": len(data)},
                                    warnings=("pypdf not installed: text deferred",))
        import io
        try:
            reader = PdfReader(io.BytesIO(data))
            pages = len(reader.pages)
            out: list[str] = []
            for page in reader.pages:
                out.append(page.extract_text() or "")
                if sum(map(len, out)) >= MAX_INDEX_CHARS:
                    break
            text = "\n".join(out)
            trunc = len(text) >= MAX_INDEX_CHARS
            return ExtractedContent(
                text=text[:MAX_INDEX_CHARS], truncated=trunc,
                metadata={"size": len(data), "pages": pages},
                warnings=() if text.strip() else ("no extractable text (scanned?)",))
        except Exception as e:
            return ExtractedContent(status="failed", metadata={"size": len(data)},
                                    warnings=(f"pdf parse failed: {e}",))


REGISTRY: tuple[ResourceExtractor, ...] = (
    MarkdownAdapter(), HtmlAdapter(), PdfAdapter(), LocalFileAdapter(),
)


def adapter_for(kind: str, filename: str) -> ResourceExtractor:
    for adapter in REGISTRY:
        if adapter.supports(kind, filename):
            return adapter
    raise UnsupportedType(f"no F2 adapter for kind={kind}")
