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
  Los seis: `malla_simple`, `doble_malla`, `divisor_cargado`, `puente_equilibrado`, `puente_desbalanceado`, `rc_escalon`. Los cinco primeros se resuelven en forma cerrada exacta (con Gauss en la doble malla) y el sexto con `Decimal` de 50 dígitos. Los cinco pasivos se contrastan con el MNA de producción; el RC es de primer orden y lo resuelve `f8l`.
| `test_eng_security` ampliado | ✔ | 5 pruebas nuevas: sin `eval`/`exec`/`subprocess`, sin reloj ni azar ni fichero, inyección rechazada |
| Determinismo (P1) | ✔ | Misma entrada, mismo `digest`, comprobado en las pruebas |

**96 pruebas** en `tests/test_mathlab_circuits_ci0.py` + 5 en `tests/test_eng_security.py`.

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

## 1 bis. El banco canónico, contrastado con el motor de producción

Un banco de regresión que se comprueba a sí mismo no comprueba nada. Esta vuelta ha montado los **mismos circuitos** con el modelo `circuit.Circuit` de producción y los ha resuelto con `mna.solve_linear_dc`, y ha comparado las trece magnitudes con las del banco. Trece coinciden, dentro de los 28 dígitos con que el MNA presenta (resuelve exacto por dentro; el decimal es de presentación).

**Y en el primer cruce encontró un error real: el canónico `doble_malla` tenía el signo del 3 Ω común cambiado.**

| | Lo que decía el banco | Lo correcto |
|---|---|---|
| Ecuaciones | 7·i₁ − 3·i₂ = 12, −3·i₁ + 9·i₂ = 6 | 7·i₁ + **3**·i₂ = 12, **3**·i₁ + 9·i₂ = 6 |
| Motivo dado | «la resistencia común aparece con el signo contrario porque las dos corrientes la cruzan en sentidos opuestos» | las dos corrientes **vuelven** por el 3 Ω **en el mismo sentido** y se suman |
| i₁, i₂ | 7/3, 13/9 | 5/3, 1/9 |
| KCL en el nodo central | entra 34/9 A, sale 8/9 A → **la viola** | entra 5/3 + 1/9 = 16/9, sale 16/9 |
| Balance de potencias | — | 20 + 2/3 = 62/3 = 100/9 + 2/27 + 256/27 |

El motivo dado era cierto en **otra** topología (la del resistor común entre los dos puntos medios, que sí es de libro) y falso en la que el banco resolvía. Lo que lo hace grave es que **el canónico se autocomprobaba y pasaba**: la autocomprobación usa el mismo criterio equivocado, así que no puede verlo. Solo el cruce con una implementación independiente lo cazó, a la primera.

Ahora hay seis pruebas que contrastan el banco con el MNA, y una que comprueba KCL sobre la doble malla por si alguien vuelve a cambiar el signo.

## 2 bis. Revisión de robustez (segunda vuelta)

Se auditó el bloque buscando fallos propios, no fallos de los datos: se intentó tumbar cada comprobación con entradas degeneradas (`float`, ceros, listas vacías, `ref` que no existen, sellos mal escritos) y se revisó a mano la notación de entrada. **Se encontraron trece defectos más, todos en código que se presenta como garantía.**

| # | Defecto | Por qué importa |
|---|---|---|
| 6 | **`1R2` devolvía 12 Ω en vez de 1,2 Ω.** En la notación de la serie E la letra es el punto decimal y la `R` vale por uno, no por diez. Y la prueba que lo cubría **fijaba 12 como si fuera lo correcto** | Un factor diez en una resistencia es un circuito que no funciona, y el error estaba ratificado por la propia batería: así es como un error se convierte en especificación |
| 7 | **`1m5` con unidad Ω devolvía 1,5 metros.** `m` es prefijo (mili) y unidad (metro) a la vez, y el lector ganaba el metro | No reventaba: devolvía un número plausible y equivocado. El peor tipo de fallo. Arreglado comparando por **dimensión**, no por «que no sea adimensional» |
| 8 | **Las invariantes aceptaban `float`.** El contrato los rechazaba, pero las invariantes eran una segunda puerta | Con `Fraction(0.5)` el valor sale exacto **por casualidad**, y esa casualidad es la que hace peligroso dejarlo pasar: otros valores sí pierden cifras y el residuo que se compararía es el del redondeo, no el del cálculo |
| 9 | **Un `Sello` con veredicto mal escrito se dibujaba con `?` sin avisar.** `ok` daba falso sin que nadie supiera por qué | Un sello con «verificado » (un espacio) o «Verificado» (mayúscula) es un error de tecleo, y sale como si el cálculo no estuviera verificado. Ahora el veredicto es lista cerrada y se rechaza al construirlo |
| 10 | **El mensaje decía «picos amortiguados» de una oscilación de amplitud constante** | Afirmar algo que no se ha comprobado es el mismo fallo que el resto del laboratorio evita. Una oscilación marginal ahora sale como **no comprobada** |
| 11 | **Una regla de región para un dispositivo que no está se ignoraba en silencio** | Un `ref` mal escrito dejaba la comprobación sin hacer y sin decir nada. Mismo arreglo en `dimensiones` para una magnitud esperada sin nombre que coincida |
| 12 | **Los balances de potencia del banco canónico eran `[0]` contra `[0]`** | `[0]` contra `[0]` es la rama de «red sin fuentes», y los seis circuitos **tienen fuentes**: la comprobación se daba por buena sin mirar nada. Ahora cada circuito declara sus potencias reales y el balance cierra a cero exacto (probado sin holgura) |

