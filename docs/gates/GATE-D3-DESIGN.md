# D3 Design Gate — Licencia única de AcademicCore

Documentation only: no code under `src/` was created or modified, no
tests were written, no engine was altered, D1/D2 gates were not
touched, no LICENSE/metadata/README was installed or edited, no
repository was fused, no F15 work was started. The only output of this
phase is this file plus one local commit (no push).

> **Legal boundary.** This is an engineering repository audit, not
> formal legal advice. Where evidence is insufficient for certainty the
> verdict is `UNKNOWN` or `REVIEW REQUIRED`, never a legal conclusion.

## 1. Baseline

- Repository `Damaga2005/AcademicCore`, branch `main`.
- Baseline at audit time: **`5670ffd`** (`docs(architecture): approve
  D2 logging and error design`), `origin/main == c79961b`, working
  tree clean.
- D1 (`2e8017f`) and D2 (`5670ffd`) gates approved and intact
  (verified via `git diff HEAD --stat`, empty for both).
- Roadmap authority (§5.1 rows :213–:216): D1 [12º] DONE → D2 [13º]
  DONE → **D3 [14º] THIS GATE** → F15 [15º]. Strict order.

## 2. Roadmap authority

| Row | Content | Status |
|:---|:---|:---|
| :213 D1 | static modules, manifest, adapter slots | DONE (frozen) |
| :214 D2 | error/logging standard, `UiError`, `d2-error/1` | DONE (frozen) |
| :215 D3 | single license; conversor already MIT | THIS GATE |
| :216 F15 | final app; must not discover license conflicts | prerequisites only |
| D1 §28 | fused code arrives with license metadata in manifest | adopted (§14) |
| D2 §24bis | `ERROR-CODES.md` + new modules carry license metadata | adopted (§17) |

D3 precedes F15 and precedes every fusion (F3-ext conversor, F4-ext
GREELEC, F13-ext sync, F14 Sistemes-de-Mesura).

## 3. Current license inventory (evidence)

| Check | Result |
|:---|:---|
| `LICENSE` / `LICENSE.md` / `LICENSE.txt` in repo | **ABSENT** (`Test-Path` False ×3) |
| `NOTICE*` / `COPYING*` / `AUTHORS*` / `PATENTS*` | **ABSENT** (all False) |
| `LICENSE` in git history (`git log --all -- LICENSE…`) | **NEVER EXISTED** (empty) |
| `pyproject.toml` `license` / `authors` / `maintainers` / classifiers | **ABSENT** (only `name/version/description/readme/requires-python/dependencies`) |
| `README.md:10` badge | `license-MIT-informational` (informational shield, no target URL) |
| `README.md:497-499` | "licensed under the [MIT License](LICENSE)" → **DANGLING LINK** (target does not exist) |
| SPDX / copyright headers in `src/` / `tests/` | **ZERO** (`SPDX\|Copyright\|©` grep: no source headers; only prose matches) |
| Provenance comments (same-author reuse) | 5 files: `conversor_tables.py:3`, `conversor_sanitize.py:4`, `conversor_math.py:4`, `encoding.py:3`, `conversor_images.py:3` — all cite `MIT © 2026 Damaga2005` |
| `docs/migration/CONVERSOR-REUSE-MAP.md:3` | "License: MIT © 2026 Damaga2005 (same author; reuse permitted)" |
| `docs/adr/ADR-0001-ui-technology.md:11,29` | PySide6 (Qt 6, LGPL) chosen; "LGPL compliance: dynamic linking, document in release notes" |
| `docs/architecture/MODULES.md:13` | `pdf/engine` avoids "Qt, Stirling, AGPL libs" (AGPL treated as boundary) |
| `docs/architecture/STIRLING-INTEGRATION.md:8-9` | Stirling top-level `LICENSE` = MIT © 2025 Stirling PDF Inc., open-core proprietary |
| `docs/adr/ADR-0006-pdf-stirling.md:11` | "Stirling-PDF is Apache-2.0 (verify pinned release)" → tension with MIT line above; flagged §12 |
| Copyleft strings in `src/` (`GPL/AGPL/LGPL/MPL/EPL/CDDL`) | **ZERO** code hits (only doc hits above) |

