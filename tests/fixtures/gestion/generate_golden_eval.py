# SPDX-License-Identifier: MIT
"""Regenerate tests/fixtures/gestion/golden_eval.json from the REAL
Gestion-Academica implementation (not from AcademicCore's port).

NOT collected by pytest. Requires a checkout of Gestion-Academica@187a614
and its requirements (Flask, Flask-SQLAlchemy, Flask-Migrate) in a separate
virtualenv:

    python generate_golden_eval.py /path/to/gestion-academica out.json

Cases are synthetic and seeded (random.Random(20260923)): no personal data.
"""
import json
import random
import sys
import tempfile
from pathlib import Path


def main(gestion: str, out: str) -> None:
    sys.path.insert(0, gestion)
    from app import create_app
    from models import (Anio, Asignatura, BloqueEvaluacion, ComponenteEvaluacion, Cuatrimestre,
                        EsquemaEvaluacion, calcular_estado_notas, db, esquemas_con_ganador)

    rng = random.Random(20260923)
    tmp = tempfile.mkdtemp()
    app = create_app(auto_seed=False, database_uri=f"sqlite:///{tmp}/g.db",
                     documentos_dir=f"{tmp}/docs")
    cases = []
    weights = [10.0, 15.0, 20.0, 25.0, 30.0, 33.33, 33.34, 40.0, 50.0, 60.0, 66.67, 100.0]
    scores = [None, 0.0, 2.5, 3.9, 4.0, 4.99, 5.0, 5.01, 6.5, 7.25, 8.75, 10.0]
    with app.app_context():
        anio = Anio(numero=1)
        db.session.add(anio)
        db.session.flush()
        cu = Cuatrimestre(anio_id=anio.id, numero=1, estado="actual")
        db.session.add(cu)
        db.session.flush()
        for i in range(400):
            a = Asignatura(cuatrimestre_id=cu.id, nombre=f"S{i}", creditos_ects=6.0,
                           nota_final=rng.choice([None] * 9 + [rng.choice(scores[1:])]))
            db.session.add(a)
            db.session.flush()
            rows = {"asignatura": {"id": a.id, "nota_final": a.nota_final,
                                   "regla_esquemas": "maximo"},
                    "esquemas": [], "bloques": [], "componentes": []}
            for e_i in range(rng.choice([0, 1, 1, 1, 2, 2, 3])):
                e = EsquemaEvaluacion(asignatura_id=a.id, nombre=f"E{e_i}", orden=e_i)
                db.session.add(e)
                db.session.flush()
                rows["esquemas"].append({"id": e.id, "asignatura_id": a.id, "orden": e_i})
                blocks = []
                for b_i in range(rng.choice([0, 0, 1, 2])):
                    b = BloqueEvaluacion(esquema_id=e.id, nombre=f"B{b_i}",
                                         porcentaje=rng.choice(weights[:8]), orden=b_i)
                    db.session.add(b)
                    db.session.flush()
                    blocks.append(b)
                    rows["bloques"].append({"id": b.id, "esquema_id": e.id,
                                            "porcentaje": b.porcentaje, "orden": b_i})
                for c_i in range(rng.choice([1, 2, 3, 4])):
                    b = rng.choice([None] + blocks) if blocks else None
                    c = ComponenteEvaluacion(
                        asignatura_id=a.id, esquema_id=e.id, bloque_id=b.id if b else None,
                        nombre=f"C{c_i}", porcentaje=rng.choice(weights),
                        nota=rng.choice(scores),
                        nota_minima=rng.choice([None, None, None, 4.0, 3.5]), orden=c_i)
                    db.session.add(c)
                    db.session.flush()
                    rows["componentes"].append({
                        "id": c.id, "asignatura_id": a.id, "esquema_id": e.id,
                        "bloque_id": c.bloque_id, "porcentaje": c.porcentaje, "nota": c.nota,
                        "nota_minima": c.nota_minima, "orden": c_i, "tipo": "otro"})
            db.session.commit()
            db.session.refresh(a)
            estado = calcular_estado_notas(a)
            ganador = [e["aplicado"] for e in esquemas_con_ganador(a.esquemas, "maximo")]
            cases.append({"input": rows, "expected": estado, "winner_flags": ganador})
    Path(out).write_text(json.dumps({"source": "Gestion-Academica@187a614 models.py",
                                     "seed": 20260923, "cases": cases}, sort_keys=True,
                                    ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
