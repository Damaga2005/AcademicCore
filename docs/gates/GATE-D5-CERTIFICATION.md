# GATE-D5-CERTIFICATION — D5 Suite global de tests

> **FASE:** D5 — Suite global de tests y consolidación de regresión.
> **BASELINE:** `main @ 2d7da42` (D4 CERTIFICADA); árbol limpio al inicio.
> **Rama:** `main`, sin líneas paralelas.

## 1. Baseline pre-D5 (2026-09-26, local win, py 3.14.6)

Comando idéntico al job CI: `pytest -m "not external" -q`
(`PYTHONPATH=src`, `QT_QPA_PLATFORM=offscreen`).

- Colectados: **4598 tests en 138 ficheros** (`not external`).
- Resultado: **4583 passed, 2 failed, 13 skipped**, ~60 min.
  (13 skips = sondas ngspice/symlink/STIRLING-ausente; 0 errores.)
- Duraciones top: `test_perf_f8g_scales` 691s (`slow`, por diseño),
  `test_n108_f8_suites_green` 599s, resto F8/E0 scaling (ver log).

### Fallos baseline (ambos preexistentes, ambos tratados §12)

1. `test_f42_notify.py::test_activity_from_documents_and_reading` —
   **test con fecha caducada** (código correcto, test no determinista):
   `add_document` sella `added_at` con el reloj real; con lectura fijada
   el 2026-09-20, cómputo el 2026-10-10 y umbral 14, el test pasa si
   hoy ≤ 2026-09-25 (CI D4 verde) y falla si hoy ≥ 2026-09-26 (local
   rojo). Reproducido aislado. Fix SOLO-test: backdate `added_at` vía
   `replace` + `INSERT OR REPLACE` del repositorio (mismo patrón que
   `test_subject_activity` con `notes_updated_at`). Todas las fechas
   fijas ahora; robusto para siempre. Cero toques a producto.
2. `test_f8d2_complex_solver.py::test_generality_sweep_both_modes` —
   **presupuesto temporal en runner lento** (`105.3s < 90s` en exact-64;
   asserts de corrección todos verdes; CI verde en runners rápidos).
   Fix: `@pytest.mark.perf` individual + docstring (clasificación §9,
   umbral INTACTO, nunca relajado).

## 2. Auditoría (resumen)

- Markers: `external` 15 (runtimes vivos, fuera del gate),
  `integration` 20 (13 con `external`; 7 f8b/f8c con sonda `skipif`
  ngspice — clasificación correcta, no bypass), `slow` 1 (en gate por
  diseño), `migration` 8, `arch`/`repro` registrados sin usar,
  perf sin clasificar.
- Conversor §4: cobertura completa mapeada (headings/listas, enlaces,
  imágenes CAS, tablas, fórmulas MathML/OMML, `code_block`, Unicode,
  malformado, límites, determinismo, seguridad) — sin huecos.
- Consolidación §10: **cero eliminaciones justificadas** (p.ej.
  `test_schedule` = dominio Series vs `test_f4_schedule` = servicio
  calendario+ICS; `test_results` = escalas vs `test_grading` =
  equivalencia Gestion). Eliminar perdería cobertura.
- Matriz 16 áreas / 4598 tests / 0 ficheros sin grupo: ver
  `docs/testing/TEST-SUITE.md` §7.

## 3. Implementación D5

| Cambio | Alcance |
|---|---|
| `tests/test_f13ext_service.py` (nuevo, 13 tests) | Hueco real §5: identidad estable/persistida/regenerada, alcance de export, sync A↔B en 2 BDs reales, favoritos/notas, idempotencia servicio, sin bump espurio, `AC-SYN-001` sin tocar estado, límites transporte, `sync_log` |
| `tests/test_d5_contracts.py` (nuevo, 7 tests) | Cierra §9 F13EXT-SYNC.md (AST sin `eval/exec/subprocess/red` en 7 ficheros F13-ext/D4 + 5 tests), pureza `domain/sync.py`, markers usados ⊆ registrados, `perf` en tests de presupuesto, `arch`/`repro` en uso |
| `application/sync.py` (1 llamada) | **Bug real §12**: `_apply_winners` llamaba `history.add_favourite(kind, ref, title)` estilo-servicio sobre el REPOSITORIO (`add_favourite(SavedSearch)`) → `TypeError` siempre que un favorito remoto se aplicaba. Fix mínimo: construir `PL.SavedSearch` (preserva `created` remoto). Regresión: `test_favourite_and_note_roundtrip` (fallaba antes, pasa ahora) |
| `tests/test_f42_notify.py` (1 test) | Fix §12 test-con-fecha-caducada (solo test) |
| `tests/test_f8d2_complex_solver.py` (marker+doc) | Clasificación `perf`, umbral intacto |
| `pytestmark perf` en `test_perf.py`, `test_perf_f5.py`, `test_academic_perf.py`; `arch` en `test_architecture.py`; `repro` en `test_reproducibility.py`; registro `perf` en `pyproject.toml` | Metadato aditivo; CI ejecuta exactamente lo mismo |
| `docs/testing/TEST-SUITE.md` (nuevo, canónico) + `STRATEGY.md` (puntero) | Suite estándar, comandos, markers, fixtures, determinismo, límites ambientales, matriz, decisiones |

Código certificado tocado: **una llamada** (`sync.py`, justificada arriba
con regresión). Nada más: ni motores, ni migraciones, ni gates, ni tests
certificados (salvo los 2 fixes §12 documentados).

## 4. Evidencia fresca (local)

- `test_f42_notify.py`: 10 passed (fix verificado).
- Nuevos: `test_f13ext_service.py` + `test_d5_contracts.py` = 20 passed
  (los 2 fallos iniciales — `TypeError` favorito y expectativa de
  versión — confirmaron que los tests muerden antes del fix).
- Regresión áreas tocadas × 3 hash-seeds (0/1/42):
  `architecture, f13ext_sync/service, d5_contracts, d4_pipeline, f42_*,
  f4_mgmt, persistence, migration, f15_app` → **134 passed × 3**.
- Riesgo residual documentado (sin cambio): `saved:<kind>` remoto con
  kind fuera de `SEARCH_KINDS` lanzaría `DomainError` en apply (frontera
  de confianza del transporte; futuro F13).

## 5. Criterios (§15)

- [x] suite definida y reproducible (TEST-SUITE.md §1–§2)
- [x] integrada con CI D4 (mismos comandos; CI intacto)
- [x] baseline documentado (§1)
- [x] auditoría realizada (§2)
- [x] duplicaciones: ninguna procedente (evidencia §2)
- [x] conversor cubierto (matriz §7 doc)
- [x] F13-ext protegido (12 motor + 13 servicio + contratos AST)
- [x] migraciones y arquitectura protegidos (sin tocar + tests verdes)
- [x] external/perf clasificados (markers + comandos, umbrales intactos)
- [x] sin bypasses (conftest intacto; skips solo con sonda)
- [x] sin reducción de cobertura (CI ejecuta lo mismo + 20 tests nuevos)
- [x] documentación y gate creados
- [ ] suite verde en CI — pendiente run del proveedor (ver §6)
- [ ] evidencia CI fresca — pendiente (ver §6)

## 6. Veredicto

**D5 IMPLEMENTADA, PENDIENTE DE RUN REAL EN CI** (precedente D4 §15:
no certificar sin ejecución del proveedor). Roadmap queda en
`D5 SIGUIENTE` → `CERTIFICADA` (y `D6 SIGUIENTE`) con el run verde.
