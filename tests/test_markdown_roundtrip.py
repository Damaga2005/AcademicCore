"""Markdown semantic round-trip: md→AST→md→AST compares normalized ASTs."""
import json

from academic_core.documents import ast as A
from academic_core.documents import render_markdown as RM
from academic_core.documents.markdown_parser import parse_markdown


def norm(doc: A.Document) -> str:
    return json.dumps(doc.to_dict(), sort_keys=True)


SAMPLE = """# Tema 3

Texto con **negrita**, *cursiva*, `código` y [enlace](https://x.test/t).

Ecuación $U=R\\cdot I$ y display:

$$\\frac{a}{b}$$

- item uno
- item dos

1. primero
2. segundo

> Nota importante

```python
x = 1
```

| H1 | H2 |
|----|----|
| a  | b  |

---
"""


def test_roundtrip_stable():
    once = parse_markdown(SAMPLE)
    twice = parse_markdown(RM.render(once))
    assert norm(once) == norm(twice)


def test_roundtrip_preserves_semantics():
    doc = parse_markdown(SAMPLE)
    kinds = [c.kind for c in doc.children]
    assert kinds == ["heading", "paragraph", "paragraph", "paragraph", "list",
                     "list", "quote", "code_block", "table", "thematic_break"]
    eqs = [n for p in doc.children if p.kind == "paragraph" for n in p.children
           if n.kind == "equation"]
    assert [(e.attrs["source"], e.attrs["display"]) for e in eqs] == [
        ("U=R\\cdot I", False), ("\\frac{a}{b}", True)]
    assert doc.meta.title == "Tema 3"
    A.validate(doc)


def _leaf_text(n: A.Node) -> str:
    """Concatenate text() leaves under an inline node (recursing through
    strong/emphasis wrappers) so nesting depth doesn't matter for the check."""
    if n.kind == "text":
        return n.attrs["value"]
    return "".join(_leaf_text(c) for c in n.children)


def test_strongem_asterisks_nested_strong_emphasis():
    """`***negrita cursiva***` must parse as strong(emphasis(...)), not as a
    plain strong node flanked by stray literal '*' text nodes (the old bug)."""
    doc = parse_markdown("Esto es ***negrita cursiva*** de estilos.")
    para = doc.children[0]
    assert para.kind == "paragraph"
    kinds = [c.kind for c in para.children]
    assert kinds == ["text", "strong", "text"], kinds
    strong_node = para.children[1]
    assert len(strong_node.children) == 1
    assert strong_node.children[0].kind == "emphasis"
    assert _leaf_text(strong_node.children[0]) == "negrita cursiva"
    # regression guard: no stray literal asterisks leaked into text nodes
    assert "*" not in para.children[0].attrs["value"]
    assert "*" not in para.children[2].attrs["value"]
    A.validate(doc)


def test_strongem_underscores_nested_strong_emphasis():
    """`___bold italic___` (underscore variant) must also nest properly."""
    doc = parse_markdown("Esto es ___negrita cursiva___ de estilos.")
    para = doc.children[0]
    kinds = [c.kind for c in para.children]
    assert kinds == ["text", "strong", "text"], kinds
    strong_node = para.children[1]
    assert len(strong_node.children) == 1
    assert strong_node.children[0].kind == "emphasis"
    assert _leaf_text(strong_node.children[0]) == "negrita cursiva"
    assert "_" not in para.children[0].attrs["value"]
    assert "_" not in para.children[2].attrs["value"]
    A.validate(doc)


def test_strongem_roundtrip_markdown_output():
    """parse -> render must re-emit a clean ***...*** run, not a mangled one."""
    doc = parse_markdown("Esto es ***negrita cursiva*** de estilos.")
    md = RM.render(doc)
    assert "***negrita cursiva***" in md
    # re-parsing the rendered markdown must reproduce the same nested AST
    doc2 = parse_markdown(md)
    assert norm(doc) == norm(doc2)


def test_strongem_does_not_affect_plain_strong_or_emphasis():
    """Regression guard: plain **bold**, plain *italic*, and the two used
    side-by-side (not combined) must be unaffected by the strongem fix."""
    doc = parse_markdown("**negrita** sola.")
    para = doc.children[0]
    assert [c.kind for c in para.children] == ["strong", "text"]
    assert _leaf_text(para.children[0]) == "negrita"
    assert para.children[0].children[0].kind == "text"

    doc = parse_markdown("*cursiva* sola.")
    para = doc.children[0]
    assert [c.kind for c in para.children] == ["emphasis", "text"]
    assert _leaf_text(para.children[0]) == "cursiva"
    assert para.children[0].children[0].kind == "text"

    doc = parse_markdown("**negrita** y *cursiva* por separado.")
    para = doc.children[0]
    kinds = [c.kind for c in para.children]
    assert kinds == ["strong", "text", "emphasis", "text"], kinds
    assert para.children[0].children[0].kind == "text"
    assert _leaf_text(para.children[0]) == "negrita"
    assert para.children[2].children[0].kind == "text"
    assert _leaf_text(para.children[2]) == "cursiva"

    md = RM.render(doc)
    assert "**negrita**" in md and "*cursiva*" in md
    assert "***" not in md
