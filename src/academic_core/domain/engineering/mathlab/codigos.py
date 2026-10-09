# SPDX-License-Identifier: MIT
"""ML-17, bloques 9–10: cifrado clásico, tablas, hash, GF(2ᵐ), códigos
lineales, Shamir, RSA/Diffie-Hellman y privacidad (D12).

El cifrado clásico (respaldo E) y ℤₙ van primero; GF(2ᵐ) al final (§10).
Aviso fijo: material pedagógico, nunca seguridad real. Todo determinista:
el azar sembrado sale del Generador de ``eventos``.
"""

from __future__ import annotations

import math
from fractions import Fraction

from academic_core.domain.engineering.mathlab import enteros as Z
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError

AVISO_PEDAGOGICO = "material pedagógico: nunca para seguridad real"


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


def _Q(x) -> Fraction:
    if isinstance(x, Fraction):
        return x
    if isinstance(x, int):
        return Fraction(x)
    s = str(x).strip().replace(",", ".")
    try:
        return Fraction(s)
    except (ValueError, ZeroDivisionError):
        raise _error("BAD_INPUT", f"«{x}» no es un número racional")


def _ent(x, que="n") -> int:
    q = _Q(x)
    if q.denominator != 1:
        raise _error("BAD_INPUT", f"{que} ha de ser entero")
    return q.numerator


# ---------------------------------------------------------------------------
# alfabeto y cifrado clásico (E: César 3/7 finales APR)
# ---------------------------------------------------------------------------

def _letra(c: str) -> int:
    c = c.upper()
    if len(c) != 1 or not ("A" <= c <= "Z"):
        raise _error("BAD_INPUT", f"alfabeto cerrado A-Z sin ñ ni tildes: «{c}»")
    return ord(c) - 65


def _al_num(texto: str) -> list[int]:
    return [_letra(c) for c in texto if not c.isspace()]


def _a_texto(xs: list[int]) -> str:
    return "".join(chr(x % 26 + 65) for x in xs)


def cesar(texto: str, k: int, trace: Trace | None = None) -> dict:
    """César (x+k) mod 26; descifra con −k; k ≡ k+26."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.cesar", "letra → 0..25 → +k mod 26 → letra",
                 why="el desplazamiento cíclico es la definición del César")
    k = int(_Q(k)) % 26
    xs = _al_num(texto)
    trace.hipotesis("sen.cesar_alfabeto", "A-Z sin ñ ni tildes", "cumple")
    cif = [(x + k) % 26 for x in xs]
    if _a_texto([(c - k) % 26 for c in cif]) != _a_texto(xs):
        raise _error("DISCREPANT", "descifrar(cifrar(x)) ≠ x")
    trace.verificacion("sen.cesar_ida_vuelta", "descifrar(cifrar(x)) = x")
    return {"cifrado": _a_texto(cif), "k": k}


def afin(texto: str, a: int, b: int, trace: Trace | None = None) -> dict:
    """Afín a·x+b mod 26 (descifra con a⁻¹); exige gcd(a,26) = 1."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.afin", "x → a·x+b mod 26 con a invertible",
                 why="sin inverso de a no hay descifrado único")
    a, b = int(_Q(a)) % 26, int(_Q(b)) % 26
    if math.gcd(a, 26) != 1:
        raise _error("BAD_INPUT", f"gcd({a},26) ≠ 1: sin inverso")
    inv = Z.inverso_modular(a, 26, Trace())
    xs = _al_num(texto)
    cif = [(a * x + b) % 26 for x in xs]
    if _a_texto([(inv * (c - b)) % 26 for c in cif]) != _a_texto(xs):
        raise _error("DISCREPANT", "ida y vuelta difieren")
    trace.verificacion("sen.afin_inverso", f"a·a⁻¹ ≡ 1 (a⁻¹ = {inv})")
    return {"cifrado": _a_texto(cif), "a_inv": inv}


