"""F8-N Virtual Laboratory — same-version deterministic replay.

``save -> load -> replay -> compare``: a document stores schema +
engine versions; replay requires all to equal the running software
(``VERSION_MISMATCH``, no execution) unless ``allow_version_mismatch``
is set (executed, but marked not comparable). Cross-version
equivalence is not claimed. Notes/annotations never affect replay.
"""
from .model import (
    LoadStatus,
    ReplayResult,
    ReplayStatus,
)
from .serialize import (
    SCHEMA_MISMATCH,
    LoadResult,
    experiment_id,
    from_document,
    loads_document,
    run_digest,
)

_EQUIV = ReplayStatus.EQUIVALENT.value
_DIFFERS = ReplayStatus.RESULT_DIFFERS.value
_VERSION = ReplayStatus.VERSION_MISMATCH.value
_SCHEMA = ReplayStatus.SCHEMA_MISMATCH.value
_INVALID = ReplayStatus.INVALID_SERIALIZATION.value


def current_engine_versions():
    from .run import ENGINE_VERSIONS
    return dict(ENGINE_VERSIONS)


def check_versions_compatible(session_versions, allow_mismatch=False):
    """Compare stored engine versions + schema against the running stack."""
    from .run import ENGINE_VERSIONS
    running = dict(ENGINE_VERSIONS)
    problems = []
    for key, value in (session_versions or {}).items():
        if running.get(key) != value:
            problems.append(f"{key}: stored {value!r} != running {running.get(key)!r}")
    for key in running:
        if key not in (session_versions or {}):
            problems.append(f"{key}: not recorded in document")
    return problems


def replay_run(session, run_id, allow_version_mismatch=False):
    """Re-execute the run's experiment and compare ``result_digest``.

    The session is never mutated. ``EQUIVALENT`` means bit-identical
    digests under the same versions; ``RESULT_DIFFERS`` carries the
    first differing JSON path.
    """
    target = None
    definition = None
    for record in session.records:
        for run in record.runs:
            if run.run_id == run_id:
                target = run
                break
    if target is None:
        return ReplayResult(run_id, _INVALID, False, "", "",
                            "", "unknown run")
    for existing in session.experiments:
        if experiment_id(existing, session.circuit) == target.experiment_id:
            definition = existing
            break
    if definition is None:
        return ReplayResult(run_id, _INVALID, False, "", "",
                            "", "experiment missing for run")
    stored_versions = dict((target.provenance or {}).get("engine_versions", {}))
    problems = check_versions_compatible(stored_versions)
    if problems and not allow_version_mismatch:
        return ReplayResult(run_id, _VERSION, False, target.result_digest, "",
                            "", "; ".join(problems))
    from .run import execute_run
    prior = sum(1 for record in session.records for r in record.runs
                if r.experiment_id == target.experiment_id)
    # Re-execution must not depend on run count: execute with a scratch
    # index, then compare digests only (run_id excluded from digests).
    fresh, _payload = execute_run(session.circuit, definition,
                                  target.experiment_id, prior + 1,
                                  session.session_id)
    comparable = not problems
    if fresh.result_digest == target.result_digest:
        return ReplayResult(run_id, _EQUIV, comparable, target.result_digest,
                            fresh.result_digest, "", "")
    diff = _first_difference(target, fresh)
    return ReplayResult(run_id, _DIFFERS, comparable, target.result_digest,
                        fresh.result_digest, diff,
                        "result digest differs")


def _first_difference(old, new):
    if old.status != new.status:
        return "status"
    if old.engine_status != new.engine_status:
        return "engine_status"
    old_m = {m.key: (m.status, m.value) for m in old.measurements}
    new_m = {m.key: (m.status, m.value) for m in new.measurements}
    if set(old_m) != set(new_m):
        return "measurements.keys"
    for key in sorted(old_m):
        if old_m[key] != new_m[key]:
            return f"measurements[{key}]"
    old_r = {r.key: (r.status, r.reason) for r in old.readings}
    new_r = {r.key: (r.status, r.reason) for r in new.readings}
    if old_r != new_r:
        return "readings"
    return "result"
