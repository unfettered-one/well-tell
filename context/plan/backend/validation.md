# Backend validation

Validated locally on 17 October 2026 with Python 3.12, OpenCode 2.0.32 and
`github-copilot/gpt-6.1-sol#low` using the already connected Copilot account.

## Reproducible checks

- `python -m pytest -q`: offline ingest, real stdio MCP, HTTP contract and
  OpenCode V2 protocol tests. See the root README for environment setup.
- `python ingest/verify.py --db data/well_copilot.db`: structural checks,
  extraction coverage and sample golden answers.
- `python eval.py --db data/eval.db`: live model checks, using a disposable DB.
  Feedback scenarios mutate runtime knowledge; rebuild a fresh disposable DB
  before repeating the entire suite. Responses are saved under `data/`.
- `python -m pip check`: installed dependency compatibility.

## Confirmed real-model path

Both the ASGI harness and a real Uvicorn/TCP request exercised:

`HTTP -> FastAPI -> OpenCode V2 session -> stdio MCP -> SQLite -> JSON response`.

Cold-start HTTP `/health`, `/ready` and `/chat` returned 200. Q1 returned a
`status_card`, named Ryan Brooks, cited `INS-0001-0203` and `CTX-0001-003`, and
classified WELL-0001 as not producing. Live Q4 returned 6 real spills / 15.1 bbl,
excluding the corrected rainwater detection. Live Q10 returned the 7.1-hour and
8.1-hour containment breaches, compared with the SOP limit.

OpenCode `big-pickle` and `mimo-v2.6-flash-free` returned provider 403 on this
installation, including through `opencode run`; they were not reported as
working. Copilot is now the configurable default. No additional API key was used.

## Regression fixes

Final offline result: **37 tests passed**, plus `pip check` and `git diff --check`.
The initial complete live run passed 15/18 keyword checks. The cold-start failure
and missing runtime-correction attribution were fixed and **Q1/Q15 both passed
live retests**. Q8's original response contained all 40 correct heatmap cells;
its failed yearly-total keyword check was replaced by cell-by-cell verification.
The resulting combined coverage is **18/18 scenario checks**, not a claim that
the original uninterrupted run passed. Original responses, retests and combined
results are retained separately in `data/eval-full-results.json`,
`data/eval-retest.json` and `data/eval-final-results.json`.

Three additional real-model follow-ups passed: Jake's workover plan was visible
to Michael; Jessica could not access Michael's three-well conversation; and the
corrected 5.4-bbl spill was reportable/overdue for a different user. Those answers
are in `data/eval-followups.json`.

### Fixes covered by regressions

- Rule joins now include dataset_id: identical IDs in sample/test cannot
  multiply status, downtime or obligation results.
- Explicit as-of dates reach the per-dataset views; global as-of is the latest
  active dataset date.
- Equal-timestamp corrections resolve by insertion order deterministically.
- Hour-based deadlines compare timestamps, not just calendar dates.
- Runtime claims appear in dataset-filtered conflict queries without cross joins.
- Private SQL tables are blocked, conversation owners cannot be reassigned, and
  API-created MCP calls bind private operations to their stored owner.
- Report/manual selection can be explicitly dataset-scoped and is automatically
  bound to the conversation in the HTTP flow.
- MCP discovery is awaited before the first model turn on a new location.

The live evaluator checks selected facts, visuals and tool use; it is not an
LLM judge and does not prove every sentence is correct. The API validates the
response shape and evidence presence, not complete semantic entailment. The
HTTP service still needs real authentication before public deployment.
