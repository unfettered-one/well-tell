# Benchmark Suite — Asset Intelligence Copilot (v1)

Fresh benchmark questions for testing the well-tell copilot, with verified gold ("expected") answers computed directly from the raw sample dataset (`dataset/flytbase-ahc-swe-asset-intelligence-dataset/sample-data/`).

**Validation:** the pipeline that produced these answers reproduced the organizers' official expected answers exactly — Q2 (NE-08 non-producing: WELL-0164/0170/0172/0175) and Q8 (2026 spills heatmap: SW-23 35, SW-24 43, NE-07 37, NE-08 26).

**Conventions** (same as the challenge): "Today" = 17 Oct 2026; "right now" = each well's latest inspection; periods such as "last 90 days" end today and are compared by date; a repair belongs to a period by its start date; threshold rules live in the well-type manuals (T200: producing when wellhead ≥ **15 °C** above ambient; T350: ≥ **20 °C**); each non-producing weekly inspection counts as **7 days** of downtime; missed inspections add none; a formal correction note (`note_type: correction`) overrides the inspection's spill detection.

Visuals: answer names the expected visual per the challenge's selection guide (card / table / line chart / bar chart / map / heatmap).

---

## Part A1 — Grounded data questions

### B1. Single-well status (card)

**Q:** "Is WELL-0060 producing oil right now? When was it last inspected and by whom?"

**Gold / expected:**
- **No, not producing.** Wellhead − ambient = 4.9 °C (28.2 °C vs 23.3 °C), below the **15 °C T200** limit. Absolute temperature is a distractor (a hot idle wellhead reads warm).
- Latest inspection: **INS-0060-0207**, 15 Oct 2026 08:15 UTC, **drone**, by **Jake Morales**.
- `recorded_status` = **active** → out of date.
- No context note, no open maintenance. Drone note: *"No stroke observed during flight."* No recorded reason exists — copilot must say so and may suggest a pump jack / breaker check. Must **not invent a cause**.

**Tested:** threshold lookup per well type, out-of-date recorded status, evidence citation, no-invention.

### B2. Area sweep with reasons (table)

**Q:** "Which wells in Southwest Block 24 are not producing right now, and why? Show them in a table."

**Gold / expected (table, 3 wells, all last inspected 15 Oct 2026):**

| Well | Wellhead above air | Recorded status | Reason |
|---|---|---|---|
| WELL-0060 | 4.9 °C | active (out of date) | No recorded reason. Inspector noted "No stroke observed during flight." |
| WELL-0066 | 1.3 °C | active (out of date) | No recorded reason. No human note either — must say "no recorded reason", not invent one. |
| WELL-0079 | 4.0 °C | active (out of date) | Repair **MNT-0079-036**, prime mover failure, started **16 Oct 2026** (one day *after* the inspection), still open. Inspector noted "Wellhead cold to touch." |

**Tested:** area filter, T200 vs T350 thresholds (0066 and 0079 include T200/T350 mix), joining open maintenance, honest "unknown cause".

### B3. Spill history with corrections (table)

**Q:** "How many spills has WELL-0082 had in the last 4 years, and how much oil in total? List them in a table."

**Gold / expected:**
- **3 spills, 2.9 bbl total**:
  - 6 Jun 2024 — 2.0 bbl (INS-0082-0083)
  - 29 Jan 2026 — 0.2 bbl (INS-0082-0167)
  - 10 Sep 2026 — 0.7 bbl (INS-0082-0198)
- No correction notes exist on this well, so every detection counts. (Contrast with official Q4 / WELL-0001 where one detection was corrected away.)

**Tested:** spill counting logic, window by date, no false "corrected" removal.

### B4. Downtime in a calendar year (short answer, no visual needed)

**Q:** "How many days was WELL-0164 down in 2025?"

**Gold / expected:**
- **14 days** — from 2 non-producing weekly inspections in 2025:
  - 30 Jan 2025 (INS-0164-0117): wellhead 10.6 °C, air 5.6 °C → only **5.0 °C** warmer (< 15; a cold well — the absolute temperatures look unremarkable, the **difference** is what matters).
  - 6 Feb 2025 (INS-0164-0118): wellhead 14.1 °C, air 8.4 °C → 5.7 °C.
