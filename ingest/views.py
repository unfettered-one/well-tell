"""views.py — the derived views (accuracy layer).

All math lives here: every view joins `rules` + `corrections`, never hardcoded
thresholds (database_plan.md §5/§9). Recreated on every ingest.

Shared conventions, defined once (ingest_plan.md §6, review F1–F8):
  - corrections.dataset_id matching: row matches when dataset_id equals the
    inspection's dataset OR is NULL (runtime corrections apply everywhere).
  - open-work predicate: started_at <= as_of AND (completed_at IS NULL OR
    completed_at >= as_of).
  - "latest correction wins": correlated latest-row join ordered by created_at.
  - rule lookup prefers is_overridden=1 rows (Q14 runtime overrides).
  - as_of is PER DATASET (meta key `as_of_<dataset_id>`, global fallback) so the
    test set's end date can differ from the sample's without shifting answers.
  - spill reporting class is derived from the EFFECTIVE volume against the
    rules bands (corrections can make a spill reportable — Q13); the report's
    own class is kept as reported_class.
"""

# "today" comes from meta, never date('now') — wall clock != eval date.
# Per-dataset as_of (meta 'as_of_<dataset_id>'), global 'as_of' as fallback.
def as_of_for(dataset_col):
    return (f"COALESCE((SELECT value FROM meta WHERE key = 'as_of_' || {dataset_col}), "
            f"(SELECT value FROM meta WHERE key = 'as_of'))")


# Corrections applicable to a given field for row aliased `i` (inspections)
# with well type aliased `w.well_type`. Latest wins; temporal window vs as_of.
def _corr_subquery(field):
    return f"""(
        SELECT c.corrected_value FROM corrections c
        WHERE c.field = '{field}'
          AND c.status = 'applied'
          AND (c.dataset_id = i.dataset_id OR c.dataset_id IS NULL)
          AND (c.inspection_id = i.inspection_id
               OR (c.inspection_id IS NULL AND c.asset_id = i.asset_id)
               OR (c.inspection_id IS NULL AND c.asset_id IS NULL
                   AND c.well_type = w.well_type))
          AND (c.valid_from IS NULL OR c.valid_from <= {as_of_for('i.dataset_id')})
          AND (c.valid_to   IS NULL OR c.valid_to   >= {as_of_for('i.dataset_id')})
        ORDER BY c.created_at DESC, c.rowid DESC LIMIT 1
    )"""


# Winner rule row for a parameter: overridden row wins, else the base row
# (Q14 runtime override mechanism; the original row is kept, never deleted).
def _rule_join(alias, dataset_col, param, well_col):
    return f"""JOIN rules {alias} ON {alias}.dataset_id = {dataset_col}
      AND {alias}.rule_id = (
        SELECT r3.rule_id FROM rules r3
        WHERE r3.dataset_id = {dataset_col}
          AND r3.parameter = '{param}'
          AND (r3.applies_to = {well_col} OR r3.applies_to = 'fleet')
        ORDER BY r3.is_overridden DESC, r3.rowid DESC LIMIT 1)"""


R_PROD  = _rule_join("r_prod",  "w.dataset_id", "production_threshold", "w.well_type")
R_DOWN  = _rule_join("r_down",  "w.dataset_id", "production_threshold", "w.well_type")
R_DDF   = _rule_join("r_ddf",   "e.dataset_id", "downtime_days_per_finding", "'fleet'")
R_RCA   = _rule_join("r_rca",   "m.dataset_id", "rca_after_n_repairs", "w.well_type")
R_LB    = _rule_join("r_lb",    "m.dataset_id", "rca_lookback_months", "'fleet'")
R_SR01  = _rule_join("r_sr01",  "sc.dataset_id", "sr01_hours", "'fleet'")
R_SR01M = _rule_join("r_sr01m", "sc.dataset_id", "sr01_major_hours", "'fleet'")
R_SR02  = _rule_join("r_sr02",  "sc.dataset_id", "sr02_contain_hours", "'fleet'")
R_SR03  = _rule_join("r_sr03",  "sc.dataset_id", "sr03_verify_days", "'fleet'")
R_SMIN  = _rule_join("r_smin",  "s.dataset_id", "spill_minor_max_bbl", "'fleet'")
R_SMOD  = _rule_join("r_smod",  "s.dataset_id", "spill_moderate_max_bbl", "'fleet'")
R_SMAJ  = _rule_join("r_smaj",  "s.dataset_id", "spill_major_min_bbl", "'fleet'")
R_HSE   = _rule_join("r_hse",   "sc.dataset_id", "moderate_hse_notice_hours", "'fleet'")
R_RC04  = _rule_join("r_rc04",  "nov.dataset_id", "rc04_nov_response_days", "'fleet'")

