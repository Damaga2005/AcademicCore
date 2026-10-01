# Laboratorios: especificaciones de diseño

Especificaciones de los laboratorios de la aplicación. Son **documentos de
diseño**, no código: describen qué resuelve cada calculadora, qué pasos muestra,
cómo se verifica cada resultado y en qué fases se entrega. La implementación
vive en `src/academic_core/domain/engineering/`.

| Documento | Laboratorio | Estado de la implementación |
|---|---|---|
| `MATH_LAB.md` | Matemáticas (20 bloques, 23 fases ML-0 … ML-22) | **ML-0 completa**, ML-1 en curso — ver [`MATH_LAB_ML0.md`](../architecture/MATH_LAB_ML0.md) |
| `SIGNALS_LAB.md` | Señales y sistemas | Sin implementar |
| `CIRCUITS_LAB.md` | Circuitos y dispositivos | Sin implementar (`_CIRCUITS_BRIEF.md` es el resumen ejecutivo) |
| `DIGITAL_DESIGN_LAB.md` | Diseño digital y álgebra de Boole | En curso |
| `AEROSPACE_LAB.md` | Espacial y telemetría | Sin implementar |

## Cómo se relacionan

Las especificaciones se cruzan entre sí a propósito, y el reparto está escrito
en `MATH_LAB.md` §16 («qué va dónde»). La regla que lo gobierna:

> **El laboratorio de matemáticas ofrece la capa matemática genérica; los demás
> laboratorios no aportan modelos a cambio.** La dependencia va
> `digital → math`, `signals → math`, `circuits → math`. Nunca al revés.

Para que eso no se rompa, el motor de matemáticas expone el contrato estable de
`MATH_LAB.md` §5.9 (`mathlab.contract.calcular`) y acepta que otro laboratorio
registre su motor como **plug-in de verificación**. La puerta de arquitectura
está en `tests/test_mathlab_arch.py`: si un módulo de `mathlab` llegara a
importar `dsp`, `ac`, `rf` o cualquier otro laboratorio, la prueba falla.

## Dos reglas que atraviesan todas las especificaciones

1. **Nada se muestra como correcto sin un segundo camino independiente**
   (`MATH_LAB.md` §5.3). Un resultado que no se puede comprobar lleva un sello
   `⚠ Solo numérico`, y uno que se contradice lleva `✘ Discrepa`.
2. **La honestidad por encima de la respuesta** (§5.4). Si el motor no sabe
   resolver algo de forma exacta, lo dice y ofrece el valor numérico con su
   error acotado. Nunca redondea un resultado a una fracción «exacta» que no
   sale del cálculo.

## Fases

El orden de entrega de cada laboratorio está en su propio §10. El de matemáticas
es el único con una fase terminada, y su documento de estado es
[`docs/architecture/MATH_LAB_ML0.md`](../architecture/MATH_LAB_ML0.md), que
incluye también la lista explícita de lo que **no** existe todavía.
