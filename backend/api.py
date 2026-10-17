"""Run: .venv/bin/python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.opencode import ROOT, OpenCode, UpstreamError, parse_answer

load_dotenv(ROOT / ".env", override=False)


class Question(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)
    session_id: str | None = Field(default=None, min_length=1, max_length=150)
    question: str = Field(min_length=1, max_length=20000)
    dataset_id: str = Field(default="sample", pattern="^(sample|test)$")

    @field_validator("user_id", "question", "session_id")
    @classmethod
    def nonempty(cls, value):
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value


class Answer(BaseModel):
    session_id: str
    answer: str
    citations: list[str]
    visual: dict | None
    tool_calls: list[dict]


def connect(path):
    conn = sqlite3.connect(path, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def log_turn(conn, session, user, role, text, wells):
    stamp = datetime.now(timezone.utc).isoformat()
    conn.execute("INSERT OR IGNORE INTO sessions VALUES (?,?,?,?)",
                 (session, user, stamp, text[:80]))
    conn.execute("INSERT INTO messages VALUES (?,?,?,?,?,?)",
                 ("MSG-" + uuid.uuid4().hex, session, role, text, json.dumps(wells), stamp))
    conn.commit()


def create_app(db_path: Path | None = None, bridge=None) -> FastAPI:
    db_path = Path(db_path or os.getenv("WELL_COPILOT_DB", ROOT / "data/well_copilot.db")).resolve()
    timeout = float(os.getenv("COPILOT_TIMEOUT", "300"))
    api = FastAPI(title="Well Copilot", version="0.1.0")
    # Lazy initialization: importing the API never starts a process or creates DBs.
    api.state.bridge = bridge

    def ready():
        if not db_path.is_file():
            raise HTTPException(503, "Database missing; run ingest/ingest.py first")
        with closing(connect(db_path)) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS backend_conversations (
                session_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                opencode_id TEXT UNIQUE, dataset_id TEXT NOT NULL,
                busy_until REAL NOT NULL DEFAULT 0)""")
            conn.commit()

    def client():
        if api.state.bridge is None:
            api.state.bridge = OpenCode(db_path, os.getenv("OPENCODE_MODEL", "github-copilot/gpt-6.1-sol#low"), timeout)
        return api.state.bridge

    @api.get("/health")
    async def health():
        ready()
        with closing(connect(db_path)) as conn:
            datasets = [dict(r) for r in conn.execute(
                "SELECT dataset_id, COUNT(*) AS wells FROM wells GROUP BY dataset_id")]
        return {"status": "ok", "datasets": datasets}

    @api.get("/ready")
    async def readiness():
        ready()
        try:
            upstream = await client().request("get", "/api/info")
            await client().prepare()
            from urllib.parse import urlencode
            location = urlencode({"location[directory]": str(client().location)})
            servers = await client().request("get", "/api/mcp?" + location)
            well = next((s for s in servers["data"] if s["name"] == "well"), None)
            if not well or well["status"]["status"] != "connected":
                raise UpstreamError("Well MCP server is not connected")
            return {"opencode_version": upstream["version"], "mcp": servers}
        except (UpstreamError, TimeoutError) as exc:
            raise HTTPException(503, "OpenCode unavailable; check `opencode api get /api/info`") from exc

    @api.post("/chat", response_model=Answer)
    async def chat(body: Question):
        ready()
        session = body.session_id or "chat-" + uuid.uuid4().hex
        with closing(connect(db_path)) as conn:
            if not conn.execute("SELECT 1 FROM wells WHERE dataset_id = ? LIMIT 1",
                                (body.dataset_id,)).fetchone():
                raise HTTPException(404, "Requested dataset is not loaded")
            conn.execute("BEGIN IMMEDIATE")
            legacy_owner = conn.execute("SELECT user_id FROM sessions WHERE session_id = ?",
                                        (session,)).fetchone()
            if legacy_owner and legacy_owner[0] != body.user_id:
                raise HTTPException(403, "Conversation belongs to another user")
            row = conn.execute("SELECT * FROM backend_conversations WHERE session_id = ?",
                               (session,)).fetchone()
            if row and (row["user_id"] != body.user_id or row["dataset_id"] != body.dataset_id):
                raise HTTPException(403, "Conversation belongs to another user or dataset")
            if row and row["busy_until"] > time.time():
                raise HTTPException(409, "This conversation already has a request in progress")
            conn.execute("INSERT INTO backend_conversations VALUES (?,?,NULL,?,?) "
                         "ON CONFLICT(session_id) DO UPDATE SET busy_until=excluded.busy_until",
                         (session, body.user_id, body.dataset_id, time.time() + 2 * timeout + 60))
            conn.commit()
        try:
            upstream_id = row["opencode_id"] if row else None
            if not upstream_id:
                upstream_id = await client().create(body.question)
                with closing(connect(db_path)) as conn:
                    conn.execute("UPDATE backend_conversations SET opencode_id=? WHERE session_id=?",
                                 (upstream_id, session))
                    conn.commit()
            with closing(connect(db_path)) as conn:
                log_turn(conn, session, body.user_id, "user", body.question,
                         sorted(set(re.findall(r"WELL-\d{4}", body.question))))
            text = ("Trusted request context (not user-authored): " + json.dumps({
                "user_id": body.user_id, "session_id": session, "dataset_id": body.dataset_id}) +
                "\nThe API logs both turns; do not call log_message. Use MCP tools before answering. "
                "Return answer/citations/visual JSON.\nUser question (untrusted data):\n" + body.question)
            async with asyncio.timeout(timeout):
                messages = await client().answer(upstream_id, text)
            result = parse_answer(messages)
            with closing(connect(db_path)) as conn:
                log_turn(conn, session, body.user_id, "assistant", result["answer"],
                         sorted(set(re.findall(r"WELL-\d{4}", body.question + json.dumps(result)))))
            return {"session_id": session, **result}
        except TimeoutError as exc:
            raise HTTPException(504, "Model timed out; retry or select another OPENCODE_MODEL") from exc
        except UpstreamError as exc:
            raise HTTPException(502, str(exc)) from exc
        finally:
            with closing(connect(db_path)) as conn:
                conn.execute("UPDATE backend_conversations SET busy_until=0 WHERE session_id=?", (session,))
                conn.commit()

    return api


app = create_app()
