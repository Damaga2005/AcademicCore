# Changelog

## 2026-10-05 — `taylor` era la puerta más débil a una serie que el módulo ya sabía

**Cerrar la cota de T-19 dejó a la vista algo peor que la cota.** La misma función
tenía dos entradas al mismo polinomio y sólo una funcionaba: `taylor(tan(x), 0, 4)`
moría con `EXPRESSION_LIMIT` mientras `maclaurin("tan", 4)` devolvía la serie, y
`ln` alrededor de 1 topaba en el orden 4 de 40.

| | antes | ahora |
|---|---|---|
| `taylor(tan(x), 0, n)` | orden 3 | orden 40 |
| `taylor(ln(x), 1, n)` | orden 4 | orden 40 |

No era una limitación del método sino de la puerta. `tan' = 1/cos²` y
`ln^(k) = (k-1)!/x^k`: derivar cualquiera de las dos expande un producto de
potencias en cada paso, el registro guarda todos los intermedios, y el campo de 2000
caracteres se agota antes de que la matemática llegue a nada interesante. Escribir
los números tangentes o los términos de Mercator no tiene ese problema. Ahora una
función conocida se **escribe** en `taylor` en lugar de derivarse, y donde ambas
puertas podían calcularse coinciden exactamente — 48 combinaciones de polinomio,
residuo y cota sobre seis funciones, **0 diferencias**.

**La trampa que cruzó la delegación, y la alarma que la vigila.** Delegar en el
origen hacía que `taylor(ln(x), 0, n)` contestara `x − x²/2 + x³/3 − …` a una
pregunta sobre `ln`: la serie era correcta, de `ln(1+x)`. `maclaurin("ln", n)` es la
de Mercator, una rareza deliberada de ese nombre; `taylor(ln(x), 0, n)` promete el
polinomio de Taylor de `ln` en 0, y ahí no existe. Antes se negaba con «`ln(0)` no es
un número» y esa negativa era la respuesta correcta. Sigue negándose.

**Otra mentira que salió en el paseo.** La hipótesis anunciaba «radio de
convergencia 1» para `tan` y para `ln`, cuando el de `tan` es π/2. Tres líneas más
abajo, una tabla del mismo módulo decía π/2 correctamente: las dos afirmaciones
coexistieron sin que nadie las leyera una contra otra. Era falso en la dirección que
prohíbe una serie que converge — entre 1 y 1,57 la serie de `tan` suma bien, y el
motor lo negaba.

**La misma puerta, un orden menos.** `maclaurin('exp', -1)` siempre se negó con «el
orden tiene que ser 0 o mayor»; `taylor(exp(x), 0, -1)` contestaba un polinomio de
`0` con residuo `1`, que como aritmética se sostiene y como respuesta no sirve. Dos
respuestas a la misma pregunta. Ahora las dos puertas usan el mismo juicio y las
mismas palabras.

## 2026-10-05 — Las dos de las tres cotas que el motor declaraba no eran cotas

**T-19 queda COMPLETADA.** Su límite era uno solo: la cota de error cuando no hay
cota sobre la derivada omitida. Al cerrarlo resultó que la regla que llenaba ese
hueco —«el primer término omitido es la cota», con `None` para las cuatro series
restantes— no era ni muy cierta ni muy honesta.

**Las siete series ahora llevan cota, por un mecanismo y no siete.** La cola de la
serie se mayeriza término a término con una progresión geométrica construida de sus
propios coeficientes. Si `m` es la primera potencia no escrita:

| serie | razón | válida para |
|---|---|---|
| `sin`, `cos`, `sinh`, `cosh` | `\|x\|²/((m+1)(m+2))` | `\|x\| < √((m+1)(m+2))` |
| `exp` | `\|x\|/(m+1)` | `\|x\| < m+1` |
| `tan` | `\|x\|²/2` | `\|x\| < √2`, dentro del radio π/2 |
| `ln` | `\|x\|` | `\|x\| < 1`, su radio de convergencia |

Cada cota viaja con su dominio y con el argumento que la sostiene, leído en
`serie.hipotesis`: una cota sin dominio es un número, y un número sin dominio es
una promesa que nadie puede comprobar. La razón de `tan` es sound porque
`RAZON_TANGENTES = 1/2` **se comprobó** en aritmética racional exacta para todos los
coeficientes que el módulo puede escribir, no porque `4/π²` se parezca a un medio.

**Los dos fallos, y dónde estaban.** Los dos en el semiplano negativo y en el
argumento grande, que es donde nadie muestreaba:

- `sin` y `cos`: la estimación alternante exige que los términos **decrezcan**, y
  `x⁹/9!` deja de decrecer pasado `x ≈ 8`. Para un argumento grande la cota
  declarada era menor que el error real y se imprimía como cota superior.
- `ln`: la serie de Mercator alterna **sólo para `x > 0`**. En `x < 0` todos los
  términos son negativos, la cola es monótona, y el primer término omitido es cota
  **inferior**. En `x = -0,9` con cinco términos el motor declaraba `0,0886` para un
  error de `0,4725`. La prueba anterior sólo miraba `x > 0`, que es donde no falla.

**Lo que se niega sigue negándose, por una razón medida.** `taylor` de una
expresión que no reconoce no declara cota. El atajo —ver `exp` dentro de `x²·exp(x)`
y reusar su cota— está disponible y es falso: el error real sale **20 a 26 veces
mayor** que la cota que ese reuso adjuntaría. Lo que cambió es que `taylor` de una
de las siete funciones conocidas **sí** acota, y lo hacía por una razón que ya no
existe: `taylor(exp(x), 0, 6)` llevaba `cota = None` mientras el módulo acotaba esa
misma cola por `maclaurin`.

**La alarma cambió de pregunta.** `test_las_series_no_alternantes_no_declaran_cota_inventada`
comprobaba que cuatro funciones no declararan cota. Comprobar que un número existe
es más débil que medir si acota, y no habría visto ninguno de los dos fallos de
arriba —los habría dejado pasar. La sustituta mide `|exacta − polinomio| ≤ cota` en
546 puntos, con los negativos incluidos, y además comprueba que la cota no sea vacía.

**Un borde encontrado de paso:** `mx.text` imprimía un `Fraction` desnudo pero no un
`int`, así que `taylor(poli, 0, 9)` —tal como lo escribe una persona— moría con «no
se sabe imprimir int» desde cuatro marcos de `as_poly` más abajo. Se acepta el `int`
en `_print`/`_prec` y `taylor` normaliza el centro en la frontera. Un primer intento
añadió un guardia que **rechazaba** los números en `text`; rompió nueve pruebas y
era lo contrario de lo cierto: `exact_value` devuelve un `Fraction`, y el contrato de
`text` es imprimirlo.

## 2026-10-04 — `u⁴+1` era un biquadrático, y el tercer límite de T-18 era una clase

**T-18 queda COMPLETADA.** Los tres límites que le quedaban se cerraron, y ninguno de
los tres era una función que faltara: eran tres clases que el motor no reconocía.

El último era el que la documentación llevaba años diciendo: «un denominador de
grado 4 sin raíz racional no se sabe partir en dos cuadráticas sobre ℚ». Eso es
cierto —y es también la razón por la que el motor no lo intentaba— pero la frase
escribe mal el motivo. `∫du/(u⁴+1)` se negaba porque `_factores` **solo miraba
raíces racionales**, y un biquadrático no tiene ninguna que encontrar. Se parte:

    u⁴ + a·u² + c  =  (u² + p·u + q)(u² - p·u + q)    con  q = √c  y  p² = 2q - a

| | antes | ahora |
|---|---|---|
| `∫du/(u⁴+1)` | se negaba | `√8/8·log\|(u²+√8·u+1)/(u²-√8·u+1)\|` |
| `∫du/(u⁴+u²+1)` | se negaba | cerrada, con factores racionales |
| `∫du/(u⁴-6u²+1)` | se negaba | cerrada, con `m<0` y por tanto logaritmos |
| `∫dx/(cos x·cos 2x)` | se negaba | cerrada vía `(u²-1)(u⁴-6u²+1)` |

Verificado **derivando** en 81 puntos por caso: error máximo 1,2·10⁻²⁶.

### Por qué no hizo falta aritmética de cuerpos

Esto es lo que parecía el obstáculo y no lo era. Con un numerador `(Au²+C)` sobre
el cuartico, el reparto en dos cuadráticas da `α = (C/q - A)/(2p)` y
`β = C/(2q)`, y al integrar los términos se agrupan como

    (α/2)·log\|Q₊/Q₋\|  +  (β - α·p/2)·(I₊ + I₋)

y **`β - α·p/2` se simplifica a `(A + C/q)/4`, que es racional**. De los dos
coeficientes, uno es racional y el otro es un racional partido por `√(p²)`. Con
`q = √c` exigido racional queda un solo radical, y `√(p²)·t` es un producto, no un
tipo nuevo. La condición no es estética: con `√c` irracional harían falta dos
radicales y el reparto ya no cabría en una expresión.

### Cuatro bugs propios, y los cuatro eran silenciosos

**El cover-up con numerador 1.** `∫dx/(cos x·cos 2x)` llega aquí con numerador
`-2(u²+1)²`, y la primera versión usaba `1` en dos sitios: `c = 1/[(den/(u-r))(r)]`
en vez de `num(r)/[…]`, y `1 - Σc·M` en vez de `num - Σc·M`. Es el caso de
manual, así que falló como una respuesta plausible y no como un rechazo.

**El cover-up sobre el resto en curso.** Se dividía el *resto* por `(u+1)` después
de haber sacado `(u-1)`, y eso da el cuartico donde cover-up quiere `den/(u+1)`. El
coeficiente salía `-1/4` donde era `+1/8`, y la división final no cerraba —por lo que
el caso se negaba por un motivo que no tenía nada que ver con su motivo real.

**El término de coeficiente cero.** La primera respuesta correcta del caso de
`cos` medía **318 caracteres**, y `expr.parse` corta en 256: correcta y no
relegible. La mitad del texto era un `0/4·(…)` que multiplicaba cero. Una respuesta
que el lector no puede teclear no es una respuesta, por muy exacta que sea; quitando
el término vanishes son 156.

**`Mul(Num(1), None)`.** La rama nueva multiplicaba el resultado interior sin
comprobar que no fuera `None`, y el agujero salió tres frames más tarde como
`'NoneType' object has no attribute 'left'` — un crash donde tocaba un rechazo.

## 2026-10-04 — Tres afirmaciones que mentían, y una invitación a no intentarlo

Tres líneas de `MATH_LAB.md` y `COVERAGE_CATALOG.md` decían cosas que el motor ya
no hacía. Dos eran **afirmaciones de capacidad** —«no hay motor de límites» y «el
polinomio de Taylor de un monomio lleva un término de más»— y una capacidad que no
se anuncia es una invitación a no intentarla: alguien lee que el motor no puede
hacer algo, no lo intenta, y la línea sigue ahí diciendo la verdad sobre nada.

| afirmación | realidad |
|---|---|
| «Asíntotas horizontales y oblicuas. **No hay motor de límites.**» | `mathlab/limites.py` existe. `asintotas_de_horizonte_y_oblicua` da `y = 1` para `(x²−1)/(x²+1)`, `y = 0` para `1/(x²+1)` y para `x/(x²+1)`, y **nada** para `(x²+1)`, que sí tiene |
| «el polinomio de Taylor de un monomio lleva un término de más, documentado en `test_mathlab_series`» | 8 monomios con orden por encima del grado: polinomio exacto y residuo exactamente 0. El propio `COVERAGE_CATALOG.md` ya lo decía — 168 combinaciones, 0 distintas de lo esperado— desde hacía tiempo. **`graficas.py` era el único sitio que aún lo afirmaba** |
| T-20: cuatro objetivos con «su porqué y **cero reglas**» | No tienen familias de reescritura porque **no reescriben nada**: devuelven una derivada, una primitiva, un complejo o un fasor. Lo que deben es un `porque` y un `verifica`, y los cuatro tienen ambos |

La primera es la que más cuesta. No es solo que la frase fuera falsa: es que
**usaba como excusa el mismo razonamiento que el módulo cumple**. Decía «muestrear
en un `x` grande no es un límite: un senoide da diez límites distintos en diez `x`
grandes», y `orden_en_infinito()` saca el orden de crecimiento **por grado
dominante, nunca por muestreo**. Alguien escribió ese argumento y luego no lo
conectó con el módulo que lo cumple.

### Cómo se evita la recaída

`tests/test_mathlab_docs_contra_motor.py` no comprueba el texto: **comprueba el
motor y lo compara con lo que la documentación afirma de él**. Si el motor cambia
y la frase no, la prueba falla y obliga a decidir cuál de las dos estaba
equivocada, que es la decisión que no se puede tomar por omisión.

Una sutileza que costó un test: la etiqueta corregida de T-20 **cita** «cero
reglas» para explicar que era otra cosa. Buscar la frase en crudo confundiría
«afirmar esto» con «explicar por qué se dejó de afirmar», que es exactamente la
diferencia entre una mentira y su corrección. Las comprobaciones ignoran lo que
va entre comillas angulares.

La guarda se comprobó a sí misma: reintroducir la mentira en `graficas.py` hace
fallar el test, y revertirla lo hace pasar.

## 2026-10-04 — `(u²+1)²` era una cuadrática, y el motor la tenía por un cuartico

**El último límite de T-18 que no era un límite.** De los tres que quedaban, dos
no eran fronteras del método sino un agujero en una función, y este era el más
interesante porque llevaba dos años diciendo una cosa y siendo otra.

`∫du/(u²+1)²` se negaba. El motivo que se registraba era «cuartico sin raíz
racional», y el motivo real era que `_factores` solo miraba raíces racionales.
`_como_racional` escribe `(u²+1)²` como `u⁴ + 2u² + 1`, y eso es un grado 4 sin
raíz racional; el motor lo veía, y un grado 4 sin raíz racional es la parte sin
resolver de este módulo. **El polinomio que llegaba nunca fue un cuartico**: era
una cuadrática escrita dos veces, y nadie había mirado a ver si lo era.

La respuesta a por qué no se miraba es la misma de siempre, y no es pereza: mirar
exige una descomposición squarefree, y eso es otro algoritmo.

| | antes | ahora |
|---|---|---|
| `∫du/(u²+1)²` | se negaba | `arctg(u)/2 + u/(2(u²+1))` |
| `∫(u+1)/(u²+1)²` | se negaba | `-1/(2(u²+1)) + arctg(u)/2 + u/(2(u²+1))` |
| `∫du/(u²+1)³` | se negaba | cerrada |
| `∫du/(u²+1)⁴` | se negaba | cerrada |
| `∫sen²x/(1+cos x) dx` | se negaba | cerrada |

`∫sen²x/(1+cos x) dx` no se arregló por separado: se negaba por lo mismo, porque
con `u = tg(x/2)` se convierte en `4u²/(1+u²)²`. Llegó al mismo sitio por otro camino.

Verificado **derivando** en 81 puntos por caso: error máximo 1,2·10⁻²⁷.

### La frontera no se movió, y eso es lo que hay que comprobar

`∫du/(u⁴+1)` se sigue negando. Ahora `∫du/(u⁴+1)²` también, pero **por el factor
de dentro** y no por parecer un cuartico, y esas dos negaciones eran
indistinguibles antes de este cambio. Un motor que empieza a responder «a veces»
es peor que uno que se niega, así que la prueba de la frontera comprueba las dos
mitades por separado.

La descomposición es la de Musser, exacta sobre `Fraction`, apoyada en
`_p_derivada` y `_p_mcd_polinomios`, que ya existían: faltaba un solo eslabón.
Cada división se comprueba con su resto, porque una descomposición squarefree que
no dividiera exactamente sería una respuesta equivocada sin camino de vuelta.

### Dos bugs que aparecieron al hacerlo

**`w = d` en vez de `w = d/c`.** Una inicialización de un carácter, y **no falla
en voz alta**: `gcd(d, c)` devolvía el factor propio de `d` en vez de 1, el primer
cociente salía con multiplicidad 1, y el resultado era `(u²+1)·(u²+1)²` — un
denominador de grado 6 para un polinomio de grado 4, con todos los coeficientes
del sistema de fracciones parciales equivocados a partir de ahí.

**`_p_potencia(p, -1)` devolvía `1`.** Su bucle es `range(max(0, n))`, así que
todo exponente negativo devolvía el producto vacío. La línea que lo invoca con
exponente negativo —`Q^(1-j)` en `_integral_pieza`, con `j ≥ 2`— era **la única**
así en todo el módulo, y era inalcanzable: solo se llega a ella con una cuadrática
irreducible repetida, que es exactamente lo que este commit introduce. El síntoma
era `∫(u+1)/(u²+1)² du` saliendo como `(-1/2)·1 + arctg(u)/2 + …`: un
`-1/(2(u²+1))` que había perdido el denominador. No un signo mal: un término
entero, y verificó bien durante las pruebas que no lo diferenciaron.

Las dos se encontraron midiendo, no leyendo. Las alarmas saltaron —que es justo
para lo que están— y las respuestas que quedaron mal se detectaron porque el
comprobador de este repositorio deriva la primitiva y la compara con el integrando,
no porque alguien las leyera.

## 2026-10-04 — `arctg` entra en el lenguaje, y lo que ya estaba dentro

**El cuarto límite de T-18 cerrado**, y no por añadir una función: por añadir un
**nombre** que hacía meses que el motor sabia usar y no sabía escribir.

La documentación de T-18 llevaba tiempo diciendo que a la capa `symbolic` le faltaba
la inversa trigonométrica. Eso era la mitad de la verdad. `atan` estaba en la tabla de
derivadas desde T-17 —el motor diferenciaba `arctg` sin dificultad—, y lo que no
existía era su sitio en la gramática del parser ni en la del evaluador. El integrador
llegaba hasta el final de la cuenta, escribía `Fn('atan', u)`, y se paraba ahí: una
traza que el lector no puede teclear no es una traza.

| | antes | ahora |
|---|---|---|
| `∫du/(u²+1)` | se negaba | `arctg u` |
| `∫1/(2+cos x)` | se negaba | `2/√3 · arctg(tg(x/2)/√3)` |
| `∫(2u+1)/(u²+1)` | se negaba | `ln(u²+1) + arctg u` |
| `∫du/(4u²+4u+2)` | se negaba | `arctg(2u+1)` |
| `∫du/(u²+u+1)` | se negaba | `2/√3 · arctg((2u+1)/√3)` |

Verificado **derivando** en 81 puntos por cada una, no leyendo el texto: el error
máximo es inferior a 1e-12. Un texto puede tener todos los términos bien escritos y el
signo de todos invertido, y por eso no se comprueba como texto.

### Tres listas escritas en tres sitios, cerradas a la vez

La gramática del parser, la whitelist del evaluador certificado y la tabla de kernels
son tres listas en tres ficheros distintos. Con una de ellas creciendo y las otras dos
quietas, el motor vuelve a poder imprimir algo que no sabe leer —que es exactamente el
fallo que esto vino a cerrar—, así que las tres se tocaron en el mismo commit:

- **`symbolic/expr.py`**: `FUNCTIONS` pasa de 7 a 23 nombres. La regla que gobierna la
  lista es ahora escrita: **todo lo que el motor imprime, el motor lo puede volver a
  leer**.
- **`math/trig.py`**: quince kernels nuevos, todos escritos como la identidad que los
  define sobre `sen`, `cos`, `exp` y `ln`. No hay una segunda serie en ningún sitio.
- **`engineering/equations.py`**: `ALLOWED_FUNCS` pasa de 8 a 23 y `ENGINE_VERSION` de
  `engcalc/6.0` a **`engcalc/6.1`**. Es un motor certificado bajo gate, y cambiarle el
  lenguaje se dice con un número de versión, no en la letra pequeña.

`tests/test_math_trig_family.py` compara las tres listas y vigila que no se separen.

### Dos opciones, y por qué se descarto la otra

`atan` **no** se puede escribir con el vocabulario que el evaluador ya tenía
(`sen cos tg exp log log10 abs`): no hay ninguna función inversa ahí, y `arctg` no es
una combinación de las demás. La primera idea era reescribir el nombre en
`numeric._evaluable`, que ya reescribe las potencias no enteras como `exp(r·log b)`, y
por ahí no pasaba: no hay a qué reescribirlo.

La descartada de verdad era la más rápida: ampliar `numeric.py` con una segunda
aritmética. `numeric.py` dice en su docstring que no hay «un segundo motor
aritmético», y razón tiene: un integrador que devuelve un número por un camino que
nadie ha verificado no es un integrador verificado.

### `getattr` en un módulo certificado

El reparto de nombres a kernels se resolvió primero con
`getattr(_trig, f"decimal_{nombre}")`, y el gate E0 lo rechazó:
`test_e0_x01_no_dynamic_execution` prohíbe `getattr`/`setattr` en `equations.py`. El
gate tenía razón y la tabla es ahora **literal** —quince entradas que se leen enteras—,
con la comparación contra `ALLOWED_FUNCS` en el test. Una tabla que se puede leer de
punta a punta es además la única forma de ver que todo nombre tiene kernel detrás: una
búsqueda por nombre calculado falla en la primera errata y en ningún otro sitio.

### Tres cosas que se encontraron por el camino

**Un bug vivo, no hipotético.** La regla de reducción de potencias impares de `tg`
emitía `Fn("ln", 1/cos(u))` mientras la tabla emitía `Fn("log", |cos u|)` para la primera
potencia: dos grafías de la misma función dentro del mismo módulo. La tabla se podía
leer y la reducción no. `∫tg³u du` imprimía una primitiva que no se podía teclear ni
verificar. Ahora el nombre es `log` —el único que tiene el lenguaje— y hay una prueba
que pasa por el texto y lo teclearía de vuelta, sobre las seis potencias.

**Un mensaje de dominio que señalaba a la función equivocada.** `acos` se construye
sobre `asin`, y el error de dominio nombraba a `asin`. Quien pedía `acos` recibía un
mensaje sobre una función que nunca mencionó. Los kernels de `math/trig.py` escriben
ahora la **condición** y nunca su propio nombre; el nombre lo compone el evaluador, que
es quien sabe cuál se llamó.

**Una prueba que se medía a sí misma.** Comparar un kernel contra `math` dio «errores»
de 2,2·10⁻¹⁶ relativo en quince funciones: era el error de la referencia `float`, no
del kernel. Peor: `acosh(1,0001)` salía con 5,5·10⁻¹⁴, unas 250 veces un ulp, porque
`1/√(x²-1) ≈ 70` amplifica el error del argumento float. Los kernels se comprueban
ahora contra literales exactos y contra identidades, y el invariante que decide es
`cosh(acosh x) == x`, que se sostiene a 1e-43.

