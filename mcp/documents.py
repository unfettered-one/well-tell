"""documents.py — resolve + read dataset documents and repair reports.

Docs and reports live on disk, never inside the DB (database_plan.md §4). The DB
keeps only the catalog: ``documents`` (path, title, doc_type for manuals/SOPs)
and ``maintenance.report_file`` (a path relative to the well folder). The root
folder per dataset comes from ``meta.dataset_root_<dataset_id>``; every path is
validated against the DB and resolved *under that root*, so a tool call can
never read outside the dataset folder.

Rejections are corrective: they state what was wrong and name the SQL that finds
the right value (database_plan.md §6 spirit, mcp_plan.md §5).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import db


class ResolveError(Exception):
    """A document/report could not be resolved. Message is agent-actionable."""


# ------------------------------------------------------------------- paths


def normalize_path(path: str) -> str:
    """Tolerate the harmless variants an LLM produces ('./fleet\\x.md' etc.)."""
    p = (path or "").strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def dataset_root(conn: sqlite3.Connection, dataset_id: str) -> Path:
    raw = db.meta(conn, f"dataset_root_{dataset_id}")
    if not raw:
        raise ResolveError(
            f"meta.dataset_root_{dataset_id} is missing — the DB was not ingested "
            f"properly. Check: SELECT key, value FROM meta WHERE key LIKE 'dataset_root%';")
    root = Path(raw)
    if not root.is_dir():
        raise ResolveError(
            f"dataset root recorded in meta does not exist on disk: {root} "
            f"(meta.dataset_root_{dataset_id})")
    return root


def _safe_join(root: Path, rel: str) -> Path:
    """Resolve ``rel`` under ``root``; refuse escapes and missing files."""
    target = (root / rel).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ResolveError(f"path escapes the dataset folder: {rel}")
    if not target.is_file():
        raise ResolveError(f"file recorded in the DB is missing on disk: {target}")
    return target


def _pick_dataset(conn: sqlite3.Connection, rows: list[sqlite3.Row],
                  id_label: str) -> sqlite3.Row:
    """When the same id exists in several datasets (sample + test), the newest
    dataset (by as_of) is the reference; that is the dataset a live question is
    about on test day. Deterministic and stated in the payload."""
    order = {ds: i for i, ds in enumerate(db.dataset_order(conn))}
    return sorted(rows, key=lambda r: order.get(r["dataset_id"], 999))[0]


def _others(rows: list[sqlite3.Row], chosen: sqlite3.Row) -> list[str]:
    return sorted({r["dataset_id"] for r in rows} - {chosen["dataset_id"]})


# --------------------------------------------------------------- documents


def find_document(conn: sqlite3.Connection, path: str, dataset_id: str | None = None) -> dict:
    """Resolve a cataloged doc path -> {dataset_id, doc_type, path, title}."""
    norm = normalize_path(path)
    rows = conn.execute(
        "SELECT dataset_id, doc_id, doc_type, path, title FROM documents "
        "WHERE path = ? AND (? IS NULL OR dataset_id = ?)",
        (norm, dataset_id, dataset_id)).fetchall()
    if not rows:
        base = norm.rsplit("/", 1)[-1]
        near = conn.execute(
            "SELECT path, title FROM documents WHERE path LIKE ? "
            "ORDER BY path LIMIT 10", (f"%/{base}",)).fetchall()
        hint = ("Find the right path first:\n"
                "  SELECT doc_type, path, title FROM documents;")
        if near:
            hint += "\nClosest catalog entries: " + \
                ", ".join(r["path"] for r in near)
        raise ResolveError(
            f"'{path}' is not in the documents catalog — only paths from the "
            f"`documents` table can be read.\n{hint}")
    chosen = _pick_dataset(conn, rows, "path")
    out = {k: chosen[k] for k in ("dataset_id", "doc_type", "path", "title")}
    also = _others(rows, chosen)
    if also:
        out["also_in_datasets"] = also
    return out


def read_document(conn: sqlite3.Connection, path: str, dataset_id: str | None = None) -> dict:
    """Read a cataloged manual/SOP from disk."""
    doc = find_document(conn, path, dataset_id)
    root = dataset_root(conn, doc["dataset_id"])
    target = _safe_join(root, doc["path"])
    doc["file"] = str(target)
    doc["content"] = target.read_text(encoding="utf-8")
    return doc


# ----------------------------------------------------------------- reports


def find_report(conn: sqlite3.Connection, maintenance_id: str, dataset_id: str | None = None) -> dict:
    """Resolve a maintenance id -> its report row (never build paths by hand)."""
    rows = conn.execute(
        "SELECT dataset_id, maintenance_id, asset_id, maintenance_type, "
        "       triggered_by_inspection_id, report_file "
        "FROM maintenance WHERE maintenance_id = ? AND (? IS NULL OR dataset_id = ?)",
        (maintenance_id, dataset_id, dataset_id)).fetchall()
    if not rows:
        raise ResolveError(
            f"'{maintenance_id}' is not a maintenance id in this database.\n"
            "Resolve it from the records you have, e.g.:\n"
            "  SELECT m.maintenance_id, m.asset_id, m.report_file\n"
            "  FROM maintenance m WHERE m.triggered_by_inspection_id = 'INS-...';")
    chosen = _pick_dataset(conn, rows, "maintenance_id")
    if not chosen["report_file"]:
        raise ResolveError(
            f"{maintenance_id} has no report file on record "
            f"(maintenance_type={chosen['maintenance_type']}). Only corrective "
            "repairs carry reports; scheduled jobs never have one.")
    out = {k: chosen[k] for k in ("dataset_id", "maintenance_id", "asset_id",
                                  "maintenance_type", "triggered_by_inspection_id",
                                  "report_file")}
    also = _others(rows, chosen)
    if also:
        out["also_in_datasets"] = also
    return out


def read_report(conn: sqlite3.Connection, maintenance_id: str, dataset_id: str | None = None) -> dict:
    """Read the repair report markdown from disk, plus its extracted facts."""
    info = find_report(conn, maintenance_id, dataset_id)
    root = dataset_root(conn, info["dataset_id"])
    target = _safe_join(root, f"assets/{info['asset_id']}/{info['report_file']}")
    info["file"] = str(target)
    info["content"] = target.read_text(encoding="utf-8")
    facts = conn.execute(
        "SELECT contained_hours_after, rca_action_required, spill_class, "
        "       root_cause, extraction_status "
        "FROM report_facts WHERE dataset_id = ? AND maintenance_id = ?",
        (info["dataset_id"], maintenance_id)).fetchone()
    info["report_facts"] = dict(facts) if facts else None
    return info
