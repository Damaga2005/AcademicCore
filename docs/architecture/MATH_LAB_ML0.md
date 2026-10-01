# MATH_LAB — fase ML-0 (Cimientos)

Estado: **ML-0 implementada y verificada** · Especificación: `MATH_LAB.md` §10

El laboratorio de matemáticas son 23 fases (ML-0 … ML-22) con un esfuerzo
total de varios meses. Este documento describe **lo que está construido**, cómo
se usa, y lo que **no** existe todavía, para que nadie tenga que leer el código
para saber qué esperar.

---

## 1. Qué es ML-0

La fase de cimientos de §10:

> Expresiones con varias variables, entrada de texto con vista previa, traza de
> pasos, corrector por equivalencia y graficador 2D. (La ampliación de v2 —
> racionales multivariable, cuerpo como parámetro y contrato — es ML-12.)

Todo lo demás depende de esto. Cada fase posterior se añade **encima**, sin
reescribir lo que hay (§12: *«se amplía lo existente, no se reescribe»*).

## 2. Cómo se usa

```python
import academic_core.domain.engineering.mathlab as ML

ML.calcular(ML.Peticion("derivar", "x^3+2x")).como_texto()
```

```
operación: derivar
versión del contrato: 1.0
exacto: 3·x² + 2·1
sello: ✔ Verificado (forma idéntica)
gráfica: la función x³ + 2·x y su derivada 3·x² + 2·1 respecto a x, …
pasos:
1. [e01.regla de la potencia] d/dx x^n = n·x^(n-1)
   trozo: n = 3
   antes: d/dx[x^3]
   después: 3*x^(3 - 1)
…
6. [derivada.producto_cadena] se deriva respecto a «x» con las reglas del motor E0.1
   por qué este método: …
```

Operaciones disponibles: `derivar`, `gradiente`, `simplificar`, `evaluar`,
`igualdad`, `integrar`.

## 3. Los módulos

| Módulo | Responsabilidad |
|---|---|
| `mvexpr` | Expresiones exactas multivariables, parser con vista previa, objetos de cálculo de primera clase, puente al motor E0.1 |
| `poly` | Forma normal multivariable exacta y funciones racionales — el motor del corrector por equivalencia |
| `trace` | Traza de pasos versionada y serializable, con los tres niveles de detalle y el «por qué este método» obligatorio |
| `verify` | Los caminos independientes de §5.3 y los tres sellos |
| `derive_mv` | Derivadas parciales y totales, verificadas contra diferencias centrales |
| `contract` | La interfaz estable de §5.9 que usan los demás laboratorios |
| `calculators` | Las primeras calculadoras, registradas contra ese contrato |

## 4. Las cuatro reglas que el paquete no rompe

1. **Nada se da por correcto sin un segundo camino independiente** (§5.3,
   §11.2 criterio 2). Un resultado cuyo segundo camino falla recibe el sello
   `✘ Discrepa`, y `calcular()` no deja que el llamante lo ignore.
2. **El dominio es puro**: sin Qt, sin ficheros, sin red, sin biblioteca
   externa. Una librería como SymPy puede registrarse como *verificador* desde
   fuera (§5.8, D1), pero los pasos los da siempre este motor.
3. **`symbolic/` (E0.1) se reutiliza, no se reescribe**: el puente es
   `mvexpr.to_symbolic`, y sus reglas y explicaciones son la fuente de los
   pasos de derivación e integración.
4. **La honestidad por encima de la respuesta**: si no hay solución exacta se
   dice («no sé darte una solución exacta») y se ofrece el valor numérico
   **con su error acotado**. Un flotante nunca se redondea a una fracción
   exacta inventada.

## 5. Decisiones de diseño que conviene conocer

- **Nombre de variable**: una tirada de letras se descompone (`xy` = `x·y`,
  `2xy` = `2·x·y`); un nombre con dígito o guion bajo es una variable entera
  (`x1`, `t_0`). Los nombres reservados (`pi`, `e`, `i`, funciones) ganan
  siempre.
- **Coma decimal**: `,` siempre es un token separado. `0,5` es un medio
  (fuera de una lista de argumentos) y `raiz(8,3)` son dos argumentos (dentro).
  La decisión es del analizador, no del léxico, porque solo él sabe si está
  leyendo argumentos.
- **Átomos**: `sin(x)`, `pi` o `sqrt(2)` se tratan como indeterminados
  independientes en la forma normal. Por eso `x²·pi` **no** se reconoce como
  `3.14·x²`: son expresiones distintas, y el camino numérico decide si además
  son cercanas. Es un límite declarado, no un fallo silencioso.
- **`(x²−1)/(x−1) = x + 1` con hipótesis**: la cancelación es exacta, pero
  `x = 1` se conserva como valor excluido y la interfaz lo imprime (§5.7).
- **Identidad sin prueba exacta**: `sin(x)² + cos(x)² = 1` no tiene forma
  normal común, así que el sello es `⚠ Solo numérico`, nunca `✔ Verificado`.
  Muestrear puntos no demuestra una identidad.

## 6. Pruebas

| Fichero | Qué cubre |
|---|---|
| `tests/test_mathlab_ml0.py` | Parseo, exactitud, objetos de cálculo, equivalencia, traza, sellos, contrato y los límites honestos |
| `tests/test_mathlab_arch.py` | La puerta de arquitectura: sin Qt, sin capas superiores, sin los laboratorios que consumen este motor, sin biblioteca externa, sin `random` |

Las dosseries pasan. `test_mathlab_arch.py` lleva la marca `arch` y convive
con `test_architecture.py`.

## 7. Lo que NO existe todavía

Esto es ML-0, no el laboratorio completo. **No** está implementado:

- los bloques 0 a 19 del catálogo (§4): aritmética elemental, cálculo de una
  variable (límites, Taylor, estudio de funciones), álgebra lineal, series,
  varias variables, integración múltiple, Green/Stokes/Gauss, EDOs y
  transformadas, probabilidad y estadística, y los bloques nuevos 8 a 19
  (discreta, cuerpos finitos, códigos, información, Markov, aprendizaje
  automático, finanzas, señales, detección, fasores, campos, física);
- el graficador con Qt: ML-0 entrega la **gráfica descrita como datos**
  (`Graph`/`Serie`), que es lo que el contrato §5.9 exige; dibujarla es trabajo
  de la capa de interfaz;
- la plantilla única de ejercicio, el corrector de ejercicios, el generador
  sembrado y el enlace con la maestría (§7, ML-10);
- racionales multivariable con `R`, `C`, `K` simbólicos, cuerpo como parámetro,
  distribuciones con área y análisis dimensional (ML-12);
- el registro de SymPy/NumPy como verificador externo: el **mecanismo** existe
  (`registrar_verificador`) y está probado, pero ningún verificador real está
  registrado todavía.

El orden de fases y el contenido exacto de cada una están en `MATH_LAB.md` §10.
La siguiente fase natural es **ML-1** (bloque 0: aritmética y álgebra
elemental), que solo necesita `Trace` y `contract`, ya entregados.
