"""Authoring domain (Phase 5): pure editing model over the canonical AST.

Paths address nodes: () = document root children, (2,) = third top block,
(2, 0) = its first child, etc. Commands are frozen dataclasses with
`apply(doc) -> Document` and `inverse() -> Command`; both are total on valid
inputs and raise AuthoringError otherwise. No Qt. No I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from academic_core.documents import ast as A

Path = tuple[int, ...]
UNDO_LIMIT = 200

LIFECYCLE = ("DRAFT", "REVIEW", "PUBLISHED", "ARCHIVED")
TRANSITIONS = {
    "DRAFT": ("REVIEW", "ARCHIVED"),
    "REVIEW": ("PUBLISHED", "DRAFT"),
    "PUBLISHED": ("ARCHIVED",),
    "ARCHIVED": (),
}


class AuthoringError(ValueError):
    pass


def transition(state: str, to: str) -> str:
    if state not in TRANSITIONS:
        raise AuthoringError(f"bad lifecycle state: {state}")
    if to not in TRANSITIONS[state]:
        raise AuthoringError(f"illegal transition {state} -> {to}")
    return to


def _get(doc: A.Document, path: Path) -> A.Node:
    node: A.Node = A.Node("document", {}, doc.children)
    for i in path:
        if not (0 <= i < len(node.children)):
            raise AuthoringError(f"path out of range: {path}")
        node = node.children[i]
    return node


def _set(doc: A.Document, path: Path, new: A.Node) -> A.Document:
    if not path:
        raise AuthoringError("cannot replace the document root")
    parent = _get(doc, path[:-1])
    kids = list(parent.children)
    if not (0 <= path[-1] < len(kids)):
        raise AuthoringError(f"path out of range: {path}")
    kids[path[-1]] = new
    return _rebuild(doc, path[:-1], parent, kids)


def _rebuild(doc: A.Document, path: Path, node: A.Node, kids: list) -> A.Document:
    new_node = A.Node(node.kind, dict(node.attrs), tuple(kids))
    if not path:
        return A.Document(doc.meta, doc.history, tuple(kids))
    return _set(doc, path, new_node)


def _insert_at(doc: A.Document, path: Path, node: A.Node) -> A.Document:
    if not path:
        return A.Document(doc.meta, doc.history, doc.children + (node,))
    parent = _get(doc, path[:-1])
    kids = list(parent.children)
    if not (0 <= path[-1] <= len(kids)):
        raise AuthoringError(f"path out of range: {path}")
    kids.insert(path[-1], node)
    return _rebuild(doc, path[:-1], parent, kids)


def _delete_at(doc: A.Document, path: Path) -> tuple[A.Document, A.Node]:
    if not path:
        raise AuthoringError("cannot delete the document root")
    parent = _get(doc, path[:-1])
    kids = list(parent.children)
    if not (0 <= path[-1] < len(kids)):
        raise AuthoringError(f"path out of range: {path}")
    removed = kids.pop(path[-1])
    return _rebuild(doc, path[:-1], parent, kids), removed


@dataclass(frozen=True)
class InsertNode:
    path: Path
    node: A.Node

    def apply(self, doc: A.Document) -> A.Document:
        A.validate(_insert_at(doc, self.path, self.node))
        return _insert_at(doc, self.path, self.node)

    def inverse(self) -> "DeleteNode":
        return DeleteNode(self.path)


@dataclass(frozen=True)
class DeleteNode:
    path: Path

    def apply(self, doc: A.Document) -> "DeleteNodeWithOld":
        new_doc, removed = _delete_at(doc, self.path)
        A.validate(new_doc)
        return DeleteNodeWithOld(self.path, removed)

    def inverse(self):
        raise AuthoringError("apply DeleteNode first (returns the invertible form)")


@dataclass(frozen=True)
class DeleteNodeWithOld:
    path: Path
    removed: A.Node

    def apply(self, doc: A.Document) -> A.Document:
        new_doc, _ = _delete_at(doc, self.path)
        A.validate(new_doc)
        return new_doc

    def inverse(self) -> "InsertNode":
        return InsertNode(self.path, self.removed)


@dataclass(frozen=True)
class ReplaceNode:
    path: Path
    node: A.Node

    def apply(self, doc: A.Document) -> "ReplaceNode":
        old = _get(doc, self.path)
        new_doc = _set(doc, self.path, self.node)
        A.validate(new_doc)
        return ReplaceNodeWithOld(self.path, self.node, old)

    def inverse(self):
        raise AuthoringError("apply ReplaceNode first (returns the invertible form)")


@dataclass(frozen=True)
class ReplaceNodeWithOld:
    path: Path
    node: A.Node
    old: A.Node

    def apply(self, doc: A.Document) -> A.Document:
        return _set(doc, self.path, self.node)

    def inverse(self) -> "ReplaceNodeWithOld":
        return ReplaceNodeWithOld(self.path, self.old, self.node)


@dataclass(frozen=True)
class MoveNode:
    src: Path
    dst: Path

    def apply(self, doc: A.Document) -> "MoveNodeWithNode":
        node = _get(doc, self.src)
        tmp, _ = _delete_at(doc, self.src)
        # dst shifts left when it sits after src in the same parent
        dst = self.dst
        if self.dst[:-1] == self.src[:-1] and self.dst[-1] > self.src[-1]:
            dst = self.dst[:-1] + (self.dst[-1] - 1,)
        new_doc = _insert_at(tmp, dst, node)
        A.validate(new_doc)
        return MoveNodeWithNode(self.src, dst, node)

    def inverse(self):
        raise AuthoringError("apply MoveNode first (returns the invertible form)")


@dataclass(frozen=True)
class MoveNodeWithNode:
    src: Path
    dst: Path
    node: A.Node

    def apply(self, doc: A.Document) -> A.Document:
        tmp, _ = _delete_at(doc, self.src)
        return _insert_at(tmp, self.dst, self.node)

    def inverse(self) -> "MoveNodeWithNode":
        # after the move the node lives at dst; move it back to src
        return MoveNodeWithNode(self.dst, self.src, self.node)


@dataclass(frozen=True)
class UpdateText:
    path: Path
    text: str

    def apply(self, doc: A.Document) -> "UpdateTextWithOld":
        node = _get(doc, self.path)
        if node.kind != "text":
            raise AuthoringError("UpdateText targets text nodes only")
        new_doc = _set(doc, self.path, A.text(self.text))
        A.validate(new_doc)
        return UpdateTextWithOld(self.path, self.text, node.attrs["value"])

    def inverse(self):
        raise AuthoringError("apply UpdateText first (returns the invertible form)")


@dataclass(frozen=True)
class UpdateTextWithOld:
    path: Path
    text: str
    old: str

    def apply(self, doc: A.Document) -> A.Document:
        return _set(doc, self.path, A.text(self.text))

    def inverse(self) -> "UpdateTextWithOld":
        return UpdateTextWithOld(self.path, self.old, self.text)


@dataclass(frozen=True)
class UpdateMetadata:
    meta: A.Metadata

    def apply(self, doc: A.Document) -> "UpdateMetadataWithOld":
        return UpdateMetadataWithOld(self.meta, doc.meta)

    def inverse(self):
        raise AuthoringError("apply UpdateMetadata first (returns the invertible form)")


@dataclass(frozen=True)
class UpdateMetadataWithOld:
    meta: A.Metadata
    old: A.Metadata

    def apply(self, doc: A.Document) -> A.Document:
        return A.Document(self.meta, doc.history, doc.children)

    def inverse(self) -> "UpdateMetadataWithOld":
        return UpdateMetadataWithOld(self.old, self.meta)


@dataclass(frozen=True)
class SetAttribute:
    path: Path
    key: str
    value: object

    def apply(self, doc: A.Document) -> "SetAttributeWithOld":
        node = _get(doc, self.path)
        if self.key in ("kind", "children"):
            raise AuthoringError(f"attribute {self.key} is structural")
        new_doc = _set(doc, self.path, A.Node(
            node.kind, {**node.attrs, self.key: self.value}, node.children))
        A.validate(new_doc)
        return SetAttributeWithOld(self.path, self.key, self.value,
                                   node.attrs.get(self.key))

    def inverse(self):
        raise AuthoringError("apply SetAttribute first (returns the invertible form)")


@dataclass(frozen=True)
class SetAttributeWithOld:
    path: Path
    key: str
    value: object  # value to set when applied
    old: object  # previous value (None = key absent)

    def apply(self, doc: A.Document) -> A.Document:
        node = _get(doc, self.path)
        attrs = dict(node.attrs)
        if self.value is None:
            attrs.pop(self.key, None)
        else:
            attrs[self.key] = self.value
        new_doc = _set(doc, self.path, A.Node(node.kind, attrs, node.children))
        A.validate(new_doc)
        return new_doc

    def inverse(self) -> "SetAttributeWithOld":
        return SetAttributeWithOld(self.path, self.key, self.old, self.value)


def _run(cmd, doc: A.Document) -> tuple[A.Document, object]:
    """Run any command form; return (new_doc, executable_form_for_history)."""
    result = cmd.apply(doc)
    if isinstance(result, A.Document):
        return result, cmd
    final = result.apply(doc)
    if not isinstance(final, A.Document):
        raise AuthoringError("command did not resolve to a document")
    return final, result


@dataclass
class AuthoringDocument:
    """Working state: AST + command history. Undo/redo never touch versions."""

    doc: A.Document
    revision: int = 0
    dirty: bool = False
    _undo: list = field(default_factory=list)
    _redo: list = field(default_factory=list)

    def execute(self, cmd) -> None:
        """Apply a command; redo is invalidated; history capped."""
        self.doc, form = _run(cmd, self.doc)
        self._undo.append(form)
        if len(self._undo) > UNDO_LIMIT:
            self._undo.pop(0)
        self._redo.clear()
        self.revision += 1
        self.dirty = True

    def undo(self) -> bool:
        if not self._undo:
            return False
        form = self._undo.pop()
        self.doc, _ = _run(form.inverse(), self.doc)
        self._redo.append(form)
        self.revision += 1
        self.dirty = True
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        form = self._redo.pop()
        self.doc, form2 = _run(form, self.doc)
        self._undo.append(form2)
        self.revision += 1
        self.dirty = True
        return True

    def mark_clean(self) -> None:
        self.dirty = False
