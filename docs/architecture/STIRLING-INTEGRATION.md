# Stirling-PDF integration (researched 2026-09-12, no vendoring, no clone)

## Pinned release
- `STIRLING_VERSION = v2.14.3` · `STIRLING_RELEASE = "2.14.3 lots of bug fixes (2026-08-06)"`
- Source: https://github.com/Stirling-Tools/Stirling-PDF (91k★, Java+Docker)
- `STIRLING_SHA`: empty until an artifact is actually downloaded and verified.

## License (verified via API: SPDX NOASSERTION/"Other")
Top-level `LICENSE` = MIT © 2025 Stirling PDF Inc. BUT open-core: proprietary
subdirectories (`app/proprietary/`, `app/saas/`, `engine/`, editor
proprietary/desktop/saas/cloud/prototypes) carry their own licenses. The
self-hostable server surface is what the API integration uses.
Consequence: Academic Core NEVER vendors/clones Stirling; it talks to an
external runtime's public REST API over localhost. No license contamination
of Academic Core sources.

## Distribution strategy (documented, not yet executed — no Java/Docker here)
Prefer official release assets (`Stirling-PDF.jar` / `Stirling-PDF-server.jar`
/ Windows `.msi`/setup) from GitHub Releases over git clone. `StirlingRuntime`
supports: detect (java+jar+HTTP) → bootstrap (explicit artifact, allow-listed
hosts `github.com`/`objects.githubusercontent.com`, SHA-256 sidecar when
known) → version/health → start/stop/restart → cleanup. States:
NOT_INSTALLED/INSTALLING/READY/UNAVAILABLE/INCOMPATIBLE/ERROR/STOPPED.

## API (official docs: docs.stirlingpdf.com, in-app Swagger `/swagger-ui/`)
- Base `http://127.0.0.1:8080`, multipart `fileInput`, optional `X-API-KEY`
  (`SECURITY_CUSTOMGLOBALAPIKEY`). Localhost enforced client-side.
- Confirmed path shape: `/api/v1/<group>/<op>` (e.g. `/api/v1/security/
  add-watermark` per official docs). `ENDPOINTS` map in `pdf/stirling.py`
  follows this shape for merge/split/rotate/extract-text; `detect_capabilities()`
  probes `/v3/api-docs` and drops anything the running version does not
  expose — endpoint drift across versions is handled, not assumed.
- Frontend-only features (view-pdf, visual sign) are NOT API-addressable
  (official limitation) and are not in the capability map.

## Memory/runtime fit (16 GB machine)
Stirling is a Java server (typical 512 MB–1 GB RSS): runs as an OPTIONAL
sidecar process, started on demand, stopped after batch ops. Native pypdf
backend stays default; Stirling only for ops the native backend cannot do.

## Certification honesty
Client logic (multipart, validation, timeouts, states) is VERIFIED against a
local fake HTTP server in-suite. Live bootstrap/ops are `@pytest.mark.external`
and SIMULATED in this environment (no Java/Docker) — never VERIFIED.