- Cause: **MNT-0164-014**, stuffing box packing leak, started 1 Feb 2025.
- ⚠️ Distractor trap: exactly 14 days ⇒ the RC-03 rule (>14 consecutive days reported to supervisor) is **not** triggered. A copilot that over-reports compliance breaches fails this.

**Tested:** hot-day / cold-well reasoning, downtime counting (2 × 7), maintenance join, boundary-exact rule application.

### B5. Area downtime ranking (bar chart)

**Q:** "Which 2 wells in Southwest Block 24 had the most downtime in the last 4 months? Show a bar chart."

**Window:** 16 Jun – 17 Oct 2026 (periods end today, compared by date).

**Gold / expected:**
- **WELL-0084: 42 days (T200)**
- **WELL-0069: 35 days (T200)**
- Third place is a **4-way tie at 28 days** (WELL-0071, WELL-0061, WELL-0080 — all T200 — and WELL-0093, T350) behind WELL-0084 (42) and WELL-0069 (35). The gold answer requires surfacing the tie honestly, not inventing a #3.

**Tested:** windowed downtime across a whole area, tie handling / honesty under ambiguity.

### B6. Area spill map (map)

**Q:** "Show on a map every well in Southwest Block 23 with a real spill in the last 90 days."

**Window:** 18 Jul – 17 Oct 2026.

**Gold / expected (map with 11 pins across 9 wells — two wells have 2 spills each):**

| Well | Date | Barrels | Location (lat, lon) |
|---|---|---|---|
| WELL-0001 | 1 Oct 2026 | 1.6 | 31.85425, −102.50232 |
| WELL-0017 | 13 Aug 2026 | 3.0 | 31.84718, −102.49253 |
| WELL-0022 | 1 Oct 2026 | 4.8 | 31.86334, −102.53377 |
| WELL-0030 | 23 Jul 2026 | 0.6 | 31.82700, −102.50114 |
| WELL-0039 | 23 Jul 2026 | 1.0 | 31.82745, −102.52900 |
| WELL-0039 | 30 Jul 2026 | 3.4 | 31.82745, −102.52900 |
| WELL-0041 | 20 Aug 2026 | 1.7 | 31.81561, −102.50151 |
| WELL-0042 | 17 Sep 2026 | 5.4 | 31.85833, −102.53226 |
| WELL-0042 | 24 Sep 2026 | 4.6 | 31.85833, −102.53226 |
| WELL-0044 | 20 Aug 2026 | 1.6 | 31.81950, −102.50695 |
| WELL-0045 | 24 Sep 2026 | 1.1 | 31.85808, −102.52834 |

**Tested:** map visual, per-well multi-pin handling, lat/lon fidelity.

### B7. Spill heatmap, area × month (heatmap) — regression check

**Q:** "Show a heatmap of 2026 spills by geographic area and month."

**Gold / expected (detections corrected as not-oil removed):**

| Area | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | **Total** |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Southwest Block 23 | 4 | 3 | 3 | 6 | 3 | 4 | 4 | 3 | 3 | 2 | **35** |
| Southwest Block 24 | 7 | 4 | 5 | 6 | 5 | 5 | 3 | 1 | 5 | 2 | **43** |
| Northeast Block 7 | 5 | 3 | 2 | 4 | 6 | 6 | 2 | 4 | 4 | 1 | **37** |
| Northeast Block 8 | 4 | 4 | 4 | 3 | 2 | 4 | 4 | 0 | 1 | 0 | **26** |

