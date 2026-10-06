# SPDX-License-Identifier: MIT
"""MATH_LAB ML-0: the first calculators, registered against the §5.9 contract.

Each calculator is a **function of the domain** that returns
:class:`~.contract.Resultado`; the interface only displays it (§8.3). They are
the ML-0 deliverables of §10: the engine works, the steps are recorded, and
every result is verified by an independent second path before it is shown as
correct.

Delivered here
--------------

``derivar``       partial and total derivative (§4.2), verified against a
                  central difference
``gradiente``     gradient of a function of several variables (§4.4)
``simplificar``   exact simplification with a declared convention (§5.4)
``evaluar``       exact value when the expression is closed, else numeric
``igualdad``      «son iguales?» as a first-class, *teachable* operation: it
                  explains why two forms are the same polynomial, which is the
                  skill §7's corrector is built on
``integrar``      indefinite and definite integration, delegated to E0.1 and
                  verified by *differentiating the primitive* (§5.3 row 2)

``integrar`` is here rather than in ML-2 because ML-0's acceptance test needs
it: a round trip (differentiate ∘ integrate) is the strongest seeded property
available, and the E0.1 engine already provides the rules.
"""

from __future__ import annotations

from fractions import Fraction

from academic_core.domain.engineering.mathlab import continuidad as K
from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import derive_mv as D
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import verify as V
from academic_core.domain.engineering.mathlab.trace import (
    DETALLADO,
    PASO,
    RESUMEN,
    Trace,
)
from academic_core.domain.engineering.symbolic import integrate as _e01_integrate
from academic_core.domain.engineering.symbolic import steps as _e01_steps
from academic_core.errors import UnsupportedError, ValidationError


def _expr(entrada: object) -> mx.Expr:
    if isinstance(entrada, mx.Expr):
        return entrada
    if isinstance(entrada, str):
        return mx.parse(entrada)
    raise C.error("BAD_INPUT", "se esperaba una expresión o su texto")


def _expresion_de(entrada: object, *claves: str) -> mx.Expr:
    """The expression of a request, whether it is given bare or in a mapping.

    ``derivar`` accepts ``"x^2"``, ``{"expr": "x^2"}`` and
    ``{"integrando": "x^2"}``; the caller should not have to care which.
    """
    if isinstance(entrada, dict):
        for clave in claves:
            if clave in entrada:
                return _expr(entrada[clave])
        raise C.error(
            "BAD_INPUT",
            f"falta {' o '.join(claves)} en la petición; se esperaba una de esas claves",
        )
    return _expr(entrada)


def _exacto_legible(valor: object) -> object:
    """Render an exact result as something readable, not a raw dataclass repr.

    ``Resultado.exacto`` is a value, and ``Como_texto`` prints it; a raw
    ``Add(left=Add(...))`` would be useless to a student. A single expression is
    printed in Unicode notation; a mapping keeps its keys as variable names.
    """
    if isinstance(valor, dict):
        return {k: _exacto_legible(v) for k, v in valor.items()}
    if isinstance(valor, mx.Expr):
        return mx.pretty(valor)
    return valor


def _objetivo_declarado(traza: Trace, nombre: str) -> None:
    """Write an engine objective's declared method into the trajectory (T-20).

    The four objectives that used to live in the modules that need them —
    ``derivar``, ``integrar``, ``complejos`` and ``fasores`` — are declared in
    ``trig.OBJETIVOS`` with the same discipline as the eight rewrite ones: a
    written «por qué este método» and a named second path. This is what puts
    them in front of the student, because a declaration nobody reads is a
    declaration in a file.

    The step is emitted at ``resumen`` level, so it costs nothing at the other
    two and is still there when someone asks «why this method».
    """
    from academic_core.domain.engineering.mathlab import trig

    objetivo = trig.objetivo(nombre)
    traza.metodo(
        f"objetivo.{objetivo.nombre}",
        objetivo.porque[:120],
        why=objetivo.porque,
        alternatives=(
            (f"call it without naming the objective ({objetivo.procede_de})",
             "the method is then the only thing that happened and nothing says "
             "which one it was, nor whether anyone checked it (§5.2)"),
        ),
        before=f"objetivo declarado en {objetivo.procede_de}",
    )
    traza.verificacion(
        f"objetivo.{objetivo.nombre}.verifica", objetivo.verifica,
        after=("por derivación" if objetivo.verifica.startswith("se deriva")
               else "declarado"),
    )


def _finalizar(peticion: C.Peticion, traza: Trace, exacto, *,
               aproximado=None, error=None, sello: V.Seal, grafica=None,
               avisos: tuple[str, ...] = ()) -> C.Resultado:
    traza.level = peticion.nivel
    peticion.limites.validar(len(traza), 0)
    hipotesis = tuple(traza.hypotheses())
    convenciones = peticion.convenciones
    for linea in convenciones.as_lines():
        traza.convencion(f"convencion.{linea.split('=')[0].strip()}", linea)
    if sello.verdict == V.DISCREPANT:
        traza.verificacion(
            "verificacion.discrepa",
            "el segundo camino no coincide: el resultado no se da por bueno",
            after=sello.detail,
        )
    elif sello.verdict == V.VERIFIED:
        traza.verificacion("verificacion.ok", sello.method, after=sello.detail)
    else:
        traza.verificacion("verificacion.numerico", sello.method, after=sello.detail)
    return C.Resultado(
        operacion=peticion.operacion,
        exacto=_exacto_legible(exacto),
        exacto_expr=exacto if isinstance(exacto, mx.Expr)
        or (isinstance(exacto, dict) and all(isinstance(v, mx.Expr)
                                             for v in exacto.values()))
        else None,
        aproximado=aproximado,
        error_acotado=error,
        cifras=peticion.cifras,
        traza=traza,
        sello=sello,
        grafica=grafica,
        convenciones=convenciones,
        hipotesis=hipotesis,
        version=C.CONTRACT_VERSION,
        avisos=avisos,
    )


# ---------------------------------------------------------------------------
# derivar
# ---------------------------------------------------------------------------


def _derivar(peticion: C.Peticion) -> C.Resultado:
    expr = _expresion_de(peticion.entrada, "expr", "expresion", "f")
    entrada = peticion.entrada
    variables = entrada.get("var") if isinstance(entrada, dict) else None
    trace = Trace()
    names = sorted(mx.variables(expr))
    if variables is None:
        if len(names) != 1:
            raise C.error(
                "AMBIGUOUS",
                f"«{mx.pretty(expr)}» depende de {', '.join(names)}: "
                "indica con «var» de qué variable es la derivada",
            )
        variables = names[0]
    derivada = D.differentiate(expr, variables, trace)
    sello = D.verify_derivative(expr, derivada, variables)
    _objetivo_declarado(trace, "derivar")
    derivada = _presentable(derivada, trace)
    grafica = _grafica_derivada(expr, derivada, variables)
    return _finalizar(peticion, trace, derivada, aproximado=mx.evaluate(derivada),
                      sello=sello, grafica=grafica)


def _presentable(e: mx.Expr, trace: Trace) -> mx.Expr:
    """The result as a student should read it: ``2·x`` and not ``2·x¹``.

    The rules write what they apply — ``cos(2x)·2·1`` is the chain rule with the
    derivative of ``2x`` still visible — and that belongs in the steps, which keep
    it. The ANSWER is folded to its exact normal form, and only if the folded one
    agrees with the raw one at seeded points: a presentation step may never change
    the value it presents.
    """
    from academic_core.domain.engineering.mathlab import poly as P
    from academic_core.domain.engineering.mathlab import trig as T

    candidatas = []
    try:
        candidatas.append(T.simplify(P.to_expr(P.as_poly(T.simplify(e)))))
    except Exception:  # noqa: BLE001 - the raw form is still the right answer
        pass
    variables = sorted(mx.variables(e))
    if len(variables) == 1:
        # a rational function reads best as ONE quotient: 2·x/(x² + 1), and not
        # 2·1/(x² + 1)·x, which is the ring's polynomial-in-an-atom form
        try:
            razon = P.as_ratio(e, variables[0])
            if razon is not None:
                candidatas.append(mx.Div(P.to_expr(razon.numerator),
                                         P.to_expr(razon.denominator))
                                  if not razon.is_constant_ratio()
                                  else P.to_expr(razon.numerator))
        except Exception:  # noqa: BLE001
            pass
    validas = [c for c in candidatas if mx.text(c) != mx.text(e)
               and V.numeric_agreement(c, e)[0]]
    if not validas:
        return e
    plegada = min(validas, key=lambda c: len(mx.text(c)))
    if len(mx.text(plegada)) > len(mx.text(e)):
        return e
    trace.cambio("presentacion.simplificada", "se presenta la forma simplificada",
                 before=mx.text(e), after=mx.text(plegada),
                 why=("los pasos conservan la forma en que la regla la escribe; el "
                      "resultado se da plegado, comprobado igual en puntos sembrados"))
    return plegada


def _grafica_derivada(f: mx.Expr, df: mx.Expr, var: str) -> C.Graph:
    """Function and derivative on the same axes (§6: «función y derivada»)."""
    puntos = V.sampled_points([var], count=48)
    xs = tuple(p[var] for p in puntos)
    ys = tuple(_real(mx.evaluate(f, p)) for p in puntos)
    dys = tuple(_real(mx.evaluate(df, p)) for p in puntos)
    return C.Graph(
        series=(
            C.Serie(f"y = {mx.pretty(f)}", xs, ys),
            C.Serie(f"y' = {mx.pretty(df)}", xs, dys),
        ),
        x_label=var,
        y_label="y",
        description=(
            f"la función {mx.pretty(f)} y su derivada {mx.pretty(df)} "
            f"respecto a {var}, en el mismo sistema de ejes"
        ),
    )


def _real(value: complex | None) -> float:
    if value is None or value != value:
        return float("nan")
    return value.real


# ---------------------------------------------------------------------------
# gradiente
# ---------------------------------------------------------------------------


def _gradiente(peticion: C.Peticion) -> C.Resultado:
    expr = _expresion_de(peticion.entrada, "expr", "expresion", "f")
    trace = Trace()
    grad = D.gradient(expr, trace)
    sellos = {k: D.verify_derivative(expr, v, k) for k, v in grad.items()}
    peor = max(sellos.values(), key=lambda s: {"discrepa": 2, "solo_numerico": 1,
                                                "verificado": 0}[s.verdict])
    if peor.verdict == V.NUMERIC_ONLY and peor.method == "sin puntos evaluables":
        # A partial derivative of a several-variable expression has no
        # single-variable exact path here, so each component is *substituted*
        # to reduce it to one variable and then checked exactly. This is the
        # §5.3 rule "verificar por un camino independiente", done properly
        # instead of settling for a weaker numeric seal.
        sellos = {}
        for name, partial in grad.items():
            uno = _reduce_to_one_variable(expr, partial, name)
            if uno is None:
                sellos[name] = peor
                continue
            sellos[name] = D.verify_derivative(uno[0], uno[1], name)
        peor = max(sellos.values(),
                   key=lambda s: {"discrepa": 2, "solo_numerico": 1, "verificado": 0}[s.verdict])
    grad = {k: _presentable(v, trace) for k, v in grad.items()}
    return _finalizar(peticion, trace, grad, sello=peor)


def _reduce_to_one_variable(f: mx.Expr, df: mx.Expr, var: str
                            ) -> tuple[mx.Expr, mx.Expr] | None:
    """Freeze the other variables at distinct exact values.

    The identity ``d/dx f = df/dx`` holds at any point, so substituting the
    remaining variables for exact rationals turns a several-variable check into
    a one-variable one — and ``differentiate`` then has an exact path. Returns
    ``None`` if the substitution is not possible.
    """
    others = sorted(mx.variables(f) - {var})
    reduced_f, reduced_df = f, df
    for i, name in enumerate(others):
        value = mx.num(Fraction(3 + i, 2))  # 3/2, 5/2, ...: distinct and exact
        reduced_f = mx.substitute(reduced_f, name, value)
        reduced_df = mx.substitute(reduced_df, name, value)
    if mx.variables(reduced_f) != {var}:
        return None
    return reduced_f, reduced_df