### Lo que queda, que no es poco

Tres límites, y se niegan por tres motivos distintos, que conviene no confundir:

| hueco | por qué |
|---|---|
| `∫du/(u²+1)²` | `_como_racional` expande a grado 4 y `_factores` no reagrupa: falta la descomposición squarefree, que es otro algoritmo |
| `∫du/(u⁴+1)` | sin raíz racional: partirlo en dos cuadráticas sobre ℚ es un sistema que hay que resolver entero, y hacerlo a medias es como un integrador empieza a responder «a veces» |
| `∫sen²x/(1+cos x) dx` | el primero de los dos, alcanzado por `u = tg(x/2)`, que lo convierte en `4u²/(1+u²)²` |

Ninguno es una carencia del método: es no haber escrito una pieza. Y los tres tienen
su alarma, en `tests/test_mathlab_huecos_documentados.py`, en listas que **fallan** el
día que se cierren.

## 2026-10-04 — `t = tg(x/2)` en la integración, y lo que hacía falta debajo

**T-18 cerrado en su último punto abierto**, por la vía larga: un integrador de
funciones racionales por descomposición en fracciones parciales sobre ℚ. Ninguna de
las dos integrales que faltaban se negaba por falta de una fórmula: se negaba porque
**no había ninguna pieza de ellas escrita**.

| | antes | ahora |
|---|---|---|
| `∫dx/(1+cos x)` | se negaba | `tg(x/2)` |
| `∫dx/(cos x + cos 2x)` | se negaba | `-tg(x/2)/3 - 2/(3√3)·ln|(u-1/√3)/(u+1/√3)|`, `u = tg(x/2)` |
| `∫du/(1-3u²)` | se negaba | log, cerrada |
| `∫du/(u²-1)` | se negaba | `½ ln|u-1| - ½ ln|u+1|` |
| `∫du/(u²-1)²` | se negaba | `-u/(2(u²-1)) - ¼ ln|(u-1)/(u+1)|` |

Verificado **derivando** en 41 puntos de la recta, no leyendo el texto: el error
máximo en `∫dx/(cos x + cos 2x)` es 3.6·10⁻¹³.

### Lo que faltaba no era difícil, era un método

El motor leía `1/(au+b)` y `u/(1+u²)` — el denominador cuya derivada está en el
numerador — y se negaba en todo lo demás. Lo que no tenía era lo que convierte la
integración racional en **método** y no en lista: **factorizar el denominador sobre
ℚ y repartir**. `∫du/(1+u²)` no se negaba por difícil; se negaba porque no había
nadie escrito ninguna parte suya.

Cinco pasos, todos exactos: división entera, factorización sobre ℚ, el sistema por
igualación de coeficientes (hay tantas incógnitas como el grado del denominador, así
que es cuadrado), **Gauss-Jordan sobre `Fraction`** y la primitiva de cada trozo.

### Tres decisiones que parecían detalles y no lo eran

**Aritmética exacta, nunca un redondeo.** Un coeficiente que es 1e-18 en vez de 0 es
una respuesta equivocada tres pasos más allá, donde nada apunta de vuelta a aquí.

**El `abs` del logaritmo es de la respuesta, no del método.** Y `log|x|` se imprime
así porque es lo que se lee; el motor no tiene una entrada «log de un cociente».

**Un resto no es un factor, y el cociente no es el resto.** Los dos saltos de la
factorización están comentados en el sitio donde importan.

### Y el `arctg` que no se emite, que es la decisión de este commit

`∫du/(u²+1) = arctg(u)`. mathlab **deriva y evalúa** `arctg` sin problema, así que un
`Fn("arctg", u)` se habría **impreso** — y no se podría **volver a leer**, porque
`arctg` no está en la lista de funciones del parser de `symbolic`, ni en su tabla de
derivadas, ni en su evaluador numérico. Una traza que el lector no puede teclear no
es una traza, y una respuesta que no se puede volver a meter en el motor no es
comprobable por el mismo camino que las demás. **Se emite negación, no `arctg`.**

Es un límite, no un hueco del método: la descomposición funciona y lo que sale
necesita una función que la capa no tiene. Las dos listas de negaciones están
separadas en `tests/test_mathlab_integral_racional.py` **a propósito**, porque dos
negaciones distintas en una sola lista parecen un solo hueco.

### El otro límite, que es aritmética

Un denominador sin raíz racional de grado 4 —`u⁴+1`, o lo que deja
`∫dx/(cos x·cos 2x)`— no se sabe partir en dos cuadráticas sobre ℚ. Eso es un sistema
que hay que resolver, y hacerlo a medias —tratar las cuadráticas que salgan y tirar
el resto— es exactamente cómo un integrador racional empieza a responder «a veces».

### Tres fallos míos, de los que dos se leían como un rechazo honesto

| | |
|---|---|
| `{}` significaba dos cosas | el polinomio **cero** y el denominador **uno**. Multiplicar dos denominadores `{}` daba `{}`, la reducción veía un denominador nulo y se negaba, y **`u²` —que la regla de la potencia ya respondía— dejó de responder** |
| `{}` en el monomio | el **cero**, cuando ahí era `u⁰`. Todas las filas del sistema de fracciones parciales salieron a 0, el sistema fue singular, y `∫du/(u²-1)` se negó **con el mismo mensaje** que `∫du/(1+u²)` |
| el signo del factor lineal | `u - r` se guardaba como `u + c`, y la base salía `x - c` en vez de `x + c`: `u-1` integrándose como `+½ ln|u+1|`, con el signo de **todos** los términos invertido |

Los tres se leen igual desde fuera: un motor que devuelve «no lo sé» por el motivo
equivocado y por el correcto es indistinguible del que no lo sabe. Se encontraron
imprimiendo el polinomio intermedio, no mirando si devolvía algo.

### Lo que queda

Nada en T-14 ni en el catálogo de ecuaciones. En T-18 quedan **dos límites
declarados**, que son lo único que impide decir COMPLETADA: la cuadrática irreducible
de discriminante negativo (falta `arctg` en el lenguaje) y el cuártico sin raíz
racional. Los dos están en `tests/test_mathlab_huecos_documentados.py`, en listas que
**fallan** el día que se cierren.

## 2026-10-04 — el quíntico era de la sustitución, no de la ecuación

**47 de 47 ecuaciones del catálogo de sonido respondidas. 0 negadas, 0 inventadas,
0 incompletas.** El último rechazo delominado «aritmética» era una etiqueta falsa.

### Lo que estaba escrito y por qué era falso

La entrada anterior de este fichero afirma que `sen(x) + sen(2x) = 1` «no tiene
solución por radicales» y que el rechazo «es correcto y no es una limitación del
motor sino de la aritmética». La primera mitad es cierta; la conclusión no se sigue.

Lo que no tiene solución por radicales es **un quíntico**, y lo que la sustitución
`u = tg(x/2)` produce no es la ecuación: es la ecuación **con un punto enviado al
infinito**, y el denominador que aparece ahí es el que carga el grado sobrante.

| | |
|---|---|
| por `u = tg(x/2)` | numerador de grado 6, un factor racional y un **quíntico** detrás |
| por la cuenta de abajo | un **cúbico** |

### La cuenta

```
sen x + 2 sen x cos x = 1      ->      sen x (1 + 2cos x) = 1
sen x = 1/(1 + 2cos x)                 se despeja el seno
sen²x = 1/(1 + 2cos x)²                se eleva al cuadrado
1 - cos²x = 1/(1 + 2cos x)²            se usa sen²u + cos²u = 1

  1 = (1 - c²)(1 + 2c)²
  4c + 3c² - 4c³ - 4c⁴ = 0
  c · (4c³ + 4c² - 3c - 4) = 0          <-- un CÚBICO
```

Cardano, que ya estaba en el motor, lo cierra. `c = 0.9375648971`, y
`sen x + sen 2x = 1.000000000000`.

| | |
|---|---|
| `x = 1/2·π` | del factor `c` |
| `x = arccos(raiz(73/216 + 1/36·√87, 3) + raiz(73/216 − 1/36·√87, 3) − 1/3)` | del cúbico |

### Dos avisos que este caso tuvo que cumplir

**Elevar al cuadrado AÑADE soluciones.** Del cúbico salen cuatro candidatas en
`cos x`, y solo una anula la ecuación original. Cada candidata se comprueba contra
`f` en los ángulos que dan ese coseno, y solo se publica la que la anula. Sin esa
comprobación el caso habría publicado la mitad de la respuesta, y la mitad de la
respuesta es una respuesta que miente con la misma seguridad.

**La raíz va exacta, no su decimal.** La primera versión publicó
`arccos(193072653/205929908)`: un racional que se acerca a la raíz del cúbico hasta el
décimo. Una solución que falla en el décimo decimal no es una solución con redondeo,
es una mentira con aspecto de respuesta (§5.4). Ahora el ángulo lleva la raíz exacta
dentro, y el redondeo no aparece por ninguna parte.

### El fallo de redacción que costó dos vueltas

En el término `1·sen(x)` —el `1` de `(1 + 2cos x)`— hacía `Mul` en vez de `Add`, **y
asignaba el resultado a una variable local en lugar de al acumulador**. El efecto
observado era un cuártico sin raíces reales, que se lee exactamente igual que un
«no lo sé»: un motor que devuelve `None` por un motivo equivocado y por el motivo
correcto son indistinguibles desde fuera. Es la clase de fallo que sólo aparece si
se imprime el polinomio intermedio en vez de mirar si devuelve algo.

### Lo que queda

Nada en el catálogo de ecuaciones. Sigue abierto, y es otra cosa: la sustitución
`t = tg(x/2)` en la **integración** (`∫1/(1+cos x)` y `∫1/(cos x + cos 2x)`, T-18).

## 2026-10-04 — la sustitución universal, y con ella el último rechazo

**47 de 49 ecuaciones del catálogo de sonido respondidas. 0 inventadas, 0
incompletas.** De los 18 rechazos con los que empezó esto, quedan 2 — y son la misma
ecuación escrita al revés.

### Qué es

`t = tg(x/2)`, con la que **toda** expresión trigonométrica se vuelve racional:
`sen → 2u/(1+u²)`, `cos → (1−u²)/(1+u²)`, `tg → 2u/(1−u²)`. Es el último camino,
después de todos los demás, y lo que compra es una clase entera: dos términos
trigonométricos con argumentos distintos, que antes no se leían.

`cos(x)/cos(2x) = 1` es un ejemplo de lo que se abre: tres familias, completas.

### Tres cosas comprobadas, que son tres preguntas distintas

**El argumento tiene que SER la incógnita.** `sen(2x)` **no** es `2u/(1+u²)`: esa
entrada de la tabla es `sen(v)` para `v = x`, y leer `2x` como una `v` afín es el
**mismo error que `_como_polinomio` cometía** — sustituir una función por su nombre
sin mirar qué hay dentro. Por eso el desarrollo de ángulos múltiples ocurre **antes**:
`cos(2x)` nunca llega a ser un `cos(2x)` cuando la sustitución lo mira.

**Una raíz donde se anula el denominador es espuria.** Viene de despejar
denominadores, no de la ecuación, y el denominador de `tg` está muerto en `u = ±1`.

**`x = pi` se pregunta aparte.** `t = tg(x/2)` no está definida ahí, y un punto que el
cambio de variable no alcanza no es un punto que no sea solución: se pregunta, y si
anula la ecuación se publica como lo que es — un punto suelto, no una familia.

### Y el dominio del original, que es la última palabra

`1/tg(x)·sen(x) = 0` se reduce a `(1−u²)/(1+u²) = 0`, cuyas raíces `u = ±1` son
ceros perfectamente buenos de esa función racional — y en `x = 0` el original es `1/0`.
La sustitución no puede verlo: hizo un cociente de cocientes y perdió el polo interior.

### El fallo que encontró de paso: `_caso_racional` no filtraba los polos

Multiplicar por el denominador **añade candidatos**: cada cero de ese denominador
ahora satisface `N/D = 0`, y ninguno satisface la ecuación, porque la ecuación no está
planteada ahí. La hipótesis decía que los polos no eran soluciones; **esto lo hace
cierto**, y era un agujero de sonido anterior a este commit que solo se hizo visible
cuando otro camino consiguió responder al numerador reducido.

### El último rechazo era correcto por un motivo equivocado

`sen(x)·cos(x)·tg(x) = 0` llevaba mucho tiempo negándose, y la negativa era *cierta*
por un argumento *equivocado*: el producto sí tiene agujeros y `cos x = 0` cae en uno,
pero `tg x = 0` da `k·pi` y **ninguno de esos puntos es un agujero**. `A·B = 0` hace
las dos preguntas y solo una tenía agujeros.

Igual que con la etiqueta de `T-14` hace dos semanas: la afirmación era falsa, y lo
falso estaba escrito con la seguridad de lo verdadero.

### Lo que queda

| | |
|---|---|
| `sen(x) + sen(2x) = 1` | **aritmética.** En `t = tg(x/2)` su numerador es `u⁶ − 4u⁵ + 2u⁴ + 3u³ + 3u² − 6u + 1`, con un solo factor racional y un **quíntico** detrás. Ningún motor lo resuelve por radicales |

Aparece dos veces en el catálogo porque es la misma ecuación escrita al revés. Dos
entradas, un problema, y no es del motor.

### Y una tercera cosa que el arnés no veía

La batería no sabía medir una familia que es **un punto suelto** en vez de
`base + paso·k`, que es como la sustitución publica `x = pi`. Se las saltaba, y un
instrumento que no ve una respuesta no es evidencia de que la respuesta sea mala: lo
hizo `sen(x)·cos(x)·tg(x) = 0` inmedible.

## 2026-10-04 — `sech` y `csch`, y con ellas T-14 entera

Dos entradas de tabla y una etiqueta de documentación que pasa a **COMPLETADA**.

```
∫sech(u) du = arctg(senh u)
∫csch(u) du = log|tanh(u/2)|
```

No estaban porque no son la derivada de nada que ya estuviera en la tabla, y eso es
una razón distinta de «alguien se olvidó»:

- `d/du arctg(senh u) = cosh u / (1 + senh²u) = cosh u / cosh²u = 1/cosh u`
- `d/du log|tanh(u/2)| = 1/(2·senh(u/2)·cosh(u/2)) = 1/senh u`

Ninguna de las dos se escribe desde la tabla de derivadas por multiplicación por la
recíproca, que es como salen `∫senh`, `∫cosh`, `∫tanh` y `∫cotanh`. Hacen falta las
identidades hiperbólicas, y por eso se escriben como la derivada de una primitiva
**legible**: la entrada de la tabla se puede comprobar derivándola, que es lo que
hace la prueba.

### Lo que la alarma hizo

`tests/test_mathlab_huecos_documentados.py` tenía estas dos en una lista de huecos,
con una prueba que exigía que **fallaran** si algún día se integraban. Fallaron al
integrarlas, que es exactamente lo que se les pidió: una alarma que no suena cuando el
hueco se cierra no es una alarma.

Y la lista no se ha borrado: está vacía a propósito, con una aserción que dice que lo
está. Una lista de huecos vacía que **se ve** vacía informa de lo mismo que una
llena, y en seis meses alguien tendrá que añadir algo a ella. La alarma sigue
conectada.

### Etiquetas

`T-14` pasa a **COMPLETADA**: identidades, sumas y diferencias, dobles, inversas,
conexión exponencial, seis derivadas y seis integrales.

## 2026-10-04 — un reductor de radicales, que hace legible lo que ya era exacto

Sin ecuaciones nuevas: esto es **legibilidad**, y es una falta distinta de las de las
tandas anteriores.

### El problema

Toda raíz que el motor publica sale de una fórmula cuadrática o cúbica en la forma
`(-0 - sqrt(8))/2`, que es exactamente `-sqrt(2)`. Las dos cosas son exactas y una
solo se puede leer. Y el detalle pequeño que más llama la atención: el `-0` no es un
número, es un coeficiente de fórmula que ha salido cero, y la fórmula cuadrática
fabrica uno cada vez que el coeficiente central es 0.

### Qué hace

`trig.reducir_radicales`, un objetivo propio:

| antes | después |
|---|---|
| `sqrt(8)` | `2*sqrt(2)` |
| `sqrt(1/8)` | `1/4*sqrt(2)` |
| `sqrt(19/1728)` | `1/72*sqrt(57)` |
| `(-0 - sqrt(8))/2` | `-sqrt(2)` |
| `(-2 + sqrt(12))/4` | `-1/2 + 1/2*sqrt(3)` |
| `-0` | `0` |

Y con ello la respuesta de Cardano queda legible de verdad:

```
x = arccos(raiz(1/8 + 1/72·√57, 3) + raiz(1/8 - 1/72·√57, 3)) + 2·π·k
```

### Por qué es un objetivo aparte, y no una regla más

Porque **alarga la expresión**: `sqrt(8)` son cinco caracteres y `2*sqrt(2)` son ocho.
Las reglas de `_REGLAS` solo pueden hacer la expresión estrictamente más barata o
más cara (§5.5b), y «más corta» no es la misma pregunta que «más legible». Así que es
un objetivo por sí mismo, lo llama el solucionador de camino a publicar una raíz, y
`simplificar` no lo llama nunca.

Nada de esto es aritmética de verdad: toda la numeración es con `Fraction`, y las
pruebas comprueban las dos cosas por separado — que el texto salga como está escrito y
que **el valor no haya cambiado**. Un reductor de radicales que cambiara el número
sería el peor de los bugs posibles aquí, porque las respuestas seguirían pareciendo
iguales.

Lo que **no** hace, y queda dicho: no combina `sqrt(2) + sqrt(8)` en `3*sqrt(2)`, ni
simplifica un cociente raíz (`sqrt(2)/sqrt(3)`), ni baja un factor común. Reducir
cada radical por separado es un objetivo legible y acotado; la simplificación de
radicales en serio es otro.

## 2026-10-04 — Cardano, y lo que «irreducible» no significa

De 3 rechazos a 2, y de 18 a 2 en cuatro tandas. `cos(3x) + cos(x) = 1`.

### El rechazo que era aritmética, no motor

`cos(3x) + cos(x) = 1` se desarrolla a `4c³ − 2c − 1` y se negaba con el motivo «queda
un factor de grado 3 sin raíces racionales, que este motor no resuelve».

**Irreducible quiere decir «sin raíz racional», no «sin solución».** Una cúbica
siempre tiene una raíz real: es la razón por la que existe la fórmula de Cardano. El
motor estaba negándose a la aritmética y lo escribía como si fuera una carencia suya.

En la forma deprimida `v³ + pv + q` la raíz real es
`∛(−q/2 + √Δ) + ∛(−q/2 − √Δ)` con `Δ = (q/2)² + (p/3)³`, y volver es `u = v − b/(3a)`.
Todos los coeficientes son `Fraction`, así que `p`, `q` y `Δ` son exactos y las raíces
cúbicas **se anidan** dentro de la cuadrada. El resultado para esta ecuación es
`cos x = 0.8846461771`, y el lado izquierdo se anula a 1e-15.

**Solo con `Δ > 0`.** `Δ < 0` es el *casus irreducibilis*: tres raíces reales que
Cardano solo alcanza por raíces cúbicas **complejas**, y escribir eso es peor respuesta
que no escribirla (§5.4). Y `Δ = 0` nunca llega aquí, porque una cúbica con raíz
repetida tiene raíz racional y la rama anterior ya la cogió.

De regalo, `cos(x)³ − 2cos(x) + 1 = 0` también responde ahora: raíz racional `1` y
cuadrática detrás, que es donde ya estaba el camino.

### Lo que cuesta

La respuesta es legible-peor de lo que uno querría:

```
x = arccos(raiz(1/8 + √19/1728, 3) + raiz(1/8 - √19/1728, 3) - 0) + 2·π·k
```

Es exacta y es honesta —un decimal disfrazado de solución exacta sería peor (§5.4)—,
pero es larga. El `- 0` del final es ruido del constructor. Un simplificador de
radicales que escribiera `raiz(1/8 + √19/1728, 3)` como `(∛9 + ∛3)/(2·∛3)` no existe
todavía en el motor, y es el mismo trabajo que quedó pendiente para `(-0 - sqrt(8))/2`.

### El estado

**46 de 49 ecuaciones del catálogo de sonido respondidas, 3 negadas, 0 inventadas, 0
incompletas.** Y el hueco de clasificación que llevaba abierto desde el principio se
cerró solo: ya no hay ninguna ecuación que conteste vacío sin declarar por qué.

Las tres que quedan:

| | |
|---|---|
| `sen(x) + sen(2x) = 1` | sin factor común —el `−1` se lo quita— y por `t = tg(x/2)` su numerador es de grado 6 con un solo factor racional: queda un **quíntico**, que no tiene solución por radicales. Aparece dos veces en el catálogo, es la misma ecuación escrita al revés |
| `sen(x)·cos(x)·tg(x) = 0` | **se niega correctamente.** Una familia `base + paso·k` no tiene agujeros y el producto sí |

Las dos categorías que quedan son, por fin, de naturaleza distinta: **una es aritmética**
—ningún motor la puede resolver— **y la otra es una decisión de diseño.** Durante
tres tandas fueron las cuatro cosas lo mismo, y esa indistinción es lo que ha costado
más trabajo que cualquier otro.

## 2026-10-04 — la tangente como cociente, y Pitágoras en el sitio correcto

De 4 rechazos a 3, y de 18 a 3 en las tres últimas tandas. `tg(x) + cos(x) = 0`.

### El hueco

`as_ratio` no podía ayudar con `tg(x) + cos(x) = 0` porque lee `tg(x)` como un
**átomo**: en `cos(x) + tg(x)` no hay ninguna división, así que el cociente no llega
a aparecer y el caso racional nunca dispara. El cociente solo existe después de
escribir la tangente como lo que es.

`tg(x) + cos(x) = 0` es `sen(x)/cos(x) + cos(x) = 0`; el caso racional multiplica
por el denominador y sale `sen(x) + cos²(x) = 0`; y con `cos²x = 1 − sen²x` queda
`sen²(x) − sen(x) − 1 = 0`, cuyas raíces son `(1 ± √5)/2` — y solo una de las dos es
un valor del seno. La traza dice las tres cosas, incluida la que rechaza la otra raíz.

La Pitágoras va **en el caso del solucionador**, no en `trig.simplificar`, porque los
solucionadores leen ese y esta reescritura **crece** la expresión: `sen²x` son cinco
caracteres donde `cos²x` son seis. Una reescritura que alarga pertenece a su objetivo
(§5.5b), y lo único que la quiere es el solucionador.

