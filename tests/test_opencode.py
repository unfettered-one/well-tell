"""V2 session protocol tests without invoking a paid/free model."""

import asyncio
import json

import pytest

from backend.opencode import OpenCode, UpstreamError, parse_answer


def test_v2_create_model_and_private_config(tmp_path):
    class Stub(OpenCode):
        async def request(self, method, path, body=None):
            self.sent = (method, path, body)
            if path.startswith("/api/mcp"):
                return {"data": [{"name": "well", "status": {"status": "connected"}}]}
            return {"data": {"id": "ses_created"}}

    bridge = Stub(tmp_path / "db.sqlite", "github-copilot/gpt-6.1-sol#low")
    assert asyncio.run(bridge.create("question")) == "ses_created"
    assert bridge.sent[1] == "/api/session"
    assert bridge.sent[2]["model"] == {"providerID": "github-copilot", "id": "gpt-6.1-sol", "variant": "low"}
    config = json.loads((bridge.location / "opencode.json").read_text())
    assert "--require-session" in config["mcp"]["servers"]["well"]["command"]
    assert config["mcp"]["servers"]["well"]["codemode"] is False
    assert config["snapshots"] is False
    assert "Output contract" in config["agents"]["copilot"]["system"]


def test_turn_pagination_excludes_previous_answers(tmp_path):
    class Stub(OpenCode):
        async def request(self, method, path, body=None):
            if path.startswith("/api/mcp"):
                return {"data": [{"name": "well", "status": {"status": "connected"}}]}
            if path.endswith("/prompt"):
                assert body == {"text": "question"}
                return {"data": {"id": "current-user"}}
            if path.endswith("/wait"):
                return None
            if "cursor=" in path:
                return {"data": [{"id": "tool"}, {"id": "current-user"}, {"id": "old-answer"}],
                        "cursor": {"next": None}}
            return {"data": [{"id": "latest-answer"}], "cursor": {"next": "opaque/+="}}

    bridge = Stub(tmp_path / "db.sqlite", "provider/model")
    assert asyncio.run(bridge.answer("ses_1", "question")) == [{"id": "tool"}, {"id": "latest-answer"}]


def test_missing_current_turn_is_not_previous_response(tmp_path):
    class Stub(OpenCode):
        async def request(self, method, path, body=None):
            if path.startswith("/api/mcp"):
                return {"data": [{"name": "well", "status": {"status": "connected"}}]}
            if path.endswith("/prompt"):
                return {"data": {"id": "current-user"}}
            if path.endswith("/wait"):
                return None
            return {"data": [{"id": "old-answer"}], "cursor": {"next": None}}
    with pytest.raises(UpstreamError, match="admitted"):
        asyncio.run(Stub(tmp_path / "db.sqlite", "provider/model").answer("ses_1", "question"))


def test_missing_recall_is_not_silently_accepted():
    messages = [{"type": "assistant", "content": [
        {"type": "tool", "name": "well_query_db", "state": {
            "status": "completed", "content": [{"type": "text", "text": "{}"}]}},
        {"type": "text", "text": '{"answer":"x","citations":[],"visual":null}'},
    ]}]
    with pytest.raises(UpstreamError, match="recall"):
        parse_answer(messages)


def test_cold_start_waits_for_mcp_catalog_before_model_creation(tmp_path):
    class Cold(OpenCode):
        calls = 0

        async def request(self, method, path, body=None):
            if path.startswith("/api/mcp"):
                self.calls += 1
                if self.calls == 1:
                    return {"data": []}
                return {"data": [{"name": "well", "status": {"status": "connected"}}]}
            assert self.calls == 2
            return {"data": {"id": "ses_ready"}}

    bridge = Cold(tmp_path / "db.sqlite", "provider/model")
    assert asyncio.run(bridge.create("question")) == "ses_ready"


def test_failed_mcp_does_not_start_a_model(tmp_path):
    class Failed(OpenCode):
        async def request(self, method, path, body=None):
            assert path.startswith("/api/mcp")
            return {"data": [{"name": "well", "status": {"status": "failed"}}]}

    with pytest.raises(UpstreamError, match="failed to connect"):
        asyncio.run(Failed(tmp_path / "db.sqlite", "provider/model").create("question"))
