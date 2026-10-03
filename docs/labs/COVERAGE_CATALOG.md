# Catálogo maestro de cobertura de Laboratorios

Fecha: 2026-10-01

Este documento establece el nivel de exhaustividad obligatorio para los cinco laboratorios de AcademicCore. Su objetivo es evitar el patrón detectado en trigonometría: un documento puede declarar un área amplia sin haber descompuesto todas sus familias, casos límite, verificaciones y criterios de completitud.

## 1. Estados

- **DISEÑADO**: alcance definido, pero no necesariamente implementado.
- **ESPECIFICADO**: existe inventario de operaciones, casos, hipótesis y aceptación.
- **PARCIAL**: existe solo una parte funcional.
- **IMPLEMENTADO**: funcional en código.
- **TESTADO**: tests específicos cubren el alcance implementado.
- **VERIFICADO**: existe segundo camino independiente.
- **CERTIFICADO**: documentación, tests, verificación y CI cumplen el contrato.
- **PENDIENTE**: requisito conocido aún no implantado.

Regla: **documentar una capacidad nunca cambia su estado de implementación**.

## 2. Contrato común de cada familia

Cada familia temática de los cinco labs debe tener:

1. identificador estable;
2. objetivo;
3. operaciones;
4. casos normales;
5. casos límite y degenerados;
6. dominio/restricciones;
7. hipótesis;
8. métodos disponibles;
9. estrategia de selección del método;
10. transformaciones;
11. resultado exacto, si existe;
12. fallback numérico y error;
13. trazabilidad de pasos;
14. verificación independiente;
15. representación gráfica/diagrama cuando aplique;
16. calculadora;
17. tipos de ejercicio;
18. errores típicos del estudiante;
19. tests unitarios;
20. tests de propiedades/generativos cuando proceda;
21. integración;
22. documentación;
23. CI;
24. estado.

Una familia no puede declararse **CERTIFICADA** si falta cualquiera de los puntos aplicables.

---

# 3. MATH_LAB

## M-00 Aritmética y álgebra elemental
**Estado global: PARCIAL/pendiente de inventario exhaustivo.**

- enteros, racionales y reales;
- fracciones y simplificación;
- potencias y raíces;
- radicales;
- notación científica;
- proporciones y porcentajes;
- polinomios;
- productos notables;
- factorización;
- fracciones algebraicas;
- ecuaciones e inecuaciones;
- valor absoluto;
- sistemas elementales;
- logaritmos y exponenciales;
- números complejos;
- intervalos y desigualdades;
- dominio y restricciones.

## M-01 Funciones y trigonometría
**Estado: PARCIAL. T-01 a T-23 COMPLETADAS.**

Incluye funciones, inversas, identidades, periodicidad, ecuaciones, inecuaciones, hiperbólicas, complejos, fasores, derivadas, integrales, series, valores exactos, gráficas y verificación.

Lo implantado son las familias de identidades, ramas, ecuaciones, inecuaciones, dominio, complejos, fasores, derivadas, series y gráficas. Todas tienen un módulo propio con operación en `calculators.py` y un sello producido por un camino que no consulta el cálculo que dio la respuesta: sustitución de miembros para ecuaciones, muestreo bidireccional para inecuaciones, contraejemplo para ramas, contrato de fase con `CIRCUITS_LAB` para fasores, sensibilidad medida para el camino numérico, y muestreo denso de la función contra los hechos declarados para gráficas.

Lo que queda, y por qué:

- **T-14** sin derivadas ni integrales propias; las de la familia viven en T-17.
- **T-18** sin reducción de potencias de seno o coseno al integrando, y sin encadenar integración por partes para logaritmos. `sen(x)^2` se rechaza en vez de Integration by parts + double angle.
- **T-19** con un término de más en el polinomio de Taylor de un monomio. Las derivadas se comprueban una a una y son correctas; el fallo está en cómo se arman los términos. Hay una prueba que lo documenta sin aprobarlo. T-23 lo esquivó: donde hay serie conocida usa `series.maclaurin`, que es correcta, y avisa de que si no la hay va por `taylor`.
Lo que queda, y por qué:

