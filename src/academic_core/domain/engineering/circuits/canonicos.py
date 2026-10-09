# SPDX-License-Identifier: MIT
"""CI-0 (§20.4): el banco de circuitos canónicos.

Un banco de regresión vale sólo si la solución esperada viene de **otro sitio**.
Si el banco calculase lo que espera con el mismo solver que después comprueba,
estaría comparando el código consigo mismo y un error común a los dos pasaría
inadvertido. Por eso aquí el cálculo se escribe de otra manera a como lo
hará el motor de producción, y en dos formatos distintos:

- **fórmula cerrada** en los cinco circuitos Pasivos (malla simple, doble
  malla, divisor, los dos puentes): se aplica la ley que se enseña y se
  escribe el resultado en `Fraction`;
- **eliminación de Gauss con `Fraction`** en la doble malla, que es el único
  donde hace falta un sistema. La implementa :func:`gauss`, escrita aquí a
  propósito.

**No hay resolutor de nodos todavía** (ni Kron ni Kirchhoff): los circuitos con
fuente en un rama se resuelven aquí por fórmula cerrada, no por sistema. Cuando
llegue el solver de nodos de CI-1 se pondrá a la obra y el banco pasará a tener
las dos vías para los mismos circuitos, que es cuando la comparación empieza a
valer algo.

Los valores esperados están calculados a mano y comprobados por un camino
independiente (el divisor por Thevenin, el puente por el criterio de
equilibrio, la doble malla por la corriente del nodo medio), y cada
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
from decimal import Decimal
from fractions import Fraction

from academic_core.domain.engineering.circuits import invariantes as I
from academic_core.domain.engineering.circuits.contrato import con_precision


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
        # 2 V x 1/3 A = 2/3 W, y las dos resistencias disipan
        # (1/3)²x2 + (1/3)²x4 = 2/9 + 4/9 = 2/3 W
        "absorbidas": [Fraction(2, 9), Fraction(4, 9)],
        "suministradas": [Fraction(2, 3)],
    },
))


# ---------------------------------------------------------------------------
# 2. doble malla: dos espiras con resistencia común
# ---------------------------------------------------------------------------


def _doble_malla() -> dict:
    """12 V alimentando 4 Ω; 6 V alimentando 6 Ω; los dos tramos se juntan en
    un nodo del que sale un 3 Ω común a masa:

        V1 0→n1 (12 V)   R1 n1→n2 (4 Ω)
        V2 0→n3 (6 V)    R2 n3→n2 (6 Ω)
        R3 n2→0 (3 Ω)

    **Las dos corrientes de malla vuelven por R3 en el mismo sentido**, así que
    sus corrientes se **suman**: 4·i1 + 3·(i1 + i2) = 12 y 6·i2 +
    3·(i1 + i2) = 6, es decir 7·i1 + 3·i2 = 12 y 3·i1 + 9·i2 = 6.

    La primera versión de este canónico llevaba **menos** en el 3 Ω y decía
    que la razón era que «la resistencia común aparece con el signo
    contrario porque las dos corrientes la cruzan en sentidos opuestos». Eso es
    cierto en **otra** topología, la del resistor común entre los dos puntos
    medios, y falso en ésta. El error daba i1 = 7/3 e i2 = 13/9, que
    **violan KCL**: al nodo central entran 34/9 A y salen 8/9. Se cazó al
    contrastar este canónico con el MNA de producción, que es para lo que sirve
    un banco canónico; el propio banco se autocomprobaba y no lo veía, porque
    autocomprobarse con el mismo criterio equivocado no comprueba nada.
    """
    A = [[Fraction(7), Fraction(3)], [Fraction(3), Fraction(9)]]
    b = [Fraction(12), Fraction(6)]
    i1, i2 = gauss(A, b)
    return {"I1": i1, "I2": i2, "Ic": i1 + i2}


registra(Canonico(
    nombre="doble_malla",
    descripcion="dos espiras que comparten el 3 Ω de retorno, con 12 V y 6 V",
    resuelve=_doble_malla,
    espera={"I1": Fraction(5, 3), "I2": Fraction(1, 9), "Ic": Fraction(16, 9)},
    metodo="mallas: las dos corrientes vuelven por el 3 Ω común en el mismo "
           "sentido, así que allí se suman y no se restan; 7·i1 + 3·i2 = 12 y "
           "3·i1 + 9·i2 = 6",
    comprobacion="por KCL en el nodo central: por R1 llega i1 = 5/3 y por "
                 "R2 llega i2 = 1/9, y por el 3 Ω se salen los 16/9; el MNA de "
                 "producción da los tres números, y el balance de potencias "
                 "cierra a 62/3 W por los dos lados",
    invariantes={
        "corrientes": {"medio": [Fraction(16, 9), Fraction(-16, 9)]},
        # 12 V x 5/3 = 20 W y 6 V x 1/9 = 2/3 W; los tres resistores
        # disipan 100/9 + 2/27 + 256/27 = 62/3 W, que es lo mismo
        "absorbidas": [Fraction(100, 9), Fraction(2, 27), Fraction(256, 27)],
        "suministradas": [Fraction(20), Fraction(2, 3)],
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
        # 12 V por 3 mA = 36 mW; R1 9/500, y el paralelo R2||RL a 6 V
        # disipa 9/1000 + 9/1000
        "absorbidas": [Fraction(9, 500), Fraction(9, 1000), Fraction(9, 1000)],
        "suministradas": [Fraction(9, 250)],
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
        # las dos ramas en paralelo desde la misma fuente de 12 V: 12 x
        # (6/5 + 4/3) = 152/5 W, y las cuatro resistencias 152/5 W
        "absorbidas": [Fraction(144, 25), Fraction(216, 25),
                       Fraction(32, 3), Fraction(16, 3)],
        "suministradas": [Fraction(152, 5)],
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
        # las dos ramas llevan 6/5 A: 2 x 144/25 + 2 x 216/25 = 144/5 W
        "absorbidas": [Fraction(144, 25), Fraction(216, 25),
                       Fraction(144, 25), Fraction(216, 25)],
        "suministradas": [Fraction(144, 5)],
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
    with con_precision():
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
        # la resistencia sola durante el transitorio: 5 V x 5 mA = 25 mW
        "absorbidas": [Fraction(25, 1000)],
        "suministradas": [Fraction(25, 1000)],
    },
))
