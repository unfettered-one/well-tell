"""Fresh HTTP -> existing agent -> MCP -> SQLite UI-contract smoke test.

Run ONLY against a disposable database: --allow-writes exercises a correction
and private memory through ordinary chat. No fake model, fixtures or second call.
"""
import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.visuals import Visual  # noqa: E402

import httpx  # noqa: E402

QUESTIONS = [
    ("status_card", "Is WELL-0001 producing oil right now? When was it inspected and by whom? Show a status card."),
    ("table", "Which wells in Northeast Block 8 are not producing and why? Show a table."),
    ("line", "Show WELL-0001 wellhead and ambient temperatures for the last 13 weeks in a line chart. Include explicit axes and Celsius units."),
    ("bar", "Which three wells in Northeast Block 7 had the most downtime in the last four months? Show a bar chart with days as the unit."),
    ("map", "Map every well in Northeast Block 8 with a real spill in the last 90 days. Return actual well coordinates and spill details."),
    ("heatmap", "Show a heatmap of 2026 real spill counts by area and month, with corrected detections removed. Include explicit row/column/value mappings."),
]


async def main(args):
    results = []
    output = ROOT / "data/ui-live-results.json"
    async with httpx.AsyncClient(base_url=args.api_url, timeout=660) as client:
        health = (await client.get("/health")).raise_for_status().json()
        assert any(d["dataset_id"] == "sample" and d["users"] and d.get("as_of") for d in health["datasets"])
        (await client.get("/ready")).raise_for_status()

        async def ask(name, question, *, session=None, user="U-201", dataset="sample", expected=None):
            start = time.monotonic()
            response = await client.post("/chat", json={"user_id": user, "dataset_id": dataset, "session_id": session, "question": question})
            result = {"case": name, "status": response.status_code, "seconds": round(time.monotonic() - start, 1), "response": response.json()}
            results.append(result)
            output.write_text(json.dumps(results, indent=2) + "\n")
            response.raise_for_status()
            answer = result["response"]
            assert answer["answer"] and answer["tool_calls"], result
            if expected:
                spec = Visual.model_validate(answer["visual"])
                assert spec.type == expected, result
                if spec.type in ("line", "bar"):
                    assert spec.x and spec.y and all(f.unit for f in spec.y), result
                if spec.type == "map":
                    assert spec.latitude and spec.longitude, result
                if spec.type == "heatmap":
                    assert spec.row and spec.column and spec.value, result
            print(f"PASS {name}: HTTP {response.status_code} ({result['seconds']}s)", flush=True)
            return answer

        selected = [item for item in QUESTIONS if not args.only or item[0] in args.only.split(",")]
        for kind, question in selected:
            await ask(kind, question, expected=kind)
        if args.only:
            print(f"{len(results)} selected live visual checks passed; responses saved to {output.relative_to(ROOT)}", flush=True)
            return
        # Fresh questions, not just golden sample queries. Follow-ups must reuse
        # the actual returned session, not substitute a new conversation.
        first = await ask("fresh", "What is the latest inspection evidence for WELL-0042? Show its status card.", expected="status_card")
        follow = await ask("follow_up", "Show that same well's latest inspection evidence as a table, including its well ID.", session=first["session_id"], expected="table")
        assert follow["session_id"] == first["session_id"] and "WELL-0042" in json.dumps(follow)
        empty = await ask("empty", "Show a table of real oil spills recorded for WELL-0042 during calendar year 1900. Do not invent records.", expected="table")
        assert empty["visual"]["data"] == []
        if args.allow_writes:
            corrected = await ask("correction", "The 15 Oct reading for WELL-0164 is wrong. The thermal gun was faulty; the crew re-measured the wellhead at 41.0 °C. Record this correction and say if it is producing now.")
            assert re.search(r"COR-(?:RT-)?\d+", json.dumps(corrected)), corrected
            other = await ask("shared_correction_other_user", "Is WELL-0164 producing? Identify the stored correction and its author.", user="U-202")
            assert "41" in json.dumps(other) and "COR-" in json.dumps(other)
            await ask("private_memory", "Remember privately for me: I prefer temperature summaries in Celsius and concise bullet points.")
            own = await ask("memory_own_user", "What private preference have I asked you to remember about temperature summaries?")
            assert "celsius" in own["answer"].lower(), own
            isolated = await ask("memory_other_user", "What private preference have I asked you to remember about temperature summaries?", user="U-202")
            assert "celsius" not in isolated["answer"].lower(), isolated
        if any(d["dataset_id"] == "test" for d in health["datasets"]):
            await ask("other_dataset", "Show the latest status of one well in this dataset as a status card. Use its actual well ID.", dataset="test", expected="status_card")
        print(f"{len(results)} fresh live HTTP checks passed; responses saved to {output.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--allow-writes", action="store_true", help="Confirm this is a disposable DB; test correction/private memory writes")
    parser.add_argument("--only", help="Run selected visual type(s), e.g. heatmap or line,map")
    asyncio.run(main(parser.parse_args()))
