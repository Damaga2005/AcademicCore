# Gate: CI-0 Cimientos del laboratorio de circuitos

Fecha: 2026-10-09 · Spec: `docs/labs/CIRCUITS_LAB.md` §14.1, §20.2, §20.4 · Código: `src/academic_core/domain/engineering/circuits/`

Este gate **no certifica el laboratorio de circuitos**: certifica sus cimientos, y ni siquiera todos. **CI-0 va a medias: 4 de sus 6 entregables.** Faltan el catálogo de ecuaciones con unidades y validez, y el formato `circuits/1` (B.1). No hay ninguna calculadora de circuitos todavía. Lo que se certifica es que las cuatro piezas hechas hacen lo que prometen, y que fallan a propósito cuando no.

## 1. Veredicto

| Criterio | Estado | Cómo se comprueba |
|---|---|---|
| Contrato §14.1 completo y en código | ✔ | `contrato.py`; los ocho puntos del contrato son funciones comprobables, no comentarios |
| Entrada con unidades estricta (§14.1.1) | ✔ | `test_la_magnitud_se_lee_como_la_escribe_uno` (7 formas), `test_una_magnitud_que_no_se_entiende_dice_como_escribirla`, `test_el_vacio_se_rechaza` |
| Convención declarada, nunca supuesta (§14.1.2) | ✔ | `test_la_convencion_se_declara_o_no_se_calcula`, `test_una_convencion_inventada_no_pasa` |
| Resultado con pasos y motivo (§14.1.3) | ✔ | `test_una_traza_explica_el_metodo_o_no_explica_nada`, `test_el_resultado_se_puede_ensenar_completo` |
| `float` prohibido en el dominio (P1) | ✔ | `test_un_float_se_rechaza_explicando_como_escribirlo`, `test_un_float_no_pasa_ni_disfrazado_de_booleano` |
| Segundo camino y sello (§14.1.5) | ✔ | `test_el_segundo_camino_es_un_invariante_mas` |
| Rango de validez declarado y comprobado (§14.1.6) | ✔ | `contrato.Validez` con tres estados; comprobado en `Validez.linea()` |
| Salida enviable y reproducible (§14.1.7) | ✔ | `test_el_digest_solo_cambia_cuando_cambia_el_calculo`, `test_el_digest_tambien_cambia_si_cambia_el_valor` |
| Nueve invariantes ejecutables (§20.2) | ✔ | `invariantes.py`; cada una tiene prueba de caso bueno **y** de caso malo |
| «No comprobado» es tercer estado | ✔ | `test_una_serie_corta_no_se_declara_verificada`, `test_una_region_sin_inecuacion_evaluada_no_se_declara_comprobada`, `test_lo_sin_comprobar_se_cuenta_aparte` |
| Informe vacío no certifica nada | ✔ | `test_un_informe_vacio_no_pasa` |
| Banco canónico con solución conocida (§20.4) | ✔ (6 de la lista de §20.4) | `canonicos.py` con resolutor propio; `test_los_circuitos_canónicos_son_consistentes_por_construccion` |
| `test_eng_security` ampliado | ✔ | 5 pruebas nuevas: sin `eval`/`exec`/`subprocess`, sin reloj ni azar ni fichero, inyección rechazada |
| Determinismo (P1) | ✔ | Misma entrada, mismo `digest`, comprobado en las pruebas |

**56 pruebas** en `tests/test_mathlab_circuits_ci0.py` + 5 en `tests/test_eng_security.py`.

### Entregables de CI-0 que faltan

| Entregable | Estado | Por qué no bloquea |
|---|---|---|
| Catálogo de ecuaciones con unidades y validez | Pendiente | Es catálogo de datos. El contrato ya sabe declarar la validez (`contrato.Validez`); lo que falta es la lista de fórmulas |
| Formato `circuits/1` (B.1) | Pendiente | Serialización de esquemáticos. Depende del `SchematicDoc` de CI-4, así que estaba mal colocado en CI-0 en el spec |

## 2. Las cuatro cosas que este bloque sabe hacer y las anteriores no

