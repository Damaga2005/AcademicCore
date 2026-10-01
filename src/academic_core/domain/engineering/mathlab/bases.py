# SPDX-License-Identifier: MIT
"""MATH_LAB ML-1: numeral bases, bit masks and IPv4 addressing.

The «Bases de numeración» calculator of §8.2 A and its v2 additions:

    Conversión con pasos (enlaza con el laboratorio digital)
    AND/OR/XOR/desplazamiento; red, difusión y número de hosts 2^(32−p)−2

A deliberate omission
--------------------

**Two's complement, signed range and overflow are NOT implemented here.**
§4.0 assigns their single implementation to ``DIGITAL_DESIGN_LAB.md`` §10, so
re-implementing them would create the second source of truth that §16 exists to
prevent. What this module offers is the *unsigned* view — which is what
addressing needs — and it says so in the trace when a signed question comes up,
rather than answering with half the rule.

Bases and masks
---------------

Conversion is done by repeated division, one step per digit, because that is the
method a student can check. The v2 part works on integers, never on strings of
bits, and every bit operation is verified by re-computing it from the definition
(``a AND b`` is checked against the mask of set bits, ``a OR b`` against the
union, ``a XOR b`` against the symmetric difference) — the second path of §5.3.
"""

from __future__ import annotations

from dataclasses import dataclass

from academic_core.domain.engineering.mathlab import verify as V
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import ValidationError

DIGITOS = "0123456789ABCDEF"
MAX_BITS = 64
MAX_CIFRAS = 64
MAX_HOSTS = 2 ** 24


def _error(reason: str, message: str) -> ValidationError:
    return ValidationError(f"{reason}: {message}")


def _entero(valor: object, que: str = "el número") -> int:
    try:
        n = int(valor)
    except (TypeError, ValueError) as exc:
        raise _error("BAD_INPUT", f"{que} debe ser un número entero: {valor!r}") from exc
    if abs(n) >= 2 ** MAX_BITS:
        raise _error("EXPRESSION_LIMIT", f"{que} supera los {MAX_BITS} bits")
    return n


# ---------------------------------------------------------------------------
# conversion
# ---------------------------------------------------------------------------


def a_base(n: object, base: int, trace: Trace | None = None) -> str:
    """Represent ``n`` in ``base`` by repeated division, one step per digit."""
    trace = trace if trace is not None else Trace()
    valor = _entero(n, "el número")
    if not 2 <= base <= 16:
        raise _error("BAD_BASE", f"la base debe estar entre 2 y 16, no {base}")
    if valor == 0:
        trace.metodo("base.cero", "el cero se escribe 0 en cualquier base",
                     why="es el único número cuyo resto en la división por la base es 0",
                     before="0", after="0")
        return "0"
    signo = "-" if valor < 0 else ""
    resto = abs(valor)
    digitos: list[str] = []
    while resto:
        cociente, r = divmod(resto, base)
        digitos.append(DIGITOS[r])
        trace.regla(
            "base.division",
            f"{resto} = {cociente}·{base} + {r}  (dígito {DIGITOS[r]})",
            before=str(resto), after=f"dígito {DIGITOS[r]}, sigue {cociente}",
            piece=f"división entre {base}",
            conditions=(f"0 ≤ {r} < {base}",),
            why=("el resto es la cifra de la derecha y el cociente es lo que queda por "
                 "escribir; se repite hasta llegar a cero, y por eso los restos se "
                 "obtienen al revés"),
        )
        resto = cociente
    resultado = signo + "".join(reversed(digitos))
    if len(resultado) > MAX_CIFRAS:
        raise _error("EXPRESSION_LIMIT", f"el número necesita más de {MAX_CIFRAS} cifras")
    trace.regla("base.resultado", f"{valor} en base {base}",
                before=str(valor), after=resultado,
                why=("los restos se leen de abajo arriba; comprobarlo es volver a "
                     f"convertir {resultado} a base 10"))
    return resultado


def de_base(texto: str, base: int, trace: Trace | None = None) -> int:
    """Read a number written in ``base`` back to an integer, one step per digit."""
    trace = trace if trace is not None else Trace()
    if not isinstance(texto, str) or not texto.strip():
        raise _error("BAD_INPUT", "expresión vacía en base " + str(base))
    if not 2 <= base <= 16:
        raise _error("BAD_BASE", f"la base debe estar entre 2 y 16, no {base}")
    limpio = texto.strip().upper()
    signo = 1
    if limpio[:1] == "-":
        signo, limpio = -1, limpio[1:]
    if len(limpio) > MAX_CIFRAS:
        raise _error("EXPRESSION_LIMIT", f"más de {MAX_CIFRAS} cifras")
    valores = []
    for indice, caracter in enumerate(limpio):
        if caracter not in DIGITOS[:base]:
            raise _error(
                "BAD_DIGIT",
                f"«{caracter}» no existe en base {base} (posición {indice + 1}); "
                f"los dígitos válidos son {DIGITOS[:base]}",
            )
        valores.append(DIGITOS.index(caracter))
    total = 0
    for indice, valor in enumerate(valores):
        total = total * base + valor
        trace.regla(
            "base.lectura",
            f"se lee {DIGITOS[valor]} en la posición {indice + 1} desde la izquierda",
            before=str(total - valor), after=str(total),
            piece=f"dígito {DIGITOS[valor]}",
            why=(f"acumulando: valor = valor·{base} + dígito, es decir "
                 f"{total - valor}·{base} + {valor} = {total}"),
        )
    return signo * total


