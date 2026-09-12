"""Engineering persistence: projects, circuits (netlist text), calculations."""

from __future__ import annotations

import json

from academic_core.domain.engineering.circuit import Circuit, EngineeringProject
from academic_core.infrastructure.repositories import IntegrityError


class EngineeringRepository:
    def __init__(self, db):
        self.db = db

    # -- projects ------------------------------------------------------------
    def save_project(self, p: EngineeringProject) -> None:
        cx = self.db.connect()
        cx.execute("INSERT OR REPLACE INTO engineering_projects VALUES (?,?,?,?)",
                   (p.name, p.subject_id, p.topic_id, p.description))
        cx.commit(); cx.close()

    def get_project(self, name: str) -> EngineeringProject | None:
        cx = self.db.connect()
        r = cx.execute("SELECT * FROM engineering_projects WHERE name=?", (name,)).fetchone()
        cx.close()
        if not r:
            return None
        return EngineeringProject(r["name"], r["subject_id"], r["topic_id"], r["description"])

    def list_projects(self) -> list[EngineeringProject]:
        cx = self.db.connect()
        rows = cx.execute("SELECT * FROM engineering_projects ORDER BY name").fetchall()
        cx.close()
        return [EngineeringProject(r["name"], r["subject_id"], r["topic_id"],
                                   r["description"]) for r in rows]

    def delete_project(self, name: str) -> None:
        cx = self.db.connect()
        n = cx.execute("SELECT COUNT(*) FROM circuits WHERE project=?", (name,)).fetchone()[0]
        m = cx.execute("SELECT COUNT(*) FROM calculations WHERE project=?", (name,)).fetchone()[0]
        if n or m:
            cx.close()
            raise IntegrityError(f"cannot delete project {name}: circuits({n}) calculations({m})")
        cx.execute("DELETE FROM engineering_projects WHERE name=?", (name,))
        cx.commit(); cx.close()

    # -- circuits --------------------------------------------------------------
    def save_circuit(self, project: str, circuit: Circuit, notes: str = "") -> None:
        cx = self.db.connect()
        cx.execute("INSERT OR REPLACE INTO circuits(project, name, netlist, notes)"
                   " VALUES (?,?,?,?)",
                   (project, circuit.name, circuit.to_netlist(), notes))
        cx.commit(); cx.close()

    def load_circuit(self, project: str, name: str) -> Circuit | None:
        cx = self.db.connect()
        r = cx.execute("SELECT netlist FROM circuits WHERE project=? AND name=?",
                       (project, name)).fetchone()
        cx.close()
        if not r:
            return None
        return Circuit.from_netlist(r["netlist"], name)

    def circuits_of(self, project: str) -> list[str]:
        cx = self.db.connect()
        rows = cx.execute("SELECT name FROM circuits WHERE project=? ORDER BY name",
                          (project,)).fetchall(); cx.close()
        return [r["name"] for r in rows]

    def delete_circuit(self, project: str, name: str) -> None:
        cx = self.db.connect()
        cx.execute("DELETE FROM circuits WHERE project=? AND name=?", (project, name))
        cx.commit(); cx.close()

    # -- calculations ------------------------------------------------------------
    def save_calculation(self, result, project: str = "", circuit: str = "") -> None:
        cx = self.db.connect()
        cx.execute("INSERT OR REPLACE INTO calculations VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (result.digest, project, circuit, result.name,
                    result.equation_source, json.dumps(result.inputs),
                    str(result.value.value), result.value.unit.display,
                    result.engine, result.timestamp))
        cx.commit(); cx.close()

    def calculations_of(self, project: str) -> list[dict]:
        cx = self.db.connect()
        rows = cx.execute("SELECT * FROM calculations WHERE project=? ORDER BY timestamp",
                          (project,)).fetchall(); cx.close()
        return [dict(r) for r in rows]

    def get_calculation(self, digest: str) -> dict | None:
        cx = self.db.connect()
        r = cx.execute("SELECT * FROM calculations WHERE digest=?", (digest,)).fetchone()
        cx.close()
        return dict(r) if r else None
