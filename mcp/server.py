#!/usr/bin/env python3
"""server.py — Well Copilot MCP server (stdio).

The passive middleman between the copilot agent and the well_copilot SQLite DB
(mcp_plan.md §1). Reads run against the derived ``v_*`` views (all domain math
lives in SQL); writes land only in runtime tables (corrections, facts,
memories, claims, messages, and runtime rule overrides). The server never
pushes anything — every lookup is an agent tool call, steered by the tool
docstrings below and by prompts.py.

Tools (mcp_plan.md §4, §9):
  read   query_db · list_tables · describe · get_doc · get_report · recall
  write  record_correction · remember · log_message · set_rule
         (set_rule closes the Q14/B14 rule-feedback path: the plan's tool list
         had no way to write a well-type rule override, which the DB design and
         database_plan.md §5 explicitly anticipate)

Run:  python mcp/server.py [--db data/well_copilot.db]
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import db  # noqa: E402
import documents  # noqa: E402
import prompts  # noqa: E402

try:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
    from mcp.server.fastmcp.exceptions import ToolError
except ImportError:  # mcp >= 2 renamed FastMCP to MCPServer
    from mcp.server.mcpserver import MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError

from mcp.types import ToolAnnotations  # noqa: E402

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True)
WRITE = ToolAnnotations(read_only_hint=False, idempotent_hint=False)

MAX_ROWS = 50          # query_db cap (mcp_plan.md §4)
MAX_RECALL_ROWS = 20   # per recall section

app = _Server("well-copilot", instructions=prompts.SERVER_INSTRUCTIONS)


# ------------------------------------------------- prompt resources (prompts.py)
# The copilot agent's system prompt includes copilot_system_prompt verbatim
# (mcp_plan.md §7); the pieces are exposed separately for reuse.


@app.prompt()
def copilot_system_prompt() -> str:
    """The copilot system prompt: answer protocol, routing ladder, citation and
    honesty rules. Include it verbatim in the agent's system prompt."""
    return prompts.copilot_system_prompt()


@app.prompt()
def routing_ladder() -> str:
    """Where a user statement lands: correction vs claim vs fact vs private
    memory vs rule change (database_plan.md §7)."""
    return prompts.routing_ladder()


@app.prompt()
def answer_protocol() -> str:
    """The five hard rules for answering a well-specific question (views not
    raw, recall first, report follow-through, cite ids, honest gaps)."""
    return prompts.answer_protocol()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rows(conn: sqlite3.Connection, sql: str, params=(), cap: int = MAX_ROWS):
    """(rows, truncated) for an internal, fixed-shape query."""
    rows = conn.execute(sql, params).fetchmany(cap + 1)
    return [dict(r) for r in rows[:cap]], len(rows) > cap


def _user_name(conn: sqlite3.Connection, user_id: str | None) -> str | None:
    if not user_id:
        return None
    names = {r[0] for r in conn.execute(
        "SELECT DISTINCT name FROM users WHERE user_id = ? AND name IS NOT NULL",
        (user_id,))}
    return names.pop() if len(names) == 1 else None


def _as_float(label: str, text) -> float:
    try:
        return float(str(text).strip())
    except (TypeError, ValueError):
        raise ToolError(f"{label} must be a number, got {text!r}.") from None


def _as_flag(label: str, text) -> int:
    s = str(text).strip().lower()
    if s in ("1", "true", "yes"):
        return 1
    if s in ("0", "false", "no"):
        return 0
    raise ToolError(f"{label} must be 0/1 (or true/false), got {text!r}.")


def _canon(field: str, value) -> str:
    """Canonical stored form of a corrected value (matches the ingested mirror)."""
    return str(int(value)) if field == "spill_detected" else str(float(value))


# ------------------------------------------------------------------- reads


@app.tool(annotations=READ_ONLY)
def query_db(sql: str) -> dict:
    """Run ONE read-only SQL statement against the well_copilot database.

    Returns {columns, rows, rowcount, truncated}. Results are capped at 50 rows
    (truncated=true tells you so) — narrow the question with WHERE / LIMIT /
    date filters instead of skimming a wide result.

    Rules of the house:
    - For production status, downtime, spills, SOP deadlines, RCA and conflicts,
      query the `v_*` views — NEVER compute from raw tables: every threshold and
      every correction is already applied in SQL. Use raw tables only for slices
      no view covers, and run describe(name) before those queries.
    - One statement only (SELECT / WITH / EXPLAIN); comments and semicolons
      inside strings are fine, stacking two statements is not.
    - "Today" is meta.as_of (per dataset: meta.as_of_<dataset_id>) — never
      date('now'); the wall clock is not the evaluation date. When several
      datasets are loaded, filter by dataset_id (see list_tables).
    - An empty result is a legitimate answer: say "not in the data" — do not pad.
    """
    problem = db.validate_readonly_sql(sql)
    if problem:
        raise ToolError(
            f"rejected: {problem}. Send exactly one SELECT / WITH / EXPLAIN "
            f"statement (this connection is read-only).")
    try:
        with closing(db.ro_conn()) as conn:
            cur = conn.execute(sql)
            if cur.description is None:
                raise ToolError("that statement returns no rows — it is not a SELECT.")
            columns = [d[0] for d in cur.description]
            rows = cur.fetchmany(MAX_ROWS + 1)
    except sqlite3.Error as exc:
        raise ToolError(
            f"SQL error: {exc}. Check names with list_tables() / describe(name) "
            f"and remember the v_* views are the read path for domain questions."
        ) from None
    truncated = len(rows) > MAX_ROWS
    payload = {
        "columns": columns,
        "rows": db.rows_as_dicts(columns, rows[:MAX_ROWS]),
        "rowcount": len(rows[:MAX_ROWS]),
        "truncated": truncated,
    }
    if truncated:
        payload["hint"] = (f"showing the first {MAX_ROWS} rows — add WHERE/LIMIT "
                           "to narrow, or aggregate in SQL")
    elif not rows:
        payload["hint"] = ("no rows — 'not in the data' is a legitimate answer; "
                           "do not pad or guess")
    return payload