Y se aplica **solo cuando la lectura simple del mismo candidato ha fallado**, porque
`1/cos(x)⁴ = 16` leída como `cos` es una cuadrática, y leída como `sen` a través de
Pitágoras es un cuártico sin raíces racionales. Una reescritura que ayuda en un sitio
y esconde la respuesta en otro es peor que no tenerla.

### Un test que afirmaba algo falso

`sen(x) + 1` y `cos²(x) + 1` se comparaban como «diferencia sin ceros», y se creían
porque el motor **no sabía** encontrar las raíces: `sen x − cos²x = 0` es
`sen²x + sen x − 1 = 0`, cuya raíz `(√5 − 1)/2 ≈ 0.618` **está en el rango del seno**.
Sí se cortan, en `x = arcsen(0.618) ≈ 0.666`, y ahí los dos lados valen `1.618`.

Una prueba que afirma una cosa falsa pasa exactamente mientras el motor sea bastante
ignorante, y esta llevaba pasando por eso. Ahora hay dos: una con un par que de
verdad no se cortan (`cos²x` contra `sen²x + 2`, cuya diferencia es `cos 2x − 2` y
está acotada por `−1`), y otra que dice en voz alta que el par antiguo sí se corta.

### El método, que es la otra mitad del commit

El intento anterior mezcló las dos piezas y rompió `cos(x)² > 1/2`. Esta vez, **una
variable cada vez**: primero Pitágoras sola —y el culpable resultó ser un fallo mío
concreto: reescribía `cos(x)` a `cos(u)`, con lo que el «ángulo» que `_trasladar`
deshace pasaba a ser `u` en vez de `x`, y todas las soluciones se desplazaban— y solo
después la tangente encima.

Es la misma lección del propio CHANGELOG, escrita y luego incumplida dos veces en la
misma tarde.

### Lo que queda: tres, y son distintos entre sí

| | por qué |
|---|---|
| `sen(x) + sen(2x) = 1` | sin factor común —el `−1` se lo quita— y por `t = tg(x/2)` su numerador es de grado 6 con un solo factor racional: queda un **quíntico**, sin solución por radicales. Es aritmética, no una carencia del motor |
| `cos(3x) + cos(x) = 1` | cúbica irreducible `4u³ − 2u − 1`. **Cardano la resuelve**, con raíz cúbica de un irracional |
| `sen(x)·cos(x)·tg(x) = 0` | **se niega correctamente.** No es un hueco: una familia `base + paso·k` no tiene agujeros, y el producto sí los tiene |

## 2026-10-04 — el factor común, sacado de la suma

De 18 rechazos a 5. Es el paso que faltaba entre el ángulo múltiple y el producto, y
es el más pequeño de los tres que había: **sacar el factor común de una suma**.

### El hueco

`sen(x) + sen(2x) = 0` se desarrolla a `sen x + 2sen x cos x`. El producto ya
sabía partir `A·B = 0`, pero ahí **no hay un producto**: hay una suma con el factor
repetido en cada término, y la regla de producto no ve un producto donde no lo hay.

`sen x + 2sen x cos x` es `sen x · (1 + 2cos x)`. Una vez sacado el factor, las dos preguntas son las que el
motor ya contestaba solo: `sen x = 0` y `cos x = −1/2`.

Cuatro ecuaciones:

| | antes | después |
|---|---|---|
| `sen(x) + sen(2x) = 0` | se negaba | `{0, pi, 2/3·pi, −2/3·pi}` |
| `sen(x) − sen(2x) = 0` | se negaba | `{0, pi, 1/3·pi, −1/3·pi}` |
| `cos(x) − sen(2x) = 0` | se negaba | `{1/2·pi, −1/2·pi, 1/6·pi, 5/6·pi}` |
| `sen(2x) − sen(x) = 0` | se negaba | `{0, pi, 1/3·pi, −1/3·pi}` |

**43 de 49 respondidas con datos, 5 negadas, 0 inventadas, 0 incompletas.**

### La factorización se comprueba por muestreo

Un factorizado que no lo es es **otra ecuación**, y lo más barato aquí es equivocarse
en silencio. Así que la forma factorizada se compara con la suma original en siete
puntos y, si discrepan en algo, no se usa. Preguntar al dominio no serviría —las dos
formas existen donde existe cualquiera de las dos— y preguntar el álgebra sería
confiar en el álgebra que se está comprobando.

Ese muestreo cobró su trabajo enseguida: la primera versión **perdía el coeficiente de
cada término** y daba `cos x − 2cos x sin x` → `cos x(cos x − sin x)`, que es otra
función. Y un término que *es* exactamente el factor común tiene cociente **uno**,
no cociente vacío; devolver `None` ahí era lo que hacía que todas estas ecuaciones
siguieran negándose.

### Los cinco que quedan

| | por qué |
|---|---|
| `sen(x) + sen(2x) = 1` | no tiene factor común —el `−1` se lo quita— y en `t = tg(x/2)` el numerador es de grado 6 con un solo factor racional, así que queda un quíntico |
| `cos(3x) + cos(x) = 1` | cúbica irreducible, `4u³ − 2u − 1`: sin raíces racionales ni fórmula |
| `tg(x) + cos(x) = 0` | mezcla seno y tangente, y el producto no aplica |
| `tg(x)·sen(x) = 0` | **se niega correctamente**: el producto tiene agujeros |
| `sen(x)·cos(x)·tg(x) = 0` | **se niegan correctamente**, por lo mismo |

Los dos últimos no son un hueco sino una decisión: una familia `base + paso·k` no
tiene agujeros, así que una solución con huecos no se puede publicar ni a medias.

## 2026-10-04 — el producto se parte por los puntos, no por los dominios

De 5 rechazos a 4. Y uno de los que se negaban **no debía negarse**.

### El rechazo que sobraba

`tg(x)·sen(x) = 0` se negaba porque `tg` no existe en `x = pi/2 + k·pi` y `sen` sí, de modo que los dos factores tienen dominios distintos y la regla de producto exigía que coincidieran. Pero las soluciones son `x = k·pi`, y **ninguno de esos puntos es un agujero**. El conjunto solución no tiene ni un hueco, y el rechazo era una admisión de hueco donde no lo hay.

La condición correcta es exacta y es sobre el **producto**: un punto resuelve `A·B = 0` cuando es cero de algún factor **y el producto existe allí**. Así que se pregunta el dominio del producto y se comprueba punto por punto. Ni demasiado fuerte ni demasiado floja.

La tabla que la pone a prueba:

| | dominios distintos | se publica |
|---|---|---|
| `tg(x)·sen(x) = 0` | sí | **sí** \u2014 las soluciones son `k·pi`, sin un agujero |
| `sen(x)·tg(x) = 0` | sí | **sí**, por lo mismo |
| `cos(x)·tg(x) = 0` | sí | **no** \u2014 `cos x = 0` da `pi/2 + k·pi`, que sí es agujero |
| `sen(x)·cos(x)·tg(x) = 0` | sí | **no**, por lo mismo |
| `1/tg(x)·sen(x) = 0` | sí | **no** \u2014 su única solución *es* el agujero |

La pregunta se le hace al DOMINIO y nunca al evaluador, que en `x = pi/2` ve `cos = 6·10⁻¹⁷` y `tg = 1.6·10¹⁶` y llama al producto un número grande y corriente donde no hay nada.

### Y lo que queda de los cinco

- `sen(x) + sen(2x) = 1`: sin factor común —el `−1` se lo quita— y en `t = tg(x/2)` su numerador es `t⁶ − 4t⁵ + 2t⁴ + 3t³ + 3t² − 6t + 1`, con un solo factor racional y un **quíntico** detrás. No tiene solución por radicales. El rechazo es correcto y no es una_LIMITACIÓn del motor sino de la aritmética.
- `cos(3x) + cos(x) = 1`: cúbica irreducible `4u³ − 2u − 1`. **Cardano la resuelve**, con razón cúbica de un irracional; la respuesta sería exacta pero horrible de leer, y el motor no tiene forma de escribirla.
- `tg(x) + cos(x) = 0`: aquí el camino existe pero falta una pieza. Necesita `tg → sen/cos` y `cos²x → 1 − sen²x`, y **ninguna de las dos identidades está en el motor**: `trig.razones` no reescribe `tg` ni `cos²`, y `as_ratio` trata `tg(x)` como átomo, así que nunca ve el cociente. Por `t = tg(x/2)` tampoco sale: el numerador es `t⁴ + 2t³ − 2t² + 2t + 1`, sin raíces racionales \u2014 aunque es **palindródrico**, así que con `w = t + 1/t` cae a `w² + 2w − 4 = 0` y de ahí sí. Ese es el camino corto y es trabajo de una tarde.

## 2026-10-04 — el ángulo múltiple, desarrollado, y ocho ecuaciones más

Cierra el punto 1 de la lista. Y cierra también un agujero de documentación que
llevaba dos commits abierto: el `CHANGELOG` de la tanda `9a3e8e4` afirmaba que
existía una función que escribía los ángulos múltiples en potencias de la misma
función, y esa función **nunca se commiteó**: se perdió al pegar un bloque por
índice de línea y la afirmación se quedó. Esto la vuelve a poner, y esta vez está en
el código y en las pruebas.

### Qué hace

Un ángulo múltiple **junto a otro término** es lo que ningún caso sabía leer. El
análisis es bueno en `a·cos(u) + b = c` y en polinomios de **una** función, y
`cos(x) + cos(2x) = 0` no tiene ninguna de las dos formas: el segundo término es un
coseno de **otro** argumento, y ningún caso estaba dispuesto a llamar a los dos
`cos`.

Escrito en potencias de la misma función no cuesta nada y es exacto —
`cos(2x) = 2cos²(x) - 1`, `sen(3x) = -4sen³(x) + 3sen(x)` — y de ahí lo resuelve el
camino que ya resolvía `cos(x)² = 1/2`. El solucionador de raíces divide luego las
racionales y cierra la cuadrática que queda, que es lo que convierte `4c³ − 2c − 1`
en algo con sus tres raíces y no en un rechazo.

Ocho ecuaciones, de negadas a respondidas:

| | antes | después |
|---|---|---|
| `cos(x) + cos(2x) = 0` | se negaba | `{1/3·pi, pi, -1/3·pi}` |
| `cos(x) - cos(2x) = 0` | se negaba | `{2/3·pi, 0, -2/3·pi}` |
| `cos(3x) + cos(x) = 0` | se negaba | seis familias |
| `sen(3x) - sen(x) = 0` | se negaba | seis familias |

**39 de 49 respondidas con datos, 9 negadas, 0 inventadas, 0 incompletas.** Antes de
esta tanda eran 31 respondidas. La batería mide 49 ecuaciones, cada una por los dos
lados.

### Dos decisiones que hay que explicar

**El original va primero.** La expansión conserva el valor —eso es lo que la hace
segura— así que nunca puede contestar otra ecuación, pero sí puede contestar la misma
de forma menos clara. `cos(2x) = 0` ya tenía una respuesta limpia de dos familias, y
desarrollarla primero la habría sustituido por cuatro que dicen lo mismo peor. La
expansión es para las ecuaciones sin respuesta, que es donde faltaba.

**Un intento que se revirtió.** Marcar una declinación como rechazo
(`MOTIVO_DECLINA`) arreglaba un agujero real de clasificación: `cos(3x) + cos(x) = 1`
publica cero familias y no declara rechazo, así que quien pregunte «¿se negó?» no lo
ve. Pero rompía `cos(x)³ > 2`, que **hoy acierta**: `|cos| ≤ 1` así que no hay
soluciones. Lo acertaba por el motivo equivocado —«no ha publicado nada» leído como
«no hay soluciones»—, pero lo acierta, y un refinamiento de clasificación no puede
costar una respuesta correcta. Se queda el agujero, y se dice.

### Lo que queda

De los nueve rechazos, **seis son el mismo mecanismo**: dos términos trigonométricos
con argumentos distintos. `sen(x) + sen(2x) = 0` es `sen x·(1 + 2cos x) = 0`, que
factoriza, pero hace falta factorizar y factorizar es la sustitución universal. Los
otros tres: `cos(3x) + cos(x) = 1` es una cúbica irreducible (`4u³ − 2u − 1`), sin
raíces racionales ni fórmula; y `tan(x)·sen(x) = 0` y `sen(x)·cos(x)·tan(x) = 0` se
niegan **correctamente**, porque el producto tiene agujeros y una familia
`base + paso·k` no los puede expresar.

## 2026-10-04 — la carta de signos ya coloca los puntos que son expresiones

Cierra el punto 2 de la lista. `Punto` tenía desde el principio una tercera forma
—un punto de la recta que es una expresión, y no un racional o un múltiplo de `pi`— y
su docstring decía que existía justo para esto. Lo que faltaba no era el tipo: era
que **la carta no lo usaba**, y lo usaba de la peor manera posible.

### El fallo

La carta cortaba sus huecos por los **coeficientes** de los puntos:

```python
coeficientes = [p.coeficiente for p in puntos]
```

Un punto que es una expresión tiene coeficiente **cero**. Así que todos los
radicales iban a parar al origen, y la carta dibujaba con menos fronteras de las
que tenía:

| inecuación | decía | verdad |
|---|---|---|
| `x^2 - 2 > 0` | `∅` | `(-∞, -√2) ∪ (√2, ∞)` |
| `x^3 - 2x > 0` | `(-∞, 0)` | `(-√2, 0) ∪ (√2, ∞)` |
| `2x^3 - 3x + 1 > 0` | `(-∞, 0) ∪ (1, ∞)` | `(-∞, (1-√5)/2) ∪ ((1+√5)/2, ∞)` |

No descartaba los puntos: los **convertía en el origen**. Y ninguna de las tres se
anunciaba como dudosa.

### El arreglo

Eran dos cosas:

1. `ceros_en_puntos` pide `completar=True` y convierte una raíz que no es racional
   en `D.Punto(expresion=raiz)`, ordenando por `valor()` y no por coeficiente.
2. `_carta_aperiodica` corta por los **puntos** y muestrea por su **`valor()`**. El
   extremo del intervalo es el `Punto` entero —que es lo que se imprime— y su
   posición es el número —que es lo que se evalúa—. Son dos preguntas distintas, y
   mezclarlas es lo que perdía los puntos.

Una trampa de paso: `Root` es una subclase de `Call`, así que la guardia que
descartaba «una llamada» descartaba también `√2`. Un radical no es una función
transcendental, y aquella guardia lo daba por una.

### Lo que se gana

`x^2 - 2 > 0`, `x^3 - 2x > 0` y `2x^3 - 3x + 1 > 0`, con sus cinco inequalities hermanas,
más el dominio de `1/(x^2-2)`, que antes se negaba y ahora da los tres intervalos
con los dos agujeros en `±√2`. Comprobado por muestreo denso: **19 de 19, 0 falsos,
0 omitidos**, que es sonido y completitud a la vez — como se comprueba un conjunto y
no una expresión.

Con esto cae la última razón de `completar=False`: ya no es que la carta no sepa
nombrar un radical, es que ahora sí.

### Lo que queda mal escrito

Los extremos salen como `(-0 - sqrt(8))/2` donde deberían leerse `√2`. Es correcto y
es legible-peor, y la causa es que **no hay simplificador de radicales en el motor**:
`T.simplify` no toca `sqrt(8)`. Reducirlo es trabajo nuevo y no se ha hecho aquí.

## 2026-10-04 — las raíces racionales se dividen, y lo que queda se resuelve

Cierra el defecto que abrió la entrada siguiente. Allí «sen(x)³ - sen(x)/2 = 0»
publicaba cuatro de sus seis soluciones; ahora publica las seis, y **31 de las 49**
ecuaciones del catálogo de sonido quedan respondidas, con **0 inventadas y 0
incompletas**.

### Lo que hace

El teorema de la raíz racional da un conjunto **parcial** en grado 3 o mayor. Que la
respuesta parcial se dijera ya era cosa de la entrada anterior; lo que faltaba era
dejar de ser parcial, y es más simple de lo que parecía:

1. dividir fuera las raíces racionales que se encuentren, una por una;
2. resolver con la fórmula cuadrática lo que queda, si queda un grado 2;
3. si queda grado 3 o mayor, decirlo, y seguir sin poder.

El paso 1 es `poly._divide_linear`, que ya existía. El paso 2 es el mismo
`discriminante` del caso cuadrático de siempre. No hay método numérico ni
tolerancias: es factorizar por la raíz racional y cerrar la cuadrática.

`-4u³ + 2u` es `-2u(2u² - 1)`, y `2u² - 1` es una cuadrática que este motor llevaba
resolviendo desde el principio. `2u³ - 3u + 1` es `(u - 1)(2u² - 2u - 1)` y da
`(1 ± √5)/2` de regalo.

### Lo que hubo que arreglar por el camino

**La salida temprana de `_divide_linear` estaba mal planteada, no mal escrita.** La
entrada anterior cambió `coeff % a != 0` por una prueba de denominador, y siguió
fallando: `a` es **un coeficiente**, así que es siempre un `Fraction`, y `coeff/a` es
siempre un cociente racional válido. Preguntar si es entero no es la pregunta de si
la división es exacta; esa la responde el resto final. `-u³ + u/2` dividido por `u` se
paraba en el coeficiente `1/2` y se declaraba inexacto — la división más simple que
existe. La salida temprana se eliminó entera y la exactitud la decide `_divide_exact`
con `is_zero(remainder)`, que es donde estaba desde el principio.

**`mx.evaluate` contesta en complejos para todo.** `Num(0)` llega como `0j`, y está
documentado como herramienta de *verificación* (§5.3), no de decisión. Una guarda
`isinstance(valor, complex)` rechaza **toda** comparación sin decir por qué. Añadido
`mx.valor_real`, que es el accesor para la otra pregunta: «¿es esto un número real, y
cuál?».

**Dos familias que eran la misma.** `cos(x) - cos(x)³ = 0` publicaba `x = π + 2k·π` **y**
`x = -π + 2k·π`: una sola familia escrita de dos formas, y el alumno contaba cinco
soluciones donde hay cuatro. `_deduplica` comparaba el texto base; ahora compara por
valor a través del paso.

### Lo que no se completa, y por qué no se completa

`1/cos(x)⁵ = 32` es `u⁵ - 1/32`. Se divide `u - 1/2` y queda un factor de grado 4,
que no es de los que se cierran con una cuadrática. La respuesta que publica **es
correcta** — las cuatro raíces que faltan son complejas — pero el motor no lo sabe, y
la nota que pone lo dice así:

> se han dividido sus factores lineales y queda uno de grado 4, que este motor no
> resuelve. Las raíces racionales que se han encontrado están todas; de las demás
> **no puede afirmar** que sean reales, y eso no es lo mismo que decir que no lo sean.

Son tres frases distintas: «no hay raíces» (falso, y la respuesta estaría mal), «no lo
sé» (cierto e inútil) y la tercera, que es la única que se puede sostener. Hay una
prueba que la vigila.

### Una precaución sobre la carta de signos

`_raices_reales` tiene un parámetro `completar`, y la carta de signos lo pide en
`False`. No es pereza: `inequaciones._ceros_aperiodicos` necesita las raíces como
**puntos** para dibujar, y un radical no es un punto que sepa nombrar. Completar las
raíces convertiría un dibujo que podía hacer en una negación: honesta e inútil. El
solucionador de ecuaciones quiere lo contrario, porque allí un radical **es** una
solución.

El orden importa, y por eso son dos etapas: primero las raíces completas — esto —, y
después la tercera forma de `Punto`, la de expresión, que existe y no se usa para
esto. Hasta entonces, esa clase de polinomio queda abierta.

### Dos fallos del arnés, que son peores que no tenerlo

**El barrido contaba dos veces la misma raíz.** Termina exactamente en `2·π`, y el
resto de eso es un residuo de unos `10⁻¹⁵`, no `0`, así que `x = 2·π` se contaba como
raíz distinta de `x = 0`. Salió como una séptima raíz de una ecuación que tiene
seis. Un instrumento que **añade** puntos acusa al motor de inventar soluciones, y esa
es la peor manera de equivocarse.

**Y la cuenta de soluciones la escribí mal dos veces.** Son seis, no ocho: `sen x = 0`
da dos y `sen²x = 1/2` da las otras cuatro. Lo sostienen las pruebas, no la prosa, y por
eso las pruebas las cuentan.

### Y este CHANGELOG tenía 98 escapes `\uXXXX` literales

Las dos entradas anteriores se escribieron con los caracteres escapados en vez de
escritos, así que se leía `\u00edces` donde debía leerse «raíces». Estaba en el
`CHANGELOG` y también en once comentarios de `ecuaciones.py`, ya committeados. En
Python un `\u00ed` dentro de una cadena normal se interpreta, así que el código no
fallaba: lo que estaba roto era lo que se lee. Reparado, y la comprobación de que no
quedan es de un minuto.

## 2026-10-04 — el solucionador publicaba la mitad de las soluciones sin decirlo

Un fallo de la misma familia que los dos de la cabecera de este fichero, y
encontrado por el camino al intentar lo otro: **una sustitución o un algoritmo
que se aplica sin mirar lo que devuelve, y el resultado se publica como si fuera
del todo**.

### El fallo

`sen(x)³ - sen(x)/2 = 0` es `-u³ + u/2` con `u = sen(x)`. Sus raíces son `0`,
`±1/√2` y `±1/√2`. El teorema de la raíz racional encuentra `u = 0` y
se detiene, porque las otras dos no son racionales y ningún teorema que solo
mire números racionales va a encontrarlas.

El motor publicaba `{0, pi}`. **Cuatro de las ocho soluciones, sin decir nada.**

El motivo estaba calculado: `_raices_reales` devuelve `(«solo se dan las raíces
racionales exactas», §5.4)` y `_caso_polinomio` **lo tiraba en la línea siguiente a
comprobarlo**, al empezar la lista de hipótesis de cero. Una frase que existe,
se calcula, y se descarta antes de que nadie la lea.

Lo mismo con `cos(x)³ - cos(x)/2 = 0`, y con `sen(x) - sen(x)³/2 = 0` y
`cos(x) - cos(x)³ = 0`, que perdían las cuatro de `±±1/√2` y `±√2`.

### Por qué la batería no lo vio

Ninguna de las 41 ecuaciones de `RESPONDIDAS` produce un polinomio con raíces
irracionales. Treinta y una ecuaciones comprobadas dos veces por cada lado, con
cero inventadas y cero incompletas, y el agujero estaba justo en la clase de
polinomio que la batería no tocaba. Las pruebas miden lo que se les pone.

### Lo que se arregla aquí

Solo una cosa, y es la raíz del fallo: **la frase se conserva.** La respuesta sigue
siendo parcial, y ahora lo dice. No es una respuesta completa y no se presenta
como tal; es un hueco que el usuario puede ver, que antes no podía.

