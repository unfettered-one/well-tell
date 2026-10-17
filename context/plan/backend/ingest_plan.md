# Ingest Plan — Well Copilot (detailed build spec)

Companion to `database_plan.md` (design decisions) and `db-schema.drawio` (schema).
This file is the **implementation plan for the `ingest/` folder**: file layout, exact
data shapes (verified against the real sample dataset), extraction patterns, seeding
logic, views, and the verification gate. Everything here was checked against
`dataset/flytbase-ahc-swe-asset-intelligence-dataset/sample-data/` on 17 Oct 2026.

---

## 1. File layout (decided)

```
ingest/
  create.py    # tables + indexes + meta table (DDL as Python, drop-and-recreate on --fresh)
  ingest.py    # CLI entry: parse dataset folder -> INSERT everything; imports create/views/verify
  views.py     # the 8 derived views (accuracy layer) as SQL, applied after data load
  verify.py    # hard-fail checks; standalone-runnable + called by ingest.py at the end
  README.md    # how to run (for the judged repo)
```

One command builds the working DB:

```bash
python ingest/ingest.py --data dataset/flytbase-ahc-swe-asset-intelligence-dataset/sample-data \
                        --dataset sample \
                        --db data/well_copilot.db
```

- `--dataset sample|test` — `dataset_id` stamped on every ingested row. Default: sniff
  from folder name, fatal if ambiguous.
- **Default mode = replace per dataset**: delete the rows belonging to this `dataset_id`
  (all ingested tables + rules/report_facts for it, then re-seed views) inside one
  transaction; runtime tables are never touched. Idempotent — re-running never
  duplicates. This is what makes the final-2-hours test load *alongside* the sample.
- `--fresh` — delete the DB file first, full rebuild (dev loop + eval-day reset).
- `--as-of YYYY-MM-DD` — the evaluation "today". Default = `max(inspected_at) + 1 day`
  (for sample: 15 Oct + 1 = **16 Oct 2026**, matching the eval doc). Stored in `meta`,
  used by all "right now / last N months" view logic. We must NOT use `date('now')`
  (wall clock ≠ eval date).
- stdlib only (json, sqlite3, re, argparse, pathlib). No pip deps. Bulk insert via
  one transaction + `executemany` — 40k inspections in seconds.

## 2. Verified dataset shapes (what ingest must parse)

Counts on sample: **200 wells, 39,567 inspections, 5,665 maintenance
(4,156 scheduled / 1,509 corrective), 1,509 reports, 90 regulatory events, 141
context notes (82 operator_note / 56 correction / 3 operator_feedback).**

| Source | Shape notes |
|---|---|
| `fleet/areas.json` | `{areas:[{area_id,name,team_id,center{lat,lon},asset_ids}], teams:[{team_id,name,lead_user_id}]}` — **team names live here**, not in users.json. Insert teams first, then areas; `asset_ids` is redundant (metadata.json has area_id per well) — not stored. |
| `fleet/users.json` | `{users:[{user_id,name,role,team_id}]}` — 15 users, 6 roles. |
| `assets/WELL-XXXX/metadata.json` | flat fields + `equipment[]` (6 kinds; `separator` only on 94 of 200 wells). `asset_category` asserted `oil_well` singleton. `last_inspection` + `recorded_status` stored as-is (stale by design). |
| `inspections.jsonl` | one JSON per line; `evidence_images` is a list → store as JSON text. Compute `temp_delta_c = wellhead_temp_c − ambient_temp_c` at load. |
| `maintenance.jsonl` | flatten `cost_usd{labor,parts,total}` into three columns. Corrective rows always have `report_file` + `triggered_by_inspection_id` (verified: 1509/1509, zero missing files, zero orphan triggers). |
| `maintenance-reports/*.md` | parsed at ingest only (see §4). Files stay on disk; DB keeps the path. |
| `regulatory-events.jsonl` | direct map, all keys are columns. |
| `context.jsonl` | keys: `note_id, asset_id, created_at, author_user_id, note_type, inspection_id (corrections only), text, valid_from, valid_to`. |

Composite PKs `(dataset_id, <id>)` on every ingested table so test-day ID reuse can't
collide with sample rows. Orphan FK check at verify.

## 3. Corrections mirror (the one effective layer)

`context.jsonl` rows with `note_type='correction'` → copied into `corrections` with
`source='ingested'`; the original note row stays in `context_notes` untouched.
Non-correction notes never enter `corrections` (Q18: opinions ≠ corrections).

**Verified: all 56 of 56 correction notes match exactly one regex pattern** (4 distinct
reasons across all of them: rainwater/wet soil, produced water, pump-jack shadow):

