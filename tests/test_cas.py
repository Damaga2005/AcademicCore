"""CAS: SHA-256, dedup, reopen, integrity, atomicity, streaming, safety."""
import hashlib

import pytest

from academic_core.infrastructure.cas import (
    BlobNotFound, CorruptBlob, FileBlobStore, TooLarge,
)


def test_known_sha256_and_roundtrip(tmp_path):
    blobs = FileBlobStore(tmp_path / "cas")
    h = blobs.put_bytes(b"abc")
    assert h == hashlib.sha256(b"abc").hexdigest()
    assert h == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert blobs.get_bytes(h) == b"abc"
    assert blobs.exists(h)


def test_dedup_single_blob(tmp_path):
    blobs = FileBlobStore(tmp_path / "cas")
    assert blobs.put_bytes(b"same") == blobs.put_bytes(b"same")
    files = list((tmp_path / "cas").rglob("*"))
    assert sum(1 for f in files if f.is_file()) == 1


def test_survives_reopen(tmp_path):
    h = FileBlobStore(tmp_path / "cas").put_bytes(b"persist me")
    assert FileBlobStore(tmp_path / "cas").get_bytes(h) == b"persist me"


def test_corruption_detected(tmp_path):
    blobs = FileBlobStore(tmp_path / "cas")
    h = blobs.put_bytes(b"pristine")
    target = tmp_path / "cas" / h[0:2] / h[2:4] / h
    target.write_bytes(b"tampered")
    with pytest.raises(CorruptBlob):
        blobs.get_bytes(h)


def test_missing_and_invalid(tmp_path):
    blobs = FileBlobStore(tmp_path / "cas")
    with pytest.raises(BlobNotFound):
        blobs.get_bytes("00" * 32)
    with pytest.raises(ValueError):
        blobs.get_bytes("../../etc/passwd")
    with pytest.raises(ValueError):
        blobs.get_bytes("not-a-hash")
    assert blobs.exists("00" * 32) is False
    assert blobs.delete("00" * 32) is False


def test_delete_explicit(tmp_path):
    blobs = FileBlobStore(tmp_path / "cas")
    h = blobs.put_bytes(b"bye")
    assert blobs.delete(h) is True
    assert blobs.exists(h) is False


def test_put_file_streaming_with_cap(tmp_path):
    src = tmp_path / "big.bin"
    src.write_bytes(b"x" * (3 << 20))
    blobs = FileBlobStore(tmp_path / "cas")
    h, size = blobs.put_file(src, 10 << 20)
    assert size == 3 << 20
    assert blobs.get_bytes(h) == b"x" * (3 << 20)


def test_put_file_too_large_leaves_no_trace(tmp_path):
    src = tmp_path / "big.bin"
    src.write_bytes(b"x" * 16)
    blobs = FileBlobStore(tmp_path / "cas")
    with pytest.raises(TooLarge):
        blobs.put_file(src, 8)
    assert list((tmp_path / "cas" / "tmp").iterdir()) == []
