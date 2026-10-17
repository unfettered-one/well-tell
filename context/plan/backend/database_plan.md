# Backend DB Plan — Well Copilot (detailed design decisions)

Companion to `db-schema.drawio` (structure) and `high_level_backend_plan.md` (system flow).
This file records **why** the database works the way it does, plus the run-time behaviors that
don't fit on the diagram. Implementation target: `schema.sql` + `ingest.py` (SQLite).

---

## 1. Shape: one SQLite file, three layers

A single `well_copilot.db` with three kinds of content:

| Layer | Written by | Access |
|---|---|---|
| **Raw** (ingested dataset) | `ingest.py` only | read-only for the agent |
| **Derived** (SQL views) | `schema.sql` (recreated at ingest) | the agent's ONLY read path |
| **Runtime** (knowledge + memory) | MCP tools during chat | write via `record_correction` / `remember` / chat logging |

- **`dataset_id` on every ingested table** (`sample` | `test`) — so the final-2-hours test
  dataset loads *alongside* the sample. One connection, no ATTACH gymnastics; cross-dataset
  compare is a WHERE clause.
- Runtime tables have NO `dataset_id` — corrections/facts/memory are event knowledge, they
  apply to the well regardless of which dataset it appeared in.

## 2. `wells` IS the asset table

No separate `assets` table. `metadata.json` has `asset_category` which is always `oil_well`
on all 200 wells — not a discriminator, a constant. Sub-assets (`pump_jack`, `flowline`, …)
live at `equipment` level. Ingest asserts:

```sql
SELECT COUNT(DISTINCT asset_category) FROM wells;  -- must be 1
```

If the test dataset ever introduces a second category: rename `wells` → `assets`, surface
`asset_category` as a real column. FKs from inspections/maintenance/etc. are unchanged
(they reference `asset_id` either way) — a one-line diff, not a redesign.

## 3. Small tables that earn their keep

- **`teams`** (4 rows/dataset): the only source of team *names* ("Southwest Production",
  "Health, Safety & Environment") and `lead_user_id`. Team names are org units, not areas —
  no area maps to TEAM-HSE/TEAM-MX (service teams with no geography). IDs are keys; names
  are answers. All ID→name conversion happens in SQL joins, never by the LLM guessing.
- **`equipment`**: 6 rows per well, feeds Q6-style "which equipment failed" filters.

## 4. NO FTS anywhere — docs stay on disk

Decision: no `documents_fts`, no `reports_fts`, no `notes_fts`. The `search_docs` MCP tool
is REMOVED (from the original plan) — tool surface is now:
`query_db`, `get_doc`, `remember`, `recall`, `record_correction`.

- **`documents`** is a path catalog only (doc_type manual|sop, path, title). The markdown
  lives in the dataset folder on disk; `get_doc(path)` reads it at runtime.
- **Maintenance reports** are never stored in the DB: `maintenance.report_file` holds the
  relative path, resolution needs `dataset_id` + relative path only. Reach reports by
  following the linkage (`inspection → maintenance.triggered_by_inspection_id → report_file`)
  — every SOP question (Q9/Q10/Q13) flows through that link, not keyword search.
- **Manuals/SOPs** are read on demand via `get_doc` for citation wording; the numbers that
  matter live in `rules` (below), not in LLM memory.
