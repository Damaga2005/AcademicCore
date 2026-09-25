# SPDX-License-Identifier: MIT
"""F13-ext: sincronización determinista entre 2 PCs (LWW + log, sin CRDT)."""

from academic_core.domain import sync as S


A = "a" * 32
B = "b" * 32


def _rec(rid="pref:f42.theme", kind="preference", payload=None, ms=1000, dev=None):
    dev = dev or A
    return S.make_record(rid, kind, payload if payload is not None else {"value": "claro"},
                         ms, dev, dev)


RID = "pref:f42.theme"


def test_01_no_changes_noop():
    s = {RID: _rec(RID, "preference", {"value": "claro"}, 1000, A)}
    r = {RID: _rec(RID, "preference", {"value": "claro"}, 1000, A)}
    out, log = S.sync(s, r, A, now_ms=2000)
    assert out[RID].digest == s[RID].digest
    assert len(log) == 1 and log[0].operation == "unchanged" and not log[0].conflict


def test_02_change_only_a_propagates():
    s = {RID: _rec(payload={"value": "oscuro"}, ms=2000, dev=A)}
    r = {RID: _rec(payload={"value": "claro"}, ms=1000, dev=A)}
    # _rec default rid is pref:f42.theme; fix keys to real resource_id
    s = {v.resource_id: v for v in s.values()}
    r = {v.resource_id: v for v in r.values()}
    out, log = S.sync(s, r, A, now_ms=3000)
    assert out[RID].payload == {"value": "oscuro"}
    assert log[0].operation == "local-wins" and log[0].conflict


def test_03_change_only_b_propagates():
    s = {RID: _rec(payload={"value": "claro"}, ms=1000, dev=A)}
    r = {RID: _rec(payload={"value": "oscuro"}, ms=2000, dev=B)}
    s = {v.resource_id: v for v in s.values()}
    r = {v.resource_id: v for v in r.values()}
    out, log = S.sync(s, r, A, now_ms=3000)
    assert out[RID].payload == {"value": "oscuro"}
    assert log[0].operation == "remote-wins" and log[0].winner == "remote"


def test_04_same_change_idempotent():
    s = {RID: _rec(payload={"value": "x"}, ms=2000, dev=A)}
    r = {RID: _rec(payload={"value": "x"}, ms=3000, dev=B)}
    s = {v.resource_id: v for v in s.values()}
    r = {v.resource_id: v for v in r.values()}
    out, log = S.sync(s, r, A, now_ms=4000)
    assert out[RID].digest == s[RID].digest == r[RID].digest
    assert log[0].operation == "same"
    out2, _ = S.sync(out, r, A, now_ms=4000)
    assert out2[RID].digest == out[RID].digest


def test_05_conflict_lww_plus_log():
    s = {RID: _rec(payload={"value": "A"}, ms=2000, dev=A)}
    r = {RID: _rec(payload={"value": "B"}, ms=3000, dev=B)}
    s = {v.resource_id: v for v in s.values()}
    r = {v.resource_id: v for v in r.values()}
    out, log = S.sync(s, r, A, now_ms=4000)
    assert out[RID].payload == {"value": "B"}
    e = log[0]
    assert e.conflict and e.winner == "remote"
    for f in ("event_id", "device_id", "resource_id", "operation", "local_version",
              "remote_version", "winner", "result", "digest_before", "digest_after",
              "protocol_version"):
        assert getattr(e, f)


def test_06_equal_timestamps_deterministic_tiebreak():
    s = {RID: _rec(payload={"value": "A"}, ms=5000, dev=A)}
    r = {RID: _rec(payload={"value": "B"}, ms=5000, dev=B)}
    s = {v.resource_id: v for v in s.values()}
    r = {v.resource_id: v for v in r.values()}
    out1, _ = S.sync(s, r, A, now_ms=6000)
    out2, _ = S.sync(s, r, A, now_ms=6000)
    assert out1[RID].digest == out2[RID].digest
    # 'b'*32 > 'a'*32 -> remote wins deterministically
    assert out1[RID].payload == {"value": "B"}


def test_07_skewed_clocks_defined_behaviour():
    # Remote clock behind but version smaller -> local wins; still deterministic.
    s = {RID: _rec(payload={"value": "new"}, ms=9000, dev=A)}
    r = {RID: _rec(payload={"value": "old"}, ms=1000, dev=B)}
    s = {v.resource_id: v for v in s.values()}
    r = {v.resource_id: v for v in r.values()}
    out, log = S.sync(s, r, A, now_ms=9500)
    assert out[RID].payload == {"value": "new"}
    assert log[0].winner == "local"


def test_08_delete_tombstone_propagates():
    live = _rec("note:mi-nota", "quick_note", {"text": "hola"}, ms=1000, dev=A)
    tomb = S.delete_record("note:mi-nota", "quick_note", ms=2000, device_id=B)
    out, log = S.sync({"note:mi-nota": live}, {"note:mi-nota": tomb}, A, now_ms=3000)
    assert out["note:mi-nota"].deleted is True
    assert log[0].conflict


def test_09_repeat_idempotent():
    s = {RID: _rec(payload={"value": "A"}, ms=1000, dev=A)}
    r = {RID: _rec(payload={"value": "B"}, ms=2000, dev=B)}
    s = {v.resource_id: v for v in s.values()}
    r = {v.resource_id: v for v in r.values()}
    out, _ = S.sync(s, r, A, now_ms=3000)
    out2, log2 = S.sync(out, r, A, now_ms=3000)
    assert out2[RID].digest == out[RID].digest
    assert all(e.operation in ("unchanged", "same") for e in log2)
    # invariant: sync(sync(A,B),B) == sync(A,B)
    assert S.sync(out, r, A, now_ms=3000)[0][RID].digest == out[RID].digest


def test_10_corrupt_snapshot_does_not_destroy_valid_state():
    rec = _rec()
    s = {rec.resource_id: rec}
    with_corr = dict(s)
    try:
        S.sync(s, {rec.resource_id: "CORRUPT"}, A, now_ms=2000)
    except Exception:
        pass
    else:  # pragma: no cover - sync must reject corrupt input
        raise AssertionError("corrupt remote must raise")
    assert with_corr[rec.resource_id].digest == s[rec.resource_id].digest


def test_11_digest_canonical_stable():
    r1 = _rec(payload={"b": 1, "a": [1, 2]}, ms=1000, dev=A)
    r2 = _rec(payload={"a": [1, 2], "b": 1}, ms=2000, dev=B)
    assert r1.digest == r2.digest == S.canonical_digest(r1.kind, r1.resource_id, r1.payload, False)


def test_12_transport_roundtrip_and_reject(tmp_path):
    from academic_core.infrastructure.sync_transport import FileTransport
    t = FileTransport()
    rec = _rec()
    snap = S.export_snapshot({rec.resource_id: rec}, A, now_ms=2000)
    p = tmp_path / "sync.json"
    t.save(snap, p)
    loaded = t.load(p)
    assert loaded["device_id"] == A
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema":"nope"}', encoding="utf-8")
    try:
        t.load(bad)
    except Exception:
        pass
    else:  # pragma: no cover
        raise AssertionError("bad snapshot must raise")
