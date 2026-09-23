# SPDX-License-Identifier: MIT
"""F4.1 closure — relations survive: professors, evaluation, groups, tasks
(incl. subject-less), series, study spaces (+documents, goals), sessions,
activity days, milestones, notes, concepts, Wuolah/Studocu links."""
import pytest

from gestion_real_harness import SOURCES, certified


@pytest.mark.parametrize("source", SOURCES)
def test_relations_and_external_resources(source):
    rep, _ = certified(source)
    rel = rep["relations"]
    assert rel["differences"] == {} and rel["unmapped_subjects"] == 0
    assert rel["target"]["external"] == rel["target"]["external_distinct_urls"]
    assert rel["external_by_provider"] == rep["inventory"]["external_by_provider"]
    assert rel["target"]["tasks_without_subject"] == rep["inventory"]["tasks_without_subject"]


@pytest.mark.parametrize("source", SOURCES)
def test_professor_identity_is_evidence_based(source):
    rep, _ = certified(source)
    pi = rep["migration"]["professor_identity"]
    assert pi["source_rows"] == rep["inventory"]["tables"]["profesor"]
    # every non-merged row keeps its own identity; merges need e-mail evidence
    assert pi["identities"] + pi["merged_by_email_evidence"] + (
        rep["migration"]["counts"]["profesor"]["preserved"]) == pi["source_rows"]
