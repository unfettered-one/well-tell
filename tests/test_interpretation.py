"""Independent interpretation evaluator regressions; no model needed."""

import sqlite3

import pytest

from backend.opencode import parse_answer
from eval_interpretation import check_response, readonly_connection, reference_counts


def test_reference_distinguishes_records_completion_and_services(tmp_path):
    path = tmp_path / "reference.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE meta(key TEXT,value TEXT)")
        conn.execute("INSERT INTO meta VALUES ('as_of_sample','2026-10-16')")
        conn.execute("CREATE TABLE maintenance(dataset_id TEXT,maintenance_id TEXT,maintenance_type TEXT,started_at TEXT,completed_at TEXT)")
        conn.executemany("INSERT INTO maintenance VALUES (?,?,?,?,?)", [
            ("sample", "done", "corrective", "2026-10-01", "2026-10-16T23:59:00Z"),
            ("sample", "future-completion", "corrective", "2026-10-01", "2026-10-17"),
            ("sample", "open", "corrective", "2026-10-01", None),
            ("sample", "future-start", "corrective", "2026-10-17", "2026-10-18"),
            ("sample", "service", "scheduled", "2026-10-01", "2026-10-02"),
            ("test", "other", "corrective", "2026-10-01", "2026-10-02"),
        ])
    assert reference_counts(path, "sample") == {
        "as_of": "2026-10-16", "completed_repairs": 1,
        "recorded_repairs": 3, "completed_services": 1,
    }


def response(answer, tools=None):
    return {"answer": answer, "citations": [], "visual": None,
            "tool_calls": tools or [{"name": "well_recall", "status": "completed"}]}


def test_clarification_is_success_not_an_answer_failure():
    assert check_response(response("Do you mean repair activities or equipment categories?"), None, [], clarify=True) == []
    assert check_response(response("There are 2 categories. Do you want more?"), None, [], clarify=True)
    assert check_response(response("Two maintenance types."), None, [], clarify=True)


def test_count_cannot_pass_on_answer_keyword_alone():
    data = response("1500 completed corrective jobs.")
    assert check_response(data, 1500, [])
    queries = [{"sql": "SELECT COUNT(*) AS jobs FROM maintenance", "result": {"rows": [{"jobs": 1500}]}}]
    assert check_response(data, 1500, queries) == []
    assert check_response(response("1509 repair jobs."), 1500, queries)


def test_read_question_must_not_mutate_domain():
    data = response("Which types?", [
        {"name": "well_recall", "status": "completed"},
        {"name": "well_set_rule", "status": "completed"},
    ])
    assert "read-only question caused a domain write" in check_response(data, None, [], clarify=True)


def test_activity_check_requires_real_report_followthrough():
    data = response("Pipe repairs.")
    assert check_response(data, None, [])
    data["citations"] = ["MNT-example"]
    data["tool_calls"].append({"name": "well_get_report", "status": "completed"})
    assert check_response(data, None, [{"sql": "SELECT issue FROM maintenance", "result": {}}]) == []


def test_reference_connection_cannot_change_data(tmp_path):
    path = tmp_path / "wal.db"
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE records(value INTEGER)")
        conn.execute("INSERT INTO records VALUES (1)")
    conn = readonly_connection(path)
    try:
        assert conn.execute("SELECT value FROM records").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO records VALUES (2)")
    finally:
        conn.close()


def test_clarification_uses_existing_answer_contract_with_recall_only():
    messages = [{"type": "assistant", "content": [
        {"type": "tool", "name": "well_recall", "state": {
            "status": "completed", "content": [{"type": "text", "text": "{}"}]}},
        {"type": "text", "text": '{"answer":"Do you mean repair activities or equipment categories?","citations":[],"visual":null}'},
    ]}]
    data = parse_answer(messages)
    assert data["visual"] is None
    assert data["citations"] == []
    assert data["answer"].endswith("?")
