"""db.py — SQLite connections for the Well Copilot MCP server.

Two connection factories, one discipline (mcp_plan.md §6):

    ro_conn()   read-only: opened through a ``file:...?mode=ro`` URI (layer 1),
                ``PRAGMA query_only=ON`` (layer 2); every statement also passes
                ``validate_readonly_sql()`` (layer 3) before it reaches SQLite.
    rw_conn()   read-write, used only by the write tools (record_correction,
                remember, log_message, set_rule); ``busy_timeout=5000`` so a
                mid-chat re-ingest (WAL) never blocks or corrupts a write.

DB path resolution: ``--db`` (server.py) > env ``WELL_COPILOT_DB`` >
``data/well_copilot.db`` next to the repo root. The DB itself is built by
``ingest/ingest.py`` — this module never creates or migrates it.
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "data" / "well_copilot.db"

_db_override: Path | None = None


# --------------------------------------------------------------------- path


def configure(path: str | os.PathLike | None) -> None:
    """Point the module at a DB file (``--db``). None = env/default resolution."""
    global _db_override
    _db_override = Path(path).expanduser().resolve() if path else None


def db_path() -> Path:
    """The DB file in effect: override > WELL_COPILOT_DB > data/well_copilot.db."""
    if _db_override is not None:
        return _db_override
    env = os.environ.get("WELL_COPILOT_DB")
    if env:
        return Path(env).expanduser().resolve()
    return DEFAULT_DB


def _existing_path() -> Path:
    path = db_path()
    if not path.exists():
        raise FileNotFoundError(
            f"database not found: {path} — build it first, e.g. "
            "python ingest/ingest.py --data <dataset>/sample-data "
            "--dataset sample --db data/well_copilot.db"
        )
    return path


# -------------------------------------------------------------- connections


def ro_conn() -> sqlite3.Connection:
    """One fresh read-only connection (never share across calls/threads).

    Layer 1 (file): open through the URI ``mode=ro``. Layer 2 (connection):
    ``query_only=ON``, always applied. Layer 3 (statement) is
    ``validate_readonly_sql()`` at the tool boundary.

    Fallback note: a WAL database whose ``-shm``/``-wal`` files do not exist yet
    (fresh ingest, a copied file) cannot be opened by a strictly read-only handle
    — SQLite is not allowed to create the shared-memory file — and the failure
    is lazy: ``connect()`` and the ``query_only`` pragma both succeed, and the
    first real read raises. The probe below forces that read inside the ``try``,
    so this one case transparently falls back to a normal handle where layer 2
    alone enforces read-only access (SQLite itself rejects every write on
    ``query_only`` connections).
    """
    path = _existing_path()
    conn = None
    try:
        conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=5.0)
        conn.execute("PRAGMA query_only = ON")
        conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()  # probe
    except sqlite3.OperationalError:
        if conn is not None:
            conn.close()
        conn = sqlite3.connect(str(path), timeout=5.0)
        conn.execute("PRAGMA query_only = ON")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def rw_conn() -> sqlite3.Connection:
    """One fresh read-write connection, for the write tools only."""
    path = _existing_path()
    conn = sqlite3.connect(str(path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")  # already on from ingest; idempotent
    conn.execute("PRAGMA busy_timeout = 5000")
    # Reserve the write transaction before next_id()/sanity checks. Concurrent
    # users cannot allocate the same runtime ID between a read and an insert.
    conn.execute("BEGIN IMMEDIATE")
    return conn


# ------------------------------------------------- layer 3: statement guard

_WRITE_WORDS = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|"
    r"pragma|vacuum|reindex|analyze)\b",
    re.IGNORECASE,
)
_HEAD_RE = re.compile(r"^\s*(select|with|explain)\b", re.IGNORECASE)


def strip_literals_and_comments(sql: str) -> str:
    """Return the statement skeleton: comments removed and string/identifier
    literals blanked, so a ``;`` or a write keyword *inside a literal* cannot
    fool the guard. Quote forms handled: 'str', "ident", `ident`, [ident].
    """
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch in ("'", '"'):
            quote = ch
            i += 1
            while i < n:
                if sql[i] == quote:
                    if i + 1 < n and sql[i + 1] == quote:  # doubled quote = escaped
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            out.append(" ")
        elif ch == "-" and i + 1 < n and sql[i + 1] == "-":
            nl = sql.find("\n", i)
            i = n if nl == -1 else nl
        elif ch == "/" and i + 1 < n and sql[i + 1] == "*":
            end = sql.find("*/", i + 2)
            i = n if end == -1 else end + 2
        elif ch == "[":
            end = sql.find("]", i + 1)
            i = n if end == -1 else end + 1
            out.append(" ")
        elif ch == "`":
            end = sql.find("`", i + 1)
            i = n if end == -1 else end + 1
            out.append(" ")
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def validate_readonly_sql(sql: str) -> str | None:
    """Layer 3. Returns None when the statement is allowed, else a rejection
    label explaining the rule it broke (the tool folds it into an error the
    agent can act on).

    Rules: the skeleton must contain exactly one statement, and it must start
    with SELECT, WITH or EXPLAIN — and a WITH/EXPLAIN must not smuggle a write
    keyword (blocks ``WITH x AS (...) INSERT ...``).
    """
    if not sql or not sql.strip():
        return "empty statement"
    skeleton = strip_literals_and_comments(sql)
    statements = [s for s in skeleton.split(";") if s.strip()]
    if not statements:
        return "no statement found (comments only?)"
    if len(statements) > 1:
        return ("multiple statements in one call — send exactly one "
                "SELECT/WITH/EXPLAIN statement")
    stmt = statements[0].strip()
    m = _HEAD_RE.match(stmt)
    if not m:
        return ("statement must start with SELECT, WITH or EXPLAIN "
                "(read-only access)")
    head = m.group(1).lower()
    if head in ("with", "explain") and _WRITE_WORDS.search(stmt):
        return f"{head.upper()} statement contains a data-changing keyword"
    return None


# ------------------------------------------------------------------ helpers


def meta(conn: sqlite3.Connection, key: str, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def meta_all(conn: sqlite3.Connection) -> dict:
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM meta")}


def dataset_as_of(conn: sqlite3.Connection, dataset_id: str) -> str | None:
    """Per-dataset 'today' (meta.as_of_<id>), global meta.as_of as fallback."""
    return (meta(conn, f"as_of_{dataset_id}") or meta(conn, "as_of"))


def dataset_order(conn: sqlite3.Connection) -> list[str]:
    """Dataset ids, newest as_of first (deterministic: id desc breaks ties).

    The bound reference row for ids that can repeat across datasets
    (inspection/maintenance ids on test day) is the first entry here.
    """
    ids = [r[0] for r in conn.execute(
        "SELECT DISTINCT dataset_id FROM wells ORDER BY dataset_id")]
    return sorted(ids, key=lambda d: (dataset_as_of(conn, d) or "", d), reverse=True)


def next_id(conn: sqlite3.Connection, table: str, column: str, prefix: str,
            width: int = 4) -> str:
    """A free id like ``COR-RT-0001`` (table/column are internal constants)."""
    n = conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE {column} LIKE ?",
        (prefix + "%",)).fetchone()[0]
    while True:
        n += 1
        candidate = f"{prefix}{n:0{width}d}"
        hit = conn.execute(
            f"SELECT 1 FROM {table} WHERE {column} = ?", (candidate,)).fetchone()
        if hit is None:
            return candidate


def jsonable(value):
    """sqlite3 value -> JSON-safe (only bytes need help in this schema)."""
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<blob {len(value)} bytes>"
    return value


def rows_as_dicts(columns: list[str], rows) -> list[dict]:
    """Rows as dicts, disambiguating repeated column names (``name#2``)."""
    counts: dict[str, int] = {}
    keys: list[str] = []
    for c in columns:
        counts[c] = counts.get(c, 0) + 1
        keys.append(c if counts[c] == 1 else f"{c}#{counts[c]}")
    return [dict(zip(keys, (jsonable(v) for v in row))) for row in rows]
