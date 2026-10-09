# SPDX-License-Identifier: MIT
"""CI-0 (§20.2): las nueve invariantes físicas, ejecutables.

Un resultado de solver **no se muestra sin pasar por aquí**. Cada invariante
es un predicado que dice si la solución es admisible, y todas se ejecutan, no
se declaran:

1. **KCL** en cada nodo: |Σ I| ≤ ε·Σ|I|.
2. **KVL** en cada malla.
3. **Balance de potencias**: lo absorbido es lo suministrado.
4. **Condiciones de región** de cada dispositivo, coherentes con la solución.
5. **Pasividad**: en redes sin fuentes la potencia disipada no puede ser < 0.
6. **Estabilidad**: un transitorio no crece sin realimentación declarada.
7. **Dimensiones**: cada magnitud lleva la suya y encaja.
8. **Reciprocidad**: z₁₂ = z₂₁ en redes pasivas; S₁₂ = S₂₁ en parámetros S.
9. **Segundo camino**: el método alterno coincide (lo comprueba quien llama,
   no aquí: aquí se deja el hueco explícito).

La ε es **relativa** y se declara: una comprobación con tolerancia absoluta
pasa siempre en circuitos grandes y falla siempre en los pequeños, que es
peor que no comprobar nada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction

from academic_core.domain.engineering.units import Quantity


class InvarianteRota(ValueError):
    """Una solución que no cumple una ley de la física: no se muestra."""


def _muestra(valor, cifras: int = 6) -> str:
    """Escribe un número grande sin reventar.

    `float(10**500)` lanza `OverflowError`, y todos estos `float(x)` estaban
    **dentro de los mensajes de error**: una comprobación que revienta al
    intentar explicar por qué falló es peor que una que no comprueba, porque
    entrega un traceback en vez del diagnóstico. Se intenta el camino corto y,
    si no cabe, se escribe en notación científica con el número de cifras
    que tiene de verdad, que es información exacta y no una aproximación.
    """
    try:
        return f"{float(valor):.{cifras}g}"
    except (OverflowError, ValueError):
        pass
    if isinstance(valor, Fraction):
        num, den = valor.numerator, valor.denominator
        if num == 0:
            return "0"
        digitos = len(str(abs(num))) - len(str(den))
        if digitos > 300:      # la mantisa se escribe, no el entero entero
            return f"{num / den:.0e}" if digitos < 400 else f"~1e{digitos}"
        return f"{float(num) / float(den):.{cifras}g}"
    try:
        return f"{Decimal(valor):.{cifras}E}"
    except (OverflowError, ValueError, TypeError):
        return f"~{valor}"


def _sin_float(valor, donde: str) -> None:
    """Se niega a dejar pasar un `float`, venga de donde venga.

    Vive aquí y no solo en el contrato porque el `valor` de un
    :class:`Resultado` también tiene que estar limpio: con `float` en el valor,
    el digest que se calcula no corresponde al cálculo que se haría al
    reproducirlo, y la comparación de dos resultados iguales daría distinta
    por culpa de un redondeo que nadie ve.
    """
    if isinstance(valor, float):
        raise InvarianteRota(
            f"{donde} ha llegado como float ({valor!r}); el dominio calcula "
            f"exacto (P1). Escríbelo como fracción o decimal")


def _exacto(valor, donde: str) -> Fraction:
    """Convierte a fracción exacta **rechazando** los `float` (P1).

    El contrato de calculadoras ya rechaza los `float` en la puerta, pero las
    invariantes son una puerta también: si un residuo llega como `0.5`, la
    comparación se hace en binario y ni la ley ni nadie sabe ya si lo que se
    compara es el número que se escribió. Con `Fraction(0.5)` el valor sería
    exacto por casualidad —0,5 sí es representable—, y esa casualidad es
    justo la que hace peligroso dejarlo pasar: otros valores sí perderían
    cifras y el residuo que se compararía no sería el del cálculo, sino el de
    su redondeo.
    """
    if isinstance(valor, float):
        raise InvarianteRota(
            f"{donde} ha llegado como float ({valor!r}); las comprobaciones "
            f"físicas son exactas (P1). Escríbelo como fracción o decimal")
    return Fraction(valor)


#: tolerancia relativa por defecto (§20.2 usa ε). Con aritmética exacta el
#: residuo de una solución buena es 0, así que la tolerancia sólo existe para
#: atrapar un resultado *aproximado* que se ha redondeado sin decirlo. Se
#: pone en 10⁻⁷ —un milésimo de una milésima— porque es holgura de sobra para
#: cualquier redondeo honesto y demasiado estrecha para que una ley mal
#: aplicada (que se desvía en tanto por ciento) pase por buena.
EPS = Fraction(1, 10 ** 7)


@dataclass(frozen=True)
class VeredictoInvariante:
    """El resultado de una comprobación: si se cumple y por qué no, si no.

    ``comprobado`` a ``False`` quiere decir que **no se ha podido mirar**: no
    es un «cumple» disfrazado. Un invariante sin comprobar se cuenta aparte en
    el informe, porque esconderlo detrás de un ✔ es como se hace pasar por
    bueno un hueco.
    """

    nombre: str
    cumple: bool
    detalle: str = ""
    comprobado: bool = True

    def linea(self) -> str:
        if not self.comprobado:
            return f"? {self.nombre}: sin comprobar — {self.detalle}"
        marca = "✔" if self.cumple else "✘"
        return f"{marca} {self.nombre}" + (f": {self.detalle}" if self.detalle else "")


@dataclass
class Informe:
    """Todas las comprobaciones de una solución, juntas."""

    veredictos: list[VeredictoInvariante] = field(default_factory=list)

    def anade(self, v: VeredictoInvariante) -> VeredictoInvariante:
        self.veredictos.append(v)
        return v

    @property
    def cumple(self) -> bool:
        return all(v.cumple for v in self.veredictos if v.comprobado)

    @property
    def rotas(self) -> list[VeredictoInvariante]:
        return [v for v in self.veredictos if v.comprobado and not v.cumple]

    @property
    def sin_comprobar(self) -> list[VeredictoInvariante]:
        return [v for v in self.veredictos if not v.comprobado]

    def texto(self) -> str:
        cab = (f"{len(self.veredictos)} invariantes; "
               f"{len(self.sin_comprobar)} sin comprobar; "
               + ("las comprobadas cumplen" if self.cumple
                  else f"{len(self.rotas)} rotas"))
        return "\n".join([cab] + ["  " + v.linea() for v in self.veredictos])

    def exige(self) -> None:
        """§20.3.2: sin pasar esto, el resultado no se enseña."""
        if not self.cumple:
            raise InvarianteRota(
                "la solución no cumple las invariantes físicas: "
                + "; ".join(v.linea() for v in self.rotas))


# ---------------------------------------------------------------------------
# 1 y 2. KCL y KVL
# ---------------------------------------------------------------------------


def kcl(corrientes_por_nodo: dict, eps: Fraction = EPS) -> VeredictoInvariante:
    """En cada nodo, lo que entra es lo que sale.

    ``corrientes_por_nodo`` va de nombre de nodo a las corrientes que salen de
    él (negativas si entran). El residuo se compara **relativo** a la suma de
    los valores absolutos: si no, un nodo con corrientes enormes daría un
    residuo grande siendo correcto.

    El umbral por defecto es 10⁻⁷, no 10⁻⁹. Con aritmética racional el
    residuo de una solución exacta es cero, así que un umbral más pequeño
    sólo serviría para que la comprobación sólo bite en un nodo con 10¹³ A de
    fondo, que no es el caso que quiere cazar esta prueba: la que se busca es
    la ley mal aplicada, que se desvía en tanto por ciento, no en la novena
    cifra.
    """
    peor_nodo, peor = None, None
    for nodo, corro in corrientes_por_nodo.items():
        vals = [_exacto(v, f"la corriente de la rama del nodo {nodo}")
                for v in corro]
        residuo = abs(sum(vals))
        escala = sum(abs(v) for v in vals)
        if escala == 0:
            continue
        relativo = residuo / escala
        if peor is None or relativo > peor:
            peor_nodo, peor = nodo, relativo
    if peor_nodo is None:
        return VeredictoInvariante("KCL", True, "sin nodos con corriente")
    tol = max(eps, Fraction(1, 10 ** 12))
    if peor > tol:
        return VeredictoInvariante(
            "KCL", False,
            f"en el nodo {peor_nodo} el residuo es {_muestra(peor, 3)} de la suma "
            f"de corrientes, por encima de {_muestra(tol, 3)}")
    return VeredictoInvariante("KCL", True,
                               f"peor residuo relativo {_muestra(peor, 3)}")


def kvl(tensiones_por_malla: dict, eps: Fraction = EPS) -> VeredictoInvariante:
    """En cada malla, la suma de tensiones es cero."""
    peor_malla, peor = None, None
    for malla, tens in tensiones_por_malla.items():
        vals = [_exacto(v, f"la tensión del tramo de la malla {malla}")
                for v in tens]
        residuo = abs(sum(vals))
        escala = sum(abs(v) for v in vals)
        if escala == 0:
            continue
        relativo = residuo / escala
        if peor is None or relativo > peor:
            peor_malla, peor = malla, relativo
    if peor_malla is None:
        return VeredictoInvariante("KVL", True, "sin mallas con tensión")
    tol = max(eps, Fraction(1, 10 ** 12))
    if peor > tol:
        return VeredictoInvariante(
            "KVL", False,
            f"en la malla {peor_malla} la suma de tensiones deja un residuo "
            f"relativo de {_muestra(peor, 3)}")
    return VeredictoInvariante("KVL", True,
                               f"peor residuo relativo {_muestra(peor, 3)}")


# ---------------------------------------------------------------------------
# 3. balance de potencias
# ---------------------------------------------------------------------------


def balance_potencias(absorbidas, suministradas,
                      eps: Fraction = Fraction(1, 10 ** 6)) -> VeredictoInvariante:
    """Lo que se consume es lo que se entrega (convención pasiva, §14.2.1).

    La comparación es **relativa a lo suministrado**: si no hay nada
    suministrado la comprobación no significa nada, y se dice en vez de
    devolver «cumple» por el cero trivial.
    """
    a = [_exacto(v, "una potencia absorbida") for v in absorbidas]
    s = [_exacto(v, "una potencia suministrada") for v in suministradas]
    ta, ts = sum(a), sum(s)
    if ts == 0:
        if ta == 0:
            return VeredictoInvariante("balance de potencias", True,
                                       "red sin fuentes: potencia nula")
        return VeredictoInvariante(
            "balance de potencias", False,
            f"nada suministra energía pero se absorben {_muestra(ta, 6)} W")
    if ta < 0:
        return VeredictoInvariante(
            "balance de potencias", False,
            f"potencia absorbida negativa ({_muestra(ta, 6)} W): con la "
            f"convención pasiva eso es un generador que se ha puesto al revés")
    residuo = abs(ta - ts) / abs(ts)
    if residuo > eps:
        return VeredictoInvariante(
            "balance de potencias", False,
            f"se absorben {_muestra(ta, 6)} W y se suministran "
            f"{_muestra(ts, 6)} W; el desnivel relativo es {_muestra(residuo, 3)}")
    return VeredictoInvariante("balance de potencias", True,
                               f"desequilibrio relativo {_muestra(residuo, 3)}")


# ---------------------------------------------------------------------------
# 4. región de cada dispositivo
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Region:
    """El estado que un dispositivo dice tener y por qué."""

    ref: str
    tipo: str
    region: str
    corriente: Fraction | None = None
    tension: Fraction | None = None

    def linea(self) -> str:
        extra = []
        if self.corriente is not None:
            extra.append(f"I = {_muestra(self.corriente)} A")
        if self.tension is not None:
            extra.append(f"V = {_muestra(self.tension)} V")
        return f"{self.ref} ({self.tipo}): {self.region}" + (
            ", " + ", ".join(extra) if extra else "")


def regiones(datos: dict, reglas: dict) -> list[VeredictoInvariante]:
    """Comprueba que la región que dice cada dispositivo es coherente.

    ``reglas`` va de ``"D1"`` a una tupla ``(región, comprobable, motivo)``
    donde ``comprobable`` es la desigualdad que la justifica, escrita con los
    valores de la solución. Se comprueba **con los números**, no con lo que
    el dispositivo afirma: un diodo que se declara «ON» con corriente negativa
    es un error aunque el código diga ON. ``comprobable`` a ``None`` significa
    que la regla existe pero no se ha evaluado, y sale como *sin comprobar*.
    """
    fuera = []
    for ref in reglas:
        if ref not in datos:
            # una regla para un dispositivo que no está es un nombre mal
            # escrito. Ignorarla en silencio deja el hueco tapado y, cuando
            # se añada el dispositivo, su región sevaluateá sola sin que
            # nadie se entere de que la regla llevaba ahí sin usarse.
            fuera.append(VeredictoInvariante(
                f"región de {ref}", False,
                "hay una regla de región para un dispositivo que no está en "
                "la solución: el nombre no coincide con ningún ref"))
    for ref, info in datos.items():
        if ref not in reglas:
            fuera.append(VeredictoInvariante(
                f"región de {ref}", False,
                "sin regla de región declarada: nadie ha dicho por qué este "
                "dispositivo está donde dice estar"))
            continue
        region, prueba, motivo = reglas[ref]
        if prueba is None:
            fuera.append(VeredictoInvariante(
                f"región de {ref}", True,
                f"«{region}», pero la desigualdad ({motivo}) no se ha "
                f"evaluado: región afirmada, no comprobada", comprobado=False))
        else:
            fuera.append(VeredictoInvariante(
                f"región de {ref}", bool(prueba),
                "" if prueba else f"declarado «{region}» pero {motivo}"))
    return fuera


# ---------------------------------------------------------------------------
# 5. pasividad
# ---------------------------------------------------------------------------


def pasiva(potencias, tol: Fraction = Fraction(1, 10 ** 12)
           ) -> VeredictoInvariante:
    """Una red sin fuentes no genera energía: ninguna potencia puede ser < 0."""
    malos = [(k, p) for k, v in potencias.items()
             if (p := _exacto(v, f"la potencia de {k}")) < -tol]
    if malos:
        k, v = malos[0]
        return VeredictoInvariante(
            "pasividad", False,
            f"{k} disipa {_muestra(v, 6)} W (negativo): una red pasiva no "
            f"entrega energía")
    return VeredictoInvariante("pasividad", True,
                               f"{len(potencias)} elementos, ninguno negativo")


# ---------------------------------------------------------------------------
# 6. estabilidad de un transitorio
# ---------------------------------------------------------------------------


def _picos(magnitudes: list[Fraction]) -> list[Fraction]:
    """Los máximos locales, incluyendo el último punto si lo es.

    Es la serie que distingue un amortiguamiento de una divergencia: en un
    oscilador estable los picos bajan, en uno que se va suben.
    """
    picos = []
    for i, v in enumerate(magnitudes):
        anterior = magnitudes[i - 1] if i else Fraction(0)
        siguiente = magnitudes[i + 1] if i + 1 < len(magnitudes) else Fraction(0)
        if v >= anterior and v > siguiente:
            picos.append(v)
    return picos


def estable(ys, margen: Fraction = Fraction(1, 10 ** 4)) -> VeredictoInvariante:
    """El transitorio no se va sin que se haya declarado realimentación.

    No basta con que la respuesta **suba**: toda transitoria sube antes de
    asentarse, y una RC de 0 a 1 es lo más estable que hay. La diferencia la
    marcan los **picos** y el **tamaño de los pasos**:

    - si hay dos o más máximos locales y **bajan**, la respuesta se amortigua
      (caso normal, oscilador estable);
    - si **suben**, la oscilación se amplifica y eso es divergencia;
    - sin estructura de picos, la respuesta se está asentando mientras sus
      pasos **no se agranden** (`0,15 → 0,05` es un RC; `4 → 8` es una
      divergencia), siempre que la magnitud no deje de crecer.

    Un único pico, o una serie demasiado corta para tener estructura, sale
    como *sin comprobar*: con cinco muestras no se puede decir si una
    oscilación se está apagando, y devolver un ✔ sería inventar.

    Está **probada en las dos direcciones**: la suite incluye el RC normal, la
    oscilación amortiguada, la divergencia pura, la oscilación que se amplifica
    y la serie corta. Una comprobación que sólo aceptase casos divergentes, o
    que sólo rechazase casos normales, habría pasado igual con un solo test.

    **Lo que no ve:** el crecimiento lento y sin límite, como la raíz de t.
    Sus pasos se acortan, así que aquí sale como un asentamiento, y no lo es:
    la respuesta se va al infinito igual. Distinguirlo exige mirar el
    comportamiento asintótico (Routh-Hurwitz, CI-12.1) y no la forma de una
    muestra. Está anotado en los límites honestos del gate en vez de
    disimularlo con una comprobación que no lo distingue.
    """
    vals = [_exacto(v, f"un punto del transitorio ({i})")
            for i, v in enumerate(ys)]
    magnitudes = [abs(v) for v in vals]
    if len(vals) < 4:
        return VeredictoInvariante(
            "estabilidad", True,
            ("no hay ningún punto que mirar" if not vals else
             f"solo {len(vals)} {'punto' if len(vals) == 1 else 'puntos'}: "
             f"hace falta la respuesta asentada para juzgar si diverge"),
            comprobado=False)
    if max(magnitudes) == 0:
        return VeredictoInvariante("estabilidad", True, "respuesta nula")
    if min(magnitudes) == max(magnitudes):
        return VeredictoInvariante(
            "estabilidad", True,
            f"la magnitud se mantiene en {_muestra(magnitudes[0], 6)}: ya está "
            f"asentada")
    if magnitudes[-2] == 0 and magnitudes[-1] > 0:
        return VeredictoInvariante(
            "estabilidad", False,
            f"la respuesta es cero hasta el penúltimo punto y salta a "
            f"{_muestra(magnitudes[-1], 6)}: nace de la nada sin fuente "
            f"declarada")
    picos = _picos(magnitudes)
    if len(picos) >= 2:
        penultimo, ultimo = picos[-2], picos[-1]
        if ultimo > penultimo * (1 + margen):
            return VeredictoInvariante(
                "estabilidad", False,
                f"los picos crecen ({_muestra(penultimo, 6)} → "
                f"{_muestra(ultimo, 6)}): la oscilación se amplifica sin "
                f"realimentación declarada")
        # picos iguales no están «amortiguados»: se mantienen. Decir
        # «amortiguados» de una oscilación de amplitud constante sería un
        # mensaje que afirma algo que no se ha comprobado, que es el mismo
        # fallo que se evita en el resto del laboratorio.
        if ultimo == penultimo:
            return VeredictoInvariante(
                "estabilidad", True,
                f"los picos se mantienen en {_muestra(ultimo, 6)}: "
                f"oscilación marginal, ni crece ni se apaga",
                comprobado=False)
        return VeredictoInvariante(
            "estabilidad", True,
            f"picos amortiguados ({_muestra(penultimo, 6)} "
            f"a {_muestra(ultimo, 6)})")
    if len(magnitudes) < 5:
        return VeredictoInvariante(
            "estabilidad", True,
            f"solo {len(magnitudes)} puntos y un único pico: no hay forma de "
            f"distinguir un asentamiento de una divergencia", comprobado=False)
    pasos = [abs(magnitudes[i + 1] - magnitudes[i])
             for i in range(len(magnitudes) - 1)]
    cola = [magnitudes[i] for i in range(len(magnitudes) // 2, len(magnitudes))]
    monótona = all(b >= a for a, b in zip(cola, cola[1:]))
    if monótona and pasos[-1] > pasos[-2] * (1 + margen):
        return VeredictoInvariante(
            "estabilidad", False,
            f"la magnitud no deja de crecer y sus pasos se agrandan "
            f"({_muestra(pasos[-2], 6)} → {_muestra(pasos[-1], 6)}): diverge sin "
            f"realimentación declarada")
    if pasos[-1] > pasos[-2] * (1 + margen):
        return VeredictoInvariante(
            "estabilidad", True,
            f"el último paso crece ({_muestra(pasos[-2], 6)} → "
            f"{_muestra(pasos[-1], 6)}) pero la magnitud no es monótona: puede "
            f"ser un transitorio normal, sin comprobar", comprobado=False)
    return VeredictoInvariante(
        "estabilidad", True,
        f"los pasos no se agrandan (últimos: {_muestra(pasos[-2], 6)} → "
        f"{_muestra(pasos[-1], 6)}): la respuesta se asienta, no diverge")


# ---------------------------------------------------------------------------
# 7. dimensiones
# ---------------------------------------------------------------------------


def dimensiones(magnitudes: dict, esperadas: dict) -> VeredictoInvariante:
    """Cada magnitud tiene que medir lo que dice medir."""
    malos = []
    for nombre, q in magnitudes.items():
        if not isinstance(q, Quantity):
            malos.append(f"{nombre} no es una magnitud con unidades")
            continue
        if nombre in esperadas and q.dimension != esperadas[nombre]:
            malos.append(f"{nombre} mide {q.dim_name} y se esperaba otra cosa")
    if malos:
        return VeredictoInvariante("dimensiones", False, "; ".join(malos))
    return VeredictoInvariante("dimensiones", True,
                               f"{len(magnitudes)} magnitudes correctas")


# ---------------------------------------------------------------------------
# 8. reciprocidad
# ---------------------------------------------------------------------------


def reciproca(z12, z21, eps: Fraction = Fraction(1, 10 ** 9)
              ) -> VeredictoInvariante:
    """En una red pasiva, z₁₂ = z₂₁ (y S₁₂ = S₂₁)."""
    a, b = _exacto(z12, "z₁₂"), _exacto(z21, "z₂₁")
    escala = max(abs(a), abs(b), Fraction(1))
    if abs(a - b) / escala > eps:
        return VeredictoInvariante(
            "reciprocidad", False,
            f"z₁₂ = {_muestra(a, 6)} y z₂₁ = {_muestra(b, 6)}: una red sin "
            f"fuentes controladas no puede romper la simetría")
    return VeredictoInvariante("reciprocidad", True,
                               f"z₁₂ = z₂₁ = {_muestra(a, 6)}")


# ---------------------------------------------------------------------------
# comprobación completa
# ---------------------------------------------------------------------------


def comprueba(*, corrientes=None, mallas=None, absorbidas=None,
              suministradas=None, regiones_datos=None, reglas=None,
              potencias=None, transitorio=None, magnitudes=None,
              esperadas=None, z12=None, z21=None,
              segundo_camino: bool | None = None) -> Informe:
    """Ejecuta todo lo que se le dé y devuelve el informe.

    Cada invariante se evalúa **solo si se le pasa su dato**: no se inventa un
    «cumple» para lo que no se ha comprobado, porque eso es exactamente la
    forma de que un hueco se haga pasar por bueno. El invariante 9 (segundo
    camino) lo confirma quien llama, porque aquí no se puede repetir el
    cálculo por otra vía sin saber cuál era.
    """
    inf = Informe()
    if corrientes is not None:
        inf.anade(kcl(corrientes))
    if mallas is not None:
        inf.anade(kvl(mallas))
    if absorbidas is not None and suministradas is not None:
        inf.anade(balance_potencias(absorbidas, suministradas))
    if regiones_datos is not None:
        for v in regiones(regiones_datos, reglas or {}):
            inf.anade(v)
    if potencias is not None:
        inf.anade(pasiva(potencias))
    if transitorio is not None:
        inf.anade(estable(transitorio))
    if magnitudes is not None:
        inf.anade(dimensiones(magnitudes, esperadas or {}))
    if z12 is not None and z21 is not None:
        inf.anade(reciproca(z12, z21))
    if segundo_camino is not None:
        inf.anade(VeredictoInvariante(
            "segundo camino", bool(segundo_camino),
            "" if segundo_camino else "el método alterno no coincide"))
    if not inf.veredictos:
        raise InvarianteRota(
            "no se ha comprobado ningún invariante: un informe vacío no "
            "certifica nada")
    return inf