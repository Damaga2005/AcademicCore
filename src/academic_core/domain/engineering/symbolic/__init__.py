# SPDX-License-Identifier: MIT
"""E0.1 bounded, rule-based symbolic engine with recorded pedagogical steps.

- ``expr``: exact AST, safe parser, printers
- ``normal``: exact normal form (simplification)
- ``derive``: differentiation
- ``integrate``: indefinite and definite integration
- ``solve``: linear equations
- ``steps``: step log
- ``numeric``: verification through the certified evaluator

Every step is a rule that the engine really applied. If no registered
rule applies, the engine raises ``UnsupportedError NO_RULE``; it never
invents a step.
"""