La lista `PARCIALES` de `tests/test_mathlab_ecuaciones_sonido.py` deja las cuatro
ecuaciones escritas con su número de soluciones que faltan, de modo que el día
sea una medida y no una sensación: si algún completa las raíces, esa prueba falla
y avisa.

### Lo que NO se arregla, y por qué

Completar las raíces se implementó y se midió: dividiendo las racionales
fuera con división exacta y resolviendo la cuadrática que queda, `sen(x)³ -
sen(x)/2 = 0` pasó de 2 familias a 6, y sobre 15 ecuaciones quedó **0 inventadas y 0
incompletas**, con los reciprocos con potencia intactos. Rompió otras dos cosas, y
por eso no entra:

1. **`mx.evaluate` contesta en números complejos para todo.** `Num(0)` llega como
   `0j`. Una guarda `isinstance(valor, complex)` rechaza **toda** comparación sin
   decir nada, y por eso `x = pi + 2k·pi` y `x = -pi + 2k·pi` salían como dos
   familias: son la misma, y el alumno cuenta cinco soluciones donde hay cuatro.
   Hay que sacar `.real` y comprobar la imaginaria.
2. **El exponente cero es la monomia vacía `()`**, no `((·,0),)`. Leerla como
   `((·,0),)` devuelve un cero silencioso, y toda división por `(u - r)` con
   término constante salía «inexacta» pareciendo correcta en la traza.
3. **`poly._divide_linear` prueba la divisibilidad con `coeff % a != 0`**, que en
   `Fraction` no es la pregunta correcta: `Fraction(-1, 2) % 1` es `Fraction(1, 2)`.
   `u³ - u/2` dividido por `u` — la división más simple que hay — se
   declara inexacta. Arreglarlo ahí es lo correcto, pero `as_ratio` comparte esa
   función con el dominio y con la carta de signos, y cambiar lo que se cancela en
   un cociente llega a las tres: rompió `1/cos(x)µ = 32` y `sec(x)µ > 32`.
   **Tanda propia, con batería propia.**
4. **Completar las raíces convierte la carta de signos en un rechazo.**
   `inequaciones._ceros_aperiodicos` necesita las raíces como *puntos* y un radical
   no es un punto que sepa nombrar, así que la cuadrática exacta solo cambia un
   dibujo que podía hacer por una negación: honesta e inútil. El arreglo tiene
   dos mitades y en este orden, o la carta de signos deja de funcionar:
   primero las raíces completas, después la tercera forma de `Punto` — la de
   expresión, que existe y no se usa para esto.

Los tres primeros son media hora cada uno y no dependen uno del otro.

## 2026-10-03 — la sustitución universal, intentada y revertida

El paso que quedaba era factorizar después de `t = tg(x/2)`. Se ha
implementado, se ha medido, **produce respuestas incompletas**, y se ha revertido.
Queda escrito por qué, que es lo que hace útil el siguiente intento.

### Lo que se midió bien

El mecanismo funciona donde la sustitución queda plana, y abre siete ecuaciones
que el motor se negaba:

| | antes | después |
|---|---|---|
| `cos(x) + cos(2x) = 0` | se negaba | `{1/3·pi, pi, -1/3·pi}` |
| `cos(x) - cos(2x) = 0` | se negaba | `{2/3·pi, 0, -2/3·pi}` |
| `cos(3x) + cos(x) = 0` | se negaba | `{1/2·pi, -1/2·pi}` |
| `cos(x) + cos(2x) = 1` | se negaba | `acos((-1 + √17)/4)` ± |

Y `cos(x) + cos(2x) = 0` pasó a leerse en potencias de la misma función —
`cos x + 2cos²x - 1` — y de ahí la resuelve el camino que ya resolvía
`cos(x)² = 1/2`. Ese es el punto bueno del asunto: **las identidades ya estaban, lo
que faltaba era un caso que las usara**.

### Por qué se revierte

`sen(3x) - sen(x) = 0` se respondía `{0, pi}` y le faltan las de
`cos(2x) = 0`. Es una **respuesta incompleta presentada como completa**, que es
justo el fallo que §5.4 recuento, en el sitio donde el motor se le exige
exactitud. Un rechazo es honesto; publicar la mitad de las soluciones con la misma
seguridad con que se publican todas, no.

Las cuatro cosas que hay que tener resueltas antes de reintentarlo, en orden:

1. **`as_ratio` NO despeja una división anidada.** El numerador de
   `cos(x) - cos(2x)` llega como `(1-u²)/(1+u²) - 2((1-u²)/(1+u²))² + 1`, con
   fracciones dentro. `degree_in` lee el exponente del `u²` interior y dice
   «grado 2», la fórmula cuadrática corre sobre una fracción y las raíces salen
   como `0/0`. La forma tiene que comprobarse **donde se produce la respuesta**,
   que es donde no la comprobaba nadie.
2. **La sustitución solo lee el nombre de la función.** `cos(2x)` no es
   `(1-t²)/(1+t²)`: esa entrada de la tabla es `cos(u)` con `u = x`. Leír
   `2x` como `u` afín es **el mismo error que `_como_polinomio` cometía** —
   sustituir una función por su nombre sin mirar qué hay dentro — y contestó
   `cos(x) + cos(2x) = 0` con `2·arctg(1)`, un punto donde el lado izquierdo es `−1`.
   Por eso el desarrollo de ángulos múltiples tiene que ocurrir ANTES.
3. **Las raíces de grado alto son irracionales.** `sen(x) + sen(2x) = 0` es
   `2t(3 - t²)` en `t`: `0` y `±√3`. El teorema de la raíz racional no las ve, y
   sin la cuadrótica exacta el caso solo puede negarse. Publicar las racionales
   que se encontram **sin decir que faltan las demás** es la misma respuesta
   incompleta de arriba.
4. **`x = pi` es donde `t = tg(x/2)` no está definida.** Hay que preguntarlo por
   separado, no dejar que falte en silencio.

Además, un descuido propio que conviene no repetir: al pegar bloques por
índice de línea se perdió por el camino una función entera
(`_desarrolla_angulos_multiples`), y el CHANGELOG de la tanda anterior segú
afirmando que existía. Las afirmaciones del CHANGELOG hay que comprobarse
contra el código, no contra lo que uno recuerda haber escrito.

## 2026-10-03 — `A·B = 0` se parte en sus factores, con su condición de sonido

`sen(x)·cos(x) = 0` se negaba, y es la ecuación más simple de la familia. El motor
sabía resolver `sen(x) = 0` y `cos(x) = 0` por separado y no veía que un producto
pregunta las dos cosas a la vez, así que el rechazo no era una limitación que
declarar sino un hueco quehacía invisible toda la familia.

### La regla y su condición

`A·B = 0` es `A = 0` o `B = 0` — **solo donde el producto entero existe**, y esa
segunda mitad es la que cuesta. `sen(x)·cos(x)·tg(x) = 0` tiene `cos(x) = 0` como
respuesta de uno de sus factores, y en `x = pi/2` el producto es `0·0·indefinido`: la
ecuación ni siquiera está planteada ahí. Publicar esa familia metería puntos
donde la expresión no se puede evaluar — el mismo fallo que un dominio que gana
un agujero, en la respuesta en vez de en el conjunto.

Así que el producto solo se parte **cuando todos sus factores comparten
dominio**, que es lo que hace exacta la equivalencia. Se pregunta al DOMINIO y
nunca al evaluador: en `x = pi/2` el coseno vale `6·10⁻¹⁷` y la tangente
`1.6·10¹⁶`, y preguntar «existe aquí?» a un punto flotante devuelve un número
grande y corriente donde no hay nada.

Un factor con potencia no negativa se cuenta una sola vez, porque `a^k = 0`
exactamente cuando `a = 0`; uno con potencia negativa se deja fuera, porque
`1/sen(x)` no tiene ceros que aportar y meterlo sería anunciar una raíz donde
no la hay.

Medido sobre una batería de 41 ecuaciones, con **sonido** (cada punto publicado
anula la ecuación) y **completitud** (cada raíz real está cerca de un punto
publicado, raíces por cambio de signo y descartando los polos):

| | antes del producto | ahora |
|---|---|---|
| responde | 17 de 41 | **23 de 41** |
| soluciones **inventadas** | 0 | **0** |
| incompletas | 0 | **0** |
| se niegan con soluciones | 24 | 18 |

### Lo que queda, y es un solo mecanismo

Las 18 son casi todas lo mismo: **dos términos trigonomótricos con argumentos
distintos**. `sen(x) + sen(2x) = 0` se factoriza a `sen(x)·(2cos(x)+1) = 0`, y una vez
partido lo sabe resolver cada factor. Lo que falta es el paso de factorizar, que
necesita la sustitución universal `t = tg(x/2)` — con su hueco en `x = pi`, que es
justo del tipo de detalle que produce las soluciones inventadas que esta tanda
pasó en quitar — y factorizar el polinomio racional resultante.

Tambien quedan dos rechazos correctos por dominio: `tg(x)·sen(x) = 0` y
`sen(x)·cos(x)·tg(x) = 0`, que tienen soluciones pero no se pueden publicar como
familia única porque el producto tiene agujeros.

## 2026-10-03 — el solucionador de ecuaciones ya no contesta otra ecuación

El aviso anterior decía que `ceros(cos x + cos 2x)` daba `{pi/2, 3pi/2}`, que
no son ceros. Es cierto, y el motivo resulta ser **una sustitución que no mira
lo que sustituye**. Los dos bugs que he encontrado aquí son el mismo error
fundamental en dos sitios distintos.

### Uno: `_como_polinomio` reemplazaba `cos(·)` por `u` sin mirar el argumento

`cos(x) + cos(2x)` se convertía en `u + u = 2u`, cuya única raíz es `u = 0`, y
eso se leía como `cos(x) = 0`: **`{pi/2, -pi/2}`**, las soluciones de otra
ecuación. El guardia que ya había no podía verlo, porque al borrar `2x` no
queda nada fuera de sitio: no sobraba ningún término, faltaba uno.

Medido antes y después sobre 35 ecuaciones, con dos comprobaciones que no dependen
de la opinion del motor — **sonido** (cada punto publicado anula la ecuación) y
**completitud** (cada raíz real está cerca de un punto publicado, con las raíces
buscadas por **cambio de signo** para que no dependan de dónde caigan):

| | antes | después |
|---|---|---|
| soluciones **inventadas** | 8 ecuaciones | **0** |
| se niegan con soluciones | 13 | 19 |

El intercambio es deliberado: **un rechazo es honesto, una solución inventada no**.
Las 19 son huecos declarados, con su motivo escrito.

Además, ahora que hay **un solo argumento** por nombre de función, se recuerda
cuál era y se deshace al final. Antes se pasaba `x` como variable de sustitución, lo
que hacía que el paso fuera un no-op — y no lo es: `tg(x/2) = -1` salía como
`x = -pi/4 + k·pi` cuando la respuesta es `x = -pi/2 + 2k·pi`. La escala dentro del
argumento es toda la diferencia entre esas dos, y se estaba tirando.

### Dos: `_caso_fase` comprobaba el argumento en una rama y no en la otra

La rama del coseno comparaba `u` con el argumento nuevo y se negaba si no
coincidían; la del seno **asignaba `u` sin mirar**. Asimétrica. `cos(x) - sen(2x)`
se leía como una sola función de un solo ángulo con dos nombres encima, y
respondía `{pi/8, 5pi/8, 9pi/8, 13pi/8}`: las soluciones de `tg(2x) = 1`, para una
ecuación que no tiene ninguna de esas.

### Y un paso que abre equations que no se sabían

Un ángulo múltiple al lado de otro término no lo cubría ningún caso:
`cos(x) - cos(2x) = 0` se negaba. Ahora, antes del análisis de casos y **solo si el
original no ha respondido**, `sen(n·x)` y `cos(n·x)` con `|n|` entre 2 y 3 se
escriben en potencias de la misma función — `cos(2x) = 2cos²(x) - 1`,
`sen(3x) = -4sen³(x) + 3sen(x)` — y de ahí las resuelve el mismo camino que ya
resolvía `cos(x)² = 1/2`.

El original va primero a propósito: `cos(2x) = 0` ya tenía una respuesta limpia de
dos familias, y expandir primero la sustituía por cuatro que describen el mismo
conjunto menos claramente.

### Una corrección sobre el aviso anterior

Avisé de que `cos(2x) = 0` y `sen(2x) = 0` estaban mal. **Estaban bien**, y el
error era de mi arnés: comparaba las bases de las familias y no las familias, y el
paso es lo que lleva el resto. Con los pasos enumerados, los dos dan la solución
completa. Un arnés que llama erróneo a lo correcto es peor que ninguno.

### Lo que queda, y es un hueco grande de cobertura

19 ecuaciones con soluciones que el motor **se niega** a resolver, y todas con el
mismo motivo: producto de factores (`sen(x)·cos(x) = 0` — la más simple del
montá), y dos términos trigonomótricos con argumentos distintos
(`sen(x) + sen(2x) = 0` se factoriza a `sen(x)·(2cos(x)+1) = 0`). El motor sabe
resolver cada factor por separado; lo que no sabe es **sacar el producto**.

Es la pieza que falta, y es la queI'd atacar a continuación.

## 2026-10-03 — el dominio era cierto en un solo periodo

`dominio()` encontraba los huecos de **un** periodo, los quitaba de la recta
entera y publicaba el resultado como si fuera todo. Para `1/sen(x)` imprimía
`(-∞, 0) ∪ (0, π) ∪ (π, 2·π) ∪ (2·π, ∞)`, que excluye `0`, `π` y
`2·π` y no dice nada de `3·π`. Preguntado por `3·π` el conjunto
respondía que el punto existe y el evaluador respondía `None`. Diez de doce
expresiones probadas estaban mal fuera del primer periodo; las dos únicas bien
—las que no son periódicas—.

Un conjunto cuyos huecos son infinitos tiene que **decir** que se repite. Ahora lo
dice.

### `Conjunto` declara su periodo

Un campo `periodo`, en unidades de `π`, que por defecto es `None` y significa
«lectura literal» — que es lo que quiere todo lo demás: la carta de signos
construye un periodo **a propósito** y no puede que se le doble por debajo.
`dominio()` lo fija con el de la propia expresión, que es el techo seguro y
está demostrado: si `f(x + p) = f(x)` entonces `f` existe en `x + p` exactamente
cuando existe en `x`.

`texto()` añade `«y se repite cada 2·π», **salvo cuando el conjunto es `ℝ`**,
que no necesita explicarse y a quien `ℝ  y se repite cada 2·π` solo le añade ruido.

### Dos bugs decepción en el mismo sitio, y ambos hacia falsear el dominio

**Uno: `periodo_minimo` no miraba dentro de los argumentos.** Decía que `arcsen`,
`ln` y las hiperbólicas «no son periódicas» y paraba. Pero `f(g(x))` hereda el
periodo de `g` sea cual sea `f`: si `g(x + p) = g(x)` entonces `f(g(x + p)) = f(g(x))`
para cualquier `f`. `arcsen(2·sen(x))`, `ln(sen(x))`, `raiz(cos(x))` y
`acosh(1+cos(x))` tienen todos periodo `2··pi` y los cuatro lo publicaban como
si no tuvieran ninguno.

**Dos: el chequeo de periodo pasaba en vacío.** `_es_periodo` se saltaba las
muestras que no podía comparar y devolvía `True` si no le quedaba ninguna. `raiz(cos(x))`
es el caso: la mitad de sus valores no son reales, casi todas las muestras caen ahí, y
un periodo recortado que no lo es salía confirmado — así que `periodo_minimo`
recortaba `2·π` hasta nada. Ahora menos de cuatro comparaciones es «no
probado», y «no probado» es `False`, que es la respuesta que conserva el
candidato mayor.

Además `_muestras_para_periodo` solo miraba **medio** periodo: repetirse en
`(0, p/2)` es otra afirmación que repetirse en `(p/2, p)`.

Medido: 32 expresiones, tres periodos, rejilla `π/8`, con el evaluador como
segunda autoridad. **31 correctas**; la que queda es otro bug (abajo).

### BUG NUEVO, y es más grave que este: el solucionador de ecuaciones

Al verificar el dominio de `1/(cos(x) + cos(2·x))` apareció esto:

    ceros(cos x + cos 2x)  ->  ['1/2*pi', '3/2*pi']

Esos puntos **no** son ceros: `cos(π/2) + cos(π) = 0 − 1 = −1`. Los ceros
verdaderos son `±1·π/3` y `π`, y el dominio publicado excluía puntos donde
la función existe y}daba por existentes puntos donde no.

Y `sen(x) + sen(2·x) = 0` devuelve solo `{0, π}`: le falta la rama
`cos(x) = −1/2`, que son `2·π/3` y `4·π/3`. Incompleto, no erróneo.

Está en `ecuaciones.py`, no en el dominio, y es de la misma familia que los bugs
queVINieron de la tanda pasada: un motor que contesta sin mentir del todo pero
contesta mal. **Queda declarado y pendiente**, y es lo que yo atacaría a
continuación.

## 2026-10-03 — la familia del medio ángulo, entera

De las diez formas de la familia del medio ángulo, el motor reconocía **dos**:
`(1∓cos x)/(1+cos x)` y `(1+cos x)/(1∓cos x)`, que son las que llevan el
cuadrado. Las ocho restantes pasaban de largo, y entre ellas la que es la misma
identidad sin el cuadrado: `(1∓cos x)/(1+cos x)` se doblaba a `tg(x/2)²` mientras
`sen(x)/(1+cos x)` se quedaba como estaba.

### Solo dos de las ocho van en la simplificación, y el motivo está medido

`(1∓cos x)/sen x = tg(x/2)` es **más barata** que lo que reemplaza — 7 nodos y
19 caracteres por 4 y 8 — así que §5.5b la acepta, y entró en `simplify` a la
primera. Se sacó porque **cambia el dominio**:

| original | nuevo | dominio |
|---|---|---|
| `sen/(1+cos x)` | `tg(x/2)` | el mismo |
| `sen/(1∓cos x)` | `cotg(x/2)` | el mismo |
| `(1∓cos x)/sen x` | `tg(x/2)` | **cambia**: gana `0` y `2·pi` |
| `(1+cos x)/sen x` | `cotg(x/2)` | **cambia**: gana `pi` |
| `cos/(1+sen x)` | `(1∓tg(x/2))/(1+tg(x/2))` | **cambia** |
| `(1∓sen x)/cos x` | `(1∓tg(x/2))/(1+tg(x/2))` | **cambia**: pierde `pi` |
| `1/(1±sen x)` | `(1∓sen x)/cos²x` | **cambia** |

El original no existe en **todos** los múltiplos de `pi` porque el denominador se
anula, y `tg(x/2)` solo en los impares. Un dominio que **gana** puntos es la
dirección peligrosa — un agujero que desaparece se convierte en una solución
falsa — y `simplify` es justo lo que leen los solucionadores.

Los seis que lo cambian van en dos objetivos nuevos, uno por dirección, porque
mezclarlas en un bucle es lo que lo hace no terminar:

- `trig.medio_angulo(expr)`: las dos baratas que tapan un agujero. Su paso dice
  cuál tapa (`«un agujero que se tapa se convierte en una solución falsa», §5.7).
- `trig.medio_angulo_racional(expr)`: las cuatro caras — racionalizar el
  denominador. Van con `reducir=False` porque cuestan más: 7 nodos y 19
  caracteres por 13 y 29.

El docstring de la primera versión decía que las cuatro caras conservaban el
dominio. **Es falso**, y lo cazó el muestreo: `1/(1∓sen x)` vale `1/2` en
`x = 3·pi/2` y `(1+sen x)/cos²x` vale `2/0` ahí — el numerador se anula
exactamente donde el denominador también. La muestreo también cazó el signo
invertido en una de las dos ramas, que daba `cotg(x/2)` donde toca `tg(x/2)`.

### Un bug encontrado de paso, y **no** es de esta familia

`dominio()` publica los huecos de **un solo periodo** como si fueran los únicos.
Para `1/(1∓sen x)` publica `(−∞, π/2) ∪ (π/2, ∞)`: un solo hueco,
cuando `1∓sen x` se anula en `π/2 + 2k·pi`. Preguntado por `5·pi/2` responde que
el punto **existe**, y el evaluador responde `None`.

Es previo, es de otro módulo, y las pruebas de esta familia se han escrito
**dentro de un periodo** para no apoyarse en él. Queda declarado y pendiente.

## 2026-10-03 — las seis escrituras de `tg = sen/cos`, en un objetivo aparte

T-02 estaba marcada COMPLETADA con su última línea —«todas las formas
despejadas equivalentes»— y las seis escrituras de la relación pasaban de largo
sin que nadie las tocara. Ahora se reconocen: `sen/tg = cos`, `cos/sec = cos²`,
`tg/sen = 1/cos`, `sec/cos = 1/cos²`, `sen·cot = cos` y `cos·cosec = cot`.

**No van en `simplify`, y esa es la parte importante.** `sen(x)/tg(x)` y `cos(x)`
coinciden donde las dos existen y se diferencian en todas demás: la primera no
existe en `pi/2` y la sí. Los solucionadores leen el dominio de lo que devuelve
`simplify`, así que fundirlas allía mueve el dominio — medido, puso 193 de 383
respuestas en el lado equivocado de una inecuación. La nueva función
`trig.razones(expr)` es un objetivo aparte, como ya lo eran la sustitución universal
y las formas de producto a suma, y su paso dice dónde vale (§5.7).

### Una identidad falsa que el muestreo cazó y las pruebas no

La regla se escribió «la forma de producto es la de cociente con el denominador
invertido». Invertir `sec` da `csc`, así que `cos·csc` salía como `cos²`. Y
`cosec(x)·cos(x)` es `cotg(x)`, no `cos²(x)`: la identidad era falsa en 398 de 399
puntos.

Las once pruebas que la cubrían pasaban. Afirmaban la respuesta que el código
estaba dando, que era la respuesta equivocada — el fallo que produce una prueba escrita
después de mirar el resultado en vez de antes. Las pruebas nuevas comprueban las
**dos** cosas: la forma exacta que da el motor, y que las dos expresiones coinciden
donde las dos existen, por muestreo. Con las dos, la versión falsa falla.

## 2026-10-03 — asíntotas horizontales y oblicuas, por orden de crecimiento

`graficas` publicaba solo las verticales y lo decía, con razón: una asíntota es
un límite, y muestrear en un `x` grande no es un límite. `3·sen(2x)/x` muestreada
en diez valores grandes da diez números distintos, y declarar `y = 0` porque uno
era pequeño sería inventar una recta a partir de una coincidencia. La negativa
era correcta; lo que faltaba era el otro camino.