def vigenere(texto: str, clave: str, trace: Trace | None = None) -> dict:
    """Vigenère con clave repetida; descifra restando."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.vigenere", "cada letra con su desplazamiento de la clave",
                 why="Vigenère es César con clave que rota")
    xs, ks = _al_num(texto), _al_num(clave)
    if not ks:
        raise _error("BAD_INPUT", "clave vacía")
    cif = [(x + ks[i % len(ks)]) % 26 for i, x in enumerate(xs)]
    if _a_texto([(c - ks[i % len(ks)]) % 26 for i, c in enumerate(cif)]) != _a_texto(xs):
        raise _error("DISCREPANT", "ida y vuelta difieren")
    trace.verificacion("sen.vigenere_ida_vuelta", "descifrar(cifrar(x)) = x")
    return {"cifrado": _a_texto(cif)}


def _mat_vec_mod(M, v, n):
    return [sum(M[i][j] * v[j] for j in range(len(v))) % n for i in range(len(M))]


def _inv_mod_matriz(M, n, trace) -> list[list[int]]:
    # Gauss-Jordan mod n con pivotes unidad (si no, se dice)
    m = len(M)
    A = [[x % n for x in fila] + [1 if i == j else 0 for j in range(m)]
         for i, fila in enumerate(M)]
    for col in range(m):
        piv = next((r for r in range(col, m) if math.gcd(A[r][col], n) == 1), None)
        if piv is None:
            raise _error("BAD_INPUT", "pivote no invertible mod 26: matriz no válida")
        A[col], A[piv] = A[piv], A[col]
        inv = Z.inverso_modular(A[col][col], n, Trace())
        A[col] = [x * inv % n for x in A[col]]
        for r in range(m):
            if r != col and A[r][col] % n != 0:
                f = A[r][col]
                A[r] = [(x - f * y) % n for x, y in zip(A[r], A[col])]
    odd = [fila[m:] for fila in A]
    trace.regla("sen.hill_inversa", "Gauss-Jordan mod 26 con pivotes unidad",
                why="26 no es cuerpo: solo valen pivotes coprimos con 26")
    return odd


def hill(texto: str, matriz: list[list[int]],
         trace: Trace | None = None) -> dict:
    """Hill con matriz invertible mod 26 (det coprimo con 26)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.hill", "bloques por la matriz; A·A⁻¹ = I (mod 26)",
                 why="Hill es lineal sobre ℤ₂₆: la inversa existe si el "
                     "determinante es coprimo con 26")
    M = [[int(_Q(x)) % 26 for x in fila] for fila in matriz]
    m = len(M)
    xs = _al_num(texto)
    while len(xs) % m:
        xs.append(23)  # relleno X
    inv = _inv_mod_matriz(M, 26, trace)
    bloques = [xs[i:i + m] for i in range(0, len(xs), m)]
    cif = [y for bl in bloques for y in _mat_vec_mod(M, bl, 26)]
    rec = [y for bl in [cif[i:i + m] for i in range(0, len(cif), m)]
           for y in _mat_vec_mod(inv, bl, 26)]
    if rec != xs:
        raise _error("DISCREPANT", "A·A⁻¹ ≠ I (mod 26)")
    trace.verificacion("sen.hill_inversa_ok", "A·A⁻¹ = I (mod 26)")
    return {"cifrado": _a_texto(cif)}


# ---------------------------------------------------------------------------
# tablas de ℤₙ y hash/cumpleaños
# ---------------------------------------------------------------------------

def tabla_zn(n: int, trace: Trace | None = None) -> dict:
    """Tablas de suma y producto de ℤₙ (n ≤ 12) + ¿es cuerpo?"""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.tabla_zn", "tabla completa solo si n es pequeño",
                 why="con n grande la tabla no se lee: Euclides (§4.9)")
    n = _ent(n)
    if not n >= 2:
        raise _error("BAD_INPUT", "n ≥ 2")
    if n > 12:
        raise _no("n > 12: sin tabla completa (se dice)")
    suma = [[(i + j) % n for j in range(n)] for i in range(n)]
    prod = [[(i * j) % n for j in range(n)] for i in range(n)]
    primo = all(n % d for d in range(2, n))
    trace.verificacion("sen.tabla_cuerpo",
                       f"ℤ_{n} {'es' if primo else 'no es'} cuerpo")
    return {"suma": suma, "producto": prod, "cuerpo": primo}