```
^Inspection (INS-\S+): <reason>. (Not a (crude )?spill\.?)$
```

→ emits: `field='spill_detected'`, `original_value='1'` (the JSON bool stored as text),
`corrected_value='0'`, `reason=<note text>`, `author_user_id`/`created_at`/
`valid_from`/`valid_to` copied, PK `correction_id = 'COR-' + note_id`, plus

- a micro-normalizer for the wording variants above.
- covers the *format contract*: anything not matching → row dropped +
  `unparsed_corrections` in `meta` ≥ 1 → verify hard-fails.

Non-numeric corrections (temp/volume rewrites) are runtime-only (Q12/Q13) — the MCP
`record_correction` tool inserts them with `original_value` sanity-checked against the
live row before use. Ingest does not need to anticipate their format.

## 4. Report extraction (safe because format is guaranteed identical in test data)

Walk `maintenance-reports/*.md` once; per file write one `report_facts` row
(PK/FK `maintenance_id`):

| Column | Pattern (verified) | Coverage on sample |
|---|---|---|
| `contained_hours_after` | `contained about (X) hours` (`contained about 7.1 hours after the inspection` / after the inspection flight) | 616/1509 have SR-02 (only spill repairs mention it) |
| `rca_action_required` | `Action required` | 307/1509 |
| `spill_class` | `(minor|moderate|reportable|major) class` | 616 classed: 443 moderate / 137 minor / 36 reportable |
| `root_cause` | text under `## Root cause` (all 1509 files have the section) | 1509/1509 |

- `extraction_status='full'` when regexes hit; `'fts_only'` when a field that should
  exist is missed → agent falls back to `get_doc(path)` at runtime.
- Print per-field coverage; **hard-fail below 95 %** of *expected* (for class/contained,
  expected = rows with the SOP-relevant ending… simplest robust proxy: contained/class
  coverage ≥ 99 % **of spill-repair rows**, defined as `maintenance` rows whose report
  mentions SR-02 — verified 616/616 on sample).
- Sanity: Q10 WELL-0082 ≈ 7.1 h must extract (golden check, sample only).

## 5. Rules seeding — parsed from the dataset's OWN docs (decided)

No threshold is hardcoded in SQL/prompts (database_plan.md §5). `ingest.py` parses the
manuals/SOPs into `rules(rule_id, protocol_id, parameter, value, unit, applies_to,
is_overridden, source_doc, source_snippet, dataset_id)`.

**Mechanics proven on the real files: 28/28 extractions hit** after (a) whitespace
normalization — line breaks split sentences ("above\nambient"), (b) `\**` at
inconsistent bold markers, (c) word-numbers ("**Three** or more" → 3). Notable
cross-check: T200 §10 and T350 §6 both give RCA after **3** corrective repairs → assert
they agree.

Seeded set (parameter → value → source on sample):

```
production_threshold        15 °C   T200.md §9.3      20 °C  T350.md §3
overtemp_alarm_c            85 °C   T200.md §9.4      95 °C  T350.md §4
spill_shutin_area_pct       5 %     T200.md §9.5 (+ T350 §5 "same as")
rca_after_n_repairs         3       T200.md §10       + rca_lookback_months 12
downtime_report_days        14      T200.md §10 (RC-03 same, regulatory SOP)
sr01_hours                  24 h    SR-01 (major: 2 h → sr01_major_hours)
sr02_contain_hours          4 h     SR-02
sr03_tph_pct 1.0 · sr03_samples 4 · sr03_verify_days 60          SR-03
spill_minor_max_bbl 1 · spill_moderate_max_bbl 5 · spill_major_min_bbl 25   SR §3
moderate_hse_notice_hours   72      SR §3 notes
rc01_inspection_days 14 · rc03_report_days 14 · rc04_nov_response_days 30
ws03_stopwork_ppm 10 · ws04_lel_pct 10 · ws05_test_multiple 1.25 · ws05_hold_hours 4
ws07_report_days 3                                              Field-Work SOP
planned_shutin_log_required 1 (flag, not parsed number)          T200.md §4
```

Guards at seed time (fail-safe, never fail-silent):
1. whitespace-normalize every doc before matching (proven necessary);
2. **hard-fail**: every expected rule key must exist — `rule 'sr01_hours' not found in
   spill-response-sop.md` with the file named;
3. `--dataset sample`: values must equal the known set above (hard-fail on drift);
4. test dataset: structural checks only (every key present, T200/T350 cross-checks) —
   values come from the test's own docs, that is the point;
5. ingest prints the full rules table as `value ← "source sentence fragment"` for a
   5-second human eyeball;
