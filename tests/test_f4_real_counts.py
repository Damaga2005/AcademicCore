# SPDX-License-Identifier: MIT
"""F4.1 closure — real input counts and the no-loss table."""
import pytest

from gestion_real_harness import SOURCES, certified


@pytest.mark.parametrize("source", SOURCES)
def test_inventory_and_no_loss_table(source):
    rep, expected = certified(source)
    inv = rep["inventory"]["tables"]
    if expected:
        assert inv == expected
    for row in rep["no_loss"]:
        assert row["difference"] == 0, row
        assert row["input"] == inv[row["entity"]]
        assert row["migrated"] + row["preserved"] == row["input"]


@pytest.mark.parametrize("source", SOURCES)
def test_components_migrate_as_they_exist(source):
    """168 vs 164: migrate what really exists, nothing more, nothing less."""
    rep, _ = certified(source)
    c = rep["migration"]["counts"]["componente_evaluacion"]
    assert c["migrated"] == rep["inventory"]["tables"]["componente_evaluacion"]
    assert rep["relations"]["target"]["components"] == c["migrated"]
    assert rep["relations"]["target"]["blocks"] == rep["inventory"]["tables"]["bloque_evaluacion"]