- **T-18 cerrado entero.** Los tres huecos que quedaban eran el mismo fallo de lectura —una regla que mira una cosa y no la otra— y los tres están resueltos:
  - **Producto de dos potencias** (`sen(x)^3·cos(x)^2`): los tres casos clásicos lo convierten en una suma de potencias simples, y ninguna es nueva. Exponente impar en `sen`, impar en `cos`, y los dos pares por `sen^(2a)·cos^(2b) = 2^-(a+b)·(1-cos(2g))^a(1+cos(2g))^b`. Cada término es o `sen·cos^p` —que el cambio de variable siempre hizo— o `cos(2g)^k`, que es la reducción con factor de cadena.
  - **`∫sec^n`, `∫cosec^n`, `∫cot^n` para n ≥ 3**: `f^n = f^(n-2)·f^2`, con el cuadrado en la tabla. La cotangente NO tiene la misma forma que las otras dos, y escribirle la misma fórmula hacía que `∫sec^3` saliera con las piezas correctas y los coeficientes equivocados.
  - **`e^x·sen(x)`, `e^x·cos(x)`, `senh(x)^2`, `cosh(x)^2`**: entradas de tabla. La primera tiene forma cerrada y ningún cambio de variable la encuentra; las partes por dos veces vuelven a la integral de la que salieron.

  Lo que queda es un **límite declarado, no un hueco**: `sen(x)^6·cos(x)^6` se integra bien (234 caracteres) y su derivada no cabe en los 480. El motor devuelve una respuesta correcta que no puede comprobar, y la prueba lo dice y lo verifica por diferencias finitas.

**Auditoría de T-13, T-11, T-15 y T-16 cerrada: seis bugs de respuesta falsa.**
Un barrido por las familias que la auditoría anterior no cubría, buscando
respuestas **falsas** y no capacidades que faltaran. Los seis contestaban mal:

- **T-13: `sen(x) >= 1` publicaba `∅`.** La carta de signos recorre huecos, y una
  solución sin interior —el máximo es tangente, no un cambio de signo— no tiene
  ninguno que quedarse. Se cumple en `pi/2` y en `3pi/2`. También `sen(x) <= -1`,
  `cos(x) >= 1` y `cos(x) <= -1`. Un `∅` sobre una expresión llena de soluciones.
- **T-13: `<=` y `<` publicaban lo mismo** en `tg(x)`, con `pi` dentro de `< 0`. El
  extremo del periodo se decidía contra un conjunto de ceros ya doblado, sin doblar
  el punto, y `tg(pi) = -1e-16` pasa cualquier `< 0`.
- **T-13: `0·pi` y `periodo·pi` se contestaban distinto** siendo el mismo punto, en
  las doce combinaciones de operador sobre seno, coseno y tangente. La respuesta
  declara que se repite cada `P·pi`, así que no puede separarlos.
- **T-11: las dos ramas de `acosh(cosh)` estaban cambiadas de sitio.** El motor
  publicaba `x` en `(-inf, 0]` y `-x` en `[0, inf)`; `acosh(cosh(x)) = |x|` dice lo
  contrario. Y la **nota** de cada fila describía el lado correcto, así que el motor
  se contradecía a sí mismo y las dos frases decían la misma cosa falsa.
- **T-15: `arg` mal en el segundo cuadrante.** Con parte real negativa hay dos
  cuadrantes y se doblan en direcciones opuestas: `arg(-3 + 4i)` salía en -4.069 en
  vez de +2.214, fuera del rango `(-pi, pi]` que el módulo declara.
- **T-15: `principal=False` no era una vuelta más**, que es lo que su nombre
  prometía: devolvía el `atan(y/x)` sin doblar, que con parte real negativa no es un
  argumento del número.

Y un **bucle sin suelo**, preexistente: `periodo_minimo` partía el candidato por la
mitad con la condición `candidato / 2 > 0`, y un `Fraction` positivo partido por dos
nunca llega a cero. `sen(x)^2 + cos(x)^2 - 1/2` es la constante 1/2 escrita más
larga, repite tras cualquier desplazamiento, y **`sen(x)^2 + cos(x)^2 > 1/2`
colgaba el motor**. Ahora se niega con el motivo que ya daba `1 > 1/2`: no hay
periodo mínimo, y un periodo sin mínimo no lo usa una carta de signos.

Lo que salió limpio: T-16 entero, las otras cinco familias de ramas de T-11, y el
periodo, la frecuencia, la amplitud y los ceros de T-23. 159 comprobaciones nuevas
en `tests/test_mathlab_auditoria.py`, que pasa de 326 a 485.

**T-20 cerrado.** `trig.OBJETIVOS` declara los doce objetivos en un solo registro, con dos clases que no son la misma cosa:

- **reescritura** (`simplificar`, `expandir`, `producto_a_suma`, `suma_a_producto`, `potencias`, `sustitucion_universal`, `hiperbolicas`, `exponencial`): disparan reglas sobre subexpresiones y su respuesta es otra expresión, así que llevan un registro de familias **no vacío**. La entrada es un registro de reglas y cambia la forma de la expresión.
- **transformación** (`derivar`, `integrar`, `complejos`, `fasores`): llevan una expresión a algo de otro tipo —una derivada, una primitiva, un complejo, un fasor—. No tienen familias porque no reescriben nada, y lo que deben en su lugar es un `porque` escrito y un `verifica` que nombre el segundo camino.

