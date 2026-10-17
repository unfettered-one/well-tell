# Ingest — Well Copilot

Builds the single SQLite DB (`well_copilot.db`) from a dataset folder:
raw tables + rules parsed from the dataset's own manuals/SOPs + the 11 derived
views, then hard-fail verification. stdlib only — no pip deps.

## Run

```bash
# build from the sample dataset
python ingest/ingest.py \
    --data dataset/flytbase-ahc-swe-asset-intelligence-dataset/sample-data \
    --dataset sample \
    --db data/well_copilot.db

# load the test dataset alongside the sample (final 2 hours)
python ingest/ingest.py \
    --data dataset/flytbase-ahc-swe-asset-intelligence-dataset/test-data/dataset \
    --dataset test --as-of 2027-01-15 --db data/well_copilot.db

# full rebuild from scratch
python ingest/ingest.py --data <path> --dataset sample --db data/well_copilot.db --fresh
```

## Files

| File | Role |
|---|---|
| `create.py` | DDL: tables + indexes + `meta` (runtime tables created empty) |
| `ingest.py` | CLI entry: parse folder → insert → seed rules → apply views → verify |
| `views.py` | The derived views (`v_producing_now`, `v_downtime`, `v_spills`, `v_spill_classified`, `v_sobligations` incl. RC-04, `v_rca_due`, `v_repairs_corrective`, `v_conflicts`, `v_repairs_costs`, `v_inspection_effective`) |
| `verify.py` | Hard-fail checks (standalone-runnable: `python ingest/verify.py --db data/well_copilot.db`). Golden checks run against the ingested baseline — runtime corrections/overrides are hidden inside a rolled-back transaction |

## Behavior

- **`--dataset sample|test`** — `dataset_id` stamped on every ingested row
  (composite PKs `(dataset_id, <id>)` so ID reuse can't collide). Default: sniffed
  from the folder name; fatal if ambiguous.
- **Default mode = replace per dataset** — deletes this `dataset_id`'s rows and
  re-inserts in one transaction. Idempotent; runtime tables untouched.
- **`--fresh`** — delete the DB file first.
- **`--as-of YYYY-MM-DD`** — the eval "today". Default: `max(inspected_at) + 1 day`
  (sample → 2026-10-16). Stored per dataset in `meta.as_of_<dataset_id>`;
  the global date is the latest dataset date. Views never use `date('now')`.
- **Rules are parsed from the dataset's own docs** — nothing hardcoded. Every
  expected rule key must be found (hard-fail naming rule + file otherwise); on the
  sample, values must match the known set. `--allow-override` is the escape hatch:
  an unmatchable rule is inserted as a known row with `is_overridden=1`.
- **Expanded test data** — all Markdown files under `fleet/` are cataloged;
  T500 thresholds and its ESP-specific RCA trigger are parsed from its manual.
  Structured `data_correction` notes, type/team histories, late-entry timestamps,
  cost revisions, and report parts/follow-up sections are retained in queryable
  columns/tables. Existing databases are upgraded in place by `create_schema`.
- **Verification gate** — row counts, FK orphans, report-file resolution,
  extraction coverage, rule cross-checks, and (sample only) the golden answers
  from `03-evaluation-queries.md` (Q2/Q4/Q5/Q6/Q10/Q18 + rules snapshot), run
  against the ingested baseline. Any failure → non-zero exit.

## Runtime contract (for the MCP server — review F7/R1/R2)

- `record_correction`: **`dataset_id` must be NULL** — runtime corrections are
  event knowledge and apply to every dataset; the views' dataset matching
  (`c.dataset_id = i.dataset_id OR c.dataset_id IS NULL`) already treats NULL
  as global, and the verify count checks assume ingested corrections are the
  only dataset-scoped rows.
- `record_correction`: **do not stamp `valid_from` with the wall-clock date** —
  views gate on `valid_from <= as_of(dataset)`; a wall-clock date after the
  eval "today" would be silently invisible. Use `NULL` or the dataset's `as_of`.
- Runtime `correction_id`s must be unique (`COR-runtime-<uuid>`); the
  corrections PK `(dataset_id, correction_id)` does not enforce uniqueness when
  `dataset_id` is NULL.
- Runtime rule overrides: `rules.dataset_id` is matched per active dataset by
  the views — insert the override row with the dataset the user is working in
  (`sample` or `test`), `is_overridden=1`, `source_doc='runtime'`.
  **`rule_id` must not reuse an ingested rule's id** (PK conflict) — use e.g.
  `rca_after_n_repairs:T350:override` or another unique id; views match by
  `parameter` + `applies_to`, so the id itself is free. Overrides **survive
  re-ingest** (replace-per-dataset skips them) — that's the Q14 persistence
  guarantee; `--fresh` is the only thing that clears them.
- Structural check note: verify hides `source='runtime'` corrections and
  `is_overridden=1 AND source_doc='runtime'` rules during golden checks and
  counts them out of the structural row counts — never write runtime state
  with other `source_doc` markers.