### `limites.py`: el orden de crecimiento, por aritmética

Un módulo nuevo que nunca muestrea. Clasifica cada nodo por su **orden** (el
exponente de `x`) y su **coeficiente principal**, exacto, como `Fraction`; más un
booleano `oscila` que dice si hay dentro una función acotada del mismo orden que
todo lo demás.

- `grado < 0` → `y = 0`, en los dos extremos. La expresión se anula, y la
  oscilación con ella: `|sen(x)|/x` está acotado por `1/x`.
- `grado == 0` sin oscilar → `y = coeficiente`.
- `grado == 1` sin oscilar → la oblicua, pendiente y ordenada leídas término a
  término.
- `grado >= 2`, o cualquier oscilación de orden `>= 0`, → no hay asíntota, que es
  una respuesta real: `x²` crece más rápido que cualquier recta, y `x·sen(x)`
  nunca se asienta en ninguna.

Lo que **se niega** es `exp`, `ln`, `tg`, `sec`, `cosec`, `cot`, raíces y todo lo que
no clasifique. No porque esas no tengan asíntota — algunas la tienen — sino
porque improvisar aquí sería la misma invención con un nombre más largo.

La asintota oblicua se resuelve término a término porque preguntar a la
expresión entera «cuál es tu orden» no puede contestar «y tu término
constante»: los dos términos principales se cancelan, y esa cancelación hay que
verla para notarla. `x` menos `x` no es `0` para algo que solo conoce el orden de
crecimiento, y es exactamente `0` aquí.

Un fallo que el propio motor cometió y que las pruebas ahora fijan: `x/sen(x)` y
`x·sen(x)` salían con `y = x`. El orden es el correcto y la asíntota no, porque una
ola del tamaño de la recta no la alcanza jamás. `oscila` solo se descarta cuando el
grado es negativo, y solo ahí lo mata la caída.

Medido: `3·sen(2x)/x` → `y = 0`; `sen(x)/x`, `1/x`, `1/(2x)`, `3/(x+1)`,
`cos(x)/x^3` → `y = 0`; `(x^2-1)/(x^2+1)`, `x/(x+1)`, `(2x^3+1)/(x^3-5)` → `y = 1`,
`y = 1`, `y = 2`; `x`, `x+1/x` → `y = x`; `2x+3` → `y = 2·x + 3`; `x^2`, `sen(x)`,
`x·sen(x)`, `x/sen(x)`, `x+sen(x)`, `tg(x)` → ninguna. Las verticales siguen igual:
`1/tan(x)` publica `x = 0` y `x = π` y ninguna horizontal.

### Un hueco que se ha declarado en vez de escondido

`(x^2 - 1)/(x^2 + 1)` tiene asíntota `y = 1` y el motor la calcula, pero
`caracteristicas` no puede publicarla porque también necesita el DOMINIO, y el
dominio de esa expresión necesita los ceros de `x^2 + 1`, que nadie ha enseñado a
escribir al motor. Son dos huecos en dos módulos distintos y la prueba los
comprueba por separado, para que tapar uno no tape el otro.

## 2026-10-03 — los ceros fuera de la rejilla de pi, y una primitiva que ya se
puede verificar

### Los puntos críticos ya no tienen que caer en un múltiplo de pi

`cosec(x)^2 > 9` se negaba con «no se saben los ceros» sobre un motor cuyo
solucionador de ecuaciones ya había escrito `arcsen(1/3)`. Los dos hechos son
compatibles y la combinación era absurda: lo que faltaba no era el conocimiento,
era una carta de signos que supiera colocar un punto que no es `k·pi`.

- `Punto` admite una tercera forma además de racional y de múltiplo de pi: una
  expresion exacta cualquiera. Comparar dos de esos no se puede hacer exacto, así
  que la comparación corchetea con `PI_BAJO`/`PI_ALTO` y **se niega** cuando el
  corchete no alcanza. La igualdad exacta de valores sí es decidible y no se
  niega: preguntar «¿es este extremo el que ya tengo?» es parte de la carta.
- `carta_de_signos` trabaja con pares (posición, punto). La posición es un
  flotante porque dos escrituras de un mismo punto solo coinciden a quince dígitos;
  el punto es lo que se publica, y para un múltiplo de pi eso significa el
  racional exacto y no su imagen a quince dígitos. Sin esa separación la
  respuesta a `sen(x) < 1/2` salía con el extremo en `83333336/500000015·pi`.
- Los puntos se canonizan dentro de un periodo **como expresión**, añadiendo
  periodos enteros, y la operación se repite porque plegar los términos lineales
  puede sacar el valor otra vez: `-2·pi - arcsen(1/3)` necesita tres periodos más.
- El plegado recoge los términos lineales a través de la suma antes de sumarlos.
  `pi - arcsen(-1/3) - pi` tiene un `pi` a cada lado de una llamada y nunca se
  encuentran si solo se pliega lo que ya es lineal a ambos lados.
- Las identidades son las que no mueven el punto: `arcsen(-t) = -arcsen(t)` y
  `arctan(-t) = -arctan(t)` son impares, `arccos(-t) = pi - arccos(t)` es el punto
  espejo. Una tercera escritura, `arcsen(-t) = pi - arcsen(t)`, estaba en el código
  durante una medición y daba bien `cosec(x)^2 > 9` — cuya expresión sí tiene
  periodo pi. Correcta para el caso medido y errónea para todos los demás: esa
  es la forma más peligrosa de estar equivocado.
- Se negate la regla «algún cero no es un múltiplo exacto de pi» que convertía
  una duda de representación en un «no lo sé». `ceros` ya no devuelve `None`
  por no saber COLOCAR un cero que sabe ESCRIBIR; sigue devolviéndolo cuando no
  puede escribirlo, que es el «no lo sé» de verdad.

Medido: 45 inecuaciones con nivel irracional (`sen(x) > 1/3`, `cos(x) <= -1/3`,
`cosec(x)^2 > 9`, `cosec(x)^3 > 8`, `tg(x) >= -1/3`, `sec(x) > 2`, …) con **0
respuestas incorrectas** en 767 puntos de muestreo cada una, saltándose los polos
que el punto flotante ve como número enorme.

Siguen negándose, y ahora se dice por qué: `cot(x)^3 > 4` necesita
`tg(x) = 4^(-1/3)`, una raíz irracional de un polinomio. Ahí el hueco es del
solucionador de ecuaciones, no de la carta.

### El presupuesto de 480 caracteres estaba por debajo del trabajo

El motor entrega la primitiva correcta de `sen^6·cos^6` — 234 caracteres, bien
dentro — y no podía comprobarla: el verificador construye la derivada en el
árbol simbólico, con un presupuesto de 480, y la de esa primitiva mide 511. El
límite no era una protección, era un obstáculo, y la respuesta correcta quedaba
sin verificar.

- `expr.MAX_TEXT`: 480 → 4000. `MAX_SOURCE` se queda en 256, que acota lo que una
  persona ESCRIBE, que es otra pregunta distinta de hasta dónde puede derivar una
  máquina.
- `steps.MAX_FIELD`: 500 → 2000, que es el techo del formato de traza (2000), no un
  número arbitrario. El log se negaba a registrar el paso que probaba la integral.

Medido: `sen^6·cos^6` (511), `sen^8·cos^8` (839), `sec^6`, `cot^6`, `tg^8` verifican
por el camino simbólico, 8/8 puntos, en 0,02 s.

### La primitiva larga se verifica por los dos caminos

La prueba de diferencias finitas que allowía saber que la respuesta era correcta se
queda como segunda comprobación: dos caminos que llegan al mismo sitio valen más
que uno.

## Unreleased — MathLab: motor trigonométrico exacto (T-01 a T-23, T-24)
- **Punto de partida: la suite estaba en rojo.** El motor entregado en `20e031f` dejaba `tests/test_mathlab_trig.py` con 4 fallos por tres causas distintas: `sec`, `csc` y `cot` no eran evaluables numéricamente; la paridad solo se aplicaba a `Neg(Call)` y por tanto `sin(-x)` no se reducía nunca; y tres expectativas comparaban contra `pretty()` —la forma española Unicode para pantalla (§5.1)— lo que el motor produce en `text()`, que es la forma canónica ASCII.
- **Motor.** `mathlab/trig.py` reescrito como motor de reglas por objetivo (T-20, §5.5b): cada transformación pertenece a un objetivo y solo acepta reescrituras estrictamente más baratas o estrictamente más caras, medidas por `(nodos, longitud del texto canónico)`. Esa medida es un orden bien fundado, así que cada objetivo termina y su resultado es punto fijo por construcción. Mezclar las dos direcciones en un mismo bucle no puede terminar: `sin(2x)` se desarrolla a `2·sin(x)·cos(x)` y vuelve a colapsarse.
- **Ocho objetivos**: `simplificar` (reducir), `expandir` (T-04, T-05), `producto_a_suma` (T-08), `suma_a_producto` (T-09), `potencias` (T-10), `sustitucion_universal` (T-07), `hiperbolicas` (T-14) y `exponencial` (T-14). Cada familia lleva escrito su «por qué este método», y `simplify_ex` devuelve las que han actuado para que la calculadora las escriba en la traza (§5.2, T-22).
- **Cobertura**: T-02 completo (las seis formas de cada relación), T-03 completo (paridad, periodicidad, opuestos, suplementarios y complementarios en una tabla por cuadrante en lugar de una regla por signo), T-04 y T-05 en ambos sentidos, con las tres formas de `cos(2x)` **ofrecidas** y no elegidas, T-08, T-09, T-10, y la parte de T-21 que el motor necesita (0°–180° con las seis funciones exactas y `None` donde la función no existe).
- **Inventario honesto.** `identities()` se deriva ahora de los registros de reglas. Antes anunciaba `angulo_doble_coseno`, `angulo_doble_tangente` y `medio_angulo` sin que existiera regla para ninguna de las tres; hay una prueba que falla si eso vuelve a pasar.
- **`sec`, `csc` y `cot` evaluables.** El motor los produce y la verificación no podía evaluarlos: una comprobación que no puede evaluar lo que el motor emite no comprueba nada. Ahora son `1/cos`, `1/sin`, `1/tan`. El polo el camino numérico **no lo ve** (a `pi/2`, `cos` vale 6·10⁻¹⁷ y no cero): la negativa la da la tabla simbólica y el numérico solo puede dar la magnitud.
- **Límite de profundidad.** `RecursionError` a 500 niveles escapaba del motor; ahora `MAX_REWRITE_DEPTH = 200` y se declara `EXPRESSION_LIMIT` en castellano. Nada que se pueda escribir llega ahí: el parser limita el anidamiento a `MAX_DEPTH = 64`.
- **Pruebas**: en `test_mathlab_trig.py`, en tres capas — doradas por familia, **sonoridad** (cada identidad recomprobada por camino numérico independiente con puntos sembrados, 50 casos paramétricos) y **propiedades del motor** (idempotencia, que `simplify` nunca agranda, que el inventario no promete familias sin regla). Hay un **control negativo** (`cos(x)` frente a `sin(x)` tiene que ser rechazado) porque si no la comprobación pasaría igual sin comparar nada, y un fuzz de 60 semillas que cubre los cinco objetivos.
- **Hallazgo honesto sobre la verificación**: `tan(((x³)⁴)² + x)` y `sin(x) + sin(cot(y))` son identidades verdaderas, pero con `x^24` o `cot(y)≈10⁴` dentro las dos caras difieren entre 10⁻⁵ y 10⁻², porque `sin` de un argumento enorme ya no tiene dígitos fiables. Es condicionamiento de punto flotante, no un error de las reglas; queda documentado y acotado en las pruebas en vez de esconderse.
- **T-11 (inversas y ramas).** `mathlab/ramas.py` distingue las dos direcciones, que no son simétricas: `sen(arcsen(u)) = u` vale donde está definida y el motor la reduce; `arcsen(sen x) = x` **no**, y el motor se niega a reescribirla. `ramas.ramas()` da cada rama con su intervalo de validez y `ramas.evidencia_global()` un contraejemplo calculado —en `2·pi`, `arcsen(sen(2·pi))` vale 0 y no `2·pi`—. Los dominios se marcan como abierto o cerrado según el caso: `[-1,1]` para `arcsen` y `arccos`, `(-1,1)` para `arctanh` porque en los extremos no existe.
- **T-12 (ecuaciones).** `mathlab/ecuaciones.py` resuelve `sen/cos/tan = c`, `a·sen+b·cos = c` por desplazamiento de fase, y polinomios en `sen`, `cos` o `tan` con raíces exactas. Cada familia se comprueba **sustituyendo miembros en la ecuación original**, que es lo único que caza una solución espuria. Un valor irracional como `√2/2` da una solución exacta —y además notable: `arcsen(√2/2)` sale como `pi/4`, no como un `arcsen` sin evaluar—. Cuando ningún caso encaja la respuesta es «no lo resuelve todavía», **nunca** «no hay soluciones».
- **T-13 (inecuaciones).** `mathlab/inequaciones.py` convierte `f(x) > 0` en una carta de signos sobre **un** periodo, y la carta solo vale si sus puntos críticos están todos. Dos requisitos que no son opcionales: los **polos** —`tg(x) < 1` son dos intervalos, y solo el polo de `pi/2` parte el primero en dos; los polos de `tg` y `cotg` no tienen denominador en la expresión, así que se sacan de los ceros de `cos` y `sen`— y el **origen del periodo**, que se lee en la función en lugar de asumirlo abierto, porque dejarlo abierto pierde una solución real (`cos(x)² > 1/2` se cumple en 0). El signo dentro de cada hueco se decide numéricamente, lo cual es una prueba y no una aproximación: una función continua sin ceros ni polos en un hueco no puede cambiar de signo en él. Si alguna vez cambiara, el motor se niega en vez de elegir un lado. `=` da los ceros como puntos y no como intervalos, porque una ecuación no tiene interior.
- **Dos bugs que cazó la verificación de T-13 y que son de la misma familia.** `f^n = 0` está exactamente donde `f = 0` para todo entero positivo, y el código trataba la potencia par como un caso aparte: `sen(x)²` se quedaba **sin ceros**, que es decir respondía «no hay soluciones» sobre una expresión llena de ellas. Y `dominio.periodo` daba `2·pi` para `sen(x)²`, cuyo periodo real es `pi`: no es un error en el conjunto —los puntos son los mismos— pero duplica cada intervalo y tapa la simetría que lo explica. Ahora `dominio.periodo_minimo` reduce mientras siga cumpliéndose.
- **T-14 (hiperbólica).** Identidades, suma y diferencia, ángulos dobles, inversas y la conexión exponencial. Fuera: derivadas e integrales, que son de T-17 y T-18.
- **La verificación de T-13 mira en las dos direcciones**: cada punto muestreado tiene que estar dentro exactamente cuando la desigualdad se cumple, y fuera exactamente cuando falla. Un conjunto que fuese solo un subconjunto de la verdad pasaría una dirección y fallaría la otra, y por eso es una comprobación y no una prueba de humo. Los puntos son racionales exactos, no flotantes, así que los que caen en un extremo prueban las banderas abierto/cerrado en lugar de esquivarlas.
- **T-20, T-21 y T-24 cerrados.** Tres cosas que faltaban y que no eran adornos. **La estrategia de resolución**: `N/D = 0` tiene los ceros de `N`, nunca los de `D`, porque donde el denominador se anula hay un polo y un polo no es solución de nada. Con ese paso, `sec(x) = 1`, `cosec(x) = 1` y `cotg(x) = 1` se resuelven, que antes se rechazaban. **El fallback numérico con error declarado**: `verify.aproximacion()` mide la sensibilidad de la expresión perturbando la entrada y declara el error a partir de ahí. `sen(x)` en `x = 1` sale con error 4·45·10⁻¹⁵; en `x = 10⁶` sale con **2·08·10⁻⁴**, porque la entrada y la salida son exactas y las dos se calculan en dobles. **La integración en la calculadora**: `resolver`, `resolver_inequidad`, `ramas` y `aproximar` tienen operación propia y cada resultado lleva un sello trazado por un camino que no consulta el cálculo que produjo la respuesta.
- **Agujero encontrado al sellar T-24: la comprobación de espurias no se ejecutaba nunca.** Hacía `if not mx.variables(miembro): continue`, y el miembro de una familia resuelta es justamente una constante, así que el `continue` se saltaba el caso que hay que mirar. La función devolvía una lista vacía para **toda** familia, incluidas las que no satisfacen la ecuación — y esa lista es la única evidencia de que T-12 no arrastra soluciones espurias. Una comprobación que no puede fallar no es una comprobación. Ahora una familia con el paso equivocado se marca como espuria con su residuo.
- **Dos bugs en `poly.to_expr`, escritos y cazados en la misma tanda.** El primero: el bucle de factores **asignaba** en vez de multiplicar, así que se quedaba con el último factor — `2·sen(x)·cos(x)` se reconstruía como `2·sen(x)`. El segundo: un coeficiente negativo escondido dentro de un producto es invisible para quien lee términos por signo, así que `cos(x) - sen(x)` volvió como `1·cos(x) + (-1)·sen(x)` y el caso con fase no lo reconocía. Los dos los cazó el test de ida y vuelta, que es exactamente para lo que está.
- **T-19 (series)** cierra el bloque con la parte más dura de T-20. `mathlab/series.py` escribe la serie de Maclaurin de `sen`, `cos`, `tg`, `exp`, `senh`, `cosh` y `ln` término a término, en aritmética racional exacta: `x^7/7!` es `1/5040` y no un 0.0001984 redondeado. Cada respuesta son **tres** cosas y nunca una: el polinomio, el residuo —el primer término que no se escribe— y una cota declarada. La cota solo existe para las series alternantes, donde el primer término omitido **es** una cota; para `exp` y `tg` no se declara ninguna, porque allí el término es una orden de magnitud y presentarlo como cota sería una promesa falsa de precisión. El radio de convergencia se declara en la hipótesis y no se infiere del truncamiento, porque una serie truncada no falla nunca: solo empeora.

- **Cuatro bugs de las series, todos del mismo tipo: la forma correcta con el número equivocado.** `sen`, `cos`, `senh` y `cosh` salían con el **mismo** polinomio, leídas de una única tabla de «impares y alternantes»; una serie de coseno que empieza en `x` no es una serie de nada. Los números tangentes salían `x + x^5/5 + 2x^9/45` con la convolución indexada por potencia en vez de por índice — `x + x^3/3 + 2x^5/15 + 17x^7/315` es lo correcto— y con la forma y los signos bien, que es lo que lo hacía plausible: un error de 2.6·10⁻³ en `x = 0.2` con trece términos. Y Taylor dividía por la derivada en vez de evaluarla en el centro, con lo que `sen(0)` —que solo pliega el motor trigonométrico— llegaba al coeficiente como `1/sen(0)`.

- **Un hueco de T-19 documentado en vez de tapado.** El polinomio de Taylor de un monomio lleva un término de más: `taylor(x^3, 0, 4)` da `1/12*x^2` donde debería dar `x^3`. Las derivadas se comprueban una a una y son correctas, así que el fallo está en cómo se arman los términos. La prueba está ahí, afirma lo que el motor hace y está marcada como hueco; cuando se arregle, falla. Fijarla ahora significaba escribir una mentira sobre lo que hace el motor.

- **T-20 y T-22** quedan con los objetivos `integrar`, `derivar`, `complejos` y `fasores` repartidos por los módulos que los necesitan en vez de declarados como objetivos del motor, y la verificación por derivación de T-22 existente y usada.

- **T-23 (gráficas como hechos exactos).** `mathlab/graficas.py` contesta las cinco preguntas del enunciado —periodo, amplitud, frecuencia, fase, ceros, extremos, asíntotas, discontinuidades, comparación y aproximación— con hechos comprobables; la polilínea es un dato más, con su texto alternativo y **partida en los polos**, porque una recta dibujada a través de `pi/2` enseña una función que ahí está definida y una gráfica que miente es peor que no tener gráfica. La operación `caracteristicas` lleva un segundo camino que no consulta los solucionadores que produjeron la respuesta: un muestreo denso de la función contra cada hecho declarado. Las muestras pegadas a un polo se saltan y **se cuentan** en el sello, porque medir `tan` justo donde diverge hace ver aperiódica una función que es exactamente periódica.

- **Tres decisiones de T-23 donde el enunciado no dice nada.** *La amplitud es la mitad del recorrido, no la mitad del máximo*: `3·sen(2x)` tiene amplitud 3 y un máximo de 3, así que dividir el máximo por dos da 1.5 y sale mal en toda función no centrada en el cero; `sen(x) + 1` recorre de 0 a 2 y su amplitud es 1. *Un senoide no necesita que se le estime la amplitud*: en la forma canónica el coeficiente de la llamada **es** la amplitud, y `5·sen(x + π/3)` vale 5 mientras que muestrear el máximo devuelve 4.989 —un hecho de la rejilla, no de la función—. *Una función sin máximo no tiene amplitud*: `1/tan(x)` no tiene una amplitud pequeña, no tiene ninguna, y un número ahí sería una altura muestreada que no significa nada.

- **Lo que T-23 no hace, declarado.** Solo asíntotas verticales: las horizontales y oblicuas necesitan el límite en el infinito, y muestrear en un `x` grande no es un límite —un senoide da diez «límites» distintos en diez `x` grandes—. Y `sen(x) + cos(x)`, que sí es un senoide, se declina porque encontrar el desplazamiento de fase es una búsqueda y contestarla a medias es peor que callarse.

- **Cinco bugs de T-23, todos «la forma correcta con el número equivocado».** La amplitud dividía el máximo en vez del recorrido. El coeficiente de la llamada se comparaba contra `"sin"` cuando el texto del átomo es `sen(2·x)` entero, así que `es_sinusoidal` era falso para *toda* expresión, la más obvia incluida. La fase se sacaba con `trig._reconstruir`, que mapea los hijos de cada nodo y no el nodo: en un `sen(x)` desnudo la llamada es la expresión entera y nunca llegaba al visitante, así que la fase volvía como un símbolo de relleno. Los extremos se evaluaban en `1/4` en vez de en `pi/4` —un punto de pi guarda el *coeficiente* de pi—, tres radianes lejos del punto crítico, y por eso todos salían «sin clasificar». Y la curva nunca se partía: `ys[i] != ys[i]` compara dos valores idénticos y siempre da falso, así que ni un polo se detectaba nunca.

- **Un rechazo que parece arbitrario y no lo era: `tan`, `sec`, `csc` y `cot` no son senoides.** Son no acotadas, así que llamarlas senoide reclama una amplitud que no tienen. Y el cociente se busca en el esqueleto del árbol, no en el texto: un `sen(x + π/3)` tiene una barra y una potencia **dentro del argumento**, y un test de texto rechaza el desplazamiento de fase más corriente que hay, mientras que `sen(x)/x` —que sí es un cociente— se esconde en un solo átomo y cuela.