**Tested:** fleet-wide aggregation, correction filtering, heatmap visual. (Matches the organizers' official Q8 gold exactly.)

### B8. Compliance joins: reportable spills vs SR-01 deadline (table)

**Q:** "List every reportable spill (5 bbl or more) in 2026, whether the written notice met the 24-hour SR-01 deadline, and the outcome. Table."

**Gold / expected (12 spills; join inspections + regulatory events + SOP):**

*On time (hours_to_report < 24):*

| Well | Date | bbl | Hours to report | Outcome |
|---|---|---|---|---|
| WELL-0123 | 24 Sep 2026 | 6.0 | 4 | No violation |
| WELL-0182 | 15 Jan 2026 | 5.9 | 2 | No violation |
| WELL-0002 | 5 Feb 2026 | 5.0 | 7 | No violation |
| WELL-0135 | 14 May 2026 | 5.8 | 10 | No violation |
| WELL-0042 | 17 Sep 2026 | 5.4 | 11 | No violation |
| WELL-0168 | 11 Jun 2026 | 5.6 | 18 | No violation |
| WELL-0071 | 21 May 2026 | 5.7 | 20 | No violation |

*Late (SR-01 breach → notice of violation):*

| Well | Date | bbl | Hours to report | NOV / fine status |
|---|---|---|---|---|
| WELL-0099 | 12 Mar 2026 | 5.1 | 29 | NOV **USD 7,500, closed** (response filed 5 May; site inspection 7 May) |
| WELL-0033 | 19 Feb 2026 | 5.2 | 31 | NOV USD 5,000, **closed** |
| WELL-0001 | 11 Jun 2026 | 6.8 | 41 | NOV USD 5,000, **OPEN** |
| WELL-0013 | 11 Jun 2026 | 5.2 | 48 | NOV USD 5,000, **closed** (response filed 27 Jun) |

**Follow-up:** "Which fine is still open?" → **WELL-0001 only** (REG-0001-002, $5,000, open).

**Tested:** multi-source join, threshold from SOP (24 h), fine/status tracking, follow-up drill-down.

### B9. Containment rule hidden in report text (table)

**Q:** "In Southwest Block 23, which spills in the last 90 days were not contained within the SOP time limit?"

**Window:** 18 Jul – 17 Oct 2026. **SR-02 limit: contained within 4 hours of discovery.** Containment time exists **only inside the free-text maintenance reports** of this sample.

**Gold / expected (table, 4 spills):**

| Well | Spill date | Contained after | Report / inspection |
|---|---|---|---|
| WELL-0017 | 13 Aug 2026 | ≈ 4.9 h | MNT-0017-029 (INS-0017-0198) |
| WELL-0030 | 23 Jul 2026 | ≈ 7.3 h | MNT-0030-032 (INS-0030-0192) |
| WELL-0042 | **24** Sep 2026 | ≈ 7.5 h | MNT-0042-026 (INS-0042-0204) — note its 17 Sep spill was 3.7 h = compliant; only the 24 Sep one breached |
| WELL-0044 | 20 Aug 2026 | ≈ 7.9 h | MNT-0044-036 (INS-0044-0197) |

All other SW-23 spills in the window were contained ≤ 4 h: 0001 (1.7 h), 0022 (3.8 h), 0039 (2.4 h and 1.1 h), 0041 (1.2 h), 0042-17 Sep (3.7 h), 0045 (3.3 h).

**Tested:** reading rules from SOPs, extracting facts that exist only in free-text reports, per-inspection (not per-well) reasoning.

### B10. Maintenance escalation rule (list)

**Q:** "Which wells need a root-cause analysis on their pump jack?"

**Gold / expected:** wells with **3+ corrective pump_jack repairs in the 12 months** to 17 Oct 2026 (T200 manual §10; T350 manual §6 refers to it):

| Well | Type | Corrective pump jack repairs (dates) |
|---|---|---|
| WELL-0020 | T200 | 9 Nov 2025, 6 Mar 2026, 15 Aug 2026 (MNT-0020-027/-030/-034) |
| WELL-0108 | T350 | 6 Mar, 17 Apr, 26 Jun 2026 (MNT-0108-024/-026/-028) |
| WELL-0121 | T200 | 30 May, 4 Sep, 9 Oct 2026 (MNT-0121-031/-034/-035) |
| WELL-0138 | T350 | 19 Jul, 23 Aug, 2 Oct 2026 (MNT-0138-031/-032/-034) |
| WELL-0159 | T350 | 19 Dec 2025, 21 Mar, 22 Aug 2026 (MNT-0159-023/-025/-029) |
| WELL-0182 | T200 | 14 Nov 2025, 30 Jan, 27 Mar 2026 (MNT-0182-018/-021/-023) |

**Tested:** escalation rule from manuals, rolling 12-month window, correct-maintenance-type filtering (scheduled jobs don't count).

---

## Part A2 — Memory & feedback (run as a sequenced conversation)

### B11. Private memory of past conversations

**Script:**
- **Day 1** — Michael Turner asks **B5** (top-2 downtime in Southwest Block 24).
- **Day 2** — Michael Turner, in a **new chat**: "For the two wells we discussed yesterday, what have their repairs cost this year?"

**Gold / expected:**
- **WELL-0084: USD 19,285** (9 maintenance jobs in 2026, incl. 5 corrective).
- **WELL-0069: USD 63,677** (9 jobs in 2026; includes the USD 37,313 well service MNT-0069-035 on 26 Jun — a big-ticket distractor).
- Memory check: **Jessica Reed** asking the same thing in her own chat must be told *"no such earlier conversation with you"* — Michael's history must not leak.

**Tested:** user-private conversation memory, year-scoped cost summation.

### B12. Correcting wrong raw data (scope: one well)

**Script:** Michael Turner: "The 15 Oct reading for WELL-0164 is wrong. The handheld thermal gun used in that inspection was faulty; the field crew re-measured the wellhead at 41.0 °C."

**Gold / expected:**
- Correction recorded against **INS-0164-0205**; original value **24.0 °C** kept for reference; who (Michael Turner) and why (faulty gun) recorded.
- With 41.0 °C vs **19.9 °C** air → **21.1 °C** warmer, above the T200 limit ⇒ **WELL-0164 is producing oil**.
- Copilot must also flag the inspector's note on the same inspection ("Pump jack not moving." — Tyler Hughes) as **disagreeing** with the correction, and ask Michael to confirm.
- Then re-asking **B2** must yield **2 wells** (WELL-0066, WELL-0079) with WELL-0164 absent and the reason explained.

**Tested:** correction provenance (keep original, record who/why), re-derivation after feedback, conflict surfacing.

### B13. Correcting the AI's analysis (SOP cascade)

**Script:** Michael Turner: "The AI estimated the 17 Sep spill at WELL-0042 as 5.4 bbl. The field crew measured **7.2 bbl**."

**Gold / expected:**
- Correction recorded against **INS-0042-0203** (AI estimate kept for reference).
- At **7.2 bbl** the spill is **reportable** (5–25 bbl class). The written notice REG-0042-001 was filed **11 h** after the 17 Sep inspection ⇒ SR-01 met (within 24 h). No NOV exists.
- Containment ≈ 3.7 h ⇒ SR-02 met.
- But at reportable volume, **SR-03** applies: agency verification of remediation due within **60 days** of discovery → **due by 16 Nov 2026**. No verification/scheduled site inspection exists ⇒ flag as **open compliance duty**. (At the old 5.4 bbl estimate it was also reportable, so severity/notes in the report don't flip — the copilot may note classification stays "reportable".)

**Tested:** correction of AI output, SOP deadline cascade (SR-03 60-day clock), what changes vs what doesn't.

### B14. A rule scoped to a whole well type

**Script:**
- Michael Turner first asks **B10**.
- Michael Turner: "Note for all **T350** wells: our team now wants a pump jack root-cause analysis after **2** repairs, not 3."
- Then, in a new chat, he asks B10 again.

**Gold / expected:**
- Baseline six wells (B10) **plus** the T350 wells with exactly 2 corrective pump jack repairs in the last 12 months: **WELL-0004, WELL-0013, WELL-0021, WELL-0055, WELL-0079, WELL-0093, WELL-0120, WELL-0183, WELL-0189**.
- Must **NOT** add the 2-repair **T200** wells: WELL-0015, WELL-0023, WELL-0069, WELL-0071, WELL-0078, WELL-0084, WELL-0102, WELL-0170.
- The answer must attribute the change to **Michael Turner's rule**, not the manual (e.g., "...following your rule of 2, overriding the manual's 3").

**Tested:** user rule learning with **well-type scope**, cross-type exclusion (WELL-0102-style trap from official Q14).

---

## Part B — Several users (runtime scenarios)

### B15. Corrections reach other users (follows B12 and B13)

- **Jessica Reed**, in her own chat: "Is WELL-0164 producing oil right now?" → **Yes**, based on the corrected 41.0 °C reading (21.1 °C above air). Answer must say the 15 Oct value was corrected by Michael Turner and mention Tyler Hughes's "Pump jack not moving." note that disagrees.
- **Laura Simmons**: "Which spills in Northeast Block 8 in the last 90 days needed a report to the regulator?" → gold mirrors the official Q15 mechanism: only spills at ≥ 5 bbl *after* corrections count; reportable ones with no written notice on record must be flagged as SR-01 breaches.

### B16. Shared knowledge, private memory

- **Jake Morales**: "FYI for everyone: WELL-0007 will be shut in from 17 Oct for a 10-day planned workover."
- **Michael Turner**, new chat: "Is any downtime planned for WELL-0007?" → **Yes**, from 17 Oct for about 10 days, per Jake Morales.
- **Jessica Reed**: "For the two wells we discussed yesterday, what have repairs cost this year?" → copilot must say it has **no such earlier conversation with her**; Michael's B11 history must not be used.

### B17. People disagree with the data

- **Michael Turner**: "WELL-0079 has been shut in for planned work since 14 Oct."
- **Later, another user**: "WELL-0079 is running fine." → copilot points out INS-0079-0200 (15 Oct) shows the wellhead only **4.0 °C** above air (T350 threshold 20 °C ⇒ not producing), and open repair **MNT-0079-036** (prime mover failure from 16 Oct). Matches Michael's note, not the second claim; the claim is recorded as **unconfirmed** and confirmation requested.

### B18. People disagree about the AI's analysis

**Q (any user):** "Was the 20 Aug spill at WELL-0101 real oil?"

**Gold / expected:**
- AI flagged a **1.0 bbl** spill at inspection **INS-0101-0197** ("Oil sheen around cellar").
- Two notes disagree: **Ryan Brooks** thought it was produced water (CTX-0101-002), but **Chris Dalton** (HSE) sampled the stain and confirmed crude (CTX-0101-003).
- Neither note is a formal **correction**, and a spill repair (**MNT-0101-029**) was carried out, so the detection stands.
- Answer: **yes**, real oil — while showing the disagreement and both sources.

---

## What the suite stresses (mapped to the judging rubric)

| Capability | Questions |
|---|---|
| Threshold lookup per well type (15 / 20 °C) | B1, B2, B12, B17 |
| Correction-override logic on detections | B3 (control), B7, B12, B18 |
| Date-window math, ties, boundary rules | B4, B5, B10 |
| Rules found in manuals/SOPs, deadlines | B4, B8, B9, B10, B13 |
| Facts only in free-text reports | B9 |
| Multi-source joins + outcome drilling | B8 |
| Visual selection (card/table/bar/map/heatmap) | B1–B9 |
| Private vs shared memory | B11, B15, B16 |
| Feedback: raw data, AI analysis, type-scoped rules | B12, B13, B14 |
| Conflict honesty (never silently pick a side) | B12, B17, B18 |

## Scoring guidance

- **Facts (hard pass/fail):** IDs, dates, numbers must match the gold above (within rounding for "≈ h" values parsed from report text).
- **Evidence:** answer must cite the inspection / maintenance / regulatory / context record IDs or documents used.
- **Visual:** the named visual, or a fitting one if the question doesn't name it.
- **Honesty checks:** "no recorded reason" (B1/B2), tie disclosure (B5), not triggered (>14 days, B4), unknown-volume registration must not invent causes or pick sides silently (B12/B17/B18).
