# SPDX-License-Identifier: MIT
"""F4.1 closure: certification harness for a REAL Gestion-Academica install.

Runs every check the F4.1 certification gate requires against the user's
own ``academico.db`` + ``documentos/`` and writes an anonymized, reproducible
JSON report (no names, e-mails, file names or free text: only counts,
stable ids, hashes and legacy numeric ids).

    python -m academic_core.application.gestion_certification \\
        --source <gestion>/academico.db --documents <gestion>/documentos \\
        --work <empty dir> --out F4.1_REAL_CERTIFICATION.json

The source is never written: the DB is opened read-only by the migrator and
its SHA-256 (plus a manifest hash of every document file) is compared
before/after. All AcademicCore writes go to fresh targets under ``--work``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

from academic_core.application.gestion_migration import MigrationOptions
from academic_core.application.gestion_oracle import gestion_estado_notas
from academic_core.domain import career as CR
from academic_core.domain import course_material as CM
from academic_core.infrastructure.legacy_gestion import (
    SOURCE_SYSTEM, TABLES, LegacyGestionSource, resolve_document,
)

CERT_SCHEMA = "f4.1-real-certification/1"
SEEDS = ("0", "11", "2024", "random")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with Path(p).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def documents_manifest(root: str | Path | None) -> dict:
    """Hash of (relative path, size, sha256) for every file under root."""
    if not root or not Path(root).is_dir():
        return {"files": 0, "bytes": 0, "digest": ""}
    base = Path(root)
    h = hashlib.sha256()
    n = size = 0
    for p in sorted(x for x in base.rglob("*") if x.is_file() and not x.is_symlink()):
        st = p.stat()
        h.update(f"{p.relative_to(base).as_posix()}\0{st.st_size}\0{sha256_file(p)}\n"
                 .encode("utf-8"))
        n += 1
        size += st.st_size
    return {"files": n, "bytes": size, "digest": h.hexdigest()}


def _app(data_dir: Path):
    from academic_core.application.facade import AcademicApp
    from academic_core.config import Settings
    os.environ["ACORE_DATA_DIR"] = str(data_dir)
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    return core


def _check(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def _dec(v) -> str | None:
    return None if v is None else str(v)


class Certifier:
    def __init__(self, source: str | Path, documents: str | Path | None, work: str | Path,
                 options: MigrationOptions | None = None):
        self.source = Path(source)
        self.documents = Path(documents) if documents else None
        self.work = Path(work)
        self.opts = options or MigrationOptions()
        if self.documents:
            self.opts.documents_dir = str(self.documents)
        self.report: dict = {"schema": CERT_SCHEMA, "criteria": {}}
        self.timings: dict[str, float] = {}

    # ------------------------------------------------------------- helpers
    def _t(self, key: str, fn):
        t = time.perf_counter()
        out = fn()
        self.timings[key] = round(time.perf_counter() - t, 4)
        return out

    def _crit(self, name: str, ok: bool, evidence) -> None:
        self.report["criteria"][name] = {"result": _check(ok), "evidence": evidence}

    # ---------------------------------------------------------------- run
    def run(self, *, seeds: tuple[str, ...] = SEEDS, today: date | None = None) -> dict:
        self.work.mkdir(parents=True, exist_ok=True)
        if any(self.work.iterdir()):
            raise ValueError("work directory must be empty")
        today = today or date.today()
        src_before = sha256_file(self.source)
        docs_before = documents_manifest(self.documents)
        snap = LegacyGestionSource(self.source).read()
        rows = snap.tables
        self.report["source"] = {"revision": snap.revision, "db_sha256": src_before,
                                 "db_bytes": self.source.stat().st_size,
                                 "documents": docs_before, "data_digest": snap.digest()}
        self.report["inventory"] = self._inventory(rows)

        core = _app(self.work / "target")
        dry = self._t("dry_run_s", lambda: core.migration.dry_run(self.source, self.opts))
        rep = self._t("apply_s", lambda: core.migration.apply(
            self.source, self.opts, snapshot_dir=self.work / "snapshot"))
        rerun = self._t("rerun_s", lambda: core.migration.apply(
            self.source, self.opts, snapshot_dir=self.work / "snapshot"))
        self.report["migration"] = {
            "dry_run": {"lossless": dry.lossless, "errors": len(dry.errors),
                        "digest": dry.digest},
            "apply": {"lossless": rep.lossless, "errors": rep.errors,
                      "validation_failures": rep.validation_failures,
                      "digest": rep.digest, "snapshot_sha256": rep.snapshot["sha256"]},
            "counts": rep.counts, "professor_identity": rep.professor_identity,
            "evaluation_check": rep.evaluation_check,
        }
        self._no_loss(rep)
        self._documents(core, rows)
        self._evaluation(core, rows)
        self._career(core, rows, today)
        self._relations(core, rows)
        self._backup(core)
        self._idempotence(core, rerun)
        if seeds:
            self._determinism(seeds)
        # source protection LAST: after every operation
        src_after = sha256_file(self.source)
        docs_after = documents_manifest(self.documents)
        self._crit("source_untouched", src_after == src_before and docs_after == docs_before,
                   {"db_sha256_before": src_before, "db_sha256_after": src_after,
                    "documents_digest_before": docs_before["digest"],
                    "documents_digest_after": docs_after["digest"]})
        self._crit("migration_valid", rep.lossless and not rep.validation_failures
                   and not rep.cancelled, {"errors": len(rep.errors),
                                           "validation_failures": rep.validation_failures})
        self.report["performance"] = self.timings | {
            "documents": docs_before["files"], "pages": len(rows.get("pagina_texto", []))}
        self.report["verdict"] = _check(all(c["result"] == "PASS"
                                            for c in self.report["criteria"].values()))
        return self.report

    # ------------------------------------------------------------ sections
    @staticmethod
    def _inventory(rows: dict) -> dict:
        counts = {t: len(rows.get(t, [])) for t in TABLES}
        ext = [CM.provider_of(r.get("url") or "") for r in rows.get("recurso_externo", [])]
        comps = rows.get("componente_evaluacion", [])
        tasks = rows.get("tarea_evento", [])
        return {"tables": counts,
                "external_by_provider": {p: ext.count(p) for p in sorted(set(ext))},
                "components_in_blocks": sum(1 for c in comps if c.get("bloque_id")),
                "components_without_scheme": sum(1 for c in comps if not c.get("esquema_id")),
                "tasks_without_subject": sum(1 for t in tasks if not t.get("asignatura_id")),
                "subject_states": {s: sum(1 for a in rows.get("asignatura", [])
                                          if a.get("estado") == s)
                                   for s in sorted({a.get("estado") for a in
                                                    rows.get("asignatura", [])})},
                "current_terms": sum(1 for c in rows.get("cuatrimestre", [])
                                     if c.get("estado") == "actual")}

    def _no_loss(self, rep) -> None:
        table = []
        ok = True
        for t, c in rep.counts.items():
            accounted = c["migrated"] + c["preserved"] + c["already_migrated"]
            diff = c["source"] - accounted
            ok &= diff == 0
            table.append({"entity": t, "input": c["source"], "migrated": c["migrated"],
                          "preserved": c["preserved"], "difference": diff})
        self.report["no_loss"] = table
        self._crit("no_loss", ok and rep.lossless, {"entities": len(table)})

    def _documents(self, core, rows) -> None:
        mapped = core.migration.legacy.all_mapped(SOURCE_SYSTEM)
        by_id = {str(r["id"]): r for r in rows.get("documento", [])}
        checked = bad = 0
        problems: list[str] = []
        for (table, sid), rid in sorted(mapped.items()):
            if table != "documento":
                continue
            r = by_id[sid]
            checked += 1
            try:
                path = resolve_document(self.documents, r["ruta_local"],
                                        self.opts.max_document_bytes)
            except FileNotFoundError:
                # Same identity rule as the migrator (closure §3): historic
                # path is provenance; filename + size is identity.
                from academic_core.infrastructure.legacy_gestion import (
                    resolve_document_by_identity)
                path = resolve_document_by_identity(
                    self.documents, r["nombre_archivo"], r.get("tamano_bytes"),
                    self.opts.max_document_bytes)
            res = core.records.get(rid)
            cur = res.current()
            src_hash = sha256_file(path)
            subj = mapped.get(("asignatura", str(r["asignatura_id"])))
            links = [d for d in core.material.documents(subj) if d.resource_id == rid]
            grp = mapped.get(("grupo_documento", str(r["grupo_documento_id"]))) if r.get(
                "grupo_documento_id") else ""
            checks = {
                "sha256": src_hash == cur.content_hash == hashlib.sha256(
                    core.blobs.get_bytes(cur.content_hash)).hexdigest(),
                "size": path.stat().st_size == cur.size,
                "subject_relation": bool(links),
                "filename": bool(links) and links[0].filename == r["nombre_archivo"],
                "group": bool(links) and (not grp or links[0].group_id == grp),
                # byte-identical rows share the first row's resource (dedup);
                # the resource must come from the migration or pre-exist
                "provenance": any(v.provenance.origin == "migration" and v.provenance.source
                                  .startswith(f"{SOURCE_SYSTEM}:documento/")
                                  for v in res.versions) or cur.provenance.origin != "",
            }
            if not all(checks.values()):
                bad += 1
                problems.append(f"documento#{sid}: " + ",".join(k for k, v in checks.items()
                                                                if not v))
        preserved = [p for p in core.migration.legacy.payloads(SOURCE_SYSTEM, "documento")]
        dup_same_subject = sum(1 for p in preserved if p["target_id"])
        self.report["documents"] = {
            "source_rows": len(by_id), "migrated_verified": checked, "mismatches": bad,
            "problems": problems[:50], "preserved_rows": len(preserved),
            "preserved_duplicates_same_subject": dup_same_subject,
            "resources": len(core.records.all_ids()),
        }
        missing = len(preserved) - dup_same_subject
        self._crit("documents_real_hashes", bad == 0 and missing == 0,
                   {"verified": checked, "mismatches": bad, "not_migrated": missing})

    def _evaluation(self, core, rows) -> None:
        mapped = core.migration.legacy.all_mapped(SOURCE_SYSTEM)
        out, mism = [], 0
        for a in rows.get("asignatura", []):
            sid = mapped.get(("asignatura", str(a["id"])))
            if not sid:
                continue
            g = gestion_estado_notas(a, rows.get("esquema_evaluacion", []),
                                     rows.get("bloque_evaluacion", []),
                                     rows.get("componente_evaluacion", []))
            ev = core.evaluation.evaluate(sid)
            grade_ok = (g["nota_actual"] is None and ev.grade is None) or (
                g["nota_actual"] is not None and ev.grade is not None
                and abs(Decimal(str(g["nota_actual"])) - ev.grade) <= Decimal("0.0001"))
            same = (grade_ok and g["estado_notas"] == ev.state
                    and g["minimo_incumplido"] == ev.min_grade_violated
                    and g["evaluaciones_realizadas"] == ev.evaluated_items
                    and g["evaluaciones_pendientes"] == ev.pending_items
                    and abs(Decimal(str(g["porcentaje_evaluado"])) - ev.percent_evaluated)
                    <= Decimal("0.01"))
            mism += not same
            out.append({"subject": sid, "legacy_id": a["id"], "equal": same,
                        "gestion": {"state": g["estado_notas"], "grade": g["nota_actual"],
                                    "percent": g["porcentaje_evaluado"],
                                    "min_violated": g["minimo_incumplido"]},
                        "core": {"state": ev.state, "grade": _dec(ev.grade),
                                 "percent": str(ev.percent_evaluated),
                                 "min_violated": ev.min_grade_violated,
                                 "applied_scheme": ev.applied_scheme_id,
                                 "schemes": len(ev.schemes)}})
        self.report["evaluation"] = {"subjects": len(out), "mismatches": mism, "rows": out}
        self._crit("evaluation_real", mism == 0, {"subjects": len(out), "mismatches": mism})

    def _career(self, core, rows, today: date) -> None:
        subjects = core.academic.all_subjects()
        ids = [s.stable_id for s in subjects]
        home = core.career.home(today)
        car = core.career.career()
        part = car.partition
        cur_terms = set(part.current_term_ids)
        home_ok = all(s.state == "cursando" and s.term_id in cur_terms
                      for s in home.current_subjects)
        union = part.all_ids()
        states = {s: sum(1 for a in rows.get("asignatura", []) if a.get("estado") == s)
                  for s in ("cursando", "superada", "no_superada", "pendiente", "no_elegida")}
        buckets = {"current": len(part.current), "in_progress_elsewhere":
                   len(part.in_progress_elsewhere), "approved": len(part.approved),
                   "failed": len(part.failed), "not_taken": len(part.not_taken),
                   "not_chosen": len(part.not_chosen)}
        counts_ok = (buckets["current"] + buckets["in_progress_elsewhere"] == states["cursando"]
                     and buckets["approved"] == states["superada"]
                     and buckets["failed"] == states["no_superada"]
                     and buckets["not_taken"] == states["pendiente"]
                     and buckets["not_chosen"] == states["no_elegida"])
        details = {}
        for status in CR.AcademicStatus:
            s = next((x for x in subjects if CR.classify(x.state) is status), None)
            if s is None:
                details[status.value] = None
                continue
            d = core.career.course(s.stable_id)
            details[status.value] = {"subject": s.stable_id, "professors": len(d.professors),
                                     "schemes": len(d.schemes), "documents": len(d.documents),
                                     "external": len(d.external_resources),
                                     "tasks": len(d.tasks), "series": len(d.series),
                                     "study_spaces": len(d.study_spaces)}
        self.report["career"] = {
            "home": {"current_terms": list(part.current_term_ids),
                     "current_subjects": [s.stable_id for s in home.current_subjects],
                     "study_spaces": len(home.study_spaces), "upcoming": len(home.upcoming),
                     "week_items": len(home.week)},
            "career_buckets": buckets, "source_states": states, "details": details}
        # Home = present only: every subject shown is CURSANDO in a current
        # term (never the whole catalogue); Carrera below covers everything.
        self._crit("home_real", home_ok and len(home.current_subjects) == len(part.current),
                   {"home_subjects": len(home.current_subjects), "all_subjects": len(ids)})
        self._crit("career_real", sorted(union) == sorted(ids) and len(union) == len(set(union))
                   and counts_ok, {"buckets": buckets, "source_states": states})

    def _relations(self, core, rows) -> None:
        mapped = core.migration.legacy.all_mapped(SOURCE_SYSTEM)
        cx = sqlite3.connect(core.db.path)
        try:
            def n(sql):
                return cx.execute(sql).fetchone()[0]
            got = {
                "professor_links": n("SELECT COUNT(*) FROM subject_staff"),
                "schemes": n("SELECT COUNT(*) FROM assessment_schemes"),
                "blocks": n("SELECT COUNT(*) FROM assessment_blocks"),
                "components": n("SELECT COUNT(*) FROM assessment_components"),
                "external": n("SELECT COUNT(*) FROM external_resources"),
                "external_distinct_urls": n("SELECT COUNT(DISTINCT subject_id || url)"
                                            " FROM external_resources"),
                "groups": n("SELECT COUNT(*) FROM document_groups"),
                "tasks": n("SELECT COUNT(*) FROM tasks"),
                "tasks_without_subject": n("SELECT COUNT(*) FROM tasks WHERE subject_id=''"),
                "series": n("SELECT COUNT(*) FROM schedule_series WHERE stable_id<>''"),
                "spaces": n("SELECT COUNT(*) FROM study_spaces WHERE stable_id<>''"),
                "space_documents": n("SELECT COUNT(*) FROM study_space_documents"),
                "space_goals": n("SELECT COUNT(*) FROM study_space_goals"),
                "sessions": n("SELECT COUNT(*) FROM study_sessions"),
                "activity_days": n("SELECT COUNT(*) FROM activity_days"),
                "milestones": n("SELECT COUNT(*) FROM milestones"),
                "notes": n("SELECT COUNT(*) FROM quick_notes"),
                "concepts": n("SELECT COUNT(*) FROM study_concepts"),
            }
        finally:
            cx.close()
        src = {t: len(rows.get(t, [])) for t in TABLES}

        def acc(t):  # migrated or preserved rows of a source table
            c = self.report["migration"]["counts"][t]
            return c["migrated"] + c["already_migrated"]
        expect = {
            "professor_links": acc("profesor"), "schemes": acc("esquema_evaluacion"),
            "blocks": acc("bloque_evaluacion"), "components": acc("componente_evaluacion"),
            "external": acc("recurso_externo"), "groups": acc("grupo_documento"),
            "tasks": acc("tarea_evento"), "series": acc("horario_clase"),
            "spaces": acc("espacio_estudio"), "space_documents": acc("espacio_estudio_documento"),
            "space_goals": acc("objetivo_espacio"), "sessions": acc("sesion_estudio"),
            "activity_days": acc("dia_actividad"), "milestones": acc("hito"),
            "notes": acc("nota_rapida"), "concepts": acc("concepto"),
            "tasks_without_subject": sum(1 for t in rows.get("tarea_evento", [])
                                         if not t.get("asignatura_id")),
        }
        diffs = {k: (got[k], v) for k, v in expect.items() if got[k] != v}
        ext = [CM.provider_of(x.url) for x in core.course_material.all_externals()]
        conflicts = 0
        for t in core.planning.all_tasks():
            if t.day and t.start and t.end:
                conflicts += len(core.calendar.conflicts(t.day, t.start, t.end,
                                                         exclude=t.stable_id))
        self.report["relations"] = {
            "source": src, "target": got, "differences": diffs,
            "external_by_provider": {p: ext.count(p) for p in sorted(set(ext))},
            "timed_task_conflicts": conflicts,
            "unmapped_subjects": sum(1 for a in rows.get("asignatura", [])
                                     if ("asignatura", str(a["id"])) not in mapped)}
        self._crit("relations_real", not diffs and got["external"] ==
                   got["external_distinct_urls"], {"differences": diffs})

    def _backup(self, core) -> None:
        from academic_core.application.backup import BackupService
        arc = core.backup.export_zip(self.work / "backup.zip", cas_root=core.blobs.root)
        verify = BackupService.verify_zip(arc.path)
        restored = BackupService.restore_zip(arc.path, self.work / "restored")
        back = _app(self.work / "restored")
        same = (sorted(s.stable_id for s in back.academic.all_subjects())
                == sorted(s.stable_id for s in core.academic.all_subjects())
                and back.records.all_ids() == core.records.all_ids())
        self.report["backup"] = {"archive_sha256": arc.sha256, "members": verify["members"],
                                 "blobs": verify["blobs"], "restored_equal": same}
        self._crit("backup_verify_restore", same and restored["blobs"] == verify["blobs"],
                   self.report["backup"])

    def _idempotence(self, core, rerun) -> None:
        new = sum(c["migrated"] for c in rerun.counts.values())
        self.report["idempotence"] = {"second_run_migrated": new,
                                      "second_run_digest": rerun.digest,
                                      "validation_failures": rerun.validation_failures}
        self._crit("idempotence", new == 0 and not rerun.validation_failures,
                   self.report["idempotence"])

    def _determinism(self, seeds) -> None:
        results = {}
        script = ("import json,sys\n"
                  "from academic_core.application.gestion_certification import _seed_run\n"
                  "print(json.dumps(_seed_run(sys.argv[1], sys.argv[2], sys.argv[3])))\n")
        for seed in seeds:
            env = dict(os.environ, PYTHONHASHSEED=seed,
                       PYTHONPATH=os.pathsep.join([str(Path(__file__).resolve().parents[2])]
                                                  + sys.path))
            r = subprocess.run([sys.executable, "-c", script, str(self.source),
                                str(self.documents or ""), str(self.work / f"seed-{seed}")],
                               env=env, capture_output=True, text=True, timeout=3600)
            if r.returncode != 0:
                results[seed] = {"error": r.stderr[-400:]}
                continue
            results[seed] = json.loads(r.stdout.strip().splitlines()[-1])
        first = next(iter(results.values()))
        same = all(v == first and "error" not in v for v in results.values())
        self.report["determinism"] = {"seeds": list(seeds), "equal": same,
                                      "fingerprint": first}
        self._crit("determinism", same, {"seeds": list(seeds)})


def _seed_run(source: str, documents: str, work: str) -> dict:
    """One isolated migration (used per PYTHONHASHSEED)."""
    core = _app(Path(work) / "data")
    opts = MigrationOptions(documents_dir=documents or None)
    rep = core.migration.apply(source, opts, snapshot_dir=Path(work) / "snap")
    ev = [(s.stable_id, core.evaluation.evaluate(s.stable_id).state,
           _dec(core.evaluation.evaluate(s.stable_id).grade))
          for s in core.academic.all_subjects()]
    h = hashlib.sha256(json.dumps({
        "subjects": [s.stable_id for s in core.academic.all_subjects()],
        "professors": [p.stable_id for p in core.academic.all_professors()],
        "resources": core.records.all_ids(), "evaluation": ev,
        "tasks": [t.stable_id for t in core.planning.all_tasks()],
    }, sort_keys=True).encode()).hexdigest()
    return {"report_digest": rep.digest, "state_digest": h,
            "counts": {k: v["migrated"] for k, v in rep.counts.items()}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", required=True)
    ap.add_argument("--documents")
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-seeds", action="store_true")
    a = ap.parse_args(argv)
    rep = Certifier(a.source, a.documents, a.work).run(seeds=() if a.no_seeds else SEEDS)
    Path(a.out).write_text(json.dumps(rep, indent=1, sort_keys=True, ensure_ascii=False),
                           encoding="utf-8")
    sys.stdout.write(f"{rep['verdict']}\n")
    for k, v in sorted(rep["criteria"].items()):
        sys.stdout.write(f"  {k}: {v['result']}\n")
    return 0 if rep["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