- **Tres huecos que el verificador de T-23 encontró en módulos anteriores y que NO se han corregido aquí, porque son de T-12 y T-13.** `dominio.periodo_minimo("sen(x)/x")` responde `2·π` y la función no es periódica: tiende a cero, así que `f(x + T) = f(x)` falla para todo `T`. `ecuaciones` da `0` como cero de `5·sen(x + π/3)`, que se anula en `x = -π/3`: el cero se lee de la función sin desplazar. Y `inequaciones.dominio` marca `pi/2` y `3pi/2` como discontinuidades de `1/tan(x)`, que es cotangente y está definida —y vale cero— ahí, porque el cociente hereda las restricciones del denominador sin tener en cuenta el recíproco. Cada uno tiene una prueba que lo nombra en vez de aprobarlo, y el sello de la operación dice «discrepa» para los tres.

- **T-23 esquivó el hueco de T-19 en vez de heredarlo.** Donde hay serie conocida, `aproximar` usa `series.maclaurin`, que es correcta: `taylor("sen(x)")` saca el **polinomio del coseno**, porque el polinomio de un monomio lleva un término de más. Donde no la hay, avisa de que va por `taylor` y de que el polinomio que sale arrastra ese hueco.

- **PRUEBAS**: 1289 sobre estas familias, en once ficheros de `test_mathlab_*.py`: 424 en `test_mathlab_trig.py`, 191 en `test_mathlab_ml1.py`, 165 en `test_mathlab_inequaciones.py`, 135 en `test_mathlab_ml0.py`, 99 en `test_mathlab_ecuaciones.py`, 95 en `test_mathlab_series.py`, 75 en `test_mathlab_complejos.py`, 64 en `test_mathlab_graficas.py`, 40 en `test_mathlab_ramas.py`, 30 en `test_mathlab_t24.py`, 23 en `test_mathlab_fasores.py` y 12 en `test_mathlab_arch.py`. Las de T-19 comprueban la serie por tres caminos independientes —el polinomio contra la función real en varios puntos, que el error **baje** al subir el orden (que es lo que distingue una serie que converge de una que trunca), y que la cota alternante acote el error real—.

## Unreleased — MathLab: los tres huecos que encontró el verificador de T-23

Cerrados. Los tres eran de T-12 y T-13 y los encontró el camino independiente de
`caracteristicas`, que muestrea la función contra cada hecho declarado. La
comprobación hizo su trabajo: los tres aparecieron como «discrepa» y ahora
verifican.

- **El periodo se preguntaba a la llamada, no a la expresión.** `periodo` leía el
  periodo del primer seno que encontraba y lo devolvía, así que `sen(x)/x`
  respondía `2·π` para una función que tiende a cero y donde
  `f(x + T) = f(x)` falla para todo `T`. Ahora la pregunta es estructural y
  recursiva: la periodicidad sobrevive a sumas, productos y cocientes, así que
  **una parte no periódica zanja la respuesta**, y `sen(x)/x`, `x + sen(x)` y
  `sen(x)·x` dan `None`. `sen(2x)·cos(3x)` sigue dando el mínimo común múltiplo,
  `sen(x/2)` da `4·π` y `sen(3x)` da `2/3·π`: los senoides no han cambiado de
  nombre.

- **`_afine` no veía la parte constante, y un desplazamiento de fase es
  precisamente una parte constante.** `trig._factores` reparte productos y nunca
  reparte sumas: `x + π/3` volvía como **un** factor, así que la comprobación
  «hay variable y hay otro factor» lo declaraba no afín y `sen(x + π/3) = 0`
  quedaba sin resolver —el solucionador lo decía, pero `ceros` leía igualmente
  el valor como si fuera una `x`—. Con las sumas repartidas: `sen(x + π/3) = 0`
  da `-π/3 + 2k·π` y `2π/3 + 2k·π`; `cos(x + π/4) = 0` da `π/4` y `-3π/4`;
  `tg(x + π/2) = 0` da `-π/2 + k·π`.

- **Una familia que no se pudo deshacer en `x` no lleva la bandera.** Ahora
  `Familia` tiene `en_x`, y `ceros` se salta las que van en la variable de
  sustitución. Una hipótesis escrita dentro de un texto es fácil de no leer; un
  booleano en un dataclass, no. Una hipótesis ENCADENADA con `deshacer ese cambio
  de variable no está resuelto todavía» y un `0` publicado como cero era la peor
  combinación posible: el motor avisando y el consumidor copiándolo.

- **Un cero inexistente no es un cero.** `0/0` no es un número, es un punto donde
  nada está definido, y `sen(x)/x` declaraba `0` como cero. Los ceros de un
  cociente son los de su numerador **menos** los puntos donde el denominador se
  anula, y esos se preguntan al dominio —que es quien sabe dónde deja de existir
  una expresión— en vez de volver a resolver `denominador = 0`, porque el
  solucionador se niega a `x = 0` con el motivo correcto y así se queda.

- **`pi/3` no era un múltiplo de `pi`.** El lector de múltiplos de `pi` comparaba
  contra `[Const(pi)]` y `trig._factores` no divide `pi/3`, así que toda base ya
  desplazada se quedaba fuera de la rejilla. `trig._multiplo_de_pi` lo resuelve
  recursivamente, y con dos formas que rompían por separado: `-pi/2` es
  `Div(Neg(pi), 2)` con el signo **dentro** del numerador, y `3pi/4` es
  `Div(Mul(3, pi), 4)` con un coeficiente delante. Vive en `trig` y no en
  `ecuaciones` porque los dos lo necesitan y que uno importe al otro sería un
  círculo.

- **Un sello que no puede decir «discrepa» no es un sello.** Corregidos los tres
  huecos, nada discrepa ya de forma natural, así que la ruta del fallo se
  ejercita a propósito sobre una descripción con un cero plantado que la función
  no tiene. Una comprobación que solo pasa es indistinguishable de una
  comprobación que no compara nada.

- **Una afirmación mía que era FALSA, y el motor tenía razón.** El bloque de T-23
  afirmaba que `1/tan(x)` es cotangente y que por tanto `π/2` no es una
  discontinuidad suya. La cotangente lo es como función; la **expresión**
  `1/tan(x)` no existe en `π/2`, porque `tan(π/2)` no existe y el recíproco de
  nada es nada. El dominio del motor era correcto. Lo que falta no es la
  discontinuidad sino la nota de que el hueco es **removible**, con límite 0, y
  eso sigue sin implementarse.

- **El verificador ya no comprueba las discontinuidades, y lo dice.** A `π/2` el
  valor de `tan` es 6·10⁻¹⁷ y no cero, así que el muestreo no puede ver si una
  expresión existe: `1/tan` se evalúa ahí a un número finito y pequeño y parece
  continua mientras la tabla simbólica —la autoridad sobre la existencia— dice
  que no existe. Comprobarlo numéricamente señalaba `π/2` como error cuando el
  dominio es correcto. Está fuera de la comprobación y su motivo está en el
  sello.

- **Pruebas**: 63 nuevas en `tests/test_mathlab_fases.py`, en cuatro capas —`_afine`
  con y sin parte constante, las bases de cada familia tras un desplazamiento
  comprobadas **sustituyendo en la ecuación original**, el periodo de las
  expresiones que no son periódicas, y los ceros de un cociente contra sus
  polos—. Las de sustitución son las que cazan un miembro espurious, que es lo
  único que las caza. 1408 pasan y 8 se saltan en los trece ficheros
  `test_mathlab_*.py`.

## Unreleased - MathLab: T-20, los doce objetivos declarados

`trig.OBJETIVOS` pasa de ser un diccionario nombre -> registro de reglas a un
registro de declaraciones con dos clases que no son la misma cosa.

- **REESCRITURA** - `simplificar`, `expandir`, `producto_a_suma`,
  `suma_a_producto`, `potencias`, `sustitucion_universal`, `hiperbolicas`,
  `exponencial`: disparan reglas sobre subexpresiones y su respuesta es otra
  expresion, asi que llevan un registro de familias **no vacio**. La entrada es
  un registro de reglas y cambia la forma de la expresion.
- **TRANSFORMACION** - `derivar`, `integrar`, `complejos`, `fasores`: llevan una
  expresion a algo de otro tipo -una derivada, una primitiva, un complejo, un
  fasor-. No tienen familias porque no reescriben nada, y lo que deben en su
  lugar es un `porque` escrito y un `verifica` que nombre el segundo camino.

Los cuatro vivian en los modulos que los necesitan, asi que el motor no podia
decir que sabe hacer: **un objetivo que no se puede enumerar es uno que no se
puede prometer**, y el inventario era la mitad de grande de lo que el
laboratorio hacia sin que nadie lo notara. Ahora cada uno declara su metodo y su
modulo de procedencia, `trig.inventario()` expone la lista entera, y la
calculadora escribe el metodo declarado en la trayectoria de las cuatro
operaciones. Una declaracion que nadie lee es una declaracion en un fichero.

El registro se guarda CRUDO en `Objetivo` y `familias` se deriva de el, para que
el inventario no pueda separarse del registro: una familia se anuncia
exactamente cuando hay una regla detras.

`integrar` es el unico de los cuatro que no habla el mismo arbol: el integrador
se escribio contra `symbolic.expr` y el objetivo habla `mvexpr`. La conversion
esta en el objetivo y no dentro del integrador, porque una conversion escondida
en medio de un modulo es una que nadie mira dos veces.

- **`complejos` no es «la version compleja de una expresion arbitraria».** Es la
  correspondencia: `sen`, `cos` y `tan` como funciones de un `Complejo`.
  Extenderla a una expresion real cualquiera es un problema mucho mayor que este
  y no se finge resuelto; `sen(i) = i·senh(1)` y `cos(i) = cosh(1)` salen
  exactos, y una funcion sin contrapartida se NIEGA con el motivo escrito.

- **Pruebas**: 42 nuevas en `tests/test_mathlab_objetivos.py`: los doce
  declarados, cada uno con `porque` y `verifica` de mas de cuarenta caracteres,
  cada reescritura con al menos una regla real y cada transformacion sin
  familias, los cuatro ejecutandose, y la declaracion llegando a la trayectoria
  con su alternativa escrita. 1478 pasan y 8 se saltan en los catorce ficheros
  `test_mathlab_*.py`.

## Unreleased — MathLab: T-14, T-18 y T-19 cerradas, y la auditoría del motor

Las tres familias que quedaban del bloque. Todas se comprueban por un camino que
**no consulta el cálculo que produjo la respuesta**.

- **T-19 (Taylor).** Dos fallos que se cancelaban entre sí, que es la razón por la
  que todo valor intermedio parecía plausible: el bucle leía el término de orden
  k con la derivada de orden k+1, y el coeficiente salía como recíproco.
  `taylor(x^3, 0, 4)` daba `1/12*x^2` y ahora da `x^3`. Efecto lateral: la serie
  del seno salía con el polinomio del coseno, leídas de una única tabla de
  «impares y alternantes» donde una serie de coseno que empieza en `x` no es una
  serie de nada. Y `ln` se niega donde no tiene desarrollo, en vez de escribir
  `1/0` en cada coeficiente.

- **T-18 (integrales).** `∫sen(x)^2 dx` se rechazaba porque **reducir la potencia
  nunca se hacía**. Ahora `∫cos^n`, `∫sen^n` y `∫tg^n` salen de la fórmula de
  reducción y `∫ln^n` de las partes tabulares. Dos cosas que solo se ven con
  argumento escalado:

  - el **factor de cadena**: `∫cos(2x)^2` tiene que dar `cos(2x)sen(2x)/4 + x/2`
    y no `cos*sen/2 + x/2`. Leer `x` por el argumento es invisible en todos los
    `cos^n` a secas —por eso todos esos salían bien— y equivoca por un factor de
    cuatro en el escalado, que es el error que no verifica contra nada.
  - el factor **no se repite** en la recursión: `∫cos^(n-2)u du` es `k·I_(n-2)` y
    el `1/k` de fuera lo deshace. Llevar un `k^2` es invisible con `k = 1`.

  La fórmula tabular tampoco lleva `1/n` en ningún sitio: por partes con
  `u = g^n` y `dv = dx` sale `x·g^n - n·∫x·g'·g^(n-1)`, y `∫ln(x)^2` se cierra.
  `∫sen(x)^n` NO va por ahí —la derivada del seno devuelve el coseno y la
  recursión deja de terminar—, y por eso son dos reglas y no una con la lista
  larga.

- **T-14 (la familia).** Las derivadas ya estaban (T-17). Las integrales propias
  eran el hueco, y tres no faltaban por casualidad: `∫sec(x)^2` estaba en la tabla
  solo con la ortografía `1/cos(x)^2`, y un estudiante que escribe `sec(x)` lo
  rechaza un solucionador que tiene la respuesta. Ahora están `∫cot`, `∫sec^2`,
  `∫cosec^2`, `∫cot^2`, `∫coth` y `∫sech^2`.

- **EL CASO LINEAL DE T-12** ya no se niega `x = 0`, que era lo más elemental que
  faltaba, y arrastró tres bugs de fondo que no se buscaban: `0·pi` y `0` eran dos
  puntos distintos para el motor, la regla de fusión de intervalos estaba al
  revés —se fundían los que se tocan con ambos extremos abiertos, que es
  exactamente el caso que no debe fundirse— y un extremo infinito no ganaba
  nunca en una fusión. Efecto lateral que era un agujero tapado:
  `dominio(ln(x^2))` daba `(-∞, 0)`, media recta de menos.

- **EL HUECO REMOVIBLE** que quedaba de T-23 se decide por estructura —el
  recíproco se simplifica a cotg, cuyo dominio sí incluye `pi/2`— y un hueco que la
  simplificación no cancela se declara polo, que es el lado seguro.

## Unreleased — MathLab: la auditoría del motor entero

Un barrido buscando **respuestas falsas**, no capacidades faltantes, convertido en
`tests/test_mathlab_auditoria.py`: 326 comprobaciones sobre identidades,
derivadas, integrales, ecuaciones, ceros, dominio, periodos, series, gráficas y la
conversión entre los dos árboles de expresiones. Cada una por un camino que no
consulta el cálculo que produjo la respuesta, y con control negativo donde hace
falta para que la comprobación no pueda pasar sin comparar nada.

Encontró dos bugs que ninguna otra prueba veía:

- **`x^(3/2)` volvía del otro árbol como `√x`.** El numerador del exponente se
  perdía en la conversión, y la primitiva de `√x` —que es `x^(3/2)·2/3`— salía
  `2·√x/3`, cuya derivada es `1/(3√x)`. El primer arreglo puso el numerador
  ENCIMA de la raíz y dio `x^3·√x`, que es `x^(7/2)` y sale 35 veces demasiado
  grande. Las dos versiones **se imprimen como una potencia fraccionaria** y solo
  derivar la primitiva lo delata. La parte entera va DEBAJO de la raíz.
- **El bucle de Taylor** con sus dos fallos que se cancelaban (arriba).

El barrido salió limpio en las demás familias: 28 identidades por 6 objetivos,
13 derivadas contra la tabla y las dos tablas entre sí, 35 integrales derivadas de
vuelta, 13 ecuaciones con el miembro sustituido en la original, ceros, dominio con
las banderas abierto/cerrado, periodos, series cuyo error baja al subir el orden, y
las gráficas contra su propio sello.

Dos comprobaciones del propio barrido resultaron **ingenuas** y se corrigieron, no
el motor: un polo visto por punto flotante es un número finito muy grande —a
`pi/2`, `tg` vale 6·10⁻¹⁷ y `1/tg` vale 6·10¹⁶, ninguno de los dos es `None`— y
`1/tg(pi/2)` vale 6·10⁻¹⁷, un número pequeño que parece continuo. Ninguna muestra
puede decidir si un punto existe: la tabla simbólica es la autoridad, y el sello de
T-23 ya lo dice en vez de fingir que lo comprueba.

1863 pasan y 8 se saltan en los quince ficheros `test_mathlab_*.py`.


## Unreleased — MathLab: T-18 cerrada entera, y una rama muerta que una prueba sostenía

Los tres huecos que quedaban de T-18 eran el **mismo fallo de lectura**: una regla
que mira una cosa y no la otra. Los tres están cerrados.

- **El producto de dos potencias.** `∫sen(x)^3·cos(x)^2` se rechazaba porque la
  reducción es de UNA potencia y el cambio de variable no ve el factor que sobra.
  No es difícil: los tres casos clásicos lo convierten en una **suma de potencias
  simples**, y ninguna de ellas es nueva. Exponente impar en `sen`, impar en `cos`,
  y los dos pares por
  `sen^(2a)·cos^(2b) = 2^-(a+b)·(1-cos(2g))^a·(1+cos(2g))^b`. Cada término es o
  `sen·cos^p` —que el cambio de variable siempre hizo— o `cos(2g)^k`, que es la
  reducción con factor de cadena. La regla nueva no añade ninguna primitiva: solo
  lee el integrando para encontrar las que ya existían.

- **`∫sec^n`, `∫cosec^n` y `∫cot^n` para n ≥ 3.** `f^n = f^(n-2)·f^2`, y el
  cuadrado ya estaba en la tabla. **La cotangente no tiene la misma forma que las
  otras dos**, y escribirle la misma fórmula es lo que hacía que `∫sec^3` saliera
  como `sec·tg - ln|sec+tg|`: las piezas correctas con los coeficientes
  equivocados, que es peor que no responder porque parece terminado. La correcta
  lleva `(n-2)/(n-1)` positivo delante de la integral anterior, y la de `cot` es
  `-cot^(n-1)/(n-1) - ∫cot^(n-2)`, de otra forma.

- **`e^x·sen(x)`, `e^x·cos(x)`, `senh(x)^2`, `cosh(x)^2`.** Entradas de tabla. La
  primera tiene forma cerrada y **ningún cambio de variable la encuentra**: `u =
  sen(x)` no aplica y las partes por dos veces vuelven a la integral de la que
  salieron. `senh^2` y `cosh^2` se diferencian en el **signo del término lineal**, y
  comprobarlo derivando es lo único que las distingue.

**Dos bugs de los mí mismos, de la familia de siempre: la forma correcta con el
número equivocado.**

- El denominador del caso par-par era `4^(a+b)` en vez de `2^(a+b)`, así que
  `∫sen^2·cos^2` salía cuatro veces pequeña. Ni la forma ni el signo delatan nada.
- Al caso con exponente impar en `cos` le faltaba el `(-1)^j` del binomio, que es
  **todo** lo que separa las dos ramas: `∫sen^2·cos^3` daba una derivada
  `sen^2·cos(1 + sen^2)` —una expresión real y la primitiva equivocada—.

**Una prueba que sostenía una rama muerta.** `test_e01r_limitations.py` fallaba
en `main` desde antes de este bloque y por una razón que no era del motor:
`∫1/cos(u)^2` tenía **dos** ramas con la misma integral y etiquetas distintas
—`tg(u)` y `tan(u)`—, la segunda inalcanzable porque `_PROPIAS` cubre las dos
escrituras del integrando y sale antes. La prueba clavaba la etiqueta de la rama
muerta. Eso es lo que hace un bug de código muerto: no se manifiesta como
respuesta falsa, sino como una afirmación sobre el motor que dejó de ser cierta
y nadie revisó. Rama eliminada, etiqueta fijada a la que sale de verdad —que es la
de su hermana, `∫1/sen(u)^2 = -cotg(u)`— y verde.

**Y una convención que era lo contrario de una convención.** `symbolic/integrate.py`
y `symbolic/derive.py` estaban en CRLF mientras el `.gitattributes` del repo fija
`* text=auto eol=lf`. Con eso, **un literal de cadena no puede cruzar el salto de
línea** —el `\r` cuenta como terminador para el tokenizador—, y tres
explicaciones escritas en dos líneas cada una eran un `SyntaxError` que solo
aparecía al leer el fichero con sus propios finales. Ambos normalizados a LF: el
repo ya lo pedía y el bug era una consecuencia directa de no hacerlo.

**Un límite declarado, no un hueco.** `sen(x)^6·cos(x)^6` se integra bien —234
caracteres, dentro del presupuesto— y **su derivada no cabe en los 480**. El
motor devuelve una respuesta correcta que no puede comprobar. La prueba lo nombra y
lo verifica por diferencias finitas, porque ahí ya no queda la verificación
simbólica: es exactamente lo que el presupuesto existe para hacer visible en vez
de esconder.

**Pruebas**: 31 nuevas en `tests/test_mathlab_integrales.py` —14 productos de dos
potencias, 10 potencias altas de la familia, 4 entradas de tabla—, más la que
**documentaba el hueco y ahora afirma lo contrario**: `e^x·sen(x)`, `senh(x)^2` y
`sec(x)^3` estaban en una prueba que comprobaba la negativa. Cerrar el hueco la
hizo fallar, y ese es el mecanismo entero —una lista de huecos que nadie relee
sigue verde—, así que ahora comprueba que se integran y su nombre y su docstring
dicen de dónde viene. Dos más que apuntan a las trampas concretas: que los dos
sentidos del desdoblar no se confundan (el signo del binomio es lo único que los
distingue, y sin él ambos verifican) y que el doble ángulo aparezca de verdad en
`∫sen^2·cos^2`. Con la de `test_e01r_limitations.py` que fijaba la etiqueta de la
rama muerta. 1894 pasan y 8 se saltan en los dieciséis ficheros
`test_mathlab_*.py`, más los cuatro de la familia E0/E01 que tocan el
integrador.

## Unreleased — MathLab: la auditoría de T-13, T-11, T-15 y un bucle sin suelo

Un barrido por las familias que la auditoría permanente **no** cubría —T-13, T-11,
T-15, T-16 y la fase y amplitud de T-23— buscando respuestas falsas. Encontró
**seis bugs reales en tres familias**, ninguno de ellos una capacidad que faltara:
todos contestaban mal.

- **T-13, y el más grave de todos: un «no hay soluciones» FALSO.** La carta de
  signos recorre **huecos** y se queda con los que cumplen. Una solución sin
  interior no tiene ningún hueco que quedarse —el máximo es tangente, no un cambio
  de signo— así que `sen(x) >= 1` publicaba `∅` con el motivo de que no hay
  soluciones. Lo cumple en `pi/2` y en `3pi/2`. Igual `sen(x) <= -1`,
  `cos(x) >= 1` y `cos(x) <= -1`. Y lo escondía el caso vecino: `sen(x) <= 1` sí
  salía bien, porque todos los huecos cumplen y no hay nada que buscar. Un
  `∅` sobre una expresión llena de soluciones es la peor respuesta posible.

