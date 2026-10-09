# SPDX-License-Identifier: MIT
"""El laboratorio de circuitos electrónicos.

Por ahora, **CI-0**: los cimientos de los que dependen todas las fases
siguientes. Tres piezas y ninguna calculadora todavía:

- :mod:`.contrato` — el contrato común de toda calculadora (§14.1): entrada
  con unidades y validación estricta, convención declarada, resultado con
  pasos y motivo, exactitud sin ``float``, segundo camino y rango de validez.
- :mod:`.invariantes` — las nueve invariantes físicas de §20.2, ejecutables
  y con la condición de *no comprobado* explícita.
- :mod:`.canonicos` — el banco de circuitos con solución conocida de §20.4,
  resuelto con un resolutor propio para que la referencia no dependa del
  código que se está probando.

La fase CI-R renombrará ``domain/engineering`` a ``domain/circuits``; este
paquete viaja con ella sin más cambios.
"""

from academic_core.domain.engineering.circuits import canonicos, contrato, invariantes

__all__ = ["contrato", "invariantes", "canonicos"]
