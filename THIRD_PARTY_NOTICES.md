# SPDX-License-Identifier: MIT
# Third-Party Notices — AcademicCore (D3 implementation, F15)

This file records the licenses of third-party components used by
AcademicCore, as verified from locally installed package metadata at
F15 implementation time (2026-09-22). No holder, license, or URL is
invented: every row cites its evidence source.

Runtime distribution ships only: Python stdlib (PSF, runtime, not
distributed), PySide6 (LGPL, dynamic link), beautifulsoup4 (MIT),
lxml (BSD-3-Clause, wheels bundle libxml2 — see note), pypdf
(BSD-3-Clause, License-Expression), markdownify (MIT, classifier),
mathml2latex (MIT), genanki (MIT). Dev/test-only (never shipped in
runtime distribution): pytest (MIT, License-Expression), pytest-qt
(MIT). No wheels, jars, exes, or DLLs are vendored in the repo.

| Component | Version (pinned at F15) | Source | License (evidence) | Bundled? | Notice |
|:---|:---|:---|:---|:---:|:---|
| Python stdlib (sqlite3, etc.) | interpreter 3.14.6 | PSF | PSF (runtime, not distributed) | no | no |
| PySide6 (Qt 6) | 6.11.1 | `pip show PySide6` | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only (`pip show` License field) + ADR-0001 LGPL record | no (pip dep, dynamic link; F15 installer must not embed Qt statically) | YES — LGPL attribution; license text shipped in distribution; documented in release notes per ADR-0001 |
| beautifulsoup4 | 4.15.0 | `pip show beautifulsoup4` | MIT (`pip show` License field) | no | attribution via this file |
| lxml | 6.1.3 | `pip show lxml` | BSD-3-Clause (`pip show` License field) | no (wheels bundle libxml2 — noted) | YES |
| markdownify | 1.2.3 | installed metadata classifier | MIT (`License :: OSI Approved :: MIT License` classifier in installed `markdownify` metadata; blank `License` field) — VERIFIED at F15, was D3 UNKNOWN | no | attribution via this file |
| mathml2latex | 0.2.12 | `pip show mathml2latex` | MIT (`pip show` License field) | no | attribution via this file |
| genanki | 0.13.1 | `pip show genanki` | MIT (`pip show` License field) | no | attribution via this file |
| pypdf | 6.14.2 | installed metadata | BSD-3-Clause (`License-Expression: BSD-3-Clause` in installed `pypdf` METADATA) — VERIFIED at F15, was D3 UNKNOWN | no | attribution via this file |
| pytest | 9.1.1 | installed metadata | MIT (`License-Expression: MIT` in installed `pytest` METADATA) — VERIFIED at F15, was D3 UNKNOWN; TEST-ONLY, never shipped | no (dev-only) | no |
| pytest-qt | 4.5.0 | `pip show pytest-qt` | MIT (`pip show` License field); TEST-ONLY, never shipped | no (dev-only) | no |
| ngspice 47 | external exe | PATH / user-archive probe | own upstream license (NOT bundled, NOT linked; spawned as separate process via `infrastructure/ngspice.py`, `shell=False`) | NO | mention in docs only |
| Stirling-PDF | optional local Java / HTTP | `pdf/stirling.py` | REVIEW REQUIRED: ADR-0006 says Apache-2.0 (verify pinned release) vs STIRLING doc MIT-open-core — UNRESOLVED pin; NOT bundled, user-supplied jar path only | NO | pin + verify before any distribution that touches it |

GREELEC: UNKNOWN / REQUIRES INPUT / NO INTEGRATION (zero in-repo
references; 4 provenance inputs required before any F4-ext fusion:
owner, license text + holder, third-party inventory, F4 mapping owner).

Stirling pin: REVIEW REQUIRED (see row above). Not bundled, so
non-blocking for F15.

No secrets, credentials, or private paths appear in this file.