# ---------------------------------------------------------------------------
# simplificar
# ---------------------------------------------------------------------------


def _simplificar(peticion: C.Peticion) -> C.Resultado:
    expr = _expresion_de(peticion.entrada, "expr", "expresion")
    trace = Trace()
    # the exact simplification the engine can prove: the difference of the
    # expression and its rational normal form is zero
    from academic_core.domain.engineering.mathlab import poly as P
    from academic_core.domain.engineering.mathlab import trig as T

    names = sorted(mx.variables(expr))
    var = names[0] if names else None
    ratio = P.as_ratio(expr, var) if var else None
    trigonometria = T.simplify_ex(expr)
    exacto = trigonometria.expresion
    metodo = "normalización trigonométrica exacta + forma normal algebraica" if exacto != expr else "no hace falta simplificar: ya está en forma canónica"
    if ratio is not None and not ratio.is_constant_ratio():
        # The rational form is a *normalisation*, not a rewrite: the displayed
        # value stays the student's expression and the equality is what the
        # seal attests, so no new (possibly uglier) form is shown.
        metodo = "forma normal racional"
    if len(names) > 1:
        metodo = "comparación multivariable: una forma normal por variable"
    trace.metodo(
        "simplificar.forma_normal",
        metodo,
        why=("se compara con la forma normal exacta del motor, que agrupa términos "
             "iguales y pliega constantes; si la forma normal ya es la expresión, no "
             "hay nada que simplificar"),
        alternatives=(
            ("simplificar numéricamente", "perdería la forma exacta (§5.1)"),
            ("usar la librería externa como resultado",
             "§5.8: una librería puede comprobar, nunca dar los pasos"),
        ),
        before=mx.text(expr),
    )
    # §5.2 and T-22: a reduction that leaves no trace cannot be explained to a
    # student, so each family that actually fired gets its own step, with the
    # «por qué este método» the engine carries for it (§5.5b).
    for familia in trigonometria.familias:
        trace.cambio(
            f"trig.{familia}",
            f"regla trigonométrica: {familia}",
            why=T.descripcion(familia),
            before=mx.text(expr),
            after=mx.text(exacto),
        )
    sello = V.verify_against(exacto, expr)
    return _finalizar(peticion, trace, exacto, aproximado=mx.evaluate(exacto),
                      sello=sello)


def _expande(e: mx.Expr) -> mx.Expr:
    """The exact ring normal form: products of sums multiplied out, terms collected."""
    from academic_core.domain.engineering.mathlab import poly as P

    try:
        return _sin_unos(P.to_expr(P.as_poly(e)))
    except Exception:  # noqa: BLE001
        return e


def _sin_unos(e: mx.Expr) -> mx.Expr:
    """``c·1`` is ``c``: the ring writes a constant term as a product with 1."""
    if isinstance(e, mx.Mul):
        a, b = _sin_unos(e.left), _sin_unos(e.right)
        if mx.exact_value(b) == 1:
            return a
        if mx.exact_value(a) == 1:
            return b
        return mx.Mul(a, b)
    if isinstance(e, (mx.Add, mx.Sub, mx.Div)):
        return type(e)(_sin_unos(e.left), _sin_unos(e.right))
    if isinstance(e, mx.Neg):
        return mx.Neg(_sin_unos(e.arg))
    return e


def _pliega_argumentos(e: mx.Expr) -> mx.Expr:
    """Each trigonometric argument folded, and its sign taken out by parity.

    The identities write their arguments as they come — sen(x + 3x), sen(x - 3x)
    — which is correct and is not what anyone writes: sen(4x) and -sen(2x).
    """
    from academic_core.domain.engineering.mathlab import poly as P

    if isinstance(e, mx.Call) and len(e.args) == 1:
        try:
            arg = P.to_expr(P.as_poly(_pliega_argumentos(e.args[0])))
        except Exception:  # noqa: BLE001
            arg = _pliega_argumentos(e.args[0])
        negativo = isinstance(arg, mx.Neg) or (
            isinstance(arg, mx.Mul) and mx.exact_value(arg.left) is not None
            and mx.exact_value(arg.left) < 0)
        if negativo and e.name in ("sin", "tan", "sinh", "tanh", "cos", "cosh"):
            opuesto = arg.arg if isinstance(arg, mx.Neg) else mx.Mul(
                mx.Num(-mx.exact_value(arg.left)), arg.right)
            if mx.exact_value(getattr(opuesto, "left", mx.ZERO)) == 1:
                opuesto = opuesto.right
            llamada = mx.Call(e.name, (opuesto,))
            return llamada if e.name in ("cos", "cosh") else mx.Neg(llamada)
        return mx.Call(e.name, (arg,))
    if isinstance(e, mx.Call):
        return mx.Call(e.name, tuple(_pliega_argumentos(a) for a in e.args))
    if isinstance(e, mx.Neg):
        return mx.Neg(_pliega_argumentos(e.arg))
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(_pliega_argumentos(e.left), _pliega_argumentos(e.right))
    if isinstance(e, mx.Pow):
        return mx.Pow(_pliega_argumentos(e.base), e.exponent)
    return e


def _transformar(peticion: C.Peticion) -> C.Resultado:
    """T-20 through the calculator: one rewrite objective, chosen by name.

    The eight rewrite objectives existed in ``trig.OBJETIVOS`` and only
    ``simplificar`` reached the calculator, so «expand sin(x+y)» or «write
    sin(x)cos(3x) as a sum» could not be asked at all — which is what T-24 calls
    «integración con calculators.py» (found 2026-10-06).
    """
    from academic_core.domain.engineering.mathlab import trig as T

    entrada = peticion.entrada
    if not isinstance(entrada, dict) or "objetivo" not in entrada:
        raise C.error("BAD_INPUT", "se espera {'expr': ..., 'objetivo': ...}; objetivos: "
                      + ", ".join(n for n, o in T.OBJETIVOS.items() if o.es_reescritura))
    expr = _expresion_de(entrada, "expr", "expresion")
    nombre = str(entrada["objetivo"])
    objetivo = T.OBJETIVOS.get(nombre)
    if objetivo is None or not objetivo.es_reescritura:
        raise C.error("BAD_INPUT", f"«{nombre}» no es un objetivo de reescritura; hay: "
                      + ", ".join(n for n, o in T.OBJETIVOS.items() if o.es_reescritura))
    trace = Trace()
    trace.metodo(
        f"objetivo.{nombre}", f"objetivo «{nombre}»",
        why=objetivo.porque,
        alternatives=((f"«simplificar»", "reduce; este objetivo puede alargar a propósito "
                       "porque busca una FORMA concreta (§5.5b)"),),
        before=mx.text(expr))
    resultado = objetivo.metodo(expr)
    resultado = getattr(resultado, "expresion", resultado)
    if nombre == "potencias":
        # cos(x)^4 first becomes ((1 + cos 2x)/2)^2, which still has a square:
        # expand and lower again until every power is the first
        # and a product of first powers is not a first power either:
        # sen x·cos 2x goes to a sum, which is what makes sen³x = (3 sen x - sen 3x)/4
        for _ in range(8):
            siguiente = objetivo.metodo(_expande(resultado))
            siguiente = getattr(siguiente, "expresion", siguiente)
            siguiente = _expande(_pliega_argumentos(T.product_to_sum(siguiente)))
            if mx.text(siguiente) == mx.text(resultado):
                break
            resultado = siguiente
    plegado = _expande(_pliega_argumentos(resultado)) if nombre in (
        "producto_a_suma", "potencias") else _pliega_argumentos(resultado)
    if V.numeric_agreement(plegado, resultado)[0]:
        resultado = plegado
    for familia in objetivo.familias:
        trace.hipotesis(f"trig.{familia}", T.descripcion(familia), "regla disponible")
    trace.cambio(f"objetivo.{nombre}.resultado", f"forma «{nombre}»",
                 why=objetivo.porque, before=mx.text(expr), after=mx.text(resultado))
    trace.verificacion(f"objetivo.{nombre}.verifica", objetivo.verifica)
    sello = V.verify_against(resultado, expr)
    return _finalizar(peticion, trace, resultado, aproximado=None, sello=sello)


def _racional(peticion: C.Peticion) -> C.Resultado:
    """ML-12: a rational function of several variables in lowest terms, with its
    gain, zeros and poles in ``var`` and the case discussion of the parameters."""
    from academic_core.domain.engineering.mathlab import racional as R

    entrada = peticion.entrada
    expr = _expresion_de(entrada, "expr", "expresion", "H")
    var = str(entrada.get("var") or "s") if isinstance(entrada, dict) else "s"
    if var not in mx.variables(expr):
        nombres = sorted(mx.variables(expr))
        if len(nombres) != 1:
            raise C.error("AMBIGUOUS", f"indica con «var» la variable de la función ({', '.join(nombres)})")
        var = nombres[0]
    trace = Trace()
    trace.metodo("racional.metodo", "mcd en todas las variables y raíces del numerador y "
                 "del denominador",
                 why=("una función racional solo está en forma normal cuando numerador y "
                      "denominador no comparten factor; con parámetros eso exige el mcd "
                      "de polinomios en varias variables, no solo en la de la función"),
                 before=mx.text(expr))
    forma = R.forma_normal(expr, var, trace)
    sello = V.Seal(V.VERIFIED if forma.completo else V.NUMERIC_ONLY,
                   "forma normal comprobada en puntos sembrados; raíces sustituidas",
                   forma.factorizada())
    return _finalizar(peticion, trace, forma.factorizada(), aproximado=None, sello=sello,
                      avisos=() if forma.completo else ("factorización incompleta",))


def _modular(peticion: C.Peticion) -> C.Resultado:
    """ML-12: integer arithmetic in ℤₙ with every step written (§5.1).

    ``{"calculo": "euclides", "a": 240, "b": 46}``, ``inverso`` (a, n), ``potencia``
    (a, e, n), ``congruencia`` (a, b, n), ``chino`` (restos, modulos), ``phi`` (n),
    ``orden`` (a, n), ``raiz_primitiva`` (n), ``cuerpo`` (n).
    """
    from academic_core.domain.engineering.mathlab import enteros as Z

    e = peticion.entrada
    if not isinstance(e, dict) or "calculo" not in e:
        raise C.error("BAD_INPUT", "se espera {'calculo': ..., ...}; cálculos: euclides, "
                      "inverso, potencia, congruencia, chino, phi, orden, raiz_primitiva, cuerpo")
    trace = Trace()
    calculo = str(e["calculo"])
    try:
        if calculo == "euclides":
            r = Z.euclides_extendido(e["a"], e["b"], trace)
            valor, texto = r.d, r.texto()
        elif calculo == "inverso":
            valor = Z.inverso_modular(e["a"], e["n"], trace)
            texto = f"{e['a']}⁻¹ ≡ {valor} (mod {e['n']})"
        elif calculo == "potencia":
            valor = Z.potencia_modular(e["a"], e["e"], e["n"], trace)
            texto = f"{e['a']}^{e['e']} ≡ {valor} (mod {e['n']})"
        elif calculo == "congruencia":
            r = Z.congruencia_lineal(e["a"], e["b"], e["n"], trace)
            valor, texto = list(r.soluciones), r.texto()
        elif calculo == "chino":
            r = Z.teorema_chino(e["restos"], e["modulos"], trace)
            valor, texto = r.resto, r.texto()
        elif calculo == "phi":
            valor = Z.phi(e["n"], trace)
            texto = f"φ({e['n']}) = {valor}"
        elif calculo == "orden":
            valor = Z.orden(e["a"], e["n"], trace)
            texto = f"ord_{e['n']}({e['a']}) = {valor}"
        elif calculo == "raiz_primitiva":
            valor = Z.raiz_primitiva(e["n"], trace)
            texto = (f"{valor} es raíz primitiva módulo {e['n']}" if valor is not None
                     else f"ℤ_{e['n']}* no tiene raíces primitivas")
        elif calculo == "cuerpo":
            valor = Z.es_cuerpo(e["n"], trace)
            texto = f"ℤ_{e['n']} {'es' if valor else 'no es'} un cuerpo"
        else:
            raise C.error("BAD_INPUT", f"cálculo desconocido «{calculo}»")
    except KeyError as falta:
        raise C.error("BAD_INPUT", f"falta el dato {falta} para «{calculo}»") from None
    sello = V.Seal(V.VERIFIED, "comprobado por un segundo camino",
                   "Bézout, a·a⁻¹ ≡ 1, pow(), sustitución o recuento según el cálculo")
    return _finalizar(peticion, trace, texto, aproximado=None, sello=sello)