1. **Lee lo que se escribe en un papel.** `4k7`, `4,7 kΩ`, `1R2`, `2u2F`, `4.7e3` dan la misma magnitud. Sin esto, quien escribe como escribe en la libreta recibe un error que no se parece a nada que haya escrito, y busca el fallo en su código en vez de en sus datos.
2. **`float` se rechaza en la puerta.** Un `float` que entra ya ha perdido precisión antes de llegar; se dice ahí, con el motivo y la forma buena de escribirlo, en vez de arrastrar el error por veinte operaciones.
3. **Lo que no se ha comprobado se ve.** Es la diferencia entre un informe que certifica y uno que aparenta certificar.
4. **La referencia no depende del código probado.** El banco canónico tiene su propio resolutor. Si no, un error común a los dos pasaría inadvertido, que es el peor fallo posible en un banco de regresión.

## 3. Bugs encontrados por el propio bloque

Cinco, y cuatro estaban en los controles, que es donde más daño hacen porque se presentan como la garantía:

| # | Bug | Por qué importa |
|---|---|---|
| 1 | KCL decía «sin nodos con corriente» cuando el nodo cuadrava exactamente: el peor residuo se quedaba sin registrar porque su valor inicial era 0 y la comparación era estricta | Una comprobación que se congratula de no haber mirado nada |
| 2 | `estable` aceptaba una divergencia pura (`1, 2, 4, 8, 16`): comparaba el final con su propio máximo, y en una señal creciente **el final es el máximo** | El fallo nunca podía detectar lo que decía detectar |
| 3 | Corregido lo anterior, `estable` declaraba **inestable un RC normal** (`0, 0,5, 0,8, 0,95, 1`) | Habría marcado como inestable el transitorio más corriente que existe |
| 4 | El canónico del RC mezclaba kΩ y ohmios: `R·C` con 1 Ω y 1 µF daba τ = 1 µs en vez de 1 ms | Un banco de regresión con un valor mal puesto certifica el error |
| 5 | `5(1−1/e)` esperado, calculado a mano, no coincidía con los 50 dígitos del motor | **Tenía razón el motor.** Quinta vez que ocurre en este repositorio |

La secuencia 2 → 3 es la razón de que exista la prueba `test_la_estabilidad_acepta_un_rc_normal`: sin ella, la corrección del bug 2 habría metido un error nuevo.

## 4. Límites honestos

Lo que este bloque **no** hace, dicho sin adornos:

1. **No comprueba que el «por qué» sea bueno.** Se verifica que cada paso tenga motivo, no que la razón escrita sea la correcta. Es texto escrito a mano y sigue siendo la principal fuente de error del laboratorio.
2. **El banco canónico cubre 6 circuitos de los ~35 de §20.4**, y sólo los resolubles en forma cerrada exacta. Los de dispositivos (BJT, MOSFET, zener, op-amp, conmutadores) llegan con CI-9, que trae los modelos.
3. **El invariante 9 (segundo camino) no lo comprueba `invariantes.py`**: lo recibe como un booleano de quien llama, porque aquí no se puede repetir el cálculo por otra vía sin saber cuál era. La siguiente fase (CI-1) es la que tiene que empezarlo.
4. **`mallas` se espera como lista de caídas de tensión por malla, no como una lista de mallas del esquema.** La topología real la trae CI-1; aquí la comprobación es sobre los números que le pasan.
5. **`estabilidad` no sustituye a un análisis de polos.** Mira la forma de la respuesta. Un sistema con un polo real positivo y una respuesta recortada por la simulación podría pasar; se documenta para que CI-2 lo afine con el criterio de Routh-Hurwitz.
6. **`Validez` se comprueba, pero cada calculadora decide su condición.** La clase comprueba; el contenido es responsabilidad de quien la rellena.
7. **No hay puerta de entrada desde la aplicación ni pestaña de UI.** CI-0 es dominio puro, como debe ser. La primera calculadora de CI-1 es la que expondrá la primera pantalla.
8. **CI-R está pendiente** (decisión 7 de §21.2.2). Este paquete viaja con el renombrado sin cambios.
9. **La suite completa tiene un test de rendimiento ajeno que falla en esta máquina** (`test_academic_perf`: 20,46 s contra un techo de 20 s). No lo ha causado este bloque —no toca `academic`— y se ha medido antes y después sin diferencia; queda anotado como preexistente, que es lo que §21.1.1 pide.
