"""test_mcp_units.py — unit tests for the pieces under mcp/ (no server spawned).

Covers the read-only statement guard (db.validate_readonly_sql /
strip_literals_and_comments), document path helpers, corrected-value matching,
and ro_conn() enforcement — including the regression case of a WAL database
whose -shm file is absent (the lazy-failure fallback the docstring promises).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import db
import documents
import server


# ------------------------------------------------------- read-only SQL guard


def test_guard_accepts_read_statements():
    allowed = [
        "SELECT 1",
        "  select 1 ",
        "SELECT * FROM v_spills WHERE dataset_id = 'sample'",
        "WITH x AS (SELECT 1 AS a) SELECT a FROM x",
        "EXPLAIN QUERY PLAN SELECT 1",
        "SELECT ';' AS s",                       # semicolon inside a literal
        "SELECT 1 /* comment; with ; semicolons */",
        "-- leading comment\nSELECT 1",
        "SELECT * FROM wells WHERE name = 'insert into x'",  # write words in a literal
    ]
    for sql in allowed:
        assert db.validate_readonly_sql(sql) is None, sql


def test_guard_rejects_writes_and_stacking():
    rejected = [
        "INSERT INTO wells(dataset_id, asset_id) VALUES ('x','y')",
        "UPDATE wells SET name = 'x'",
        "DELETE FROM wells",
        "DROP TABLE wells",
        "PRAGMA query_only = OFF",
        "SELECT 1; SELECT 2",                                        # stacked
        "SELECT 1; DROP TABLE wells",                                # stacked write
        "WITH x AS (SELECT 1) INSERT INTO wells SELECT * FROM x",     # CTE smuggle
        "WITH x AS (SELECT 1) DELETE FROM wells WHERE 1=0",
        "",
        "   ",
        "-- only a comment\n/* nothing else */",
    ]
    for sql in rejected:
        assert db.validate_readonly_sql(sql) is not None, sql


def test_strip_literals_handles_every_quote_form():
    sql = "SELECT 'it''s; fine', \"col;umn\", `back;tick`, [brack;et] FROM t"
    skeleton = db.strip_literals_and_comments(sql)
    assert ";" not in skeleton

    # a block comment hides a semicolon; a doubled quote is escaped, not a terminator
    assert ";" not in db.strip_literals_and_comments("SELECT 1 /* ; */")
    assert ";" not in db.strip_literals_and_comments("SELECT 'it''s; fine' FROM t")


# ------------------------------------------------------ document path helpers


def test_normalize_path_tolerates_llm_variants():
    assert documents.normalize_path("./fleet/sops/x.md") == "fleet/sops/x.md"
    assert documents.normalize_path("fleet\\sops\\x.md") == "fleet/sops/x.md"
    assert documents.normalize_path(" /fleet/x.md ") == "fleet/x.md"
    assert documents.normalize_path("") == ""


def test_safe_join_rejects_escapes_and_missing_files(tmp_path: Path):
    root = tmp_path / "root"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "f.md").write_text("hi")
    assert documents._safe_join(root, "sub/f.md").read_text() == "hi"
    with pytest.raises(documents.ResolveError):
        documents._safe_join(root, "../../etc/hosts")
    with pytest.raises(documents.ResolveError):
        documents._safe_join(root, "sub/missing.md")


# ------------------------------------------------------------ value matching


def test_values_match_and_canon():
    assert server._values_match("wellhead_temp_c", 24.0, "24.0")
    assert server._values_match("spill_detected", "1", 1)
    assert not server._values_match("wellhead_temp_c", 24.1, 24.0)
    assert not server._values_match("spill_detected", "0", 1)
    assert server._canon("spill_detected", True) == "1"
    assert server._canon("wellhead_temp_c", 41) == "41.0"


# ------------------------------------------------- connection-level read-only


def _tiny_db(path: Path, wal: bool = True) -> None:
    conn = sqlite3.connect(str(path))
    try:
        if wal:
            conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("CREATE TABLE t(x)")
        conn.execute("INSERT INTO t VALUES (1)")
        conn.commit()
    finally:
        conn.close()


@pytest.fixture()
def configured_db(tmp_path: Path):
    """Point db at a temp file, restore the default resolution afterwards."""
    yield lambda p: db.configure(p)
    db.configure(None)


def test_ro_conn_blocks_writes(configured_db, tmp_path: Path):
    p = tmp_path / "tiny.db"
    _tiny_db(p)
    configured_db(p)
    conn = db.ro_conn()
    try:
        assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO t VALUES (2)")
    finally:
        conn.close()


def test_ro_conn_falls_back_when_wal_shm_is_missing(configured_db, tmp_path: Path):
    """Regression: a WAL db with no -shm cannot be opened read-only, and the
    failure is lazy (first read, not connect). ro_conn() must fall back and
    still read (the real DB after a fresh ingest is exactly this shape)."""
    p = tmp_path / "wal.db"
    _tiny_db(p, wal=True)
    for suffix in ("-wal", "-shm"):
        f = Path(str(p) + suffix)
        if f.exists():
            f.unlink()
    configured_db(p)
    conn = db.ro_conn()
    try:
        assert conn.execute("SELECT x FROM t").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO t VALUES (2)")
    finally:
        conn.close()