@app.tool(annotations=READ_ONLY)
def list_tables() -> dict:
    """List every table and view, plus the datasets loaded and each one's as_of
    ('today' for that dataset).

    Start here when you don't know names. `v_*` are the derived views (the fast
    path: status, downtime, spills, obligations, RCA, conflicts, costs);
    everything else is raw ingested data, the documents catalog, or runtime
    knowledge. Filter queries by `dataset_id` whenever more than one dataset is
    loaded. Then describe(name) before querying a name you haven't seen.
    """
    with closing(db.ro_conn()) as conn:
        names = [r["name"] for r in conn.execute(
            "SELECT name, type FROM sqlite_master "
            "WHERE type IN ('table','view') ORDER BY type, name")]
        views = [r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='view' ORDER BY name")]
        tables = [n for n in names if n not in set(views)]
        datasets = []
        for ds in db.dataset_order(conn):
            datasets.append({
                "dataset_id": ds,
                "as_of": db.dataset_as_of(conn, ds),
                "wells": conn.execute(
                    "SELECT COUNT(*) FROM wells WHERE dataset_id = ?", (ds,)).fetchone()[0],
                "inspections": conn.execute(
                    "SELECT COUNT(*) FROM inspections WHERE dataset_id = ?",
                    (ds,)).fetchone()[0],
            })
        return {
            "tables": tables,
            "views": views,
            "datasets": datasets,
            "as_of": db.meta(conn, "as_of"),
            "notes": ("Read path = the v_* views (rules + corrections already "
                      "applied). Ingested tables are keyed (dataset_id, <id>); "
                      "runtime tables are not dataset-scoped."),
        }


_RELATIONSHIPS = {
    "teams": ["wells.team_id -> teams.team_id", "areas.team_id -> teams.team_id"],
    "users": ["wells.in_charge_user_id -> users.user_id",
              "inspections.inspector_user_id -> users.user_id",
              "maintenance.technician_user_id -> users.user_id",
              "context_notes.author_user_id -> users.user_id"],
    "areas": ["wells.area_id -> areas.area_id"],
    "wells": ["inspections.asset_id -> wells.asset_id",
              "maintenance.asset_id -> wells.asset_id",
              "context_notes.asset_id / corrections.asset_id / claims.asset_id -> wells.asset_id"],
    "equipment": ["equipment.asset_id -> wells.asset_id"],
    "inspections": ["inspections.asset_id -> wells.asset_id",
                    "maintenance.triggered_by_inspection_id -> inspections.inspection_id  "
                    "(the chain: inspection -> repair -> report)",
                    "corrections.inspection_id -> inspections.inspection_id"],
    "maintenance": ["maintenance.report_file -> assets/<asset_id>/<report_file> on disk "
                    "(read it with get_report(maintenance_id), never by hand)"],
    "report_facts": ["report_facts.maintenance_id -> maintenance.maintenance_id",
                     "report_facts.inspection_id -> inspections.inspection_id"],
    "regulatory_events": ["regulatory_events.related_inspection_id -> inspections.inspection_id",
                          "regulatory_events.asset_id -> wells.asset_id"],
    "context_notes": ["context_notes.inspection_id -> inspections.inspection_id"],
    "corrections": ["corrections.inspection_id / corrections.asset_id / corrections.well_type "
                    "= the scope; applied at read time by the v_* views"],
    "documents": ["documents.path -> file under the dataset root (read with get_doc(path))"],
    "rules": ["rules.(parameter, applies_to) is joined by every v_* view; a runtime "
              "override (is_overridden=1) wins"],
    "sessions": ["messages.session_id -> sessions.session_id (a session is private to "
                 "sessions.user_id)"],
    "messages": ["messages.session_id -> sessions.session_id"],
    "memories": ["memories.user_id -> private to that user"],
    "facts": ["facts.author_user_id -> users.user_id (facts are shared with every user)"],
    "claims": ["claims.asset_id -> wells.asset_id", "claims.user_id -> the user who said it"],
}

_VIEW_NOTES = {
    "v_inspection_effective": "base pattern: raw inspections COALESCE'd with the latest "
                              "applicable correction (corrections win at read time)",
    "v_producing_now": "per well: latest effective inspection vs rules.production_threshold "
                       "(15 °C T200 / 20 °C T350), plus recorded_status, the latest "
                       "context note and any still-open repair",
    "v_downtime_findings": "one row per non-producing finding (7 days each, from rules)",
    "v_downtime": "weekly rollup of downtime findings",
    "v_spills": "effective detections only (correction-removed ones are gone)",
    "v_spill_classified": "spills + the SOP class band for the EFFECTIVE volume "
                          "(effective_class vs the report's reported_class)",
    "v_repairs_corrective": "corrective repairs with the prior corrective count per "
                            "equipment kind (RCA math inputs)",
    "v_rca_due": "wells/equipment at or above rules.rca_after_n_repairs corrective "
                 "repairs in the lookback window ending at as_of",
    "v_sobligations": "spills -> SR-01/SR-02/SR-03/RC-04 deadlines from rules; status is "
                      "met / breached / open / overdue / not_required",
    "v_conflicts": "inspection vs disagreeing non-correction notes vs runtime claims",
    "v_repairs_costs": "maintenance cost sums per well and year",
}


@app.tool(annotations=READ_ONLY)
def describe(name: str) -> dict:
    """Describe one table or view: columns, types, PK flags, relationships, row count.

    Call this before querying any name you have not seen — never guess a column.
    Ingested tables are keyed (dataset_id, <id>); runtime tables are not
    dataset-scoped. `v_*` views already apply rules + corrections.
    """
    with closing(db.ro_conn()) as conn:
        row = conn.execute(
            "SELECT name, type FROM sqlite_master WHERE name = ?", (name,)).fetchone()
        if row is None:
            known = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view') "
                "ORDER BY name")]
            raise ToolError(
                f"no table or view named '{name}'. Known names: {', '.join(known)}")
        kind = row["type"]
        columns = [{
            "name": c["name"], "type": c["type"],
            "notnull": bool(c["notnull"]), "pk": bool(c["pk"]),
            "default": c["dflt_value"],
        } for c in conn.execute(f'PRAGMA table_info("{name}")')]
        pk = [c["name"] for c in columns if c["pk"]]
        payload = {
            "name": name,
            "kind": kind,
            "columns": columns,
            "primary_key": pk,
            "row_count": conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0],
            "relationships": _RELATIONSHIPS.get(name, []),
            "note": _VIEW_NOTES.get(name)
                    or ("ingested table — keyed (dataset_id, <id>)"
                         if "dataset_id" in {c["name"] for c in columns}
                         else "runtime table — not dataset-scoped"),
        }
        return payload