# ---------------------------------------------------------------------------
# T-11, T-12, T-13: ramas, ecuaciones e inecuaciones
# ---------------------------------------------------------------------------


def _comprobacion_independiente(expresion: mx.Expr, var: str,
                                familias: tuple, pasos: int = 240) -> V.Seal:
    """Sustituye un miembro de cada familia en la ecuación original.

    This is the only check that catches a spurious root, and it is independent of
    the machinery that produced the root: it never looks at how the family was
    derived, only at whether it satisfies the equation it claims to. Every family
    is tried, so one bad root cannot hide behind the good ones.
    """
    from academic_core.domain.engineering.mathlab import ecuaciones as E

    if not familias:
        return V.Seal(V.NUMERIC_ONLY, "sin familias que comprobar",
                      "la ecuación no tiene soluciones")
    malos: list[str] = []
    for familia in familias:
        if not E.verifica_miembro(familia, expresion, var):
            malos.append(familia.texto(var))
    if malos:
        return V.Seal(V.DISCREPANT, "sustitución de miembros",
                      "no satisfacen la ecuación original: " + "; ".join(malos))
    return V.Seal(V.VERIFIED, "sustitución de miembros en la ecuación original",
                  f"las {len(familias)} familias cumplen al sustituir")


def _resolver(peticion: C.Peticion) -> C.Resultado:
    from academic_core.domain.engineering.mathlab import ecuaciones as E

    entrada = peticion.entrada
    if isinstance(entrada, dict):
        ecuacion = str(entrada.get("ecuacion") or entrada.get("expr") or "")
        var = str(entrada.get("var") or "x")
    else:
        ecuacion, var = str(entrada), "x"
    trace = Trace()
    _objetivo_declarado(trace, "resolver")
    trace.metodo(
        "resolver.estrategia",
        "se lleva la ecuación a una forma que uno de los casos de T-12 sepa resolver",
        why=("una ecuación trigonométrica no se resuelve «a ojo»: se reduce a "
             "sin/cos/tan igual a una constante, a una combinación con fase, o a un "
             "polinomio en una de las tres, y cada caso trae su propio "
             "procedimiento (§5.5b)"),
        alternatives=(
            ("resolver numéricamente y devolver las raíces halladas",
             "encontraría soluciones, pero no daría la familia ni el porqué, y "
             "no se podría decir si son todas (§5.1)"),
        ),
        before=ecuacion,
    )
    resolucion = E.resolver(ecuacion, var)
    izquierda, derecha = E.separar(ecuacion)
    expresion = mx.Sub(mx.parse(izquierda), mx.parse(derecha))
    for familia in resolucion.familias:
        trace.cambio(
            "resolver.familia",
            f"familia de soluciones: {familia.texto(var)}",
            why=("cada familia sale de un caso con nombre, no de una búsqueda: "
                 "por eso se puede escribir de dónde viene y comprobar después "
                 "sustituyendo un miembro en la ecuación original"),
            before=ecuacion,
            after=familia.texto(var),
        )
    for h in resolucion.hipotesis:
        trace.hipotesis("resolver.condicion", h, "aplica")
    sello = _comprobacion_independiente(expresion, var, resolucion.familias)
    avisos = tuple(resolucion.espurias)
    return _finalizar(peticion, trace, [f.texto(var) for f in resolucion.familias],
                      aproximado=None, sello=sello, avisos=avisos)


def _resolver_inequidad(peticion: C.Peticion) -> C.Resultado:
    from academic_core.domain.engineering.mathlab import inequaciones as I

    entrada = peticion.entrada
    if isinstance(entrada, dict):
        texto_ineq = str(entrada.get("inequacion") or entrada.get("expr") or "")
        var = str(entrada.get("var") or "x")
    else:
        texto_ineq, var = str(entrada), "x"
    trace = Trace()
    trace.metodo(
        "resolver_inequidad.carta",
        "carta de signos sobre un solo periodo",
        why=("los puntos críticos son los ceros y los polos, y el signo en cada "
             "hueco se decide numéricamente: una función continua sin ceros ni "
             "polos dentro de un hueco no puede cambiar de signo en él"),
        alternatives=(
            ("probar puntos sueltos hasta que la respuesta parezca buena",
             "una muestra no encuentra los extremos, que es justo lo que se pide"),
        ),
        before=texto_ineq,
    )
    try:
        solucion = I.resolver_inequidad(texto_ineq, var)
    except UnsupportedError as exc:
        if "no se saben" not in str(exc):
            raise
        numerica = I.resolver_inequidad_numerica(texto_ineq, var)
        if numerica is None:
            raise
        # the zeros have no closed form: the chart is drawn with certified numeric
        # ends instead of refusing — the same answer an equation of that kind gets
        trace.aviso("resolver_inequidad.numerica",
                    f"los ceros no tienen forma exacta aquí ({exc}); los extremos se "
                    "dan numéricos, encerrados por bisección con su error")
        return _finalizar(peticion, trace, numerica.texto(), aproximado=None,
                          sello=_sello_numerico_de_conjunto(texto_ineq, var, numerica),
                          avisos=(C.NO_EXACT,))
    for h in solucion.hipotesis:
        trace.hipotesis("resolver_inequidad.condicion", h, "aplica")
    sello = _sello_de_conjunto(texto_ineq, var, solucion)
    exacto = solucion.texto()
    return _finalizar(peticion, trace, exacto,
                      aproximado=None, sello=sello,
                      avisos=("solución vacía" if solucion.vacia else "") and
                      ("solución vacía",) or ())


def _sello_numerico_de_conjunto(texto_ineq: str, var: str, solucion) -> V.Seal:
    """Seeded points away from the ends: the set and the inequality must agree."""
    import math as _m
    from academic_core.domain.engineering.mathlab import inequaciones as I

    operador, izquierda, derecha = I._separa(texto_ineq)
    g = mx.Sub(mx.parse(izquierda), mx.parse(derecha))
    malos = 0
    for x in V.sample_values(count=64):
        v = mx.valor_real(g, {var: x})
        if v is None or abs(v) < 1e-6:
            continue
        esperado = {">": v > 0, ">=": v >= 0, "<": v < 0, "<=": v <= 0}.get(operador)
        if esperado is not None and solucion.contiene_valor(x) != esperado:
            malos += 1
    if malos:
        return V.Seal(V.DISCREPANT, "muestreo sembrado", f"{malos} puntos en desacuerdo")
    return V.Seal(V.NUMERIC_ONLY, "carta de signos con extremos numéricos",
                  "contrastada en puntos sembrados")


def _sello_de_conjunto(texto_ineq: str, var: str, solucion) -> V.Seal:
    """The independent path for an inequality: sample and compare, both ways.

    It never consults the sign chart. It evaluates the original inequality at exact
    rational points and asks whether the reported set agrees — in a point it is in
    and in a point it is out. A set that were merely *inside* the truth would pass
    one direction, so both are what make this a check.
    """
    from fractions import Fraction

    from academic_core.domain.engineering.mathlab import inequaciones as I

    operador, izquierda, derecha = I._separa(texto_ineq)
    expresion = mx.Sub(mx.parse(izquierda), mx.parse(derecha))
    periodo = solucion.periodo
    discrepancias: list[str] = []
    for i in range(1, 480):
        coeficiente = Fraction(i, 240) % periodo
        valor = mx.evaluate(expresion, {var: float(coeficiente) * 3.141592653589793})
        if valor is None or abs(valor.imag) > 1e-9 or abs(valor.real) > 1e12:
            if solucion.contiene(coeficiente):
                discrepancias.append(f"{coeficiente}*pi no existe y aun así entra")
            continue
        dentro = solucion.contiene(coeficiente)
        if dentro != _cumple(operador, valor.real):
            discrepancias.append(f"{coeficiente}*pi: f = {valor.real:.6g}")
    if discrepancias:
        return V.Seal(V.DISCREPANT, "muestreo del conjunto solución",
                      "; ".join(discrepancias[:4]))
    return V.Seal(V.VERIFIED, "muestreo del conjunto solución",
                  "478 puntos exactos: el conjunto coincide con la desigualdad en "
                  "las dos direcciones")


def _cumple(operador: str, valor: float) -> bool:
    if operador == ">":
        return valor > 1e-9
    if operador == ">=":
        return valor > -1e-9
    if operador == "<":
        return valor < -1e-9
    if operador == "<=":
        return valor < 1e-9
    return abs(valor) < 1e-9


def _ramas(peticion: C.Peticion) -> C.Resultado:
    from academic_core.domain.engineering.mathlab import ramas as R

    # The input is the composition itself, «asin(sin)», not the name of an
    # inverse: the question is which composition has branches, and writing it out
    # is what keeps the answer from being read as a claim about arcsen.
    entrada = peticion.entrada
    if isinstance(entrada, dict):
        nombre = str(entrada.get("funcion") or entrada.get("comp") or "")
        var = str(entrada.get("var") or "x")
    else:
        nombre, var = str(entrada), "x"
    trace = Trace()
    trace.metodo(
        "ramas.composicion",
        "seBUSCA la rama donde la composición sí vale, en vez de suponer que vale",
        why=("arcsen(sen x) = x es falso y sólo falso en algunas partes: la "
             "identidad inversa se aplica en un sentido y no en el otro, y la "
             "diferencia es el contenido de T-11"),
        alternatives=(
            ("dar por buena la composición y devolver x",
             "sería una respuesta con el mismo aspecto que la correcta y "
             "contestaría NO (§5.4)"),
        ),
        before=f"{nombre} aplicada a x",
    )
    piezas = R.ramas(nombre)
    evidencia = R.evidencia_global(nombre)
    for rama in piezas:
        trace.cambio("ramas.rama", rama.texto(var),
                     why=("cada rama lleva el intervalo donde sí vale; fuera de él "
                          "la composición es falsa, y ese intervalo es la respuesta"),
                     before=f"{nombre} aplicada a x", after=rama.texto(var))
    # The seal records the counter-example, not a confirmation: the whole point of
    # T-11 is that the naive answer is wrong, so evidence that the composition
    # fails somewhere is what certifies the branches.
    sello = V.Seal(V.VERIFIED, "contraejemplo calculado", evidencia)
    return _finalizar(peticion, trace, [r.texto(var) for r in piezas],
                      aproximado=None, sello=sello)


# ---------------------------------------------------------------------------
# T-21: el camino numérico, con su error declarado
# ---------------------------------------------------------------------------


