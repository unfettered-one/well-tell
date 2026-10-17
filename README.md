# Well Tell — Well Copilot

Ask questions about oil-well production, spills, downtime, repairs and compliance.
Answers come from dataset-derived SQLite views and documents, through real MCP
tool calls executed by an OpenCode V2 `copilot` agent.

```text
POST /chat -> FastAPI -> OpenCode V2 conversation -> Well MCP (stdio)
                                                -> SQLite + dataset reports
          <- {session_id, answer, citations, visual, tool_calls}
```

## Setup

Requires Python 3.12+ and OpenCode V2 (tested with 2.0.32).

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
.venv/bin/python ingest/ingest.py \
  --data dataset/flytbase-ahc-swe-asset-intelligence-dataset/sample-data \
  --dataset sample --db data/well_copilot.db
opencode api get /api/info
.venv/bin/python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

The default model is `github-copilot/gpt-6.1-sol#low`, using the Copilot account
already connected in OpenCode. If needed, open OpenCode, run `/connect`, select
GitHub Copilot and finish its login. No provider secret belongs in this repo.
Set `OPENCODE_MODEL` in `.env` to another enabled tool-capable model. The API loads
`.env` at startup; restart **the API** after changing it. New conversations use
the selected model; existing conversations retain their OpenCode model.

OpenCode free models remain selectable (for example `opencode/big-pickle`), but
on the tested installation they returned provider HTTP 403, even through
`opencode run`. The API does not silently switch providers or fabricate a reply.
Adding a provider key to the API's `.env` alone does not update credentials in an
already running OpenCode service: connect that provider using OpenCode `/connect`.

## Ask a question

```bash
curl http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"U-201","question":"Is WELL-0001 producing oil right now? Show its status card.","dataset_id":"sample"}'
```

Use the returned `session_id` in subsequent `/chat` requests to continue the same
conversation. Omit it to start a new chat. User history is still available through
identity-bound MCP recall across that user's chats.

- `GET /health`: loaded database datasets.
- `GET /ready`: OpenCode connectivity and Well MCP connection status (does not
  spend model tokens or guarantee provider quota).
- `GET /docs`: interactive HTTP schema.
- `POST /chat`: question plus user/conversation/dataset context.

Visuals are specifications, not rendered images:
`{"type":"status_card|table|line|bar|map|heatmap","title":"...","data":[...]}`.
The frontend renders them. Short answers may return `visual: null`.

## Tests

```bash
# Offline: real stdio MCP, HTTP contract, isolation, feedback and actual ingest.
.venv/bin/python -m pytest -q

# Standalone structural and sample-golden gate.
.venv/bin/python ingest/verify.py --db data/well_copilot.db

# Build a DISPOSABLE DB for live evaluations (feedback cases intentionally write).
.venv/bin/python ingest/ingest.py \
  --data dataset/flytbase-ahc-swe-asset-intelligence-dataset/sample-data \
  --dataset sample --db data/eval.db
.venv/bin/python eval.py --db data/eval.db --only Q1,Q4,Q10

# All 18 scenario checks, in order (Q11/Q15 depend on earlier scenarios).
.venv/bin/python eval.py --db data/eval.db

# Optional: hit a running Uvicorn instance over TCP instead of ASGI.
# Start that API with WELL_COPILOT_DB=data/eval.db first.
.venv/bin/python eval.py --db data/eval.db --api-url http://127.0.0.1:8000 --only Q1
```

`eval.py` sends real requests through the FastAPI ASGI app, invokes the selected
model through OpenCode, and checks facts, citations/tool usage and visual types.
It exits nonzero for failures and saves full responses to `data/eval-results.json`.
It is a deterministic smoke/keyword harness, **not proof of full semantic accuracy**;
review the saved answers, especially conflict explanations and feedback scope.

## Loading new data

```bash
.venv/bin/python ingest/ingest.py --data /path/to/test-data \
  --dataset test --db data/well_copilot.db
```

Send `dataset_id: "test"` in **a new conversation**. Loading a dataset replaces
only its ingested rows; shared runtime knowledge survives. Manuals in that folder
supply thresholds. `--as-of YYYY-MM-DD` overrides that dataset's evaluation date.
Default sample date is **2026-10-16**, independent of the wall clock.

## Boundaries and safety

- API-created conversations have durable user/dataset/OpenCode-session mappings
  in `backend_conversations`; another user cannot reuse the same chat ID.
- The API uses the supported `opencode api` CLI for authenticated V2 requests; no
  hardcoded service port or reading OpenCode's credential files.
- It generates a private per-database config under `data/<db-name>_opencode/`.
  The `copilot` agent denies shell/filesystem/other MCP tools and permits only
  `well_*`. MCP source revisions trigger server reconnection after code changes.
- Private SQL tables are blocked from arbitrary `query_db`; recall and writes
  bind user IDs to API-created sessions using OpenCode call metadata.
- Raw data stays read-only. Corrections and rules use audited runtime writes.
- Both user and successful assistant turns are logged by the API, not the model.
- Responses fail closed on provider errors, missing recall/tool execution,
  malformed JSON, invalid visual shapes or citations absent from tool results.
- This is a **local/trusted demo**, not a public multi-tenant service: `user_id`
  is caller-supplied, not authenticated. Add authentication/authorization before
  exposing it, especially the shared correction/rule-write tools. MCP session
  metadata is a correlation/binding mechanism, not authentication against a
  malicious local process. Run a single API deployment per database.
- HTTP errors: 403 wrong conversation owner/dataset, 404 unloaded dataset,
  409 concurrent turn, 422 invalid request, 502 model/output failure, 503 missing
  DB/unavailable service, 504 timeout. Retrying writes after a timeout needs care:
  earlier model tool writes may already have committed.

Details: [ingest](ingest/README.md), [MCP](mcp/README.md),
[backend plans](context/plan/backend/high_level_backend_plan.md).
