#!/usr/bin/env python3
"""Live natural-language checks beyond the original 18 scenarios.

Uses a disposable SQLite backup and independent SQL expectations, never places
expected numbers in the model prompt. Saves answers AND executed query evidence.
This checks selected observable properties, not complete semantic entailment.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path

import httpx

from backend.api import create_app


def readonly_connection(path: Path):
    # A fresh WAL backup may need SQLite to create its -shm file. mode=rw
    # permits that bookkeeping but cannot create a missing DB; query_only
    # rejects all data writes on this independent reference connection.
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=rw", uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def reference_counts(path: Path, dataset: str) -> dict:
    """Independent, read-only reference for the words completed/recorded/service."""
    with closing(readonly_connection(path)) as conn:
        row = conn.execute("SELECT value FROM meta WHERE key=?", ("as_of_" + dataset,)).fetchone()
        if not row:
            raise ValueError(f"No evaluation date for dataset {dataset}")
        cutoff = row[0]
        counts = {"as_of": cutoff}
        for label, kind, completed in [
            ("completed_repairs", "corrective", True),
            ("recorded_repairs", "corrective", False),
            ("completed_services", "scheduled", True),
        ]:
            sql = "SELECT COUNT(DISTINCT maintenance_id) FROM maintenance WHERE dataset_id=? AND maintenance_type=?"
            params = [dataset, kind]
            if completed:
                sql += " AND completed_at IS NOT NULL AND date(completed_at)<=?"
                params.append(cutoff)
            else:
                sql += " AND date(started_at)<=?"
                params.append(cutoff)
            counts[label] = conn.execute(sql, params).fetchone()[0]
        return counts


def numbers(value):
    if isinstance(value, dict):
        return [n for v in value.values() for n in numbers(v)]
    if isinstance(value, list):
        return [n for v in value for n in numbers(v)]
    return [value] if isinstance(value, (int, float)) and not isinstance(value, bool) else []


def check_response(data: dict, expected: int | None, queries: list[dict], clarify=False) -> list[str]:
    errors = []
    tools = data.get("tool_calls", [])
    if not any(t["name"] == "well_recall" and t["status"] == "completed" for t in tools):
        errors.append("missing successful recall")
    if any(t["name"] in {"well_remember", "well_set_rule", "well_record_correction"} for t in tools):
        errors.append("read-only question caused a domain write")
    if clarify:
        if "?" not in data.get("answer", ""):
            errors.append("did not ask a clarification question")
        if data.get("visual") is not None:
            errors.append("presented a visual before resolving ambiguity")
        if re.search(r"\b(?:there are|total(?:\s+of)?)\s+\*{0,2}\d|\b\d[\d,]*\s+(?:repair jobs|jobs|wells|categories)\b",
                     data.get("answer", ""), re.I):
            errors.append("asserted numbers before resolving ambiguity")
        return errors
    if expected is None:
        if not any(t["name"] == "well_get_report" and t["status"] == "completed" for t in tools):
            errors.append("repair-activity explanation did not read a report")
        if not queries:
            errors.append("repair-activity explanation did not query records")
        if not any(c.startswith("MNT-") for c in data.get("citations", [])):
            errors.append("repair-activity explanation lacks maintenance/report citations")
        # This verifies report-backed investigation, not an exhaustive taxonomy.
        return errors
    answer = data.get("answer", "").replace(",", "")
    if not re.search(rf"(?<!\d){expected}(?!\d)", answer):
        errors.append(f"answer does not state expected count {expected}")
    # A guessed number alone cannot pass: a successful SQL tool result must
    # contain the independently computed count, and it must have aggregated.
    supported = any(expected in numbers(q["result"]) and re.search(r"\bcount\s*\(", q["sql"], re.I)
                    for q in queries)
    if not supported:
        errors.append("expected count not supported by a successful aggregate query")
    return errors


async def query_evidence(app, path: Path, session: str) -> list[dict]:
    with closing(sqlite3.connect(path)) as conn:
        upstream = conn.execute("SELECT opencode_id FROM backend_conversations WHERE session_id=?", (session,)).fetchone()[0]
    # The new independent conversations/short clarification pair fit one page.
    page = await app.state.bridge.request("get", f"/api/session/{upstream}/message?order=desc&limit=100")
    current = []
    for message in page["data"]:
        if message.get("type") == "user":
            break
        current.append(message)
    queries = []
    for message in reversed(current):
        for part in message.get("content", []):
            state = part.get("state", {})
            if part.get("name") != "well_query_db" or state.get("status") != "completed":
                continue
            for content in state.get("content", []):
                try:
                    payload = json.loads(content.get("text", ""))
                except ValueError:
                    continue
                queries.append({"sql": state.get("input", {}).get("sql", ""), "result": payload})
    return queries


async def run(args):
    source = Path(args.db).resolve()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    copy = output.parent / ("interpretation-" + uuid.uuid4().hex[:12] + ".db")
    with closing(readonly_connection(source)) as src, closing(sqlite3.connect(copy)) as dst:
        src.backup(dst)
    expected = reference_counts(copy, args.dataset)
    app = create_app(copy)
    user = "interpretation-eval-" + uuid.uuid4().hex[:12]
    results = []
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://copilot", timeout=None) as client:
        async def ask(name, question, metric=None, clarify=False, session=None):
            body = {"user_id": user, "question": question, "dataset_id": args.dataset}
            if session:
                body["session_id"] = session
            response = await client.post("/chat", json=body)
            data = response.json()
            queries = await query_evidence(app, copy, data["session_id"]) if response.status_code == 200 else []
            errors = check_response(data, expected[metric] if metric else None, queries, clarify) if response.status_code == 200 else ["HTTP request failed"]
            result = {"case": name, "question": question, "passed": not errors,
                      "errors": errors, "expected": expected.get(metric),
                      "status": response.status_code, "response": data, "queries": queries}
            results.append(result)
            output.write_text(json.dumps({"database": str(copy), "reference": expected, "results": results}, indent=2))
            print(json.dumps(result), flush=True)
            return data.get("session_id")

        await ask("completed_repairs", "How many total repair jobs have been done across all wells?", "completed_repairs")
        await ask("recorded_repairs", "How many corrective repair jobs are on record, including unfinished ones?", "recorded_repairs")
        await ask("completed_services", "How many scheduled maintenance jobs have been completed?", "completed_services")
        await ask("unclear_types", "How many types of repairs happen across all wells?", clarify=True)
        session = await ask("unclear_measure", "How many types are there?", clarify=True)
        if session:
            await ask("clarification_followup", "I mean the total number of completed corrective repair jobs across all wells, not a count of categories.", "completed_repairs", session=session)
        await ask("actual_activities", "What kinds of actual repair work have been performed across the wells? Give examples from the reports.")
    print(f"{sum(r['passed'] for r in results)}/{len(results)} interpretation checks passed", flush=True)
    return bool(results) and all(r["passed"] for r in results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/well_copilot.db", help="Source DB; live calls use a disposable backup")
    parser.add_argument("--dataset", default="sample", choices=["sample", "test"])
    parser.add_argument("--output", default="data/interpretation-results.json")
    raise SystemExit(0 if asyncio.run(run(parser.parse_args())) else 1)
