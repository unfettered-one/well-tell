#!/usr/bin/env python3
"""Live free-model -> OpenCode -> stdio MCP -> SQLite -> HTTP contract checks.

Run on a disposable DB: feedback scenarios intentionally change runtime knowledge.
Assertions are deterministic evidence/keyword checks, NOT an LLM judge.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

import httpx

from backend.api import create_app

# Checks focus on facts, tool use and visual type; narrative quality needs review.
CASES = [
    ("Q1", "U-201", "Is WELL-0001 producing oil right now? When was it last inspected and by whom? Show its status card.", ["INS-0001-0203", "Ryan Brooks", "3.2", "CTX-0001-003"], "card"),
    ("Q2", "U-201", "Which wells in Northeast Block 8 are not producing oil right now, and why? Show a table.", ["WELL-0164", "WELL-0170", "WELL-0172", "WELL-0175"], "table"),
    ("Q3", "U-201", "Show a line chart of WELL-0001 wellhead versus ambient temperature for the last 13 weeks; mark non-producing readings.", ["2026-07-23", "2026-10-15"], "line"),
    ("Q4", "U-201", "How many real spills has WELL-0001 had in the last 4 years and how many barrels total? List them in a table and explain excluded detections.", ["15.1", "INS-0001-0070", "6"], "table"),
    ("Q5", "U-201", "How many days was WELL-0001 down in 2025? Cite the findings.", ["21"], None),
    ("Q6", "U-201", "Which 3 wells in Northeast Block 7 had most downtime in the last 4 months? Show a bar chart.", ["WELL-0121", "WELL-0138", "WELL-0107", "49", "42"], "bar"),
    ("Q7", "U-201", "Show on a map every well in Northeast Block 8 with a real spill in the last 90 days.", ["WELL-0151", "WELL-0165", "WELL-0175", "WELL-0186"], "map"),
    ("Q8", "U-201", "Show a heatmap of 2026 real spills by geographic area and month, with corrected detections removed.", ["Southwest Block 24"], "heatmap"),
    ("Q9", "U-201", "Which rules has WELL-0001 broken in the last 12 months and what is still open?", ["SR-01", "SR-02", "SR-03", "RC-04"], None),
    ("Q10", "U-201", "In Southwest Block 24 which spills in the last 90 days were not contained within the SOP limit?", ["WELL-0082", "7.1", "WELL-0100", "8.1"], None),
    ("Q11", "U-201", "For the three wells we discussed with most downtime in Northeast Block 7, what have repairs cost this year?", ["25,794", "46,942", "5,176"], None),
    ("Q12", "U-201", "The 15 Oct reading for WELL-0164 is wrong. The handheld thermal gun was faulty; the crew re-measured the wellhead at 41.0 °C. Record the correction and tell me if it is producing now.", ["COR-", "41", "INS-0164-0205"], None),
    ("Q13", "U-201", "The AI estimated the 24 Sep spill at WELL-0151 as 4.5 bbl; the field crew measured 5.4 bbl. Correct it and explain reporting duties.", ["COR-", "5.4", "SR-01", "SR-03"], None),
    ("Q14", "U-201", "Note for all T350 wells: RCA after 2 repairs not 3. Apply that rule. Which wells in Northeast Block 7 now need pump jack RCA?", ["WELL-0108", "WELL-0120", "WELL-0121", "WELL-0138"], None),
    ("Q15", "U-202", "Is WELL-0164 producing now? Identify any correction and conflicting inspector note.", ["41", "COR-", "Michael Turner"], None),
    ("Q16", "U-102", "FYI for everyone: WELL-0007 will be shut in from 17 Oct for a 10-day planned workover. Remember that as shared operational knowledge.", ["WELL-0007", "10"], None),
    ("Q17", "U-102", "WELL-0001 is back online since 14 Oct. Check against the latest data and keep my claim on record.", ["unconfirmed", "INS-0001-0203"], None),
    ("Q18", "U-301", "Was the 20 Aug spill at WELL-0101 real oil? Explain the conflicting notes and whether there was a formal correction.", ["INS-0101-0197", "CTX-0101-002", "CTX-0101-003"], None),
]


def check_case(name, data, expected, visual):
    normalized = json.dumps(data).lower().replace(",", "")
    missing = [x for x in expected if x.lower().replace(",", "") not in normalized]
    spec = data.get("visual") or {}
    if visual and visual not in str(spec.get("type", "")):
        missing.append("visual:" + visual)
    if name == "Q8":
        # A correct heatmap need not print yearly totals. Verify all 40 cells,
        # not the appearance of a total such as '43' somewhere in prose.
        matrix = {
            "Southwest Block 23": [4,3,3,6,3,4,4,3,3,2],
            "Southwest Block 24": [7,4,5,6,5,5,3,1,5,2],
            "Northeast Block 7": [5,3,2,4,6,6,2,4,4,1],
            "Northeast Block 8": [4,4,4,3,2,4,4,0,1,0],
        }
        x, y, value = spec.get("x", "month"), spec.get("y", "area_name"), spec.get("value", "spill_count")
        cells = {(r.get(y), str(r.get(x))): r.get(value) for r in spec.get("data", [])}
        for area, values in matrix.items():
            for month, count in enumerate(values, 1):
                if cells.get((area, f"2026-{month:02}")) != count:
                    missing.append(f"heatmap:{area}:{month}")
    return missing


async def main(args):
    app = create_app(Path(args.db)) if not args.api_url else None
    results = []
    transport = httpx.ASGITransport(app=app) if app else None
    async with httpx.AsyncClient(transport=transport, base_url=args.api_url or "http://copilot", timeout=None) as client:
        for name, user, question, expected, visual in CASES:
            if args.only and name not in args.only.split(","):
                continue
            start = time.monotonic()
            response = await client.post("/chat", json={"user_id": user, "question": question})
            data = response.json()
            missing = check_case(name, data, expected, visual)
            ok = response.status_code == 200 and not missing and bool(data.get("tool_calls"))
            result = {"case": name, "passed": ok, "status": response.status_code,
                      "missing": missing, "seconds": round(time.monotonic() - start, 1), "response": data}
            results.append(result)
            Path(args.output).write_text(json.dumps(results, indent=2))
            print(json.dumps(result), flush=True)
    Path(args.output).write_text(json.dumps(results, indent=2))
    print(f"{sum(r['passed'] for r in results)}/{len(results)} live checks passed", flush=True)
    return all(r["passed"] for r in results)


def rescore(args):
    """Re-run deterministic checks on saved answers; never pretend this is a rerun."""
    results = json.loads(Path(args.rescore).read_text())
    cases = {c[0]: c for c in CASES}
    for result in results:
        _, _, _, expected, visual = cases[result["case"]]
        result["original_scoring_passed"] = result["passed"]
        result["missing"] = check_case(result["case"], result["response"], expected, visual)
        result["passed"] = result["status"] == 200 and not result["missing"] and bool(result["response"].get("tool_calls"))
        result["rescored_without_model_call"] = True
    Path(args.output).write_text(json.dumps(results, indent=2))
    print(f"{sum(r['passed'] for r in results)}/{len(results)} saved-answer checks passed (no model rerun)")
    return all(r["passed"] for r in results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="Disposable, ingested sample DB")
    parser.add_argument("--only", help="Comma-separated case IDs, e.g. Q1,Q4,Q10")
    parser.add_argument("--api-url", help="Optional running HTTP API URL; otherwise test via ASGI")
    parser.add_argument("--output", default="data/eval-results.json")
    parser.add_argument("--rescore", help="Recheck a saved result file without making model calls")
    options = parser.parse_args()
    if not options.db and not options.rescore:
        parser.error("--db is required unless --rescore is used")
    raise SystemExit(0 if (rescore(options) if options.rescore else asyncio.run(main(options))) else 1)
