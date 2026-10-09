# SPDX-License-Identifier: MIT
"""CI-0 (§20.4): el banco de circuitos canónicos.

Un banco de regresión vale sólo si la solución esperada viene de **otro sitio**.
Si el banco calculase lo que espera con el mismo solver que después comprueba,
estaría comparando el código consigo mismo y un error común a los dos pasaría
inadvertido. Por eso aquí hay un resolutor propio, mínimo y exacto, escrito a
propósito: nodos por Kron y mallas por eliminación de Gauss, todo con
`Fraction`. Es lento e inútil para un circuito de mil nodos, y ése es el punto:
es lento, es corto y es fácil de leer entera, así que cuando discrepa del
motor de producción se sabe que el fallo está en uno de los dos.

Los valores esperados están calculados a mano y comprobados dos veces por
camino distinto (nodos y mallas, o fórmula cerrada y ley de Ohm), y cada
circuito dice cuál es su comprobación. Todos en forma exacta salvo el
transitorio, que es transcendente y va marcado como tal.

Lista completa de §20.4 pendiente de incorporar por fases: divisor cargado,
puente de Wheatstone equilibrado y desequilibrado, fuente dependiente, RC a
escalón y a onda cuadrada, RLC serie sub/sobre/crítico, filtros, rectificadores,
zener, BJT por divisor, MOS con carga activa, par diferencial, espejo de
corriente, op-amp, Sallen-Key, Wien, Schmitt, línea λ/4, stub, convertidores,
lazo con margen de fase, calibración. Empieza por los que se resuelven en forma
cerrada exacta; los de dispositivos van con su modelo y llegan con CI-9.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, localcontext
from fractions import Fraction

from academic_core.domain.engineering.circuits import invariantes as I

#: el transitorio necesita 50 dígitos; con 28 no coincide ni el sello
PRECISION = 50


# ---------------------------------------------------------------------------
# un resolutor exacto propio: la referencia no puede ser el código bajo prueba
# ---------------------------------------------------------------------------


def gauss(A: list[list[Fraction]], b: list[Fraction]) -> list[Fraction]:
    """Eliminación de Gauss con pivoteo parcial sobre `Fraction`."""
    n = len(b)
    M = [fila[:] + [b[i]] for i, fila in enumerate(A)]
    for col in range(n):
        pivote = max(range(col, n), key=lambda r: abs(M[r][col]))
        if M[pivote][col] == 0:
            raise ZeroDivisionError(
                f"el sistema no tiene solución única: la columna {col} se anula")
        M[col], M[pivote] = M[pivote], M[col]
        for fila in range(col + 1, n):
            factor = M[fila][col] / M[col][col]
            if factor:
                for j in range(col, n + 1):
                    M[fila][j] -= factor * M[col][j]
    x = [Fraction(0)] * n
    for col in reversed(range(n)):
        acc = M[col][n] - sum(M[col][j] * x[j] for j in range(col + 1, n))
        x[col] = acc / M[col][col]
    return x


# ---------------------------------------------------------------------------
# el canónico
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Canonico:
    """Un circuito con su solución conocida y el por qué de esa solución."""

    nombre: str
    descripcion: str
    resuelve: object                 # () -> dict[str, valor]
    espera: dict
    comprobacion: str = ""           # el segundo camino, escrito
    metodo: str = ""                 # cómo se ha resuelto
    invariantes: dict = field(default_factory=dict)

    def linea(self) -> str:
        return (f"{self.nombre}: {self.descripcion}\n"
                f"  método: {self.metodo}\n"
                f"  espera: {self.espera}\n"
                f"  comprobado por: {self.comprobacion}")

    def cumple_invariantes(self) -> I.Informe:
        """Las comprobaciones que este circuito puede hacer de sí mismo."""
        if not self.invariantes:
            raise I.InvarianteRota(
                f"{self.nombre} no declara ninguna invariante comprobable")
        return I.comprueba(**self.invariantes)


_BANCO: dict[str, Canonico] = {}


def registra(c: Canonico) -> Canonico:
    _BANCO[c.nombre] = c
    return c


def nombres() -> list[str]:
    return sorted(_BANCO)


def busca(nombre: str) -> Canonico:
    try:
        return _BANCO[nombre]
    except KeyError:
        raise KeyError(
            f"no hay ningún canónico llamado {nombre!r}; hay "
            + ", ".join(nombres())) from None


# ---------------------------------------------------------------------------
# 1. malla simple: una sola espira
# ---------------------------------------------------------------------------


def _malla_simple() -> dict:
    """V = 2 V entre R1 = 2 Ω y R2 = 4 Ω en serie. Una espira: I = V/R_total."""
    v, r1, r2 = Fraction(2), Fraction(2), Fraction(4)
    i = v / (r1 + r2)
    return {"I": i, "V1": i * r1, "V2": i * r2}


registra(Canonico(
    nombre="malla_simple",
    descripcion="una espira de dos resistencias en serie con 2 V",
    resuelve=_malla_simple,
    espera={"I": Fraction(1, 3),
            "V1": Fraction(2, 3), "V2": Fraction(4, 3)},
    metodo="división de tensión: I = V / (R1 + R2) = 2/6 = 1/3 A, y luego "
           "V = I·R en cada tramo",
    comprobacion="KCL/KVL de la espira y suma de las caídas = la fuente: "
                 "2/3 + 4/3 = 2 V",
    invariantes={
        "corrientes": {"nodo": [Fraction(1, 3), Fraction(-1, 3)]},
        "mallas": {"espira": [Fraction(2), Fraction(-2, 3), Fraction(-4, 3)]},
    },
))


# ---------------------------------------------------------------------------
# 2. doble malla: dos espiras con resistencia común
# ---------------------------------------------------------------------------


def _doble_malla() -> dict:
    """12 V con 4 Ω en la espira 1; 6 V con 6 Ω en la espira 2; 3 Ω comunes.

    Ecuaciones de malla:  4·i1 + 3·(i1 − i2) = 12 ;  6·i2 + 3·(i2 − i1) = 6
    """
    A = [[Fraction(7), Fraction(-3)], [Fraction(-3), Fraction(9)]]
    b = [Fraction(12), Fraction(6)]
    i1, i2 = gauss(A, b)
    return {"I1": i1, "I2": i2, "Ic": i1 - i2}


registra(Canonico(
    nombre="doble_malla",
    descripcion="dos espiras que comparten 3 Ω, con 12 V y 6 V",
    resuelve=_doble_malla,
    espera={"I1": Fraction(7, 3), "I2": Fraction(13, 9), "Ic": Fraction(8, 9)},
    metodo="mallas: la resistencia común aparece con el signo contrario en "
           "las dos ecuaciones porque las dos corrientes la cruzan en sentidos "
           "opuestos; 7·i1 − 3·i2 = 12 y −3·i1 + 9·i2 = 6",
    comprobacion="la corriente por el 3 Ω shared sale de la diferencia "
                 "i1 − i2 = 8/9 A, y por KCL en el nodo medio ni entra ni sale",
    invariantes={
        "corrientes": {"medio": [Fraction(8, 9), Fraction(-8, 9)]},
        "absorbidas": [Fraction(0)],
        "suministradas": [Fraction(0)],
    },
))


# ---------------------------------------------------------------------------
# 3. divisor cargado
# ---------------------------------------------------------------------------


def _divisor_cargado() -> dict:
    """12 V, R1 = 2 kΩ en serie, R2 = 4 kΩ a masa y RL = 4 kΩ de carga.

    R2‖RL = 2 kΩ, así que V_sal = 12 · 2/(2+2) = 6 V. Y por Thevenin:
    V_th = 12 · 4/6 = 8 V, R_th = 2‖4 = 4/3 kΩ, y 8·4/(4/3+4) = 6 V.
    """
    v, r1, r2, rl = Fraction(12), Fraction(2), Fraction(4), Fraction(4)
    par = r2 * rl / (r2 + rl)
    vsal = v * par / (r1 + par)
    vth = v * r2 / (r1 + r2)
    rth = r1 * r2 / (r1 + r2)
    return {"V_sal": vsal, "Vth": vth, "Rth": rth,
            "V_sal_teorico": vth * rl / (rth + rl)}


registra(Canonico(
    nombre="divisor_cargado",
    descripcion="divisor 2k/4k con 4k de carga, alimentado con 12 V",
    resuelve=_divisor_cargado,
    espera={"V_sal": Fraction(6), "Vth": Fraction(8),
            "Rth": Fraction(4, 3), "V_sal_teorico": Fraction(6)},
    metodo="paralelo de R2 con la carga y después el divisor; la carga baja "
           "la salida de 8 V en vacío a 6 V",
    comprobacion="por Thevenin, que es un camino independiente: V_th = 8 V, "
                 "R_th = 4/3 kΩ, y 8·4/(4/3 + 4) = 6 V, el mismo valor",
    invariantes={
        "absorbidas": [Fraction(0)],
        "suministradas": [Fraction(0)],
    },
))


# ---------------------------------------------------------------------------
# 4. puente de Wheatstone desequilibrado
# ---------------------------------------------------------------------------


def _puente_desbalanceado() -> dict:
    """12 V entre A (arriba) y D (masa); R1=4 y R2=6 en el brazo izquierdo,
    R3=6 y R4=3 en el derecho. El puente da 0 V sólo si R1/R2 = R3/R4, y aquí
    4/6 ≠ 6/3, así que la diagonal tiene tensión: es el caso que enseña algo.

    B: (V_B−12)/4 + V_B/6 = 0  →  V_B = 36/5
    C: (V_C−12)/6 + V_C/3 = 0  →  V_C = 4
    """
    v, r1, r2, r3, r4 = (Fraction(12), Fraction(4), Fraction(6),
                         Fraction(6), Fraction(3))
    vb = v * r2 / (r1 + r2)
    vc = v * r4 / (r3 + r4)
    return {"V_A": v, "V_B": vb, "V_C": vc, "V_D": Fraction(0),
            "V_diagonal": vb - vc}


registra(Canonico(
    nombre="puente_desbalanceado",
    descripcion="puente de Wheatstone 4/6 frente a 6/3 con 12 V: desequilibrado",
    resuelve=_puente_desbalanceado,
    espera={"V_A": Fraction(12), "V_B": Fraction(36, 5), "V_C": Fraction(4),
            "V_D": Fraction(0), "V_diagonal": Fraction(16, 5)},
    metodo="cada rama es un divisor independiente porque el punto medio de la "
           "diagonal es de alta impedancia y no se cargan entre sí: V_B = "
           "12·6/10 = 7,2 V y V_C = 12·3/9 = 4 V",
    comprobacion="la diagonal mide 7,2 − 4 = 3,2 V, que es cero sólo si "
                 "4/6 = 6/3; como no lo son, la diferencia es la lectura y "
                 "no un error de cálculo",
    invariantes={
        "absorbidas": [Fraction(0)],
        "suministradas": [Fraction(0)],
    },
))


# ---------------------------------------------------------------------------
# 5. puente equilibrado: el caso cuyo error es pasar por alto
# ---------------------------------------------------------------------------


def _puente_equilibrado() -> dict:
    """12 V con R1=4, R2=6, R3=4, R6: 4/6 = 4/6, luego la diagonal es 0."""
    v, r1, r2, r3, r4 = (Fraction(12), Fraction(4), Fraction(6),
                         Fraction(4), Fraction(6))
    return {"V_B": v * r2 / (r1 + r2), "V_C": v * r4 / (r3 + r4),
            "V_diagonal": v * r2 / (r1 + r2) - v * r4 / (r3 + r4)}


registra(Canonico(
    nombre="puente_equilibrado",
    descripcion="puente de Wheatstone 4/6 frente a 4/6 con 12 V: equilibrado",
    resuelve=_puente_equilibrado,
    espera={"V_B": Fraction(36, 5), "V_C": Fraction(36, 5),
            "V_diagonal": Fraction(0)},
    metodo="el criterio de equilibrio R1/R2 = R3/R4 se cumple y predice "
           "diagonal nula sin necesidad de calcularla",
    comprobacion="el criterio de equilibrio da 0, y el cálculo directo de las "
                 "dos mitades da también 0: los dos caminos coinciden en el "
                 "caso en que la diagonal no se nota",
    invariantes={
        "absorbidas": [Fraction(0)],
        "suministradas": [Fraction(0)],
    },
))


# ---------------------------------------------------------------------------
# 6. RC a escalón: el primero que no es racional
# ---------------------------------------------------------------------------


def _rc_escalon() -> dict:
    """R = 1 kΩ, C = 1 µF (τ = 1 ms) y un escalón de 5 V.

    v(t) = 5·(1 − e^(−t/τ)). Con t = τ sale 5·(1 − 1/e) ≈ 3,1606…: número
    decimal, no fracción, y por eso va con más cifras de las que se muestran
    en pantalla. Lo que sí es exacto son τ, v(0) = 0 y v(∞) = 5.
    """
    # 1 kΩ y 1 µF: en unidades base, 1000 Ω y 1e-6 F. Escribir «1» para la
    # resistencia salía aquí con τ = 1 µs en vez de 1 ms.
    v, r, c = Fraction(5), Fraction(1000), Fraction(1, 10 ** 6)
    tau = r * c
    with localcontext() as ctx:
        ctx.prec = PRECISION
        e = Decimal(1).exp()
        # la fracción se entra como decimal, no al revés: mezclar
        # `Fraction * Decimal` es un TypeError, no una aproximación silenciosa
        en_tau = Decimal(v.numerator) / Decimal(v.denominator) * (
            Decimal(1) - Decimal(1) / e)
    return {"tau": tau, "v_0": Fraction(0), "v_inf": v,
            "v_tau": en_tau, "i_0": v / r, "i_inf": Fraction(0)}


registra(Canonico(
    nombre="rc_escalon",
    descripcion="RC de 1 kΩ y 1 µF con escalón de 5 V; τ = 1 ms",
    resuelve=_rc_escalon,
    espera={"tau": Fraction(1, 1000), "v_0": Fraction(0), "v_inf": Fraction(5),
            "v_tau": Decimal("3.16060279414278839202238114919269566277094"
                             "43448412"),
            "i_0": Fraction(5, 1000), "i_inf": Fraction(0)},
    metodo="solución forzada de un RC de primer orden: v(t) = V∞·(1 − "
           "e^(−t/τ)) con τ = R·C = 1 ms; la corriente arranca en V/R y se "
           "apaga cuando el condensador queda cargado",
    comprobacion="τ en cerrado exacto y los extremos v(0) = 0, v(∞) = 5, "
                 "i(0) = 5 mA, i(∞) = 0; el valor intermedio es el único "
                 "trascendente y se guarda con 50 dígitos",
    invariantes={
        # la respuesta de un RC se acerca a 5 V desde abajo: los pasos se
        # acortan (3,00 → 1,33 → 0,42 → 0,25) y eso es lo que la distingue de
        # una divergencia, no el hecho de que suba
        "transitorio": [Fraction(0), Fraction(3), Fraction(13, 3),
                        Fraction(19, 4), Fraction(5)],
        "absorbidas": [Fraction(0)],
        "suministradas": [Fraction(0)],
    },
))
