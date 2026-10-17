"""Offline tests of the real HTTP bridge contract; live model tests are eval.py."""

import asyncio
import json
import sqlite3

import httpx
import pytest

from backend.api import create_app
from backend.opencode import UpstreamError, parse_answer


def turn(answer="Not producing: INS-0001-0203", citations=None):
    return [{"id": "a", "type": "assistant", "content": [
        {"type": "tool", "name": "well_recall", "state": {
            "status": "completed", "content": [{"type": "text", "text": "{}"}]}},
        {"type": "tool", "name": "well_query_db", "state": {
            "status": "completed", "content": [{"type": "text", "text":
                '{"inspection_id":"INS-0001-0203","is_producing":0}'}]}},
        {"type": "text", "text": json.dumps({"answer": answer,
            "citations": citations if citations is not None else ["INS-0001-0203"], "visual": None})},
    ]}]


class FakeOpenCode:
    def __init__(self):
        self.created, self.prompts = [], []

    async def create(self, title):
        session = "ses_test_" + str(len(self.created))
        self.created.append(session)
        return session

    async def answer(self, session, text):
        self.prompts.append((session, text))
        return turn()


def test_http_sessions_logging_privacy_and_restart(db_copy):
    with sqlite3.connect(db_copy) as conn:
        test_dataset_loaded = conn.execute(
            "SELECT 1 FROM wells WHERE dataset_id='test' LIMIT 1").fetchone() is not None

    async def scenario():
        bridge = FakeOpenCode()
        app = create_app(db_copy, bridge)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.get("/health")).status_code == 200
            body = {"user_id": "U-201", "question": "Is WELL-0001 producing?"}
            first = await client.post("/chat", json=body)
            assert first.status_code == 200, first.text
            session = first.json()["session_id"]
            body["session_id"] = session
            assert (await client.post("/chat", json=body)).status_code == 200
            assert len(bridge.created) == 1
            assert all(p[0] == bridge.created[0] for p in bridge.prompts)
            assert '"dataset_id": "sample"' in bridge.prompts[0][1]
            body["user_id"] = "U-202"
            assert (await client.post("/chat", json=body)).status_code == 403
            body["user_id"] = "U-201"
            body["dataset_id"] = "test"
            # If present, the test dataset is loaded but the existing sample
            # conversation cannot be switched in place; otherwise it is absent.
            expected = 403 if test_dataset_loaded else 404
            assert (await client.post("/chat", json=body)).status_code == expected
            assert (await client.post("/chat", json={"user_id": "a", "question": "  "})).status_code == 422
        # Fresh API instance reuses the durable mapping.
        bridge2 = FakeOpenCode()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(db_copy, bridge2)), base_url="http://test") as client:
            body.update(user_id="U-201", dataset_id="sample")
            assert (await client.post("/chat", json=body)).status_code == 200
            assert bridge2.created == []
        with sqlite3.connect(db_copy) as conn:
            assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 6
            assert conn.execute("SELECT busy_until FROM backend_conversations").fetchone()[0] == 0
    asyncio.run(scenario())


def test_api_failure_releases_session(db_copy):
    class Broken(FakeOpenCode):
        async def answer(self, *_):
            raise UpstreamError("Provider unavailable")

    async def scenario():
        app = create_app(db_copy, Broken())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            body = {"user_id": "U-201", "session_id": "retry", "question": "WELL-0001?"}
            assert (await client.post("/chat", json=body)).status_code == 502
            app.state.bridge = FakeOpenCode()
            assert (await client.post("/chat", json=body)).status_code == 200
            with sqlite3.connect(db_copy) as conn:
                conn.execute("UPDATE backend_conversations SET busy_until=9999999999")
            assert (await client.post("/chat", json=body)).status_code == 409
    asyncio.run(scenario())


def test_answer_validation():
    assert parse_answer(turn())["citations"] == ["INS-0001-0203"]
    with pytest.raises(UpstreamError, match="evidence not returned"):
        parse_answer(turn(citations=["INVENTED"]))
    with pytest.raises(UpstreamError, match="successfully call"):
        parse_answer([{ "type": "assistant", "content": [{"type": "text", "text": "fake"}]}])
    with pytest.raises(UpstreamError, match="run failed"):
        parse_answer([{"outcome": "failed", "error": {"message": "rate limit"}}])


def test_missing_db(tmp_path):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(tmp_path / "missing.db")), base_url="http://test") as client:
            assert (await client.get("/health")).status_code == 503
    asyncio.run(scenario())


def test_chart_only_wells_are_logged_for_future_recall(db_copy):
    class ChartOnly(FakeOpenCode):
        async def answer(self, *_):
            messages = turn("The wells are shown in the chart.")
            messages[0]["content"][1]["state"]["content"][0]["text"] += ' WELL-0121'
            text = messages[0]["content"][-1]
            data = json.loads(text["text"])
            data["visual"] = {"type": "bar", "data": [{"asset_id": "WELL-0121", "days": 49}]}
            text["text"] = json.dumps(data)
            return messages

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(db_copy, ChartOnly())), base_url="http://test") as client:
            response = await client.post("/chat", json={"user_id": "U-201", "question": "Which well had most downtime?"})
            assert response.status_code == 200, response.text
            with sqlite3.connect(db_copy) as conn:
                wells = conn.execute("SELECT referenced_wells_json FROM messages WHERE role='assistant'").fetchone()[0]
                assert "WELL-0121" in json.loads(wells)
    asyncio.run(scenario())


def test_legacy_mcp_session_cannot_be_taken_over(db_copy):
    with sqlite3.connect(db_copy) as conn:
        conn.execute("INSERT INTO sessions VALUES ('old-mcp-session','U-202','2026-10-17','private')")

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(db_copy, FakeOpenCode())), base_url="http://test") as client:
            response = await client.post("/chat", json={"user_id": "U-201", "session_id": "old-mcp-session", "question": "Hello"})
            assert response.status_code == 403
    asyncio.run(scenario())