- **Context notes** are reached structurally: `context_notes WHERE asset_id = ?` + joins.
  If eval later shows a keyword-search gap (e.g. "find every note mentioning produced
  water"), add ONE FTS index bolted on at ingest — isolated change in the MCP server.

## 5. Rules as data (the accuracy anchor)

`ingest.py` parses the manuals/SOPs and seeds a `rules` table:

```
rules(rule_id, protocol_id, parameter, value, applies_to 'fleet'|well_type,
      is_overridden, source_doc, dataset_id)
```

Seeded rows: `production_threshold` (T200=15 °C, T350=20 °C), `downtime_days_per_finding`=7,
`reportable_spill_bbl`=5 (the reportability cutoff that drives the Q13 cascade),
SR-01 `report_within_h`=24, SR-02 `contain_within_h`=4, SR-03 `cleanup_verify_within_d`=60,
RC-04 `nov_response_within_d`, `rca_after_n_corrective_repairs`=3 (manuals §10),
`planned_shutin_log_required` (T200 manual §4), etc. Add the SOP's spill-class bands
(minor/moderate/major) the same way if the text defines numeric thresholds.

Consequences:

- **No threshold is hardcoded in SQL or prompts.** Views join `rules`; the agent never
  needs to "remember" 15/20/24h — it would just narrate what a view returned.
- **Q14 falls out for free**: a runtime rule update sets `value=2, applies_to='T350',
  is_overridden=1`; `v_repairs_corrective` joins `rules`, so WELL-0120 (T350, 2 repairs)
  is added and WELL-0102 (T200) is untouched.

## 6. Corrections — one table, applied at read time (the "effective layer")

One `corrections` table holds BOTH ingested corrections (`context.jsonl` notes with
`note_type='correction'`, copied in at ingest with `source='ingested'`) and runtime
corrections (`source='runtime'`).

```
corrections(correction_id, source, asset_id, inspection_id, well_type,
            field, original_value, corrected_value, reason, author_user_id,
            created_at, valid_from, valid_to, status 'applied'|'pending')
```

Key mechanics:

- **`inspections` (and all raw tables) are never UPDATEd.** `original_value` on the row IS
  the "keep the original" requirement.
- **Correction precedence is deterministic**: when multiple valid corrections exist for the
  same field on the same record (e.g., Q13's 4.5→5.4, later revised again), the view picks
  the **latest applicable one** by `created_at` (correlated latest-row join, not a naive
  LEFT JOIN which could fan out or pick arbitrarily). Older rows remain in the table as
  the audit trail — visible via `v_conflicts`-style reads if ever needed, never applied.
- **One table, one COALESCE** — no per-field merge logic, no ad-hoc tolerance rules.
  Whether a correction is trusted is a `status` question, expressed once in the view JOIN.
- **Scope enforcement by row shape**: scoping to `inspection_id`/`asset_id` **never leaks past that record**; `well_type` scope only touches T350. Scope lives on the row, not in the logic.
- **Temporal validity** (`valid_from`/`valid_to`) is part of the view JOIN — CTX-0001-003
  (shut-in through 20 Oct) auto-expires from answers after that date. No pruning job.
- **Sanity check in the MCP tool**: `record_correction` re-reads `inspections.<field>` and
  compares the JSON value to the agent's `original_value` — mismatch → reject and re-resolve.
  Prevents correcting the wrong inspection/field, critical on the unseen test dataset.
- **Non-correction opinions stay in `context_notes`** and never touch `corrections`
  (Q18: "produced water" vs "confirmed crude" — neither note is a formal correction).
  `v_conflicts` pairs them with the inspection, so the detection **stands** and both
  sides are shown.

## 7. Runtime routing ladder (goes verbatim into the copilot system prompt)

How the copilot decides where a user statement lands:

```
1. Explicit /correct command (or UI "fix data" intent)
      → record_correction. Forced; no heuristics; sanity check still applies.

2. No command, but statement contradicts a STORED value and asserts the true one
      ("X is wrong, it's actually Y" / "AI said A but real is B" — Q12/Q13 phrasing)
      → record_correction.

3. No command, contradicts a DERIVED conclusion only ("it's running fine"
   while view says not-producing — Q17)
      → claims (status='unconfirmed'). Surface the disagreement, never apply it.

4. Everything else
      → shared well-scoped operational info ("FYI for everyone": WELL-0007 shut-in, Q16)
          → facts (scope well | well_type | fleet; visible to ALL users — no user_id column)
      → personal preference ("I'm watching this well")
          → memories (user_id keyed — private)
```

Notes:

- Routing ladder exists because **eval corrections arrive commandless** — Q12/Q13 are
  natural speech; rank 2 must catch them or A2 fails.
- Facts store `author_user_id` so the answer can say "per Jake Morales" (Q16).
- Claims promote on explicit confirmation (any user; promoting user recorded) → becomes
  a fact or correction as appropriate. Unconfirmed claims are surfaced as disagreements,
  never as truth (honesty pillar).
- Privacy is enforced structurally: private tables (`sessions`, `messages`, `memories`)
  carry `user_id`; shared tables (`facts`, `corrections`, `rules`) don't. "The three wells
  we discussed yesterday" = `SELECT referenced_wells FROM messages JOIN sessions
  USING(session_id) WHERE user_id = ?` → Jessica gets an empty set; she must hear
  "no earlier conversation with *you*" (Q16).
- **Messages ALWAYS log** with `referenced_wells_json` — this is the cheapest possible
  implementation of conversational recall and costs one JSON column.

## 8. Reports: regex extractor with status flag

At ingest, run a regex/section parser over `maintenance-reports/*.md` and extract a small
fixed set of facts (extraction is safe because the format is guaranteed identical in the
test dataset):

```
report_facts(maintenance_id PK/FK, inspection_id,
             contained_hours_after_discovery,   -- Q10 (SR-02 breach detection)
             rca_action_required,               -- Q9 ("Action required")
             spill_class,                       -- Q13 ("moderate" class no longer holds)
             root_cause,                        -- pattern analysis
             extraction_status 'full'|'fts_only')
```

- `extraction_status='fts_only'` (regex missed) → the agent falls back to reading the file
  with `get_doc` on demand. This fallback rejection is fine; schema/extractor stays stable.
- Validation at ingest: % of reports extracted per field; if a field drops below e.g. 95%
  coverage, tighten the regex later against the actual prose.

## 9. Derived views (the accuracy layer — all math lives here)

Views **join** `rules` + `corrections` — the agent never does arithmetic or date logic itself:

| View | Purpose | Example question |
|---|---|---|
| `v_producing_now` | per well: latest effective inspection + delta vs `rules.production_threshold` → Q1/Q2/Q15 status | |
| `v_downtime(days)` | weekly non-producing findings × 7d, filterable by date window (missed inspection = 0) | Q5/Q6 |
| `v_spills` | effective spills (correction-removed detections excluded — Q4: 7 detections → 6 spills, 15.1 bbl) | Q4/Q7/Q8 |
| `v_repairs_corrective` | corrective counts per well/type/window | Q14 RCA rule |
| `v_sobligations` | spill → SR/RC deadlines from `rules` → breach/open | Q9/Q13 |
| `v_conflicts` | inspection vs. non-correction notes vs. runtime claims | Q17/Q18 |
| `v_inspection_effective` | the base pattern: COALESCE (all corrections over raw) | |
| `v_repairs_costs` | maintenance cost SUM per well/year (Q11: recall wells → costs) | Q11/Q16 |

Conventions baked into every view:

- **Open-work predicate** (defined once, reused everywhere): a maintenance job is open ⇔
  `started_at <= today AND (completed_at IS NULL OR completed_at >= today)`. Critical
  because `completed_at` can be a *planned* future end for repairs still in progress
  (Q2: WELL-0170/0172 "still open").
- **Correction precedence**: latest valid correction wins (see §6).

Design rule: **a new computation = a new view.** If the agent starts computing
(counts, sums, deltas) in its narration during eval, we push that down into SQL.

## 10. Ingest order + indexes + ingest-time validation

Order: teams/areas (`areas.json`) → users (`users.json`) → wells+equipment (`metadata.json`
per well dir) → inspections → maintenance → report extraction (`report_facts`, on disk) →
regulatory_events → context_notes (+ ingested `correction` mirroring into `corrections`) →
documents catalog (manuals + SOPs) → rules seeded from parsing manuals/SOPs → create views.

Indexes: `inspections(asset_id, inspected_at)`, `inspections(inspected_at)`,
`maintenance(asset_id, started_at)`, `maintenance(maintenance_type, equipment_kind, started_at)`
(RCA window), `regulatory_events(related_inspection_id)`, `context_notes(asset_id)`,
`corrections(inspection_id)`, `corrections(asset_id)`, `corrections(well_type)`.

Ingest-time smoke tests (fail fast after ingest, before any eval):

- Q4 on WELL-0001: 6 spills / 15.1 bbl total (correction to INS-0001-0070 excluded).
- Q5: WELL-0001 2025 downtime = 21 days (3 non-producing × 7).
- `rules` sanity: threshold for T200 is 15, T350 is 20.
- `report_facts` extraction coverage per field.
- Q10: WELL-0082 containment extracted as ~7.1 h (report regex works).

## 11. Explicitly deferred (decided out-of-scope for now)

- `/correct` UI affordance + claim-confirmation UX (rank-1 ladder impl).
- Adding back an FTS index IF eval demonstrates a keyword gap.
- Separate `assets` rename IF the test set introduces new `asset_category`.
