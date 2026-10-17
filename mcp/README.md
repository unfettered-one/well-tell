# MCP — Well Copilot

The copilot's tool surface (mcp_plan.md): a passive MCP server over the
`well_copilot` SQLite DB. The LLM can't read a database by itself, so every
lookup is one of the ten tools below — reads run against the derived `v_*`
views (all domain math lives in SQL), writes land only in runtime tables
(`corrections`, `facts`, `memories`, `claims`, `messages`, `rules` overrides).
The server never pushes anything; behavior is steered by the tool docstrings
and by `prompts.py`.

Transport is **stdio**, SDK is the official `mcp` package (v1 `FastMCP` and v2
`MCPServer` are both handled). Everything else is stdlib.

## Run

```bash
python mcp/server.py                            # data/well_copilot.db (default)
python mcp/server.py --db data/well_copilot.db  # explicit
WELL_COPILOT_DB=/path/to.db python mcp/server.py
```

Resolution order: `--db` > env `WELL_COPILOT_DB` > `data/well_copilot.db`.
A missing DB is a warning, not a crash — tool calls fail with a corrective
message until `ingest/ingest.py` has built the DB.

Normally you do **not** run it by hand: an MCP client starts it and speaks
JSON-RPC over stdin/stdout.

## Register (OpenCode)

```jsonc title="opencode.jsonc"
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "well-copilot": {
        "type": "local",
        "command": [".venv/bin/python", "mcp/server.py"],
        "cwd": "."
      }
    }
  }
}
```

- Server `instructions` (from `prompts.py`) are added to OpenCode's system
  prompt automatically as `<mcp_instructions>`; the complete behavioral contract
  is supplied at initialization, so an agent need not fetch a prompt resource.
- The prompt resources become commands: `/well-copilot:copilot_system_prompt`,
  `:routing_ladder`, `:answer_protocol` — the copilot agent's system prompt
  includes `copilot_system_prompt` verbatim.
- Clients that honor tool annotations (`read_only_hint=true` on all six read
  tools) can skip approval prompts for reads.

The repository also ships `opencode.json` and the HTTP bridge. API-created
conversations start this server with `--require-session`: private recall and
write attribution are bound to the stored OpenCode-session owner, using call
metadata, rather than trusting a model-supplied user ID. `query_db` cannot read
private `memories`, `messages`, `sessions` or `backend_conversations` tables.
Standalone local MCP clients retain the explicit user_id interface.
See the root [README](../README.md) for the local/trusted security boundary.

## Files

| File | Role |
|---|---|
| `server.py` | FastMCP/MCPServer app: all tools + prompt resources, stdio entrypoint |
| `db.py` | `ro_conn()` / `rw_conn()`, the 3-layer read-only guard, id/meta helpers |
| `documents.py` | resolve + read docs/reports against `meta.dataset_root_<dataset>` |
| `prompts.py` | routing ladder, citation rules, answer protocol (single source of truth) |

## Tools

| Tool | Kind | What it does |
|---|---|---|
| `query_db(sql)` | read | ONE SELECT/WITH/EXPLAIN; capped at 50 rows with a narrow-it-down hint |
| `list_tables()` | read | tables, `v_*` views, loaded datasets + each one's `as_of` ("today") |
| `describe(name)` | read | columns, types, PK, relationships, row count — call before raw queries |
| `get_doc(path)` | read | a cataloged manual/SOP by path from the `documents` table |
| `get_report(maintenance_id)` | read | a repair report by id (SQL-resolves `report_file`) + extracted facts |
| `recall(query?, well_id?, user_id?)` | read | shared facts + the user's private memories + unconfirmed claims + conversation |
| `record_correction(...)` | write | correct a stored inspection value; sanity-checked, raw row untouched |
| `remember(...)` | write | shared fact / unconfirmed claim / private memory (routing ladder 3–4) |
| `set_rule(...)` | write | threshold-rule override for a well type or the fleet (Q14/B14 path) |
| `log_message(...)` | write | one conversational turn + `referenced_wells`; powers "wells we discussed" |

The first nine are the mcp_plan §4 set; `set_rule` is the extra write path the
DB design explicitly anticipates (database_plan.md §5, `is_overridden=1`) —
without it there is no tool for "for all T350 wells: RCA after 2 repairs".

## Read-only enforcement (db.py, three stacked layers)

1. **File** — `file:...?mode=ro` URI: even a bypassed guard cannot write.
   A WAL database with no `-shm` file cannot be opened read-only (SQLite can't
   create the shared-memory file), and the failure is lazy; `ro_conn()` probes
   a real read inside the `try` and falls back to layer 2 for exactly that case.
2. **Connection** — `PRAGMA query_only=ON`, always applied.
3. **Statement** — `validate_readonly_sql()`: strips comments/literals, rejects
   multi-statement strings and non-`SELECT`/`WITH`/`EXPLAIN` heads or
   CTE-smuggled writes (`WITH x AS (...) INSERT ...`).

## Runtime contracts (what the write tools must get right)

- **`record_correction`** — sanity-checks `original_value` against the live
  row and rejects with the *actual* value + the re-resolve query; inserts with
  `source='runtime'`, `status='applied'`, **`dataset_id=NULL`** (applies to
  every dataset) and **`valid_from=NULL`** (wall-clock dates after `as_of`
  would be invisible); ids are `COR-RT-NNNN`. Echoes the affected `v_*` view.
- **`remember`** — `fact` rows are shared (no user_id column) and attributed
  (author required, answers cite "per <name>"); `claim` rows are
  `status='unconfirmed'` disagreements, never truth; `memory` rows are private
  (user_id required). Privacy is structural.
- **`set_rule`** — runtime override rows (`is_overridden=1`,
  `source_doc='runtime'`) written **per loaded dataset** so the override wins
  whichever dataset the next question touches (runtime knowledge is
  dataset-agnostic, database_plan.md §1); the manual's original row is kept;
  overrides survive re-ingest (replace-per-dataset skips runtime rows).
- **`log_message`** — auto-creates the session; stores `referenced_wells_json`
  for per-user "the wells we discussed yesterday" recall.

`ingest/README.md` §"Runtime contract" is the ingest-side view of the same
rules; the tests below assert them.

## 'Today' and two datasets

`meta.as_of_<dataset>` (fallback `meta.as_of`) is "today" for that dataset —
never `date('now')`. Sample + test datasets coexist (replace-per-dataset
ingest); answers must filter `dataset_id`. Docs/reports resolve through
`meta.dataset_root_<dataset>`; when an id exists in both datasets, the newest
dataset (by `as_of`) is the reference and the payload says so.

## Tests

```bash
pytest tests/                                  # everything (fast: ~3 s)
pytest tests/test_mcp_smoke.py -q              # end-to-end over real stdio
pytest tests/test_mcp_units.py -q              # guards, path helpers, ro_conn
```

Both suites run against a private copy of `data/well_copilot.db` (sqlite
backup API); the round-trip tests (correction, memory, rule override) never
touch the real DB. `tests/test_mcp_smoke.py` spawns `mcp/server.py` exactly the
way `opencode.json` would, on a copy, and walks the mcp_plan §11 checklist:
Q1/Q4/Q10 gold values, read-only rejections, correction → view flip, recall /
log_message privacy, `set_rule` → `v_rca_due` (T350 flips, T200 trap stays
manual, original row kept).