# ---------------------------------------------------------------------------
# masks
# ---------------------------------------------------------------------------


def mascara(subred: int, prefijo: int, trace: Trace | None = None) -> int:
    """The subnet mask of a ``/prefijo``: ones where the prefix says network."""
    trace = trace if trace is not None else Trace()
    if not 0 <= prefijo <= 32:
        raise _error("BAD_PREFIX", f"el prefijo debe estar entre 0 y 32, no {prefijo}")
    if not 0 <= subred <= 2 ** 32 - 1:
        raise _error("BAD_ADDRESS", "una dirección IPv4 no supera 2³²−1")
    mascara_valor = ((1 << prefijo) - 1) << (32 - prefijo) if prefijo else 0
    trace.regla(
        "ipv4.mascara",
        f"máscara de /{prefijo}: {prefijo} unos y {32 - prefijo} ceros",
        before=f"prefijo {prefijo}", after=a_base(mascara_valor, 2, trace),
        conditions=("un prefijo /32 deja 0 hosts útiles y un /31 solo deja 2, que es el "
                    "límite histórico de la RFC 3021",),
        why=("el prefijo dice cuántos bits identifican la red; la máscara pone un 1 en "
             "esos bits y un 0 en los que identifican el host, y AND entre la dirección y "
             "la máscara da la dirección de red"),
    )
    return mascara_valor


@dataclass(frozen=True)
class Red:
    """An IPv4 network: address, mask, prefix, broadcast and usable hosts."""

    red: int
    mascara: int
    prefijo: int
    difusion: int
    primero_util: int | None
    ultimo_util: int | None
    hosts: int

    @property
    def texto(self) -> str:
        base = f"{_ipv4(self.red)}/{self.prefijo}"
        if self.hosts > 0:
            return (f"{base} → red {_ipv4(self.red)}, difusión {_ipv4(self.difusion)}, "
                    f"hosts útiles {self.hosts} "
                    f"({_ipv4(self.primero_util)} – {_ipv4(self.ultimo_util)})")
        return f"{base} → sin hosts útiles"