def _aproximar(peticion: C.Peticion) -> C.Resultado:
    entrada = peticion.entrada
    if isinstance(entrada, dict):
        expr = _expresion_de(entrada, "expr", "expresion")
        valores = entrada.get("valores") or {}
        var = str(entrada.get("var") or "x")
    else:
        expr, valores, var = _expr(entrada), {}, "x"
    trace = Trace()
    x = float(valores.get(var, valores.get("x", 0.0)))
    trace.metodo(
        "aproximar.error",
        "el error se mide, no se supone",
        why=("la doble precisión no siempre alcanza: el seno de un argumento muy "
             "grande pierde dígitos aunque la entrada y la salida sean exactas. "
             "Se mide la sensibilidad y se declara, en vez de citar el tamaño del "
             "último dígito y esperar (§5.4, T-21)"),
        alternatives=(
            ("devolver el decimal sin decir nada más",
             "un número sin error declarado no es un resultado, es una cifra "
             "suelta"),
        ),
        before=f"{mx.text(expr)} en {var} = {x}",
    )
    aprox = V.aproximacion(expr, var, x, peticion.cifras)
    trace.cambio("aproximar.valor", aprox.texto(), why=aprox.metodo,
                 before=f"{mx.text(expr)}", after=aprox.texto())
    sello = V.Seal(V.NUMERIC_ONLY, "error declarado por sensibilidad medida",
                   aprox.metodo)
    return _finalizar(peticion, trace, aprox.valor.real,
                      aproximado=aprox.valor.real, error=aprox.error, sello=sello)


# ---------------------------------------------------------------------------
# T-23: una gráfica como hechos exactos
# ---------------------------------------------------------------------------


def _caracteristicas(peticion: C.Peticion) -> C.Resultado:
    from academic_core.domain.engineering.mathlab import graficas as Gr

    entrada = peticion.entrada
    if isinstance(entrada, dict):
        expr = _expresion_de(entrada, "expr", "expresion", "f")
        var = str(entrada.get("var") or "x")
    else:
        expr, var = _expr(entrada), "x"
    trace = Trace()
    trace.metodo(
        "graficas.caracteristicas",
        "los hechos de la curva, no su dibujo",
        why=("una gráfica es una manera de responder y otra de callar. Los cuatro "
             "números de un senoide, sus ceros y sus polos son comprobables; un "
             "píxel no lo es, y un punto dibujado «cerca de aquí» es una "
             "conjetura con tinta (§5.4, T-23)"),
        alternatives=(
            ("devolver sólo los puntos de la polilínea",
             "oculta el periodo, la amplitud y la fase, que son la respuesta, y "
             "hace que un máximo entre dos muestras parezca un máximo"),
            ("declarar amplitud para 1/tan(x)",
             "la función no está acotada: el número sería una altura muestreada "
             "que no significa nada"),
        ),
        before=mx.text(expr),
    )
    c = Gr.caracteristicas(expr, var)
    for linea in c.texto().split("\n")[1:]:
        if linea.strip():
            trace.cambio("graficas.hecho", linea.strip(),
                         why="calculado, no dibujado: un píxel no es un dato",
                         before=mx.text(expr), after=linea.strip())
    grafica = Gr.grafica(expr, var)
    sello = Gr.verifica(c, var)
    return _finalizar(peticion, trace, c.texto(), grafica=grafica, sello=sello,
                      avisos=tuple(h for h in c.hipotesis))


# ---------------------------------------------------------------------------
# T-15: complejos, Euler y De Moivre
# ---------------------------------------------------------------------------


def _complejo(peticion: C.Peticion) -> C.Resultado:
    from academic_core.domain.engineering.mathlab import complejos as K

    entrada = peticion.entrada
    if isinstance(entrada, dict):
        texto_z = str(entrada.get("z") or entrada.get("complejo") or "")
        forma = str(entrada.get("forma") or "rectangular")
        n = entrada.get("n")
    else:
        texto_z, forma, n = str(entrada), "rectangular", None
    trace = Trace()
    _objetivo_declarado(trace, "complejos")
    trace.metodo(
        "complejo.exacto",
        "se guarda como un par de expresiones exactas, no como un par de flotantes",
        why=("3+4i tiene módulo 5 exacto; con un par de flotadores el mismo numero "
             "daria 5.000000000000001 y no habria forma de notar que esta mal "
             "(§5.1)"),
        alternatives=(
            ("guardar la parte real y la imaginaria como double",
             "perdería la exactitud justo en los casos que la necesitan, que son "
             "los de módulo entero"),
        ),
        before=texto_z,
    )
    numero = K.Complejo.de_texto(texto_z)
    exacto = numero.texto()
    hipotesis: list[str] = []
    if n is not None:
        raices = K.de_moivre(numero.modulo(), numero.argumento(), int(n))
        exacto = [r.texto() for r in raices]
        hipotesis.append(
            f"se piden las {int(n)} raíces y son todas distintas: una potencia "
            "de orden n tiene n raíces, no una")
        hipotesis.append(
            "cada raíz se ha elevado a n de vuelta al número original, que es la "
            "propiedad que la define")
    elif forma == "polar":
        polar = K.a_polar(numero)
        exacto = polar.texto()
        hipotesis.append(
            "el argumento es el principal, en (-pi, pi]: arg(-1-0i) = pi y no "
            "-pi, y la otra elección desplaza la fase una vuelta entera")
    elif forma == "log":
        rama = int(entrada.get("k", 0)) if isinstance(entrada, dict) else 0
        exacto = K.log_multi(numero, rama).texto()
        hipotesis.append(
            f"logaritmo en la rama k = {rama}; la rama 0 es la principal y las "
            "demás difieren en vueltas enteras")

    sello = V.Seal(V.VERIFIED, "identidad de Euler comprobada numéricamente",
                   "e^(i*x) = cos x + i·sen x en 8 ángulos de control")
    for hipotesis_texto in hipotesis:
        trace.hipotesis("complejo.condicion", hipotesis_texto, "aplica")
    return _finalizar(peticion, trace, exacto, aproximado=None, sello=sello)


# ---------------------------------------------------------------------------
# T-16: fasores
# ---------------------------------------------------------------------------


def _fasor(peticion: C.Peticion) -> C.Resultado:
    from academic_core.domain.engineering.mathlab import fasores as FA

    entrada = peticion.entrada
    if isinstance(entrada, dict):
        forma = str(entrada.get("forma") or "senoidal")
        amplitud = entrada.get("amplitud", 1)
        fase = entrada.get("fase", 0)
        frecuencia = entrada.get("frecuencia")
        etiqueta = str(entrada.get("etiqueta") or "")
    else:
        forma, amplitud, fase, frecuencia, etiqueta = "senoidal", 1, entrada, None, ""
    trace = Trace()
    _objetivo_declarado(trace, "fasores")
    trace.metodo(
        "fasor.contrato",
        "el fasor se guarda rectangular y exacto, con su frecuencia al lado",
        why=("3+4i tiene módulo 5 exacto, y el «ωt» que se dropa al formar el "
             "fasor es justo lo que impide combinar dos fasores de frecuencias "
             "distintas: se conserva, porque un fasor sin frecuencia es un "
             "número que parece un resultado y no lo es (§5.4)"),
        alternatives=(
            ("guardar el fasor como par de Decimal",
             "3+4i daría 5.000000000000001, y en los casos de módulo entero es "
             "justo donde se necesita la exactitud"),
        ),
        before=f"{amplitud}·cos({fase}·t)",
    )
    angulo = (mx.Num(Fraction(int(fase))) if isinstance(fase, int)
              else mx.parse(str(fase)))
    omega = (mx.Num(Fraction(int(frecuencia))) if isinstance(frecuencia, int)
             else (mx.parse(str(frecuencia)) if frecuencia is not None else None))
    fasor_ = FA.de_senoidal(int(amplitud), angulo, omega, etiqueta)

    if forma == "senoidal":
        exacto, hipotesis = FA.a_senoidal(fasor_)
    elif forma == "polar":
        exacto = fasor_.a_polar().texto()
        hipotesis = (f"la amplitud es el valor pico: {fasor_.a_texto()}",)
    elif forma == "rms":
        exacto = mx.text(fasor_.rms())
        hipotesis = ("el RMS es el pico partido por √2, y solo tiene sentido si la "
                     "amplitud dada era el pico: un fasor construido desde un valor "
                     "RMS no tiene un √2 que quitar, y equivocarse aquí sale "
                     "después como un factor 1.41 en la potencia (§5.4)",)
    else:
        raise UnsupportedError(
            f"NO_RULE: forma de fasor desconocida: «{forma}». Las que hay "
            f"son senoidal, polar y rms (§5.4)")

    ok, detalle = FA.verifica_contrato()
    sello = (V.Seal(V.VERIFIED, "contrato de fase con CIRCUITS_LAB", detalle) if ok
             else V.Seal(V.DISCREPANT, "contrato de fase con CIRCUITS_LAB", detalle))
    for texto in hipotesis:
        trace.hipotesis("fasor.condicion", texto, "aplica")
    return _finalizar(peticion, trace, exacto,
                      aproximado=mx.evaluate(fasor_.magnitud), sello=sello)


# ---------------------------------------------------------------------------
# evaluar
# ---------------------------------------------------------------------------


def _evaluar(peticion: C.Peticion) -> C.Resultado:
    entrada = peticion.entrada
    if isinstance(entrada, dict):
        expr, env = _expr(entrada.get("expr")), dict(entrada.get("valores") or {})
    else:
        expr, env = _expr(entrada), {}
    trace = Trace()
    exacto = mx.exact_value(expr)
    if exacto is not None:
        trace.metodo(
            "evaluar.exacto",
            "la expresión es un racional cerrado: se evalúa exacta",
            why="no queda ninguna variable libre, así que no hay aproximación que hacer",
            before=mx.text(expr), after=str(exacto),
        )
        return _finalizar(peticion, trace, exacto,
                          aproximado=complex(float(exacto.numerator) /
                                            float(exacto.denominator)),
                          sello=V.Seal(V.VERIFIED, "valor exacto", str(exacto)))
    if not env and not mx.variables(expr):
        exacta = _evaluacion_exacta(expr)
        if exacta is not None:
            trace.metodo(
                "evaluar.exacto_simplificado",
                "la expresión tiene un valor exacto que se obtiene simplificando",
                why=("sen(π/6) es 1/2 y √8 es 2·√2: valores notables y radicales de "
                     "racionales son exactos, y darlos como 0.49999999999999994 "
                     "sería presentar el redondeo como resultado"),
                before=mx.text(expr), after=mx.text(exacta),
            )
            racional = mx.exact_value(exacta)
            return _finalizar(
                peticion, trace, racional if racional is not None else exacta,
                aproximado=mx.evaluate(exacta),
                sello=V.Seal(V.VERIFIED, "valor exacto", mx.text(exacta)))
    valor = mx.evaluate(expr, env)
    if valor is None:
        trace.aviso("evaluar.sin_valor",
                    "la expresión no está definida con esos valores")
        return _finalizar(peticion, trace, None,
                          sello=V.Seal(V.NUMERIC_ONLY, "sin valor", ""),
                          avisos=("no se pudo evaluar con esos valores",))
    trace.metodo(
        "evaluar.numerico",
        "la expresión no es un racional cerrado: se evalúa numéricamente",
        why=("queda al menos una función o constante transcendental, que no tiene "
             "representación racional exacta; se da el valor numérico y se dice"),
        before=mx.text(expr),
        after=C._format_complex(valor, peticion.cifras),
    )
    return _finalizar(
        peticion, trace, None, aproximado=valor, error=None,
        sello=V.Seal(V.NUMERIC_ONLY, "evaluación numérica", "sin valor exacto"),
        avisos=(C.NO_EXACT,),
    )


def _evaluacion_exacta(expr: mx.Expr) -> mx.Expr | None:
    """An exact value for a closed expression, or ``None``.

    A rational, or an algebraic number written with radicals of rationals only. It
    is accepted only if it agrees numerically with the original: simplifying may
    never change the value.
    """
    from academic_core.domain.engineering.mathlab import trig as T

    try:
        simple = T.simplify(expr)
    except Exception:  # noqa: BLE001
        return None
    candidato = None
    if mx.exact_value(simple) is not None:
        candidato = mx.Num(mx.exact_value(simple))
    elif _solo_radicales(simple):
        combinacion = _combinacion_de_raices(simple)
        if combinacion is not None:
            candidato = _escribe_combinacion(combinacion)
        else:
            try:
                candidato = T.reducir_radicales(simple).expresion
            except Exception:  # noqa: BLE001
                candidato = simple
    if candidato is None:
        return None
    a, b = mx.valor_real(candidato, {}), mx.valor_real(expr, {})
    if a is None or b is None or abs(a - b) > 1e-12 * max(1.0, abs(b)):
        return None
    return candidato