# Spill class bands from the rules table (SR §3):
#   minor < spill_minor_max_bbl <= moderate < spill_moderate_max_bbl
#   <= reportable < spill_major_min_bbl <= major
EFFECTIVE_CLASS_SQL = """CASE
      WHEN s.est_volume_bbl IS NULL THEN NULL
      WHEN s.est_volume_bbl >= CAST(r_smaj.value AS REAL) THEN 'major'
      WHEN s.est_volume_bbl >= CAST(r_smod.value AS REAL) THEN 'reportable'
      WHEN s.est_volume_bbl >= CAST(r_smin.value AS REAL) THEN 'moderate'
      ELSE 'minor'
  END"""


VIEWS = {

# 1. Base pattern: raw inspections COALESCE'd with latest-applicable corrections.
"v_inspection_effective": f"""
CREATE VIEW v_inspection_effective AS
SELECT
    i.dataset_id,
    i.inspection_id,
    i.asset_id,
    w.well_type,
    w.name            AS well_name,
    w.area_id,
    i.inspected_at,
    i.inspector_user_id,
    i.method,
    i.ambient_temp_c,
    CAST(COALESCE(
        {_corr_subquery('wellhead_temp_c')},
        CAST(i.wellhead_temp_c AS TEXT)
    ) AS REAL)                                      AS eff_wellhead_temp_c,
    CAST(COALESCE(
        {_corr_subquery('spill_detected')},
        CAST(i.spill_detected AS TEXT)
    ) AS INTEGER)                                   AS eff_spill_detected,
    CAST(COALESCE(
        {_corr_subquery('spill_est_volume_bbl')},
        CAST(i.spill_est_volume_bbl AS TEXT)
    ) AS REAL)                                      AS eff_spill_volume_bbl,
    CAST(COALESCE(
        {_corr_subquery('temp_delta_c')},
        CAST(CAST(COALESCE(
            {_corr_subquery('wellhead_temp_c')},
            CAST(i.wellhead_temp_c AS TEXT)
        ) AS REAL) - i.ambient_temp_c AS TEXT),
        CAST(i.temp_delta_c AS TEXT)
    ) AS REAL)                                      AS eff_temp_delta_c,
    i.spill_area_pct,
    i.evidence_images_json,
    i.notes
FROM inspections i
JOIN wells w ON w.asset_id = i.asset_id AND w.dataset_id = i.dataset_id
""",

# 2. Per well: latest effective inspection vs per-well-type production rule.
"v_producing_now": f"""
CREATE VIEW v_producing_now AS
SELECT
    w.dataset_id,
    w.asset_id,
    w.name            AS well_name,
    w.well_type,
    w.area_id,
    a.name            AS area_name,
    w.recorded_status,
    i.inspection_id   AS latest_inspection_id,
    i.inspected_at    AS latest_inspection_at,
    i.inspector_user_id AS last_inspector_user_id,
    i.method          AS last_method,
    i.ambient_temp_c,
    e.eff_wellhead_temp_c,
    e.eff_temp_delta_c,
    e.notes           AS latest_inspector_notes,
    CAST(r_prod.value AS REAL) AS production_threshold_c,
    (e.eff_temp_delta_c >= CAST(r_prod.value AS REAL)) AS is_producing,
    (SELECT n.note_id || ': ' || n.text
       FROM context_notes n
      WHERE n.asset_id = w.asset_id AND n.dataset_id = w.dataset_id
        AND n.note_type != 'correction'
        AND (n.valid_from IS NULL OR n.valid_from <= {as_of_for('w.dataset_id')})
        AND (n.valid_to   IS NULL OR n.valid_to   >= {as_of_for('w.dataset_id')})
      ORDER BY n.created_at DESC LIMIT 1) AS context_reason,
    (SELECT m.maintenance_id || ': ' || m.issue
            || ' (started ' || substr(m.started_at, 1, 10) || ', still open)'
       FROM maintenance m
      WHERE m.asset_id = w.asset_id AND m.dataset_id = w.dataset_id
        AND date(m.started_at) <= {as_of_for('w.dataset_id')}
        AND (m.completed_at IS NULL OR date(m.completed_at) >= {as_of_for('w.dataset_id')})
      ORDER BY m.started_at DESC LIMIT 1) AS open_repair_reason
FROM wells w
JOIN areas a ON a.area_id = w.area_id AND a.dataset_id = w.dataset_id
JOIN inspections i ON i.asset_id = w.asset_id AND i.dataset_id = w.dataset_id
 AND i.inspected_at = (SELECT MAX(i2.inspected_at) FROM inspections i2
                        WHERE i2.asset_id = w.asset_id AND i2.dataset_id = w.dataset_id)
JOIN v_inspection_effective e ON e.inspection_id = i.inspection_id
                             AND e.dataset_id = i.dataset_id
{R_PROD}
""",

# 3a. Downtime findings, one row per non-producing inspection (7 d each,
#     from the Dataset-Guide rule). Filterable window: found_date.
"v_downtime_findings": f"""
CREATE VIEW v_downtime_findings AS
SELECT
    e.dataset_id,
    e.inspection_id,
    e.asset_id,
    w.well_type,
    w.area_id,
    a.name            AS area_name,
    w.name            AS well_name,
    date(e.inspected_at) AS found_date,
    CAST(r_ddf.value AS REAL) AS days_per_finding
FROM v_inspection_effective e
JOIN wells w ON w.asset_id = e.asset_id AND w.dataset_id = e.dataset_id
JOIN areas a ON a.area_id = w.area_id AND a.dataset_id = w.dataset_id
{R_DOWN}
{R_DDF}
WHERE e.eff_temp_delta_c < CAST(r_down.value AS REAL)
""",

# 3b. Weekly rollup (missed week = 0 falls out of the per-finding counting).
"v_downtime": """
CREATE VIEW v_downtime AS
SELECT dataset_id, asset_id, well_type, area_id, area_name, well_name,
       week_start_date,
       COUNT(*)          AS nonproducing_findings,
       SUM(days_per_finding) AS downtime_days,
       MIN(found_date)   AS first_found_date,
       MAX(found_date)   AS last_found_date
FROM (
    SELECT *, date(found_date, 'weekday 0', '-6 days') AS week_start_date
    FROM v_downtime_findings
)
GROUP BY dataset_id, asset_id, week_start_date
""",

# 4. Effective spills: detection stands AND no correction removed it.
"v_spills": f"""
CREATE VIEW v_spills AS
SELECT
    e.dataset_id,
    e.inspection_id,
    e.asset_id,
    w.well_type,
    w.area_id,
    a.name            AS area_name,
    w.name            AS well_name,
    w.lat,
    w.lon,
    date(e.inspected_at) AS spill_date,
    e.inspected_at    AS discovered_at,
    e.eff_spill_volume_bbl AS est_volume_bbl,
    e.spill_area_pct,
    e.inspector_user_id,
    e.method
FROM v_inspection_effective e
JOIN wells w ON w.asset_id = e.asset_id AND w.dataset_id = e.dataset_id
JOIN areas a ON a.area_id = w.area_id AND a.dataset_id = w.dataset_id
WHERE e.eff_spill_detected = 1
""",

# 4b. Spills with reporting class. effective_class is derived from the
#     EFFECTIVE volume vs the rules bands (Q13: a corrected volume can make a
#     spill reportable); reported_class is what the maintenance report said.
"v_spill_classified": f"""
CREATE VIEW v_spill_classified AS
SELECT
    s.*,
    rf.spill_class   AS reported_class,
    rf.contained_hours_after,
    {EFFECTIVE_CLASS_SQL} AS effective_class,
    (rf.spill_class IS NOT NULL
     AND {EFFECTIVE_CLASS_SQL} != rf.spill_class) AS class_changed
FROM v_spills s
LEFT JOIN maintenance m ON m.dataset_id = s.dataset_id
      AND m.triggered_by_inspection_id = s.inspection_id
LEFT JOIN report_facts rf ON rf.dataset_id = m.dataset_id
      AND rf.maintenance_id = m.maintenance_id
{R_SMIN}
{R_SMOD}
{R_SMAJ}
""",

# 5. Corrective repairs + per-repair context. prior_corrective_count is the
#     number of corrective events on the same equipment kind in the lookback
#     window BEFORE this repair started (historical fact per repair).
#     For "which wells/equipment need RCA now" use v_rca_due (F2).
"v_repairs_corrective": f"""
CREATE VIEW v_repairs_corrective AS
SELECT
    m.dataset_id,
    m.maintenance_id,
    m.asset_id,
    w.well_type,
    w.area_id,
    w.name            AS well_name,
    m.equipment_kind,
    m.started_at,
    m.completed_at,
    m.issue,
    m.action_taken,
    m.report_file,
    CAST(r_rca.value AS INTEGER) AS rca_after_n_repairs,
    CAST(r_lb.value  AS INTEGER) AS rca_lookback_months,
    (SELECT COUNT(*)
       FROM maintenance m2
      WHERE m2.dataset_id = m.dataset_id
        AND m2.asset_id = m.asset_id
        AND m2.maintenance_type = 'corrective'
        AND m2.equipment_kind = m.equipment_kind
        AND m2.started_at < m.started_at
        AND m2.started_at >= date(m.started_at,
                '-' || CAST(r_lb.value AS INTEGER) || ' months')
    ) AS prior_corrective_count
FROM maintenance m
JOIN wells w ON w.asset_id = m.asset_id AND w.dataset_id = m.dataset_id
{R_RCA}
{R_LB}
WHERE m.maintenance_type = 'corrective'
""",

# 5b. RCA due NOW (manual: "3+ corrective events on the same equipment kind in
#     the 12 months before the CURRENT DATE" — window ends at as_of, F2).
"v_rca_due": f"""
CREATE VIEW v_rca_due AS
SELECT
    m.dataset_id,
    m.asset_id,
    w.name            AS well_name,
    w.well_type,
    w.area_id,
    a.name            AS area_name,
    m.equipment_kind,
    COUNT(*)                    AS corrective_count_window,
    MIN(date(m.started_at))     AS window_first_repair_date,
    MAX(date(m.started_at))     AS most_recent_repair_date,
    CAST(r_rca.value AS INTEGER) AS rca_after_n_repairs,
    CAST(r_lb.value  AS INTEGER) AS rca_lookback_months,
    (COUNT(*) >= CAST(r_rca.value AS INTEGER)) AS rca_due
FROM maintenance m
JOIN wells w ON w.asset_id = m.asset_id AND w.dataset_id = m.dataset_id
JOIN areas a ON a.area_id = w.area_id AND a.dataset_id = w.dataset_id
{R_RCA}
{R_LB}
WHERE m.maintenance_type = 'corrective'
  AND date(m.started_at) <= {as_of_for('m.dataset_id')}
  AND date(m.started_at) >= date({as_of_for('m.dataset_id')},
          '-' || CAST(r_lb.value AS INTEGER) || ' months')
GROUP BY m.dataset_id, m.asset_id, m.equipment_kind
""",

# 6. Spill + regulatory obligations: deadlines from `rules`, status vs as_of.
#     SR-01/SR-02/SR-03 derive from the EFFECTIVE spill class (F1); RC-04 NoV
#     response rows are included (F4). Status values:
#       met | breached | open (not yet due) | overdue (past due, not done)
#       | not_required (SR-01 on minor/moderate spills)
"v_sobligations": f"""
CREATE VIEW v_sobligations AS
-- SR-01: written notice to the State Oil & Gas Commission (reportable/major only)
SELECT
    'SR-01'           AS obligation_protocol,
    sc.dataset_id,
    sc.asset_id,
    sc.well_name,
    sc.well_type,
    sc.area_name,
    sc.inspection_id,
    (SELECT re.event_id FROM regulatory_events re
      WHERE re.dataset_id = sc.dataset_id
        AND re.related_inspection_id = sc.inspection_id
        AND re.protocol_id = 'SR-01'
        AND re.event_type = 'spill_report_filed' LIMIT 1) AS event_id,
    sc.discovered_at  AS source_at,
    (CASE WHEN sc.effective_class IN ('reportable', 'major')
          THEN datetime(sc.discovered_at, '+' || (CASE WHEN sc.effective_class = 'major'
                    THEN CAST(r_sr01m.value AS REAL) ELSE CAST(r_sr01.value AS REAL) END)
                    || ' hours')
          ELSE NULL END) AS deadline_at,
    (CASE WHEN sc.effective_class IN ('reportable', 'major')
          THEN (CASE WHEN sc.effective_class = 'major' THEN CAST(r_sr01m.value AS REAL)
                     ELSE CAST(r_sr01.value AS REAL) END)
          ELSE NULL END) AS limit_value,
    'hours'           AS unit,
    (SELECT MIN(re.hours_to_report) FROM regulatory_events re
      WHERE re.dataset_id = sc.dataset_id
        AND re.related_inspection_id = sc.inspection_id
        AND re.protocol_id = 'SR-01'
        AND re.event_type = 'spill_report_filed') AS actual_value,
    (CASE
       WHEN sc.effective_class NOT IN ('reportable', 'major') THEN 'not_required'
       WHEN NOT EXISTS (SELECT 1 FROM regulatory_events re
                         WHERE re.dataset_id = sc.dataset_id
                           AND re.related_inspection_id = sc.inspection_id
                           AND re.protocol_id = 'SR-01'
                           AND re.event_type = 'spill_report_filed')
          THEN (CASE WHEN datetime({as_of_for('sc.dataset_id')}) > datetime(sc.discovered_at,
                       '+' || (CASE WHEN sc.effective_class = 'major'
                                THEN CAST(r_sr01m.value AS REAL)
                                ELSE CAST(r_sr01.value AS REAL) END) || ' hours')
                     THEN 'overdue' ELSE 'open' END)
       WHEN (SELECT MIN(re.hours_to_report) FROM regulatory_events re
              WHERE re.dataset_id = sc.dataset_id
                AND re.related_inspection_id = sc.inspection_id
                AND re.protocol_id = 'SR-01'
                AND re.event_type = 'spill_report_filed')
             > (CASE WHEN sc.effective_class = 'major'
                     THEN CAST(r_sr01m.value AS REAL)
                     ELSE CAST(r_sr01.value AS REAL) END)
         THEN 'breached'
       ELSE 'met'
     END) AS status,
    'effective class ' || COALESCE(sc.effective_class, '?')
        || CASE WHEN sc.class_changed THEN ' (report said '
             || sc.reported_class || ' — no longer holds)' ELSE '' END AS detail
FROM v_spill_classified sc
{R_SR01}
{R_SR01M}
UNION ALL
-- SR-02: contain within 4 hours of discovery (every spill)
SELECT
    'SR-02',
    sc.dataset_id, sc.asset_id, sc.well_name, sc.well_type, sc.area_name,
    sc.inspection_id,
    NULL,
    sc.discovered_at,
    datetime(sc.discovered_at, '+' || CAST(r_sr02.value AS REAL) || ' hours'),
    CAST(r_sr02.value AS REAL),
    'hours',
    sc.contained_hours_after,
    (CASE
       WHEN sc.contained_hours_after IS NULL
          THEN (CASE WHEN datetime({as_of_for('sc.dataset_id')}) > datetime(sc.discovered_at,
                       '+' || CAST(r_sr02.value AS REAL) || ' hours')
                     THEN 'overdue' ELSE 'open' END)
       WHEN sc.contained_hours_after > CAST(r_sr02.value AS REAL) THEN 'breached'
       ELSE 'met'
     END),
    'contain within ' || CAST(r_sr02.value AS REAL) || ' hours of discovery'
FROM v_spill_classified sc
{R_SR02}
UNION ALL
-- SR-03: agency verifies remediation within 60 days (reportable/major only)
SELECT
    'SR-03',
    sc.dataset_id, sc.asset_id, sc.well_name, sc.well_type, sc.area_name,
    sc.inspection_id,
    (SELECT re.event_id FROM regulatory_events re
      WHERE re.dataset_id = sc.dataset_id
        AND re.related_inspection_id = sc.inspection_id
        AND re.protocol_id = 'SR-03' LIMIT 1),
    sc.discovered_at,
    (CASE WHEN sc.effective_class IN ('reportable', 'major')
          THEN date(sc.discovered_at, '+' || CAST(r_sr03.value AS REAL) || ' days')
          ELSE NULL END),
    (CASE WHEN sc.effective_class IN ('reportable', 'major')
          THEN CAST(r_sr03.value AS REAL) ELSE NULL END),
    'days',
    NULL,
    (CASE
       WHEN sc.effective_class NOT IN ('reportable', 'major') THEN 'not_required'
       WHEN EXISTS (SELECT 1 FROM regulatory_events re
                     WHERE re.dataset_id = sc.dataset_id
                       AND re.related_inspection_id = sc.inspection_id
                       AND re.protocol_id = 'SR-03'
                       AND re.event_type = 'site_inspection'
                       AND re.status = 'closed') THEN 'met'
       WHEN {as_of_for('sc.dataset_id')} > date(sc.discovered_at,
               '+' || CAST(r_sr03.value AS REAL) || ' days') THEN 'overdue'
       ELSE 'open'
     END),
    'agency remediation verification within '
        || CAST(r_sr03.value AS REAL) || ' days'
FROM v_spill_classified sc
{R_SR03}
UNION ALL
-- RC-04: answer notices of violation within 30 days, track until closed
SELECT
    'RC-04',
    nov.dataset_id,
    nov.asset_id,
    w.name,
    w.well_type,
    a.name,
    nov.related_inspection_id,
    nov.event_id,
    nov.date,
    date(nov.date, '+' || CAST(r_rc04.value AS REAL) || ' days'),
    CAST(r_rc04.value AS REAL),
    'days',
    (SELECT MIN(resp.date) FROM regulatory_events resp
      WHERE resp.dataset_id = nov.dataset_id
        AND resp.related_inspection_id = nov.related_inspection_id
        AND resp.event_type = 'nov_response_filed'),    (CASE
       WHEN EXISTS (SELECT 1 FROM regulatory_events resp
                     WHERE resp.dataset_id = nov.dataset_id
                       AND resp.related_inspection_id = nov.related_inspection_id
                       AND resp.event_type = 'nov_response_filed'
                       AND date(resp.date) <= date(nov.date,
                             '+' || CAST(r_rc04.value AS REAL) || ' days'))
         THEN 'met'
       WHEN EXISTS (SELECT 1 FROM regulatory_events resp
                     WHERE resp.dataset_id = nov.dataset_id
                       AND resp.related_inspection_id = nov.related_inspection_id
                       AND resp.event_type = 'nov_response_filed') THEN 'late'
       WHEN {as_of_for('nov.dataset_id')} > date(nov.date,
               '+' || CAST(r_rc04.value AS REAL) || ' days') THEN 'overdue'
       ELSE 'open'
     END),
    nov.detail
FROM regulatory_events nov
JOIN wells w ON w.asset_id = nov.asset_id AND w.dataset_id = nov.dataset_id
JOIN areas a ON a.area_id = w.area_id AND a.dataset_id = w.dataset_id
{R_RC04}
WHERE nov.event_type = 'notice_of_violation'
""",

# 7. Conflicts: inspection vs non-correction notes vs runtime claims.
#    Notes that *mention* an inspection (but are not corrections) pair with the
#    latest inspection in the 14 days before the note — Q17/Q18 pairs.
#    Corrections never appear here (opinions != corrections, Q18).
"v_conflicts": f"""
CREATE VIEW v_conflicts AS
SELECT
    'note_vs_inspection' AS conflict_type,
    n.dataset_id,
    n.asset_id,
    w.well_type,
    n.note_id     AS source_a_id,
    n.note_type   AS source_a_type,
    n.text        AS source_a_text,
    n.author_user_id AS source_a_author,
    n.created_at  AS source_a_at,
    i.inspection_id AS inspection_id,
    i.spill_detected AS raw_spill_detected,
    i.spill_est_volume_bbl AS raw_spill_volume_bbl,
    (SELECT c.correction_id FROM corrections c
      WHERE (c.dataset_id = n.dataset_id OR c.dataset_id IS NULL)
         AND c.inspection_id = i.inspection_id
         AND c.status = 'applied'
      ORDER BY c.created_at DESC, c.rowid DESC LIMIT 1) AS superseding_correction_id
FROM context_notes n
JOIN wells w ON w.asset_id = n.asset_id AND w.dataset_id = n.dataset_id
JOIN inspections i ON i.asset_id = n.asset_id AND i.dataset_id = n.dataset_id
 AND i.inspected_at <= n.created_at
 AND i.inspected_at >= datetime(n.created_at, '-14 days')
 AND i.inspected_at = (SELECT MAX(i2.inspected_at) FROM inspections i2
                        WHERE i2.asset_id = n.asset_id
                          AND i2.dataset_id = n.dataset_id
                          AND i2.inspected_at <= n.created_at
                          AND i2.inspected_at >= datetime(n.created_at, '-14 days'))
WHERE n.note_type != 'correction'
  AND n.text LIKE '%INS-%'
UNION ALL
SELECT
    'claim_vs_inspection' AS conflict_type,
    w.dataset_id,
    cl.asset_id,
    w.well_type,
    cl.claim_id   AS source_a_id,
    'claim'       AS source_a_type,
    cl.text       AS source_a_text,
    cl.user_id    AS source_a_author,
    cl.created_at AS source_a_at,
    i.inspection_id,
    i.spill_detected,
    i.spill_est_volume_bbl,
    NULL AS superseding_correction_id
FROM claims cl
JOIN wells w ON w.asset_id = cl.asset_id
JOIN inspections i ON i.asset_id = cl.asset_id
 AND i.dataset_id = w.dataset_id
 AND i.inspected_at <= cl.created_at
 AND i.inspected_at = (SELECT MAX(i2.inspected_at) FROM inspections i2
                         WHERE i2.asset_id = cl.asset_id
                           AND i2.dataset_id = i.dataset_id
                          AND i2.inspected_at <= cl.created_at)
""",

# 8. Maintenance cost sums per well/year (Q11).
"v_repairs_costs": """
CREATE VIEW v_repairs_costs AS
SELECT dataset_id, asset_id,
       substr(started_at, 1, 4) AS year,
       COUNT(*)      AS jobs,
       SUM(cost_labor) AS labor_usd,
       SUM(cost_parts) AS parts_usd,
       SUM(cost_total) AS total_usd
FROM maintenance
GROUP BY dataset_id, asset_id, year
""",
}


def apply_views(conn):
    """Drop + recreate all views. Called after data load (views.py runs last)."""
    for name, sql in VIEWS.items():
        conn.execute(f"DROP VIEW IF EXISTS {name}")
        conn.execute(sql)
    conn.commit()
