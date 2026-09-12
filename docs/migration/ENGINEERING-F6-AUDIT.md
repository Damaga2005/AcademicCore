# ENGINEERING-F6-AUDIT — fuentes y AcademicCore (base F5 `a915ce7`)

## AcademicCore existente (reutilizar)
- `engines/engineering.py` (F0 stub): `Component{ref,kind,value,nodes}`,
  `Circuit{stable_id,components,parameters,to_netlist}` — SUPERSEDED por el
  modelo F6 (pins/nets explícitos, quantities tipadas); se conserva el fichero
  intacto y se documenta aquí la sustitución (no se borra en F6).
- `domain/results.py` (Decimal, HALF_UP): patrón a seguir para cantidades.
- `Resource/CAS/versions`, `doc_links`, AuthoringDocument: integración docs.
- Migraciones 001–009; UI facade + tabs; arch tests.

## Conversor-HTML-A-MD (read-only, HEAD `e5b8d60`)
| Concepto | Origen | Veredicto F6 |
|---|---|---|
| GUM calculator + Monte Carlo (`calculate_and_display_gum` L5664, `run_monte_carlo_gum` L5783, `GUM_TEMPLATES` L3402) | `eval()` sobre fórmulas de usuario + Tk | **DO_NOT_REUSE código** (eval prohibido en F6); conceptos (fórmula+vars+distribuciones k=2/k=3/rect/tri) como REFERENCE para F8 |
| Fórmulas cerradas sensores (Pt100 CVD L6161, NTC, AD620 `Rg=49.4k/(G-1)` L6140, Wheatstone) | matemática cerrada + Tk | **REUSE_CONCEPT**: entran como ecuaciones de la librería F6 con provenance, re-derivadas con Quantity/Dimension |
| RLC/filter math + Bode Canvas (L5992–L6728) | Tk-acoplado | **REUSE_CONCEPT**: relaciones RC/frecuencia como ecuaciones F6; plots fuera de F6 |
| Netlists `.cir` strings (divisores, Pt100 4-hilos, BJT, PID, TX-line) | strings | **REFERENCE**: formato de representación para `to_netlist`; sin ejecución |
| MNA/Thévenin en lab JS | sin tests | **DO_NOT_MIGRATE** en F6 (MNA es fase posterior) |
| `math`/`sqrt` whitelist en `safe_dict` | idea sana | **REUSE_CONCEPT**: funciones permitidas explícitas en el evaluador seguro |

## Sistemes-de-Mesura (referencia)
KB de fórmulas con provenance + gate 100% retrieval (F0). Para F6 aporta el
requisito: **toda ecuación de ingeniería conserva source + provenance** (ya
política F1/F3). Sin código reutilizable directo (stdlib retrieval ≠ cálculo).

## Decisiónarquitectónica resultante
F6 = modelo + cálculo determinista con evaluador seguro propio (AST parser,
sin eval/exec/subprocess). Frontera F7 (motores externos tras
`SimulationBackend`: Null/Mock en F6) y F8 (GUM/MC/instrumentos) documentadas.