@app.tool(annotations=READ_ONLY)
def get_doc(path: str) -> dict:
    """Read a manual or SOP from the dataset, by catalog path (returns its text).

    `path` must be one from the `documents` table, e.g.
    'fleet/well-types/T200.md' or 'fleet/sops/spill-response-sop.md'. If unsure:
    SELECT doc_type, path, title FROM documents.

    Use this for rule wording and citations from manuals/SOPs. Do NOT use it for
    repair reports — use get_report(maintenance_id), which resolves the file
    through SQL.
    """
    try:
        with closing(db.ro_conn()) as conn:
            return documents.read_document(conn, path)
    except documents.ResolveError as exc:
        raise ToolError(str(exc)) from None


@app.tool(annotations=READ_ONLY)
def get_report(maintenance_id: str) -> dict:
    """Read a repair report (markdown) by maintenance id, e.g. 'MNT-0082-028'.

    The file is resolved through SQL (maintenance.report_file + the dataset root)
    — never build report paths by hand. Returns the report text plus the facts
    already extracted from it (report_facts): check extraction_status — when it
    is 'fts_only' the extraction missed fields and you must read the text here.

    Facts such as containment time often exist ONLY in this report. Follow the
    chain: inspection -> maintenance.triggered_by_inspection_id -> this report.
    """
    try:
        with closing(db.ro_conn()) as conn:
            return documents.read_report(conn, maintenance_id)
    except documents.ResolveError as exc:
        raise ToolError(str(exc)) from None