Los cuatro vivían en los módulos que los necesitan, así que el motor no podía decir qué sabe hacer: **un objetivo que no se puede enumerar es uno que no se puede prometer**. Ahora están declarados con la disciplina que ya tenían los otros ocho, `trig.inventario()` los expone, y la calculadora escribe el método declarado en la trayectoria de `derivar`, `integrar`, `complejo` y `fasor`.

Lo que T-23_NO hace, declarado:

- **Asíntotas horizontales y oblicuas.** Necesitan el límite en el infinito y no hay motor de límites. Muestrear en un `x` grande no es un límite: un senoide da diez «límites» distintos en diez `x` grandes, y declarar `y = 0` porque uno de ellos salió pequeño sería inventar una recta a partir de una coincidencia.
- **Desplazamiento vertical `D`.** Una expresión de la forma `A·sen(Bx + C) + D` es un senoide y su amplitud es exacta, pero `D` no se reporta como parte de la forma canónica; sí aparece implícito en el desplazamiento de los ceros.
- **`sen(x) + cos(x)`** es un senoide, pero solo tras un desplazamiento de fase que el módulo tendría que buscar. Se declina en vez de contestarse a medias.
- **La existencia de un punto, comprobada por muestreo.** A `pi/2` el valor de `tan` es 6·10⁻¹⁷ y no cero, así que el muestreo no ve si una expresión existe ahí. La tabla simbólica es la autoridad, y el sello de T-23 lo dice en vez de fingir que lo comprobó.

El verificador de T-23 encontró tres huecos en T-12 y T-13. **Los tres están cerrados**, y el que se creyó un hueco resultó no serlo:

- `dominio.periodo_minimo("sen(x)/x")` respondía `2·π` y la función no es periódica. Ahora el periodo se pregunta a la expresión **entera**: la periodicidad sobrevive a sumas, productos y cocientes, así que una parte no periódica —la `x` desnuda del denominador— zanja la respuesta. `sen(x)/x`, `x + sen(x)` y `sen(x)·x` dan `None`.
- Los ceros de `5·sen(x + π/3)` daban `0`, que es donde se anula el seno sin desplazar. La causa era que `_afine` no veía la parte constante: `trig._factores` reparte productos y no sumas, así que `x + π/3` volvía como un factor único y todo desplazamiento salía «no afín». Con las sumas repartidas, `sen(x + π/3) = 0` da `-π/3 + 2k·π` y `2π/3 + 2k·π`.
- `sen(x)/x` declaraba `0` como cero, y `0/0` no es un cero: es un punto donde no está definido. Los ceros de un cociente son los de su numerador **menos** los puntos donde el denominador se anula, y esos se preguntan al dominio.

Una cuarta cosa salió de camino y **no** era un falso «no hay soluciones»: `resolver("x = 0")` se niega con el motivo correcto, fuera de los casos de T-12. Es una negativa honesta y así se queda; el filtro del cociente se apoya en el dominio precisamente para no depender de ella.

Y una afirmación de T-23 resultó **falsa**: decía que `1/tan(x)` es cotangente y que por tanto `pi/2` no es una discontinuidad suya. La cotangente lo es como función, pero la **expresión** `1/tan(x)` no existe en `pi/2`, porque `tan(pi/2)` no existe y el recíproco de nada es nada. El dominio del motor era correcto; la afirmación era el error. Lo que falta no es la discontinuidad sino la nota de que el hueco es **removible**, con límite 0.

El hueco **removible** que quedaba de T-23 también está cerrado: `inequaciones.removibles()` decide por estructura —el recíproco se simplifica a `cotg`, cuyo dominio sí incluye `pi/2`— y T-23 lo enseña. Un hueco que la simplificación no alcanza a cancelar se declara polo, que es el lado seguro: `sen(x)/x` en 0 está en ese caso aunque su límite sea 1.

Y el caso lineal del solucionador también: `x = 0` no era una ecuación exótica y estaba fuera de alcance. No era cosmético, porque `ceros` le pide al solucionador los ceros de un denominador. Arreglarlo destapó tres bugs de fondo —`0·pi` y `0` como dos puntos distintos, la regla de fusión de intervalos al revés, y un extremo infinito que nunca ganaba en una fusión— y uno de ellos, `x^2 = 0`, respondía «no hay soluciones» teniendo la solución `x = 0`.

## M-02 Cálculo diferencial
**Estado: PARCIAL.**

