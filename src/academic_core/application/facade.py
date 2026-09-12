"""Academic facade (Phase 4): the ONLY wiring point the UI may use.

UI imports application + domain. Never infrastructure, sqlite3, CAS, FTS.
"""

from __future__ import annotations

from pathlib import Path

from academic_core.application.academic_io import AcademicIO
from academic_core.application.backup import BackupService
from academic_core.application.documents import DocumentService
from academic_core.application.ingest import IngestionService
from academic_core.application.queries import AcademicQueries
from academic_core.application.search import SimpleSearchService
from academic_core.application.security import AppLock
from academic_core.application.services import (
    AcademicService, GradingService, ResultsService, ScheduleService,
)
from academic_core.config import Settings
from academic_core.infrastructure import (
    AcademicRepository, Database, FileBlobStore, FtsResourceIndexer,
    GradebookRepository, GradingRepository, PlanningRepository,
    SqliteResourceRecords, StudyRepository,
)


class AcademicApp:
    """Owns Database, repositories and services for one data directory."""

    def __init__(self, settings: Settings):
        self.settings = settings
        data = Path(settings.storage.location)
        self.db = Database(data / "academic.db")
        cas_root = Path(settings.ingest.cas_dir or data / "cas")
        self.blobs = FileBlobStore(cas_root)
        self.academic = AcademicRepository(self.db)
        self.planning = PlanningRepository(self.db)
        self.grading_repo = GradingRepository(self.db)
        self.gradebook = GradebookRepository(self.db)
        self.study = StudyRepository(self.db)
        self.records = SqliteResourceRecords(self.db)
        self.fts = FtsResourceIndexer(self.db)
        self.svc = AcademicService(self.academic)
        self.grading = GradingService(self.grading_repo)
        self.results = ResultsService(self.gradebook)
        self.schedule = ScheduleService(self.planning)
        self.queries = AcademicQueries(self.academic, self.planning,
                                       self.grading_repo, self.gradebook)
        self.search = SimpleSearchService(self.academic, self.planning)
        self.ingest = IngestionService(
            self.blobs, self.records, self.fts, self.academic, self.planning,
            max_bytes=settings.ingest.max_bytes)
        self.documents = DocumentService(self.blobs, self.records, self.db)
        self.backup = BackupService(self.db.path)
        self.io = AcademicIO(self)
        self.lock = AppLock()
        from academic_core.pdf.stirling import StirlingRuntime
        self.stirling = StirlingRuntime(settings.tools.stirling_url)

    def ensure_demo(self) -> None:
        """Generic, deletable demo hierarchy (never institution-specific)."""
        from datetime import date as _date

        from academic_core.domain import entities as _E
        if self.academic.list_universities():
            return
        self.academic.add_university(_E.University("university:demo", "Universidad Demo"))
        self.academic.add_degree(_E.Degree("degree:demo-grado", "Grado Demo", "university:demo"))
        self.academic.add_year(_E.AcademicYear("year:2025-26", "2025-26", "degree:demo-grado"))
        self.academic.add_term(_E.Term("term:demo-c1", "Cuatrimestre 1", "cuatrimestre", 1,
                                       "year:2025-26", _date(2025, 9, 1), _date(2026, 1, 31)))