def _ipv4(n: int) -> str:
    return ".".join(str((n >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def red_ipv4(direccion: object, prefijo: int, trace: Trace | None = None) -> Red:
    """Split an address into network, broadcast and usable hosts, with the count."""
    trace = trace if trace is not None else Trace()
    n = _entero(direccion, "la dirección")
    if not 0 <= n <= 2 ** 32 - 1:
        raise _error("BAD_ADDRESS", "una dirección IPv4 no supera 2³²−1")
    m = mascara(n, prefijo, trace)
    red = n & m
    difusion = red | (~m & 0xFFFFFFFF)
    total = 1 << (32 - prefijo)
    # the network and the broadcast addresses are not assignable to a host
    hosts = max(total - 2, 0)
    primero = red + 1 if hosts else None
    ultimo = difusion - 1 if hosts else None
    trace.regla(
        "ipv4.hosts",
        f"número de hosts de un /{prefijo}: 2^{32 - prefijo} − 2 = {total} − 2 = {hosts}",
        before=f"2^{32 - prefijo} direcciones", after=str(hosts),
        conditions=("se restan la dirección de red y la de difusión porque ninguna de las "
                    "dos se asigna a un equipo",),
        why=(f"un /{prefijo} deja {32 - prefijo} bits para el host, así que hay "
             f"2^{32 - prefijo} direcciones; al restar las dos reservadas quedan las "
             f"asignables, que es el {hosts} del enunciado"),
    )
    if hosts > MAX_HOSTS:
        trace.aviso("ipv4.hosts.grandes",
                    f"un /{prefijo} da {hosts} hosts: es una red enorme, comprueba el "
                    "enunciado")
    return Red(red, m, prefijo, difusion, primero, ultimo, hosts)


def _bits(n: int, ancho: int = 32) -> str:
    return format(n & ((1 << ancho) - 1), f"0{ancho}b")


def mascara_y(valor: object, mascara_bits: object,
              trace: Trace | None = None) -> int:
    """``a AND b`` on the bit string, verified against the set bits."""
    trace = trace if trace is not None else Trace()
    a, b = _entero(valor, "el primer operando"), _entero(mascara_bits, "la máscara")
    resultado = a & b
    esperados = [i for i in range(MAX_BITS) if (a >> i & 1) and (b >> i & 1)]
    obtenido = [i for i in range(MAX_BITS) if (resultado >> i & 1)]
    trace.regla(
        "bits.and",
        f"{_bits(a)} AND {_bits(b)} = {_bits(resultado)}",
        before=f"{_bits(a)} y {_bits(b)}", after=_bits(resultado),
        piece="bit a bit",
        why=("un 1 sale solo si los dos operandos tienen 1 en esa posición; es la "
             "intersección de los bits activos"),
    )
    if esperados != obtenido:
        raise _error("INTERNAL", "AND no coincide con la intersección de bits")
    return resultado


def mascara_o(valor: object, otro: object, trace: Trace | None = None) -> int:
    """``a OR b``, verified against the union of the set bits."""
    trace = trace if trace is not None else Trace()
    a, b = _entero(valor, "el primer operando"), _entero(otro, "el segundo operando")
    resultado = a | b
    esperados = sorted({i for i in range(MAX_BITS) if (a >> i & 1) or (b >> i & 1)})
    obtenido = [i for i in range(MAX_BITS) if (resultado >> i & 1)]
    trace.regla("bits.or", f"{_bits(a)} OR {_bits(b)} = {_bits(resultado)}",
                before=f"{_bits(a)} y {_bits(b)}", after=_bits(resultado),
                piece="bit a bit",
                why=("un 1 sale si cualquiera de los dos tiene 1; es la unión de los bits "
                     "activos"))
    if esperados != obtenido:
        raise _error("INTERNAL", "OR no coincide con la unión de bits")
    return resultado


def mascara_xor(valor: object, otro: object, trace: Trace | None = None) -> int:
    """``a XOR b``, verified against the symmetric difference."""
    trace = trace if trace is not None else Trace()
    a, b = _entero(valor, "el primer operando"), _entero(otro, "el segundo operando")
    resultado = a ^ b
    esperados = sorted({i for i in range(MAX_BITS) if (a >> i & 1)} ^
                       {i for i in range(MAX_BITS) if (b >> i & 1)})
    obtenido = [i for i in range(MAX_BITS) if (resultado >> i & 1)]
    trace.regla("bits.xor", f"{_bits(a)} XOR {_bits(b)} = {_bits(resultado)}",
                before=f"{_bits(a)} y {_bits(b)}", after=_bits(resultado),
                piece="bit a bit",
                why=("un 1 sale si los dos bits difieren; es la diferencia simétrica, y por "
                     "eso a XOR a = 0, que es lo que hace posible el checksum"))
    if esperados != obtenido:
        raise _error("INTERNAL", "XOR no coincide con la diferencia simétrica")
    return resultado


def desplazar(valor: object, posiciones: int, izquierda: bool = True,
              trace: Trace | None = None) -> int:
    """``a << k`` or ``a >> k``, with the bit string before and after."""
    trace = trace if trace is not None else Trace()
    a = _entero(valor, "el número")
    if not 0 <= abs(posiciones) <= MAX_BITS:
        raise _error("EXPRESSION_LIMIT", f"el desplazamiento debe estar entre 0 y {MAX_BITS}")
    resultado = (a << posiciones) if izquierda else (a >> posiciones)
    trace.regla(
        "bits.desplazamiento",
        f"{a} {'<<' if izquierda else '>>'} {posiciones} = {resultado}",
        before=_bits(a), after=_bits(resultado),
        piece=f"{posiciones} posiciones hacia {'la izquierda' if izquierda else 'la derecha'}",
        conditions=(f"un desplazamiento a la {'izquierda' if izquierda else 'derecha'} "
                    f"multiplica por 2^{posiciones}",),
        why=("desplazar un bit es multiplicar o dividir por 2, porque el bit que entra o "
             "sale vale 0 y los demás se desplazan una posición"),
    )
    return resultado


def verificar_mascara(direccion: int, prefijo: int, trace: Trace | None = None) -> V.Seal:
    """Second path for :func:`red_ipv4`: rebuild the address from the network.

    ``red OR (host bits)`` must give back the original address, and the host
    count must match ``2^(32−p) − 2`` recomputed independently. If either fails,
    the seal is ``discrepa``.
    """
    r = red_ipv4(direccion, prefijo, trace)
    esperado_hosts = max(2 ** (32 - prefijo) - 2, 0)
    reconstruida = r.red | (direccion & ~r.mascara & 0xFFFFFFFF)
    ok = (reconstruida == direccion) and (r.hosts == esperado_hosts)
    if ok:
        return V.Seal(V.VERIFIED, "dirección reconstruida desde la red",
                      f"{_ipv4(direccion)} recuperada y {r.hosts} hosts confirmados")
    return V.Seal(V.DISCREPANT, "reconstrucción",
                  f"reconstruida {_ipv4(reconstruida)} frente a {_ipv4(direccion)}, "
                  f"hosts {r.hosts} frente a {esperado_hosts}")