- definición y propiedades de límite;
- continuidad;
- derivadas por definición;
- reglas de derivación;
- producto/cociente/cadena;
- derivación implícita;
- derivación logarítmica;
- funciones inversas;
- derivadas parciales;
- derivadas de orden superior;
- extremos;
- Rolle/Lagrange;
- monotonicidad;
- convexidad;
- Taylor;
- optimización;
- análisis completo de funciones;
- diferenciación numérica y control de error.

## M-03 Cálculo integral
**Estado: PARCIAL.**

- primitivas básicas;
- sustitución;
- partes;
- fracciones simples;
- integrales racionales;
- radicales;
- trigonométricas;
- integrales impropias;
- integrales definidas;
- Barrow;
- áreas;
- volúmenes;
- longitud;
- convergencia;
- integrales no elementales;
- verificación por derivación;
- métodos numéricos y error.

## M-04 Límites y series
**Estado: PENDIENTE.**

- límites laterales;
- infinitos;
- indeterminaciones;
- equivalencias;
- Taylor/Maclaurin;
- resto y error;
- series numéricas;
- criterios de convergencia;
- series de potencias;
- radio/intervalo;
- series de funciones;
- aproximaciones asintóticas.

## M-05 Álgebra lineal
**Estado: PENDIENTE/PARCIAL.**

- vectores;
- matrices;
- operaciones;
- determinantes;
- rango;
- sistemas;
- Gauss;
- espacios vectoriales;
- bases;
- dimensión;
- cambio de base;
- transformaciones lineales;
- núcleo e imagen;
- ortogonalidad;
- Gram-Schmidt;
- mínimos cuadrados;
- autovalores;
- autovectores;
- diagonalización;
- formas canónicas;
- SVD;
- condiciones y estabilidad numérica.

## M-06 Cálculo vectorial
**Estado: PENDIENTE.**

- funciones multivariables;
- límites y continuidad multivariable;
- derivadas parciales;
- gradiente;
- Jacobiano;
- Hessiano;
- regla de la cadena;
- extremos multivariables;
- Lagrange;
- campos vectoriales;
- divergencia;
- rotacional;
- integrales dobles;
- triples;
- cambio de variables;
- coordenadas polares/cilíndricas/esféricas;
- integrales de línea;
- integrales de superficie;
- Green;
- Stokes;
- Gauss;
- potenciales;
- independencia de camino.

## M-07 Ecuaciones diferenciales y transformadas
**Estado: PENDIENTE/PARCIAL.**

- EDO de primer orden;
- separables;
- lineales;
- exactas;
- Bernoulli;
- Riccati cuando aplique;
- segundo orden;
- coeficientes constantes;
- forzamiento;
- sistemas;
- estabilidad;
- condiciones iniciales;
- problemas de contorno;
- Laplace;
- inversa;
- convolución;
- Fourier;
- series de Fourier;
- transformada z;
- EDP introductorias;
- calor 1D;
- oscilador;
- verificación sustituyendo en la ecuación.

## M-08 Probabilidad y estadística
**Estado: PENDIENTE.**

- combinatoria;
- probabilidad;
- condicional;
- Bayes;
- independencia;
- variables discretas/continuas;
- esperanza;
- varianza;
- covarianza;
- distribuciones;
- conjunta/marginal/condicional;
- transformaciones;
- ley de grandes números;
- TCL;
- estimación;
- intervalos;
- contraste;
- regresión;
- correlación;
- Monte Carlo;
- incertidumbre;
- Chauvenet según convención del curso.

## M-09 Métodos numéricos
**Estado: PARCIAL.**

- raíces;
- bisección;
- Newton;
- secante;
- sistemas;
- interpolación;
- splines;
- derivación numérica;
- integración numérica;
- cuadraturas;
- ODE;
- problemas de contorno;
- mínimos cuadrados;
- ajuste no lineal;
- trascendentes con múltiples raíces;
- Lambert W;
- estabilidad;
- convergencia;
- estimación de error;
- parada reproducible.

## M-10 Matemática discreta
**Estado: PENDIENTE.**

- lógica proposicional;
- predicados;
- conjuntos;
- relaciones;
- funciones;
- inducción;
- recursión;
- recurrencias;
- sumatorios;
- combinatoria;
- grafos;
- árboles;
- caminos;
- conectividad;
- algoritmos;
- complejidad;
- aritmética discreta.

## M-11 Modular y cuerpos finitos
**Estado: PENDIENTE.**

- congruencias;
- inversos;
- Euclides;
- CRT;
- potencias;
- orden;
- grupos/cuerpos cuando proceda;
- GF(p);
- GF(2);
- GF(2^m);
- polinomios sobre cuerpos finitos;
- Gauss parametrizado por cuerpo.