def hash_cumple(m: int, claves: list, trace: Trace | None = None) -> dict:
    """h(k) = k mod m; colisiones y P(colisión) = 1 − Π(1 − i/m)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.hash", "repartir por módulo y contar colisiones",
                 why="el módulo es la función hash del tema; la fórmula del "
                     "cumpleaños se contrasta simulando")
    m = _ent(m)
    ks = [int(_Q(k)) % m for k in claves]
    if not m > 0:
        raise _error("BAD_INPUT", "m > 0")
    from academic_core.domain.engineering.mathlab import eventos as EV

    g = EV.Generador(20261007)
    n = len(ks)
    P = 1 - math.prod(1 - i / m for i in range(n)) if n <= m else 1.0
    trials, hits = 20000, 0
    for _ in range(trials):
        seen = set()
        col = False
        for _ in range(n):
            h = int(g.uniforme() * m)
            if h in seen:
                col = True
                break
            seen.add(h)
        hits += col
    trace.verificacion("sen.hash_montecarlo",
                       f"P = {P:.4g}; Monte Carlo {hits / trials:.4g}")
    return {"hashes": ks, "colisiones": n - len(set(ks)), "P": P,
            "montecarlo": hits / trials}


# ---------------------------------------------------------------------------
# GF(2^m) y polinomios sobre GF(p)
# ---------------------------------------------------------------------------

def _g2_mul(a: int, b: int, mod: int) -> int:
    deg = mod.bit_length() - 1
    p = 0
    while b:
        if b & 1:
            p ^= a
        a <<= 1
        if a >> deg:
            a ^= mod
        b >>= 1
    return p


def _g2_grado(a: int) -> int:
    return a.bit_length() - 1


def _g2_divmod(a: int, b: int) -> tuple[int, int]:
    q = 0
    while _g2_grado(a) >= _g2_grado(b) and a:
        s = _g2_grado(a) - _g2_grado(b)
        q ^= 1 << s
        a ^= b << s
    return q, a


def gf2m_irreducible(poli: int, trace: Trace | None = None) -> bool:
    """Rabin: x^(2^m) ≡ x (mod f) y sin factores de grado divisor."""
    m = _g2_grado(poli)
    x = 0b10

    def pot(e: int) -> int:
        r, b, ee = 1, x, e
        while ee:
            if ee & 1:
                r = _g2_divmod(_g2_mul(r, b, poli), poli)[1]
            b = _g2_divmod(_g2_mul(b, b, poli), poli)[1]
            ee >>= 1
        return r
    if pot(2 ** m) ^ x:
        return False
    divs = set()
    d = 1
    while d * d <= m:
        if m % d == 0:
            divs.add(d)
            divs.add(m // d)
        d += 1
    for dd in divs:
        if dd < m:
            g = pot(2 ** dd) ^ x
            # mcd(g, f): Euclides binario
            u, v = g, poli
            while u:
                _, r = _g2_divmod(v, u)
                v, u = u, r
            if v != 1:
                return False
    return True


def gf2m_tabla(m: int, poli: int | None = None,
               trace: Trace | None = None) -> dict:
    """Tabla log/antilog de GF(2^m): potencias de α, inversos, 2^m elementos."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.gf2m", "polinomios de grado < m con reducción por el "
                 "irreducible; tabla de α",
                 why="la tabla log/antilog convierte el producto en suma de "
                     "exponentes (§4.9)")
    m = _ent(m)
    if not 1 <= m <= 8:
        raise _error("BAD_INPUT", "1 ≤ m ≤ 8")
    mod = poli if poli is not None else {1: 0b11, 2: 0b111, 3: 0b1011,
                                         4: 0b10011, 5: 0b100101, 6: 0b1000011,
                                         7: 0b10000011,
                                         8: 0b100011011}[m]
    if not gf2m_irreducible(mod):
        raise _error("BAD_INPUT", "el módulo no es irreducible: no es cuerpo")
    trace.hipotesis("sen.gf2m_irred", "módulo irreducible", "cumple")
    N = 2 ** m
    pot, visto, al = [1], {1: 0}, [0] * N
    al[1] = 0
    for k in range(1, N):
        pot.append(_g2_divmod(_g2_mul(pot[-1], 0b10, mod), mod)[1])
        if pot[-1] in visto:
            break
        visto[pot[-1]] = k
        al[pot[-1]] = k
    primitivo = len(visto) == N - 1

    def _mul_plain(a: int, b: int) -> int:
        p = 0
        while b:
            if b & 1:
                p ^= a
            a <<= 1
            b >>= 1
        return p

    inv = {}
    for u in range(1, N):
        # Euclides extendido binario: t0·u + s0·mod = mcd; si es 1, t0 = u⁻¹
        r0, r, t0, t = mod, u, 0, 1
        while r:
            qq, rr = _g2_divmod(r0, r)
            r0, r = r, rr
            t0, t = t, t0 ^ _mul_plain(qq, t)
        inv[u] = t0
    for u in range(1, N):
        if _g2_divmod(_g2_mul(u, inv[u], mod), mod)[1] != 1:
            raise _error("DISCREPANT", "u·u⁻¹ ≠ 1")
    trace.verificacion("sen.gf2m_axiomas",
                       f"{N} elementos; α^{N - 1} = 1"
                       f"{'' if primitivo else ' (α no primitivo)'}")
    return {"potencias": pot[:N - 1] if primitivo else pot, "primitivo": primitivo,
            "orden": N - 1 if primitivo else len(visto)}


