# SPDX-License-Identifier: MIT
"""F3-ext import boundaries (F3.1 §44): explicit limits, never silent.

Values are starting points tuned to catch bombs without breaking real
documents; adjust only with benchmark/tests, never arbitrarily.
"""

from __future__ import annotations

MAX_HTML_BYTES = 10 * 1024 * 1024
MAX_TABLE_CELLS = 10_000
MAX_TABLE_ROWS = 1_000
MAX_TABLE_COLUMNS = 100
MAX_CELL_TEXT = 20_000
MAX_B64_BYTES = 5 * 1024 * 1024
MAX_PDF_BYTES = 100 * 1024 * 1024
MAX_XML_DEPTH = 64
MAX_XML_NODES = 200_000
MAX_ZIP_FILES = 1_000
MAX_ZIP_MEMBER_BYTES = 50 * 1024 * 1024
MAX_TOTAL_DECOMPRESSED_BYTES = 200 * 1024 * 1024
MAX_DOCUMENT_NODES = 100_000
MAX_FORMULAS_PER_DOC = 5_000
MAX_PROBLEMS_PER_DOC = 1_000
MAX_ASSET_BYTES = 20 * 1024 * 1024
