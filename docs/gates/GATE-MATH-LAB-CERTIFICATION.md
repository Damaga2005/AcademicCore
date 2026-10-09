# GATE MATH LAB — Certificación

Fecha: 2026-10-09 · Rama: `main` · Fases: ML-0 … ML-22 (las 24 de §10) · Certificador: `pulido.py` (dominio, no la suite)

## Veredicto

**MATH LAB: CERTIFICADO CON LIMITACIONES DOCUMENTADAS.**

Las cuatro cosas que ML-11 debía cerrar son **comprobaciones que se ejecutan**, no afirmaciones:

| Frente | Comprobación | Resultado medido |
|---|---|---|
| Accesibilidad (§6) | `audita_accesibilidad` sobre el resultado de cada operación | **80/80 accesibles**; el modelo de gráficas no tiene campo de color |
| Rendimiento (§5.4) | `mide` con `time.perf_counter` contra un techo declarado | **0 fuera del techo** de 10 s |
| Determinismo | la misma entrada, dos veces | **0 no deterministas** |
| Documentación (§8.1) | `describe` vuelca valor + pasos + sello + hipótesis + gráfica | presente en las 80 |
| Certificación (§8.4) | `certifica` sobre **todas** las operaciones registradas | **80 comprobadas, 0 fallos, 0 sin muestra** |

Reproducir:

```python
from academic_core.domain.engineering.mathlab import pulido
print(pulido.certifica().texto())
# 80 operaciones comprobadas
```

Nada de lo anterior se afirma sin la evidencia de §5.

## 1. Qué es «certificar» aquí

Un requisito que nadie puede ver fallar acaba mintiendo solo — que es lo que pasó
con los huecos declarados de `MATH_LAB.md`, y por eso existe
`test_mathlab_huecos_documentados.py`. Por eso ML-11 no es una lista de
intenciones: `pulido.py` **recorre las operaciones registradas y falla si algo
no cuadra**. Si mañana alguien registra una calculadora nueva sin descripción
de gráfica o sin traza, esta certificación deja de pasar.

Vive en el **dominio** y no en `tests/` a propósito: una certificación que solo
existe dentro de la suite no certifica nada, porque la suite es lo que
certifica.

## 2. Accesibilidad (§6)

§6 pide «descripción textual de cada gráfica y no depender solo del color».

- **Descripción textual**: `Graph.description` es obligatorio; `Graph.describe()`
  genera la alternativa que lee un lector de pantalla, con el recorrido de cada
  serie. Una descripción vacía, o que solo repite el nombre de la serie, se
  **rechaza**: un lector de pantalla no puede usarla.
- **Nada depende del color**: la garantía no es una promesa, es que el modelo
  `Graph`/`Serie` **no tiene campo de color**. Se comprueba leyendo el modelo
  (`hasattr(Graph, "color")` es `False`), y hay una prueba que lo fija.
- **Nombre por serie**: una serie sin nombre no se sabe qué es al leerla.
- Se comprueba además que `len(xs) == len(ys)`: una serie descuadrada no se
  puede dibujar ni describir.

## 3. Rendimiento y determinismo (§5.4)

- `mide(operación, entrada, techo)` mide la llamada real con
  `time.perf_counter` y distingue **excedido** de «rápido». Con un techo de
  `1e-12` s el veredicto pasa a `discrepa`, que es lo que evita que un techo mal
  puesto se note como aprobado.
- **Determinismo**: la misma entrada calculada dos veces tiene que dar el mismo
  valor exacto y el mismo sello. Un motor con caché que devuelve cosas distintas
  según cuándo se llama no es verificable, y aquí se nota.

Medido sobre las 80 operaciones con su entrada canónica: **0 fuera del techo,
0 no deterministas**. La operación más lenta se sitúa holgadamente por debajo
del techo de 10 s que fija §5.4.

## 4. Documentación (§8.1, §8.4)

