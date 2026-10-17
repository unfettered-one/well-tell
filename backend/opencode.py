"""Authenticated OpenCode V2 API access via its supported CLI transport.

No hardcoded server port, reading credential files, or V1 prompt endpoints.
Each API application gets a dedicated location/config pointing to its DB.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class UpstreamError(RuntimeError):
    pass


class OpenCode:
    def __init__(self, db: Path, model: str, timeout: float = 300):
        self.model = model
        self.timeout = timeout
        self._prepared = False
        self.location = db.parent / (db.stem + "_opencode")
        self.location.mkdir(parents=True, exist_ok=True)
        config = json.loads((ROOT / "opencode.json").read_text())
        config["snapshots"] = False
        config["agents"]["copilot"]["system"] = (ROOT / "backend/agent.md").read_text()
        config["mcp"]["servers"]["well"]["command"] = [
            sys.executable, str(ROOT / "mcp/server.py"), "--db", str(db),
            "--require-session",
            # A source revision changes the MCP config when code changes, so
            # OpenCode cannot silently keep an old server process after a fix.
            "--revision", hashlib.sha256(b"".join(
                p.read_bytes() for p in sorted((ROOT / "mcp").glob("*.py"))
            )).hexdigest()[:12],
        ]
        config["mcp"]["servers"]["well"]["cwd"] = str(ROOT)
        (self.location / "opencode.json").write_text(json.dumps(config, indent=2))

    async def request(self, method: str, path: str, body=None):
        args = [os.getenv("OPENCODE_BIN", "opencode"), "api", method, path]
        if os.getenv("OPENCODE_SERVER"):
            args += ["--server", os.environ["OPENCODE_SERVER"]]
        if body is not None:
            args += ["--data", json.dumps(body)]
        try:
            process = await asyncio.create_subprocess_exec(
                *args, cwd=self.location, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE)
        except OSError as exc:
            raise UpstreamError("OpenCode CLI unavailable; install OpenCode V2 and check OPENCODE_BIN") from exc
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), self.timeout)
        except (TimeoutError, asyncio.CancelledError):
            if process.returncode is None:
                process.kill()
            await process.communicate()
            raise
        if process.returncode:
            # Do not return CLI stderr: provider errors may contain credentials.
            raise UpstreamError(f"OpenCode request failed: {method} {path}; check OpenCode service/provider status")
        if not stdout.strip():
            return None
        try:
            return json.loads(stdout)
        except ValueError as exc:
            raise UpstreamError("OpenCode returned invalid API JSON") from exc

    async def prepare(self):
        """Wait for location-scoped MCP discovery before the first model turn."""
        if self._prepared:
            return
        from urllib.parse import urlencode
        location = urlencode({"location[directory]": str(self.location)})
        # Discovery starts asynchronously on a brand-new Location. A first GET
        # can return no servers or pending; explicitly connecting before the
        # config has loaded races with discovery and returns 404. Bound this
        # readiness wait instead of starting a model with an empty tool list.
        try:
            async with asyncio.timeout(min(self.timeout, 45)):
                while True:
                    servers = await self.request("get", "/api/mcp?" + location)
                    well = next((s for s in servers["data"] if s["name"] == "well"), None)
                    status = well["status"]["status"] if well else "pending"
                    if status == "connected":
                        break
                    if status in ("failed", "disabled", "needs_auth"):
                        raise UpstreamError("Well MCP server failed to connect; check /ready and OpenCode MCP status")
                    await asyncio.sleep(0.25)
        except TimeoutError as exc:
            raise UpstreamError("Well MCP server is not ready; check OpenCode MCP status and retry") from exc
        self._prepared = True

    async def create(self, title: str) -> str:
        await self.prepare()
        try:
            provider, model = self.model.split("/", 1)
        except ValueError as exc:
            raise UpstreamError("OPENCODE_MODEL must have provider/model format") from exc
        model, _, variant = model.partition("#")
        ref = {"providerID": provider, "id": model}
        if variant:
            ref["variant"] = variant
        result = await self.request("post", "/api/session", {
            "title": title[:80], "agent": "copilot",
            "model": ref,
            "location": {"directory": str(self.location)},
        })
        return result["data"]["id"]

    async def answer(self, session: str, text: str) -> list[dict]:
        await self.prepare()
        admitted = await self.request("post", f"/api/session/{session}/prompt", {"text": text})
        try:
            await self.request("post", f"/api/experimental/session/{session}/wait")
        except (TimeoutError, asyncio.CancelledError):
            await self.request("post", f"/api/session/{session}/interrupt")
            raise
        # Read only this turn, even on long, paginated conversations.
        collected = []
        path = f"/api/session/{session}/message?order=desc&limit=100"
        while path:
            page = await self.request("get", path)
            for message in page["data"]:
                if message["id"] == admitted["data"]["id"]:
                    return list(reversed(collected))
                collected.append(message)
            cursor = page.get("cursor", {}).get("next")
            if cursor:
                from urllib.parse import quote
                path = f"/api/session/{session}/message?limit=100&cursor={quote(cursor, safe='')}"
            else:
                path = None
        raise UpstreamError("OpenCode did not return the admitted conversation turn")


def parse_answer(messages: list[dict]) -> dict:
    """Fail closed on failed runs, missing tools, invalid JSON or invented evidence."""
    tools, evidence = [], []
    final = None
    for message in messages:
        if message.get("error") or message.get("outcome") in ("failed", "interrupted"):
            raise UpstreamError("OpenCode model run failed; check provider credentials/quota or select OPENCODE_MODEL")
        if message.get("type") != "assistant":
            continue
        text = []
        for part in message.get("content", []):
            if part["type"] == "text":
                text.append(part["text"])
            elif part["type"] == "tool":
                state = part["state"]
                tools.append({"name": part["name"], "status": state["status"]})
                if state["status"] == "completed" and part["name"].startswith("well_"):
                    evidence.extend(c.get("text", "") for c in state.get("content", []))
        if text:
            final = "\n".join(text).strip()
    if not evidence:
        raise UpstreamError("Model did not successfully call Well Copilot MCP tools")
    if not any(t["name"] == "well_recall" and t["status"] == "completed" for t in tools):
        raise UpstreamError("Model did not successfully recall the current user's knowledge")
    if not final:
        raise UpstreamError("Model returned no final answer")
    if final.startswith("```json") and final.endswith("```"):
        final = final[7:-3].strip()
    try:
        result = json.loads(final)
        if not isinstance(result, dict) or not isinstance(result.get("answer"), str) or not result["answer"].strip():
            raise ValueError
        citations = result["citations"]
        if not isinstance(citations, list) or not all(isinstance(c, str) and c for c in citations):
            raise ValueError
        if result.get("visual") is not None and not isinstance(result["visual"], dict):
            raise ValueError
        visual = result.get("visual")
        if visual is not None and (visual.get("type") not in {
                "status_card", "table", "line", "bar", "map", "heatmap"}
                or not isinstance(visual.get("data"), list)
                or not all(isinstance(row, dict) for row in visual["data"])):
            raise ValueError
    except (ValueError, KeyError, TypeError) as exc:
        raise UpstreamError("Model returned malformed answer JSON; retry or select another free model") from exc
    evidence_text = "\n".join(evidence)
    if any(c not in evidence_text or c.startswith("v_") for c in citations):
        raise UpstreamError("Model cited evidence not returned by MCP tools")
    return {"answer": result["answer"], "citations": citations,
            "visual": result.get("visual"), "tool_calls": tools}
