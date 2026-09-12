"""Canonical Document AST — the single internal document model.

External formats convert TO/FROM this model. Markdown is NOT the internal model.
External: HTML/PDF/DOCX/LaTeX/Markdown -> Document -> Markdown/HTML/LaTeX/PDF.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DocMetadata:
    title: str = ""
    source_path: str = ""
    source_hash: str = ""
    stable_id: str = ""


@dataclass
class Block:
    kind: str  # paragraph|equation|figure|table|code|link|reference|section
    content: dict = field(default_factory=dict)


@dataclass
class Document:
    meta: DocMetadata = field(default_factory=DocMetadata)
    blocks: list[Block] = field(default_factory=list)

    def add(self, kind: str, **content) -> Block:
        b = Block(kind=kind, content=content)
        self.blocks.append(b)
        return b
