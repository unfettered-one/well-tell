"""create.py — DDL for the Well Copilot SQLite DB.

Three layers (database_plan.md §1):
  raw      — ingested dataset rows, every table keyed (dataset_id, <id>)
  derived  — SQL views (views.py, applied after load)
  runtime  — sessions/messages/memories/facts/claims, written by MCP tools later

Run-time tables are created EMPTY here; ingest never touches them.
"""

INGEST_VERSION = "1.0.0"

DDL = [
    # ---------- fleet dimensions ----------
    """CREATE TABLE IF NOT EXISTS teams (
        dataset_id   TEXT NOT NULL,
        team_id      TEXT NOT NULL,
        name         TEXT,
        lead_user_id TEXT,
        PRIMARY KEY (dataset_id, team_id)
    )""",
    """CREATE TABLE IF NOT EXISTS users (
        dataset_id TEXT NOT NULL,
        user_id    TEXT NOT NULL,
        name       TEXT,
        role       TEXT,
        team_id    TEXT,
        PRIMARY KEY (dataset_id, user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS areas (
        dataset_id TEXT NOT NULL,
        area_id    TEXT NOT NULL,
        name       TEXT,
        team_id    TEXT,
        center_lat REAL,
        center_lon REAL,
        PRIMARY KEY (dataset_id, area_id)
    )""",
    # wells IS the asset table (database_plan.md §2)
    """CREATE TABLE IF NOT EXISTS wells (
        dataset_id         TEXT NOT NULL,
        asset_id           TEXT NOT NULL,
        name               TEXT,
        asset_category     TEXT,
        well_type          TEXT,
        area_id            TEXT,
        team_id            TEXT,
        in_charge_user_id  TEXT,
        lat                REAL,
        lon                REAL,
        installed_on       TEXT,
        last_inspection_id TEXT,
        last_inspection_at TEXT,
        recorded_status    TEXT,
        PRIMARY KEY (dataset_id, asset_id)
    )""",
    """CREATE TABLE IF NOT EXISTS equipment (
        dataset_id   TEXT NOT NULL,
        equipment_id TEXT NOT NULL,
        asset_id     TEXT NOT NULL,
        kind         TEXT,
        model        TEXT,
        PRIMARY KEY (dataset_id, equipment_id)
    )""",
    # ---------- weekly / event records ----------
    """CREATE TABLE IF NOT EXISTS inspections (
        dataset_id           TEXT NOT NULL,
        inspection_id        TEXT NOT NULL,
        asset_id             TEXT NOT NULL,
        inspected_at         TEXT,
        inspector_user_id    TEXT,
        method               TEXT,
        ambient_temp_c       REAL,
        wellhead_temp_c      REAL,
        temp_delta_c         REAL,
        spill_detected       INTEGER,
        spill_area_pct       REAL,
        spill_est_volume_bbl REAL,
        evidence_images_json TEXT,
        notes                TEXT,
        PRIMARY KEY (dataset_id, inspection_id)
    )""",
    """CREATE TABLE IF NOT EXISTS maintenance (
        dataset_id                 TEXT NOT NULL,
        maintenance_id             TEXT NOT NULL,
        asset_id                   TEXT NOT NULL,
        started_at                 TEXT,
        completed_at               TEXT,
        maintenance_type           TEXT,
        equipment_kind             TEXT,
        issue                      TEXT,
        action_taken               TEXT,
        technician_user_id         TEXT,
        contractor                 TEXT,
        downtime_hours             REAL,
        cost_labor                 REAL,
        cost_parts                 REAL,
        cost_total                 REAL,
        triggered_by_inspection_id TEXT,
        report_file                TEXT,
        PRIMARY KEY (dataset_id, maintenance_id)
    )""",
    """CREATE TABLE IF NOT EXISTS report_facts (
        dataset_id           TEXT NOT NULL,
        maintenance_id       TEXT NOT NULL,
        inspection_id        TEXT,
        contained_hours_after REAL,
        rca_action_required  INTEGER,
        spill_class          TEXT,
        root_cause           TEXT,
        extraction_status    TEXT,
        PRIMARY KEY (dataset_id, maintenance_id)
    )""",
    """CREATE TABLE IF NOT EXISTS regulatory_events (
        dataset_id             TEXT NOT NULL,
        event_id               TEXT NOT NULL,
        asset_id               TEXT NOT NULL,
        date                   TEXT,
        agency                 TEXT,
        event_type             TEXT,
        protocol_id            TEXT,
        related_inspection_id  TEXT,
        hours_to_report        REAL,
        fine_usd               REAL,
        status                 TEXT,
        detail                 TEXT,
        PRIMARY KEY (dataset_id, event_id)
    )""",
    """CREATE TABLE IF NOT EXISTS context_notes (
        dataset_id     TEXT NOT NULL,
        note_id        TEXT NOT NULL,
        asset_id       TEXT NOT NULL,
        created_at     TEXT,
        author_user_id TEXT,
        note_type      TEXT,
        inspection_id  TEXT,
        text           TEXT,
        valid_from     TEXT,
        valid_to       TEXT,
        PRIMARY KEY (dataset_id, note_id)
    )""",
    # ---------- corrections: the ONE effective layer ----------
    # dataset_id is NULL for runtime corrections (apply to every dataset).
    # SQLite rowid tables allow NULL in composite-PK columns.
    """CREATE TABLE IF NOT EXISTS corrections (
        dataset_id      TEXT,
        correction_id   TEXT NOT NULL,
        source          TEXT,
        asset_id        TEXT,
        inspection_id   TEXT,
        well_type       TEXT,
        field           TEXT,
        original_value  TEXT,
        corrected_value TEXT,
        reason          TEXT,
        author_user_id  TEXT,
        created_at      TEXT,
        valid_from      TEXT,
        valid_to        TEXT,
        status          TEXT,
        PRIMARY KEY (dataset_id, correction_id)
    )""",
    # ---------- knowledge: docs catalog + rules as data ----------
    """CREATE TABLE IF NOT EXISTS documents (
        dataset_id TEXT NOT NULL,
        doc_id     TEXT NOT NULL,
        doc_type   TEXT,
        path       TEXT,
        title      TEXT,
        PRIMARY KEY (dataset_id, doc_id)
    )""",
    """CREATE TABLE IF NOT EXISTS rules (
        dataset_id     TEXT NOT NULL,
        rule_id        TEXT NOT NULL,
        protocol_id    TEXT,
        parameter      TEXT NOT NULL,
        value          TEXT,
        unit           TEXT,
        applies_to     TEXT,
        is_overridden  INTEGER DEFAULT 0,
        source_doc     TEXT,
        source_snippet TEXT,
        PRIMARY KEY (dataset_id, rule_id)
    )""",
    # ---------- runtime (written by MCP tools during chat; never by ingest) ----------
    """CREATE TABLE IF NOT EXISTS backend_conversations (
        session_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        opencode_id TEXT UNIQUE,
        dataset_id TEXT NOT NULL,
        busy_until REAL NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        user_id    TEXT,
        started_at TEXT,
        title      TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS messages (
        message_id            TEXT PRIMARY KEY,
        session_id            TEXT,
        role                  TEXT,
        content               TEXT,
        referenced_wells_json TEXT,
        created_at            TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS memories (
        memory_id  TEXT PRIMARY KEY,
        user_id    TEXT,
        session_id TEXT,
        text       TEXT,
        created_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS facts (
        fact_id        TEXT PRIMARY KEY,
        author_user_id TEXT,
        scope          TEXT,
        scope_value    TEXT,
        text           TEXT,
        created_at     TEXT,
        valid_to       TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS claims (
        claim_id   TEXT PRIMARY KEY,
        user_id    TEXT,
        asset_id   TEXT,
        text       TEXT,
        status     TEXT DEFAULT 'unconfirmed',
        created_at TEXT
    )""",
    # ---------- meta ----------
    """CREATE TABLE IF NOT EXISTS meta (
        key   TEXT PRIMARY KEY,
        value TEXT
    )""",
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_insp_asset_time  ON inspections(dataset_id, asset_id, inspected_at)",
    "CREATE INDEX IF NOT EXISTS idx_insp_time        ON inspections(dataset_id, inspected_at)",
    "CREATE INDEX IF NOT EXISTS idx_insp_spill       ON inspections(dataset_id, spill_detected)",
    "CREATE INDEX IF NOT EXISTS idx_mnt_asset_start  ON maintenance(dataset_id, asset_id, started_at)",
    "CREATE INDEX IF NOT EXISTS idx_mnt_type_equip   ON maintenance(dataset_id, maintenance_type, equipment_kind, started_at)",
    "CREATE INDEX IF NOT EXISTS idx_mnt_trigger      ON maintenance(dataset_id, triggered_by_inspection_id)",
    "CREATE INDEX IF NOT EXISTS idx_reg_trigger      ON regulatory_events(dataset_id, related_inspection_id)",
    "CREATE INDEX IF NOT EXISTS idx_notes_asset      ON context_notes(dataset_id, asset_id)",
    "CREATE INDEX IF NOT EXISTS idx_notes_insp       ON context_notes(dataset_id, inspection_id)",
    "CREATE INDEX IF NOT EXISTS idx_corr_insp        ON corrections(dataset_id, inspection_id)",
    "CREATE INDEX IF NOT EXISTS idx_corr_asset       ON corrections(dataset_id, asset_id)",
    "CREATE INDEX IF NOT EXISTS idx_corr_welltype    ON corrections(dataset_id, well_type)",
    "CREATE INDEX IF NOT EXISTS idx_rules_param      ON rules(dataset_id, parameter)",
    "CREATE INDEX IF NOT EXISTS idx_wells_area       ON wells(dataset_id, area_id)",
    "CREATE INDEX IF NOT EXISTS idx_rf_insp          ON report_facts(dataset_id, inspection_id)",
]

# Ingested tables, in dependency order. Replace-per-dataset deletes from these only.
INGESTED_TABLES = [
    "report_facts",
    "regulatory_events",
    "context_notes",
    "maintenance",
    "inspections",
    "equipment",
    "wells",
    "corrections",   # only rows with dataset_id = <id> (runtime rows have NULL, kept)
    "documents",
    "rules",
    "teams",
    "users",
    "areas",
]


def create_schema(conn):
    """Create all tables + indexes. Idempotent (IF NOT EXISTS)."""
    for stmt in DDL:
        conn.execute(stmt)
    for stmt in INDEXES:
        conn.execute(stmt)
    conn.commit()


def set_meta(conn, key, value):
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )


def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default
