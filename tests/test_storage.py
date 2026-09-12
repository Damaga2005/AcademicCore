"""Integration: SQLite metadata + CAS bytes round-trip; blobs NOT in SQLite."""
from academic_core.storage import Store


def test_cas_roundtrip(tmp_path):
    st = Store(tmp_path / "m.db", tmp_path / "cas")
    h = st.put_bytes(b"%PDF-1.7 fake")
    assert st.get_bytes(h) == b"%PDF-1.7 fake"
    st.put_entity("resource:sistemes-de-mesura:r:00192", "resource",
                  "sistemes-de-mesura", "{}", h)
    ent = st.get_entity("resource:sistemes-de-mesura:r:00192")
    assert ent["cas_hash"] == h


def test_no_blob_in_sqlite(tmp_path):
    st = Store(tmp_path / "m.db", tmp_path / "cas")
    big = b"x" * 1_000_000
    h = st.put_bytes(big)
    import sqlite3
    cx = sqlite3.connect(tmp_path / "m.db")
    dump = b"".join(r[0] or b"" for r in cx.execute(
        "SELECT CAST(payload AS BLOB) FROM entities").fetchall())
    assert big not in dump
    assert (tmp_path / "cas" / h[0:2] / h[2:4] / h).exists()
