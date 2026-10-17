"""conftest.py — shared fixtures for the Well Copilot test suite.

The MCP server's modules live in ``mcp/``. They are imported by *path* (an
explicit sys.path entry), not as a package: the folder name would shadow the
installed ``mcp`` SDK for ``import mcp`` whenever the repo root ends up on
sys.path (which ``python -m pytest`` does).

Every scenario runs against a private COPY of the ingested DB — the write
tools (record_correction, remember, log_message, set_rule) intentionally
mutate runtime tables, and ``data/well_copilot.db`` must stay pristine until
the eval.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
MCP_DIR = REPO / "mcp"
REAL_DB = REPO / "data" / "well_copilot.db"

# `python -m pytest` puts the CWD (repo root) on sys.path, where the local
# `mcp/` folder would shadow the installed mcp SDK for `import mcp`.
# Drop it; server modules are imported via the explicit MCP_DIR entry below.
for entry in ("", str(REPO)):
    while entry in sys.path:
        sys.path.remove(entry)
sys.path.insert(0, str(MCP_DIR))


@pytest.fixture()
def db_copy(tmp_path: Path) -> Path:
    """A private, WAL-safe copy of the real DB (sqlite backup API)."""
    if not REAL_DB.exists():
        pytest.skip(f"database not built yet: {REAL_DB} — run ingest first "
                    "(see ingest/README.md)")
    dst = tmp_path / "well_copilot_test.db"
    src = sqlite3.connect(str(REAL_DB))
    out = sqlite3.connect(str(dst))
    try:
        src.backup(out)
    finally:
        out.close()
        src.close()
    return dst