## M-12 Códigos y criptografía
**Estado: PENDIENTE.**

- códigos lineales;
- matrices generadora/paridad;
- Hamming;
- distancia;
- síndrome;
- CRC;
- corrección/detección;
- Shamir;
- RSA;
- Diffie-Hellman;
- aritmética modular aplicada;
- claves, inversas y condiciones de validez;
- privacidad diferencial/k-anonimato/microagregación cuando aplique.

## M-13 Teoría de la información
**Estado: PENDIENTE.**

- entropía;
- entropía conjunta/condicional;
- información mutua;
- KL;
- Huffman;
- codificación;
- capacidad;
- canal;
- tasa;
- eficiencia;
- límites de Shannon.

## M-14 Markov, MDP y aprendizaje por refuerzo
**Estado: PENDIENTE.**

- cadenas;
- matriz de transición;
- estados estacionarios;
- absorción;
- tiempos de paso;
- MDP;
- Bellman;
- política;
- valor;
- Q-learning;
- exploración/explotación;
- bandidos;
- simulación sembrada.

## M-15 Optimización y ML
**Estado: PENDIENTE.**

- optimización sin restricciones;
- restricciones;
- gradiente;
- Newton;
- convexidad;
- mínimos cuadrados;
- regresión lineal;
- logística;
- métricas;
- k-means;
- PCA;
- SVD;
- descenso de gradiente;
- backpropagation a mano;
- regularización;
- convergencia.

## M-16 Matemáticas financieras
**Estado: PENDIENTE.**

- interés simple/compuesto;
- anualidades;
- VAN/TIR;
- bonos;
- duración;
- futuros;
- CRR;
- Black-Scholes;
- griegas;
- Monte Carlo;
- Markowitz;
- rentabilidad/riesgo;
- convenciones financieras.

## M-17 Señales matemáticas
**Estado: PARCIAL / frontera con SIGNALS_LAB.**

- señales deterministas;
- energía/potencia;
- convolución;
- correlación;
- series de Fourier;
- DTFT;
- DFT;
- z;
- PSD determinista;
- representaciones exactas;
- verificación.

## M-18 Detección y estimación
**Estado: PENDIENTE.**

- MAP;
- ML;
- Neyman-Pearson;
- ROC;
- Cramér-Rao;
- MVUE;
- MMSE;
- Wiener;
- Wiener-Hopf;
- LMS/NLMS;
- PSD de procesos discretos;
- simulación Monte Carlo y comparación teoría/experimento.

## M-19 Fasores, polarización, campos y ondas
**Estado: PENDIENTE.**

- fasores;
- polar;
- exponencial compleja;
- onda plana;
- medios con pérdidas;
- Jones;
- retardadores;
- Fresnel;
- Brewster;
- reflexión total;
- electrostática;
- Coulomb;
- Biot-Savart;
- Ampère;
- Maxwell;
- ondas;
- Poynting;
- antenas/enlace como frontera.

---

# 4. CIRCUITS_LAB

## C-01 Fundamentos y análisis sistemático
**Estado: ESPECIFICADO/PARCIAL.**

- clasificación del circuito;
- KCL/KVL;
- nodos;
- supernodos;
- mallas;
- supermallas;
- MNA;
- fuentes dependientes;
- transformación de fuentes;
- Millman;
- reciprocidad;
- Tellegen;
- selección y justificación de método.

## C-02 Equivalentes
**Estado: ESPECIFICADO.**

- Thévenin;
- Norton;
- fuente de prueba;
- máxima transferencia;
- equivalentes con dependientes;
- reducción;
- verificación independiente.

## C-03 DC y potencia
**Estado: ESPECIFICADO/PARCIAL.**

- resistivo;
- divisores;
- potencia;
- energía;
- conservación;
- superposición;
- tolerancias.

## C-04 AC y fasores
**Estado: ESPECIFICADO/PARCIAL.**

- impedancias;
- admitancias;
- fasores;
- potencia activa/reactiva/aparente;
- factor de potencia;
- resonancia;
- frecuencia;
- convenciones RMS/pico.

## C-05 Transitorios
**Estado: ESPECIFICADO/PARCIAL.**

- RC;
- RL;
- RLC;
- primer/segundo orden;
- condiciones iniciales;
- conmutación;
- eventos;
- continuidad;
- estabilidad;
- energía.

## C-06 Laplace y funciones de transferencia
**Estado: ESPECIFICADO/PENDIENTE.**

- H(s);
- polos/ceros;
- fracciones parciales;
- respuesta impulsional;
- escalón;
- convolución;
- cascadas;
- carga;
- condiciones iniciales.

