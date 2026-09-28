# F16 — Contenido Aeroespacial / Satélite (mecánica orbital básica)

> **Fase:** F16 (última del roadmap) · **Motor:** `f16-orbital/1` ·
> **Estrategia:** two-body determinista en Decimal, sin CRDT, sin segundo
> motor de nada, sin IA como autoridad.

## 1. Alcance

Mecánica orbital básica del problema de dos cuerpos, pedagógica y
verificable:

- modelo gravitacional con provenance (`G` CODATA 2018, Tierra IAU/IERS);
- órbita circular (v, T, r↔h) y periodo con inversa exacta;
- vis-viva (velocidad e inversa al semieje);
- energía (cinética, potencial, total, específica);
- velocidad de escape;
- elipses ligadas (`a`, `e`, periapsis, apoapsis, 0 ≤ e < 1);
- ecuación de Kepler (M↔E con Newton acotado, ν↔E cerradas);
- elementos clásicos (`a e i Ω ω ν` + marco) con digest `f16-elements/1`;
- trazas `physics.orbital` (E0) y helpers de conversión SI explícitos.

Fuera de alcance (§27 del prompt): propagación de alta fidelidad, J2,
arrastre, radiación, N-body, maniobras, actitud, GPS, 3D, TLE, APIs
externas, nuevo LLM.

## 2. Relación con lo existente

```text
F8-P5 Satcom (link-budget, d como ENTRADA)
   + F16 orbital (de dónde sale d, cómo se mueve el satélite)
   = cadena completa, sin duplicación
```

- `math/` (precisión 50, sqrt/cbrt/trig/pi): reutilizado, no duplicado.
- `units.py`: extendido aditivamente (MASS/FORCE, g/N/rad + alias). Sin
  factores no decimales en el parser (min/h/day/deg quedan como helpers
  explícitos F16 para no introducir conversiones silenciosas).
- `correction.py` (F9): reutilizado sin cambios (preguntas `numeric`).
- `ingestion.py` (D7): no se toca (sin filas Knowledge nuevas).
- `ExplainService`: dos métodos + una rama de replay (aditivo).
- Errores: `ControlError/ControlStatus` existentes (INVALID,
  MAX_ITERATIONS); sin códigos AC nuevos.

## 3. Modelos y ecuaciones

| Magnitud | Fórmula (único lugar) |
|---|---|
| `r = R + h`, `h = r − R` | `orbits.radius_from_altitude_m`, `altitude_from_radius_m` |
| `v = √(μ/r)` | `orbits.circular_velocity_m_s` |
| `T = 2π√(r³/μ)`, `r = ∛(μ(T/2π)²)` | `orbits.circular_period_s`, `radius_from_period_m` |
| `v² = μ(2/r − 1/a)` + inversa | `orbits.vis_viva_*` |
| `K = mv²/2`, `U = −mμ/r`, `E = K+U`, `ε = E/m` | `orbits.{kinetic,potential,total,specific}_*` |
| `v_esc = √(2μ/r)` | `orbits.escape_velocity_m_s` |
| `rp = a(1−e)`, `ra = a(1+e)` + inversa | `orbits.{periapsis,apoapsis,ellipse_from_apsides}_m` |
| `M = E − e·sinE`, Newton acotado | `kepler.mean_from_eccentric_rad`, `eccentric_from_mean_rad` |
| `ν ↔ E` cerradas | `kepler.true_from_eccentric_rad`, `eccentric_from_true_rad` |

Convenciones: `r` desde el centro, `h` sobre la superficie (nunca
mezclados); ángulos en radianes Decimal; `frame ∈ {ECI, ORBITAL}` sin
transformaciones (el tag evita mezcla silenciosa).

## 4. Unidades y precisión

SI base (m, kg, s, rad) en Decimal; contexto de 50 dígitos vía
`make_context()` (nunca el contexto ambiente). Newton (Kepler, cbrt)
con tolerancia explícita (1E-40 relativo) y presupuesto (200/500
iteraciones); `MAX_ITERATIONS` si no converge. `r` bajo superficie,
`e ∉ [0,1)`, valores no finitos/no Decimal/bool: rechazados, nunca
clamps ni defaults mágicos.

## 5. Constantes y provenance

`orbital/constants.py`: `G = 6.67430E-11` (CODATA 2018), Tierra
`M = 5.97237E24 kg`, `R = 6371000 m`, `μ = 398600441800000 m³/s²`
(IERS; `μ = G·M` es la única derivación y vive en
`gravitational_parameter`). Cada cuerpo (`CentralBody`) exige
`provenance` no vacío.

## 6. Casos conocidos (tests)

- ISS (h ≈ 420 km): v ≈ 7668 m/s, T ≈ 92–93 min.
- GEO: T = 86164.0905 s → h ≈ 35786 km.
- Escape terrestre: ≈ 11.186 km/s.
- Molniya-like (rp 7000 km, ra 42000 km): vis-viva > circular en rp;
  inversión al semieje exacta al metro.
- Kepler: M↔E↔ν round-trip a 1E-25.

## 7. Límites reales

1. Two-body puro (sin J2/arrastre/radiación/N-body).
2. `min/h/day/deg` no son unidades del parser (helpers explícitos).
3. Sin E2E contra efemérides reales (sin TLE; no se finge).
4. `ORBITAL` es etiqueta de marco, no transformación implementada.
