# SPDX-License-Identifier: MIT
"""Regenerate tests/fixtures/gestion/golden_syllabus.json from the REAL
Gestion-Academica `guia_docente.analizar_guia_docente`, over the teaching-
guide texts used by Gestion's own tests (tests/test_guia_docente.py) plus a
few extra synthetic texts. NOT collected by pytest; needs the Gestion venv:

    python generate_golden_syllabus.py /path/to/gestion-academica out.json
"""
import ast
import json
import sys
from pathlib import Path

EXTRA = [
    "SISTEMA DE CALIFICACIÓN\nNota final = MAX(0.6*Examen_final + 0.4*Nota_lab, "
    "0.3*Examen_parcial + 0.3*Examen_final + 0.4*Nota_lab)\n"
    "Nota_lab = 0.5*Practicas + 0.5*Control_lab\nBIBLIOGRAFÍA\nLibro\n",
    "PROFESORADO\nProfesorado responsable: Marta Ruiz\nOtros: Marta Ruiz - 10\n"
    "Pau Serra - 11, 12\nCAPACIDADES PREVIAS\nNinguna\n",
    "SISTEMA DE CALIFICACIÓN\nQüestionaris quinzenals 10%\nExamen parcial: 35,5%\n"
    "Examen final: 54,5%\nRECURSOS\nx\n",
]


def main(gestion: str, out: str) -> None:
    sys.path.insert(0, gestion)
    from guia_docente import analizar_guia_docente
    tree = ast.parse(Path(gestion, "tests", "test_guia_docente.py").read_text(encoding="utf-8"))
    texts = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "texto"
                                                  for t in node.targets)
                and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            texts.append(node.value.value)
    cases = [{"text": t, "expected": analizar_guia_docente(t)} for t in texts + EXTRA]
    Path(out).write_text(json.dumps({"source": "Gestion-Academica@187a614 guia_docente.py",
                                     "cases": cases}, ensure_ascii=False, indent=1,
                                    sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