## C-07 Dos puertos
**Estado: ESPECIFICADO/PARCIAL.**

- z/y/h/g/ABCD;
- conversiones;
- cascada;
- terminación;
- ganancia;
- impedancias de entrada/salida;
- reciprocidad/simetría.

## C-08 Bode, filtros y resonancia
**Estado: ESPECIFICADO/PARCIAL.**

- forma factorizada;
- magnitud;
- fase;
- aproximación;
- errores de aproximación;
- pasa-bajo/alto/banda/rechaza-banda;
- Q;
- resonancia;
- filtros pasivos/activos.

## C-09 Semiconductores
**Estado: ESPECIFICADO/PENDIENTE.**

- unión PN;
- diodo;
- Zener;
- rectificación;
- BJT;
- MOSFET;
- JFET;
- regiones;
- polarización;
- punto Q;
- pequeña señal;
- modelos;
- límites;
- térmica.

## C-10 Analógico
**Estado: ESPECIFICADO/PENDIENTE.**

- amplificadores;
- etapas;
- op-amp;
- ideal/no ideal;
- realimentación;
- estabilidad;
- osciladores;
- filtros;
- ruido;
- referencias;
- PLL;
- ADC/DAC.

## C-11 RF
**Estado: ESPECIFICADO/PENDIENTE.**

- líneas;
- impedancia característica;
- reflexión;
- VSWR;
- Smith;
- adaptación;
- S;
- ABCD;
- ruido;
- Friis;
- guías;
- pérdidas;
- potencia.

## C-12 Energía y tecnología
**Estado: ESPECIFICADO/PENDIENTE.**

- fuentes;
- convertidores;
- rectificadores;
- regulación;
- eficiencia;
- térmica;
- disipación;
- cables;
- transformadores;
- magnetismo.

## C-13 Control y medida
**Estado: ESPECIFICADO/PENDIENTE.**

- GUM;
- incertidumbre;
- propagación;
- calibración;
- ajuste;
- sensores;
- instrumentación;
- valores aberrantes;
- trazabilidad metrológica.

---

# 5. SIGNALS_LAB

## S-01 Biblioteca de señales
**Estado: ESPECIFICADO/PARCIAL.**

- seno/coseno;
- escalón/impulso;
- exponenciales;
- periódicas;
- pulsos;
- chirp;
- ruido;
- audio/WAV;
- señales paramétricas;
- semilla reproducible.

## S-02 Sistemas LTI
**Estado: ESPECIFICADO/PARCIAL.**

- linealidad;
- invariancia;
- causalidad;
- estabilidad;
- memoria;
- convolución;
- respuesta impulsional;
- respuesta a sinusoide;
- polos/ceros;
- eco.

## S-03 Espectro
**Estado: ESPECIFICADO/PARCIAL.**

- Fourier;
- espectros;
- amplitud/fase;
- DFT;
- DTFT;
- FFT;
- hermiticidad;
- lectura directa e inversa;
- incertidumbre de identificación.

## S-04 Ventanas
**Estado: ESPECIFICADO.**

- rectangular;
- Hann;
- Hamming;
- Blackman;
- Kaiser;
- triangular;
- sidelobes;
- ENBW;
- ancho de lóbulo;
- resolución;
- medidas doradas.

## S-05 Muestreo y reconstrucción
**Estado: ESPECIFICADO/PENDIENTE.**

- Nyquist;
- aliasing;
- réplicas;
- plegado;
- muestreo ideal/real;
- reconstrucción;
- DAC/ADC;
- cuantización;
- SQNR.

## S-06 Modulación y multiplexación
**Estado: ESPECIFICADO/PENDIENTE.**

- AM;
- DSB;
- SSB;
- FM;
- modulación digital;
- demodulación;
- FDM;
- TDM;
- solapes;
- Hilbert;
- filtros asociados.

## S-07 FIR
**Estado: ESPECIFICADO/PARCIAL.**

- especificación;
- ventanas;
- muestreo en frecuencia;
- sinc truncada;
- Kaiser;
- orden;
- ceros;
- respuesta;
- filtrado.

## S-08 IIR
**Estado: ESPECIFICADO/PARCIAL.**

- Butterworth;
- Chebyshev I/II;
- elíptico;
- prototipos;
- transformación bilineal;
- prewarping;
- SOS;
- estabilidad;
- cuantización.

## S-09 Parks-McClellan
**Estado: ESPECIFICADO/PENDIENTE.**

- Remez;
- alternancia;
- error ponderado;
- orden mínimo;
- tipos de filtro;
- convergencia;
- verificación independiente.

## S-10 STFT y espectrograma
**Estado: ESPECIFICADO/PENDIENTE.**

