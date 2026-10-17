#!/usr/bin/env python3
"""verify.py — hard-fail verification gate (ingest_plan.md §7).

Runs at the end of every ingest AND standalone:

    python ingest/verify.py --db data/well_copilot.db

Any failure -> non-zero exit -> the DB is not trusted.
Structural checks run for every dataset; golden checks run only when the
sample dataset is present (they are meaningless on the test dataset).
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import create  # noqa: E402


class Checker:
    def __init__(self):
        self.errors = []

    def check(self, ok, msg):
        if ok:
            print(f"  ok    {msg}")
        else:
            print(f"  FAIL  {msg}")
            self.errors.append(msg)

    def fail_if_any(self):
        if self.errors:
            print(f"\nVERIFICATION FAILED — {len(self.errors)} error(s). "
                  "The DB is not trusted.")
            sys.exit(1)
        print("\nVERIFICATION PASSED — all checks green.")


def one(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()[0]


def verify_dataset(conn, c, dataset_id):
    root = create.get_meta(conn, f"dataset_root_{dataset_id}")
    print(f"\n--- structural checks: dataset '{dataset_id}' ---")

    # ---- no silent drops: DB row counts match meta-recorded parsed counts
    # (rules: runtime overrides are NOT ingested rows — exclude them, review R1)
    for table in ("wells", "equipment", "inspections", "maintenance",
                  "report_facts", "regulatory_events", "context_notes",
                  "documents", "rules"):
        if table == "rules":
            db_n = one(conn, "SELECT COUNT(*) FROM rules WHERE dataset_id = ? "
                             "AND NOT (is_overridden = 1 AND source_doc = 'runtime')",
                       (dataset_id,))
        else:
            db_n = one(conn, f"SELECT COUNT(*) FROM {table} WHERE dataset_id = ?",
                       (dataset_id,))
        meta_n = create.get_meta(conn, f"rows_{dataset_id}_{table}")
        c.check(meta_n is not None and db_n == int(meta_n),
                f"{table}: {db_n} rows (meta says {meta_n})")

    # ---- asset_category singleton (database_plan.md §2)
    n_cat = one(conn, "SELECT COUNT(DISTINCT asset_category) FROM wells "
                      "WHERE dataset_id = ?", (dataset_id,))
    c.check(n_cat == 1, f"asset_category singleton ({n_cat} distinct)")

    # ---- FK orphans across the chain
    orphans = one(conn, """SELECT COUNT(*) FROM inspections i
        LEFT JOIN wells w ON w.asset_id=i.asset_id AND w.dataset_id=i.dataset_id
        WHERE i.dataset_id=? AND w.asset_id IS NULL""", (dataset_id,))
    c.check(orphans == 0, f"inspections -> wells orphans: {orphans}")
    orphans = one(conn, """SELECT COUNT(*) FROM maintenance m
        LEFT JOIN inspections i ON i.inspection_id=m.triggered_by_inspection_id
            AND i.dataset_id=m.dataset_id
        WHERE m.dataset_id=? AND m.maintenance_type='corrective'
          AND (m.triggered_by_inspection_id IS NULL OR i.inspection_id IS NULL)""",
                 (dataset_id,))
    c.check(orphans == 0, f"corrective maintenance with missing/orphan trigger: {orphans}")
    orphans = one(conn, """SELECT COUNT(*) FROM report_facts rf
        LEFT JOIN maintenance m ON m.maintenance_id=rf.maintenance_id
            AND m.dataset_id=rf.dataset_id
        WHERE rf.dataset_id=? AND m.maintenance_id IS NULL""", (dataset_id,))
    c.check(orphans == 0, f"report_facts -> maintenance orphans: {orphans}")
    orphans = one(conn, """SELECT COUNT(*) FROM report_facts rf
        JOIN maintenance m ON m.maintenance_id=rf.maintenance_id
            AND m.dataset_id=rf.dataset_id
        WHERE rf.dataset_id=? AND m.triggered_by_inspection_id IS NOT NULL
          AND rf.inspection_id != m.triggered_by_inspection_id""", (dataset_id,))
    c.check(orphans == 0, f"report_facts.inspection_id != maintenance trigger: {orphans}")
    orphans = one(conn, """SELECT COUNT(*) FROM regulatory_events e
        LEFT JOIN wells w ON w.asset_id=e.asset_id AND w.dataset_id=e.dataset_id
        WHERE e.dataset_id=? AND w.asset_id IS NULL""", (dataset_id,))
    c.check(orphans == 0, f"regulatory_events -> wells orphans: {orphans}")
    orphans = one(conn, """SELECT COUNT(*) FROM regulatory_events e
        LEFT JOIN inspections i ON i.inspection_id=e.related_inspection_id
            AND i.dataset_id=e.dataset_id
        WHERE e.dataset_id=? AND e.related_inspection_id IS NOT NULL
          AND i.inspection_id IS NULL""", (dataset_id,))
    c.check(orphans == 0, f"regulatory_events.related_inspection_id orphans: {orphans}")
    orphans = one(conn, """SELECT COUNT(*) FROM context_notes n
        LEFT JOIN inspections i ON i.inspection_id=n.inspection_id
            AND i.dataset_id=n.dataset_id
        WHERE n.dataset_id=? AND n.inspection_id IS NOT NULL
          AND i.inspection_id IS NULL""", (dataset_id,))
    c.check(orphans == 0, f"context_notes.inspection_id orphans: {orphans}")
    orphans = one(conn, """SELECT COUNT(*) FROM corrections c
        LEFT JOIN inspections i ON i.inspection_id=c.inspection_id
            AND i.dataset_id=c.dataset_id
        WHERE c.dataset_id=? AND c.source='ingested'
          AND (c.inspection_id IS NULL OR i.inspection_id IS NULL)""", (dataset_id,))
    c.check(orphans == 0, f"ingested corrections -> inspections orphans: {orphans}")
    orphans = one(conn, """SELECT COUNT(*) FROM equipment e
        LEFT JOIN wells w ON w.asset_id=e.asset_id AND w.dataset_id=e.dataset_id
        WHERE e.dataset_id=? AND w.asset_id IS NULL""", (dataset_id,))
    c.check(orphans == 0, f"equipment -> wells orphans: {orphans}")
    for table, col, ref, ref_col in (("wells", "area_id", "areas", "area_id"),
                                     ("wells", "team_id", "teams", "team_id"),
                                     ("wells", "in_charge_user_id", "users", "user_id")):
        orphans = one(conn, f"""SELECT COUNT(*) FROM wells w
            LEFT JOIN {ref} r ON r.{ref_col}=w.{col} AND r.dataset_id=w.dataset_id
            WHERE w.dataset_id=? AND w.{col} IS NOT NULL AND r.{ref_col} IS NULL""",
                      (dataset_id,))
        c.check(orphans == 0, f"wells.{col} -> {ref} orphans: {orphans}")

    # ---- every report_file resolves on disk
    missing = 0
    if root and os.path.isdir(root):
        rows = conn.execute("""SELECT asset_id, report_file FROM maintenance
            WHERE dataset_id=? AND report_file IS NOT NULL""",
                            (dataset_id,)).fetchall()
        for asset_id, rel in rows:
            if not (Path(root) / "assets" / asset_id / rel).exists():
                missing += 1
        c.check(missing == 0,
                f"report files on disk: {len(rows) - missing}/{len(rows)} resolve")
        c.check(one(conn, "SELECT COUNT(*) FROM maintenance WHERE dataset_id=? "
                          "AND maintenance_type='corrective' AND report_file IS NULL",
                    (dataset_id,)) == 0,
                "every corrective maintenance row has a report_file")
    else:
        c.check(False, f"dataset_root_{dataset_id} missing/invalid in meta: {root}")

    # ---- corrections format contract: zero unparsed
    unparsed = int(create.get_meta(conn, f"unparsed_corrections_{dataset_id}") or 0)
    c.check(unparsed == 0,
            f"unparsed correction notes: {unparsed} (must be 0)")

    # ---- extraction coverage thresholds (§4)
    spill_rows = int(create.get_meta(conn, f"extract_{dataset_id}_spill_rows") or 0)
    if spill_rows:
        contained = int(create.get_meta(conn, f"extract_{dataset_id}_contained") or 0)
        klass = int(create.get_meta(conn, f"extract_{dataset_id}_class") or 0)
        c.check(contained / spill_rows >= 0.99,
                f"contained_hours coverage {contained}/{spill_rows} >= 99%")
        c.check(klass / spill_rows >= 0.99,
                f"spill_class coverage {klass}/{spill_rows} >= 99%")
    total_rf = int(create.get_meta(conn, f"rows_{dataset_id}_report_facts") or 0)
    root_hits = int(create.get_meta(conn, f"extract_{dataset_id}_root") or 0)
    c.check(total_rf == 0 or root_hits / total_rf >= 0.95,
            f"root_cause coverage {root_hits}/{total_rf} >= 95%")

    # ---- all rule keys present + word/manual cross-checks (§5)
    expected_keys = [
        "production_threshold", "overtemp_alarm_c", "spill_shutin_area_pct",
        "rca_after_n_repairs", "rca_lookback_months", "downtime_report_days",
        "sr01_hours", "sr01_major_hours", "sr02_contain_hours",
        "sr03_tph_pct", "sr03_samples", "sr03_verify_days",
        "spill_minor_max_bbl", "spill_moderate_max_bbl", "spill_major_min_bbl",
        "moderate_hse_notice_hours", "rc01_inspection_days", "rc03_report_days",
        "rc04_nov_response_days", "ws03_stopwork_ppm", "ws04_lel_pct",
        "ws05_test_multiple", "ws05_hold_hours", "ws07_report_days",
        "planned_shutin_log_required", "downtime_days_per_finding",
    ]
    for key in expected_keys:
        n = one(conn, "SELECT COUNT(*) FROM rules WHERE dataset_id=? AND parameter=?",
                (dataset_id, key))
        c.check(n >= 1, f"rule present: {key}")

    # T200/T350 cross-checks: same escalation rule in both manuals
    vals = dict(conn.execute(
        """SELECT applies_to, value FROM rules
           WHERE dataset_id=? AND parameter='rca_after_n_repairs'""",
        (dataset_id,)).fetchall())
    if "T200" in vals and "T350" in vals:
        c.check(float(vals["T200"]) == float(vals["T350"]),
                f"RCA rule agrees across T200/T350 ({vals['T200']} vs {vals['T350']})")
    vals = dict(conn.execute(
        """SELECT applies_to, value FROM rules
           WHERE dataset_id=? AND parameter='downtime_report_days'""",
        (dataset_id,)).fetchall())
    rc03 = conn.execute(
        """SELECT value FROM rules WHERE dataset_id=?
           AND parameter='rc03_report_days'""", (dataset_id,)).fetchone()
    if "fleet" in vals and rc03 is not None and rc03[0] is not None:
        c.check(float(vals["fleet"]) == float(rc03[0]),
                f"downtime_report_days == rc03_report_days ({vals['fleet']} vs {rc03[0]})")

    # ---- corrections: DB count matches meta-recorded parsed count (no drops);
    # runtime corrections are never ingested rows — exclude them even if a tool
    # scoped one to this dataset (review R1/minor note)
    meta_corr = create.get_meta(conn, f"rows_{dataset_id}_corrections")
    db_corr = one(conn, "SELECT COUNT(*) FROM corrections WHERE dataset_id = ? "
                        "AND source != 'runtime'", (dataset_id,))
    c.check(meta_corr is not None and db_corr == int(meta_corr),
            f"corrections: {db_corr} rows (meta says {meta_corr})")

    # ---- as_of consistency: global = max per-dataset as_of
    ds_as_of = create.get_meta(conn, f"as_of_{dataset_id}")
    max_insp = one(conn, "SELECT MAX(inspected_at) FROM inspections "
                         "WHERE dataset_id=?", (dataset_id,))
    if max_insp and ds_as_of:
        expect = (datetime.fromisoformat(max_insp.replace("Z", "+00:00")).date()
                  + timedelta(days=1)).isoformat()
        explicit = create.get_meta(conn, f"as_of_explicit_{dataset_id}") == "1"
        c.check(explicit or ds_as_of == expect,
                f"as_of_{dataset_id} = {'explicit evaluation date' if explicit else 'max(inspected_at)+1d'} "
                f"({ds_as_of})")


def verify_sample_golden(conn, c):
    """Golden checks run against the INGESTED BASELINE: runtime corrections and
    runtime rule overrides are temporarily hidden inside a transaction that is
    rolled back afterwards (review F3). A legitimate Q12/Q13 correction on the
    live DB must never trip the gate; a broken rebuild still hard-fails."""
    print("\n--- golden checks: sample dataset, ingested baseline "
          "(values from 03-evaluation-queries.md) ---")
    g = "sample"
    conn.execute("BEGIN")
    try:
        n_corr = conn.execute(
            "DELETE FROM corrections WHERE source = 'runtime'").rowcount
        n_rules = conn.execute(
            "DELETE FROM rules WHERE is_overridden = 1 AND source_doc = 'runtime'").rowcount
        if n_corr or n_rules:
            print(f"  (baseline mode: {n_corr} runtime correction(s) and "
                  f"{n_rules} runtime rule override(s) hidden, rolled back after)")

        # Time-dependent sample goldens describe the canonical evaluation day,
        # not a user-supplied --as-of. Restore that date only for this rollback.
        create.set_meta(conn, "as_of_sample", "2026-10-16")
        _golden_checks(conn, c, g)
    finally:
        conn.execute("ROLLBACK")


def _golden_checks(conn, c, g):

    # Q4: WELL-0001 -> 6 spills / 15.1 bbl
    n, vol = conn.execute("""SELECT COUNT(*), ROUND(COALESCE(SUM(est_volume_bbl),0),1)
        FROM v_spills WHERE dataset_id=? AND asset_id='WELL-0001'""", (g,)).fetchone()
    c.check(n == 6, f"Q4 WELL-0001 spill count = 6 (got {n})")
    c.check(abs(vol - 15.1) < 0.05, f"Q4 WELL-0001 spill volume = 15.1 bbl (got {vol})")

    # Q5: WELL-0001 2025 downtime = 21 days
    d = one(conn, """SELECT COALESCE(SUM(days_per_finding),0) FROM v_downtime_findings
        WHERE dataset_id=? AND asset_id='WELL-0001'
          AND substr(found_date,1,4)='2025'""", (g,))
    c.check(d == 21, f"Q5 WELL-0001 2025 downtime = 21 days (got {d})")

    # Q6: NE-07 worst 3 in the 4-month window = 49 / 42 / 42
    rows = conn.execute("""SELECT asset_id, SUM(days_per_finding) d
        FROM v_downtime_findings
        WHERE dataset_id=? AND area_name='Northeast Block 7'
          AND found_date BETWEEN '2026-06-16' AND '2026-10-16'
        GROUP BY asset_id ORDER BY d DESC LIMIT 3""", (g,)).fetchall()
    got = [(r[0][-4:], r[1]) for r in rows]
    c.check([r[1] for r in rows] == [49, 42, 42],
            f"Q6 NE-07 top3 downtime = 49/42/42 (got {got})")
    c.check(sorted(got) == sorted([("0121", 49), ("0138", 42), ("0107", 42)]),
            f"Q6 NE-07 top3 wells = 0121/0138/0107 at 49/42/42 (got {got})")

    # Q2: 4 non-producing wells in NE-08
    n = one(conn, """SELECT COUNT(*) FROM v_producing_now
        WHERE dataset_id=? AND area_name='Northeast Block 8' AND is_producing=0""",
            (g,))
    c.check(n == 4, f"Q2 non-producing wells in NE-08 = 4 (got {n})")

    # Q10: WELL-0082 contained ~7.1 h
    n = one(conn, """SELECT COUNT(*) FROM report_facts rf
        JOIN maintenance m ON m.maintenance_id=rf.maintenance_id
            AND m.dataset_id=rf.dataset_id
        JOIN wells w ON w.asset_id=m.asset_id AND w.dataset_id=m.dataset_id
        WHERE rf.dataset_id=? AND w.asset_id='WELL-0082'
          AND rf.contained_hours_after IS NOT NULL
          AND ABS(rf.contained_hours_after - 7.1) < 0.01""", (g,))
    c.check(n >= 1, f"Q10 WELL-0082 containment 7.1 h extracted (got {n} row(s))")

    # Q18: WELL-0101 detection stands (correction absent, notes are opinions)
    n = one(conn, """SELECT COUNT(*) FROM v_spills
        WHERE dataset_id=? AND inspection_id='INS-0101-0197'""", (g,))
    c.check(n == 1, f"Q18 WELL-0101 detection stands (v_spills has INS-0101-0197: {n})")
    n = one(conn, """SELECT COUNT(*) FROM corrections
        WHERE dataset_id=? AND inspection_id='INS-0101-0197'""", (g,))
    c.check(n == 0, f"Q18 no correction row for INS-0101-0197 (got {n})")

    # rules snapshot
    for param, applies_to, expected in [
            ("production_threshold", "T200", 15), ("production_threshold", "T350", 20),
            ("sr01_hours", "fleet", 24), ("sr02_contain_hours", "fleet", 4),
            ("sr03_verify_days", "fleet", 60),
            ("spill_moderate_max_bbl", "fleet", 5),
            ("rca_after_n_repairs", "fleet", 3)]:
        # winner = overridden row if present, else base row
        row = conn.execute("""SELECT value FROM rules
            WHERE dataset_id=? AND parameter=? AND applies_to=?
            ORDER BY is_overridden DESC, rowid ASC LIMIT 1""",
            (g, param, applies_to)).fetchone()
        c.check(row is not None and float(row[0]) == float(expected),
                f"rule {param}[{applies_to}] = {expected} (got {row[0] if row else None})")


def run_all(conn, data_root=None):
    c = Checker()
    datasets = [r[0] for r in conn.execute(
        "SELECT DISTINCT dataset_id FROM wells ORDER BY dataset_id")]
    if not datasets:
        c.check(False, "no datasets ingested (wells table empty)")
        c.fail_if_any()
        return

    for ds in datasets:
        verify_dataset(conn, c, ds)

    # global as_of stored in meta
    as_of = create.get_meta(conn, "as_of")
    c.check(as_of is not None, f"global as_of stored in meta ({as_of})")
    c.check(as_of == max(create.get_meta(conn, f"as_of_{d}") or "" for d in datasets),
            "global as_of equals the latest per-dataset evaluation date")
    if data_root is not None:
        c.check(str(Path(data_root).resolve()) in
                [create.get_meta(conn, f"dataset_root_{d}") for d in datasets],
                "this ingest's data_root recorded in meta")

    if "sample" in datasets:
        verify_sample_golden(conn, c)

    c.fail_if_any()


def main():
    ap = argparse.ArgumentParser(description="Verify the Well Copilot DB.")
    ap.add_argument("--db", default="data/well_copilot.db")
    args = ap.parse_args()
    if not Path(args.db).exists():
        print(f"FAIL: DB not found: {args.db}", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(args.db)
    conn.isolation_level = None  # explicit BEGIN/ROLLBACK for baseline goldens
    run_all(conn)
    conn.close()


if __name__ == "__main__":
    main()
