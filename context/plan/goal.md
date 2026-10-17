# FlytBase AHC SWE Hackathon — Goal (Asset Intelligence Copilot)

## The Goal
- **Build an "Asset Intelligence Copilot"** — a chat assistant that answers plain-English questions about 200 oil wells, correctly, with evidence, in seconds. We're building the **agentic AI layer only** (no ML/image analysis).
- Judged on: **fact accuracy, evidence citations, and the right generative UI visual** — answers are generated, not fixed screens.

## The Domain Rules (the core logic)
- **Production is derived, not stored**: a well is producing when `wellhead_temp_c − ambient_temp_c ≥ threshold` — **15 °C for T200, 20 °C for T350** (from the manuals). Absolute wellhead temp is a trap (idle wellheads can read 50+ °C on hot days).
- **Downtime**: each weekly inspection finding "not producing" = **7 days** of downtime; missed inspection = 0 days. Ignore `maintenance.downtime_hours` for this — that's per-job stop time.
- **Spills**: ≥ 5 bbl → written report to regulator within **24 h** (SR-01) or fine. Containment limits (4 h, SR-02), 60-day cleanup verification (SR-03), etc. live in the SOPs.
- **Corrections win**: a `correction` note in `context.jsonl` (or a runtime user correction) overrides the inspection's detection. Non-correction notes that disagree are just opinions → surface the conflict, don't pick a side silently.

## The Data (sample: 200 wells, 4 areas × 50, 20 Oct 2022 → 16 Oct 2026)
- **fleet/**: `areas.json`, `users.json` (6 roles, user picker needed), 2 well-type manuals (T200.md, T350.md), 3 SOPs (spill-response, regulatory-compliance, field-work).
- **assets/WELL-XXXX/**: `metadata.json` (incl. stale `recorded_status`, refreshed monthly), `inspections.jsonl` (~40k), `maintenance.jsonl` (~5.7k, corrective ones have `report_file`), `maintenance-reports/*.md` (~1.5k free-text reports — some facts exist *only* here, e.g. containment time), `regulatory-events.jsonl`, `context.jsonl` (notes/corrections).
- **Key linkage**: inspection → repair → report → regulator events, all joined by inspection ID.
- **WELL-0001 is the reference well**; it appears in most examples.

## The 4 Pillars to Build
1. **Chat UI with generative UI** — status card (single well), table (lists), line chart (over time), bar chart (comparisons), map (locations), heatmap (2D, e.g. area × month). Honor user-named visuals; else pick the fitting one.
2. **Grounded answers with citations** — every answer cites records + documents; single-fact questions up to field-wide multi-source analysis.
3. **Two-level memory**:
   - *Shared*: corrections/facts about a well visible to all users (e.g. Jake's shutdown note for WELL-0007).
   - *Private per user*: "the three wells we discussed yesterday" = that user's history only (user picker in UI).
   - *Learning from feedback*: corrections to raw data, AI analysis, and rules (scope: one well or a whole well type only — e.g. the "RCA after 2 repairs, not 3" rule must apply to T350 only). Keep original value, record who/why, apply to everyone going forward.
4. **Honesty about conflicts** — user vs. data, user vs. user: report the disagreement, mark claims unconfirmed, never silently pick one.

## Event Mechanics
- Build on the sample dataset + 18 example questions (Q1–Q18 with expected answers — validation targets).
- **Last 2 hours**: new test dataset in the *exact same format* drops → must load it alongside, run unseen final questions, record answers.
- **Submit**: 2-page write-up (design + results), ≤5-min video, public GitHub repo (open-source license), via OrganizerHQ.
- Shortlisting is on **answer accuracy vs. expected answers**; demos for finalists.

## Traps noted in the data
- Q2/Q12: corrections can flip "not producing → producing" (WELL-0164) — and must recompute downstream answers.
- Q13: correcting a volume to ≥5 bbl cascades into new SOP obligations (SR-01 overdue, SR-02 from the report, SR-03 60-day deadline).
- Q5: hot-day false positives (51.6 °C wellhead vs 43.1 °C air = not producing).
- Q18: disagreeing non-correction notes (water vs crude) → detection stands, show both sides.