**Central finding (F-001):** the repository *declares* MIT in README
but *ships* no license text. Default posture today is effectively
all-rights-reserved with an MIT aspiration. D3 implementation closes
exactly this gap — mechanically, no re-licensing of third parties
involved (sole human author, §5).

## 4. Canonical license evidence

Target decision: **MIT** — `Copyright (c) 2026 Damaga2005`, standard
MIT text. Evidence chain:

1. README declares MIT twice (badge + §License with link to `LICENSE`).
2. Sibling conversor repo carries a real MIT license file
   (`Documents/HTML TO MD/LICENSE`: "MIT License / Copyright (c) 2026
   Damaga2005 / Permission is hereby granted…") — same author, same
   year, same intended regime; roadmap :215 confirms ("el conversor ya
   usa MIT").
3. All five in-repo conversor adaptations cite `MIT © 2026 Damaga2005`
   in provenance headers — consistent single-author MIT lineage.
4. Dependency set is MIT-compatible (no copyleft bundled, §9–10).
5. No contrary evidence: no GPL-family text, no contributor license
   conflict, no `LICENSE` history to contradict.

Tradeoffs documented (not minimized): MIT permits proprietary forks
with no contribution-back duty — accepted because the project's
integration strategy (adapters for GREELEC/conversor/OneDrive) and
redistribution model (F15 desktop app, §20) favor maximum
compatibility over copyleft enforcement. Required approval: repository
owner (`Damaga2005`) confirms the copyright line at implementation
time (open question OQ-001, non-blocking: evidence already points one
way; confirmation is a signature, not a decision).

## 5. Copyright ownership

- `git log --format="%an <%ae>" --all` (unique): `Damaga2005
  <dmartigallego05@gmail.com>` (human owner), `Dani
  <38189080+Damaga2005@users.noreply.github.com>` (same person,
  GitHub noreply alias), `Claude <noreply@anthropic.com>` (AI coding
  assistant commits — tool output, not a legal person; copyright vests
  in the operating human).
- Conclusion: **single human copyright holder candidate:
  `Damaga2005`**. No external contributors, no multi-holder files, no
  imported third-party files in `src/`/`tests/`.
- `Damaga2005` is evidenced as GitHub owner + email holder; whether it
  maps to a legal name/entity for a copyright line beyond the handle
  is OQ-001 (owner input). D3 does NOT invent a legal identity — the
  canonical line stays `Copyright (c) 2026 Damaga2005` unless the owner
  directs otherwise at implementation.

## 6. Source/header audit

Policy existing today: **no headers anywhere** (verified §3). D3
policy (design, not yet implemented):

- Adopt `SPDX-License-Identifier: MIT` single-line markers.
- Apply to: all new files from D3-implementation onward + any file
  touched by future work (ratchet, not rewrite).
- Do NOT mass-rewrite ~200 existing files in one commit (churn +
  blame destruction for zero legal gain; full-header injection is
  rejected).
- Exempt: `docs/` prose (covered by repo LICENSE), `tests/` fixtures
  that are data (covered unless third-party, §15), generated
  artifacts (`__pycache__`, build outputs — never committed anyway),
  vendored third-party code if ever added (keeps its own headers +
  NOTICE entry).
- Validation (future D3-004): ratchet test — every file whose mtime
  postdates D3-implementation must carry the SPDX line, with an
  allowlist for data/generated.

## 7. Package metadata audit

`pyproject.toml` gaps: no `license`, no `authors`, no `maintainers`,
no classifiers, no `license-files`. README already names `LICENSE` as
canonical file, so implementation is mechanical:

```toml
license = { text = "MIT" }
authors = [{ name = "Damaga2005" }]
classifiers = ["License :: OSI Approved :: MIT License", ...]
```

(`license-files` globs only if setuptools version in the F15 build
env supports it — implementation detail, fallback is file presence +
classifier.) `requirements*.txt` carry no license metadata by nature;
no change needed there. Consistency rule (invariant D3-I002): README
badge + README §License + `pyproject` + `LICENSE` file must agree;
drift is a release-blocking test (D3-002/D3-003/D3-015).

## 8. Documentation audit

- README MIT claim vs missing file = the single contradiction (F-001);
  resolves itself once `LICENSE` lands (link becomes live, no README
  rewrite beyond verification).
- ADRs/MODULES/STIRLING docs already record LGPL/Apache/AGPL-avoidance
  reasoning — no doc contradicts MIT-target; STIRLING MIT-vs-Apache
  tension is external-tool documentation, resolved by pinning (§12).
- No `CONTRIBUTING`/`SECURITY` license sections exist to contradict.

## 9. Dependency audit (direct, with evidence)

| Component | Version pin | Source | License (evidence) | Bundled? | Notice? | Status |
|:---|:---|:---|:---|:---:|:---:|:---|
| Python stdlib (sqlite3, etc.) | interpreter | PSF | PSF (runtime, not distributed) | no | no | compatible |
| PySide6 | `>=6.7` | `pyproject` + `requirements` + `pip show` | **LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only** (`pip show`) + ADR-0001 LGPL record | no (pip dep, dynamic link) | YES (future NOTICE) | compatible by documented terms (dynamic linking; no static bundling; F15 installer must not embed Qt statically) |
| beautifulsoup4 | `>=4.12` | `requirements` + `pip show` | **MIT** (`pip show`) | no | attribution via NOTICE | compatible |
| lxml | `>=5.0` | `requirements` + `pip show` | **BSD-3-Clause** (`pip show`) | no (wheels bundle libxml2 — note in NOTICE) | YES | compatible |
| markdownify | `>=1.2` | dev-req | UNKNOWN (blank local metadata) | no | verify | requires review (D3 impl: confirm upstream license) |
| mathml2latex | `>=0.1.0` | dev-req + `pip show` | **MIT** | no | attribution | compatible |
| genanki | `>=0.13.0` | dev-req + `pip show` | **MIT** | no | attribution | compatible |
| pypdf | `>=5.0` | `requirements` + `pip show` | UNKNOWN (blank local metadata; upstream historically BSD-3 — UNVERIFIED here) | no | verify | requires review |
| pytest / pytest-qt | dev | `pip show` pytest-qt | pytest-qt **MIT**; pytest UNKNOWN (blank metadata) | no (dev-only, never shipped) | no | dev-only; verify at SBOM time |
| ngspice 47 | external exe | PATH/user-archive probe | own license (GPL-family upstream — NOT bundled, NOT linked; spawned as separate process) | **NO** | mention in docs only | external-tool boundary (§12) |
| Stirling-PDF | optional local Java / HTTP | `pdf/stirling.py` | Apache-2.0 per ADR-0006 vs MIT-open-core per STIRLING doc — UNRESOLVED pin | **NO** | pin + verify | REVIEW REQUIRED (§12) |

Transitive dependencies: NOT inventoried (no lock file exists) —
D3 implementation generates the first pinned inventory; F15
distribution needs the full SBOM (§22). Nothing here is bundled into
the repo (no wheels/jars/exes vendored — verified: zero `*.jar /
*.exe / *.dll / *.whl` outside `.git`/`__pycache__`).

## 10. Copyleft review

- `GPL/AGPL/LGPL/MPL/EPL/CDDL` in `src/`: zero hits. No copyleft code
  is bundled, linked statically, or copied into the repo.
- PySide6 LGPL: consumed as a normal pip dependency with dynamic
  linking (standard `from PySide6…` imports; no static embedding, no
  Qt source in repo) — compatible by documented LGPL terms; standing
  obligations for F15: keep dynamic linkage, ship LGPL attribution +
  license text in NOTICE, document in release notes (ADR-0001 already
  requires this).
- ngspice (upstream GPL-family, unverified version text here): used
  strictly as an **external process** (`shell=False`, scoped cwd) —
  separate-process boundary, no linking, no vendoring; no copyleft
  propagation path into AcademicCore sources by the documented
  mechanism. Docs mention only.
- AGPL: explicitly avoided per MODULES.md (`pdf/engine` keeps
  AGPL libs out) — keep the avoidance rule as policy.
- Verdict: **no copyleft blocker; no bundled copyleft; no REVIEW
  REQUIRED except the Stirling pin** (§12).

## 11. Converter audit

- External repo `Conversor-HTML-A-MD`: real `LICENSE` file, MIT © 2026
  Damaga2005 (verified full header lines 1–7). Same author/year as
  AcademicCore target — fusion is license-homogeneous.
- In-repo engine (`documents/conversor_*.py` + `encoding.py`): five
  provenance headers citing `MIT © 2026 Damaga2005`; behavior adapted
  (pure functions, no Tk) — no third-party code inside beyond
  `beautifulsoup4/markdownify/mathml2latex` deps (all MIT/BSD per §9
  except markdownify pending verify).
- Converter ≠ its dependencies: recorded explicitly — fusion imports
  the *code* (MIT, same author) while each *dependency* keeps its own
  license row in §9/NOTICE.
- No action needed beyond D3-implementation NOTICE attribution
  (same-author line, one row).

## 12. ngspice and external software

- `infrastructure/ngspice.py` + `pdf/stirling.py` are the only
  `subprocess` sites (D1/D2 carried over). Both spawn external
  programs; neither vendors binaries, libraries, or source.
- ngspice: discovered via PATH/user dirs (`candidates()`), never
  shipped. `test_f7*` fixtures embed *sample stdout text* (own test
  data, no license weight).
- Stirling: `StirlingRuntime` talks HTTP to a local/remote instance
  and can spawn a local Java process from a **user-supplied jar path**
  (no jar in repo). License pin conflict (MIT-open-core vs
  Apache-2.0) → **REVIEW REQUIRED at D3 implementation**: pin the
  release, record its actual `LICENSE`, keep it outside the
  distribution bundle. Non-blocking for D3 design (no code ships it).
- Other externals (`pdflatex`, OneDrive — both config-disabled
  placeholders): same invoked-not-bundled treatment (§13 in D1 carries
  over).

## 13. GREELEC

Classification maintained: **UNKNOWN / REQUIRES INPUT / NO
INTEGRATION**. Zero code/doc references in-repo beyond roadmap rows
and `docs/migration/MATRIX.md:30`; no license, no holder, no repo
ownership evidence. Required inputs before any fusion: (1) provenance
(repo owner + commit/artifact hash), (2) license text + holder,
(3) third-party inventory of the `.exe` (bundled runtimes?), (4) F4
model mapping owner. GREELEC is the standing **provenance gate**
(D3-010): F4-ext cannot start without these four items. Non-blocking
for D3 (slot reserved, same as D1/D2).

## 14. Future adapters and OneDrive

Policy (no integration in D3): every future adapter lands with
(1) its code under the repo target license (or a recorded exception),
(2) SDK/vendor deps inventoried per §9, (3) manifest `security_policy`
+ provenance fields (D1 §28), (4) service/API terms recorded
*separately* from software license (OneDrive/Graph terms ≠ code
license; API keys never in LICENSE/NOTICE/SBOM). Static-module rule
(D1) keeps this enforceable at review time.

## 15. Plugins and modules

D1 approved static internal modules only. D3 rule: **every module in
the static registry is covered by the single repo license**; the
manifest reserves license/provenance metadata fields for future
adapters. No third-party plugin loader exists, so no plugin-license
conflict surface exists today. If dynamic plugins are ever proposed,
they need their own license gate (out of scope, recorded here).

## 16. Third-party / copied code

`based on|adapted from|copied from|derived from|source:` grep over
`src/tests/docs`: only hits are the five same-author conversor
provenance headers (§3) plus ordinary prose ("derived from KCL…",
"based on electrical loops" — physics derivations, not code
provenance). **No third-party copied code found.** `math/logarithm.py`
tolerances, `rf/networks.py` formulas are first-principles math, not
attributable expression.

## 17. Generated code

No codegen pipeline exists (`codegen/autogenerated` hits: none in
`src/`; `generated` hits are runtime values — template-minted doc ids,
deterministic item orders, power-balance descriptions). Tests contain
reference-output fixtures (`test_*_output` dirs live in the *external*
conversor dir, not this repo). Rule: if a generator is ever added, its
output inherits the repo license and needs no independent headers.

## 18. Test fixtures, assets, data

`tests/` = `.py` only (+ `__pycache__`); **no `tests/data` dir, no
vendored PDFs/HTML/images/fonts/icons**. Fixtures are inline sample
strings (ngspice stdout snippets, netlists, markdown) authored with
the tests — same-license repo content. External course HTML
(`Laboratorio_Virtual_Sensores.html`) lives in the conversor dir, not
this repo. F14 (`Sistemes-de-Mesura` corpus) is future ingestion, not
present. No asset with distinct rights found in-repo.

## 19. F8 / F8-N license relevance

F8-P1…P5 + F8-N are first-party math (same author, same repo, no
external code observed in `domain/engineering/*`). D3 introduces zero
functional change (no file touched), so certified behavior is
untouched by construction. Only standing item: engine files fall under
the same SPDX ratchet (§6) like everything else.

## 20. Distribution policy (F15-ready design)

Each future artifact (sdist, wheel, standalone app/installer,
container, zip) MUST contain: `LICENSE` (canonical MIT text),
`THIRD_PARTY_NOTICES.md` (PySide6 LGPL text + attribution rows for
MIT/BSD deps + lxml libxml2 note), and (for app/installer/container)
an SBOM snapshot (CycloneDX, generated at build). Wheel/sdist get
`license-files` metadata when the toolchain supports it. F15's release
checklist starts from D3-012; no license conflict may surface there
for the first time.

## 21. Compatibility analysis

MIT target vs inventory: stdlib ✓, PySide6 LGPL-dynamic ✓ (terms
documented), MIT deps ✓, BSD-3 lxml ✓, UNKNOWNs (markdownify, pypdf,
pytest-dev-only) → verify-before-ship, none bundled ✓, no copyleft
bundled ✓, conversor MIT-same-author ✓, GREELEC gated-out ✓. No
incompatibility found; two verify-items + one pin-review, all tracked
to implementation checks (D3-006/D3-009/D3-010).

## 22. Security / supply chain

- SBOM (CycloneDX): **required** at F15 distribution; **optional**
  before (recommended once at D3 implementation for the pinned set).
- Dependency lock (`requirements` pins are floor-only `>=` today):
  **required** before F15 (lock file or pinned SBOM); out of scope for
  D3 design.
- License scanner (e.g. `pip-licenses` class of tooling): **optional**
  (one-shot verification aid, not a committed tool).
- SPDX report: **not required** as artifact (SPDX headers + SBOM cover
  it).
- Hygiene invariant: no secrets/credentials/private paths in
  LICENSE/NOTICE/SBOM (D3-I015; scanners run on public metadata
  only).

## 23. Migration strategy (design — NOT executed)

1. Confirm target (MIT) + copyright line with owner (OQ-001 signature).
2. Install canonical `LICENSE` (standard MIT text, `Copyright (c)
   2026 Damaga2005`).
3. Set `pyproject` license/authors/classifiers.
4. Verify README link live (no rewrite needed).
5. Resolve verify-items: markdownify + pypdf upstream licenses;
   Stirling pin review.
6. Write `THIRD_PARTY_NOTICES.md` (structure §24 of D2-style: component,
   version, license, bundled?, notice text/location).
7. Add SPDX ratchet test (D3-004) + consistency tests (D3-001…003).
8. Record GREELEC gate (D3-010) in F4-ext prerequisites.
9. Validate a trial sdist/wheel contents (D3-012).
No big bang: steps 1–4 are the atomic license fix; 5–9 are follow-ups
that must land before F15, tracked as implementation checklist.

## 24. F8 preservation

No F8 file inspected beyond license relevance (§19); zero modified
(`git diff HEAD --stat -- src tests` will read empty at validation).
Certified behavior preserved by construction (design-only phase).

## 25. D1/D2 preservation

Both gate docs intact (verified empty diff). D3 consumes their
policies (manifest license fields D1 §28; `ERROR-CODES.md` license
metadata D2 §24bis) and adds no contradictions: static modules ⇒
single-license coverage (§15); `d2-error/1` wire form carries no
license text (out of scope by design).

## 26. Invariants

| ID | Property | Future check |
|:---|:---|:---|
| D3-I001 | canonical `LICENSE` (MIT, `© 2026 Damaga2005`) exists at root | D3-001 |
| D3-I002 | README + `pyproject` + `LICENSE` agree (no drift) | D3-002/003/015 |
| D3-I003 | single human copyright holder evidenced; no invented identity | D3-015 |
| D3-I004 | third-party inventory complete for shipped set; no UNKNOWN bundled | D3-005/006 |
| D3-I005 | no copyleft code bundled/linked/copied | D3-007 |
| D3-I006 | conversor lineage MIT-same-author recorded | D3-009 |
| D3-I007 | GREELEC stays NO-INTEGRATION until 4 provenance inputs | D3-010 |
| D3-I008 | external tools invoked-not-bundled (ngspice/Stirling) | D3-012 |
| D3-I009 | NOTICE exists with LGPL + attribution rows before F15 | D3-011 |
| D3-I010 | SPDX ratchet: touched files carry identifier | D3-004 |
| D3-I011 | distribution artifacts contain LICENSE + NOTICES + SBOM | D3-012 |
| D3-I012 | F8/D1/D2 untouched by licensing work | D3-013/014 |
| D3-I013 | no license change without owner evidence | D3-015 |
| D3-I014 | API/service terms recorded separately from code license | D3-011 |
| D3-I015 | no secrets/credentials/private paths in license artifacts | D3-011 |

## 27. Test/validation plan (D3 implementation, not this phase)

D3-001 canonical LICENSE exists + text hash matches MIT template ·
D3-002 metadata matches LICENSE · D3-003 README link live + claim
matches · D3-004 SPDX ratchet · D3-005 third-party inventory
completeness · D3-006 dependency license table (zero UNKNOWN shipped) ·
D3-007 copied-code scan (allowlist = 5 conversor headers) · D3-008
asset/fixture scan (no foreign-rights blobs) · D3-009 converter
license verification (external LICENSE hash + in-repo headers) ·
D3-010 GREELEC provenance gate (4 inputs or NO-INTEGRATION) · D3-011
NOTICE validation (LGPL text present, no secrets) · D3-012
distribution contents (trial sdist/wheel) · D3-013 F8 regression
(suites green) · D3-014 architecture preservation (D1/D2 diffs empty) ·
D3-015 final consistency (single-license statement + owner sign-off).

## 28. Risk matrix

| Risk | Prob. | Impact | Mitigation | Residual | Blocking? |
|:---|:---:|:---:|:---|:---|:---:|
| Wrong target license (MIT) | L | H | evidence chain §4 (README ×2, sibling LICENSE, 5 headers, dep compat) | low | no |
| Copyright holder ambiguity (handle vs legal identity) | M | M | OQ-001 owner confirmation at implementation; line stays handle-shaped meanwhile | low | **non-blocking** |
| Unknown third-party code hidden in repo | L | H | full-provenance grep (§16) + D3-007 allowlist | low | no |
| Copyleft dependency (bundled/linked) | L | H | zero-bundled verified; LGPL-dynamic terms documented; AGPL avoidance kept | low | no |
| Converter provenance mismatch | L | M | external LICENSE hash + same author/year verified | low | no |
| GREELEC unknown (license/holder/contents) | H (unknown persists) | H | NO-INTEGRATION gate; 4 required inputs; blocks F4-ext, not D3 | med | **non-blocking for D3** |
| Third-party fixture with distinct rights | L | M | no data dirs; inline fixtures only; D3-008 | low | no |
| Generated-code ambiguity | L | L | no codegen exists; inherit-rule recorded | low | no |
| Metadata drift (README/pyproject/LICENSE) | M | M | consistency tests D3-002/003/015 | low | no |
| Missing attribution (LGPL/MIT/BSD rows) | M | M | NOTICE design §20 + D3-011 | low | no |
| Distribution omission (LICENSE missing from installer) | M | M | D3-012 trial artifact check before F15 | low | no |
| Future plugin license conflict | L | M | static-only rule + manifest fields (D1 §28) | low | no |
| F15 distribution conflict (first-time surprise) | L | H | SBOM + lock required before F15 (§22) | low | no |
| Stirling pin (MIT vs Apache-2.0) | M | M | REVIEW REQUIRED; pin + record; not bundled | low | **non-blocking** |
| Unverified dep licenses (markdownify/pypdf/pytest) | M | L | verify-items to D3-006; none ship in minimal bundle unverified | low | **non-blocking** |

## 29. Open questions

- **OQ-001** Copyright line form: does `Damaga2005` suffice or is a
  legal name/entity required? Missing: owner direction. Owner: repo
  owner. Impact: one line of text. NON-BLOCKING (handle-shaped line is
  valid placeholder intent; signature at implementation).
- **OQ-002** GREELEC 4 provenance inputs (holder, license, contents,
  mapping owner). Missing: everything. Owner: whoever holds the
  artifact. Impact: blocks F4-ext only. NON-BLOCKING for D3.
- **OQ-003** Stirling release pin + license text. Missing: pinned
  version record. Owner: maintainer at implementation. NON-BLOCKING.
- **OQ-004** markdownify/pypdf/pytest upstream license confirmation.
  Missing: local metadata blanks. Owner: maintainer (`pip-licenses`
  one-shot). NON-BLOCKING.
No BLOCKING questions remain.

## 30. Acceptance criteria

Defined (§32 prompt): target defined ✓ (MIT, §4) · evidence
documented ✓ (§3–4) · canonical strategy ✓ (§23 steps 1–4) ·
ownership treated ✓ (§5 + OQ-001) · dependency inventory ✓ (§9) ·
third-party inventory ✓ (§16/§18: none found) · converter ✓ (§11) ·
GREELEC ✓ (§13 gate) · future adapters ✓ (§14) · F8 ✓ (§19/§24) ·
D1 ✓ (§25) · D2 ✓ (§25) · SPDX/header policy ✓ (§6) · NOTICE policy
✓ (§20) · distribution policy ✓ (§20) · migration ✓ (§23) · test
strategy ✓ (§27) · supply-chain ✓ (§22) · questions classified ✓
(§29, zero blocking).

## 31. Final verdict

D3 design is closed on repository evidence: the single material gap
is the missing `LICENSE` file behind an existing MIT declaration —
the fix is mechanical and owner-evidenced, not a decision awaiting
input. No blocker exists; GREELEC/Stirling/verify-items are fenced
gates, not design holes. D1, D2, F8, roadmap untouched; no license
text installed, no code modified, no fusion performed.

FINAL VERDICT: D3 DESIGN READY
