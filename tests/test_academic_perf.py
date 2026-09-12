"""Academic performance smoke: tree load, deadline/grade queries, reopen."""
import time
from datetime import date, datetime
from decimal import Decimal

from academic_core.application import AcademicApp
from academic_core.config import Settings
from academic_core.domain import entities as E
from academic_core.domain import results as R


def _core(tmp_path):
    import os
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "data")
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    return core


def test_perf_academic_scale(tmp_path):
    core = _core(tmp_path)
    ac = core.academic
    ac.add_university(E.University("university:u", "U"))
    ac.add_degree(E.Degree("degree:g", "G", "university:u"))
    ac.add_year(E.AcademicYear("year:2025-26", "2025-26", "degree:g"))
    ac.add_term(E.Term("term:c1", "C1", "cuatrimestre", 1, "year:2025-26"))
    t0 = time.perf_counter()
    for i in range(30):
        sid = f"subject:s{i:02d}"
        ac.add_subject(E.Subject(sid, "", f"S{i}", f"S{i}", term_id="term:c1"))
        for j in range(10):
            core.planning.add_task(E.Task(
                f"task:s{i:02d}:task:{j + 1:05d}", sid, f"T{j}",
                "entrega", date(2026, 3, 1)))
        core.gradebook.record(sid, R.Grade("p", "7", R.N_10, Decimal(100)))
    create_dt = time.perf_counter() - t0
    t0 = time.perf_counter()
    tree = core.queries.tree()
    up = core.queries.upcoming_deadlines(date(2026, 1, 1), limit=50)
    t1 = time.perf_counter() - t0
    assert len(tree[0]["degrees"][0]["years"][0]["terms"][0]["subjects"]) == 30
    assert len(up) == 50
    print(f"\n[perf] 30 subjects/300 tasks create: {create_dt:.2f}s; "
          f"tree+upcoming: {t1:.2f}s")
    assert create_dt < 20 and t1 < 10
    t0 = time.perf_counter()
    core2 = _core(tmp_path)
    assert len(core2.queries.tree()[0]["degrees"][0]["years"][0]["terms"][0]["subjects"]) == 30
    print(f"[perf] reopen: {time.perf_counter() - t0:.2f}s")
