from academic_core.resources.adapters import (
    HtmlAdapter, LocalFileAdapter, MarkdownAdapter, PdfAdapter, REGISTRY,
    UnsupportedType, adapter_for, detect_kind,
)

__all__ = ["HtmlAdapter", "LocalFileAdapter", "MarkdownAdapter", "PdfAdapter",
           "REGISTRY", "UnsupportedType", "adapter_for", "detect_kind"]
