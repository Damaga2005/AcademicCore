# SPDX-License-Identifier: MIT
"""Shared runner for the F4.1 closure tests (test_f4_real_*.py).

Sources certified:
- ``synthetic``: the real Gestion schema with clean synthetic rows (always).
- ``real``: the user's own installation, ONLY when the environment defines
  ACORE_GESTION_REAL_DB (and ACORE_GESTION_REAL_DOCS). Nothing from it is
  ever written to the repository; the report is anonymized.
Each source is certified once per pytest process (cached).
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

import gestion_legacy_fixture as G
from academic_core.application.gestion_certification import Certifier

_CACHE: dict[str, tuple[dict, dict]] = {}
REAL_DB = os.environ.get("ACORE_GESTION_REAL_DB", "")
REAL_DOCS = os.environ.get("ACORE_GESTION_REAL_DOCS", "")

SOURCES = ["synthetic", pytest.param(
    "real", marks=pytest.mark.skipif(not REAL_DB, reason="set ACORE_GESTION_REAL_DB "
                                     "(+ACORE_GESTION_REAL_DOCS) to certify the real install"))]


def _synthetic() -> tuple[Path, Path, dict]:
    tmp = Path(tempfile.mkdtemp(prefix="f41-synth-"))
    db, root = G.build(tmp / "legacy")
    cx = sqlite3.connect(db)
    # a clean install: no missing file / traversal row (those are covered by
    # test_f4_migration_dryrun.py and must make the harness FAIL)
    cx.execute("DELETE FROM pagina_texto WHERE documento_id IN (5, 6)")
    cx.execute("UPDATE tarea_evento SET documento_id=NULL WHERE documento_id IN (5, 6)")
    cx.execute("DELETE FROM documento WHERE id IN (5, 6)")
    cx.commit()
    cx.close()
    rows = {t: n for t, n in G.TOTAL_ROWS.items()}
    rows["documento"] -= 2
    rows["pagina_texto"] -= 1
    return db, root, rows


def certified(source: str) -> tuple[dict, dict]:
    """(report, expected_input_counts or {}) for a source."""
    if source not in _CACHE:
        work = Path(tempfile.mkdtemp(prefix=f"f41-cert-{source}-"))
        if source == "synthetic":
            db, root, expected = _synthetic()
        else:
            db, root, expected = Path(REAL_DB), Path(REAL_DOCS) if REAL_DOCS else None, {}
        seeds = ("0", "11", "2024", "random")
        _CACHE[source] = (Certifier(db, root, work / "run").run(seeds=seeds), expected)
    return _CACHE[source]