- ventanas;
- hop;
- resolución tiempo/frecuencia;
- magnitud/fase;
- escalas;
- coste;
- visualización.

## S-11 Multirate
**Estado: ESPECIFICADO/PENDIENTE.**

- decimación;
- interpolación;
- resampling;
- filtros anti-alias;
- polifase;
- conversión racional.

## S-12 Procesos y detección
**Estado: ESPECIFICADO/PENDIENTE.**

- autocorrelación;
- PSD;
- detección;
- estimación;
- ROC;
- Monte Carlo;
- intervalos de confianza;
- comparación teoría/experimento.

---

# 6. DIGITAL_DESIGN_LAB

## D-01 Álgebra de Boole
**Estado: ESPECIFICADO/PENDIENTE.**

- variables;
- AND/OR/NOT;
- NAND/NOR;
- XOR/XNOR;
- leyes;
- De Morgan;
- absorción;
- consenso;
- dualidad;
- reescritura con traza.

## D-02 Representaciones
**Estado: ESPECIFICADO/PENDIENTE.**

- expresión;
- tabla;
- minitérminos;
- maxitérminos;
- SOP;
- POS;
- formas canónicas;
- don't-care.

## D-03 Karnaugh
**Estado: ESPECIFICADO/PENDIENTE.**

- 2–6 variables;
- agrupaciones;
- wrap;
- don't-care;
- múltiples salidas;
- solución mínima;
- equivalencia.

## D-04 Minimización algorítmica
**Estado: ESPECIFICADO/PENDIENTE.**

- Quine-McCluskey;
- Petrick;
- Espresso;
- coste;
- multisalida.

## D-05 Equivalencia
**Estado: ESPECIFICADO/PENDIENTE.**

- tabla exhaustiva;
- BDD;
- SAT/DPLL/CDCL;
- contraejemplo;
- escalabilidad.

## D-06 Síntesis
**Estado: ESPECIFICADO/PENDIENTE.**

- expresión→circuito;
- tabla→circuito;
- NAND-only;
- NOR-only;
- AOI;
- MUX;
- ROM;
- PLA;
- tecnología objetivo.

## D-07 Hazards
**Estado: ESPECIFICADO/PENDIENTE.**

- estáticos;
- dinámicos;
- glitches;
- detección;
- mitigación.

## D-08 Lógica secuencial
**Estado: ESPECIFICADO/PENDIENTE.**

- latch;
- flip-flop;
- registros;
- shift;
- contadores;
- divisores;
- temporización.

## D-09 FSM
**Estado: ESPECIFICADO/PENDIENTE.**

- Moore;
- Mealy;
- transición;
- estados ilegales;
- alcanzabilidad;
- minimización;
- recuperación.

## D-10 Timing
**Estado: ESPECIFICADO/PENDIENTE.**

- setup;
- hold;
- retardos;
- frecuencia máxima;
- metastabilidad;
- sincronización.

## D-11 Calculadoras digitales
**Estado: ESPECIFICADO/PENDIENTE.**

- bases;
- complemento a 2;
- Gray;
- BCD;
- IEEE-754;
- fixed-point;
- paridad;
- Hamming;
- CRC;
- aritmética;
- Booth.

## D-12 Simulación ampliada
**Estado: PARCIAL/PENDIENTE.**

- 2/4 estados;
- X/Z;
- retardos;
- eventos;
- estímulos;
- trazas;
- replay;
- serialización;
- VCD.

---

# 7. AEROSPACE_LAB

## A-01 Mecánica orbital
**Estado: ESPECIFICADO/PARCIAL.**

- Kepler;
- elementos orbitales;
- anomalías;
- posición/velocidad;
- periodo;
- energía;
- tipos de órbita;
- Hohmann;
- J2;
- propagación;
- visibilidad.

## A-02 Ground track y geometría
**Estado: ESPECIFICADO/PARCIAL.**

- latitud/longitud;
- huella;
- elevación;
- acimut;
- distancia;
- ventana de visibilidad;
- duración;
- Doppler.

## A-03 Antenas y propagación
**Estado: ESPECIFICADO/PENDIENTE.**

- ganancia;
- apertura;
- patrón;
- polarización;
- pérdidas;
- espacio libre;
- gases;
- lluvia;
- atmósfera;
- enlaces.

## A-04 Balance de enlace
**Estado: ESPECIFICADO/PARCIAL.**

- potencia;
- EIRP/PIRE;
- FSPL;
- G/T;
- temperatura;
- C/N0;
- Eb/N0;
- BER;
- margen;
- uplink/downlink;
- transpondedor.

## A-05 Ruido
**Estado: ESPECIFICADO/PARCIAL.**