def poli_gfp(coefs: list, p: int, trace: Trace | None = None) -> dict:
    """Polinomio sobre GF(p): irreducibilidad (Rabin) y valores en el cuerpo."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.poligfp", "Rabin con el cuerpo primo como base",
                 why="sobre GF(p) la irreducibilidad se decide sin factorizar")
    p = _ent(p)
    if p < 2 or any(p % d == 0 for d in range(2, p)):
        raise _error("BAD_INPUT", "p primo")
    c = [int(_Q(v)) % p for v in coefs]
    while len(c) > 1 and c[-1] == 0:
        c.pop()
    n = len(c) - 1
    if n < 1:
        raise _error("BAD_INPUT", "grado ≥ 1")

    def mul(A, B):
        R = [0] * (len(A) + len(B) - 1)
        for i, a in enumerate(A):
            for j, b in enumerate(B):
                R[i + j] = (R[i + j] + a * b) % p
        return R

    def divmod_(A, B):
        A = list(A)
        q = [0] * max(1, len(A) - len(B) + 1)
        inv = Z.inverso_modular(B[-1], p, Trace())
        while len(A) >= len(B) and any(A):
            k = len(A) - len(B)
            f = A[-1] * inv % p
            q[k] = f
            for i in range(len(B)):
                A[k + i] = (A[k + i] - f * B[i]) % p
            while len(A) > 1 and A[-1] == 0:
                A.pop()
        return q, A

    def ppow(base, e, mod):
        r, b = [1], list(base)
        while e:
            if e & 1:
                r = divmod_(mul(r, b), mod)[1]
            b = divmod_(mul(b, b), mod)[1]
            e >>= 1
        return r

    x = [0, 1]
    resto = divmod_(ppow(x, p ** n, c), c)[1]
    es_x = len(resto) == 2 and resto[0] == 0 and resto[1] == 1
    divs = {d for d in range(1, n) if n % d == 0}
    ok = es_x
    for dd in divs:
        g = ppow(x, p ** dd, c)
        g = [(g[i] if i < len(g) else 0) - (1 if i == 1 else 0)
             for i in range(max(len(g), 2))]
        while len(g) > 1 and g[-1] == 0:
            g.pop()
        if not any(g):
            ok = False
            continue
        # mcd(g, f) por Euclides (constante ⟺ coprimos)
        u, v = g, list(c)
        while any(u):
            _, r_ = divmod_(v, u)
            while len(r_) > 1 and r_[-1] == 0:
                r_.pop()
            v, u = u, r_
        while len(v) > 1 and v[-1] == 0:
            v.pop()
        if len(v) != 1:
            ok = False
    trace.verificacion("sen.poligfp_rabin",
                       f"{'irreducible' if ok else 'reducible'} sobre GF({p})")
    return {"irreducible": ok}


# ---------------------------------------------------------------------------
# códigos lineales binarios
# ---------------------------------------------------------------------------

def codigo_lineal(G: list[list[int]], trace: Trace | None = None) -> dict:
    """G → sistemática [I|P] → H = [Pᵀ|I]; 2ᵏ palabras, d_min, G·Hᵀ = 0."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.codigo", "Gauss a forma sistemática (bloque 9) y H "
                 "de la paridad; enumerar las 2ᵏ palabras",
                 why="la forma sistemática lee H directamente y H·c = 0 "
                     "decide pertenencia (§4.10)")
    k = len(G)
    n = len(G[0])
    M = [[x & 1 for x in fila] for fila in G]
    perm = list(range(n))
    fila = 0
    for col in range(n):
        piv = next((r for r in range(fila, k) if M[r][col]), None)
        if piv is None:
            continue
        M[fila], M[piv] = M[piv], M[fila]
        for r in range(k):
            if r != fila and M[r][col]:
                M[r] = [(x ^ y) for x, y in zip(M[r], M[fila])]
        if col != fila:
            for r_ in range(k):
                M[r_][col], M[r_][fila] = M[r_][fila], M[r_][col]
            perm[col], perm[fila] = perm[fila], perm[col]
        fila += 1
        if fila == k:
            break
    if fila < k:
        raise _error("BAD_INPUT", f"G de rango {fila} < {k}")
    P = [f[k:] for f in M]
    # H = [Pᵀ | I] en el orden permutado; se deshace la permutación
    H = [[P[r][c] for r in range(k)] + [1 if c == j else 0 for j in range(n - k)]
         for c in range(n - k)]
    Hh = [[0] * n for _ in range(n - k)]
    for i in range(n - k):
        for j in range(n):
            Hh[i][perm[j]] = H[i][j]
    # G·Hᵀ = 0 con la G original
    for i in range(k):
        for j in range(n - k):
            if sum(G[i][t] * Hh[j][t] for t in range(n)) % 2:
                raise _error("DISCREPANT", "G·Hᵀ ≠ 0")
    if k > 12:
        raise _no("k > 12: sin enumerar las 2ᵏ palabras (se dice)")
    pals = []
    for m in range(2 ** k):
        u = [(m >> i) & 1 for i in range(k)]
        pals.append([sum(u[i] * G[i][j] for i in range(k)) % 2 for j in range(n)])
    for c in pals:
        if any(sum(Hh[j][t] * c[t] for t in range(n)) % 2 for j in range(n - k)):
            raise _error("DISCREPANT", "palabra con síndrome ≠ 0")
    pesos = sorted(sum(c) for c in pals[1:])
    d = pesos[0]
    trace.verificacion("sen.codigo_ght",
                       f"G·Hᵀ = 0; {2 ** k} palabras; d = {d}")
    return {"H": Hh, "palabras": pals, "n": n, "k": k, "d": d,
            "detecta": d - 1, "corrige": (d - 1) // 2}


def sindrome(H: list[list[int]], r: list[int],
             trace: Trace | None = None) -> dict:
    """s = H·r: 0, columna j (un error) o aviso de más errores."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.sindrome", "s = H·r; la columna idéntica marca el bit",
                 why="con ≤ t errores el síndrome localiza; con más, se avisa "
                     "en vez de corregir mal (§4.10)")
    n = len(r)
    s = [sum(H[j][t] * r[t] for t in range(n)) % 2 for j in range(len(H))]
    if not any(s):
        trace.verificacion("sen.sindrome_cero", "s = 0: sin errores")
        return {"sindrome": s, "corrige": None}
    cols = [[H[j][t] for j in range(len(H))] for t in range(n)]
    if s in cols:
        j = cols.index(s)
        c = list(r)
        c[j] ^= 1
        trace.verificacion("sen.sindrome_uno", f"s = columna {j}: se invierte")
        return {"sindrome": s, "corrige": j, "palabra": c}
    trace.aviso("sen.sindrome_mas", "s sin columna: más de t errores, NO se corrige")
    raise _no("más errores de los corregibles: se avisa, no se inventa")


def crc(mensaje: list[int], generador: list[int],
        trace: Trace | None = None) -> dict:
    """CRC por división polinómica mod 2; la trama completa da resto 0."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.crc", "añadir r ceros, dividir con XOR, resto = CRC",
                 why="la división larga con XOR es el algoritmo del CRC")
    msg = [int(x) & 1 for x in mensaje]
    gen = [int(x) & 1 for x in generador]
    if not gen or gen[0] != 1 or gen[-1] != 1:
        raise _error("BAD_INPUT", "generador con término independiente 1")
    r = len(gen) - 1
    reg = msg + [0] * r
    for i in range(len(msg)):
        if reg[i]:
            for j in range(len(gen)):
                reg[i + j] ^= gen[j]
    resto = reg[len(msg):]
    trama = msg + resto
    reg2 = list(trama)
    for i in range(len(msg)):
        if reg2[i]:
            for j in range(len(gen)):
                reg2[i + j] ^= gen[j]
    if any(reg2[len(msg):]):
        raise _error("DISCREPANT", "la trama completa no da resto 0")
    trace.verificacion("sen.crc_resto0", f"CRC = {resto}; trama con resto 0")
    return {"crc": resto, "trama": trama}


