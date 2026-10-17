"""Real-file ingest regressions, including alongside-dataset loads."""

import sqlite3
import subprocess
import sys

from conftest import REPO
import documents

sys.path.append(str(REPO / "ingest"))
import views

DATA = REPO / "dataset/flytbase-ahc-swe-asset-intelligence-dataset/sample-data"


def ingest(path, *extra):
    result = subprocess.run([sys.executable, str(REPO / "ingest/ingest.py"),
        "--data", str(DATA), "--db", str(path), *extra], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "VERIFICATION PASSED" in result.stdout


def test_idempotent_load_and_test_alongside_sample(db_copy):
    with sqlite3.connect(db_copy) as conn:
        conn.execute("INSERT INTO memories VALUES ('test','U-201',NULL,'private','2026-10-17')")
        conn.execute("INSERT INTO rules VALUES ('sample','test-override',NULL,'rca_after_n_repairs','2','count','T350',1,'runtime','test')")
    ingest(db_copy, "--dataset", "sample")
    ingest(db_copy, "--dataset", "test", "--as-of", "2026-10-20")
    with sqlite3.connect(db_copy) as conn:
        assert conn.execute("SELECT dataset_id,COUNT(*) FROM wells GROUP BY dataset_id ORDER BY dataset_id").fetchall() == [("sample", 200), ("test", 200)]
        assert conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 1
        assert conn.execute("SELECT value FROM rules WHERE rule_id='test-override'").fetchone()[0] == "2"
        assert conn.execute("SELECT value FROM meta WHERE key='as_of_test'").fetchone()[0] == "2026-10-20"
        assert conn.execute("SELECT value FROM meta WHERE key='as_of_sample'").fetchone()[0] == "2026-10-16"
        assert conn.execute("SELECT COUNT(*) FROM v_spills WHERE dataset_id='sample' AND asset_id='WELL-0001'").fetchone()[0] == 6
        conn.row_factory = sqlite3.Row
        for dataset in ("sample", "test"):
            assert documents.read_document(conn, "fleet/well-types/T200.md", dataset)["dataset_id"] == dataset
            assert documents.read_report(conn, "MNT-0082-028", dataset)["dataset_id"] == dataset


def test_explicit_sample_evaluation_date(db_copy):
    ingest(db_copy, "--dataset", "sample", "--as-of", "2026-10-20")
    with sqlite3.connect(db_copy) as conn:
        assert conn.execute("SELECT value FROM meta WHERE key='as_of_sample'").fetchone()[0] == "2026-10-20"


def test_invalid_date_fails_before_db_changes(tmp_path):
    path = tmp_path / "invalid.db"
    result = subprocess.run([sys.executable, str(REPO / "ingest/ingest.py"),
        "--data", str(DATA), "--db", str(path), "--as-of", "2026-02-31"], capture_output=True)
    assert result.returncode != 0
    assert not path.exists()


def test_sop_deadline_uses_hours_not_calendar_day(db_copy):
    with sqlite3.connect(db_copy) as conn:
        views.apply_views(conn)
        conn.execute("DELETE FROM regulatory_events WHERE dataset_id='sample' AND related_inspection_id='INS-0001-0185'")
        conn.execute("UPDATE inspections SET inspected_at='2026-10-15T23:00:00Z' WHERE dataset_id='sample' AND inspection_id='INS-0001-0185'")
        row = conn.execute("SELECT status,deadline_at FROM v_sobligations WHERE dataset_id='sample' AND inspection_id='INS-0001-0185' AND obligation_protocol='SR-01'").fetchone()
        assert row == ("open", "2026-10-16 23:00:00")
        conn.execute("UPDATE meta SET value='2026-10-17' WHERE key='as_of_sample'")
        assert conn.execute("SELECT status FROM v_sobligations WHERE dataset_id='sample' AND inspection_id='INS-0001-0185' AND obligation_protocol='SR-01'").fetchone()[0] == "overdue"


def test_runtime_claims_are_visible_in_dataset_filtered_conflicts(db_copy):
    with sqlite3.connect(db_copy) as conn:
        views.apply_views(conn)
        conn.execute("INSERT INTO claims VALUES ('CLAIM-test','U-201','WELL-0001','back online','unconfirmed','2026-10-17T00:00:00Z')")
        rows = conn.execute("SELECT dataset_id,inspection_id FROM v_conflicts WHERE dataset_id='sample' AND source_a_id='CLAIM-test'").fetchall()
        assert rows == [("sample", "INS-0001-0203")]


def test_latest_correction_wins_when_timestamps_tie(db_copy):
    with sqlite3.connect(db_copy) as conn:
        views.apply_views(conn)
        for number, value in enumerate((5.4, 5.8)):
            conn.execute("INSERT INTO corrections(dataset_id,correction_id,source,asset_id,inspection_id,field,original_value,corrected_value,reason,created_at,status) VALUES (NULL,?,'runtime','WELL-0151','INS-0151-0201','spill_est_volume_bbl','4.5',?,'test','2026-10-17T00:00:00Z','applied')", (f"COR-tie-{number}", str(value)))
        row = conn.execute("SELECT eff_spill_volume_bbl FROM v_inspection_effective WHERE dataset_id='sample' AND inspection_id='INS-0151-0201'").fetchone()
        assert row[0] == 5.8