- **T-13: `<=` y `<` publicaban el mismo conjunto.** `tg(x) <= 0` y `tg(x) < 0`
  publicaban las dos `(pi/2, pi]`, con `pi` dentro. La causa: el extremo del periodo
  se decidía comparando el punto **sin doblar** contra un conjunto de ceros **ya
  doblado**, así que el cero del final de periodo no se reconocía como cero y se
  decidía por el valor numérico. Ahi `tg(pi)` vale `-1e-16`, que pasa cualquier
  `< 0`.

- **T-13: el mismo punto se contestaba de dos formas.** La respuesta **declara**
  «se repite cada P·pi», así que `0·pi` y `P·pi` son el mismo punto — y
  `contiene(0)` decía falso mientras `contiene(P)` decía verdadero para
  `tg(x) <= 0`. Un conjunto que pone un punto dentro y el mismo punto fuera no es la
  solución de nada. Afectaba a las doce combinaciones de operador sobre seno,
  coseno y tangente.

- **T-11: las dos ramas de `acosh(cosh)` estaban cambiadas de sitio.**
  `acosh(cosh(x)) = |x|`, y `|x|` es `-x` a la izquierda. El motor publicaba `x`
  en `(-inf, 0]` y `-x` en `[0, inf)`, justo al revés. Y lo publicaba dos veces
  igual, porque **la nota de cada fila describía el lado correcto y la expresión
  no**: el motor se contradecía a sí mismo y las dos frases —la rama y su
  justificación— decían la misma cosa falsa. Sin ninguna prueba que lo notase: el
  `arccosh` de un coseno es siempre no negativo, y las dos filas lo eran.

- **T-15: `arg` mal en el SEGUNDO cuadrante.** `_principal` doblaba el `atan` hacia
  el mismo lado siempre que la parte real fuera negativa, y eso solo es correcto en
  el **tercer** cuadrante, donde `y/x` es positivo. En el segundo `y/x` es
  negativo y hay que **sumar** `pi`: `arg(-3 + 4i)` salía en -4.069 en vez de
  +2.214 — fuera del rango `(-pi, pi]` que el propio módulo declara, y una vuelta
  entera de la verdad, que es justo lo que el docstring de `argumento` advertía.

- **T-15: `principal=False` no era «una vuelta más», que es lo que su nombre
  prometía.** Devolvía el `atan(y/x)` sin doblar, que con parte real negativa no es
  un argumento del número: el coseno sale con el signo equivocado. O sea, ni
  principal ni una vuelta de diferencia, solo equivocado.

- **Un bucle sin suelo, preexistente y de los graves.** `periodo_minimo` partía el
  candidato por la mitad mientras la mitad siguiera valiendo, con la condición
  `candidato / 2 > 0`. Un `Fraction` positivo partido por dos es otro `Fraction`
  positivo: **nunca** llega a cero. Para una función que repite tras **cualquier**
  desplazamiento el bucle no terminaba, y `sen(x)^2 + cos(x)^2 - 1/2` es la
  constante 1/2 escrita más larga. `sen(x)^2 + cos(x)^2 > 1/2` **colgaba el motor**
  hasta que lo mataban. La respuesta correcta no es un periodo más pequeño, es que
  no hay periodo mínimo — y un periodo sin mínimo no es un periodo que una carta de
  signos pueda usar—, que es exactamente lo que ya decía `1 > 1/2`.

**Lo que salió limpio**, y conviene decirlo porque es la mitad del resultado: T-16
los cuatro cuadrantes, la suma de fasores de la misma frecuencia, el rechazo de
frecuencias distintas y el contrato; T-11 las otras cinco familias de ramas, con
control negativo; T-23 el periodo, la frecuencia, la amplitud (que es la mitad del
recorrido, medida aquí y no por el motor) y los ceros declarados, comprobados
anulando la función.

**Una prueba que comprobaba lo contrario de su nombre.**
`test_argumento_no_principal_gana_una_vuelta_entera` afirmaba que las dos vías dan
lo mismo, sobre `3+4i` —primer cuadrante, donde el `atan` sin doblar ya es
principal y la opción no cambia nada—, así que pasaba con una implementación que
ignorara la opción y no podía cazar el segundo cuadrante. Ahora hace lo que su
nombre dice, sobre seis números de los cuatro cuadrantes.

**Pruebas**: 159 nuevas en `tests/test_mathlab_auditoria.py` —que pasa de 326 a
485 comprobaciones—, con control negativo en las tres familias y en el módulo de
ramas. Los controles negativos importan: sin ellos, «la rama vale en su intervalo»
pasaría igual si todas las ramas fueran `x`, y «el argumento principal coincide
con `atan2`» pasaría si las dos vías dieran lo mismo. La comprobación de
inequaciones además **cuenta como polos los puntos que son polos**, porque un polo
visto por punto flotante es un número grande y no un `None`: sin eso marcaría como
error una respuesta que es correcta.

2064 pasan y 8 se saltan, de 2072 recogidas, en los dieciséis ficheros
`test_mathlab_*.py`, más los cuatro de la familia E0/E01 que tocan el integrador.

## Unreleased — MathLab: dos escrituras de la misma pregunta, y dos respuestas

El motor **tenia la respuesta y se negaba a darla**. `sec(x)^2 > 4` se rechazaba
mientras `1/cos(x)^2 > 4` se resolvia, que es la misma pregunta; y en el lado de
las ecuaciones pasaba igual con `sec(x)^2 = 4`. Es exactamente la enfermedad que
T-14 cerró para las integrales, en los dos solucionadores que aquella tanda no
tocó.

- **La potencia del recíproco iba FUERA del cociente.** Reescribir `sec(u)^n`
  como `(1/cos(u))^n` es el mismo número en otra forma, y es una forma que nada
  de lo que viene después reconoce. Va DENTRO: `1/cos(u)^n`, que es como lo
  escribe el estudiante. Solo para entero positivo, que es donde
  `(a/b)^n = a^n/b^n` es exacto. `cot(u)^n` tenía además su propia forma —el
  cociente `cos/sin`—, y por eso `cot(x)^2 > 1` se rechazaba mientras
  `1/tan(x)^2 > 1` se resolví­a. Medido: **6 de 8 parejas** de la misma pregunta
  coinciden ahora; eran 2 de 8.

- **Dos ceros FALSOS, que es peor que un rechazo.** `tg(x)·cos(x)` publicaba
  `pi/2` y `3pi/2` como ceros, y `tg` no existe ahí. El producto es cero donde lo
  sea un factor —eso es cierto— pero solo donde el producto **existe**, y el
  filtro que ya tenía la rama del cociente faltaba en la del producto.

- **Un cero que faltaba, y era el mismo defecto por el otro lado.** `tg(x)·cos(x)`
  es `sen(x)`, de periodo `2·pi`, mientras `tg` se dobla en `pi` y declara un solo
  cero —así que `pi`, un cero real, no se generaba nunca. Un cero que falta no es
  un cero de más, pero deja la carta de signos sin un punto crítico con el que
  explicar un cambio de signo, y el motor se negaba diciendo justo eso. La regla:
  **cada factor aporta sus ceros hasta el periodo del producto**, con vueltas
  enteras de su propio periodo. Repartir la unión por todo el periodo del
  producto se probó primero y sobregenera —movió ocho pruebas en tres ficheros—;
  la regla del factor no.

- **Un «no hay soluciones» FALSO.** `cot(x)^3 > 4` publicaba `∅` sobre una
  expresión llena de soluciones. Sus ceros necesitan `tg(x) = 4^(-1/3)`, que no es
  múltiplo racional de `pi`, y el solucionador de ecuaciones devolvía una lista de
  familias vacía **sin registrar el rechazo**: leído tal cual, «no hay ceros». El
  propio módulo lleva escrito que `∅` **no** es «no lo sé», y esa es justo la
  conversión que hacía. La comprobación independiente es el teorema del valor
  intermedio —una función continua sin polo ni cero no cambia de signo—, que
  demuestra que el cero **existe** sin poder decir dónde. `cos(x)^3 > 1` pasa la
  misma prueba, y ahí `∅` es la verdad: no se convierte todo lo desconocido en un
  rechazo, solo se deja de hacer la conversión equivocada.

- **El dominio se comía un `0/0`.** `ceros` contesta con UN periodo, así que el
  denominador `sen(x)` declaraba su cero en 0 y no en `pi`, y el dominio publicaba
  que `1/sen(x)` existía en `pi` —donde vale `1/0`— y de ahí le salía un cero
  falso. `0` y el final del periodo son el mismo punto: la regla que la carta de
  signos ya seguía y que aquí no. Tres expectativas de prueba clavaban el
  comportamiento equivocado —`cos/sen`, `1/tg` y las discontinuidades de
  `1/sen`—, y estaban derivadas de la salida, no de lo que las expresiones **son**.
  Corregidas con el razonamiento escrito, no con la salida nueva.

**Medido, no supuesto.** 13 expresiones de producto y cociente contrastadas punto
a punto contra la función, contando solo los puntos donde el dominio dice que
existe: **0 discrepancias**, antes 2 ceros falsos y 1 que faltaba.

**Lo que queda declarado, con su motivo:**

- `sen(x)/tg(x) < 2` frente a `cos(x) < 2`. Son la misma pregunta donde todo
  existe, pero cancelarlas exige reescribir `tg` como `sen/cos` **conservando el
  dominio** —en `pi/2` el cociente no existe—, y el sitio donde eso va es la
  reescritura de identidades, no la carta de signos.
- `tg(x)·cos(x) > 0` frente a `sen(x) > 0` **no son la misma pregunta**: difieren
  en los polos de `tg`, y el motor da `(0, pi/2) ∪ (pi/2, pi)`, que es lo correcto
  de la primera. Compararlas sería un error de la comprobación, no del motor.
- `sec(x)^3 > 8` se niega con el motivo correcto: su cero necesita `cos = 1/2`
  exacta pero el camino de la raíz cúbica no lo alcanza. `sec(x)^2 > 4` sí se
  resuelve.

**Pruebas**: 33 nuevas en `tests/test_mathlab_auditoria.py`, que pasa de 485 a 518
comprobaciones. 2083 pasan y 8 se saltan, de 2094 recogidas, en los dieciséis
ficheros `test_mathlab_*.py`. La comprobación de las dos escrituras lleva un
ejemplo al lado que **no** es la misma función, para que ajustar el motor a la
prueba sea visible.

## Unreleased — MathLab: el reciproco con potencia impar, y un no-hecho documentado

Quedaba un hueco de capacidad, no un bug: `sec(x)^3 > 8` se negaba con el motivo
correcto —su cero necesita `cos = 1/2`, que es exacto— mientras `sec(x)^2 > 4` se
resolvía. La única diferencia era el grado.

- **El teorema de la raíz racional usaba solo el término constante.** Dice «divisor
  del constante SOBRE divisor del coeficiente PRINCIPAL», y aquí se usaba el
  primero. Para `-16·u^4 + 1` eso da ±1, y la raíz es 1/2. El cuadrado se
  resolvía por otra vía y el cubo no, y el divisor del coeficiente principal se
  tomaba de su **denominador** —que es 1— en vez de su numerador, que es donde
  están el 2, el 4 y el 16. Ahora `1/cos(u)^n = c` resuelve para toda potencia
  entera, y con ella `sec^3 > 8`, `sec^5 > 32`, `csc^3 > 8` y `1/tan^3 > 1`.

- **Un NO HECHO que se probó y se revirtió, escrito para que no se intente otra
  vez.** `sen(u)/tg(u)` es `cos(u)` y `cos(u)/sec(u)` es `cos(u)^2`, y reducirlos
  en la normalización de los solucionadores parece obvio. No lo es, y el motivo
  está en el **periodo**: `cos²` tiene periodo `pi` y `cos/sec` tiene periodo
  `2·pi`, porque `sec` no existe donde `cos` se anula. Reescribir borra el dominio
  *y* el periodo, y el conjunto publicado pasa a ser el de otra función —medido:
  `cos(x)/sec(x) > 1/2` quedaba mal en **193 de 383 puntos**—. Un filtro de
  existencia no lo arregla, porque el filtro quita puntos y lo que falta es un
  turno entero. El sitio correcto es la reescritura de identidades, que conserva
  el dominio mientras simplifica. Queda escrito en el código, con el número.

  `cos(x)/sec(x) > 1/2` y `sen(x)/tg(x) = 1` siguen negándose, con el motivo, y
  la petición queda con el mecanismo exacto: es la reescritura, no la carta.

**Medido.** 18 inecuaciones del recíproco y sus potencias, contrastadas punto a
punto contra la función con 384 muestras cada una y los polos saltados y
**declarados**: 0 respuestas incorrectas. Antes nueve de ellas fallaban en 1 de
191 puntos, y las nueve fallaban en el mismo —el polo, donde `cos(pi/2)` vale
6·10⁻¹⁷ y `sec` parece enorme—. Saltarlos no relaja la comprobación: le quita su
única fuente de falsos positivos.

**Pruebas**: 12 nuevas en `tests/test_mathlab_auditoria.py`, que pasa de 518 a 530
comprobaciones. La del recíproco sustituye el caso de §5 por el nombre, y las
expectativas se derivan de la verdad y no de la salida. 2106 pasan y 9 se saltan,
de 2115 recogidas, en los dieciséis ficheros `test_mathlab_*.py`, más los cuatro
de E0/E01.


## Unreleased — Windows Product 1.0 (productización)
- Producto/UX post-roadmap (sin fase nueva): menú Go agrupado sobre los 13 tabs intactos; índice de módulos reales; Virtual Lab/Simulation en secciones Experiment/Inputs/Execution/Results sin renombrar widgets; vista orbital F16 con números reales; dashboard editorial con recents reales; motion 150 ms sin bounce.
- Validación: exe/installer reconstruidos del árbol final, smoke verde, regresión verde; Start Menu/uninstall-ejecutado/clean-machine/DPI sistemático NOT VERIFIED (sin admin ni 2ª máquina).
- `AcademicCore.exe` (PyInstaller onedir) + `AcademicCore-1.0.0-Setup.exe` (NSIS 3, Start Menu, desinstalación registrada). Versión única `1.0.0` (`__init__` → pyproject → version_info → installer, pineado por tests).
- Runtime: `%LOCALAPPDATA%/AcademicCore` solo en bundle (`runtime.py`); dev intacto en `~/.academic-core`. Icono propio generado por render Qt (sin assets de terceros).
- UX: splash con versión, first-run de una pantalla (sin cuentas ni red), búsqueda global Ctrl+K sobre `UnifiedSearchService` (sin segundo motor), Settings con Appearance/Data/About reales, icono de ventana.
- CI: job `release` (build exe + installer + smoke offscreen con DB verificada + artifact). Sin updater automático (limitación documentada en `packaging/windows/README.md`).
- Núcleo académico intacto (F9–F13, F15, F16 sin cambios de comportamiento).

