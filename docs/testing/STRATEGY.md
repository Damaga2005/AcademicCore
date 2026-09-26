# Testing strategy

> Estrategia histórica (resumen). Canónico: `docs/testing/TEST-SUITE.md`
> (D5). Pipeline: `docs/testing/CI.md` (D4).

- Suite estándar (= CI): `pytest -m "not external" -q` (ver TEST-SUITE.md
  §1–§2 para el resto de comandos: bucle rápido, `arch`, `repro`,
  `migration`, `external`, `perf`).
- UI Qt solo offscreen (`QT_QPA_PLATFORM=offscreen`).
- External: `@pytest.mark.external` necesita runtimes vivos
  (Stirling/Java/ngspice); nunca bloquea el gate.
- `integration` = runtime instalado con sonda skip (ver §3).
- Perf: `pytest -m perf`; presupuestos temporales intactos, nunca
  relajados para verdear.
- Equivalence: `tests/conversor_ref.py` loads the read-only Conversor module
  (CONVERSOR_PATH or default checkout) and compares 1:1; skips when absent.
- Excepciones ambientales: solo la tabla de `tests/conftest.py`
  (libxml2-linux xfail estricto, symlink skip con sonda).
