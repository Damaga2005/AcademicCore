# SPDX-License-Identifier: MIT
"""IPYNB → Document AST adapter (F3.1 §29): stdlib-only, NEVER executes code.

markdown cell → paragraphs (via markdown parser), code cell → code_block,
text/latex output → equation, image/png → F2 CAS. No pickle, no eval.
"""

from __future__ import annotations

import base64
import binascii
import json

from academic_core.documents import ast as A
from academic_core.documents import limits as L
from academic_core.errors import AdapterError, ValidationError

PARSER_NAME = "ipynb-adapter"
PARSER_VERSION = "1.0"


def parse_ipynb(data: bytes | str, put=None, filename: str = "") -> tuple[A.Document, list[str]]:
    warnings: list[str] = []
    if isinstance(data, (bytes, bytearray)):
        if len(data) > L.MAX_ZIP_MEMBER_BYTES * 2:
            raise AdapterError("TRACE_LIMIT: notebook too large", code="AC-ADP-240")
        try:
            text = bytes(data).decode("utf-8")
        except UnicodeDecodeError:
            raise ValidationError("MALFORMED_IPYNB: not UTF-8", code="AC-VAL-240") from None
    else:
        text = data
    try:
        nb = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValidationError(f"MALFORMED_IPYNB: bad JSON ({e})", code="AC-VAL-241") from None
    if not isinstance(nb, dict) or not isinstance(nb.get("cells"), list):
        raise ValidationError("MALFORMED_IPYNB: no cells array", code="AC-VAL-242")
    from academic_core.documents import markdown_parser as MD
    blocks: list[A.Node] = []
    code_cells = md_cells = images = equations = 0
    for idx, cell in enumerate(nb["cells"][:5000]):
        if not isinstance(cell, dict):
            warnings.append(f"cell {idx} skipped (not an object)")
            continue
        ctype = cell.get("cell_type", "")
        src = cell.get("source", [])
        src_text = "".join(src) if isinstance(src, list) else str(src or "")
        if len(src_text) > L.MAX_CELL_TEXT * 10:
            warnings.append(f"cell {idx} truncated (oversize)")
            src_text = src_text[:L.MAX_CELL_TEXT * 10]
        if ctype == "markdown":
            md_cells += 1
            try:
                sub = MD.parse_markdown(src_text, f"{filename}#cell-{idx}")
                blocks.extend(sub.children)
            except (ValidationError, AdapterError, ValueError) as e:
                warnings.append(f"markdown cell {idx} kept as text ({e})")
                blocks.append(A.paragraph([A.text(src_text)]))
        elif ctype == "code":
            code_cells += 1
            blocks.append(A.code_block(src_text, "python"))
            for out in (cell.get("outputs") or [])[:100]:
                if not isinstance(out, dict):
                    continue
                otype = out.get("output_type", "")
                if otype == "stream":
                    txt = "".join(out.get("text", []) or [])
                    if txt.strip():
                        blocks.append(A.code_block(txt, "text"))
                elif otype in ("display_data", "execute_result"):
                    data_map = out.get("data", {}) or {}
                    if "text/latex" in data_map:
                        latex = str(data_map["text/latex"]).strip().strip("$")
                        blocks.append(A.paragraph([A.equation(latex, "latex", True)]))
                        equations += 1
                    elif "image/png" in data_map:
                        images += 1
                        b64 = "".join(data_map["image/png"] or [])
                        if len(b64) > L.MAX_B64_BYTES:
                            warnings.append(f"cell {idx} image skipped (oversize)")
                            continue
                        try:
                            blob = base64.b64decode(b64, validate=True)
                        except (binascii.Error, ValueError):
                            warnings.append(f"cell {idx} image skipped (bad base64)")
                            continue
                        if put is not None:
                            ref = put(blob)
                        else:
                            import hashlib
                            ref = "cas:" + hashlib.sha256(blob).hexdigest()
                        blocks.append(A.paragraph([A.image(ref, f"cell {idx}")]))
                    elif "text/plain" in data_map:
                        plain = str(data_map["text/plain"])
                        if not plain.strip().startswith("<"):
                            blocks.append(A.code_block(plain, "text"))
                elif otype == "error":
                    warnings.append(f"cell {idx} error output noted (not executed)")
        else:
            warnings.append(f"cell {idx} type {ctype!r} UNSUPPORTED (kept as text)")
            if src_text.strip():
                blocks.append(A.paragraph([A.text(src_text)]))
    history = [{"parser": PARSER_NAME, "version": PARSER_VERSION, "source": filename,
                "code_cells": code_cells, "markdown_cells": md_cells,
                "images": images, "equations": equations}]
    meta = A.Metadata(origin="ipynb",
                      extra={"kernel": str(((nb.get("metadata") or {}).get("kernelspec") or {}).get("name", ""))})
    return A.Document(meta, tuple(history), tuple(blocks)), warnings
