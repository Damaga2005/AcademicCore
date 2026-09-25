# SPDX-License-Identifier: MIT
"""D4: manejo explícito de limitaciones ambientales conocidas (§14).

Este hook NO oculta fallos de código: solo aplica marcas a los dos casos
documentados abajo, cada uno con causa raíz probada y alcance mínimo
(plataforma concreta). Cualquier otro fallo sigue haciendo fallar CI.

Tabla de excepciones (fijada por tests/test_d4_pipeline.py):
1. libxml2-divergencia (linux): el golden `html_cp1252` pinea el digest de
   la recuperación HTML de lxml; el wheel manylinux de lxml produce otro
   árbol que el wheel Windows con el MISMO lock (evidencia: win py3.12 y
   py3.14 dan el golden; ubuntu-24.04 da 3cd3bc49...). Preexistente y ya
   documentado en CHANGELOG (F4.1 "fallo F3 golden preexistente por
   libxml2"). xfail estricto: si algún día coincide, XPASS vuelve rojo.
2. symlink-privilegio (solo si el SO lo niega): crear symlinks en Windows
   exige privilegio/modo desarrollador (WinError 1314). Se prueba la
   capacidad real; si existe, el test corre normal.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

CP1252_NODE = "tests/test_f3_golden.py::TestGolden::test_html_corpus"
SYMLINK_NODE = "tests/test_f4_security.py::test_document_symlink_escape_refused"

LINUX_LIBXML_REASON = (
    "golden html_cp1252 diverge con el wheel manylinux de lxml "
    "(preexistente, documentado; solo linux)"
)
SYMLINK_REASON = (
    "el SO niega crear symlinks (p.ej. WinError 1314 sin modo desarrollador)"
)


def _symlink_works() -> bool:
    if not hasattr(os, "symlink"):
        return False
    try:
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "s")
            dst = os.path.join(td, "l")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("x")
            os.symlink(src, dst)
            return True
    except (OSError, NotImplementedError):
        return False


def pytest_collection_modifyitems(session, config, items):
    for item in items:
        if item.nodeid.endswith(CP1252_NODE) and sys.platform.startswith("linux"):
            item.add_marker(pytest.mark.xfail(
                strict=True, reason=LINUX_LIBXML_REASON))
        if item.nodeid.endswith(SYMLINK_NODE) and not _symlink_works():
            item.add_marker(pytest.mark.skip(reason=SYMLINK_REASON))