@app.tool(annotations=READ_ONLY)
def recall(query: str | None = None,
           well_id: str | None = None,
           user_id: str | None = None) -> dict:
    """Recall what has been learned: shared facts, the user's private memories,
    and unconfirmed claims — each row tagged shared / private / unconfirmed.

    Call this (with well_id) BEFORE answering anything well-specific, and with
    user_id so the user's own private memory is included.

    - facts   — shared with every user (scope well / well_type / fleet), with
                author attribution ("per Jake Morales").
    - memories— private to `user_id` only; no other user's memory is returned.
    - claims  — statements that disagree with the data, status='unconfirmed':
                surface them as disagreements, never as truth, and ask the user
                to confirm.
    - conversation — with user_id, the user's own recent turns and the wells
                they discussed ("the wells we discussed yesterday"), never
                another user's.

    query: substring filter over the collected facts, memories and claims.
    """
    with closing(db.ro_conn()) as conn:
        payload: dict = {"filters": {"query": query, "well_id": well_id,
                                     "user_id": user_id}}
        as_of = db.meta(conn, "as_of")

        # ---- shared facts (scope-filtered when well_id is given)
        types = []
        if well_id:
            types = [r[0] for r in conn.execute(
                "SELECT DISTINCT well_type FROM wells WHERE asset_id = ?", (well_id,))]
        sql = ("SELECT fact_id, scope, scope_value, text, author_user_id, "
               "created_at, valid_to FROM facts "
               "WHERE (valid_to IS NULL OR valid_to >= ?)")
        params: list = [as_of or "0000-01-01"]
        if well_id:
            scope_clause = ["(scope = 'well' AND scope_value = ?)"]
            params.append(well_id)
            if types:
                scope_clause.append(
                    "(scope = 'well_type' AND scope_value IN (%s))"
                    % ",".join("?" * len(types)))
                params.extend(types)
            scope_clause.append("scope = 'fleet'")
            sql += " AND (" + " OR ".join(scope_clause) + ")"
        if query:
            sql += " AND text LIKE ?"
            params.append(f"%{query}%")
        sql += " ORDER BY created_at DESC, fact_id DESC LIMIT ?"
        params.append(MAX_RECALL_ROWS + 1)
        rows = conn.execute(sql, params).fetchall()
        facts, truncated = rows[:MAX_RECALL_ROWS], len(rows) > MAX_RECALL_ROWS
        payload["facts"] = [{
            **{k: r[k] for k in ("fact_id", "scope", "scope_value", "text",
                                 "author_user_id", "created_at", "valid_to")},
            "author_name": _user_name(conn, r["author_user_id"]),
            "visibility": "shared",
        } for r in facts]
        if truncated:
            payload.setdefault("truncated", []).append("facts")

        # ---- private memories (only ever the given user's)
        if user_id:
            sql = ("SELECT memory_id, text, session_id, created_at FROM memories "
                   "WHERE user_id = ?")
            params = [user_id]
            if query:
                sql += " AND text LIKE ?"
                params.append(f"%{query}%")
            if well_id:
                sql += " AND text LIKE ?"
                params.append(f"%{well_id}%")
            sql += " ORDER BY created_at DESC, memory_id DESC LIMIT ?"
            params.append(MAX_RECALL_ROWS + 1)
            rows = conn.execute(sql, params).fetchall()
            mem, trunc = rows[:MAX_RECALL_ROWS], len(rows) > MAX_RECALL_ROWS
            payload["memories"] = [{
                **{k: r[k] for k in ("memory_id", "text", "session_id", "created_at")},
                "private_to_user_id": user_id,
                "visibility": "private",
            } for r in mem]
            if trunc:
                payload.setdefault("truncated", []).append("memories")
        else:
            payload["memories"] = []
            payload["memories_note"] = ("private memories are per user — pass "
                                        "user_id to include them")

        # ---- claims (unconfirmed statements, never truth)
        sql = ("SELECT claim_id, user_id, asset_id, text, status, created_at "
               "FROM claims WHERE COALESCE(status, 'unconfirmed') != 'confirmed'")
        params = []
        if well_id:
            sql += " AND asset_id = ?"
            params.append(well_id)
        if query:
            sql += " AND text LIKE ?"
            params.append(f"%{query}%")
        sql += " ORDER BY created_at DESC, claim_id DESC LIMIT ?"
        params.append(MAX_RECALL_ROWS + 1)
        rows = conn.execute(sql, params).fetchall()
        claims, trunc = rows[:MAX_RECALL_ROWS], len(rows) > MAX_RECALL_ROWS
        payload["claims"] = [{
            **{k: r[k] for k in ("claim_id", "user_id", "asset_id", "text",
                                 "status", "created_at")},
            "claimant_name": _user_name(conn, r["user_id"]),
            "visibility": "unconfirmed",
        } for r in claims]
        if trunc:
            payload.setdefault("truncated", []).append("claims")

        # ---- the user's own conversation memory (privacy: joined on sessions.user_id)
        if user_id:
            rows = conn.execute(
                "SELECT m.message_id, m.session_id, m.role, m.created_at, "
                "       substr(m.content, 1, 280) AS content, m.referenced_wells_json "
                "FROM messages m JOIN sessions s ON s.session_id = m.session_id "
                "WHERE s.user_id = ? "
                "ORDER BY m.created_at DESC, m.message_id DESC LIMIT 12",
                (user_id,)).fetchall()
            discussed: list[str] = []
            for r in rows:
                try:
                    wells = json.loads(r["referenced_wells_json"] or "[]")
                except (TypeError, ValueError):
                    wells = []
                for w in wells if isinstance(wells, list) else []:
                    if isinstance(w, str) and w not in discussed:
                        discussed.append(w)
            payload["conversation"] = {
                "private_to_user_id": user_id,
                "discussed_wells_recent_first": discussed,
                "recent_messages": [dict(r) for r in rows],
                "note": ("this is the ONLY user whose history is included — if "
                         "'the wells we discussed' returns nothing, say there is "
                         "no such earlier conversation with this user"),
            }
        return payload


# ------------------------------------------------------------------- writes


SUPPORTED_CORRECTION_FIELDS = ("wellhead_temp_c", "temp_delta_c",
                               "spill_detected", "spill_est_volume_bbl")