| 13 | **Cuatro de las seis comprobaciones revientaban con `OverflowError` en valores enormes.** Todos los `float(x)` estaban **dentro de los mensajes de error**, y `float(10**500)` lanza | El diagnóstico es el producto: una comprobación que revienta al intentar explicar por qué falló entrega un traceback en vez del motivo, y el motivo es justo lo que hacía falta. Con 10⁵⁰⁰ W el estudiante se queda sin respuesta |
| 14 | **`canonicos.py` decía tener un resolutor de nodos por Kron y no lo tiene** | Afirmar una capacidad que el código no tiene es el mismo fallo que se le critica a un sello. Corregido, y hay una prueba que comprueba que la afirmación y el código no se separan |
| 15 | **El `valor` de un `Resultado` aceptaba `float`**, con lo que P1 tenía tres puertas y dos abiertas | Un resultado con float tiene un digest que **no corresponde al cálculo que se haría al reproducirlo**, y dos resultados iguales darían distinto por un redondeo que nadie ve |
| 16 | **`magnitud("5", "ΩΩ")` decía «escríbelo con la unidad ΩΩ»** | Una ayuda que repite el nombre roto no ayuda. Ahora dice que la unidad no existe y enseña una buena |
| 17 | **Había dos ayudas de precisión que prometían 50 dígitos y no los daban**: `contexto()` devolvía el ambiente sin tocar y `con_precision()` no la llamaba nadie. `decimal(1/3)` dividía con 28 | Un tercio a 28 cifras pierde las últimas 22 sin avisar, y en un cálculo que luego se compara con otro de la misma familia el fallo se propaga en silencio. Ahora es un gestor de contexto que se usa |

Además: el `digest` no incluía las hipótesis ni la validez, y dos resultados con el mismo número y distinto «válido si x > 0» compartían identificador. Un `float` en el digest no era detectable, y `dimensiones` ignoraba en silencio una magnitud esperada cuyo nombre no coincidera (mismo arreglo que en las regiones).

**Pruebas:** de 56 a 96. Cada defecto tiene la suya, y las que se pueden escribir al revés (que es donde están los fallos caros) están escritas en las dos direcciones: el RC normal, la oscilación amortiguada, la divergencia pura, la oscilación que se amplifica, la marginal y la serie corta.

Además de los casos patológicos, el criterio de estabilidad se prueba con **transitorios de libro de segundo curso** que no se parecen en nada a los que se ajustó al principio: RC cargándose y descargándose, sobreamortiguado, oscilación amortiguada larga, constante established, amplificación, divergencia exponencial, y una carga RC de 31 puntos de verdad. Un criterio que solo funciona con los casos con los que se escribió no está probado. Cada defecto tiene la suya, y las que se pueden escribir al revés (que es donde están los fallos caros) están escritas en las dos direcciones: el RC normal, la oscilación amortiguada, la divergencia pura, la oscilación que se amplifica, la marginal y la serie corta.

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

1. **No comprueba que el «por qué» sea bueno, y el caso de `doble_malla` demuestra que eso no es un detalle.** El motivo equivocado no era un texto feo: producía un número equivocado que **se autocomprobaba y pasaba**. Un «por qué» falso no es documentación incorrecta, es un cálculo incorrecto con explicación. Por eso el banco se contrasta ahora con una implementación independiente, y no basta con que el motivo exista: tiene que ser el de **esta** topología. Se verifica que cada paso tenga motivo, no que la razón escrita sea la correcta. Es texto escrito a mano y sigue siendo la principal fuente de error del laboratorio.
2. **El banco canónico cubre 6 circuitos de los ~35 de §20.4**, y sólo los resolubles en forma cerrada exacta. Los de dispositivos (BJT, MOSFET, zener, op-amp, conmutadores) llegan con CI-9, que trae los modelos.
3. **El invariante 9 (segundo camino) no lo comprueba `invariantes.py`**: lo recibe como un booleano de quien llama, porque aquí no se puede repetir el cálculo por otra vía sin saber cuál era. La siguiente fase (CI-1) es la que tiene que empezarlo.
4. **`mallas` se espera como lista de caídas de tensión por malla, no como una lista de mallas del esquema.** La topología real la trae CI-1; aquí la comprobación es sobre los números que le pasan.
5. **`estabilidad` no sustituye a un análisis de polos.** Mira la forma de la respuesta y detecta la divergencia **exponencial**; el crecimiento lento y sin límite, como √t, se le escapa porque sus pasos se acortan igual que en un asentamiento. Un sistema con un polo real positivo cuya respuesta esté recortada por la simulación también podría pasar. Lo afina CI-2 con el criterio de Routh-Hurwitz.
6. **`Validez` se comprueba, pero cada calculadora decide su condición.** La clase comprueba; el contenido es responsabilidad de quien la rellena.
7. **No hay puerta de entrada desde la aplicación ni pestaña de UI.** CI-0 es dominio puro, como debe ser. La primera calculadora de CI-1 es la que expondrá la primera pantalla.
8. **CI-R está pendiente** (decisión 7 de §21.2.2). Este paquete viaja con el renombrado sin cambios.
9. **La suite completa tiene un test de rendimiento ajeno que falla en esta máquina** (`test_academic_perf`: 20,46 s contra un techo de 20 s). No lo ha causado este bloque —no toca `academic`— y se ha medido antes y después sin diferencia; queda anotado como preexistente, que es lo que §21.1.1 pide.
