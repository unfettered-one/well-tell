#!/usr/bin/env python3
"""ingest.py — build the Well Copilot SQLite DB from a dataset folder.

One command builds the working DB:

    python ingest/ingest.py \
        --data dataset/flytbase-ahc-swe-asset-intelligence-dataset/sample-data \
        --dataset sample --db data/well_copilot.db

Default mode = replace per dataset: rows for this dataset_id are deleted and
re-inserted inside one transaction (idempotent; runtime tables untouched).
--fresh deletes the DB file first (full rebuild).

stdlib only: json, sqlite3, re, argparse, pathlib, datetime.
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import create  # noqa: E402
import views as views_mod  # noqa: E402
import verify as verify_mod  # noqa: E402

# --------------------------------------------------------------------------- helpers


def fail(msg):
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def one_count(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()[0]


def sniff_dataset_id(data_root: Path) -> str:
    name = data_root.name.lower()
    if "sample" in name:
        return "sample"
    if "test" in name:
        return "test"
    fail(f"cannot sniff dataset_id from folder name '{data_root.name}'; "
         "pass --dataset sample|test")


def read_jsonl(path: Path):
    rows = []
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                fail(f"{path}:{lineno}: bad JSON — {exc}")
    return rows


def read_json(path: Path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------- corrections mirror

# All 56/56 sample corrections match this one pattern (4 reasons: rainwater /
# wet soil, produced water, pump-jack shadow) — ingest_plan.md §3.
CORRECTION_RE = re.compile(r"^Inspection (INS-\S+): (.+?)\. (Not a (?:crude )?spill\.?)$")


def mirror_corrections(dataset_id, notes, count_bucket):
    """note_type='correction' rows -> corrections(source='ingested').
    Non-correction notes never enter corrections. Anything not matching the
    format contract is dropped and counted (verify hard-fails)."""
    out, unparsed = [], 0
    for n in notes:
        if n.get("note_type") != "correction":
            continue
        m = CORRECTION_RE.match(n.get("text", ""))
        if not m:
            unparsed += 1
            count_bucket["unparsed"] += 1
            continue
        insp_id, reason, tail = m.group(1), m.group(2), m.group(3)
        out.append((
            dataset_id,
            "COR-" + n["note_id"],          # correction_id
            "ingested",                      # source
            n.get("asset_id"),
            insp_id,
            None,                            # well_type (inspection-scoped)
            "spill_detected",                # field
            "1",                             # original_value (JSON bool as text)
            "0",                             # corrected_value
            f"{reason}. {tail}",             # reason = full note text after 'Inspection X:'
            n.get("author_user_id"),
            n.get("created_at"),
            n.get("valid_from"),
            n.get("valid_to"),
            "applied",                       # status
        ))
    return out


# ----------------------------------------------------------------- report extraction

CONTAINED_RE = re.compile(r"contained about ([0-9.]+) hours", re.I)
CLASS_RE = re.compile(r"\b(minor|moderate|reportable|major) class\b", re.I)
ACTION_RE = re.compile(r"action required", re.I)
ROOT_RE = re.compile(r"##\s*Root cause\s*\n(.*?)(?=\n##\s|\Z)", re.S)


def extract_report(text):
    """One report -> one report_facts row (ingest_plan.md §4).
    Returns (facts_dict, is_spill_relevant)."""
    norm = " ".join(text.split())  # whitespace-normalize (line breaks split sentences)
    contained = CONTAINED_RE.search(norm)
    klass = CLASS_RE.search(norm)
    action = ACTION_RE.search(norm)
    root = ROOT_RE.search(text)
    root_cause = " ".join(root.group(1).split()) if root else None

    spill_relevant = "sr-02" in norm.lower()
    expected = ["root_cause"] + (["contained_hours_after", "spill_class"] if spill_relevant else [])
    got = {
        "contained_hours_after": float(contained.group(1)) if contained else None,
        "spill_class": klass.group(1).lower() if klass else None,
        "root_cause": root_cause,
        "rca_action_required": 1 if action else 0,
    }
    status = "full" if all(got[k] is not None for k in expected) else "fts_only"
    return got, status, spill_relevant


# --------------------------------------------------------------------- rules seeding

def norm_doc(text):
    """Whitespace-normalize + strip bold markers (proven necessary: 28/28 hit)."""
    return " ".join(text.replace("*", "").split()).lower()


WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
                "twelve": 12}


def to_number(token):
    token = token.strip().lower()
    if token in WORD_NUMBERS:
        return WORD_NUMBERS[token]
    return float(token) if ("." in token) else int(token)


# Each spec: parameter, file (relative to data root), protocol, unit, applies_to,
# regex over the normalized lowercased doc, optional secondary regex, cross-check.
RULE_SPECS = [
    # --- well-type manuals ---
    dict(parameter="production_threshold", file="fleet/well-types/T200.md",
         protocol="T200", unit="celsius", applies_to="T200",
         pattern=r"at least (\d+) ?°c above ambient"),
    dict(parameter="production_threshold", file="fleet/well-types/T350.md",
         protocol="T350", unit="celsius", applies_to="T350",
         pattern=r"at least (\d+) ?°c above ambient"),
    dict(parameter="overtemp_alarm_c", file="fleet/well-types/T200.md",
         protocol="T200", unit="celsius", applies_to="T200",
         pattern=r"at or below (\d+) ?°c"),
    dict(parameter="overtemp_alarm_c", file="fleet/well-types/T350.md",
         protocol="T350", unit="celsius", applies_to="T350",
         pattern=r"at or below (\d+) ?°c"),
    dict(parameter="spill_shutin_area_pct", file="fleet/well-types/T200.md",
         protocol="T200", unit="percent", applies_to="T200",
         pattern=r"more than (\d+) ?% of the pad area"),
    dict(parameter="spill_shutin_area_pct", file="fleet/well-types/T350.md",
         protocol="T350", unit="percent", applies_to="T350",
         pattern=r"spill covering more than (\d+) ?%"),
    dict(parameter="rca_after_n_repairs", file="fleet/well-types/T200.md",
         protocol="RC-05", unit="count", applies_to="fleet",
         pattern=r"(three|four|five|\d+) or more corrective maintenance events",
         crosscheck=("fleet/well-types/T350.md",
                     r"rca after (three|four|five|\d+) corrective events")),
    dict(parameter="rca_lookback_months", file="fleet/well-types/T200.md",
         protocol="RC-05", unit="months", applies_to="fleet",
         pattern=r"same equipment kind in the (\d+) months before",
         crosscheck=("fleet/well-types/T350.md", r"within (\d+) months")),
    dict(parameter="downtime_report_days", file="fleet/well-types/T200.md",
         protocol="RC-03", unit="days", applies_to="fleet",
         pattern=r"downtime of more than (\d+) consecutive days",
         crosscheck=("fleet/sops/regulatory-compliance-sop.md",
                     r"more than (\d+) consecutive days must be reported")),
    dict(parameter="planned_shutin_log_required", file="fleet/well-types/T200.md",
         protocol="T200", unit="flag", applies_to="fleet",
         pattern=r"record the shut-in in the maintenance system"),
    # --- spill response SOP ---
    dict(parameter="sr01_hours", file="fleet/sops/spill-response-sop.md",
         protocol="SR-01", unit="hours", applies_to="fleet",
         pattern=r"cleanup plan\) within (\d+) hours of discovery"),
    dict(parameter="sr01_major_hours", file="fleet/sops/spill-response-sop.md",
         protocol="SR-01", unit="hours", applies_to="fleet",
         pattern=r"within (\d+) hours for a major spill"),
    dict(parameter="sr02_contain_hours", file="fleet/sops/spill-response-sop.md",
         protocol="SR-02", unit="hours", applies_to="fleet",
         pattern=r"contained within (\d+) hours of discovery"),
    dict(parameter="sr03_tph_pct", file="fleet/sops/spill-response-sop.md",
         protocol="SR-03", unit="percent", applies_to="fleet",
         pattern=r"cleaned to ([0-9.]+) ?% tph or less"),
    dict(parameter="sr03_samples", file="fleet/sops/spill-response-sop.md",
         protocol="SR-03", unit="count", applies_to="fleet",
         pattern=r"at least (\d+) soil samples"),
    dict(parameter="sr03_verify_days", file="fleet/sops/spill-response-sop.md",
         protocol="SR-03", unit="days", applies_to="fleet",
         pattern=r"verified within (\d+) days of discovery"),
    dict(parameter="spill_minor_max_bbl", file="fleet/sops/spill-response-sop.md",
         protocol="SR-04", unit="bbl", applies_to="fleet",
         pattern=r"minor \| below ([0-9.]+) bbl"),
    dict(parameter="spill_moderate_max_bbl", file="fleet/sops/spill-response-sop.md",
         protocol="SR-04", unit="bbl", applies_to="fleet",
         pattern=r"moderate \| [0-9.]+ bbl to below ([0-9.]+) bbl"),
    dict(parameter="spill_major_min_bbl", file="fleet/sops/spill-response-sop.md",
         protocol="SR-04", unit="bbl", applies_to="fleet",
         pattern=r"major \| ([0-9.]+) bbl or more"),
    dict(parameter="moderate_hse_notice_hours", file="fleet/sops/spill-response-sop.md",
         protocol="SR-04", unit="hours", applies_to="fleet",
         pattern=r"the (\d+)-hour hse notice"),
    # --- regulatory compliance SOP ---
    dict(parameter="rc01_inspection_days", file="fleet/sops/regulatory-compliance-sop.md",
         protocol="RC-01", unit="days", applies_to="fleet",
         pattern=r"at least once every (\d+) days"),
    dict(parameter="rc03_report_days", file="fleet/sops/regulatory-compliance-sop.md",
         protocol="RC-03", unit="days", applies_to="fleet",
         pattern=r"more than (\d+) consecutive days must be reported"),
    dict(parameter="rc04_nov_response_days", file="fleet/sops/regulatory-compliance-sop.md",
         protocol="RC-04", unit="days", applies_to="fleet",
         pattern=r"answered within (\d+) days"),
    # --- field work SOP ---
    dict(parameter="ws03_stopwork_ppm", file="fleet/sops/field-work-sop.md",
         protocol="WS-03", unit="ppm", applies_to="fleet",
         pattern=r"reads (\d+) ppm or more"),
    dict(parameter="ws04_lel_pct", file="fleet/sops/field-work-sop.md",
         protocol="WS-04", unit="percent", applies_to="fleet",
         pattern=r"reads (\d+) ?% of the lower explosive limit"),
    dict(parameter="ws05_test_multiple", file="fleet/sops/field-work-sop.md",
         protocol="WS-05", unit="ratio", applies_to="fleet",
         pattern=r"at least ([0-9.]+) ?×"),
    dict(parameter="ws05_hold_hours", file="fleet/sops/field-work-sop.md",
         protocol="WS-05", unit="hours", applies_to="fleet",
         pattern=r"hold for (\d+) hours"),
    dict(parameter="ws07_report_days", file="fleet/sops/field-work-sop.md",
         protocol="WS-07", unit="days", applies_to="fleet",
         pattern=r"within (\d+) days of finishing the work"),
]

# Known values on the sample dataset (guard 3, ingest_plan.md §5) — hard-fail on drift.
EXPECTED_SAMPLE = {
    "production_threshold": {"T200": 15, "T350": 20},
    "overtemp_alarm_c": {"T200": 85, "T350": 95},
    "spill_shutin_area_pct": {"T200": 5, "T350": 5},
    "rca_after_n_repairs": {"fleet": 3},
    "rca_lookback_months": {"fleet": 12},
    "downtime_report_days": {"fleet": 14},
    "planned_shutin_log_required": {"fleet": 1},
    "sr01_hours": {"fleet": 24},
    "sr01_major_hours": {"fleet": 2},
    "sr02_contain_hours": {"fleet": 4},
    "sr03_tph_pct": {"fleet": 1.0},
    "sr03_samples": {"fleet": 4},
    "sr03_verify_days": {"fleet": 60},
    "spill_minor_max_bbl": {"fleet": 1},
    "spill_moderate_max_bbl": {"fleet": 5},
    "spill_major_min_bbl": {"fleet": 25},
    "moderate_hse_notice_hours": {"fleet": 72},
    "rc01_inspection_days": {"fleet": 14},
    "rc03_report_days": {"fleet": 14},
    "rc04_nov_response_days": {"fleet": 30},
    "ws03_stopwork_ppm": {"fleet": 10},
    "ws04_lel_pct": {"fleet": 10},
    "ws05_test_multiple": {"fleet": 1.25},
    "ws05_hold_hours": {"fleet": 4},
    "ws07_report_days": {"fleet": 3},
    "downtime_days_per_finding": {"fleet": 7},
}

DOCS = [
    ("fleet/well-types/T200.md", "manual"),
    ("fleet/well-types/T350.md", "manual"),
    ("fleet/sops/spill-response-sop.md", "sop"),
    ("fleet/sops/regulatory-compliance-sop.md", "sop"),
    ("fleet/sops/field-work-sop.md", "sop"),
]


def seed_rules(dataset_id, data_root: Path, allow_override: bool):
    """Parse the dataset's OWN manuals/SOPs into rules rows. Fail-safe, never
    fail-silent: a missed pattern is a hard failure naming rule + file, unless
    --allow-override is given (escape hatch: row inserted with is_overridden=1)."""
    rows, seen = [], {}   # seen[(parameter, applies_to)] = value
    doc_cache = {}

    def doc_text(rel):
        if rel not in doc_cache:
            path = data_root / rel
            if not path.exists():
                fail(f"rules doc not found: {rel}")
            doc_cache[rel] = norm_doc(path.read_text(encoding="utf-8"))
        return doc_cache[rel]

    for spec in RULE_SPECS:
        text = doc_text(spec["file"])
        m = re.search(spec["pattern"], text)
        if not m:
            if allow_override:
                print(f"WARN: rule '{spec['parameter']}' pattern missed in "
                      f"{spec['file']}; inserting known row with is_overridden=1")
                rows.append((dataset_id, None, spec["protocol"], spec["parameter"],
                             None, spec["unit"], spec["applies_to"], 1,
                             spec["file"], None))
                continue
            fail(f"rule '{spec['parameter']}' not found in {spec['file']} "
                 f"(pattern: {spec['pattern']})")
        if m.lastindex is None or m.lastindex < 1:
            value = 1  # flag patterns (e.g. planned_shutin_log_required)
        else:
            value = to_number(m.group(1))
        start = max(0, m.start() - 30)
        snippet = "…" + text[start:m.end() + 40] + "…"
        rule_id = spec["parameter"] if spec["applies_to"] == "fleet" \
            else f"{spec['parameter']}:{spec['applies_to']}"
        rows.append((dataset_id, rule_id, spec["protocol"], spec["parameter"],
                     value, spec["unit"], spec["applies_to"], 0,
                     spec["file"], snippet))
        seen[(spec["parameter"], spec["applies_to"])] = value

        # cross-check: the same rule stated in a second doc must agree
        if "crosscheck" in spec:
            cc_file, cc_pattern = spec["crosscheck"]
            cc_m = re.search(cc_pattern, doc_text(cc_file))
            if not cc_m:
                fail(f"cross-check for rule '{spec['parameter']}' not found in {cc_file}")
            cc_value = to_number(cc_m.group(1))
            if cc_value != value:
                fail(f"cross-check mismatch for '{spec['parameter']}': "
                     f"{spec['file']} says {value}, {cc_file} says {cc_value}")

    # Dataset-Guide rule (the only doc-external threshold): 7 days per finding.
    guide = data_root.parent / "02-dataset-guide.md"
    ddf_value = 7
    ddf_source = "dataset-guide"
    ddf_snippet = "each inspection … counts as 7 days of downtime (fallback constant)"
    if guide.exists():
        gtext = norm_doc(guide.read_text(encoding="utf-8"))
        gm = re.search(r"counts as (\d+) days of downtime", gtext)
        if gm:
            ddf_value = int(gm.group(1))
            ddf_snippet = "…" + gtext[max(0, gm.start() - 30):gm.end() + 20] + "…"
        else:
            print("WARN: downtime days/finding not parseable in 02-dataset-guide.md; "
                  f"falling back to {ddf_value}")
    else:
        print(f"WARN: dataset guide not found next to {data_root}; "
              f"using fallback {ddf_value} days/finding")
    rows.append((dataset_id, "downtime_days_per_finding", "GUIDE",
                 "downtime_days_per_finding", ddf_value, "days", "fleet", 0,
                 ddf_source, ddf_snippet))
    seen[("downtime_days_per_finding", "fleet")] = ddf_value

    # guard 3: on sample, values must equal the known set (hard-fail on drift)
    if dataset_id == "sample":
        for param, expected in EXPECTED_SAMPLE.items():
            for applies_to, exp_val in expected.items():
                if (param, applies_to) not in seen:
                    fail(f"expected rule '{param}' ({applies_to}) missing from seeded rules")
                got = seen[(param, applies_to)]
                if float(got) != float(exp_val):
                    fail(f"rule '{param}' ({applies_to}) drifted: "
                         f"expected {exp_val}, parsed {got}")

    # print the full rules table for a 5-second human eyeball
    print(f"\n--- rules seeded for dataset '{dataset_id}' ({len(rows)} rows) ---")
    for r in rows:
        _, rule_id, protocol, parameter, value, unit, applies_to, overridden, doc, snippet = r
        flag = " [OVERRIDDEN]" if overridden else ""
        print(f"  {parameter:<28} {value!s:>6} {unit:<8} {applies_to:<6} "
              f"← {doc}  {snippet or ''}{flag}")
    print()
    return rows


# ------------------------------------------------------------------------- ingest

def ingest_dataset(conn, data_root: Path, dataset_id: str, as_of_opt, allow_override):
    counts = {}
    unparsed_bucket = {"unparsed": 0}

    # ---- fleet: teams first (team names live in areas.json), then areas, users
    areas_doc = read_json(data_root / "fleet" / "areas.json")
    teams = [(dataset_id, t["team_id"], t.get("name"), t.get("lead_user_id"))
             for t in areas_doc.get("teams", [])]
    areas = [(dataset_id, a["area_id"], a["name"], a.get("team_id"),
              a.get("center", {}).get("lat"), a.get("center", {}).get("lon"))
             for a in areas_doc.get("areas", [])]
    users = [(dataset_id, u["user_id"], u.get("name"), u.get("role"), u.get("team_id"))
             for u in read_json(data_root / "fleet" / "users.json").get("users", [])]

    # ---- wells + equipment (per-well metadata.json)
    wells, equipment = [], []
    well_dirs = sorted(data_root.glob("assets/WELL-*"))
    for wdir in well_dirs:
        meta = read_json(wdir / "metadata.json")
        if meta.get("asset_category") != "oil_well":
            fail(f"{wdir.name}: asset_category '{meta.get('asset_category')}' is not "
                 "'oil_well' — the wells-as-assets assumption broke (database_plan.md §2)")
        loc = meta.get("location", {})
        li = meta.get("last_inspection", {}) or {}
        wells.append((
            dataset_id, meta["asset_id"], meta.get("name"), meta.get("asset_category"),
            meta.get("well_type"), meta.get("area_id"), meta.get("team_id"),
            meta.get("in_charge_user_id"), loc.get("lat"), loc.get("lon"),
            meta.get("installed_on"), li.get("inspection_id"), li.get("inspected_at"),
            meta.get("recorded_status"),
        ))
        for eq in meta.get("equipment", []):
            equipment.append((dataset_id, eq["equipment_id"], meta["asset_id"],
                              eq.get("kind"), eq.get("model")))
    counts["wells"] = len(wells)
    counts["equipment"] = len(equipment)

    # ---- jsonl event records (per-well files)
    inspections, maintenance, regulatory, notes = [], [], [], []
    note_dicts = []
    for wdir in well_dirs:
        for rec in read_jsonl(wdir / "inspections.jsonl"):
            inspections.append((
                dataset_id, rec["inspection_id"], rec["asset_id"], rec.get("inspected_at"),
                rec.get("inspector_user_id"), rec.get("method"),
                rec.get("ambient_temp_c"), rec.get("wellhead_temp_c"),
                (rec.get("wellhead_temp_c") - rec.get("ambient_temp_c"))
                if rec.get("wellhead_temp_c") is not None
                and rec.get("ambient_temp_c") is not None else None,
                1 if rec.get("spill_detected") else 0,
                rec.get("spill_area_pct"), rec.get("spill_est_volume_bbl"),
                json.dumps(rec.get("evidence_images") or []), rec.get("notes"),
            ))
        for rec in read_jsonl(wdir / "maintenance.jsonl"):
            cost = rec.get("cost_usd") or {}
            maintenance.append((
                dataset_id, rec["maintenance_id"], rec["asset_id"],
                rec.get("started_at"), rec.get("completed_at"),
                rec.get("maintenance_type"), rec.get("equipment_kind"),
                rec.get("issue"), rec.get("action_taken"),
                rec.get("technician_user_id"), rec.get("contractor"),
                rec.get("downtime_hours"),
                cost.get("labor"), cost.get("parts"), cost.get("total"),
                rec.get("triggered_by_inspection_id"), rec.get("report_file"),
            ))
        for rec in read_jsonl(wdir / "regulatory-events.jsonl"):
            regulatory.append((
                dataset_id, rec["event_id"], rec["asset_id"], rec.get("date"),
                rec.get("agency"), rec.get("event_type"), rec.get("protocol_id"),
                rec.get("related_inspection_id"), rec.get("hours_to_report"),
                rec.get("fine_usd"), rec.get("status"), rec.get("detail"),
            ))
        for rec in read_jsonl(wdir / "context.jsonl"):
            note_dicts.append(rec)
            notes.append((
                dataset_id, rec["note_id"], rec["asset_id"], rec.get("created_at"),
                rec.get("author_user_id"), rec.get("note_type"),
                rec.get("inspection_id"), rec.get("text"),
                rec.get("valid_from"), rec.get("valid_to"),
            ))
    counts["inspections"] = len(inspections)
    counts["maintenance"] = len(maintenance)
    counts["regulatory_events"] = len(regulatory)
    counts["context_notes"] = len(notes)

    # ---- corrections mirror (§3): ingested corrections only
    corrections = mirror_corrections(dataset_id, note_dicts, unparsed_bucket)
    counts["corrections"] = len(corrections)

    # ---- report extraction (§4): walk maintenance.report_file — the file name
    # is NOT always the maintenance id (e.g. MNT-0001-july-2025-prime-mover.md);
    # the report_file column is the authoritative link.
    report_facts = []
    cov = {"spill_rows": 0, "contained": 0, "class": 0, "root": 0, "action": 0, "total": 0}
    insp_ids = {i[1] for i in inspections}
    for mnt in maintenance:
        rel = mnt[16]  # report_file
        if rel is None:
            continue
        rfile = data_root / "assets" / mnt[2] / rel  # assets/<asset_id>/<report_file>
        if not rfile.exists():
            fail(f"report_file missing on disk: {rfile}")
        mnt_id = mnt[1]
        facts, status, spill_relevant = extract_report(rfile.read_text(encoding="utf-8"))
        trigger = mnt[15]  # triggered_by_inspection_id
        if trigger is not None and trigger not in insp_ids:
            fail(f"{mnt_id}: triggered_by_inspection_id '{trigger}' is an orphan")
        report_facts.append((
            dataset_id, mnt_id, trigger,
            facts["contained_hours_after"], facts["rca_action_required"],
            facts["spill_class"], facts["root_cause"], status,
        ))
        cov["total"] += 1
        cov["root"] += 1 if facts["root_cause"] else 0
        cov["action"] += 1 if facts["rca_action_required"] else 0
        if spill_relevant:
            cov["spill_rows"] += 1
            cov["contained"] += 1 if facts["contained_hours_after"] is not None else 0
            cov["class"] += 1 if facts["spill_class"] else 0
    counts["report_facts"] = len(report_facts)

    # ---- documents catalog + rules seeding (§5)
    documents = []
    for rel, doc_type in DOCS:
        path = data_root / rel
        if not path.exists():
            fail(f"document missing from dataset: {rel}")
        title = path.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
        documents.append((dataset_id, rel, doc_type, rel, title))
    counts["documents"] = len(documents)
    rules_rows = seed_rules(dataset_id, data_root, allow_override)
    counts["rules"] = len(rules_rows)

    # ---- default mode = replace per dataset: delete old rows, insert new, one txn
    # (rules: runtime overrides survive the delete — review R2 — they are marked
    # is_overridden=1 AND source_doc='runtime' and carry their own rule_id)
    conn.execute("BEGIN")
    preserved_overrides = 0
    for table in create.INGESTED_TABLES:
        if table == "rules":
            preserved_overrides = one_count(conn,
                "SELECT COUNT(*) FROM rules WHERE dataset_id = ? "
                "AND is_overridden = 1 AND source_doc = 'runtime'", (dataset_id,))
            conn.execute("DELETE FROM rules WHERE dataset_id = ? "
                         "AND NOT (is_overridden = 1 AND source_doc = 'runtime')",
                         (dataset_id,))
        else:
            conn.execute(f"DELETE FROM {table} WHERE dataset_id = ?", (dataset_id,))
    conn.executemany("INSERT INTO teams VALUES (?,?,?,?)", teams)
    conn.executemany("INSERT INTO areas VALUES (?,?,?,?,?,?)", areas)
    conn.executemany("INSERT INTO users VALUES (?,?,?,?,?)", users)
    conn.executemany("INSERT INTO wells VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", wells)
    conn.executemany("INSERT INTO equipment VALUES (?,?,?,?,?)", equipment)
    conn.executemany("INSERT INTO inspections VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", inspections)
    conn.executemany("INSERT INTO maintenance VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", maintenance)
    conn.executemany("INSERT INTO report_facts VALUES (?,?,?,?,?,?,?,?)", report_facts)
    conn.executemany("INSERT INTO regulatory_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", regulatory)
    conn.executemany("INSERT INTO context_notes VALUES (?,?,?,?,?,?,?,?,?,?)", notes)
    conn.executemany("INSERT INTO corrections VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", corrections)
    conn.executemany("INSERT INTO documents VALUES (?,?,?,?,?)", documents)
    conn.executemany("INSERT INTO rules VALUES (?,?,?,?,?,?,?,?,?,?)", rules_rows)

    # ---- meta
    create.set_meta(conn, f"dataset_root_{dataset_id}", str(data_root.resolve()))
    for table, n in counts.items():
        create.set_meta(conn, f"rows_{dataset_id}_{table}", n)
    create.set_meta(conn, f"unparsed_corrections_{dataset_id}", unparsed_bucket["unparsed"])
    create.set_meta(conn, f"extract_{dataset_id}_spill_rows", cov["spill_rows"])
    create.set_meta(conn, f"extract_{dataset_id}_contained", cov["contained"])
    create.set_meta(conn, f"extract_{dataset_id}_class", cov["class"])
    create.set_meta(conn, f"extract_{dataset_id}_root", cov["root"])
    create.set_meta(conn, f"extract_{dataset_id}_action", cov["action"])

    # per-dataset as_of = max(inspected_at) + 1 day
    max_insp = conn.execute(
        "SELECT MAX(inspected_at) FROM inspections WHERE dataset_id = ?",
        (dataset_id,)).fetchone()[0]
    if max_insp is None:
        fail(f"dataset '{dataset_id}' has no inspections")
    ds_as_of = (datetime.fromisoformat(max_insp.replace("Z", "+00:00")).date()
                + timedelta(days=1)).isoformat()
    create.set_meta(conn, f"as_of_{dataset_id}", ds_as_of)

    conn.commit()

    if preserved_overrides:
        print(f"INFO: preserved {preserved_overrides} runtime rule override(s) "
              f"for dataset '{dataset_id}' (they survive re-ingest)")

    # coverage report
    print(f"--- report extraction coverage ({dataset_id}) ---")
    print(f"  reports parsed:      {cov['total']}")
    print(f"  root_cause:          {cov['root']}/{cov['total']}")
    print(f"  rca_action_required: {cov['action']}/{cov['total']}")
    if cov["spill_rows"]:
        print(f"  spill-relevant rows: {cov['spill_rows']}")
        print(f"  contained_hours:     {cov['contained']}/{cov['spill_rows']} "
              f"({100.0 * cov['contained'] / cov['spill_rows']:.1f}%)")
        print(f"  spill_class:         {cov['class']}/{cov['spill_rows']} "
              f"({100.0 * cov['class'] / cov['spill_rows']:.1f}%)")
    else:
        print("  spill-relevant rows: 0 (no SR-02 reports in this dataset)")
    if unparsed_bucket["unparsed"]:
        print(f"  WARNING: {unparsed_bucket['unparsed']} correction note(s) did not "
              "match the format contract — verify will hard-fail")

    return ds_as_of


def recompute_global_as_of(conn, as_of_opt):
    """Global as_of = max over datasets of (max inspected_at + 1 day),
    unless --as-of given."""
    if as_of_opt:
        create.set_meta(conn, "as_of", as_of_opt)
        return as_of_opt
    best = None
    for row in conn.execute(
            "SELECT MAX(inspected_at) FROM inspections").fetchall():
        if row[0] and (best is None or row[0] > best):
            best = row[0]
    if best is None:
        fail("no inspections in DB; cannot compute as_of")
    as_of = (datetime.fromisoformat(best.replace("Z", "+00:00")).date()
             + timedelta(days=1)).isoformat()
    create.set_meta(conn, "as_of", as_of)
    return as_of


# --------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Build the Well Copilot SQLite DB.")
    ap.add_argument("--data", required=True, help="dataset folder (contains assets/, fleet/)")
    ap.add_argument("--dataset", choices=["sample", "test"], default=None,
                    help="dataset_id stamped on every row (default: sniff from folder name)")
    ap.add_argument("--db", default="data/well_copilot.db", help="output SQLite path")
    ap.add_argument("--fresh", action="store_true",
                    help="delete the DB file first (full rebuild)")
    ap.add_argument("--as-of", dest="as_of", default=None,
                    help="evaluation 'today' (YYYY-MM-DD); default max(inspected_at)+1d")
    ap.add_argument("--allow-override", action="store_true",
                    help="escape hatch: a rule whose pattern misses is inserted as a "
                         "known row with is_overridden=1 instead of failing")
    ap.add_argument("--skip-verify", action="store_true",
                    help="skip the verification gate (never do this)")
    args = ap.parse_args()

    data_root = Path(args.data)
    if not (data_root / "assets").is_dir() or not (data_root / "fleet").is_dir():
        fail(f"{data_root} does not look like a dataset folder (needs assets/ + fleet/)")
    dataset_id = args.dataset or sniff_dataset_id(data_root)

    db_path = Path(args.db)
    if args.fresh and db_path.exists():
        db_path.unlink()
        print(f"deleted {db_path} (--fresh)")
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.isolation_level = None  # explicit BEGIN/COMMIT (replace-per-dataset txn)
    conn.execute("PRAGMA journal_mode = WAL")
    create.create_schema(conn)

    create.set_meta(conn, "built_at", datetime.now().isoformat(timespec="seconds"))
    create.set_meta(conn, "ingest_version", create.INGEST_VERSION)

    t0 = datetime.now()
    print(f"ingesting '{dataset_id}' from {data_root}")
    ingest_dataset(conn, data_root, dataset_id, args.as_of, args.allow_override)
    as_of = recompute_global_as_of(conn, args.as_of)
    print(f"as_of = {as_of}")

    views_mod.apply_views(conn)
    print(f"views applied ({len(views_mod.VIEWS)}): " + ", ".join(views_mod.VIEWS))

    if not args.skip_verify:
        verify_mod.run_all(conn, data_root=data_root)

    dt = (datetime.now() - t0).total_seconds()
    print(f"\nOK — {db_path} built in {dt:.1f}s")
    conn.close()


if __name__ == "__main__":
    main()