def _correction_echo(conn: sqlite3.Connection, field: str, asset_id: str,
                     inspection_id: str | None) -> dict:
    """§5.4: re-query the relevant view(s) so the agent can cite the new value."""
    echo: dict = {}
    if field in ("wellhead_temp_c", "temp_delta_c"):
        rows, trunc = _rows(
            conn,
            "SELECT dataset_id, asset_id, well_name, well_type, area_name, "
            "       recorded_status, latest_inspection_id, latest_inspection_at, "
            "       ambient_temp_c, eff_wellhead_temp_c, eff_temp_delta_c, "
            "       production_threshold_c, is_producing, context_reason, "
            "       open_repair_reason "
            "FROM v_producing_now WHERE asset_id = ?", (asset_id,))
        echo["v_producing_now"] = rows
        echo["view"] = "v_producing_now"
    elif field == "spill_detected":
        sql = ("SELECT dataset_id, inspection_id, asset_id, well_name, spill_date, "
               "       est_volume_bbl, area_name FROM v_spills WHERE asset_id = ?")
        params: list = [asset_id]
        if inspection_id:
            sql += " AND inspection_id = ?"
            params.append(inspection_id)
        rows, trunc = _rows(conn, sql, params)
        echo["v_spills"] = rows
        if inspection_id and not rows:
            echo["note"] = ("the detection is no longer in v_spills — the "
                            "correction removed it at read time")
        echo["view"] = "v_spills"
    elif field == "spill_est_volume_bbl":
        sql = ("SELECT dataset_id, inspection_id, asset_id, well_name, spill_date, "
               "       est_volume_bbl, reported_class, effective_class, "
               "       class_changed, contained_hours_after "
               "FROM v_spill_classified WHERE asset_id = ?")
        params = [asset_id]
        if inspection_id:
            sql += " AND inspection_id = ?"
            params.append(inspection_id)
        rows, _ = _rows(conn, sql, params)
        echo["v_spill_classified"] = rows
        if inspection_id:
            obl, _ = _rows(
                conn,
                "SELECT obligation_protocol, status, deadline_at, limit_value, "
                "       unit, actual_value, detail "
                "FROM v_sobligations WHERE inspection_id = ? "
                "ORDER BY obligation_protocol", (inspection_id,))
            echo["v_sobligations"] = obl
        echo["view"] = "v_spill_classified"
    return echo


@app.tool(annotations=WRITE)
def record_correction(field: str, original_value: str, corrected_value: str,
                      reason: str, asset_id: str | None = None,
                      inspection_id: str | None = None,
                      well_type_scope: str | None = None,
                      author_user_id: str | None = None) -> dict:
    """Correct a stored inspection value (the write path with teeth).

    Use when a user states a stored value is wrong ("the 15 Oct reading for
    WELL-0164 is wrong, it's actually 41.0 °C") — routing ladder rank 1/2. Do
    NOT use for statements that disagree with a DERIVED conclusion (that is a
    claim -> remember(scope='claim')) or for threshold-rule changes
    (that is set_rule).

    Scope comes from what you pass: inspection_id -> this record only; asset_id
    -> this well; well_type_scope -> that whole well type (e.g. 'T350').
    Supported fields: wellhead_temp_c, temp_delta_c, spill_detected (0/1),
    spill_est_volume_bbl — these are the fields the v_* views apply.

    The raw row is NEVER touched: original_value is the audit anchor and a sanity
    check rejects the call when it does not match the live value (the error text
    contains the actual value and the query to re-resolve). The call returns
    the affected v_* view re-queried, so cite "now says ... per COR-<n>".
    """
    field = (field or "").strip()
    if field not in SUPPORTED_CORRECTION_FIELDS:
        raise ToolError(
            f"field '{field}' cannot be corrected. Supported: "
            f"{', '.join(SUPPORTED_CORRECTION_FIELDS)} (the fields the v_* views "
            f"apply).")
    for label, val in (("original_value", original_value),
                       ("corrected_value", corrected_value),
                       ("reason", reason)):
        if val is None or not str(val).strip():
            raise ToolError(f"{label} is required and cannot be empty.")
    if field == "spill_detected":
        original_value = _as_flag("original_value", original_value)
        corrected_value = _as_flag("corrected_value", corrected_value)
    else:
        original_value = _as_float("original_value", original_value)
        corrected_value = _as_float("corrected_value", corrected_value)

    if not (inspection_id or asset_id or well_type_scope):
        raise ToolError(
            "name where the correction applies: inspection_id (record scope), "
            "asset_id (well scope) or well_type_scope (type scope).")

    with closing(db.rw_conn()) as conn:
        scope, ref = None, None
        if inspection_id or asset_id:
            # ---- sanity check against the live row (never trust the claim)
            sql = (f"SELECT dataset_id, inspection_id, asset_id, inspected_at, "
                   f"       {field} AS live_value FROM inspections WHERE 1=1")
            params: list = []
            if inspection_id:
                sql += " AND inspection_id = ?"
                params.append(inspection_id)
            if asset_id:
                sql += " AND asset_id = ?"
                params.append(asset_id)
            if inspection_id:
                sql += " ORDER BY inspected_at DESC"
            else:  # well scope: compare against the well's latest inspection
                sql += " ORDER BY inspected_at DESC LIMIT 1"
            rows = conn.execute(sql, params).fetchall()
            if not rows:
                raise ToolError(
                    f"no inspection found for "
                    f"{'inspection_id ' + inspection_id if inspection_id else 'asset_id ' + asset_id}. "
                    "Re-resolve, e.g.: SELECT inspection_id, asset_id, inspected_at "
                    f"FROM inspections WHERE asset_id = '{asset_id or 'WELL-XXXX'}' "
                    "ORDER BY inspected_at DESC LIMIT 5;")
            order = {ds: i for i, ds in enumerate(db.dataset_order(conn))}
            ref = sorted(rows, key=lambda r: order.get(r["dataset_id"], 999))[0]
            if asset_id and ref["asset_id"] != asset_id:
                raise ToolError(
                    f"{inspection_id} belongs to {ref['asset_id']}, not {asset_id} — "
                    "fix asset_id or drop it.")
            live = ref["live_value"]
            if inspection_id:
                scope = "inspection"
            elif asset_id:
                scope = "asset"
            if not _values_match(field, original_value, live):
                where = (f"inspection_id = '{inspection_id}'" if inspection_id
                         else f"asset_id = '{asset_id}' (latest inspection)")
                raise ToolError(
                    f"original_value mismatch: the DB says {field} = {live} for "
                    f"{ref['inspection_id']} ({ref['inspected_at']}), you sent "
                    f"{original_value}. Do NOT correct on a wrong original — "
                    f"re-read it first:\n"
                    f"  SELECT inspection_id, inspected_at, {field} FROM inspections "
                    f"WHERE {where};\n"
                    f"The raw row is never modified; a correction records the anchor "
                    f"you checked.")
        else:
            scope = "well_type"
            known = [r[0] for r in conn.execute(
                "SELECT DISTINCT well_type FROM wells WHERE well_type IS NOT NULL")]
            if well_type_scope not in known:
                raise ToolError(
                    f"well_type_scope '{well_type_scope}' is not a well type in the "
                    f"data — known: {', '.join(sorted(known))}")

        correction_id = db.next_id(conn, "corrections", "correction_id", "COR-RT-")
        asset_for_row = ref["asset_id"] if ref else None
        insp_for_row = ref["inspection_id"] if scope == "inspection" else None
        type_for_row = well_type_scope if scope == "well_type" else None
        conn.execute(
            "INSERT INTO corrections(dataset_id, correction_id, source, asset_id, "
            "inspection_id, well_type, field, original_value, corrected_value, "
            "reason, author_user_id, created_at, valid_from, valid_to, status) "
            "VALUES (NULL, ?, 'runtime', ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 'applied')",
            (correction_id, asset_for_row, insp_for_row, type_for_row, field,
             _canon(field, original_value), _canon(field, corrected_value),
             reason.strip(), author_user_id, _now()))
        conn.commit()

        payload = {
            "correction_id": correction_id,
            "status": "applied",
            "scope": scope,
            "field": field,
            "original_value": _canon(field, original_value),
            "corrected_value": _canon(field, corrected_value),
            "reason": reason.strip(),
            "author_user_id": author_user_id,
            "author_name": _user_name(conn, author_user_id),
            "recorded_at": _now(),
            "raw_row_untouched": ({"inspection_id": ref["inspection_id"],
                                   field: ref["live_value"]} if ref else None),
            "applies_to": ("every dataset (runtime corrections are not "
                           "dataset-scoped)"),
            "hint": ("cite it as '<value>, per " + correction_id +
                     " <reason>'; corrections win at read time, latest first"),
        }
        if ref:
            payload["matched_inspection"] = {
                "inspection_id": ref["inspection_id"], "asset_id": ref["asset_id"],
                "inspected_at": ref["inspected_at"], "dataset_id": ref["dataset_id"],
            }
        if asset_for_row:
            payload["echo"] = _correction_echo(conn, field, asset_for_row, insp_for_row)
        return payload


