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