6. escape hatch: a rule no regex can catch (docs reworded under time pressure) is
   inserted as a known row with `is_overridden=1` — the same mechanism Q14 uses.

Downtime = 7 days/finding is **not** in the docs — it's a Dataset-Guide rule. Seeded as
`downtime_days_per_finding=7` with `source_doc='dataset-guide'` (value asserted on
sample; if the test guide ever disagrees, this is the one row we'd update by hand —
it's the only doc-external rule).

## 6. Views (applied last via views.py; recreated per ingest)

All math lives here — joins `rules` + `corrections`, never hardcoded thresholds:

| View | Core logic |
|---|---|
| `v_inspection_effective` | base pattern: raw inspections COALESCE'd with latest-applicable corrections (`status='applied'`, temporal window vs `as_of`, precedence by `created_at`, scope via row shape: inspection_id > asset_id > well_type) |
| `v_producing_now` | latest effective inspection per well; delta ≥ `rules.production_threshold` (per well_type); plus `recorded_status` + context-note reasons (CTX-0001-003 style) |
| `v_downtime` | weekly non-producing findings × `downtime_days_per_finding`; filterable window; missed week = 0 |
| `v_spills` | effective spills (`spill_detected=1` and not correction-removed); volume from `spill_est_volume_bbl` |
| `v_repairs_corrective` | corrective repairs per well/equipment/window (joins the RCA rule for Q14) |
| `v_sobligations` | spill → discovery time = inspection time → SR-01/SR-02/SR-03/RC-04 deadlines from `rules`; breach/open vs `as_of` |
| `v_conflicts` | inspection vs non-correction context notes vs runtime claims (Q17/Q18 pairs) |
| `v_repairs_costs` | maintenance cost sums per well/year |

Shared SQL conventions, defined once:
- **corrections.dataset_id matching**: view matches rows where
  `corrections.dataset_id = inspections.dataset_id OR corrections.dataset_id IS NULL`
  → sample corrections never leak into test answers; runtime corrections (NULL) apply
  everywhere.
- **open-work predicate** (defined once, reused): `started_at <= as_of AND
  (completed_at IS NULL OR completed_at >= as_of)` — Q2 "still open" repairs.
- **"latest correction wins"** = correlated latest-row join (Q13's 4.5→5.4 must resolve
  deterministically; audit trail stays visible, never applied).

## 7. Verification (hard-fail ALWAYS — decided)

`verify.py` runs at the end of every ingest (and standalone:
`python ingest/verify.py --db ...`). Any failure → non-zero exit → DB not trusted.

**Structural checks — every dataset:**
- row counts match files parsed (no silent drops); wells=200-equivalent
- `asset_category` singleton; no PK/FK orphans (inspection→maintenance→report chain,
  `related_inspection_id`, correction→inspection)
- every `report_file` resolves on disk (`meta.dataset_root_<id>`)
- extraction coverage thresholds (§4)
- all rule keys present + word/manual cross-checks (§5)
- `as_of` = max(inspected_at)+1d stored in `meta`

**Golden checks — sample only** (values from 03-evaluation-queries.md; skipped for test
datasets, where they're meaningless by definition):
- Q4: WELL-0001 → **6 spills / 15.1 bbl** (INS-0001-0070 excluded via correction)
- Q5: WELL-0001 **2025 downtime = 21 days**
- Q6: NE-07 worst = **49 / 42 / 42** (WELL-0121/0138/0107)
- Q2: 4 non-producing wells in NE-08
- Q10: WELL-0082 contained ≈ **7.1 h**
- Q18: WELL-0101 detection **stands** (two non-correction notes)
- rules snapshot: T200=15, T350=20, SR-01=24, SR-02=4, SR-03=60, reportable=5, RCA=3

Test-day story: new folder + one command. Either rules/coverage auto-adapt, or ingest
aborts naming the exact rule/pattern that missed the new sentence — never silent-wrong.

## 8. `meta` table + runtime namespace

`meta(key,value)`: `as_of`, `built_at`, `ingest_version`, `dataset_root_sample`,
`dataset_root_test` (absolute folder paths — the MCP `get_doc(path)` resolves report +
doc paths against these, per dataset).

Runtime tables (`sessions/messages/memories/facts/claims`) are created empty by
`create.py`: private ones keyed `user_id`, shared ones not (structural privacy).
Runtime `rules` overrides (Q14) UPDATE/INSERT only; the original ingested row is kept
(`is_overridden` marks the winner) — "keep the original value" requirement holds.

## 9. Out of scope (for this script)

MCP server, prompts, opencode agent config, eval harness, FTS (removed by design),
storing report file contents in the DB, `/correct` UI. A new computation during eval =
a new view in `views.py`, not agent-side math.
