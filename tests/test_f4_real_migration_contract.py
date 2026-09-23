# SPDX-License-Identifier: MIT
"""F4.1 closure — certification contract: every gate criterion is computed,
the verdict is PASS only if all are PASS, and the source is untouched."""
import json

import pytest

from gestion_real_harness import SOURCES, certified

REQUIRED = {"source_untouched", "migration_valid", "no_loss", "documents_real_hashes",
            "evaluation_real", "home_real", "career_real", "relations_real",
            "backup_verify_restore", "idempotence", "determinism"}


@pytest.mark.parametrize("source", SOURCES)
def test_all_criteria_pass(source):
    rep, _ = certified(source)
    assert set(rep["criteria"]) == REQUIRED
    failed = {k: v for k, v in rep["criteria"].items() if v["result"] != "PASS"}
    assert failed == {} and rep["verdict"] == "PASS"


@pytest.mark.parametrize("source", SOURCES)
def test_source_untouched_and_report_anonymized(source):
    rep, _ = certified(source)
    ev = rep["criteria"]["source_untouched"]["evidence"]
    assert ev["db_sha256_before"] == ev["db_sha256_after"]
    assert ev["documents_digest_before"] == ev["documents_digest_after"]
    text = json.dumps(rep, ensure_ascii=False)
    assert "@" not in text  # no e-mails
    for leak in ("ruta_local", "nombre_archivo", "correo", "/home/", "C:\\\\"):
        assert leak not in text


def test_harness_fails_on_missing_documents(tmp_path):
    """The fixture with a missing file + traversal row must NOT certify."""
    from pathlib import Path

    import gestion_legacy_fixture as G
    from academic_core.application.gestion_certification import Certifier
    db, root = G.build(tmp_path / "legacy")
    rep = Certifier(db, root, tmp_path / "w").run(seeds=())
    assert rep["criteria"]["documents_real_hashes"]["result"] == "FAIL"
    assert rep["verdict"] == "FAIL"
    rep2 = Certifier(db, None, Path(tmp_path / "w2")).run(seeds=())
    assert rep2["verdict"] == "FAIL"  # no documents dir -> cannot certify
