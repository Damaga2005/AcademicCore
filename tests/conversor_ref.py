"""Equivalence harness vs Conversor-HTML-A-MD (read-only reference).

Loads the ORIGINAL module (Tk import is headless-safe; entry guarded) from
CONVERSOR_PATH or the default local checkout. Skips cleanly when absent so
CI elsewhere stays green; here it runs the real 1:1 comparisons.
"""
import importlib.util
import os

import pytest

DEFAULT = r"C:\Users\dmart\Documents\HTML TO MD\conversor_html_notebooklm.py"


def load_original():
    path = os.environ.get("CONVERSOR_PATH", DEFAULT)
    if not os.path.isfile(path):
        pytest.skip(f"conversor reference absent: {path}")
    spec = importlib.util.spec_from_file_location("conversor_orig", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