- temperatura de ruido;
- figura de ruido;
- Friis;
- cascadas;
- ruido de antena;
- contribuciones del receptor.

## A-06 Capa física
**Estado: ESPECIFICADO/PENDIENTE.**

- modulación;
- codificación;
- eficiencia espectral;
- Shannon;
- BER;
- ganancia de codificación;
- límites de enlace.

## A-07 Diagramas de enlace
**Estado: ESPECIFICADO/PENDIENTE.**

- transmisor;
- antena;
- canal;
- receptor;
- LNA;
- transpondedor;
- cadena de cálculo;
- correspondencia diagrama↔modelo.

---

# 8. Auditoría transversal

Además del contenido técnico, los cinco labs deben compartir el mismo catálogo de capacidades académicas:

| Capacidad | MATH | CIRCUITS | SIGNALS | DIGITAL | AERO |
|---|---|---|---|---|---|
| Enunciado estructurado | ✓ | ✓ | ✓ | ✓ | ✓ |
| Datos tipados | ✓ | ✓ | ✓ | ✓ | ✓ |
| Hipótesis | ✓ | ✓ | ✓ | ✓ | ✓ |
| Selección de método | ✓ | ✓ | ✓ | ✓ | ✓ |
| Pasos explicados | ✓ | ✓ | ✓ | ✓ | ✓ |
| Verificación independiente | ✓ | ✓ | ✓ | ✓ | ✓ |
| Incertidumbre/error | ✓ | ✓ | ✓ | ✓ | ✓ |
| Gráfica/diagrama | ✓ | ✓ | ✓ | ✓ | ✓ |
| Ejercicio paramétrico | ✓ | ✓ | ✓ | ✓ | ✓ |
| Semilla reproducible | ✓ | ✓ | ✓ | ✓ | ✓ |
| Corrección de errores | ✓ | ✓ | ✓ | ✓ | ✓ |
| Historial de intentos | ✓ | ✓ | ✓ | ✓ | ✓ |
| Exportación de informe | ✓ | ✓ | ✓ | ✓ | ✓ |
| Accesibilidad | ✓ | ✓ | ✓ | ✓ | ✓ |

## 9. Regla de auditoría

A partir de este documento, una frase como:

> “MathLab tiene trigonometría”

ya no se considera evidencia suficiente.

Debe poder responderse:

> ¿Qué funciones? ¿Qué identidades? ¿Qué dominios? ¿Qué transformaciones? ¿Qué casos límite? ¿Qué método de resolución? ¿Qué verificación? ¿Qué tests? ¿Qué CI? ¿Qué estado?

La misma regla se aplica a circuitos, señales, digital y aeroespacial.

## 10. Próxima clasificación

Los documentos individuales conservan el detalle propio de cada laboratorio. Este catálogo es el índice de control. Cuando una familia se amplíe, debe actualizarse su entrada y su documento de laboratorio, manteniendo el mismo ID y sin convertir documentación en falsa evidencia de implementación.


## Auditoría de la trigonometría

Un barrido del motor entero buscando **respuestas falsas**, no capacidades
faltantes. Vive en `tests/test_mathlab_auditoria.py` (326 comprobaciones) y
comprueba cada cosa por un camino que no consulta el cálculo que la produjo:

| familia | segundo camino |
|---|---|
| identidades | `numeric_agreement` con puntos sembrados, más control negativo |
| derivadas | las dos tablas de derivadas, en los dos árboles de expresiones |
| integrales | derivar la primitiva y compararla con el integrando |
| ecuaciones | sustituir cada miembro en la ecuación **original** |
| ceros, dominio, periodo | conjunto exacto y las banderas abierto/cerrado |
| series | el error tiene que **bajar** al subir el orden |
| gráficas | el sello del módulo, que muestrea la función |
| conversión entre árboles | ida y vuelta numérica |

Encontró dos bugs reales que ninguna otra prueba veía:

- **`x^(3/2)` volvía del otro árbol como `√x`.** El numerador del exponente se
  perdía en la conversión, y la primitiva de `√x` —que es `x^(3/2)·2/3`— salía
  `2·√x/3`, cuya derivada es `1/(3√x)`. El primer arreglo puso el numerador
  encima de la raíz y dio `x^3·√x`, que es `x^(7/2)` y sale 35 veces demasiado
  grande. Las dos versiones **se imprimen como una potencia fraccionaria** y sólo
  derivar lo delata: la parte entera va DEBAJO de la raíz.
- **El bucle de Taylor leía el término de orden k con la derivada de orden k+1**
  mientras el coeficiente salía como recíproco. Dos fallos que se cancelaban, que
  es la razón por la que todo valor intermedio parecía plausible.