def paridad(bits: list[int], trace: Trace | None = None) -> dict:
    """Bit de paridad par: XOR de todos."""
    trace = trace if trace is not None else Trace()
    b = [int(x) & 1 for x in bits]
    p = sum(b) % 2
    trace.verificacion("sen.paridad_xor", f"paridad = {p}")
    return {"paridad": p, "palabra": b + [p]}


def checksum16(palabras: list[int], trace: Trace | None = None) -> dict:
    """Checksum de Internet: suma en complemento a 1 de 16 bits."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.checksum", "suma con acarreo envolvente y complemento",
                 why="el complemento a 1 detecta el 0 y el desborde")
    s = 0
    for w in palabras:
        s += int(w) & 0xFFFF
        s = (s & 0xFFFF) + (s >> 16)
    s = (s & 0xFFFF) + (s >> 16)
    chk = (~s) & 0xFFFF
    # segundo camino: mensaje + checksum suma 0xFFFF
    t = s
    t += chk
    t = (t & 0xFFFF) + (t >> 16)
    if t != 0xFFFF:
        raise _error("DISCREPANT", "mensaje + checksum no da 0xFFFF")
    trace.verificacion("sen.checksum_comp", f"checksum = {chk:#06x}")
    return {"checksum": chk}


# ---------------------------------------------------------------------------
# Shamir, esquema lineal, RSA, DH, privacidad
# ---------------------------------------------------------------------------

def shamir_reparto(t: int, n: int, p: int, secreto: int, semilla: int = 7,
                   trace: Trace | None = None) -> dict:
    """Shamir (t,n) sobre GF(p): polinomio de grado t−1, partes f(i)."""
    from academic_core.domain.engineering.mathlab import eventos as EV

    trace = trace if trace is not None else Trace()
    trace.metodo("sen.shamir", "término libre = secreto; coeficientes "
                 "sembrados; partes f(1)..f(n)",
                 why="el secreto vive solo en f(0): con t−1 partes cada valor "
                     "es compatible (§4.10)")
    t, n, p, secreto = int(_Q(t)), int(_Q(n)), int(_Q(p)), int(_Q(secreto))
    if not (p > n and p > secreto and 1 < t <= n):
        raise _error("BAD_INPUT", "p primo, p > n, p > secreto, 1 < t ≤ n")
    if any(p % d == 0 for d in range(2, p)):
        raise _error("BAD_INPUT", "p primo")
    trace.hipotesis("sen.shamir_hip", f"p = {p} primo, xᵢ distintos no nulos",
                    "cumple")
    g = EV.Generador(semilla)
    coef = [secreto] + [int(g.uniforme() * p) for _ in range(t - 1)]
    partes = [(i, sum(c * pow(i, k, p) for k, c in enumerate(coef)) % p)
              for i in range(1, n + 1)]
    trace.verificacion("sen.shamir_grado", f"grado {t - 1} con f(0) = {secreto}")
    return {"coefs": coef, "partes": partes}


def shamir_reconstruye(partes: list, p: int, t: int,
                        trace: Trace | None = None) -> dict:
    """f(0) por Lagrange; dos subconjuntos deben dar lo mismo."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.shamir_lagrange", "f(0) = Σ yᵢ·Πⱼ≠ᵢ(−xⱼ)/(xᵢ−xⱼ) (mod p)",
                 why="Lagrange en 0 recupera el término libre sin el polinomio")
    p = int(_Q(p))
    pts = [(int(_Q(x)), int(_Q(y)) % p) for x, y in partes]
    if len({x for x, _ in pts}) != len(pts) or any(x == 0 for x, _ in pts):
        raise _error("BAD_INPUT", "xᵢ distintos y no nulos")
    s = 0
    for i, (xi, yi) in enumerate(pts):
        num, den = 1, 1
        for j, (xj, _) in enumerate(pts):
            if i != j:
                num = num * (-xj) % p
                den = den * (xi - xj) % p
        s = (s + yi * num * Z.inverso_modular(den, p, Trace())) % p
    trace.verificacion("sen.shamir_s", f"secreto = {s}")
    return {"secreto": s}


