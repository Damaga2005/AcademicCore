"""Canonical Document AST (Phase 3): the single internal document model.

Markdown is NOT canonical; HTML/PDF/Markdown convert TO this model and
renderers convert FROM it. Nodes are frozen dataclasses: typed, deterministic,
JSON-serializable (no pickle), versioned (SCHEMA_VERSION), validated
(`validate()` / `from_dict()` reject unknown kinds and bad shapes loudly).

No PySide6/Qt, SQLite, FTS5, CAS, Stirling, Markdown, HTML, UI here — stdlib.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SCHEMA_VERSION = 1

_VALID_KINDS = {
    "document", "section", "heading", "paragraph", "text", "emphasis",
    "strong", "link", "list", "list_item", "quote", "code_block",
    "inline_code", "table", "table_row", "table_cell", "image",
    "equation", "thematic_break",
}


class AstError(ValueError):
    pass


@dataclass(frozen=True)
class Metadata:
    title: str = ""
    author: str = ""
    language: str = ""
    created_at: str = ""
    modified_at: str = ""
    source_resource_id: str = ""
    source_version: int = 0
    origin: str = ""
    encoding: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"title": self.title, "author": self.author, "language": self.language,
                "created_at": self.created_at, "modified_at": self.modified_at,
                "source_resource_id": self.source_resource_id,
                "source_version": self.source_version, "origin": self.origin,
                "encoding": self.encoding, "extra": dict(self.extra)}

    @classmethod
    def from_dict(cls, d: dict) -> "Metadata":
        if not isinstance(d, dict):
            raise AstError("metadata must be an object")
        known = ("title", "author", "language", "created_at", "modified_at",
                 "source_resource_id", "source_version", "origin", "encoding", "extra")
        for k in d:
            if k not in known:
                raise AstError(f"unknown metadata field: {k}")
        extra = d.get("extra", {})
        if not isinstance(extra, dict):
            raise AstError("metadata.extra must be an object")
        return cls(**{k: d.get(k, "" if k != "extra" else {}) if k != "source_version"
                       else d.get(k, 0) for k in known})


@dataclass(frozen=True)
class Node:
    kind: str
    attrs: dict = field(default_factory=dict)
    children: tuple = field(default_factory=tuple)

    def __post_init__(self):
        if self.kind not in _VALID_KINDS:
            raise AstError(f"invalid node kind: {self.kind}")
        object.__setattr__(self, "attrs", dict(self.attrs))
        object.__setattr__(self, "children", tuple(self.children))

    def to_dict(self) -> dict:
        return {"kind": self.kind, "attrs": dict(self.attrs),
                "children": [c.to_dict() if isinstance(c, Node) else c
                             for c in self.children]}

    @classmethod
    def from_dict(cls, d: dict) -> "Node":
        if not isinstance(d, dict) or d.get("kind") not in _VALID_KINDS:
            raise AstError(f"invalid node: {d!r}"[:120])
        if not isinstance(d.get("attrs", {}), dict) or not isinstance(d.get("children", []), list):
            raise AstError("node attrs must be object, children must be array")
        kids = tuple(cls.from_dict(c) if isinstance(c, dict) else c for c in d["children"])
        for c in kids:
            if not isinstance(c, Node):
                raise AstError("children must be nodes")
        return cls(d["kind"], d["attrs"], kids)


def _n(kind: str, children=(), **attrs) -> Node:
    return Node(kind, dict(attrs), tuple(children))


# -- constructors --------------------------------------------------------------
def document(children=(), **meta) -> Node:
    return _n("document", children, **meta)


def section(title: str, children=()) -> Node:
    return _n("section", children, title=title)


def heading(level: int, children=()) -> Node:
    if level not in (1, 2, 3, 4, 5, 6):
        raise AstError("heading level 1..6")
    return _n("heading", children, level=level)


def paragraph(children=()) -> Node:
    return _n("paragraph", children)


def text(s: str) -> Node:
    return _n("text", (), value=s)


def emphasis(children=()) -> Node:
    return _n("emphasis", children)


def strong(children=()) -> Node:
    return _n("strong", children)


def link(target: str, children=(), title: str = "") -> Node:
    return _n("link", children, target=target, title=title)


def bullet_list(items=(), ordered: bool = False) -> Node:
    return _n("list", items, ordered=ordered)


def list_item(children=()) -> Node:
    return _n("list_item", children)


def quote(children=()) -> Node:
    return _n("quote", children)


def code_block(code: str, language: str = "") -> Node:
    return _n("code_block", (), code=code, language=language)


def inline_code(code: str) -> Node:
    return _n("inline_code", (), code=code)


def table(header=None, rows=(), caption: str = "") -> Node:
    kids = ((header,) if header is not None else ()) + tuple(rows)
    return _n("table", kids, caption=caption)


def table_row(cells=()) -> Node:
    return _n("table_row", cells)


def table_cell(children=(), header: bool = False, colspan: int = 1,
               rowspan: int = 1, align: str = "") -> Node:
    if colspan < 1 or rowspan < 1:
        raise AstError("spans must be >= 1")
    if align not in ("", "left", "center", "right"):
        raise AstError("bad align")
    return _n("table_cell", children, header=header, colspan=colspan,
              rowspan=rowspan, align=align)


def image(blob_ref: str, alt: str = "", width: int = 0, height: int = 0,
          title: str = "") -> Node:
    return _n("image", (), blob_ref=blob_ref, alt=alt, width=width,
              height=height, title=title)


def equation(source: str, format: str = "latex", display: bool = False) -> Node:
    if format not in ("latex", "mathml"):
        raise AstError("equation format latex|mathml")
    return _n("equation", (), source=source, format=format, display=display)


def thematic_break() -> Node:
    return _n("thematic_break")


# -- document envelope ------------------------------------------------------------
@dataclass(frozen=True)
class Document:
    """Root: metadata + transformation history + block children."""
    meta: Metadata = field(default_factory=Metadata)
    history: tuple = field(default_factory=tuple)  # provenance chain entries
    children: tuple = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {"schema_version": SCHEMA_VERSION, "metadata": self.meta.to_dict(),
                "history": list(self.history),
                "children": [c.to_dict() for c in self.children]}

    @classmethod
    def from_dict(cls, d: dict) -> "Document":
        if not isinstance(d, dict):
            raise AstError("document must be an object")
        if d.get("schema_version") != SCHEMA_VERSION:
            raise AstError(f"unsupported schema_version: {d.get('schema_version')!r}")
        if not isinstance(d.get("children", []), list) or not isinstance(
                d.get("history", []), list):
            raise AstError("children/history must be arrays")
        for h in d["history"]:
            if not isinstance(h, dict) or "parser" not in h:
                raise AstError("history entries must carry a parser")
        kids = tuple(Node.from_dict(c) for c in d["children"])
        return cls(Metadata.from_dict(d.get("metadata", {})), tuple(d["history"]), kids)


def validate(doc: Document) -> None:
    """Structural validation: inline nodes never carry block children, and
    block kinds only carry the children their renderers actually expect.

    - Inline kinds (text/emphasis/strong/link/inline_code/image/equation) may
      only ever carry other inline children (or none): a heading, list, table
      etc. nested under an `emphasis`/`strong`/`link` is just as illegal as
      the narrower, historically-checked set of block kinds was.
    - `paragraph` and `heading` are "leaf" block kinds: their renderers
      (render_markdown._block/_inline, render_html._block/_inline) join their
      children as inline runs, so a block child (another heading, a section,
      a list, a table, ...) would silently degrade into flattened inline text
      instead of erroring. `section`/`list_item`/`quote`/`table`/`table_row`
      are legitimate block *holders* (e.g. `section` holding its own
      `heading(2, ...)` title node per templates.py, `list_item` holding a
      nested `list`, `quote` holding `paragraph`s) and are intentionally not
      restricted here.
    """
    inline = {"text", "emphasis", "strong", "link", "inline_code", "image", "equation"}
    leaf_blocks = {"paragraph", "heading"}

    def walk(n: Node, parent: str) -> None:
        if n.kind in inline and any(isinstance(c, Node) and c.kind not in inline
                                    for c in n.children):
            raise AstError(f"inline node {n.kind} carries block children")
        if n.kind in leaf_blocks and any(
                isinstance(c, Node) and c.kind not in inline for c in n.children):
            raise AstError(f"{n.kind} carries illegal block child "
                            f"({', '.join(sorted({c.kind for c in n.children if isinstance(c, Node) and c.kind not in inline}))})")
        if n.kind == "table":
            if not n.children or any(c.kind != "table_row" for c in n.children):
                raise AstError("table children must be table_row")
            for row in n.children:
                if any(c.kind != "table_cell" for c in row.children):
                    raise AstError("table_row children must be table_cell")
        if n.kind == "table_cell" and any(
                isinstance(c, Node) and c.kind in ("table", "heading") for c in n.children):
            raise AstError("table_cell carries illegal block")
        for c in n.children:
            if isinstance(c, Node):
                walk(c, n.kind)

    for c in doc.children:
        walk(c, "document")