def _values_match(field: str, claimed, live) -> bool:
    if live is None or claimed is None:
        return claimed is None and live is None
    if field == "spill_detected":
        try:
            return _as_flag("original_value", claimed) == _as_flag("live", live)
        except ToolError:
            return False
    try:
        return math.isclose(float(str(claimed)), float(str(live)),
                            rel_tol=1e-9, abs_tol=1e-9)
    except (TypeError, ValueError):
        return str(claimed).strip() == str(live).strip()


@app.tool(annotations=WRITE)
def remember(text: str, scope: str,
             well_id: str | None = None, well_type: str | None = None,
             user_id: str | None = None) -> dict:
    """Record what a user taught you — routing ladder rank 3/4.

    scope='well'|'well_type'|'fleet'  -> a SHARED fact every user sees (pass
                                        well_id / well_type accordingly; facts
                                        are attributed to user_id).
    scope='claim'                     -> an UNCONFIRMED statement that disagrees
                                        with a derived conclusion only ("WELL-0175
                                        is running fine" while the view says not
                                        producing). Needs well_id + user_id;
                                        presented as a disagreement, never truth.
    scope='memory'                    -> a PRIVATE note for one user (needs
                                        user_id); no other user ever sees it.

    Do NOT use for: contradictions of a STORED value ("X is wrong, it's actually
    Y") -> record_correction; changes to a threshold RULE -> set_rule.
    """
    text = (text or "").strip()
    if not text:
        raise ToolError("text is required (what should be remembered?).")
    scope = (scope or "").strip().lower()
    if scope not in ("well", "well_type", "fleet", "claim", "memory"):
        raise ToolError(
            "scope must be one of: well, well_type, fleet (shared facts), "
            "claim (unconfirmed), memory (private).")

    with closing(db.rw_conn()) as conn:
        kind, row_id, where = None, None, {}
        if scope in ("well", "well_type", "fleet"):
            if scope == "well":
                if not well_id:
                    raise ToolError("scope='well' needs well_id (e.g. 'WELL-0007').")
                hit = conn.execute("SELECT 1 FROM wells WHERE asset_id = ? LIMIT 1",
                                   (well_id,)).fetchone()
                if hit is None:
                    raise ToolError(
                        f"no well '{well_id}'. Look it up: "
                        "SELECT asset_id, name FROM wells WHERE name LIKE '%...%';")
                scope_value = well_id
            elif scope == "well_type":
                if not well_type:
                    raise ToolError("scope='well_type' needs well_type (e.g. 'T350').")
                known = [r[0] for r in conn.execute(
                    "SELECT DISTINCT well_type FROM wells WHERE well_type IS NOT NULL")]
                if well_type not in known:
                    raise ToolError(
                        f"well_type '{well_type}' is not in the data — known: "
                        f"{', '.join(sorted(known))}")
                scope_value = well_type
            else:  # fleet
                scope_value = "fleet"
            if not user_id:
                raise ToolError("facts are attributed — pass user_id of the person "
                                "who said it (answers cite 'per <name>').")
            row_id = db.next_id(conn, "facts", "fact_id", "FACT-")
            conn.execute(
                "INSERT INTO facts(fact_id, author_user_id, scope, scope_value, "
                "text, created_at, valid_to) VALUES (?,?,?,?,?,?,NULL)",
                (row_id, user_id, scope, scope_value, text, _now()))
            kind, where = "fact", {"scope": scope, "scope_value": scope_value}
        elif scope == "claim":
            if not (well_id and user_id):
                raise ToolError("scope='claim' needs well_id and user_id — claims "
                                "contradict a conclusion about a specific well.")
            hit = conn.execute("SELECT 1 FROM wells WHERE asset_id = ? LIMIT 1",
                               (well_id,)).fetchone()
            if hit is None:
                raise ToolError(f"no well '{well_id}' — check the id.")
            row_id = db.next_id(conn, "claims", "claim_id", "CLAIM-")
            conn.execute(
                "INSERT INTO claims(claim_id, user_id, asset_id, text, status, "
                "created_at) VALUES (?,?,?,?, 'unconfirmed', ?)",
                (row_id, user_id, well_id, text, _now()))
            kind, where = "claim", {"asset_id": well_id, "status": "unconfirmed"}
        else:  # memory
            if not user_id:
                raise ToolError("scope='memory' needs user_id — memories are private "
                                "to one user.")
            row_id = db.next_id(conn, "memories", "memory_id", "MEM-")
            conn.execute(
                "INSERT INTO memories(memory_id, user_id, session_id, text, "
                "created_at) VALUES (?,?,NULL,?,?)",
                (row_id, user_id, text, _now()))
            kind, where = "memory", {"private_to_user_id": user_id}
        conn.commit()
        visibility = {"fact": "shared", "claim": "unconfirmed",
                      "memory": "private"}[kind]
        return {
            "recorded": kind, "id": row_id, **where,
            "text": text, "author_user_id": user_id,
            "author_name": _user_name(conn, user_id),
            "recorded_at": _now(), "visibility": visibility,
            "note": ("facts are visible to every user; claims are disagreements "
                     "until confirmed; memories are private"
                     if kind != "claim" else
                     "claim stored as unconfirmed — say it disagrees with the data, "
                     "ask the user to confirm, and never present it as truth"),
        }