`describe(resultado, nivel)` vuelca el resultado **entero** como texto: valor
exacto, aproximación con su número de cifras, error acotado, sello con su
método y su detalle, hipótesis con su veredicto, convenciones, avisos y la
gráfica descrita. Es lo que se copia a otro laboratorio (§8.1) y lo que lee un
lector de pantalla. Respeta los tres niveles de detalle (`resumen`, `paso`,
`detallado`).

## 5. Los nueve criterios de §8.4, uno a uno

| # | Criterio | Cómo se comprueba | Resultado |
|---|---|---|---|
| 1 | Existe, con modo paso a paso y sello | `validar_forma` + traza no vacía | 80/80 |
| 2 | Ningún resultado sin segundo camino | sello `discrepa` ⇒ tiene que llevar aviso | 80/80 |
| 3 | Los pasos nombran la regla y el porqué | al menos un paso con `why` **en las familias que §8.4 nombra** | cumple en las 12 |
| 4 | Cambios de variable con su(validación) | **no se comprueba**: es de juicio | fuera |
| 5 | Se puede pedir por programa | todo pasa por `contract.calcular`, sin interfaz | 80/80 |
| 6 | Sin solución exacta se avisa | `solo_numerico` ⇒ el sello dice por qué | 80/80 |
| 7 | Convenciones declaradas y verificadas | `validar_forma` las valida | 80/80 |
| 8 | Cumple el contrato de §5.9 | `validar_forma` entero | 80/80 |
| 9 | Bloques E antes que G, ninguno recortado | **no se comprueba**: es de orden de entrega | fuera |

**Sobre el criterio 3.** §8.4 solo lo exige a derivar, integrar, límites,
series, EDO y transformadas. Aplicarlo a las 80 sería inventarse un criterio
más estricto que el del documento, y **hacer fallar la certificación por algo
que la norma no pide sería una forma elegante de mentir**. Las que lo cumplen
por hoy; las otras cinco se reportan como **mejora pendiente**, ni como buenas
ni como malas:

`grafo`, `metodo_numerico`, `proceso`, `teorema`, `variable_aleatoria`.

## 6. Evidencia

- `tests/test_mathlab_ml11.py`: 24 pruebas.
- La propia prueba `test_la_certificacion_pasa` ejecuta `certifica()` sobre las
  80 operaciones y exige 0 fallos: si el motor se rompe, **la batería lo nota**.
- `test_toda_operacion_registrada_tiene_muestra_canonica` obliga a que
  `pulido.MUESTRAS` cubra todo `C.operaciones()`: una operación sin muestra se
  contaría como «sin muestra», no como buena.
- Suite completa del laboratorio: en verde por bloques.

## 7. Lo que NO se certifica aquí (y por qué)

- **La interfaz**: el visor Qt (§6, §9) es de otra capa. Aquí se certifica que
  la **gráfica descrita como dato** es accesible; que el widget lo pinte bien es
  del gate de UX, y su lector de pantalla sigue sin ejecutarse allí.
- **Los criterios 4 y 9**: son de juicio y de orden de entrega, no de forma.
- **El rendimiento de la interfaz**: aquí se mide el dominio. Pintar 80 gráficas
  es otra historia.
- **Las figuras leídas del enunciado** (§7): la aplicación no lee imágenes, y
  ML-10 lo niega con motivo.
- **El enlazado al banco D6 y a la maestría** (§7): el corrector comparte
  principio —determinista, el modelo nunca califica— pero el enlace no está.

## 8. Commits

| Fase | Commit |
|---|---|
| ML-0 … ML-22 (núcleo y bloques v2) | `8358789`, `1555970`, `f30ca5c` |
| ML-10 ejercicios, corrector y generador | `f30ca5c` |
| ML-11 el pulido (este gate) | ver `git log -1` |

## 9. Cierre

Las 24 fases de §10 están implementadas. El motor es puro (sin NumPy, sin
`eval`/`exec`, sin dependencias nuevas en el dominio), cada resultado lleva
segundo camino y sello honesto, y lo no demostrable se niega con motivo en vez
de inventarse.