## Unreleased — Fase F16: Contenido Aeroespacial (CERTIFICADA)
- Motor `domain/engineering/orbital/` (`f16-orbital/1`): two-body Decimal SI (m, kg, s, rad) con contexto de 50 dígitos; circular/periodo+inversa, vis-viva+inversa, energías (total vs específica), escape, elipses (0 ≤ e < 1), Kepler (M↔E Newton acotado, ν↔E cerradas), elementos clásicos con marcos `ECI/ORBITAL` y digest `f16-elements/1`. Constantes con provenance (G CODATA 2018, Tierra IAU/IERS). Sin persistencia, sin dependencias, sin códigos AC nuevos.
- Reutilización: `math/` (sqrt/pi/trig), `units.py` extendido aditivamente (MASS/FORCE, g/N/rad + alias; min/h/day/deg como helpers explícitos), traza E0 (`domain/execution/orbital.py` `physics.orbital` + replay + wiring `ExplainService`, aditivo). F8-P5/F9/D7 intactos.
- Nuevos: `test_f16_orbital.py` (16 contractuales: ISS/GEO/escape, round-trips, dominio, hash-seeds, traza+replay, AST). TDD: RED verificado antes de GREEN.
- Docs: `F16-AEROSPACE.md` + `GATE-F16-CERTIFICATION.md` (veredicto: CERTIFICADA con CI real; ROADMAP COMPLETADO). Evidencia local: 16/16 F16 + regresión verde salvo 1 preexistente CRLF (documentado, ajeno a F16).
- Commit impl. `195d3e7`. Run de certificación [`36394085024`](https://github.com/Damaga2005/AcademicCore/actions/runs/36394085024) verde 4/4 celdas + package. Roadmap: **F16 CERTIFICADA, ROADMAP COMPLETADO**.

## Unreleased — Fase F13: OneDrive / Cloud Sync (CERTIFICADA)
- Coordinación `application/cloud_sync.py` (`CloudSyncService`) sobre el motor F13-ext intacto (`domain/sync.py` sin cambios): primer push, join bidireccional LWW, VERIFY reutilizado, estados `synced/pending/offline/conflict/error` en tabla aditiva (fuera de digests). Nunca: error cloud → rollback local; nada marcado synced sin escritura confirmada.
- Transportes `infrastructure/cloud_transport.py` (sin red ni dependencias nuevas, solo pathlib+json): `MemoryCloudTransport` (fake/in-memory para contrato) + `OneDriveFolderTransport` (carpeta local, escritura atómica tmp+replace, `expected_remote_digest` → `AC-SYN-004`). Validación y límites reutilizados F13-ext (`AC-SYN-001`); errores nuevos `AC-SYN-002/003/004`.
- Persistencia: migración 021 aditiva (`sync_status` + `cloud_sync_meta`) + métodos `set/get_status`, `all_statuses`, `set/get_meta`; wiring `cloud_sync` en facade (carpeta OneDrive si `providers.onedrive_folder`, si no Memory). Tocado certificado: solo pins `20→21` (la 021 los exige) + extensión aditiva de `test_d5_contracts` a F13.
- Nuevos: `test_f13_cloud_sync.py` (9 contractuales: primer push, offline-first+reintento, bidireccional, conflicto determinista+log, corrupto intacto, tombstone, sin secretos, carpeta round-trip, auth/límites). TDD: RED 9/9 verificado antes de GREEN.
- Docs: `F13-CLOUD-SYNC.md` + `GATE-F13-CERTIFICATION.md` (veredicto: CERTIFICADA con CI real; F13 CERTIFICADA, F16 SIGUIENTE). Evidencia local: 9/9 F13 + regresión 176 passed / 1 skip ambiental. Sin E2E real contra OneDrive/Graph (sin credenciales; no se finge).
- Commit impl. `f34a9d5`. Run de certificación [`36385930302`](https://github.com/Damaga2005/AcademicCore/actions/runs/36385930302) verde 4/4 celdas + package. Roadmap: **F13 CERTIFICADA, F16 SIGUIENTE**.

## Unreleased — Fase F12: Tutor Socrático (CERTIFICADA)
- Contratos `domain/tutor.py` (puro): `f12-tutor-response/1` (schema cerrado, 6 `response_type`), `Claim`/`TutorProposal`/`VerifiedResponse`, `SOCRATIC_LADDER` (6 etapas derivadas del nº de turnos previos, sin store de política aparte), `verify_claims` — delega en `domain.correction.correct_answer` (F9): ningún segundo motor matemático/simbólico/de unidades/circuitos.
- `infrastructure/llm.py`: `LLMProvider` (protocolo agnóstico de proveedor), `NullProvider` (LLM=OFF determinista), `OllamaProvider` (adapta el `OllamaBackend` existente; cero dependencia nueva, cero reintentos automáticos). `application/tutor.py`: `TutorService` orquesta sin recalcular F9/F10/F11.
- Autoridad estricta: LLM propone JSON → validador de schema/política → `correct_answer` decide → `verified`/`unverified`/`rejected`. El LLM no tiene acceso a herramientas/filesystem/red/BD; solo emite texto.
- Migración 020 aditiva (`tutor_turns`, append-only, solo respuesta verificada — sin texto crudo del LLM) + `TutorRepository`. Errores nuevos `AC-TUT-001..006`. Cambio aditivo mínimo en `engines/ai.py` (`OllamaBackend.generate(timeout=)`, default idéntico, sin ruptura).
- Nuevos: `test_f12_tutor.py` (35 contractuales: schema, claims/solver routing, autoridad, política socrática, LLM=OFF/timeout/provider-error, persistencia/provenance, seguridad).
- Docs: `F12-SOCRATIC-TUTOR.md` + `GATE-F12-CERTIFICATION.md` (criterios §28: todo verde incluyendo CI real). Tocado certificado: solo pins `19→20` (la 020 los exige).
- Evidencia local: 35/35 F12 + regresión curada 306 passed / 1 skip ambiental (mismo skip que F11). Suite completa sin filtrar: 13 fallos, 12 preexistentes verificados en `main` limpio (CRLF/LF en fixtures doradas de F8/E0, ajenos a F12; confirmado además por las celdas Windows del CI real, que no los reproducen) + 1 pin de migración ya corregido.
- Commit `35763bc8b09c9f212c1b7389e0ceb8472cb62fe4`. Run de certificación [`36336990034`](https://github.com/Damaga2005/AcademicCore/actions/runs/36336990034) verde 4/4 celdas + package, a la primera. Roadmap: **F12 CERTIFICADA, F13 SIGUIENTE**.

## Unreleased — Fase F11: Aprendizaje Adaptativo (CERTIFICADA)
- Motor `domain/adaptive.py` (`f11-adaptive/1`): `AdaptiveConfig` versionada (pesos 60/20/15/5, umbrales 0.40/0.70, max_per_concept 2, exclude_done), `AdaptiveContext`, `Candidate`/`ScoredCandidate`/`AdaptivePlan` (rationale cerrado + `NO_ELIGIBLE_EXERCISES`/`PREREQUISITE_UNMET`), `target_difficulty`/`difficulty_fit`, `score_candidate`, `rank_candidates` (score DESC, question_id ASC, version ASC), `build_route` (cap por concepto), `plan_digest` (`f11-adaptive-plan/1`).
- Servicio `application/adaptive.py`: `build_plan` (eligible→filter→score→rank→route→persist), elegibilidad contractual (subject/tipo/difficulty/concept/prerequisites subject-level/historial F10), persistencia idempotente (plan_id = plan_digest). LLM=OFF: sin imports de IA.
- Migración 019 aditiva (`adaptive_plans`) + consultas `QBankRepository.questions_of_subject` (json_each) y `MasteryRepository.save_plan/get_plan/plans_of`. Cero comportamiento certificado cambiado.
- Nuevos: `test_f11_adaptive.py` (22 contractuales: elegibilidad, prioridad mastery, ranking/tie-break, historial, route, reproducibilidad, idempotencia, prerequisitos, edge cases, LLM=OFF, seguridad AST).
- Docs: `F11-ADAPTIVE.md` + `GATE-F11-CERTIFICATION.md` (criterios §31: todo verde salvo CI real y roadmap, explícitamente pendientes). Tocado certificado: solo métodos nuevos + pins `18→19` (la 019 los exige).
- Evidencia local: 22/22 F11 + regresión 217 passed / 1 skip ambiental + 36 passed × 3 hash-seeds. Run `36260971728` (`28c6863`) verde 4/4 + package a la primera. Roadmap: F11 CERTIFICADA, F12 SIGUIENTE.

## Unreleased — Fase F10: Mastery y Modelado del Estudiante (CERTIFICADA)
- Modelo `domain/mastery.py` (`f10-beta/1`): Beta-Binomial conjugado Decimal (sin floats/NaN), `P=m/(m+n)`, varianza Beta, prior Beta(1,1) configurable, `split_weight` exacto multi-concepto, `fold_observations`/`fold_deltas`/`pool_states`, digests `f10-observation/1` + `f10-state/1`.
- Servicio `application/mastery.py`: `apply_evidence` (validate→plan→1 tx; `no_update` para omitidas/sin-concepto; `AC-ACD-002` concepto desconocido; `AC-ACD-003` tamper), queries concept/topic/subject (jerarquía D7 real vía `topic_ref` del ítem), `rebuild` (fold en orden fijo; incremental == rebuild).
- Migración 018 aditiva (`mastery_states` + `mastery_observations` PK-idempotente) + `MasteryRepository` con `cx`. Extensión aditiva F9: `ItemEvidence.topic_ref` + `build_evidence(assessment=)`. Motor F9 intacto.
- Nuevos: `test_f10_mastery.py` (14 contractuales: modelo, evidencia, split, unknown-concept, idempotencia (doble apply + doble-insert concurrente), rebuild, determinismo cross-fixture, jerarquía, rollback, round-trip + NaN, seguridad AST + no-re-corrección).
- Docs: `F10-MASTERY.md` + `GATE-F10-CERTIFICATION.md` (criterios §33: todo verde salvo CI real y roadmap, explícitamente pendientes). Tocado certificado: solo DTO aditivo + pins `17→18` (la 018 los exige).
- Evidencia local: 14/14 F10 + regresión 281 passed / 1 skip ambiental + 28 passed × 3 hash-seeds. Run `36254755243` (`9e6d66c`): intento 1 con 1 flake `test_perf_academic_scale` (21.0s/20s, win-3.12, clase §8); intento 2 tras `rerun --failed` verde 4/4 + package. Roadmap: F10 CERTIFICADA, F11 SIGUIENTE.

## Unreleased — Fase F9: Assessment y Evaluación Formal (CERTIFICADA)
- Motor `domain/correction.py` (`f9-correct/1`): mcq/tf exactos, numeric `Decimal`+unidades+tolerancia/precisión (cifras significativas), symbolic con prueba `equivalent` o acuerdo exacto etiquetado, short/structured/circuit honestos (`needs_review` donde D6 no da criterio), malformados → `AC-DOM-001`, razones cerradas, nada ejecutado.
- Servicio `application/correction.py`: cupo `attempts_allowed` (cancel no consume), `prepare` (snapshots congelados idempotentes), `submit_with_correction` (submit→correct→result+evidence en 1 tx), `build_evidence` (DTO F10 con `verified`, resiliente a tamper). Errores `AC-ACD-002/003/004` + `AC-INT-001` (sin códigos nuevos).
- Migración 017 aditiva (snapshots+evidence+triggers) + refactor `save_session→_save_session_tx` (misma semántica, F9-D verde) + métodos con `cx`. `GradingPolicy`/orquestación intactas; sin scoring inventado ni simulación como corrección.
- Nuevos: `test_f9_correction.py` (19 contractuales: lifecycle, cupo/cancel, doble submit, prepare, historia congelada, tipos, bordes numeric, symbolic, inválidos, pending, omitidas, evidence+tamper, rollback, determinismo, seguridad AST).
- Docs: `F9-ASSESSMENT.md` + `GATE-F9-CERTIFICATION.md` (criterios §23: todo verde salvo CI real y roadmap, explícitamente pendientes). Tocado certificado: refactor interno + pins `16→17` (la 017 los exige).
- Evidencia local: 19/19 F9 + regresión 267 passed / 1 skip ambiental + 33 passed × 3 hash-seeds. Commit impl. `acec7ed`. Run `36244520858` (`ef1976c`): intento 1 con 1 flake `test_perf_academic_scale` (22.9s/20s, win-3.13, clase §8); intento 2 tras `rerun --failed` verde 4/4 + package. Run de certificación `36248720654` (`1b41cd5`) verde 5/5. Roadmap: F9 CERTIFICADA, F10 SIGUIENTE.

## Unreleased — Fase D7: Ingesta estructurada → Knowledge Core (CERTIFICADA)
- Plan puro `domain/ingestion.py` + servicio `application/bank_ingest.py` (plan/dry-run/ingest, 1 tx `unit_of_work`, verify post-commit, `now_ms` inyectable). Políticas: reuse/create/rechazo determinista, ambigüedad concepto+formula → error, idempotencia por digest, versiones create/unchanged/update/conflict/stale, reuse sin overwrite, fórmula modificada = conflicto.
- Migración 016 aditiva (`qbank_banks`, `qbank_questions`, `formulas` para `academic.Formula`) + `QBankRepository` con `cx`; conceptos en `study_concepts` (reuso, creación solo con catálogo + subject existente + bump `id_counters.concept`); refs section/document/topic carried opacos. Errores `AC-ACD-002/003/004` + `AC-INT-001` (sin códigos nuevos).
- Nuevos: `test_d7_ingestion.py` (18 contractuales: mínimo, mapping, digest, create, idempotencia cero-writes, update+delete, reuse, unresolved `AC-ACD-002`, ambigüedad `AC-ACD-003`, provenance E2E, no-overwrite, conflicto de fórmula, rollback inyectado, dry-run, determinismo ×2 DBs, inválidos/versiones, subject desconocido, seguridad AST + latex inerte).
- Docs: `D7-INGESTION.md` + `GATE-D7-CERTIFICATION.md` (criterios §23: todo verde salvo CI real y roadmap, explícitamente pendientes). Tocado certificado: solo pins `15→16` en `test_migration.py`/`test_persistence.py` (la 016 los exige).
- Evidencia local: 18/18 D7 + regresión amplia verde (1 pin actualizado, re-verde) + 48 passed × 3 hash-seeds. Commit impl. `18d3815`. Run `36239628773` (`03579c0`): intento 1 con 1 flake `test_perf_academic_scale` (21.47s/20s, win-3.13, clase §8); intento 2 tras `rerun --failed` verde 4/4 + package. Roadmap: D7 CERTIFICADA, F9 SIGUIENTE.

## Unreleased — Fase D6: Esquema neutro de banco de preguntas (CERTIFICADA)
- Dominio puro `domain/question_bank.py`: `Bank`/`Question`, 7 `qtype`, `answer_spec` por tipo (claves cerradas), IDs `bank:<slug>` / `question:<slug>:q:NNNNN`, `schema d6-question-bank/1` + `content_version`, canonicalización `sort_keys` + digest `sha256(tag+0x00+canonical)`, envelope con `integrity`, validación estricta + extensiones `x-`, provenance forma F2, errores D2 existentes (sin códigos nuevos), cero floats, sin persistencia (formato + validador).
- Nuevos: `test_d6_question_bank.py` (16 contractuales: mínimos, tipos, IDs, schema/rechazo `AC-VER-001`, canonicalización, digest semántico, round-trip, provenance, knowledge_refs, answer_spec, unidades + `parse_unit`, extensiones, tamper/inválidos, determinismo, seguridad AST).
- Docs: `D6-QUESTION-BANK.md` + `GATE-D6-CERTIFICATION.md` (criterios §21: todo verde salvo CI real y roadmap, explícitamente pendientes). Cero código certificado tocado.
- Evidencia local: 16/16 D6 + regresión 189 passed / 1 skip ambiental + 36 passed × 3 hash-seeds. Commit impl. `07b3136`. Run `36236406471` (`86f105d`) verde 4/4 + package. Roadmap: D6 CERTIFICADA, D7 SIGUIENTE.

## Unreleased — Fase D5: Suite global de tests (CERTIFICADA)
- Baseline pre-D5: 4598 tests / 138 ficheros → 4583 passed, 2 failed (preexistentes), 13 skipped, ~60 min local.
- Fix §12 (bug real): `SyncService._apply_winners` llamaba `add_favourite(kind, ref, title)` sobre el repositorio → `TypeError` al aplicar favoritos remotos; ahora construye `PL.SavedSearch` (preserva `created`). Regresión incluida.
- Fix §12 (test con fecha caducada): `test_activity_from_documents_and_reading` dependía del reloj real (verde CI 09-25, rojo desde 09-26); `added_at` backdateado, fechas 100% fijas. Cero producto tocado.
- Fix §9: `test_generality_sweep_both_modes` (105s > 90s en runner lento, CI verde) marcado `perf`; umbral intacto.
- Nuevos: `test_f13ext_service.py` (13: identidad, adaptadores, 2 BDs, idempotencia, `AC-SYN-001`, límites) + `test_d5_contracts.py` (7: AST F13-ext/D4, pureza dominio, markers, perf).
- Markers `arch`/`repro`/`perf` (+registro `perf`); CI ejecuta lo mismo. Docs: `TEST-SUITE.md` canónico (+matriz 16 áreas), `STRATEGY.md` como puntero. Cero eliminaciones (auditoría: sin duplicados reales).
- Evidencia: 20 nuevos verdes + regresión 134 passed × 3 hash-seeds. Run `36232344763` (`c14c317`) verde 4/4 + package. Roadmap: D5 CERTIFICADA, D6 SIGUIENTE.

## Unreleased — Fase D4: Pipeline CI/build (CERTIFICADA)
- Workflow único `.github/workflows/ci.yml`: matriz windows/ubuntu × py3.12/3.13, install desde `requirements-lock.txt`, `compileall`, `pytest -m "not external"`, job `package` con `python -m build` y artefacto `dist/`. Sin bypasses, sin secretos, sin dependencias de producto.
- Tests `test_d4_pipeline.py` (7, stdlib, sin red): triggers, sin bypasses, lock pineado, pytest ejecuta, fallo→rc!=0, build declarado, árbol limpio.
- Docs `docs/testing/CI.md` + `GATE-D4-CERTIFICATION.md`. Evidencia local: 58 passed regresión, build real sdist+whl en venv aislado. Runs del proveedor: #1 fallo setup (Qt/ubuntu, corregido), #2 un solo fallo preexistente `html_cp1252` (divergencia manylinux-lxml, documentada) → `tests/conftest.py` con tabla §14 (xfail estricto en linux + skip por sonda symlink), sin tocar ficheros certificados → Run `36133175963` (`6bdd27b`) verde en las 4 celdas + package (ver gate). Roadmap: D4 CERTIFICADA, D5 SIGUIENTE.

## Unreleased — Fase F13-ext: Sync determinista 2 PCs (CERTIFICADA)
- Motor puro `domain/sync.py`: LWW `(ms, device)`, digest canónico, tombstones, idempotencia `sync(S',R)=S'`, protocolo `f13ext-sync/1`, sin CRDT.
- Aplicación `application/sync.py`: identidad estable `sync.device_id`, adaptadores preferences/saved_searches/quick_notes, verify interno.
- Infraestructura: migración 015 (`sync_state`+`sync_log`), `FileTransport` con límites y rechazo `AC-SYN-001`, wiring en facade.
- Tests `test_f13ext_sync.py`: 12/12 normativos. Docs: `F13EXT-SYNC.md` + `GATE-F13EXT-CERTIFICATION.md`. Roadmap: F13-ext CERTIFICADA, D4 SIGUIENTE.

## Unreleased — Fase F4.1: Gestion-Academica integrada (2026-09-23)
- Modelo académico centrado en la asignatura: estados CURSANDO/APROBADA/SUSPENDIDA/NO_CURSANDO, Home/Carrera/detalle de asignatura.
- Evaluación esquema/bloque/componente/nota mínima en Decimal (golden 400 casos vs Gestion real).
- Documentos en contexto de asignatura sobre CAS+FTS, espacios de estudio, recursos externos solo-URL, ICS, guía docente sobre F3/F3.1.
- Migración Gestion → AcademicCore: dry-run, snapshot, transacción única, idempotente, sin pérdidas, determinista.
- Cierre: profesores sin fusión por nombre, restore de backup verificado, arnés de certificación real. Gate: F4.1 NOT CERTIFIED hasta ejecutar el arnés sobre la instalación real (fallo F3 golden preexistente por libxml2). Ver `docs/gates/GATE-F4.1-CERTIFICATION.md`.

## 0.18.0 — Fase F8-I: BJT Ebers-Moll Nonlinear DC Operating Point (2026-09-16)
- Bipolar Junction Transistor (BJT) model under classic Ebers-Moll equations for NPN and PNP polarities.
- Exact coupled $3 \times 3$ analytical Jacobian without numerical approximations.
- Invariant matrix properties: $\sum_i J_{ij} = 0$ (KCL conservation), $\sum_j J_{ij} = 0$ (reference voltage shift invariance).
- Strict `Decimal` physical calculations (`prec=50`, `prec=80`) and zero `float` policy (verified via AST audit).
- Robust exponential damping and clamping ($V_{\text{clamp}} = 100 \cdot V_T$) with geometric bisection line-search.
- 15 canonical circuit topologies verified (B1–B15: fixed bias, self-bias, emitter follower, common base, PNP common emitter, saturation, reverse active, current mirror, differential pair, Darlington pair, inverter switch, BJT+diode, BJT+dependent sources, BJT+OpAmp, BJT+transformer).
- Multi-BJT scaling matrix ($N=1..64$) with constant 7 Newton iterations.
- Automated cross-validation with ngspice 47 (< $10^{-4}$ relative error).
- Gate F8-I: 143 passed (69 F8-H diode + 33 F8-I BJT physics + 41 F8-I nonlinear MNA circuits).

## 0.17.0 — Fase F8-H: Shockley Diode Nonlinear DC Operating Point (2026-09-16)
- Nonlinear DC MNA solver with damped Newton-Raphson and geometric backtracking.
- Shockley diode companion model and analytical conductance $g_d = \frac{I_S}{n V_T} \exp(V_d / n V_T)$.
- Physical block convergence criteria: KCL residual $\le 10^{-12}\text{ A}$, aux residual $\le 10^{-9}\text{ V}$.
- Full conservation checks: KCL, KVL, Tellegen power balance.
- Automated cross-validation with ngspice 47.
- Gate F8-H: 69 passed.

## 0.16.0 — Fase F8-G: Ideal Transformers & Two-Port Network Parameters (2026-09-16)
- Ideal transformer model with turns ratio $n$ ($V_1 = n V_2, I_2 = -n I_1$).
- Auxiliary variables for primary and secondary winding currents in MNA.
- Linear two-port matrix parameter extraction ($Z, Y, H, ABCD$) via test-source excitation.
- Gate F8-G: CERTIFIED (`GATE-F8G.md`).

## 0.15.0 — Fase F8-F: Ideal Operational Amplifiers / Nullors (2026-09-15)
- Ideal op-amp model (nullor: $V_+ = V_-$, $i_+ = i_- = 0$) for DC and AC steady-state MNA.
- Auxiliary output current unknown $i_o$ leaving op-amp output pin into ground.
- Strict singularity and degenerate topology classification via `math.linsolve` rank analysis.
- Gate F8-F: CERTIFIED (`GATE-F8F.md`).

## 0.14.0 — Fase F8-E: Linear Dependent Sources (2026-09-14)
- All four linear controlled sources: VCVS ($E$), VCCS ($G$), CCVS ($H$), CCCS ($F$).
- Current control graph cycle detection (`check_control_cycles`) and `CircularControlError`.
- Deterministic control current resolution and DC/AC stamping.
- Gate F8-E: CERTIFIED (`GATE-F8E.md`).

## 0.13.0 — Fase F8-D: AC Small-Signal Phasor Simulation Suite (2026-09-14)
- F8-D1: Exact and arbitrary-precision complex arithmetic (`DecimalComplex`, `FractionComplex`).
- F8-D2: Complex linear system solver with Rouché-Capelli rank analysis.
- F8-D3: General AC MNA in steady-state with peak phasors ($e^{+j\omega t}$) for $R, L, C, V, I$.
- F8-D4: Complex power $S = P + jQ$, apparent power, power factor, Tellegen balance in AC.
- F8-D5: AC driving-point impedance/admittance and transfer functions.
- F8-D6: Frequency sweep engine and Bode plots (dB magnitude, phase unwrap, $-3\text{ dB}$ cutoff brackets).
- F8-D7: Complex AC Thévenin and Norton equivalents ($Z_{th}, V_{th}, I_{no}$).
- F8-D8: Resonance detection by bracket search and reactive/dissipated energy quality factor ($Q$).
- Gates F8-D1 through F8-D8: CERTIFIED.

## 0.12.0 — Fase F8-C: DC Thévenin & Norton Reductions (2026-09-13)
- General active one-port network reduction via test-source injection and open-circuit voltage calculation.
- Certified equivalence validation across arbitrary linear resistive networks.
- Gate F8-C: CERTIFIED (`GATE-F8C.md`).

## 0.11.0 — Fase F8-B: General Linear DC MNA Solver (2026-09-13)
- Exact rational MNA solver over `fractions.Fraction` for $R, V, I, E, G, H, F, O$.
- Machine-zero KCL/KVL residuals and exact power balance.
- Gate F8-B: CERTIFIED (`GATE-F8B.md`).

## 0.10.0 — Fase F8-A: Electronics Knowledge Core (2026-09-13)
- Canonical circuit model extensions, models registry, validation contracts.
- Gate F8-A: CERTIFIED (`GATE-F8A.md`).

## 0.9.0 — Fase F7-B: Simulation Suite Hardening (2026-09-13)
- Hardened external ngspice 47 subprocess execution, timeout management, stdout/stderr isolation.
- Report F7-B8: CERTIFIED (`F7-B8-HARDENING-REPORT.md`).

## 0.8.0 — F7-A Simulation Runtime Foundation (2026-09-12)
- ngspice runtime discovery, version verification, isolated execution,
  stdout/stderr/exit capture, timeout, cancellation and cleanup.
- Windows setup/runtime documentation and separate external integration test.

## 0.7.0 — Fase 6 Engineering Foundation (2026-09-12)
- Decimal quantities, SI units/prefixes/dimensions and safe equation parser.
- Deterministic electrical calculations with provenance digests.
- Circuit topology (components/pins/nets), canonical netlists and typed models.
- SQLite migration 010, engineering repository/service, Authoring links and
  structured Engineering UI.
- Simulation boundary only: Null/Mock backends; no SPICE or subprocess.
- Gate F6: 205 passed, 2 skipped.

## 0.6.0 — Fase 5 Authoring Engine (2026-09-12)
- Command model (7 deterministic commands + undo/redo) + lifecycle +
  structured validation + 5 AST templates + in-document search.
- `document` resource kind + migration 009 (authored lifecycle, doc_links) +
  versioning/autosave/copy-paste/academic links service + Authoring UI tab.
- Round-trip battery (MD+HTML, documented equivalence) + F3 compat golden.
- Fidelity fixes shared with F3 (image targets, bare-inline items, math spans).
- Gate F5: 174 passed, 2 skipped (145 F0–F4 + 29 F5).

## 0.5.0 — Fase 4 Academic Management (2026-09-12)
- Gestion audit + reuse map (concept-only, no code copied).
- Generic gradebook (scales/weights/optional/partial, Decimal) beside F1
  engine (ADR-0016); results service; planning queries; JSON import/export;
  safe deletes + prerequisites; migration 008 (additive).
- Facade (`AcademicApp`) + `ui/` workspace (tree, 5 tabs, dialogs).
- Gate F4: 145 passed, 2 skipped (123 F0–F3 + 22 F4).

## 0.4.0 — Fase 3 Document + PDF Engine (2026-09-12)
- Conversor audit (20 comps) + selective reuse (math 1:1, tables, images,
  sanitize, metadata, encoding) with equivalence tests vs original module.
- Canonical AST (19 kinds, v1, validated, deterministic JSON) + HTML/MD
  parsers + MD/HTML renderers + doc derivations (007) + provenance chain.
- PDF engine (pypdf native: inspect/merge/split/rotate/extract/PDF→AST) +
  Stirling v2.14.3 research, runtime manager, API backend (mock-verified,
  live SIMULATED). ADR-0015. Gate F3: 123 passed, 2 skipped.

## 0.3.0 — Fase 2 Resource Engine (2026-09-12)
- Ports (`BlobStore/Extractor/Indexer/Records`) + `Resource/Version/Provenance`.
- CAS: streaming SHA-256, atomic, integrity-checked, traversal-safe.
- Adapters file/md/html/pdf (+ZIP refused); pipeline idempotente + versiones.
- FTS5 derivado con rebuild + filtros; tab Resources; `ingest.max_bytes`.
- ADR-0013/0014; gate F2: 81 passed (41 F0/F1 + 40 F2).

## 0.2.0 — Fase 1 Domain & Academic Foundation (2026-09-12)
- Domain: 20 entidades (University→Subject→Topic/Assignment/Exam/Project/Lab/
  Task/Deadline/Grade/Tag/Bookmark/Annotation/StudySpace/Session/Notification),
  Term genérico, invariantes con DomainError.
- Identity: 16 kinds, slugify NFKD, IdAllocator + counters persistidos.
- Grading Decimal HALF_UP + equivalencia (ADR-0011); schedule/conflictos puros.
- Persistence: sqlite3 stdlib, 4 migraciones, repos explícitos (ADR-0012).
- Application: Academic/Grading/Schedule services + Search/Backup/AppLock.
- UI Qt validación (selectores, subjects CRUD, 4 tabs) + gate F1: 41 passed.

## 0.1.0 — Fase 0 foundation (2026-09-12)
- Audits: Conversor (monolito 6.051 lín + lab 16 módulos), Gestion (Flask,
  28 tablas, 152 rutas, 672 docs), Sistemes (91 fuentes, 2896 fórmulas,
  1092 tests) — full detail in `docs/migration/`.
- Architecture: modular monolith, 10 ADRs, domain v0, stable IDs, storage
  SQLite+CAS, engines interfaces (resource/document/pdf/ai/providers/
  engineering), Qt skeleton executable, config system, 6 test files.
- Gates: fast suite + migration contract + reproducibility + boundary test.