@app.tool(annotations=WRITE)
def set_rule(parameter: str, value: str, applies_to: str = "fleet",
             author_user_id: str | None = None, reason: str | None = None) -> dict:
    """Change a numeric threshold RULE for a well type (or the fleet) — the rule
    feedback path ("note for all T350 wells: RCA after 2 repairs, not 3").

    Writes a runtime override row (is_overridden=1) that every v_* view joins;
    the manual's original row is kept, the override wins from then on. Parameter
    names come from the rules table — look before you write:
      SELECT rule_id, parameter, value, unit, applies_to FROM rules;
    applies_to is 'fleet' or a well type ('T200', 'T350').

    Use this ONLY for threshold/rule changes. Correcting stored data is
    record_correction; unconfirmed opinions are remember(scope='claim').
    """
    parameter = (parameter or "").strip()
    if not parameter:
        raise ToolError("parameter is required — e.g. 'rca_after_n_repairs'. See: "
                        "SELECT parameter, value, unit, applies_to FROM rules;")
    try:
        float(str(value).strip())
    except (TypeError, ValueError):
        raise ToolError(f"value must be numeric, got {value!r}.") from None

    with closing(db.rw_conn()) as conn:
        known_params = [r[0] for r in conn.execute(
            "SELECT DISTINCT parameter FROM rules ORDER BY parameter")]
        if parameter not in known_params:
            raise ToolError(
                f"unknown rule parameter '{parameter}'. Known parameters: "
                f"{', '.join(known_params)}")
        applies_to = (applies_to or "fleet").strip()
        base = conn.execute(
            "SELECT applies_to FROM rules WHERE parameter = ? "
            "GROUP BY applies_to", (parameter,)).fetchall()
        well_types = [r[0] for r in conn.execute(
            "SELECT DISTINCT well_type FROM wells WHERE well_type IS NOT NULL")]
        valid = {"fleet", *well_types, *[r[0] for r in base if r[0]]}
        if applies_to not in valid:
            raise ToolError(
                f"applies_to '{applies_to}' is not valid for '{parameter}' — "
                f"use one of: {', '.join(sorted(valid))}")

        datasets = db.dataset_order(conn)
        if not datasets:
            raise ToolError("no datasets are loaded (wells table is empty).")
        written = []
        for ds in datasets:
            src = conn.execute(
                "SELECT protocol_id, unit FROM rules WHERE dataset_id = ? "
                "AND parameter = ? ORDER BY is_overridden DESC, rowid DESC LIMIT 1",
                (ds, parameter)).fetchone()
            n = conn.execute(
                "SELECT COUNT(*) FROM rules WHERE dataset_id = ? AND parameter = ? "
                "AND source_doc = 'runtime' AND applies_to = ?",
                (ds, parameter, applies_to)).fetchone()[0]
            rule_id = f"{parameter}:{applies_to}:runtime-{n + 1}"
            snippet = (f"runtime override by {author_user_id or 'unknown'}"
                       + (f": {reason.strip()}" if reason else ""))
            conn.execute(
                "INSERT INTO rules(dataset_id, rule_id, protocol_id, parameter, "
                "value, unit, applies_to, is_overridden, source_doc, source_snippet) "
                "VALUES (?,?,?,?,?,?,?,1,'runtime',?)",
                (ds, rule_id, src["protocol_id"] if src else None, parameter,
                 str(value).strip(), src["unit"] if src else None, applies_to,
                 snippet))
            written.append({"dataset_id": ds, "rule_id": rule_id})
        conn.commit()
        payload = {
            "parameter": parameter, "value": str(value).strip(),
            "applies_to": applies_to, "written": written,
            "author_user_id": author_user_id,
            "note": ("runtime override (is_overridden=1); the manual's original row "
                     "is kept — answers must say this follows the user's rule, not "
                     "the manual"),
        }
        if parameter == "rca_after_n_repairs":
            rows, _ = _rows(conn,
                            "SELECT dataset_id, asset_id, well_name, well_type, "
                            "equipment_kind, corrective_count_window, "
                            "rca_after_n_repairs, rca_due FROM v_rca_due "
                            "WHERE well_type = ? OR ? = 'fleet' "
                            "ORDER BY asset_id, equipment_kind LIMIT 200",
                            (applies_to, applies_to))
            payload["echo"] = {"v_rca_due": rows}
        return payload