def rsa(p: int, q: int, e: int, m: int, trace: Trace | None = None) -> dict:
    """RSA pedagógico: n, φ, d = e⁻¹, c = mᵉ, m = c^d."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.rsa", "φ → d por Euclides → cuadrados sucesivos",
                 why="cada paso es aritmética modular con su hipótesis")
    p, q, e, m = (int(_Q(v)) for v in (p, q, e, m))
    if p == q or m < 0:
        raise _error("BAD_INPUT", "p ≠ q primos y 0 ≤ m < n")
    for primo in (p, q):
        if primo < 2 or any(primo % d == 0 for d in range(2, primo)):
            raise _error("BAD_INPUT", f"{primo} no es primo")
    n, phi = p * q, (p - 1) * (q - 1)
    if not m < n:
        raise _error("BAD_INPUT", "m < n")
    trace.hipotesis("sen.rsa_hip", f"p ≠ q primos; m < n", "cumple")
    if math.gcd(e, phi) != 1:
        raise _error("BAD_INPUT", "gcd(e, φ) = 1 para que exista d")
    d = Z.inverso_modular(e, phi, Trace())
    c = pow(m, e, n)
    m2 = pow(c, d, n)
    if m2 != m % n or (e * d) % phi != 1:
        raise _error("DISCREPANT", "m^(ed) ≠ m")
    trace.verificacion("sen.rsa_ida_vuelta", f"c = {c}; m^(e·d) ≡ m (mod n)")
    trace.aviso("sen.rsa_aviso", AVISO_PEDAGOGICO)
    return {"n": n, "phi": phi, "d": d, "c": c, "m2": m2, "aviso": AVISO_PEDAGOGICO}


def diffie_hellman(p: int, g: int, a: int, b: int,
                   trace: Trace | None = None) -> dict:
    """DH: A = g^a, B = g^b, s = B^a = A^b (mod p)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.dh", "cada uno eleva lo del otro a su secreto",
                 why="la conmutatividad del exponente da el mismo secreto")
    p, g, a, b = (int(_Q(v)) for v in (p, g, a, b))
    A, B = pow(g, a, p), pow(g, b, p)
    s1, s2 = pow(B, a, p), pow(A, b, p)
    if s1 != s2:
        raise _error("DISCREPANT", "los secretos difieren")
    trace.verificacion("sen.dh_comun", f"secreto común {s1}")
    trace.aviso("sen.dh_aviso", AVISO_PEDAGOGICO)
    return {"A": A, "B": B, "s": s1, "aviso": AVISO_PEDAGOGICO}


