# SPDX-License-Identifier: MIT
"""E0.1-R+ honest verification labels for equivalence checks.

Every equivalence CHECK of the E0.1 integrations states how it was
verified. The label is part of the check ``detail`` (suffix
`` · verification_kind=<KIND>``), so the ``execution-trace/1`` schema
does not change:

- ``SYMBOLIC``: proven exactly. Either the exact normal form of the
  difference is 0, or the equality holds in exact rational arithmetic
  (e.g. substituting a Fraction solution). No tolerance is involved.
- ``NUMERIC``: agreement of numeric evaluations within a stated tolerance
  (central difference, evaluation at fixed points, Simpson's rule). This
  is evidence, never a symbolic proof.
- ``NONE``: nothing could be verified (NOT_APPLICABLE checks).

``verification_kind(check)`` reads the label back (``""`` for checks that
carry none, e.g. every E0 check).
"""

from __future__ import annotations

SYMBOLIC = "SYMBOLIC"
NUMERIC = "NUMERIC"
NONE = "NONE"
KINDS = (SYMBOLIC, NUMERIC, NONE)
_MARK = " · verification_kind="
_LIMIT = 512


def labelled(detail: str, kind: str) -> str:
    if kind not in KINDS:
        raise ValueError(f"INVALID_KIND: {kind!r}")
    suffix = f"{_MARK}{kind}"
    return detail[:_LIMIT - len(suffix)] + suffix


def verification_kind(check) -> str:
    """Label of a ``TraceCheck`` (``""`` when the check carries none)."""
    _head, sep, kind = check.detail.rpartition(_MARK)
    return kind if sep and kind in KINDS else ""
