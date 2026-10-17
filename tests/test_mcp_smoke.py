"""test_mcp_smoke.py — end-to-end smoke test of the mcp/ server over real stdio.

Spawns ``mcp/server.py`` exactly the way a client (e.g. opencode.json) would —
as a subprocess on stdio — against a private COPY of the ingested DB, and
walks the mcp_plan.md §11 checks:

  - tool surface + prompts (names, read-only annotations)
  - Q1  (v_producing_now WELL-0001 -> not producing, INS-0001-0203)
  - Q4  (v_spills WELL-0001 -> 6 spills / 15.1 bbl, corrected detection gone)
  - Q10 (get_report MNT-0082-028 -> contained about 7.1 h)
  - read-only rejections (INSERT / stacked / CTE-smuggled write, doc escapes)
  - a correction round-trip (record_correction -> the view flips, raw row kept)
  - recall / remember / log_message round-trips incl. per-user privacy
  - a rule override round-trip (set_rule -> v_rca_due; T350 only, manual kept)

Run:  pytest tests/          (or: python -m pytest tests/)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from pathlib import Path

import mcp as mcp_sdk  # the installed SDK — conftest removed the local shadow

assert "site-packages" in str(mcp_sdk.__file__), (
    f"import mcp resolved to {mcp_sdk.__file__} — the local mcp/ folder is "
    "shadowing the installed SDK; run pytest from the repo root")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
SERVER = REPO / "mcp" / "server.py"

U_JAKE, U_MICHAEL, U_JESSICA = "U-102", "U-201", "U-202"


# ------------------------------------------------------------- plumbing


@contextlib.asynccontextmanager
async def _session(db_path: Path):
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER), "--db", str(db_path)],
        cwd=str(REPO),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def run(db_path: Path, scenario):
    """Run one async scenario against a freshly spawned server."""
    async def main():
        async with _session(db_path) as session:
            return await scenario(session)
    return asyncio.run(main())


def _text(res) -> str:
    return "\n".join(getattr(b, "text", "") for b in res.content)


def _payload(res):
    if getattr(res, "structured_content", None) is not None:
        return res.structured_content
    return json.loads(_text(res))


async def call(session, name, args=None):
    res = await session.call_tool(name, args or {})
    assert not res.is_error, f"{name} failed: {_text(res)}"
    return _payload(res)


async def fail(session, name, args=None) -> str:
    res = await session.call_tool(name, args or {})
    assert res.is_error, f"{name} should have been rejected but succeeded"
    return _text(res)


# ----------------------------------------------------------------- tests


def test_tool_surface_and_prompts(db_copy):
    async def scenario(session):
        tools = (await session.list_tools()).tools
        names = {t.name for t in tools}
        assert names == {"query_db", "list_tables", "describe", "get_doc",
                         "get_report", "recall", "record_correction", "remember",
                         "set_rule", "log_message"}
        read_only = {"query_db", "list_tables", "describe", "get_doc",
                     "get_report", "recall"}
        for t in tools:
            assert t.annotations is not None, t.name
            assert t.annotations.read_only_hint is (t.name in read_only), t.name

        prompts = {p.name for p in (await session.list_prompts()).prompts}
        assert prompts == {"copilot_system_prompt", "routing_ladder",
                           "answer_protocol"}
        p = await session.get_prompt("copilot_system_prompt")
        text = p.messages[0].content.text
        assert "Answer protocol" in text and "Routing ladder" in text
        assert "record_correction" in text and "meta.as_of" in text
    run(db_copy, scenario)


def test_read_paths_match_gold(db_copy):
    async def scenario(session):
        tables = await call(session, "list_tables")
        assert "v_producing_now" in tables["views"]
        assert "wells" in tables["tables"]
        ds = {d["dataset_id"]: d for d in tables["datasets"]}
        assert ds["sample"]["as_of"] == "2026-10-16"

        d = await call(session, "describe", {"name": "v_spills"})
        assert d["kind"] == "view"
        assert {c["name"] for c in d["columns"]} >= {
            "inspection_id", "asset_id", "est_volume_bbl", "spill_date"}
        assert "effective" in d["note"]

        facts = await call(session, "describe", {"name": "facts"})
        assert facts["kind"] == "table" and facts["row_count"] == 0
        err = await fail(session, "describe", {"name": "nope"})
        assert "no table or view" in err

        # Q1 — WELL-0001: not producing, last inspected 15 Oct (INS-0001-0203)
        q1 = await call(session, "query_db", {"sql":
            "SELECT asset_id, is_producing, production_threshold_c, "
            "       latest_inspection_id, eff_temp_delta_c, context_reason, "
            "       open_repair_reason "
            "FROM v_producing_now "
            "WHERE dataset_id='sample' AND asset_id='WELL-0001'"})
        row = q1["rows"][0]
        assert row["is_producing"] == 0
        assert row["production_threshold_c"] == 15.0
        assert row["latest_inspection_id"] == "INS-0001-0203"
        assert abs(row["eff_temp_delta_c"] - 3.2) < 1e-9
        assert "CTX-0001-003" in row["context_reason"]
        assert row["open_repair_reason"] is None

        # Q4 — 6 spills / 15.1 bbl; the corrected-away detection is gone
        q4 = await call(session, "query_db", {"sql":
            "SELECT COUNT(*) AS n, ROUND(SUM(est_volume_bbl),1) AS bbl "
            "FROM v_spills WHERE dataset_id='sample' AND asset_id='WELL-0001'"})
        assert q4["rows"][0]["n"] == 6
        assert abs(q4["rows"][0]["bbl"] - 15.1) < 0.05
        gone = await call(session, "query_db", {"sql":
            "SELECT COUNT(*) AS n FROM v_spills "
            "WHERE dataset_id='sample' AND inspection_id='INS-0001-0070'"})
        assert gone["rows"][0]["n"] == 0

        # Q10 — WELL-0082 containment ≈ 7.1 h, resolved + returned by id
        rep = await call(session, "get_report", {"maintenance_id": "MNT-0082-028"})
        assert rep["asset_id"] == "WELL-0082"
        assert rep["triggered_by_inspection_id"] == "INS-0082-0198"
        assert abs(rep["report_facts"]["contained_hours_after"] - 7.1) < 0.01
        assert "7.1" in rep["content"]

        # scheduled jobs carry no report; unknown ids are corrective errors
        err = await fail(session, "get_report", {"maintenance_id": "MNT-0007-003"})
        assert "no report file" in err and "corrective" in err
        err = await fail(session, "get_report", {"maintenance_id": "MNT-9999-999"})
        assert "not a maintenance id" in err

        # docs come from the catalog, by path
        doc = await call(session, "get_doc", {"path": "fleet/sops/spill-response-sop.md"})
        assert doc["doc_type"] == "sop" and "SR-01" in doc["content"]

        # the 50-row cap nudges toward WHERE/LIMIT instead of skimming
        wide = await call(session, "query_db", {"sql":
            "SELECT * FROM v_spills WHERE dataset_id='sample'"})
        assert wide["rowcount"] == 50 and wide["truncated"] is True
        assert "WHERE" in wide["hint"] or "LIMIT" in wide["hint"]

        # empty result = honest "not in the data", never padded
        empty = await call(session, "query_db", {"sql":
            "SELECT * FROM v_spills WHERE dataset_id='sample' "
            "AND asset_id='WELL-9999'"})
        assert empty["rowcount"] == 0 and "not in the data" in empty["hint"]
    run(db_copy, scenario)


def test_read_only_rejections(db_copy):
    async def scenario(session):
        cases = [
            ("INSERT INTO wells(dataset_id, asset_id) VALUES ('x','y')",
             "must start with SELECT"),
            ("SELECT 1; SELECT 2", "multiple statements"),
            ("WITH x AS (SELECT 1) INSERT INTO wells SELECT * FROM x",
             "data-changing keyword"),
        ]
        for sql, needle in cases:
            err = await fail(session, "query_db", {"sql": sql})
            assert needle in err, (sql, err)

        # semicolons and write words inside literals must NOT trip the guard
        ok = await call(session, "query_db",
                        {"sql": "SELECT ';' AS s, 'insert' AS w"})
        assert ok["rows"][0] == {"s": ";", "w": "insert"}

        # only catalog paths are readable; escapes never reach the disk
        err = await fail(session, "get_doc", {"path": "../../etc/passwd"})
        assert "not in the documents catalog" in err
    run(db_copy, scenario)


def test_correction_round_trip(db_copy):
    async def scenario(session):
        # the sanity check refuses a wrong original (and names the live value)
        err = await fail(session, "record_correction", {
            "field": "wellhead_temp_c", "original_value": "99.0",
            "corrected_value": "41.0", "reason": "faulty gun",
            "inspection_id": "INS-0164-0205"})
        assert "mismatch" in err and "24.0" in err

        # B12: the faulty-gun correction flips WELL-0164 to producing
        out = await call(session, "record_correction", {
            "field": "wellhead_temp_c", "original_value": "24.0",
            "corrected_value": "41.0",
            "reason": "faulty thermal gun; field crew re-measured",
            "inspection_id": "INS-0164-0205", "author_user_id": U_MICHAEL})
        assert out["correction_id"] == "COR-RT-0001"
        assert out["status"] == "applied" and out["scope"] == "inspection"
        assert out["echo"]["v_producing_now"][0]["is_producing"] == 1

        # the view reflects it on the next read (read-time application)
        now = await call(session, "query_db", {"sql":
            "SELECT eff_wellhead_temp_c, eff_temp_delta_c, is_producing "
            "FROM v_producing_now "
            "WHERE dataset_id='sample' AND asset_id='WELL-0164'"})
        row = now["rows"][0]
        assert row["eff_wellhead_temp_c"] == 41.0
        assert abs(row["eff_temp_delta_c"] - 21.1) < 0.05
        assert row["is_producing"] == 1

        # the raw row is never touched — original_value is the audit anchor
        raw = await call(session, "query_db", {"sql":
            "SELECT wellhead_temp_c FROM inspections "
            "WHERE dataset_id='sample' AND inspection_id='INS-0164-0205'"})
        assert raw["rows"][0]["wellhead_temp_c"] == 24.0

        # runtime-row contract (ingest/README.md): dataset_id NULL, valid_from NULL
        c = await call(session, "query_db", {"sql":
            "SELECT dataset_id, source, valid_from, status FROM corrections "
            "WHERE correction_id='COR-RT-0001'"})
        assert c["rows"][0] == {"dataset_id": None, "source": "runtime",
                                "valid_from": None, "status": "applied"}
    run(db_copy, scenario)


def test_memory_round_trips_and_privacy(db_copy):
    async def scenario(session):
        # shared fact (B16): every user sees it, attributed to its author
        f = await call(session, "remember", {
            "text": "WELL-0007 will be shut in from 17 Oct for a 10-day "
                    "planned workover.",
            "scope": "well", "well_id": "WELL-0007", "user_id": U_JAKE})
        assert f["recorded"] == "fact" and f["id"] == "FACT-0001"
        assert f["author_name"] == "Jake Morales" and f["visibility"] == "shared"

        r = await call(session, "recall", {"well_id": "WELL-0007"})
        assert len(r["facts"]) == 1
        assert r["facts"][0]["author_name"] == "Jake Morales"
        r = await call(session, "recall",
                       {"well_id": "WELL-0007", "user_id": U_JESSICA})
        assert len(r["facts"]) == 1  # facts are shared, not per-user

        # unconfirmed claim (B17): surfaced as a disagreement, never truth
        cl = await call(session, "remember", {
            "text": "WELL-0079 is running fine.",
            "scope": "claim", "well_id": "WELL-0079", "user_id": U_MICHAEL})
        assert cl["recorded"] == "claim" and cl["visibility"] == "unconfirmed"
        r = await call(session, "recall", {"well_id": "WELL-0079"})
        assert [c["status"] for c in r["claims"]] == ["unconfirmed"]

        # private memory: only its owner ever gets it back
        m = await call(session, "remember", {
            "text": "I'm watching WELL-0084 this week.",
            "scope": "memory", "well_id": "WELL-0084", "user_id": U_MICHAEL})
        assert m["recorded"] == "memory" and m["visibility"] == "private"
        mine = await call(session, "recall",
                          {"user_id": U_MICHAEL, "well_id": "WELL-0084"})
        assert any("watching" in x["text"] for x in mine["memories"])
        hers = await call(session, "recall",
                          {"user_id": U_JESSICA, "well_id": "WELL-0084"})
        assert hers["memories"] == []

        # conversation memory per user (B11): "the wells we discussed"
        await call(session, "log_message", {
            "session_id": "S-MICHAEL-1", "user_id": U_MICHAEL, "role": "user",
            "content": "Top 2 downtime wells in Southwest Block 24?",
            "referenced_wells": ["WELL-0084", "WELL-0069"]})
        await call(session, "log_message", {
            "session_id": "S-MICHAEL-1", "user_id": U_MICHAEL,
            "role": "assistant",
            "content": "WELL-0084 (42 d) and WELL-0069 (35 d) ...",
            "referenced_wells": ["WELL-0084", "WELL-0069"]})
        await call(session, "log_message", {
            "session_id": "S-JESSICA-1", "user_id": U_JESSICA, "role": "user",
            "content": "How many spills at WELL-0101 last year?",
            "referenced_wells": ["WELL-0101"]})

        conv = await call(session, "recall", {"user_id": U_MICHAEL})
        assert conv["conversation"]["discussed_wells_recent_first"] == \
            ["WELL-0084", "WELL-0069"]
        assert len(conv["conversation"]["recent_messages"]) == 2

        her = await call(session, "recall", {"user_id": U_JESSICA})
        assert her["conversation"]["discussed_wells_recent_first"] == ["WELL-0101"]
        assert all(m["session_id"] == "S-JESSICA-1"
                   for m in her["conversation"]["recent_messages"])
    run(db_copy, scenario)


def test_rule_override_round_trip(db_copy):
    # benchmark B14: T350 wells at exactly 2 pump-jack repairs that must flip...
    T350_2 = ["WELL-0004", "WELL-0013", "WELL-0021", "WELL-0055", "WELL-0079",
              "WELL-0093", "WELL-0120", "WELL-0183", "WELL-0189"]

    async def scenario(session):
        base = await call(session, "query_db", {"sql":
            "SELECT value FROM rules WHERE dataset_id='sample' "
            "AND parameter='rca_after_n_repairs'"})
        assert [r["value"] for r in base["rows"]] == ["3"]  # the manual's value

        # B14: "for all T350 wells: RCA after 2 repairs, not 3"
        out = await call(session, "set_rule", {
            "parameter": "rca_after_n_repairs", "value": "2",
            "applies_to": "T350", "author_user_id": U_MICHAEL,
            "reason": "team policy"})
        assert out["applies_to"] == "T350"
        assert out["written"][0]["dataset_id"] == "sample"
        assert "v_rca_due" in out["echo"]

        # the T350 wells at exactly 2 now need RCA ...
        q = await call(session, "query_db", {"sql":
            "SELECT asset_id, rca_after_n_repairs, rca_due FROM v_rca_due "
            "WHERE dataset_id='sample' AND well_type='T350' "
            "AND equipment_kind='pump_jack' AND corrective_count_window=2 "
            "ORDER BY asset_id"})
        assert [r["asset_id"] for r in q["rows"]] == T350_2
        assert all(r["rca_due"] == 1 and r["rca_after_n_repairs"] == 2
                   for r in q["rows"])

        # ... while T200 wells still follow the manual's 3 (WELL-0102-style trap)
        q = await call(session, "query_db", {"sql":
            "SELECT COUNT(*) AS due FROM v_rca_due "
            "WHERE dataset_id='sample' AND well_type='T200' "
            "AND equipment_kind='pump_jack' AND corrective_count_window=2 "
            "AND rca_due=1"})
        assert q["rows"][0]["due"] == 0

        # the manual's original row is kept; the override is the runtime row
        rules = await call(session, "query_db", {"sql":
            "SELECT value, is_overridden, source_doc FROM rules "
            "WHERE dataset_id='sample' AND parameter='rca_after_n_repairs' "
            "ORDER BY is_overridden"})
        assert rules["rows"][0]["value"] == "3" and rules["rows"][0]["is_overridden"] == 0
        assert rules["rows"][1] == {"value": "2", "is_overridden": 1,
                                    "source_doc": "runtime"}

        err = await fail(session, "set_rule",
                         {"parameter": "not_a_rule", "value": "1"})
        assert "unknown rule parameter" in err
    run(db_copy, scenario)