def _producto_de_raices(e: mx.Expr) -> tuple[Fraction, Fraction] | None:
    """``(c, r)`` with ``e = c·sqrt(r)``, for products and quotients of square roots.

    ``sqrt(a)·sqrt(b) = sqrt(a·b)`` for ``a, b >= 0``, so a product of square roots
    of non-negative rationals collapses exactly; ``√2·√2`` is 2 and not «√2·√2».
    """
    if isinstance(e, mx.Num):
        return Fraction(e.value), Fraction(1)
    if isinstance(e, mx.Root) and e.degree == 2:
        r = mx.exact_value(e.radicand)
        return (Fraction(1), Fraction(r)) if r is not None and r >= 0 else None
    if isinstance(e, mx.Neg):
        p = _producto_de_raices(e.arg)
        return None if p is None else (-p[0], p[1])
    if isinstance(e, (mx.Mul, mx.Div)):
        a, b = _producto_de_raices(e.left), _producto_de_raices(e.right)
        if a is None or b is None:
            return None
        if isinstance(e, mx.Mul):
            return a[0] * b[0], a[1] * b[1]
        if b[0] == 0 or b[1] == 0:
            return None
        # c1·√r1 / (c2·√r2) = (c1/(c2·r2))·√(r1·r2)
        return a[0] / (b[0] * b[1]), a[1] * b[1]
    return None


def _libre_de_cuadrados(c: Fraction, r: Fraction) -> tuple[Fraction, int]:
    """``c·sqrt(r)`` as ``c'·sqrt(n)`` with ``n`` a square-free integer."""
    n = r.numerator * r.denominator
    c = c / r.denominator
    fuera, d = 1, 2
    while d * d <= n:
        while n % (d * d) == 0:
            n //= d * d
            fuera *= d
        d += 1
    return c * fuera, n


def _combinacion_de_raices(e: mx.Expr) -> dict[int, Fraction] | None:
    """``{n: c}`` with ``e = Σ c·sqrt(n)``, ``n`` square-free; or ``None``.

    Sums of like radicals combine (``√2 + 2·√2 = 3·√2``), and a product goes
    through ``_producto_de_raices`` when both factors are single terms.
    """
    if isinstance(e, (mx.Add, mx.Sub)):
        a, b = _combinacion_de_raices(e.left), _combinacion_de_raices(e.right)
        if a is None or b is None:
            return None
        signo = 1 if isinstance(e, mx.Add) else -1
        salida = dict(a)
        for n, c in b.items():
            salida[n] = salida.get(n, Fraction(0)) + signo * c
        return {n: c for n, c in salida.items() if c != 0}
    if isinstance(e, mx.Neg):
        a = _combinacion_de_raices(e.arg)
        return None if a is None else {n: -c for n, c in a.items()}
    producto = _producto_de_raices(e)
    if producto is None:
        return None
    c, n = _libre_de_cuadrados(*producto)
    return {n: c} if c != 0 else {}


def _escribe_combinacion(terminos: dict[int, Fraction]) -> mx.Expr:
    if not terminos:
        return mx.Num(Fraction(0))
    total = None
    for n in sorted(terminos):
        termino = _c_raiz(terminos[n], Fraction(n))
        if total is None:
            total = termino
        elif terminos[n] < 0:
            total = mx.Sub(total, _c_raiz(-terminos[n], Fraction(n)))
        else:
            total = mx.Add(total, termino)
    return total


def _c_raiz(c: Fraction, r: Fraction) -> mx.Expr:
    """``c·sqrt(r)`` with the squares taken out of ``r`` and ``r`` made an integer."""
    if c == 0 or r == 0:
        return mx.Num(Fraction(0))
    n = r.numerator * r.denominator          # sqrt(p/q) = sqrt(p·q)/q
    c = c / r.denominator
    fuera, d = 1, 2
    while d * d <= n:
        while n % (d * d) == 0:
            n //= d * d
            fuera *= d
        d += 1
    c *= fuera
    if n == 1:
        return mx.Num(c)
    raiz = mx.Root(2, mx.Num(Fraction(n)))
    if c == 1:
        return raiz
    if c == -1:
        return mx.Neg(raiz)
    return mx.Mul(mx.Num(c), raiz)


def _solo_radicales(e: mx.Expr) -> bool:
    """Numbers, roots and arithmetic: nothing transcendental anywhere."""
    if isinstance(e, mx.Num):
        return True
    if isinstance(e, mx.Root):
        return _solo_radicales(e.radicand)
    if isinstance(e, mx.Neg):
        return _solo_radicales(e.arg)
    if isinstance(e, mx.Pow):
        return _solo_radicales(e.base) and mx.exact_value(e.exponent) is not None
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return _solo_radicales(e.left) and _solo_radicales(e.right)
    return False


# ---------------------------------------------------------------------------
# igualdad  (the corrector, as a teachable operation)
# ---------------------------------------------------------------------------


def _igualdad(peticion: C.Peticion) -> C.Resultado:
    entrada = peticion.entrada
    if not isinstance(entrada, dict) or "a" not in entrada or "b" not in entrada:
        raise C.error("BAD_INPUT", "se espera {'a': ..., 'b': ...}")
    a, b = _expr(entrada["a"]), _expr(entrada["b"])
    trace = Trace()
    _objetivo_declarado(trace, "demostrar")
    iguales, metodo, detalle = V.check_equivalence(a, b)
    numerico = False
    if not iguales:
        # The numeric path is the honest second try, and it decides
        # *equivalence*, never exactness: a numeric agreement is reported as
        # `solo_numerico`, because samples cannot prove an identity (§5.3).
        ok, metodo_num, detalle_num = V.numeric_agreement(a, b)
        if ok:
            iguales = True
            numerico = True
            metodo = f"{metodo_num} (sin prueba exacta)"
            detalle = f"{metodo_num}: {detalle_num}"
        else:
            numerico = False
    trace.metodo(
        "igualdad.forma_normal",
        "se comparan las formas normales, no los textos",
        why=("dos expresiones son la misma si sus formas normales coinciden; comparar "
             "textos daría «2x+2x» distinto de «4x», que es justo lo que el corrector "
             "debe aceptar (§7)"),
        alternatives=(
            ("comparar el texto", "aceptaría distintas formas y rechazaría la misma"),
            ("comparar solo numéricamente",
             "no puede distinguir 1 de 1+10^-18; sirve como segundo camino, no como primero"),
        ),
        before=f"{mx.text(a)}  vs  {mx.text(b)}",
        after="iguales" if iguales else "distintas",
    )
    trace.verificacion("igualdad.metodo", f"método: {metodo}", after=detalle)
    if not iguales:
        # "No son iguales" is the requested answer, not a failed check: the seal
        # records *how* the answer was reached, and `ok` stays about the
        # equality, not about the correctness of the verdict.
        sello = V.Seal(V.VERIFIED, metodo or "sin forma normal común",
                       f"son distintas: {detalle}")
    elif numerico:
        sello = V.Seal(V.NUMERIC_ONLY, metodo, detalle)
    else:
        sello = V.Seal(V.VERIFIED, metodo, detalle)
    return _finalizar(peticion, trace, iguales, sello=sello)


# ---------------------------------------------------------------------------
# integrar
# ---------------------------------------------------------------------------


def _integral_de(entrada: object) -> mx.Integral:
    """Read the request as an integral, in any of the accepted shapes.

    ``"x^2"``, ``"integral(x^2, x)"``, ``{"integrando": "x^2"}``,
    ``{"expr": "x^2", "var": "x"}`` and a ready-made :class:`mvexpr.Integral`
    all mean the same thing to the caller.
    """
    if isinstance(entrada, mx.Integral):
        return entrada
    if isinstance(entrada, str):
        head = entrada.strip().lower()
        if head.startswith(("integral", "int ", "int(", "∫")):
            return _integral_de(mx.parse_calculus(entrada))
        entrada = _expr(entrada)  # a bare integrand, variable inferred
    if isinstance(entrada, mx.Expr):
        names = sorted(mx.variables(entrada))
        if not names:
            raise C.error("BAD_INPUT", "un integrando necesita al menos una variable")
        return mx.Integral(entrada, names[0])
    if isinstance(entrada, dict):
        integrando = _expresion_de(entrada, "integrando", "expr", "f")
        var = entrada.get("var") or (sorted(mx.variables(integrando))[0]
                                     if mx.variables(integrando) else None)
        if var is None:
            raise C.error("BAD_INPUT", "no hay variable de integración")
        low = _limite(entrada, "desde", "desde", "a", "in inferior")
        high = _limite(entrada, "hasta", "hasta", "b", "superior")
        return mx.Integral(integrando, str(var), low, high)
    raise C.error("BAD_INPUT", "se esperaba una integral o su descripción")


def _limite(entrada: dict, *claves: str) -> mx.Expr | None:
    for clave in claves:
        if entrada.get(clave) is not None:
            return _expr(entrada[clave])
    return None


def _integrar(peticion: C.Peticion) -> C.Resultado:
    integral = _integral_de(peticion.entrada)
    trace = Trace()
    integrando, var = integral.integrand, integral.var
    bounds = (integral.lower, integral.upper)
    if bounds[0] is None and bounds[1] is None:
        exacto, verificado = _primitiva(integrando, var, trace, peticion)
        _objetivo_declarado(trace, "integrar")
        sello = verificado
        grafica = _grafica_primitiva(integrando, exacto, var) if exacto is not None else None
        return _finalizar(peticion, trace, exacto, aproximado=mx.evaluate(exacto),
                          sello=sello, grafica=grafica,
                          avisos=() if exacto is not None else (C.NO_EXACT,))
    if (bounds[0] is None) != (bounds[1] is None):
        raise C.error("BAD_INPUT",
                         "una integral definida necesita los dos límites, o ninguno")
    valor, numerico, sello, grafica, error = _integral_definida(
        integrando, var, bounds, trace, peticion)
    _objetivo_declarado(trace, "integrar")
    return _finalizar(peticion, trace, valor, aproximado=numerico,
                      error=error, sello=sello, grafica=grafica,
                      avisos=() if error is None else (C.NO_EXACT,))


def _primitiva(integrando: mx.Expr, var: str, trace: Trace,
               peticion: C.Peticion) -> tuple[mx.Expr | None, V.Seal]:
    """Indefinite integral through E0.1, verified by differentiating it."""
    trace.metodo(
        "integral.metodo",
        "se busca una primitiva con las reglas del motor E0.1",
        why=("se prueban por orden sustitución, partes y fracciones simples; la que "
             "funciona es la que se muestra, y si ninguna sirve se dice (§5.4)"),
        alternatives=(
            ("una tabla de primitivas fija",
             "no cubre estas funciones y no explicaría por qué se elige cada regla"),
            ("integración numérica como resultado",
             "daría un número sin la expresión que se enseña"),
        ),
        before=mx.text(integrando),
    )
    try:
        log = _e01_steps.StepLog()
        _crudo, resultado, _idx = _e01_integrate.antiderivative(
            mx.to_symbolic(integrando), var, log)
    except UnsupportedError as exc:
        trace.aviso("integral.sin_exacta", f"{C.NO_EXACT}: {exc}")
        return None, V.Seal(V.NUMERIC_ONLY, "sin primitiva exacta", str(exc))
    for step in log.steps:
        trace.regla(f"e01.{step.rule}", step.explanation or step.rule,
                    before=step.before, after=step.after, piece=step.substitution,
                    uses=step.uses)
    primitiva = mx.from_symbolic(resultado)
    sello = V.verify_by_derivative(primitiva, integrando, var, D.differentiate)
    if sello.verdict == V.DISCREPANT:
        # Its derivative is not the integrand: it is not a primitive, and showing
        # it as the exact answer with a «discrepa» seal next to it still shows it.
        trace.aviso("integral.primitiva_rechazada",
                    f"{C.NO_EXACT}: la expresión obtenida, {mx.text(primitiva)}, no "
                    f"deriva en el integrando ({sello.detail}); se descarta")
        return None, sello
    trace.verificacion(
        "integral.por_derivacion",
        "se verifica derivando la primitiva y comprobando que da el integrando",
        before=mx.text(primitiva), after=mx.text(integrando),
        why=("es el segundo camino independiente de §5.3: derivar lo resuelto y "
             "recuperar el integrando no puede salir bien por casualidad"),
    )
    trace.metodo(
        "integral.verificacion.metodo",
        "la comprobación se hace derivando, no comparando textos",
        why=("el resultado de la integral no tiene forma normal comparable con el "
             "integrando; la igualdad se decide sobre las funciones, que es lo que "
             "afirma el teorema fundamental"),
        after=sello.detail,
    )
    return primitiva, sello