@app.tool(annotations=WRITE)
def log_message(session_id: str, user_id: str, role: str, content: str,
                referenced_wells: list[str] | None = None) -> dict:
    """Log one conversational turn (call it every turn — user AND assistant).

    This is the cheapest possible conversation memory: it powers "the wells we
    discussed yesterday" via the referenced wells, always per user (sessions are
    private to their user). `referenced_wells` = the wells this turn was about
    (e.g. ['WELL-0121','WELL-0138']); pass the assistant's answer too, with the
    same wells. Creates the session row on first call.
    """
    session_id = (session_id or "").strip()
    if not session_id:
        raise ToolError("session_id is required.")
    role = (role or "").strip().lower()
    if role not in ("user", "assistant", "system"):
        raise ToolError("role must be 'user', 'assistant' or 'system'.")
    if not content or not str(content).strip():
        raise ToolError("content is required.")
    wells: list[str] = []
    if isinstance(referenced_wells, str):
        referenced_wells = [w for w in referenced_wells.replace(";", ",").split(",")]
    for w in referenced_wells or []:
        w = str(w).strip().upper()
        if w and w not in wells:
            wells.append(w)

    with closing(db.rw_conn()) as conn:
        conn.execute(
            "INSERT INTO sessions(session_id, user_id, started_at, title) "
            "VALUES (?,?,?,?) "
            "ON CONFLICT(session_id) DO UPDATE SET "
            "user_id = COALESCE(NULLIF(sessions.user_id, ''), excluded.user_id)",
            (session_id, user_id, _now(),
             content.strip()[:80] if role == "user" else None))
        message_id = db.next_id(conn, "messages", "message_id", "MSG-")
        conn.execute(
            "INSERT INTO messages(message_id, session_id, role, content, "
            "referenced_wells_json, created_at) VALUES (?,?,?,?,?,?)",
            (message_id, session_id, role, content.strip(), json.dumps(wells), _now()))
        conn.commit()
        return {
            "message_id": message_id, "session_id": session_id,
            "user_id": user_id, "role": role,
            "referenced_wells": wells, "logged_at": _now(),
            "note": ("recall(user_id=...) will surface these wells to this user "
                     "only — never across users"),
        }


# -------------------------------------------------------------------- entry


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Well Copilot MCP server (stdio)")
    ap.add_argument("--db", default=None,
                    help="SQLite DB path (default: env WELL_COPILOT_DB, else "
                         "data/well_copilot.db)")
    args, _unknown = ap.parse_known_args(argv)
    db.configure(args.db)
    if not db.db_path().exists():
        print(f"[well-copilot] WARNING: DB not found at {db.db_path()} — tool "
              f"calls will fail until it is built (see README).", file=sys.stderr)
    app.run(transport="stdio")


if __name__ == "__main__":
    main()
