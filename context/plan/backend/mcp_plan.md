# MCP Server Plan — Well Copilot (detailed build spec)

Companion to `database_plan.md` (DB design), `ingest_plan.md` (how the DB is built), and
`high_level_backend_plan.md` (system flow). This file is the implementation plan for the
`mcp/` folder. Written after the DB was built and verified (17 Oct 2026): the DB is
`data/well_copilot.db` (WAL mode, 19 tables + 11 views, `as_of = 2026-10-16`, all ingest
golden checks green). This session covers **MCP only** — agent config (`opencode.json`),
FastAPI bridge, and eval are separate later pieces.

---

## 1. Role and shape

```
Dataset files ─ingest─▶ SQLite DB ◀─MCP server─▶ copilot agent ─▶ chat UI
                    (built ✅)      (this plan)     (next piece)
```

The MCP server is a passive middleman: the LLM cannot read a DB or files by itself, so we
expose a small set of tools it can call. Reads run against the `v_*` views (all domain
math lives in SQL); writes land only in runtime tables (`corrections`, `facts`,
`memories`, `claims`, `messages`). The server **never pushes** anything — every lookup is
an agent tool call, steered by tool docstrings + `prompts.py`.

## 2. Decisions (locked)

| Decision | Choice | Why |
|---|---|---|
| SDK | **FastMCP from the official `mcp` PyPI package** (`from mcp.server.fastmcp import FastMCP`) | Canonical, stdio transport, one dep; not the separate `fastmcp` package |
| Transport | stdio | Local single-process; OpenCode registers it directly |
| Language | Python, everything stdlib except `mcp` | Matches ingest discipline |
| Chat logging | **Yes — `log_message` tool** | Q16-style recall ("wells we discussed yesterday") works from session one |
| Report ergonomics | **Yes — `get_report(maintenance_id)`** | Resolves `maintenance.report_file` via SQL; no hand-built paths on test day |
| Schema helper | **Yes — `describe(name)` + `list_tables()`** | LLM never guesses columns from memory |

## 3. File layout

```
mcp/
  server.py      # FastMCP app: all 9 tools, stdio entrypoint
  db.py          # ro_conn() + rw_conn(); WAL, busy_timeout=5000; path from meta
  documents.py   # resolve + read docs/reports against meta.dataset_root_*
  prompts.py     # routing ladder, citation rules, "views not raw" — shipped as MCP prompt resource
  README.md      # how to run + register (judged repo)
```

`requirements.txt` gains only `mcp`. DB path resolution: `--db data/well_copilot.db`
default, overridable by env `WELL_COPILOT_DB`.

## 4. The 9 tools

### Read tools (annotated `read_only_hint=True, idempotent_hint=True` so clients skip approval prompts)

| Tool | Args | Returns | Mechanics |
|---|---|---|---|
| `query_db` | `sql` | `{columns, rows, rowcount, truncated}` | Read-only, capped at 50 rows with `truncated: true` + "narrow with WHERE/LIMIT" hint — agent narrows, never skims |
| `list_tables` | — | table/view names | one call over `sqlite_master` |
| `describe` | `name` | columns, types, PK/FK | `PRAGMA table_info` / `view` column output |
| `get_doc` | `path` | file text | validates path against the `documents` catalog, reads from disk via `meta.dataset_root_*`; rejection names the join that finds the right path |
| `get_report` | `maintenance_id` | report markdown | SQL-resolves `maintenance.report_file` (per dataset), then reads the file |
| `recall` | `query?`, `well_id?`, `user_id?` | facts + memories + open claims, each tagged `shared / private / unconfirmed` | honesty pillar is in the payload shape: unconfirmed claims surface as disagreements, never truth |

### Write tools

| Tool | Args | Writes | Mechanics |
|---|---|---|---|
| `record_correction` | `asset_id`, `inspection_id?`, `field`, `original_value`, `corrected_value`, `reason`, `well_type_scope?` | `corrections` | see §5 |
| `remember` | `text`, `scope` (`well`/`well_type`/`fleet`), `well_id?`, `well_type?`, `user_id?` | `facts` (shared) or `memories` (private; `user_id` required) | scope validated; privacy is structural (shared tables have no user_id column) |
| `log_message` | `session_id`, `user_id`, `role`, `content`, `referenced_wells` | `messages` | called every turn per system-prompt instruction; powers `referenced_wells_json` recall |

Claims are not a separate tool: rank-3 routing-ladder statements go through `remember`
into `claims` with `status='unconfirmed'`; promotion to fact/correction happens only on
explicit confirmation (promoting user recorded).

## 5. `record_correction` — the write path with teeth (database_plan §6 verbatim behaviors)

1. **Sanity check**: re-read `inspections.<field>` for that row, compare to claimed
   `original_value` → mismatch = reject with the *actual* live value + the resolution
   query to run (corrective errors — an agent retries from the error text).