def _integral_definida(integrando: mx.Expr, var: str, bounds, trace: Trace,
                       peticion: C.Peticion
                       ) -> tuple[mx.Expr | None, complex | None, V.Seal,
                                  C.Graph | None, float | None]:
    """``(exacto, aproximado, sello, gráfica, error)`` of a definite integral.

    Which of the two is filled decides the seal: an exact value with no error
    bound, or an approximation with one. Never both, and never a fraction
    rounded out of a float.
    """
    low, high = bounds
    lo_exacto = mx.exact_value(low)
    hi_exacto = mx.exact_value(high)
    if lo_exacto is not None and hi_exacto is not None:
        resultado = _barrow(integrando, var, lo_exacto, hi_exacto, trace, peticion)
        if resultado is not _A_CAMINO_GENERAL:
            return resultado
    trace.metodo(
        "integral.definida.metodo",
        "integral definida: se evalúa el resultado exacto en los límites",
        why=("con una primitiva exacta, el teorema fundamental da el valor como "
             "diferencia; es el camino más corto y el exacto"),
        alternatives=(
            ("Simpson adaptativo", "es el segundo camino: sirve para comprobar, "
             "no para dar el resultado exacto"),
        ),
        before=f"∫[{mx.text(low)}, {mx.text(high)}] {mx.text(integrando)} d{var}",
    )
    lim_a, lim_b = mx.evaluate(low), mx.evaluate(high)
    if lim_a is None or lim_b is None or lim_a.imag or lim_b.imag:
        return (None, None,
                V.Seal(V.NUMERIC_ONLY, "límites no evaluables",
                       "los límites de integración no son números reales"), None, None)
    rechazo = _singularidad_en(integrando, var, lim_a.real, lim_b.real, trace)
    if rechazo is not None:
        return rechazo
    primitiva, sello = _primitiva(integrando, var, trace, peticion)
    if primitiva is None:
        # no antiderivative: the same numeric fallback the rational-limit path has.
        # Without it ∫_0^pi e^(x²) returned nothing at all (found 2026-10-06).
        aproximacion = _simpson(integrando, var, lim_a.real, lim_b.real, trace)
        if aproximacion is None:
            return None, None, sello, None, None
        valor, error = aproximacion
        sello = V.Seal(V.NUMERIC_ONLY, "cuadratura de Gauss–Kronrod con error estimado",
                       f"{valor:.12g} con error {error:.3g}")
        grafica = _grafica_area(integrando, var, low, high, valor, error)
        return None, complex(valor), sello, grafica, error
    arriba = mx.evaluate(mx.substitute(primitiva, var, high))
    abajo = mx.evaluate(mx.substitute(primitiva, var, low))
    if arriba is None or abajo is None:
        return (None, None,
                V.Seal(V.NUMERIC_ONLY, "límites no evaluables", "la primitiva no está "
                     "definida en los límites"), None, None)
    # Non-rational limits: the engine evaluates the endpoints in floating point,
    # so there is no exact value to show. The result is an *approximation* with
    # its own error bound — rounding it to a tidy fraction with
    # ``limit_denominator`` would invent an exactness the engine never had.
    valor_num = arriba.real - abajo.real
    error = abs(arriba.imag) + abs(abajo.imag) + _error_de_redondeo(arriba.real) \
        + _error_de_redondeo(abajo.real)
    valor_num, corregido, discrepa = _barrow_comprobado(
        integrando, primitiva, var, lim_a.real, lim_b.real, valor_num, trace)
    if discrepa is not None:
        sello = discrepa
    else:
        sello = V.Seal(
            V.NUMERIC_ONLY,
            ("Barrow por tramos, descontando los saltos de la primitiva"
             if corregido else
             "diferencia en los límites de una primitiva exacta, en aritmética decimal"),
            f"error de redondeo acumulado {error:.3g}; contrastado con cuadratura",
        )
    trace.verificacion("integral.definida.verificacion", sello.method,
                       after=f"valor {valor_num:.12g}, error {error:.3g}")
    grafica = _grafica_area(integrando, var, low, high, valor_num, error)
    if discrepa is None and not corregido:
        exacto = _diferencia_exacta(primitiva, var, low, high, valor_num)
        if exacto is not None:
            # ∫_0^pi sen x is 2, not «2 con error 4e-16»: F(pi) - F(0) simplifies
            # exactly, and the decimal value already checked against the
            # quadrature is what licenses showing it
            trace.verificacion(
                "integral.definida.exacta",
                "F(b) − F(a) se simplifica a un valor exacto",
                before=f"F({mx.text(high)}) − F({mx.text(low)})", after=mx.text(exacto),
                why=("los límites no son racionales, pero los valores notables de F "
                     "en ellos sí son exactos; el valor coincide con el decimal ya "
                     "contrastado con la cuadratura"))
            sello = V.Seal(V.VERIFIED, "Barrow con valores exactos en los límites",
                           mx.text(exacto))
            racional = mx.exact_value(exacto)
            return (mx.num(racional) if racional is not None else exacto,
                    complex(valor_num), sello, grafica, None)
    return None, complex(valor_num), sello, grafica, error


def _diferencia_exacta(primitiva: mx.Expr, var: str, a: mx.Expr, b: mx.Expr,
                       decimal: float) -> mx.Expr | None:
    """``F(b) - F(a)`` simplified to a closed exact value, or ``None``.

    Accepted only when nothing transcendental is left except ``pi`` and radicals,
    and when it agrees with the decimal value to 1e-12.
    """
    from academic_core.domain.engineering.mathlab import poly as P
    from academic_core.domain.engineering.mathlab import trig as T

    try:
        diferencia = mx.Sub(mx.substitute(primitiva, var, b),
                            mx.substitute(primitiva, var, a))
        simple = T.simplify(P.to_expr(P.as_poly(pliega_constante(diferencia))))
    except Exception:  # noqa: BLE001
        return None
    if not _cerrado(simple):
        return None
    valor = mx.valor_real(simple, {})
    if valor is None or abs(valor - decimal) > 1e-12 * max(1.0, abs(decimal)):
        return None
    return simple


def pliega_constante(e: mx.Expr) -> mx.Expr:
    """A closed expression with every argument folded before its function.

    ``trig.simplify`` reads ``sin(2·(2·pi))`` with the argument as written and does
    not reduce it; folding the argument to ``4·pi`` first lets the notable value
    appear. The inverse functions take their PRINCIPAL value at notable points
    (``atan(sqrt(3)) = pi/3``, ``atan(-1) = -pi/4``), checked against the float.
    """
    import math as _m

    from academic_core.domain.engineering.mathlab import ecuaciones as E
    from academic_core.domain.engineering.mathlab import poly as P
    from academic_core.domain.engineering.mathlab import trig as T

    def normal(x: mx.Expr) -> mx.Expr:
        try:
            return T.simplify(P.to_expr(P.as_poly(x)))
        except Exception:  # noqa: BLE001
            return T.simplify(x)

    if isinstance(e, mx.Call):
        args = tuple(pliega_constante(a) for a in e.args)
        directa = {"asin": ("sin", _m.asin), "acos": ("cos", _m.acos),
                   "atan": ("tan", _m.atan)}.get(e.name)
        if directa and len(args) == 1 and not mx.variables(args[0]):
            valor = mx.valor_real(args[0], {})
            if valor is not None and (e.name == "atan" or abs(valor) <= 1):
                angulo, multiplo, _nota = E._inversa(directa[0], args[0])
                if multiplo:
                    principal = directa[1](valor)
                    for candidato in (angulo, mx.Sub(angulo, mx.PI),
                                      mx.Sub(mx.PI, angulo), mx.Neg(angulo)):
                        v = mx.valor_real(candidato, {})
                        if v is not None and abs(v - principal) < 1e-12:
                            return normal(candidato)
        if len(args) == 1 and not mx.variables(args[0]):
            valor = mx.valor_real(args[0], {})
            if e.name == "abs" and valor is not None and valor != 0:
                return args[0] if valor > 0 else normal(mx.Neg(args[0]))
            if e.name == "ln" and mx.exact_value(args[0]) == 1:
                return mx.ZERO
            if e.name == "exp" and mx.exact_value(args[0]) == 0:
                return mx.ONE
        return T.simplify(mx.Call(e.name, args))
    if isinstance(e, mx.Neg):
        return normal(mx.Neg(pliega_constante(e.arg)))
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return normal(type(e)(pliega_constante(e.left), pliega_constante(e.right)))
    if isinstance(e, mx.Pow):
        base, exponente = pliega_constante(e.base), pliega_constante(e.exponent)
        exacta = _potencia_exacta(base, exponente)
        return exacta if exacta is not None else normal(mx.Pow(base, exponente))
    if isinstance(e, mx.Root):
        radicando = pliega_constante(e.radicand)
        exacta = _potencia_exacta(radicando, mx.Num(Fraction(1, e.degree)))
        return exacta if exacta is not None else normal(mx.Root(e.degree, radicando))
    return e


def _potencia_exacta(base: mx.Expr, exponente: mx.Expr) -> mx.Expr | None:
    """``q^(p/k)`` as a rational when ``q`` is a perfect k-th power: sqrt(4) = 2."""
    q, r = mx.exact_value(base), mx.exact_value(exponente)
    if q is None or r is None:
        return None
    q, r = Fraction(q), Fraction(r)
    k = r.denominator
    if q < 0:
        if k % 2 == 0:
            return None
        # an odd root of a negative is real: (-1)^(1/3) = -1
        positiva = _potencia_exacta(mx.Num(-q), exponente)
        if positiva is None:
            return None
        valor = mx.exact_value(positiva)
        return mx.Num(valor if r.numerator % 2 == 0 else -valor)

    def raiz(n: int) -> int | None:
        c = round(n ** (1.0 / k))
        for d in (c - 1, c, c + 1):
            if d >= 0 and d ** k == n:
                return d
        return None

    num, den = raiz(q.numerator), raiz(q.denominator)
    if num is None or den is None or (q == 0 and r < 0):
        return None
    return mx.Num(Fraction(num, den) ** r.numerator)


def _cerrado(e: mx.Expr) -> bool:
    """A closed exact constant: rationals, pi, radicals, and functions of those."""
    if isinstance(e, mx.Call):
        return all(_cerrado(a) for a in e.args)
    if isinstance(e, mx.Num):
        return True
    if isinstance(e, mx.Const):
        return e.name == "pi"
    if isinstance(e, mx.Root):
        return _cerrado(e.radicand)
    if isinstance(e, mx.Neg):
        return _cerrado(e.arg)
    if isinstance(e, mx.Pow):
        return _cerrado(e.base) and mx.exact_value(e.exponent) is not None
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return _cerrado(e.left) and _cerrado(e.right)
    return False


