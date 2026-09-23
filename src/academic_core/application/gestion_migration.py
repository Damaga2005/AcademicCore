# SPDX-License-Identifier: MIT
"""Gestion-Academica -> AcademicCore data migration (F4.1, ADR-0024).

Protocol (never destructive, never a second database):

    read source (read-only) -> validate -> PLAN (deterministic)
      dry-run: report only, zero writes
      apply:   snapshot target (BackupService) -> CAS blobs -> ONE SQLite
               transaction (all rows + legacy_map + legacy_payloads)
               -> derived FTS index -> post-validation -> run record

Guarantees:
- Idempotent: every source row is recorded in ``legacy_map`` (migrated) or
  ``legacy_payloads`` (preserved verbatim, e.g. deferred to F10/F11/F12/F14
  or refused by a domain invariant). A re-run skips mapped rows.
- No loss: post-validation proves every source row id is accounted for.
- Deterministic: same source + same target state -> same plan, same ids,
  same report digest (timestamps, run ids and paths excluded).
- Cancellable: cancel before/while planning or writing leaves the target
  database unchanged (transaction rolled back). CAS blobs already written
  are immutable, content-addressed and harmless (dedup on retry).
- Safe: legacy files are resolved strictly under ``documents_dir``; bytes
  are only hashed and stored, never opened by a parser they were refused
  by, never executed; URLs are stored, never fetched.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable

from academic_core.domain import course_material as CM
from academic_core.domain import evaluation as EV
from academic_core.domain import planning as PL
from academic_core.domain import resources as R
from academic_core.domain import schedule as S
from academic_core.domain.entities import (
    AcademicYear, Degree, DomainError, Professor, StudySession, StudySpace, Subject,
    SubjectStaff, Task, Term, University,
)
from academic_core.domain.identity import IdAllocator, make, slugify
from academic_core.errors import MigrationError
from academic_core.infrastructure.academic_store import (
    CourseMaterialRepository, EvaluationRepository, LegacyRepository, PersonalRepository,
    SeriesRepository, StudySpaceRepository, TargetWriter,
)
from academic_core.infrastructure.legacy_gestion import (
    SOURCE_SYSTEM, TABLES, LegacyGestionSource, LegacySnapshot, UnsafePathError,
    resolve_document,
)
from academic_core.resources.adapters import UnsupportedType, adapter_for, detect_kind

SETTING_TARGET_AVERAGE = "grades.target_average"
REPORT_SCHEMA = "gestion-migration-report/1"

Progress = Callable[[str, int, int], None]
Cancel = Callable[[], bool]


# ------------------------------------------------------------------ helpers

dec_text = EV.legacy_float_text


def hhmm(v) -> str:
    """SQLAlchemy Time text ("15:00:00.000000") -> "15:00"."""
    if not v:
        return ""
    parts = str(v).split(":")
    return f"{int(parts[0]):02d}:{int(parts[1]):02d}"


def day(v) -> date | None:
    return date.fromisoformat(str(v)[:10]) if v else None


def iso(v) -> str:
    if not v:
        return ""
    return str(v).replace(" ", "T")


def _row_id(table: str, row: dict) -> str:
    if table == "asignatura_prerrequisito":
        return f"{row['asignatura_id']}->{row['prerrequisito_id']}"
    if table == "aviso_descartado":
        return f"{row['tipo']}|{row['entidad_id']}|{row['fecha']}"
    if table == "dia_actividad":
        return str(row["fecha"])
    return str(row["id"])


@dataclass
class MigrationOptions:
    documents_dir: str | None = None
    university_name: str = "Universidad (migrada de Gestion-Academica)"
    degree_name: str = "Grado (migrado de Gestion-Academica)"
    degree_slug: str = "gestion"
    max_document_bytes: int = 200 * 1024 * 1024
    degree_total_credits: str | None = None
    final_project_names: tuple[str, ...] = ()


@dataclass
class Op:
    table: str
    source_id: str
    action: str  # migrate | preserve | skip
    target_id: str = ""
    obj: object = None
    extra: dict = field(default_factory=dict)
    reason: str = ""
    deferred_to: str = ""


@dataclass
class MigrationReport:
    mode: str
    source_revision: str
    source_digest: str
    counts: dict
    warnings: list[str]
    errors: list[str]
    lossless: bool
    evaluation_check: dict
    cancelled: bool = False
    validation_failures: list[str] = field(default_factory=list)
    snapshot: dict | None = None
    run_id: str = ""
    started: str = ""
    finished: str = ""

    def canonical(self) -> dict:
        """Deterministic part of the report (no ids/timestamps/paths)."""
        return {"schema": REPORT_SCHEMA, "mode": self.mode,
                "source_revision": self.source_revision, "source_digest": self.source_digest,
                "counts": self.counts, "warnings": self.warnings, "errors": self.errors,
                "lossless": self.lossless, "evaluation_check": self.evaluation_check,
                "cancelled": self.cancelled, "validation_failures": self.validation_failures}

    @property
    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.canonical(), sort_keys=True, ensure_ascii=False,
                                         separators=(",", ":")).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        return self.canonical() | {"report_digest": self.digest, "snapshot": self.snapshot,
                                   "run_id": self.run_id, "started": self.started,
                                   "finished": self.finished}


class _Cancelled(Exception):
    pass


# ------------------------------------------------------------------ planner

class _Planner:
    """Pure-ish: turns the snapshot into ordered Ops. Reads only the target
    state it is given (mapped ids, taken subject ids, counters)."""

    def __init__(self, snap: LegacySnapshot, mapped: dict[tuple[str, str], str],
                 counters: dict[str, int], taken_subjects: set[str],
                 opts: MigrationOptions, cancel: Cancel | None,
                 known_hash: Callable[[str], str | None] = lambda h: None):
        self.known_hash = known_hash  # content hash -> existing resource id
        self.snap = snap
        self.mapped = dict(mapped)
        self.alloc = IdAllocator(counters)
        self.taken = set(taken_subjects)
        self.opts = opts
        self.cancel = cancel
        self.ops: list[Op] = []
        self.warnings: list[str] = []
        self.errors: list[str] = []
        self.ids: dict[tuple[str, str], str] = {}  # planned + pre-existing mapping
        self.subject_of_task: dict[str, str] = {}
        self.professors_seen: dict[str, Professor] = {}
        self.staff_seen: set[tuple[str, str]] = set()
        self.goal_count: dict[str, int] = {}
        self.blob_plan: dict[str, dict] = {}  # documento id -> file info

    # utils -----------------------------------------------------------------
    def _check(self) -> None:
        if self.cancel and self.cancel():
            raise _Cancelled()

    def target(self, table: str, source_id) -> str | None:
        key = (table, str(source_id))
        return self.ids.get(key) or self.mapped.get(key)

    def _add(self, op: Op) -> None:
        key = (op.table, op.source_id)
        if key in self.mapped:
            self.ops.append(Op(op.table, op.source_id, "skip", self.mapped[key]))
            self.ids[key] = self.mapped[key]
            return
        if op.action == "migrate":
            self.ids[key] = op.target_id
        self.ops.append(op)

    def _preserve(self, table: str, row: dict, reason: str, deferred: str = "",
                  target: str = "", error: bool = False) -> None:
        sid = _row_id(table, row)
        if error:
            self.errors.append(f"{table}#{sid}: {reason}")
        self._add(Op(table, sid, "preserve", target, obj=row, reason=reason,
                     deferred_to=deferred))

    def _scope(self, subject_id: str) -> str:
        return subject_id.split(":", 1)[1] if subject_id else "general"

    def _new(self, kind: str, subject_id: str = "") -> str:
        return self.alloc.allocate(kind, self._scope(subject_id))

    def rows(self, table: str) -> list[dict]:
        return self.snap.tables.get(table, [])

    # plan ------------------------------------------------------------------
    def build(self) -> list[Op]:
        o = self.opts
        uni = University(make("university", slugify(o.university_name)), o.university_name)
        deg = Degree(make("degree", slugify(o.degree_slug)), o.degree_name, uni.stable_id)
        self.university, self.degree = uni, deg
        for step in (self._years, self._terms, self._subjects, self._prereqs, self._professors,
                     self._evaluation, self._externals, self._apartados, self._groups,
                     self._documents, self._pages, self._pdf_marks, self._tasks, self._spaces,
                     self._space_docs, self._goals, self._series, self._milestones, self._notes,
                     self._concepts, self._sessions, self._activity, self._settings,
                     self._deferred_misc):
            self._check()
            step()
        return self.ops

    def _years(self) -> None:
        deg = slugify(self.opts.degree_slug)
        for r in self.rows("anio"):
            y = AcademicYear(make("year", f"{deg}-curso-{int(r['numero'])}"),
                             f"Curso {int(r['numero'])}", self.degree.stable_id)
            self._add(Op("anio", str(r["id"]), "migrate", y.stable_id, y))

    def _terms(self) -> None:
        deg = slugify(self.opts.degree_slug)
        by_year: dict = {}
        for r in self.rows("cuatrimestre"):
            by_year.setdefault(r["anio_id"], []).append(r)
        for anio_id, rows in by_year.items():
            for idx, r in enumerate(sorted(rows, key=lambda r: (r["numero"], r["id"])), start=1):
                year = self.target("anio", anio_id)
                if not year:
                    self._preserve("cuatrimestre", r, "orphan: anio missing", error=True)
                    continue
                try:
                    t = Term(make("term", f"{deg}-q{int(r['numero'])}"),
                             f"Cuatrimestre {int(r['numero'])}", "cuatrimestre", idx, year,
                             state=r["estado"])
                except DomainError as e:
                    self._preserve("cuatrimestre", r, str(e), error=True)
                    continue
                self._add(Op("cuatrimestre", str(r["id"]), "migrate", t.stable_id, t,
                             {"course": next((a["numero"] for a in self.rows("anio")
                                              if a["id"] == anio_id), 0)}))

    def _term_course(self, cuatri_id) -> tuple[str, int]:
        term = self.target("cuatrimestre", cuatri_id) or ""
        for op in self.ops:
            if op.table == "cuatrimestre" and op.target_id == term:
                return term, int(op.extra.get("course", 0) or 0)
        cu = next((c for c in self.rows("cuatrimestre") if c["id"] == cuatri_id), None)
        anio = next((a for a in self.rows("anio") if cu and a["id"] == cu["anio_id"]), None)
        return term, int(anio["numero"]) if anio else 0

    def _subject_id(self, r: dict) -> str:
        base = slugify(r.get("siglas") or r["nombre"])
        sid = f"subject:{base}"
        if sid in self.taken:
            sid = f"subject:{base}-{int(r['id'])}"
        return sid

    def _subjects(self) -> None:
        for r in self.rows("asignatura"):
            key = ("asignatura", str(r["id"]))
            if key in self.mapped:
                self._add(Op("asignatura", str(r["id"]), "skip"))
                continue
            term, course = self._term_course(r["cuatrimestre_id"])
            if not term:
                self._preserve("asignatura", r, "orphan: cuatrimestre missing", error=True)
                continue
            extra: dict = {"legacy": {"system": SOURCE_SYSTEM, "id": r["id"]}}
            contact = {k: r.get(k) for k in ("nombre_profesor", "despacho_profesor",
                                             "correo_profesor") if r.get(k)}
            if contact:
                extra["legacy_contact"] = contact
            classroom = (r.get("link_aula_virtual") or "").strip()
            if classroom and not classroom.lower().startswith(("http://", "https://")):
                extra["legacy_link_aula_virtual"] = classroom
                self.warnings.append(f"asignatura#{r['id']}: non-http classroom link kept in extra")
                classroom = ""
            sid = self._subject_id(r)
            try:
                s = Subject(sid, "", r["nombre"].strip(), (r.get("siglas") or "").upper(), "",
                            float(r["creditos_ects"]), r.get("tipo") or "obligatoria", course,
                            term, r.get("estado") or "pendiente", dec_text(r.get("nota_final")),
                            bool(r.get("origen_catalogo")), r.get("regla_esquemas") or "maximo",
                            r.get("notas") or "", iso(r.get("notas_actualizado_en")), classroom,
                            extra)
            except (DomainError, ValueError) as e:
                self._preserve("asignatura", r, f"invalid subject: {e}", error=True)
                continue
            self.taken.add(sid)
            self._add(Op("asignatura", str(r["id"]), "migrate", sid, s))

    def _prereqs(self) -> None:
        for r in self.rows("asignatura_prerrequisito"):
            a = self.target("asignatura", r["asignatura_id"])
            p = self.target("asignatura", r["prerrequisito_id"])
            if not (a and p) or a == p:
                self._preserve("asignatura_prerrequisito", r, "endpoint missing/self", error=True)
                continue
            self._add(Op("asignatura_prerrequisito", _row_id("asignatura_prerrequisito", r),
                         "migrate", f"{a}->{p}", (a, p)))

    def _professors(self) -> None:
        for r in self.rows("profesor"):
            subj = self.target("asignatura", r["asignatura_id"])
            if not subj:
                self._preserve("profesor", r, "orphan: asignatura missing", error=True)
                continue
            name = (r.get("nombre") or "").strip()
            try:
                pid = make("professor", slugify(name))
            except ValueError as e:
                self._preserve("profesor", r, f"invalid name: {e}", error=True)
                continue
            url = (r.get("aula_virtual") or "").strip()
            if url and not url.lower().startswith(("http://", "https://")):
                self.warnings.append(f"profesor#{r['id']}: non-http aula_virtual preserved")
                self._preserve_payload_only("profesor", r, "non-http aula_virtual")
                url = ""
            if pid not in self.professors_seen:
                self.professors_seen[pid] = Professor(pid, name, r.get("correo") or "",
                                                      r.get("despacho") or "", url)
            elif (r.get("correo") and self.professors_seen[pid].email
                  and r["correo"] != self.professors_seen[pid].email):
                self.warnings.append(f"profesor#{r['id']}: homonym with different email "
                                     f"merged into {pid} (per-link email kept)")
            if (subj, pid) in self.staff_seen:
                self._preserve("profesor", r, "duplicate professor link in subject",
                               target=pid)
                continue
            self.staff_seen.add((subj, pid))
            try:
                link = SubjectStaff(subj, pid, r.get("rol") or "docente", "",
                                    int(r.get("orden") or 0), r.get("correo") or "",
                                    r.get("despacho") or "", url)
            except DomainError as e:
                self._preserve("profesor", r, str(e), error=True)
                continue
            self._add(Op("profesor", str(r["id"]), "migrate", pid,
                         (self.professors_seen[pid], link)))

    def _preserve_payload_only(self, table: str, row: dict, reason: str) -> None:
        """Extra verbatim copy for a row that is ALSO migrated (lossy field)."""
        self.ops.append(Op(table + "#raw", _row_id(table, row), "preserve", "", obj=row,
                           reason=reason))

    def _evaluation(self) -> None:
        scheme_subject: dict[str, str] = {}
        for r in self.rows("esquema_evaluacion"):
            subj = self.target("asignatura", r["asignatura_id"])
            if not subj:
                self._preserve("esquema_evaluacion", r, "orphan: asignatura missing", error=True)
                continue
            key = ("esquema_evaluacion", str(r["id"]))
            sid = self.mapped.get(key) or self._new("scheme", subj)
            try:
                EV.AssessmentScheme(sid, subj, (r.get("nombre") or "").strip() or "Evaluación",
                                    order=int(r.get("orden") or 0))
            except DomainError as e:
                self._preserve("esquema_evaluacion", r, str(e), error=True)
                continue
            scheme_subject[sid] = subj
            self._add(Op("esquema_evaluacion", str(r["id"]), "migrate", sid,
                         (subj, (r.get("nombre") or "").strip() or "Evaluación",
                          int(r.get("orden") or 0))))
        for r in self.rows("bloque_evaluacion"):
            sch = self.target("esquema_evaluacion", r["esquema_id"])
            if not sch:
                self._preserve("bloque_evaluacion", r, "orphan: esquema missing", error=True)
                continue
            subj = scheme_subject.get(sch, "")
            key = ("bloque_evaluacion", str(r["id"]))
            if key in self.mapped:
                self._add(Op("bloque_evaluacion", str(r["id"]), "skip"))
                continue
            bid = self._new("block", subj)
            try:
                EV.AssessmentBlock(bid, r["nombre"], dec_text(r["porcentaje"]),
                                   order=int(r.get("orden") or 0))
            except DomainError as e:
                self._preserve("bloque_evaluacion", r, str(e), error=True)
                continue
            self._add(Op("bloque_evaluacion", str(r["id"]), "migrate", bid,
                         (sch, r["nombre"], dec_text(r["porcentaje"]), int(r.get("orden") or 0))))
        implicit: dict[str, str] = {}
        for r in self.rows("componente_evaluacion"):
            subj = self.target("asignatura", r["asignatura_id"])
            if not subj:
                self._preserve("componente_evaluacion", r, "orphan: asignatura missing",
                               error=True)
                continue
            key = ("componente_evaluacion", str(r["id"]))
            if key in self.mapped:
                self._add(Op("componente_evaluacion", str(r["id"]), "skip"))
                continue
            sch = self.target("esquema_evaluacion", r["esquema_id"]) if r.get("esquema_id") else None
            if r.get("esquema_id") and not sch:
                self._preserve("componente_evaluacion", r, "orphan: esquema missing", error=True)
                continue
            if not sch:  # pre-"esquemas alternativos" rows: implicit scheme
                if subj not in implicit:
                    implicit[subj] = self._new("scheme", subj)
                    self.warnings.append(f"{subj}: components without scheme grouped into an "
                                         "implicit 'Evaluación' scheme")
                    self.ops.append(Op("esquema_evaluacion#implicit", subj, "migrate",
                                       implicit[subj], (subj, "Evaluación", 0)))
                sch = implicit[subj]
            blk = ""
            if r.get("bloque_id"):
                blk = self.target("bloque_evaluacion", r["bloque_id"]) or ""
                if not blk:
                    self._preserve("componente_evaluacion", r, "orphan: bloque missing",
                                   error=True)
                    continue
            cid = self._new("component", subj)
            try:
                c = EV.AssessmentComponent(cid, r["nombre"], dec_text(r["porcentaje"]),
                                           r.get("tipo") or "otro", dec_text(r.get("nota")),
                                           dec_text(r.get("nota_minima")),
                                           int(r.get("orden") if r.get("orden") is not None
                                               else 1_000_000))
            except DomainError as e:
                self._preserve("componente_evaluacion", r, str(e), error=True)
                continue
            self._add(Op("componente_evaluacion", str(r["id"]), "migrate", cid,
                         (subj, sch, blk, c)))

    def _externals(self) -> None:
        for r in self.rows("recurso_externo"):
            subj = self.target("asignatura", r["asignatura_id"])
            if not subj:
                self._preserve("recurso_externo", r, "orphan: asignatura missing", error=True)
                continue
            key = ("recurso_externo", str(r["id"]))
            if key in self.mapped:
                self._add(Op("recurso_externo", str(r["id"]), "skip"))
                continue
            try:
                x = CM.ExternalResource(self._new("link", subj), subj, r["nombre"], r["url"],
                                        r.get("tipo") or "", int(r.get("orden") or 0),
                                        {"origin": "migration",
                                         "source": f"{SOURCE_SYSTEM}:recurso_externo/{r['id']}"})
            except DomainError as e:
                self._preserve("recurso_externo", r, f"invalid link: {e}", error=True)
                continue
            self._add(Op("recurso_externo", str(r["id"]), "migrate", x.stable_id, x))

    def _apartados(self) -> None:
        for r in self.rows("apartado"):
            self._preserve("apartado", r, "legacy classifier (superseded by categories)",
                           deferred="none", target=self.target("asignatura", r["asignatura_id"])
                           or "")

    def _groups(self) -> None:
        for r in self.rows("grupo_documento"):
            subj = self.target("asignatura", r["asignatura_id"])
            if not subj:
                self._preserve("grupo_documento", r, "orphan: asignatura missing", error=True)
                continue
            key = ("grupo_documento", str(r["id"]))
            if key in self.mapped:
                self._add(Op("grupo_documento", str(r["id"]), "skip"))
                continue
            try:
                g = CM.DocumentGroup(self._new("docgroup", subj), subj, r["categoria"],
                                     r["nombre"], int(r.get("orden") or 0))
            except DomainError as e:
                self._preserve("grupo_documento", r, str(e), error=True)
                continue
            self._add(Op("grupo_documento", str(r["id"]), "migrate", g.stable_id, g))

    def _documents(self) -> None:
        root = self.opts.documents_dir
        apartados = {a["id"]: a.get("nombre") for a in self.rows("apartado")}
        pages: dict = {}
        for p in self.rows("pagina_texto"):
            pages.setdefault(p["documento_id"], []).append(p)
        by_hash: dict[str, str] = {}
        linked: set[tuple[str, str]] = set()
        for r in self.rows("documento"):
            self._check()
            key = ("documento", str(r["id"]))
            subj = self.target("asignatura", r["asignatura_id"])
            if key in self.mapped:
                linked.add((subj, self.mapped[key]))
                self._add(Op("documento", str(r["id"]), "skip"))
                continue
            if not subj:
                self._preserve("documento", r, "orphan: asignatura missing", error=True)
                continue
            if not root:
                self._preserve("documento", r, "documents_dir not provided: bytes not migrated",
                               deferred="rerun-with-documents", error=True)
                continue
            try:
                path = resolve_document(root, r["ruta_local"], self.opts.max_document_bytes)
            except UnsafePathError as e:
                self._preserve("documento", r, f"unsafe path refused: {e}", error=True)
                continue
            except FileNotFoundError:
                self._preserve("documento", r, "file missing under documents_dir",
                               deferred="rerun-with-documents", error=True)
                continue
            h = hashlib.sha256()
            with path.open("rb") as fh:
                head = fh.read(8)
                h.update(head)
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    h.update(chunk)
            digest = h.hexdigest()
            filename = r["nombre_archivo"]
            try:
                kind, opaque = detect_kind(filename, head), False
            except UnsupportedType:
                kind, opaque = "file", True
                self.warnings.append(f"documento#{r['id']}: {filename!r} refused by F2 "
                                     "adapters; stored as opaque bytes (never extracted)")
            existing = by_hash.get(digest) or self.known_hash(digest)
            if existing:
                rid, dup = existing, True
                by_hash[digest] = rid
                if (subj, rid) in linked:
                    # same bytes twice in one subject: one relation, the
                    # second row (its own name/progress) kept verbatim.
                    self.ids[key] = rid
                    self._preserve("documento", r, "byte-identical duplicate in same subject",
                                   target=rid)
                    continue
                self._preserve_payload_only("documento", r,
                                            "byte-identical duplicate: own progress kept here")
            else:
                rid, dup = self._new("resource", subj), False
                by_hash[digest] = rid
            cat = r.get("categoria") or "otros"
            if cat not in CM.DOC_CATEGORIES:
                self.warnings.append(f"documento#{r['id']}: unknown category {cat!r} -> otros")
                cat = "otros"
            grp = self.target("grupo_documento", r["grupo_documento_id"]) if r.get(
                "grupo_documento_id") else ""
            legacy = {"id": r["id"], "ruta_local": r["ruta_local"],
                      "nombre_original": r.get("nombre_original"),
                      "fecha_subida": iso(r.get("fecha_subida")),
                      "tamano_bytes": r.get("tamano_bytes")}
            if r.get("apartado_id"):
                legacy["apartado"] = apartados.get(r["apartado_id"])
            if r.get("categoria") != cat:
                legacy["categoria"] = r.get("categoria")
            try:
                cd = CM.CourseDocument(subj, rid, cat, grp or "", filename,
                                       CM.split_tags(r.get("etiquetas")),
                                       iso(r.get("fecha_subida")), legacy)
                prog = CM.ReadingProgress(
                    rid, r.get("ultima_pagina_vista") or None, dec_text(r.get("porcentaje_leido")),
                    r.get("zoom_nivel") or "", r.get("modo_visualizacion") or "",
                    dec_text(r.get("scroll_vertical")), iso(r.get("fecha_primera_apertura")),
                    iso(r.get("fecha_ultima_apertura")),
                    int(r.get("tiempo_total_lectura_segundos") or 0),
                    int(r.get("numero_sesiones") or 0))
            except DomainError as e:
                self._preserve("documento", r, str(e), error=True)
                continue
            linked.add((subj, rid))
            page_rows = sorted(pages.get(r["id"], []), key=lambda p: (p["numero_pagina"], p["id"]))
            self.blob_plan[str(r["id"])] = {"path": path, "hash": digest, "kind": kind,
                                            "opaque": opaque, "dup": dup}
            self._add(Op("documento", str(r["id"]), "migrate", rid,
                         (cd, prog, page_rows), {"kind": kind, "opaque": opaque, "dup": dup,
                                                  "hash": digest, "size": path.stat().st_size,
                                                  "original": r.get("nombre_original")
                                                  or filename}))

    def _pages(self) -> None:
        for p in self.rows("pagina_texto"):
            rid = self.target("documento", p["documento_id"])
            if rid and ("documento", str(p["documento_id"])) not in self.mapped:
                self._add(Op("pagina_texto", str(p["id"]), "migrate",
                             f"{rid}#page={int(p['numero_pagina'])}"))
            elif rid:
                self._add(Op("pagina_texto", str(p["id"]), "skip"))
            else:
                self._preserve("pagina_texto", p, "document bytes not migrated",
                               deferred="rerun-with-documents")

    def _pdf_marks(self) -> None:
        for t in ("marcador", "anotacion_pdf"):
            for r in self.rows(t):
                self._preserve(t, r, "PDF annotations are F14", deferred="F14",
                               target=self.target("documento", r["documento_id"]) or "")

    def _tasks(self) -> None:
        for r in self.rows("tarea_evento"):
            key = ("tarea_evento", str(r["id"]))
            subj = self.target("asignatura", r["asignatura_id"]) if r.get("asignatura_id") else ""
            if r.get("asignatura_id") and not subj:
                self._preserve("tarea_evento", r, "orphan: asignatura missing", error=True)
                continue
            if key in self.mapped:
                self.subject_of_task[self.mapped[key]] = subj
                self._add(Op("tarea_evento", str(r["id"]), "skip"))
                continue
            start, end = hhmm(r.get("hora_inicio")), hhmm(r.get("hora_fin"))
            if start and not end:
                self._preserve_payload_only("tarea_evento", r, "start without end: start dropped")
                start = ""
            if start and end and end <= start:
                self._preserve_payload_only("tarea_evento", r, "end before start: times dropped")
                start = end = ""
            link = (r.get("link_relacionado") or "").strip()
            if link and not link.lower().startswith(("http://", "https://")):
                self._preserve_payload_only("tarea_evento", r, "non-http link dropped")
                link = ""
            doc = self.target("documento", r["documento_id"]) if r.get("documento_id") else ""
            tid = self._new("task", subj)
            try:
                t = Task(tid, subj, r["titulo"].strip(), r.get("tipo") or "tarea_general",
                         day(r["fecha"]), start, end, r.get("prioridad") or "media",
                         "hecha" if r.get("completada") else "pendiente", "",
                         r.get("descripcion") or "", r.get("ubicacion") or "", link,
                         r.get("recordatorio"), r.get("aula") or "", doc or "")
            except (DomainError, ValueError) as e:
                self._preserve("tarea_evento", r, f"invalid task: {e}", error=True)
                continue
            self.subject_of_task[tid] = subj
            self._add(Op("tarea_evento", str(r["id"]), "migrate", tid, t))

    def _spaces(self) -> None:
        for r in self.rows("espacio_estudio"):
            task = self.target("tarea_evento", r["tarea_evento_id"])
            if not task:
                self._preserve("espacio_estudio", r, "orphan: tarea missing", error=True)
                continue
            key = ("espacio_estudio", str(r["id"]))
            if key in self.mapped:
                self._add(Op("espacio_estudio", str(r["id"]), "skip"))
                continue
            subj = self.subject_of_task.get(task, "")
            sid = self._new("space", subj)
            try:
                sp = StudySpace(subj, task, (r.get("nombre") or "").strip())
            except DomainError as e:
                self._preserve("espacio_estudio", r, str(e), error=True)
                continue
            self._add(Op("espacio_estudio", str(r["id"]), "migrate", sid,
                         (sp, iso(r.get("created_at")))))

    def _space_docs(self) -> None:
        for r in self.rows("espacio_estudio_documento"):
            space = self.target("espacio_estudio", r["espacio_estudio_id"])
            res = self.target("documento", r["documento_id"])
            if not space or not res:
                self._preserve("espacio_estudio_documento", r,
                               "space or document not migrated", error=not space,
                               deferred="" if not space else "rerun-with-documents")
                continue
            try:
                d = CM.StudySpaceDocument(space, res, r["seccion"], bool(r.get("leido")),
                                          bool(r.get("destacado")), int(r.get("orden") or 0))
            except DomainError as e:
                self._preserve("espacio_estudio_documento", r, str(e), error=True)
                continue
            self._add(Op("espacio_estudio_documento", str(r["id"]), "migrate",
                         f"{space}#doc={res}", d))

    def _goals(self) -> None:
        rows = sorted(self.rows("objetivo_espacio"),
                      key=lambda r: (r["espacio_estudio_id"], r.get("orden") or 0, r["id"]))
        for r in rows:
            space = self.target("espacio_estudio", r["espacio_estudio_id"])
            if not space:
                self._preserve("objetivo_espacio", r, "orphan: espacio missing", error=True)
                continue
            key = ("objetivo_espacio", str(r["id"]))
            if key in self.mapped:
                self.goal_count[space] = self.goal_count.get(space, 0) + 1
                self._add(Op("objetivo_espacio", str(r["id"]), "skip"))
                continue
            n = self.goal_count.get(space, 0)
            self.goal_count[space] = n + 1
            try:
                g = CM.StudySpaceGoal(space, r["texto"], bool(r.get("completada")), n)
            except DomainError as e:
                self._preserve("objetivo_espacio", r, str(e), error=True)
                continue
            self._add(Op("objetivo_espacio", str(r["id"]), "migrate", f"{space}#goal={n}", g))

    def _series(self) -> None:
        for r in self.rows("horario_clase"):
            subj = self.target("asignatura", r["asignatura_id"])
            if not subj:
                self._preserve("horario_clase", r, "orphan: asignatura missing", error=True)
                continue
            key = ("horario_clase", str(r["id"]))
            if key in self.mapped:
                self._add(Op("horario_clase", str(r["id"]), "skip"))
                continue
            try:
                ser = S.Series(subj, r["tipo"], int(r["dia_semana"]), hhmm(r["hora_inicio"]),
                               hhmm(r["hora_fin"]), day(r["fecha_inicio"]), day(r["fecha_fin"]),
                               int(r.get("intervalo_semanas") or 1), r.get("aula") or "")
            except (ValueError, TypeError) as e:
                self._preserve("horario_clase", r, f"invalid series: {e}", error=True)
                continue
            self._add(Op("horario_clase", str(r["id"]), "migrate", self._new("series", subj),
                         (ser, r.get("notas") or "")))

    def _milestones(self) -> None:
        for r in self.rows("hito"):
            if ("hito", str(r["id"])) in self.mapped:
                self._add(Op("hito", str(r["id"]), "skip"))
                continue
            try:
                m = PL.Milestone(self._new("milestone"), r["nombre"], r.get("estado") or
                                 "pendiente", day(r.get("fecha")), int(r.get("orden") or 0))
            except DomainError as e:
                self._preserve("hito", r, str(e), error=True)
                continue
            self._add(Op("hito", str(r["id"]), "migrate", m.stable_id, m))

    def _notes(self) -> None:
        for r in self.rows("nota_rapida"):
            if ("nota_rapida", str(r["id"])) in self.mapped:
                self._add(Op("nota_rapida", str(r["id"]), "skip"))
                continue
            try:
                n = PL.QuickNote(self._new("note"), r["texto"], iso(r.get("fecha_creacion")))
            except DomainError as e:
                self._preserve("nota_rapida", r, str(e), error=True)
                continue
            self._add(Op("nota_rapida", str(r["id"]), "migrate", n.stable_id, n))

    def _concepts(self) -> None:
        for r in self.rows("concepto"):
            subj = self.target("asignatura", r["asignatura_id"])
            if not subj:
                self._preserve("concepto", r, "orphan: asignatura missing", error=True)
                continue
            if ("concepto", str(r["id"])) in self.mapped:
                self._add(Op("concepto", str(r["id"]), "skip"))
                continue
            try:
                k = PL.StudyConcept(self._new("concept", subj), subj, r["nombre"],
                                    r.get("estado") or "no_visto", day(r.get("ultima_revision")),
                                    day(r.get("proxima_revision")))
            except DomainError as e:
                self._preserve("concepto", r, str(e), error=True)
                continue
            self._add(Op("concepto", str(r["id"]), "migrate", k.stable_id, k))

    def _sessions(self) -> None:
        for r in self.rows("sesion_estudio"):
            subj = self.target("asignatura", r["asignatura_id"]) if r.get("asignatura_id") else ""
            try:
                s = StudySession(subj or "", day(r["fecha"]), int(r["minutos"]),
                                 r.get("nota") or "")
            except (DomainError, TypeError, ValueError) as e:
                self._preserve("sesion_estudio", r, str(e), error=True)
                continue
            self._add(Op("sesion_estudio", str(r["id"]), "migrate",
                         f"study_session:{SOURCE_SYSTEM}:{r['id']}", s))

    def _activity(self) -> None:
        for r in self.rows("dia_actividad"):
            d = day(r["fecha"])
            self._add(Op("dia_actividad", str(r["fecha"]), "migrate", f"activity:{d}", d))

    def _settings(self) -> None:
        for r in self.rows("configuracion_app"):
            values = {f"gestion.{k}": str(r[k]) for k in (
                "tema", "dias_aviso_examen", "dias_asignatura_abandonada", "widgets_orden",
                "widgets_ocultos") if r.get(k) is not None}
            if r.get("objetivo_media") is not None:
                values[SETTING_TARGET_AVERAGE] = dec_text(r["objetivo_media"])
            self._add(Op("configuracion_app", str(r["id"]), "migrate", "settings", values))

    def _deferred_misc(self) -> None:
        for r in self.rows("aviso_descartado"):
            self._preserve("aviso_descartado", r, "notification dismissals are F12",
                           deferred="F12")
        for t in ("busqueda_favorito", "busqueda_reciente"):
            for r in self.rows(t):
                self._preserve(t, r, "search favourites/recents are F4.2", deferred="F4.2")


# ------------------------------------------------------------------ service

class GestionMigrationService:
    def __init__(self, db, blobs, records, fts, academic, backup):
        self.db = db
        self.blobs = blobs
        self.records = records
        self.fts = fts
        self.academic = academic
        self.backup = backup
        self.legacy = LegacyRepository(db)

    # public -----------------------------------------------------------------
    def dry_run(self, source: str | Path, options: MigrationOptions | None = None,
                progress: Progress | None = None, cancel: Cancel | None = None
                ) -> MigrationReport:
        return self._run(source, options or MigrationOptions(), "dry-run", None, progress,
                         cancel)

    def apply(self, source: str | Path, options: MigrationOptions | None = None, *,
              snapshot_dir: str | Path | None, progress: Progress | None = None,
              cancel: Cancel | None = None) -> MigrationReport:
        if snapshot_dir is None:
            raise MigrationError("apply requires snapshot_dir (backup before migrating)",
                                 code="AC-MIG-004")
        return self._run(source, options or MigrationOptions(), "apply", Path(snapshot_dir),
                         progress, cancel)

    # core -------------------------------------------------------------------
    def _plan(self, snap: LegacySnapshot, opts: MigrationOptions, cancel):
        mapped = self.legacy.all_mapped(SOURCE_SYSTEM)
        taken = {s.stable_id for s in self.academic.all_subjects()}
        def known(h: str) -> str | None:
            rows = sorted(self.records.find_by_hash(h))
            return rows[0][0] if rows else None

        planner = _Planner(snap, mapped, self.academic.load_counters(), taken, opts, cancel,
                           known)
        planner.build()
        return planner

    def _run(self, source, opts: MigrationOptions, mode: str, snapshot_dir: Path | None,
             progress: Progress | None, cancel: Cancel | None) -> MigrationReport:
        started = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        tick = progress or (lambda *_: None)
        src = LegacyGestionSource(source)
        rev, warnings = src.open_and_validate()
        tick("read", 0, 1)
        snap = src.read()
        tick("read", 1, 1)
        try:
            planner = self._plan(snap, opts, cancel)
        except _Cancelled:
            return self._cancelled(mode, snap, warnings, started)
        warnings = warnings + planner.warnings
        counts = self._counts(snap, planner.ops)
        report = MigrationReport(mode, rev, snap.digest(), counts, warnings,
                                 list(planner.errors), self._lossless(counts),
                                 self._eval_check(snap, planner))
        report.started = started
        report.run_id = uuid.uuid4().hex
        if mode == "dry-run":
            report.finished = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            return report
        # -- apply --------------------------------------------------------
        snapshot = self.backup.backup(snapshot_dir)
        report.snapshot = {"path": snapshot.path, "sha256": snapshot.sha256}
        try:
            fts_rows = self._write(planner, opts, tick, cancel)
        except _Cancelled:
            rep = self._cancelled(mode, snap, warnings, started)
            rep.snapshot = report.snapshot
            return rep
        except MigrationError:
            raise
        except Exception as e:  # any write failure: transaction already rolled back
            raise MigrationError(f"migration failed, target unchanged: {type(e).__name__}: {e}",
                                 code="AC-MIG-001") from e
        for i, (rid, kind, title, text) in enumerate(fts_rows):
            try:
                self.fts.index(rid, kind, title, text)
            except Exception as e:  # derived index: report, never roll back canonical
                report.warnings.append(f"fts deferred for {rid}: {type(e).__name__}")
            tick("index", i + 1, len(fts_rows))
        report.validation_failures = self.validate(snap, planner)
        report.lossless = report.lossless and not report.validation_failures
        report.finished = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        self.legacy.record_run(report.run_id, SOURCE_SYSTEM, report.source_digest,
                               report.digest, mode, report.started, report.finished,
                               report.to_dict())
        return report

    def _cancelled(self, mode, snap, warnings, started) -> MigrationReport:
        rep = MigrationReport(mode, snap.revision, snap.digest(), {}, list(warnings), [],
                              False, {}, cancelled=True)
        rep.started = started
        rep.finished = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        return rep

    @staticmethod
    def _counts(snap: LegacySnapshot, ops: list[Op]) -> dict:
        counts = {t: {"source": snap.count(t), "migrated": 0, "preserved": 0,
                      "already_migrated": 0} for t in TABLES}
        for op in ops:
            if op.table not in counts:
                continue  # auxiliary ops (#raw copies, implicit schemes)
            k = {"migrate": "migrated", "preserve": "preserved",
                 "skip": "already_migrated"}[op.action]
            counts[op.table][k] += 1
        return counts

    @staticmethod
    def _lossless(counts: dict) -> bool:
        return all(c["migrated"] + c["preserved"] + c["already_migrated"] == c["source"]
                   for c in counts.values())

    # writing ------------------------------------------------------------------
    def _write(self, planner: _Planner, opts: MigrationOptions, tick, cancel) -> list:
        ops = [op for op in planner.ops if op.action != "skip"]
        # 1) blobs first (immutable CAS; outside the SQL transaction)
        stored: dict[str, tuple[str, int]] = {}
        blob_ops = [op for op in ops if op.table == "documento" and op.action == "migrate"]
        for i, op in enumerate(blob_ops):
            if cancel and cancel():
                raise _Cancelled()
            info = planner.blob_plan[op.source_id]
            h, size = self.blobs.put_file(info["path"], opts.max_document_bytes)
            if h != info["hash"]:
                raise MigrationError(f"documento#{op.source_id} changed during migration",
                                     code="AC-MIG-001")
            stored[op.source_id] = (h, size)
            tick("blobs", i + 1, len(blob_ops))
        # 2) one transaction for every canonical row
        fts_rows: list = []
        cx = self.db.connect()
        try:
            cx.execute("BEGIN IMMEDIATE")
            w = TargetWriter(cx)
            evals = EvaluationRepository(self.db)
            material = CourseMaterialRepository(self.db)
            spaces = StudySpaceRepository(self.db)
            series = SeriesRepository(self.db)
            personal = PersonalRepository(self.db)
            legacy = self.legacy
            w.university(planner.university)
            w.degree(planner.degree)
            goals: dict[str, list] = {}
            for i, op in enumerate(ops):
                if cancel and cancel():
                    raise _Cancelled()
                self._apply_op(op, w, cx, evals, material, spaces, series, personal, stored,
                               planner, goals, fts_rows)
                if op.action == "migrate" and "#" not in op.table:
                    legacy.map(SOURCE_SYSTEM, op.table, op.source_id, op.target_id, cx=cx)
                elif op.action == "preserve":
                    legacy.keep(SOURCE_SYSTEM, op.table, op.source_id,
                                _jsonable(op.obj), target_id=op.target_id,
                                deferred_to=op.deferred_to, reason=op.reason, cx=cx)
                if i % 200 == 0:
                    tick("write", i + 1, len(ops))
            for space_id, items in goals.items():
                base = cx.execute("SELECT COUNT(*) FROM study_space_goals WHERE space_id=?",
                                  (space_id,)).fetchone()[0]
                for g in items:
                    cx.execute("INSERT INTO study_space_goals(space_id, ord, text, done)"
                               " VALUES (?,?,?,?)", (space_id, base + g.order - min(
                                   x.order for x in items), g.text, int(g.done)))
            if opts.degree_total_credits:
                personal.set_setting("degree.total_credits", opts.degree_total_credits, cx=cx)
            if opts.final_project_names:
                personal.set_setting("degree.final_project_names",
                                     "|".join(opts.final_project_names), cx=cx)
            w.counters(planner.alloc.snapshot())
            cx.execute("COMMIT")
        except BaseException:
            cx.execute("ROLLBACK")
            raise
        finally:
            cx.close()
        tick("write", len(ops), len(ops))
        return fts_rows

    def _apply_op(self, op: Op, w: TargetWriter, cx, evals, material, spaces, series,
                  personal, stored, planner, goals, fts_rows) -> None:
        if op.action != "migrate":
            return
        t = op.table
        if t == "anio":
            w.year(op.obj)
        elif t == "cuatrimestre":
            w.term(op.obj)
        elif t == "asignatura":
            w.subject(op.obj)
        elif t == "asignatura_prerrequisito":
            w.prerequisite(*op.obj)
        elif t == "profesor":
            prof, link = op.obj
            w.professor(prof)
            w.staff(link)
        elif t in ("esquema_evaluacion", "esquema_evaluacion#implicit"):
            subj, name, order = op.obj
            cx.execute("INSERT INTO assessment_schemes(stable_id, subject_id, name, ord)"
                       " VALUES (?,?,?,?)", (op.target_id, subj, name, order))
        elif t == "bloque_evaluacion":
            sch, name, weight, order = op.obj
            cx.execute("INSERT INTO assessment_blocks(stable_id, scheme_id, name, weight, ord)"
                       " VALUES (?,?,?,?,?)", (op.target_id, sch, name, weight, order))
        elif t == "componente_evaluacion":
            subj, sch, blk, c = op.obj
            cx.execute("INSERT INTO assessment_components(stable_id, subject_id, scheme_id,"
                       " block_id, name, kind, weight, score, min_grade, ord)"
                       " VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (c.stable_id, subj, sch, blk, c.name, c.kind, str(c.weight),
                        None if c.score is None else str(c.score),
                        None if c.min_grade is None else str(c.min_grade), c.order))
        elif t == "recurso_externo":
            material.add_external(op.obj, cx=cx)
        elif t == "grupo_documento":
            material.add_group(op.obj, cx=cx)
        elif t == "documento":
            cd, prog, page_rows = op.obj
            h, size = stored[op.source_id]
            if not op.extra["dup"] and not cx.execute(
                    "SELECT 1 FROM resources WHERE stable_id=?", (op.target_id,)).fetchone():
                prov = R.ResourceProvenance(
                    "migration", f"{SOURCE_SYSTEM}:documento/{op.source_id}",
                    op.extra["original"], h, cd.added_at or "", "gestion-migration", "1",
                    "deferred" if op.extra["opaque"] else "ok", 0,
                    "opaque: refused by F2 adapters" if op.extra["opaque"] else "")
                ver = R.ResourceVersion(op.target_id, 1, h, size, prov)
                self.records.save_new(R.Resource(op.target_id, op.extra["kind"], cd.filename,
                                                 1, [ver]), cx)
                text = "\n".join(p["contenido"] or "" for p in page_rows)
                if not text and not op.extra["opaque"] and op.extra["kind"] in (
                        "text", "markdown", "html"):
                    try:
                        text = adapter_for(op.extra["kind"], cd.filename).extract(
                            self.blobs.get_bytes(h), cd.filename).text
                    except Exception:  # extraction is derived; report via empty index
                        text = ""
                fts_rows.append((op.target_id, op.extra["kind"], cd.filename, text))
            material.link(cd, cx=cx)
            if not op.extra["dup"]:
                material.set_progress(prog, cx=cx)
                if page_rows:
                    material.set_pages(op.target_id, [(int(p["numero_pagina"]), p["contenido"]
                                                       or "") for p in page_rows], cx=cx)
        elif t == "tarea_evento":
            w.task(op.obj)
        elif t == "espacio_estudio":
            sp, created = op.obj
            spaces.create(op.target_id, sp, created, cx=cx)
        elif t == "espacio_estudio_documento":
            spaces.add_document(op.obj, cx=cx)
        elif t == "objetivo_espacio":
            goals.setdefault(op.obj.space_id, []).append(op.obj)
        elif t == "horario_clase":
            ser, notes = op.obj
            series.add(op.target_id, ser.subject_id, ser.kind, ser.weekday, ser.start, ser.end,
                       ser.first_day, ser.last_day, ser.interval_weeks, ser.room, notes, cx=cx)
        elif t == "hito":
            personal.add_milestone(op.obj, cx=cx)
        elif t == "nota_rapida":
            personal.add_note(op.obj, cx=cx)
        elif t == "concepto":
            personal.add_concept(op.obj, cx=cx)
        elif t == "sesion_estudio":
            w.session(op.obj)
        elif t == "dia_actividad":
            personal.add_activity_day(op.obj, cx=cx)
        elif t == "configuracion_app":
            for k in sorted(op.obj):
                personal.set_setting(k, op.obj[k], cx=cx)
        elif t == "pagina_texto":
            pass  # written with its document (document_pages + FTS body)
        else:
            raise MigrationError(f"no writer for {t}", code="AC-MIG-001")

    # validation ---------------------------------------------------------------
    def validate(self, snap: LegacySnapshot, planner: _Planner | None = None) -> list[str]:
        """Post-migration proof: every source row accounted for + relations."""
        failures: list[str] = []
        mapped = self.legacy.all_mapped(SOURCE_SYSTEM)
        preserved = {(p["source_table"], p["source_id"]) for p in self.legacy.payloads(
            SOURCE_SYSTEM)}
        for t in TABLES:
            for row in snap.tables.get(t, []):
                key = (t, _row_id(t, row))
                if key not in mapped and key not in preserved:
                    failures.append(f"unaccounted source row {t}#{key[1]}")
        cx = self.db.connect()
        try:
            checks = {
                "subject term missing": "SELECT s.stable_id FROM subjects s WHERE s.term_id<>''"
                " AND NOT EXISTS (SELECT 1 FROM terms t WHERE t.stable_id=s.term_id)",
                "component scheme missing": "SELECT c.stable_id FROM assessment_components c"
                " WHERE NOT EXISTS (SELECT 1 FROM assessment_schemes s WHERE"
                " s.stable_id=c.scheme_id)",
                "component block missing": "SELECT c.stable_id FROM assessment_components c"
                " WHERE c.block_id<>'' AND NOT EXISTS (SELECT 1 FROM assessment_blocks b"
                " WHERE b.stable_id=c.block_id)",
                "course document subject missing": "SELECT d.resource_id FROM course_documents d"
                " WHERE NOT EXISTS (SELECT 1 FROM subjects s WHERE s.stable_id=d.subject_id)",
                "course document resource missing": "SELECT d.resource_id FROM course_documents"
                " d WHERE NOT EXISTS (SELECT 1 FROM resources r WHERE"
                " r.stable_id=d.resource_id)",
                "task subject missing": "SELECT t.stable_id FROM tasks t WHERE t.subject_id<>''"
                " AND NOT EXISTS (SELECT 1 FROM subjects s WHERE s.stable_id=t.subject_id)",
                "space task missing": "SELECT s.stable_id FROM study_spaces s WHERE"
                " s.stable_id<>'' AND NOT EXISTS (SELECT 1 FROM tasks t WHERE"
                " t.stable_id=s.exam_task_id)",
                "staff professor missing": "SELECT l.subject_id FROM subject_staff l WHERE NOT"
                " EXISTS (SELECT 1 FROM professors p WHERE p.stable_id=l.professor_id)",
                "prerequisite endpoint missing": "SELECT p.subject_id FROM prerequisites p WHERE"
                " NOT EXISTS (SELECT 1 FROM subjects s WHERE s.stable_id=p.requires_id)",
                "resource blob hash mismatch": "SELECT r.stable_id FROM resources r JOIN"
                " resource_versions v ON v.stable_id=r.stable_id AND"
                " v.version=r.current_version WHERE v.origin='migration' AND"
                " length(v.content_hash)<>64",
            }
            for label, sql in checks.items():
                bad = [r[0] for r in cx.execute(sql).fetchall()]
                if bad:
                    failures.append(f"{label}: {sorted(bad)[:5]}")
            for rid, h in cx.execute("SELECT v.stable_id, v.content_hash FROM resource_versions"
                                     " v WHERE v.origin='migration' ORDER BY v.stable_id"):
                if not self.blobs.exists(h):
                    failures.append(f"CAS blob missing for {rid}")
        finally:
            cx.close()
        return failures

    # evaluation equivalence -----------------------------------------------------
    def _eval_check(self, snap: LegacySnapshot, planner: _Planner) -> dict:
        """Gestion float semantics vs AcademicCore Decimal on every subject."""
        from academic_core.application.gestion_oracle import gestion_estado_notas
        comps = snap.tables.get("componente_evaluacion", [])
        by_subject: dict[str, list[EV.AssessmentScheme]] = {}
        blocks: dict[str, EV.AssessmentBlock] = {}
        scheme_objs: dict[str, EV.AssessmentScheme] = {}
        for op in planner.ops:
            if op.action != "migrate":
                continue
            if op.table.startswith("esquema_evaluacion"):
                subj, name, order = op.obj
                sc = EV.AssessmentScheme(op.target_id, subj, name, order=order)
                scheme_objs[op.target_id] = sc
                by_subject.setdefault(subj, []).append(sc)
            elif op.table == "bloque_evaluacion":
                sch, name, weight, order = op.obj
                b = EV.AssessmentBlock(op.target_id, name, weight, order=order)
                blocks[op.target_id] = b
                if sch in scheme_objs:
                    scheme_objs[sch].blocks.append(b)
            elif op.table == "componente_evaluacion":
                subj, sch, blk, c = op.obj
                if blk and blk in blocks:
                    blocks[blk].components.append(c)
                elif sch in scheme_objs:
                    scheme_objs[sch].components.append(c)
        checked = mismatched = 0
        diffs: list[str] = []
        for r in snap.tables.get("asignatura", []):
            sid = planner.target("asignatura", r["id"])
            if not sid or ("asignatura", str(r["id"])) in planner.mapped:
                continue
            oracle = gestion_estado_notas(r, snap.tables.get("esquema_evaluacion", []),
                                          snap.tables.get("bloque_evaluacion", []), comps)
            mine = EV.evaluate_subject(by_subject.get(sid, []), dec_text(r.get("nota_final")),
                                       r.get("regla_esquemas") or "maximo")
            checked += 1
            same_grade = (oracle["nota_actual"] is None and mine.grade is None) or (
                oracle["nota_actual"] is not None and mine.grade is not None and
                abs(Decimal(str(oracle["nota_actual"])) - mine.grade) <= Decimal("0.0001"))
            if oracle["estado_notas"] != mine.state or not same_grade:
                mismatched += 1
                diffs.append(f"{sid}: gestion={oracle['estado_notas']}/{oracle['nota_actual']}"
                             f" core={mine.state}/{mine.grade}")
        return {"subjects_checked": checked, "mismatches": mismatched, "diffs": diffs[:20]}


def _jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (bytes, bytearray)):
        return {"hex": bytes(obj).hex()}
    return obj
