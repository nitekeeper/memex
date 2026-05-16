import hashlib
import pytest
from scripts.agents import archivist


def test_archive_returns_path_and_hash(tmp_memex_home):
    payload = b"hello world\n"
    result = archivist.archive(payload, filename="hello.txt")
    # Hash is computed over the canonical form (CRLF→LF, outer whitespace stripped),
    # matching test_archive_canonicalizes_text_before_hashing.
    assert result["hash"] == hashlib.sha256(b"hello world").hexdigest()
    # Filename pattern is <stem>-<hash8><suffix>, so ends with the suffix.
    assert result["path"].endswith(".txt")
    assert (tmp_memex_home / "raw").is_dir()


def test_archive_writes_to_hash_prefixed_subdir(tmp_memex_home):
    payload = b"unique-content-A"
    result = archivist.archive(payload, filename="a.txt")
    from pathlib import Path
    path = Path(result["path"])
    # Should be under ~/.memex/raw/<hash-prefix>/a.txt
    assert path.parent.parent == tmp_memex_home / "raw"
    assert len(path.parent.name) == 2  # 2-char hash prefix


def test_archive_is_idempotent_on_same_content(tmp_memex_home):
    payload = b"same content"
    r1 = archivist.archive(payload, filename="x.txt")
    r2 = archivist.archive(payload, filename="x.txt")
    assert r1["path"] == r2["path"]
    assert r1["hash"] == r2["hash"]


def test_archive_versions_on_filename_collision_different_content(tmp_memex_home):
    """Same filename, different content → both preserved with different hashes."""
    r1 = archivist.archive(b"version 1", filename="doc.md")
    r2 = archivist.archive(b"version 2", filename="doc.md")
    assert r1["path"] != r2["path"]
    assert r1["hash"] != r2["hash"]


def test_archive_canonicalizes_text_before_hashing(tmp_memex_home):
    """Canonicalization strips leading/trailing whitespace and normalizes line endings."""
    a = archivist.archive(b"hello\r\nworld\r\n", filename="x.txt")
    b = archivist.archive(b"hello\nworld\n", filename="x.txt")
    assert a["hash"] == b["hash"]