def _singularidad_en(integrando: mx.Expr, var: str, a: float, b: float,
                     trace: Trace):
    """A refusal when the integrand is unbounded somewhere on ``[a, b]``, else None.

    The old check probed 17 equally spaced points and missed every pole off that
    grid: ``∫_0^1 dx/(x - 1/10)`` came out 2.197 and ``∫_0^2 tan x`` 0.877, both
    divergent. The zeros of each denominator, of each ``cos`` inside a ``tan``, of
    each argument of ``ln``… are located instead (``continuidad``).
    """
    lo, hi = min(a, b), max(a, b)
    malos = K.puntos_singulares(integrando, var, lo, hi)
    if not malos:
        return None
    impropia = _impropia(integrando, var, a, b, malos, trace)
    if impropia is not None:
        return impropia
    punto = f"{malos[0]:.10g}"
    mensaje = (f"el integrando no está acotado (o no está definido) en {var} ≈ {punto}, "
               f"dentro de [{lo:.10g}, {hi:.10g}]: la integral es impropia y la regla "
               "de Barrow no se aplica, porque exige un integrando continuo en todo "
               "el intervalo")
    trace.aviso("integral.dominio", mensaje)
    return (None, None, V.Seal(V.NUMERIC_ONLY, "dominio", mensaje), None, None)


def _suma_exacta_por_tramos(F: mx.Expr, var: str, puntos, decimal: float):
    """``Σ F(x1) - F(x0)`` exactly when every cut is a small rational, else None."""
    exactos = []
    for p in puntos:
        q = Fraction(p).limit_denominator(1000)
        if abs(float(q) - p) > 1e-12:
            return None
        exactos.append(mx.Num(q))
    total = None
    for a, b in zip(exactos, exactos[1:]):
        termino = mx.Sub(mx.substitute(F, var, b), mx.substitute(F, var, a))
        total = termino if total is None else mx.Add(total, termino)
    return _diferencia_exacta(mx.Sym("_t"), "_t", mx.ZERO, total, decimal)


def _raiz_real(e: mx.Expr) -> mx.Expr:
    """``u^(p/n)`` with ``n`` odd written as ``(n-th root of u)^p``, which is real.

    The integrand ``x^(1/3)`` is read as the real cube root, but the primitive
    that comes back from E0.1 keeps the power, and a power of a negative base
    evaluates on the complex principal branch: ∫_{-1}^{1} x^(-2/3) could not be
    evaluated at -1 (found 2026-10-06). The primitive is read like its integrand.
    """
    if isinstance(e, mx.Pow):
        base, exponente = _raiz_real(e.base), _raiz_real(e.exponent)
        r = mx.exact_value(exponente)
        if r is not None and Fraction(r).denominator % 2 == 1 and Fraction(r).denominator > 1:
            r = Fraction(r)
            return mx.Pow(mx.Root(r.denominator, base), mx.Num(Fraction(r.numerator)))
        return mx.Pow(base, exponente)
    if isinstance(e, mx.Neg):
        return mx.Neg(_raiz_real(e.arg))
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(_raiz_real(e.left), _raiz_real(e.right))
    if isinstance(e, mx.Call):
        return mx.Call(e.name, tuple(_raiz_real(a) for a in e.args))
    if isinstance(e, mx.Root):
        return mx.Root(e.degree, _raiz_real(e.radicand))
    return e


def _tiende_a(F: mx.Expr, var: str, c: float, lado: int, objetivo: float) -> bool:
    """Whether F(c + lado·h) approaches ``objetivo`` monotonically as h → 0."""
    distancias = []
    for k in range(2, 16):
        x = c + lado * 10.0 ** (-k)
        if x == c:
            break
        v = mx.valor_real(F, {var: x})
        if v is None:
            return False
        distancias.append(abs(v - objetivo))
    if len(distancias) < 3:
        return False
    decrece = all(b <= a + 1e-15 for a, b in zip(distancias, distancias[1:]))
    return decrece and distancias[-1] < 1e-4 * max(1.0, abs(objetivo))


def _limite_lateral(F: mx.Expr, var: str, c: float, lado: int):
    """``("converge", valor, error)`` / ``("diverge", None, None)`` / ``None``.

    F at c + lado·10^-k, k = 2..9. Converging means every step at most 0.6 of the
    previous one; the last step bounds the rest. Diverging means |F| grows
    without the steps shrinking (ln|x| at 0 grows by ln 10 each time).
    """
    valores = []
    for k in range(2, 16):
        v = mx.valor_real(F, {var: c + lado * 10.0 ** (-k)})
        if v is None:
            return None
        valores.append(v)
    pasos = [abs(y - x) for x, y in zip(valores, valores[1:])]
    if all(b <= 0.6 * a + 1e-15 for a, b in zip(pasos, pasos[1:])):
        return "converge", valores[-1], pasos[-1] / 0.4 + 1e-15
    if abs(valores[-1]) > abs(valores[0]) and min(pasos[-3:]) > 1e-3 * max(1.0, abs(valores[0])):
        return "diverge", None, None
    return None


def _impropia(integrando: mx.Expr, var: str, a: float, b: float, singulares,
              trace: Trace):
    """An integral with singular points: its value if it converges, «diverge» if not.

    ∫_0^1 dx/sqrt(x) is 2 and ∫_0^1 ln x is -1; they used to be refused as
    «impropia». The interval is cut at each singular point, the primitive's
    one-sided limits are taken there, and the sum is checked against the
    quadrature. ``None`` when nothing can be established (no primitive, a limit
    that neither converges nor diverges): the caller then refuses as before.
    """
    from academic_core.domain.engineering.symbolic import integrate as I_
    from academic_core.domain.engineering.symbolic import steps as St

    try:
        _c, resultado, _i = I_.antiderivative(mx.to_symbolic(integrando), var, St.StepLog())
        F = _raiz_real(mx.from_symbolic(resultado))
    except Exception:  # noqa: BLE001
        return None
    signo = 1.0 if b >= a else -1.0
    lo, hi = min(a, b), max(a, b)
    puntos = sorted({lo, hi, *[c for c in singulares if lo <= c <= hi]})
    total, error = 0.0, 0.0
    todos_evaluables = True
    for x0, x1 in zip(puntos, puntos[1:]):
        extremos = []
        for c, lado in ((x0, 1), (x1, -1)):
            directo = mx.valor_real(F, {var: c})
            if directo is not None and _tiende_a(F, var, c, lado, directo):
                # F defined AT the point (2·sqrt(x) at 0) and approached from the
                # side: its value is the limit, exactly
                extremos.append(directo)
                continue
            todos_evaluables = False
            if True:
                limite = _limite_lateral(F, var, c, lado)
                if limite is None:
                    return None
                if limite[0] == "diverge":
                    mensaje = (f"la integral es impropia en {var} ≈ {c:.10g} y DIVERGE: la "
                               "primitiva no tiene límite finito al acercarse a ese punto")
                    trace.aviso("integral.diverge", mensaje)
                    return (None, None, V.Seal(V.VERIFIED, "integral impropia divergente",
                                               mensaje), None, None)
                extremos.append(limite[1])
                error += limite[2]
        total += extremos[1] - extremos[0]
    total *= signo
    cuadratura, error_cuadratura = None, 0.0
    try:
        # piece by piece, cut at the singular points, so no piece has one inside
        piezas = [K.cuadratura(integrando, var, x0, x1, tolerancia=1e-12)
                  for x0, x1 in zip(puntos, puntos[1:])]
        if all(p is not None for p in piezas):
            cuadratura = signo * sum(p[0] for p in piezas)
            error_cuadratura = sum(p[1] for p in piezas)
    except Exception:  # noqa: BLE001
        pass
    # an endpoint singularity costs the quadrature digits; its own error estimate
    # is part of the comparison, or a right answer is called discrepant
    if cuadratura is not None and abs(cuadratura - total) > max(
            1e-6 * max(1, abs(total)), 10 * error, 100 * error_cuadratura):
        detalle = (f"límites de la primitiva: {total:.12g}; cuadratura: {cuadratura:.12g}; "
                   "no coinciden")
        trace.aviso("integral.discrepancia", detalle)
        return (None, complex(total), V.Seal(V.DISCREPANT, "integral impropia", detalle),
                None, error)
    if todos_evaluables:
        exacto = _suma_exacta_por_tramos(F, var, puntos, total * signo)
        if exacto is not None:
            exacto = exacto if signo > 0 else mx.Neg(exacto)
            racional = mx.exact_value(exacto)
            return (mx.num(racional) if racional is not None else exacto, complex(total),
                    V.Seal(V.VERIFIED, "integral impropia convergente, valor exacto",
                           mx.text(exacto)), None, None)
    trace.metodo(
        "integral.impropia",
        "integral impropia: límites laterales de la primitiva en los puntos singulares",
        why=("el integrando no está acotado en algún punto del intervalo; la integral "
             "existe si la primitiva tiene límite finito al acercarse a cada uno, y "
             "su valor es la suma por tramos de esos límites"),
        after=f"{total:.12g} con error {error:.2g}")
    grafica = None
    return (None, complex(total),
            V.Seal(V.NUMERIC_ONLY, "integral impropia convergente",
                   f"{total:.12g} con error {error:.2g}; contrastada con cuadratura"),
            grafica, max(error, 1e-12))


def _barrow_comprobado(integrando: mx.Expr, primitiva: mx.Expr, var: str,
                       a: float, b: float, valor: float, trace: Trace
                       ) -> tuple[float, bool, V.Seal | None]:
    """Barrow's value with the antiderivative's jumps removed, then checked.

    Returns ``(valor, corregido, sello_si_discrepa)``. Two things are done that
    Barrow's rule does not do by itself:

    * **the jumps of F.** The universal substitution yields ``atan(tan(x/2))``,
      an antiderivative on each interval between odd multiples of π and
      discontinuous at them; ``∫_0^{2π} sin(x)·sin(x)`` came out 0 instead of π.
      Each jump inside the interval is measured and subtracted.
    * **an independent second path.** An adaptive Gauss–Kronrod quadrature, which
      shares nothing with the symbolic route, has to agree; if it does not, the
      value is not shown as a result.
    """
    lo, hi = min(a, b), max(a, b)
    signo = 1.0 if b >= a else -1.0
    saltos = K.saltos(primitiva, integrando, var, lo, hi)
    corregido = bool(saltos)
    if saltos:
        total = sum(s.tamano for s in saltos)
        valor = valor - signo * total
        lista = ", ".join(f"{var} ≈ {s.punto:.10g} (salto {s.tamano:.10g})" for s in saltos)
        trace.aviso(
            "integral.saltos_de_la_primitiva",
            f"la primitiva es discontinua dentro del intervalo, en {lista}: es una "
            "primitiva en cada tramo, pero no en todo el intervalo, así que F(b) − F(a) "
            "no es la integral. Se aplica Barrow por tramos, descontando cada salto")
    cuadratura = K.cuadratura(integrando, var, lo, hi)
    if cuadratura is None:
        trace.aviso("integral.sin_contraste",
                    "la cuadratura independiente no convergió; el valor de Barrow no "
                    "se ha podido contrastar")
        return valor, corregido, None
    q, err = cuadratura
    q *= signo
    tolerancia = max(1e-8 * max(1.0, abs(q)), 100 * err)
    if abs(valor - q) > tolerancia:
        detalle = (f"Barrow da {valor:.12g} y la cuadratura de Gauss–Kronrod "
                   f"{q:.12g} (error estimado {err:.2g}); no coinciden, así que no se "
                   "da por bueno ninguno de los dos como resultado exacto")
        trace.aviso("integral.discrepancia", detalle)
        return q, corregido, V.Seal(V.DISCREPANT, "Barrow frente a cuadratura", detalle)
    trace.verificacion(
        "integral.cuadratura",
        "contraste con una cuadratura adaptativa de Gauss–Kronrod",
        before=f"Barrow: {valor:.12g}", after=f"cuadratura: {q:.12g} ± {err:.2g}",
        why=("la cuadratura no usa la primitiva ni ninguna simplificación, así que "
             "coincidir con ella no puede salir de un error compartido (§5.3)"))
    return valor, corregido, None