2. **Scope from row shape**: `inspection_id` → record-scoped; `asset_id` → well-scoped;
   `well_type` → type-scoped. Scope never leaks past the record (it lives on the row,
   not in logic).
3. **Insert** with `source='runtime'`, `status='applied'`, `dataset_id=NULL` (applies to
   every dataset); raw tables are never touched; `original_value` is the audit anchor.
4. **Echo**: re-query the relevant view for that well and return it, so the agent can
   cite "now says producing, per COR-<n>".

## 6. Read-only enforcement — three stacked layers (community-validated)

1. **File level**: open the DB via `file:...?mode=ro` URI — even a bypassed guard
   physically cannot write.
2. **Connection level**: `PRAGMA query_only=ON`.
3. **Statement level**: strip comments, reject multi-statement strings (blocks
   CTE-smuggled writes like `WITH x AS (...) INSERT ...`), whitelist only statements
   starting with `SELECT` / `WITH` / `EXPLAIN`.

The three write tools use a separate read-write connection (`busy_timeout=5000`; WAL is
already on from ingest, so a mid-chat test-dataset re-ingest never blocks or corrupts).

## 7. What is automatic vs prompt-enforced (the honest split)

**Automatic (in SQL, the agent cannot forget it):**
- rules/thresholds — every view joins `rules` (15/20 °C, 7-day downtime, SR-01 24 h…)
- corrections — views apply the `corrections` table at read time (latest wins, temporal
  validity, scope by row shape)
- extracted report facts — `report_facts` is a table, so containment hours, spill class,
  root cause, "Action required" come back as ordinary query columns

**Prompt-enforced (cheap habit, one extra call):**
- `recall(well_id=...)` before answering anything well-specific → shared facts show up
  for every user
- `get_report(maintenance_id)` when `report_facts.extraction_status='fts_only'` or the
  question needs the report's actual wording

`prompts.py` ships this as a hard rule the copilot agent's system prompt includes
verbatim: *for every well-specific answer — (1) query the `v_*` view, never raw tables;
(2) call `recall` for that well; (3) follow inspection → maintenance → report when the
fact isn't in `report_facts`; (4) cite record IDs for every claim; (5) "not in the data"
is a legitimate answer — an empty result is never padded.*

Also in `prompts.py`: the routing ladder (database_plan §7) and `meta.as_of` over
`date('now')` (wall clock ≠ eval date).

## 8. Coverage when a question matches no view

Views are the fast path, not the only path:

| Question type | Path |
|---|---|
| Status, downtime, spills, costs, obligations, RCA, conflicts | `v_*` views (math is automatic) |
| Any other slice of raw data | ad-hoc `query_db` on raw tables (full SQL engine; `describe` first) |
| Report/document wording | `get_report` / `get_doc` |
| Not in the data at all | "not found" — stated honestly |

Escape hatch on eval day: if the agent repeats one computation or does mental arithmetic,
that computation becomes a **new view in `views.py`** + re-ingest (one command) — never
trusting the LLM to multiply. Held in reserve: a "get everything about WELL-X in one
call" convenience view/tool if the recall/report habit doesn't stick during eval.

## 9. Tool docstrings as the steering surface (community-validated)

Models reach for the loosest tool offered — so every docstring states *when not to use
the tool* and points at the tighter alternative:

- `query_db`: "…for production status/downtime/spill/SOP-deadline questions, query the
  `v_*` views — never compute from raw tables."
- `get_doc`: "…prefer `get_report(maintenance_id)` for repair reports; this is for
  manuals/SOPs by catalog path."
- `remember`: "…contradictions of stored data belong in `record_correction`, not here;
  unconfirmed opinions go to `claims` via scope='claim'."

## 10. Test-day story

Zero MCP changes. Re-run ingest with `--dataset test` (per `ingest_plan.md` per-dataset
replace): `query_db` picks up new rows, `get_doc`/`get_report` resolve through the new
`meta.dataset_root_test`, rules + views re-seed, runtime tables untouched.

## 11. Build order + smoke test

1. `db.py` + `documents.py` (testable standalone against the real DB)
2. `server.py` — all 9 tools + annotations
3. `prompts.py` — ladder + citation rules as prompt resource
4. Smoke test with raw MCP Inspector / direct calls: Q1 (`v_producing_now` WELL-0001),
   Q4 (`v_spills` → 6 spills / 15.1 bbl), Q10 (`get_report` WELL-0082 → ≈7.1 h),
   a correction round-trip (`record_correction` then re-query the view), a
   recall/log_message round-trip
5. README

Then, separate sessions: `opencode.json` + copilot agent (consumes `prompts.py`), `api.py`
FastAPI bridge, `eval.py` on Q1–Q18.

## 12. Out of scope for this piece

`opencode.json` / agent definition, FastAPI bridge, eval harness, FTS (removed by
design, database_plan §4), `/correct` UI affordance, claim-promotion UX.
