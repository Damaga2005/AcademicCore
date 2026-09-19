"""Shared document-security predicates (Phase 3/5 hardening).

Single canonical home for scheme validation used by all three defense
layers — sanitizer (``conversor_sanitize``), validator (``validate``)
and renderer (``render_html``). Each layer keeps its own call site
(defense in depth is NOT collapsed into one layer); only the predicate
implementation is shared so the layers can never diverge on bypass
variants (ASCII control characters, mixed case, ...).
"""

from __future__ import annotations

import re


def is_javascript_scheme(target: str) -> bool:
    """True if `target` resolves to a javascript: URL once whitespace/control
    characters (which browsers ignore when scheme-matching) are stripped out."""
    return re.sub(r"[\x00-\x20]", "", target.lower()).startswith("javascript:")