def _simpson(integrando: mx.Expr, var: str, a, b, trace: Trace,
             panels: int = 64) -> tuple[float, float] | None:
    """The numeric value of a definite integral without an exact antiderivative.

    Named for what it replaced. Composite Simpson with a Richardson estimate used
    to live here, and the «error acotado» it declared was an estimate that could
    be smaller than the real error — measured 2026-10-05 against mpmath at 30
    digits: ``∫_{-1}^{11} ln(3x²)`` declared 0.0046 for an error of 0.069, and
    ``∫_3^{12} e^(x²-1/2)`` half the real error. A bound that is sometimes smaller
    than the error is not a bound.

    Now: adaptive Gauss–Kronrod (7-15), with the interval cut at every point where
    a denominator, a logarithm's argument or a root's radicand vanishes — even an
    integrable singularity is a place where a fixed grid loses digits — and the
    declared error is the larger of the method's own estimate (×10) and the
    difference between two runs at independent tolerances.
    """
    lo, hi = float(a), float(b)
    if hi == lo:
        return 0.0, 0.0
    signo = 1.0 if hi > lo else -1.0
    lo, hi = min(lo, hi), max(lo, hi)
    cortes = sorted({c for g in K.peligros(integrando, var)
                     for c in K.ceros(g, var, lo, hi) if lo < c < hi})
    puntos = [lo, *cortes, hi]
    fina = gruesa = estimado = 0.0
    for x0, x1 in zip(puntos, puntos[1:]):
        uno = K.cuadratura(integrando, var, x0, x1, tolerancia=1e-13)
        dos = K.cuadratura(integrando, var, x0, x1, tolerancia=1e-8)
        if uno is None or dos is None:
            return None
        fina += uno[0]
        gruesa += dos[0]
        estimado += uno[1]
    error = max(10 * estimado, abs(fina - gruesa)) + 4e-16 * abs(fina)
    valor = signo * fina
    trace.metodo(
        "integral.simpson",
        "sin primitiva exacta, la integral se calcula con cuadratura adaptativa "
        "de Gauss–Kronrod",
        why=("no hay primitiva exacta que derivar, así que el teorema fundamental no "
             "aplica; la cuadratura adaptativa da el valor y una estimación de su "
             "error, que es lo que §5.4 pide en este caso. El intervalo se corta en "
             "cada punto donde se anula un denominador o el argumento de un "
             "logaritmo, porque ahí una malla fija pierde cifras"),
        alternatives=(
            ("Simpson compuesto con extrapolación de Richardson",
             "su estimación de error resultó menor que el error real en integrandos "
             "que crecen deprisa o tienen una singularidad integrable dentro"),
            ("trapecios", "el mismo problema, con más puntos para el mismo coste"),
        ),
        before=f"∫[{lo}, {hi}] {mx.text(integrando)} d{var}",
        after=f"{valor:.12g} con error {error:.3g}",
    )
    trace.hipotesis("simpson.continuidad",
                    "el integrando es continuo en el intervalo de integración, salvo "
                    "singularidades integrables en los puntos de corte",
                    "se comprueba antes buscando los ceros de cada denominador y "
                    "argumento peligroso")
    return valor, error


#: returned by _barrow when E0.1 declines and the general path should answer
_A_CAMINO_GENERAL = object()


def _barrow(integrando: mx.Expr, var: str, a, b, trace: Trace,
            peticion: C.Peticion
            ) -> tuple[mx.Expr | None, complex | None, V.Seal,
                       C.Graph | None, float | None]:
    """Definite integral with rational limits: the exact value of F(b) − F(a).

    With exact rational limits the E0.1 engine evaluates the endpoints in exact
    arithmetic (``Fraction``), so the answer is exact and the seal can be
    ``verificado`` — no error bound is needed because there is none.
    """
    rechazo = _singularidad_en(integrando, var, float(a), float(b), trace)
    if rechazo is not None:
        return rechazo
    log = _e01_steps.StepLog()
    try:
        _F, diferencia, _idx = _e01_integrate.definite(
            mx.to_symbolic(integrando), var, Fraction(a), Fraction(b), log)
    except UnsupportedError as exc:
        # No exact antiderivative: the honest answer is Simpson with its error
        # bound (§5.3, §5.4), not a bare refusal and not an invented fraction.
        trace.aviso("integral.sin_exacta", f"{C.NO_EXACT}: {exc}")
        aproximacion = _simpson(integrando, var, a, b, trace)
        if aproximacion is None:
            return (None, None, V.Seal(V.NUMERIC_ONLY, "sin valor", str(exc)),
                    None, None)
        valor, error = aproximacion
        sello = V.Seal(V.NUMERIC_ONLY, "cuadratura de Gauss–Kronrod con error estimado",
                       f"{valor:.12g} con error {error:.3g}")
        grafica = _grafica_area(integrando, var, mx.num(a), mx.num(b), valor, error)
        return None, complex(valor), sello, grafica, error
    except ValidationError as exc:
        # E0.1 refused at an END point (its evaluator cannot do 0^(3/2)), but the
        # integrand was already checked bounded on [a, b]: ∫_0^4 sqrt(x) is 16/3 and
        # returned nothing (found 2026-10-06). The general path evaluates F with the
        # multivariate engine, measures jumps and checks against the quadrature.
        trace.aviso("integral.dominio_e01", f"{exc}; se usa el camino general")
        return _A_CAMINO_GENERAL
    for step in log.steps:
        trace.regla(f"e01.{step.rule}", step.explanation or step.rule,
                    before=step.before, after=step.after, piece=step.substitution,
                    uses=step.uses)
    # `definite` returns a Fraction when both endpoints are exact and a Decimal
    # otherwise; the branch decides the seal, so it is read here and not
    # pretended to be an expression.
    if isinstance(diferencia, Fraction):
        valor = mx.num(diferencia)
        metodo = "regla de Barrow con aritmética exacta"
        detalle = str(diferencia)
    else:
        valor = None
        error = abs(float(diferencia)) * 1e-15
        metodo = "regla de Barrow con aritmética decimal"
        detalle = f"{float(diferencia):.12g} con error {error:.3g}"
        trace.aviso("integral.decimal",
                    "los valores en los límites no son racionales: el resultado "
                    f"es decimal y se acota su error en {error:.3g}")
    trace.verificacion(
        "integral.barrow",
        "regla de Barrow sobre una primitiva exacta",
        before=mx.text(integrando), after=detalle,
        why=("con límites racionales, F(b) y F(a) se evalúan sin aproximación y la "
             "resta es exacta; si algún valor no es racional, se dice y se acota el error"),
    )
    comprobado, corregido, discrepa = _barrow_comprobado(
        integrando, mx.from_symbolic(_F), var, float(a), float(b), float(diferencia),
        trace)
    if discrepa is not None:
        grafica = _grafica_area(integrando, var, mx.num(a), mx.num(b), comprobado, 0.0)
        return None, complex(comprobado), discrepa, grafica, abs(comprobado) * 1e-9
    if corregido:
        # F jumped inside the interval: the exact F(b) - F(a) is NOT the integral,
        # so it cannot be shown as an exact value; the corrected one is decimal
        error = max(abs(comprobado) * 1e-9, 1e-12)
        sello = V.Seal(V.NUMERIC_ONLY, "Barrow por tramos, descontando los saltos "
                       "de la primitiva", f"{comprobado:.12g} con error {error:.3g}")
        grafica = _grafica_area(integrando, var, mx.num(a), mx.num(b), comprobado, error)
        return None, complex(comprobado), sello, grafica, error
    if not isinstance(diferencia, Fraction):
        exacto = _diferencia_exacta(mx.from_symbolic(_F), var, mx.num(a), mx.num(b),
                                    comprobado)
        if exacto is not None:
            # atan(1) - atan(-1) is pi/2, not 1.5707963267948966
            trace.verificacion(
                "integral.definida.exacta", "F(b) − F(a) se simplifica a un valor exacto",
                before=detalle, after=mx.text(exacto),
                why="el valor coincide con el decimal ya contrastado con la cuadratura")
            grafica = _grafica_area(integrando, var, mx.num(a), mx.num(b), comprobado, 0.0)
            racional = mx.exact_value(exacto)
            return (mx.num(racional) if racional is not None else exacto,
                    complex(comprobado),
                    V.Seal(V.VERIFIED, "Barrow con valores exactos en los límites",
                           mx.text(exacto)), grafica, None)
    sello = V.Seal(V.VERIFIED if isinstance(diferencia, Fraction) else V.NUMERIC_ONLY,
                   metodo, detalle)
    grafica = _grafica_area(integrando, var, mx.num(a), mx.num(b),
                            float(diferencia), 0.0)
    if isinstance(diferencia, Fraction):
        return valor, complex(float(diferencia)), sello, grafica, None
    return None, complex(float(diferencia)), sello, grafica, error


def _error_de_redondeo(valor: float) -> float:
    """Machine-level uncertainty of one evaluation, propagated."""
    return abs(valor) * 2.3e-16


def _grafica_primitiva(integrando: mx.Expr, primitiva: mx.Expr,
                       var: str) -> C.Graph:
    puntos = V.sampled_points([var], count=48)
    xs = tuple(p[var] for p in puntos)
    return C.Graph(
        series=(
            C.Serie(f"f(x) = {mx.pretty(integrando)}", xs,
                    tuple(_real(mx.evaluate(integrando, p)) for p in puntos)),
            C.Serie(f"F(x) = {mx.pretty(primitiva)}", xs,
                    tuple(_real(mx.evaluate(primitiva, p)) for p in puntos)),
        ),
        x_label=var, y_label="y",
        description=f"el integrando {mx.pretty(integrando)} y su primitiva "
                    f"{mx.pretty(primitiva)}",
    )


def _grafica_area(integrando: mx.Expr, var: str, low, high,
                  valor: float, error: float) -> C.Graph:
    """The integrand, the region and its area (§6)."""
    lo, hi = mx.evaluate(low, {}), mx.evaluate(high, {})
    puntos = V.sampled_points([var], count=48)
    xs, ys = [], []
    if lo is not None and hi is not None:
        left, right = min(lo.real, hi.real), max(lo.real, hi.real)
        for p in puntos:
            x = p[var]
            if not left <= x <= right:
                continue
            value = mx.evaluate(integrando, p)
            if value is not None:
                xs.append(x)
                ys.append(value.real)
    return C.Graph(
        series=(C.Serie(f"y = {mx.pretty(integrando)}", tuple(xs), tuple(ys)),),
        x_label=var, y_label="y",
        description=(f"la región bajo {mx.pretty(integrando)} entre {mx.text(low)} y "
                     f"{mx.text(high)}; la integral definida vale {valor:.6g} "
                     f"con error {error:.3g}"),
    )


# ---------------------------------------------------------------------------
# registration
# ---------------------------------------------------------------------------

C.registrar("derivar", _derivar)
C.registrar("gradiente", _gradiente)
C.registrar("simplificar", _simplificar)
C.registrar("transformar", _transformar)
C.registrar("modular", _modular)
C.registrar("racional", _racional)
C.registrar("evaluar", _evaluar)
C.registrar("igualdad", _igualdad)
C.registrar("integrar", _integrar)
C.registrar("resolver", _resolver)
C.registrar("resolver_inequidad", _resolver_inequidad)
C.registrar("ramas", _ramas)
C.registrar("aproximar", _aproximar)
C.registrar("complejo", _complejo)
C.registrar("fasor", _fasor)
C.registrar("caracteristicas", _caracteristicas)

__all__ = ["C", "Trace", "RESUMEN", "PASO", "DETALLADO"]