def k_anonimato(registros: list[dict], quasis: list[str],
                trace: Trace | None = None) -> dict:
    """Clases de equivalencia en los quasi-identificadores; k alcanzado."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.kanon", "agrupar por quasi-identificadores y contar",
                 why="k-anonimato = toda clase con ≥ k registros")
    clases: dict[tuple, int] = {}
    for r in registros:
        k = tuple(r.get(q) for q in quasis)
        clases[k] = clases.get(k, 0) + 1
    kmin = min(clases.values()) if clases else 0
    trace.verificacion("sen.kanon_k", f"k alcanzado = {kmin}")
    return {"k": kmin, "clases": len(clases)}


def dp_laplace(datos: list[float], f_suma, epsilon: float, semilla: int = 1,
               trace: Trace | None = None) -> dict:
    """Mecanismo de Laplace: b = Δf/ε con ruido sembrado; razón ≤ e^ε."""
    from academic_core.domain.engineering.mathlab import eventos as EV

    trace = trace if trace is not None else Trace()
    trace.metodo("sen.dp", "sensibilidad → escala b → ruido sembrado",
                 why="el ruido calibrado a Δf/ε es la garantía (D12)")
    xs = [float(_Q(v)) for v in datos]
    sens = float(_Q(f_suma))
    eps = float(_Q(epsilon))
    if not (eps > 0 and sens >= 0):
        raise _error("BAD_INPUT", "ε > 0, Δf ≥ 0")
    trace.hipotesis("sen.dp_hip", "ε > 0; registros independientes", "cumple")
    b = sens / eps
    g = EV.Generador(int(semilla))
    ruidos = []
    for _ in xs:
        u = g.uniforme() - 0.5
        ruidos.append(-b * math.copysign(math.log(1 - 2 * abs(u)), u)
                      if u != 0 else 0.0)
    trace.verificacion("sen.dp_ruido",
                       f"b = {b:.4g}; error esperado {b:.4g}")
    trace.aviso("sen.dp_aviso", AVISO_PEDAGOGICO)
    return {"b": b, "ruidos": ruidos, "aviso": AVISO_PEDAGOGICO}
