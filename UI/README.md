# Well Tell UI

Single-screen, trusted/local Asset Intelligence Copilot. React + TypeScript +
Vite + Tailwind, with Recharts, React Leaflet and Zod. The existing FastAPI agent,
retrieval, citations, memory and audited feedback remain the source of truth.

## Run locally

Requires Node **22.12+**, the repository's Python environment, an ingested DB and
the existing OpenCode Go subscription/provider. The default backend model is
`opencode-go/gpt-6-luna#low`. No provider secrets go in the UI.

From the repository root, start the backend:

```bash
.venv/bin/python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
cd UI
npm ci
npm run dev
```

Open **http://127.0.0.1:5173**. Vite proxies `/health`, `/ready`, `/chat` and
API documentation to port 8000. Set `WELL_API_TARGET` when starting Vite to use a
different local backend. The proxy waits for complete responses, not a stream.

For a same-origin production build:

```bash
cd UI
npm run build
```

Then start/restart FastAPI from the root. It serves `UI/dist/` at
**http://127.0.0.1:8000/** when that directory exists at startup. API routes take
priority. There is no additional app server, model call, or frontend API key.
`vite preview` is only a static build preview; use FastAPI for connected chat.

## Behavior and boundaries

- Dataset/user options and evaluation dates come from `/health`, scoped to each
  actual loaded dataset. This extends an existing endpoint instead of adding a
  user/source/history API. This is **not authentication**.
- New chat, user changes and dataset changes discard visible messages, drafts and
  session context. No frontend history or reload restoration is implemented.
- Follow-ups reuse the backend session ID. Context changes and duplicate sends
  are disabled during a pending turn. Pending text reports only actual waiting,
  not invented live tool activity.
- Markdown has raw HTML disabled. Citation chips contain the exact returned
  identifiers; they are not fake clickable source previews.
- Charts/maps are lazy loaded. All six components render returned rows only.
  No production/compliance/downtime logic is computed in the browser.
- Missing values are not zero; ambiguous, malformed, unsupported or unavailable
  visuals fall back to readable returned data without hiding answers/citations.
  Tables scroll, charts expose underlying data, heatmap cells are keyboard
  accessible, and maps have tile attribution plus a network-failure notice.
- HTTP failures preserve the draft. **No chat request is automatically retried.**
  A timeout, network failure or failed upstream turn can have committed tool
  writes. Closing/reloading the browser does not prove server execution stopped.
- Maps use OpenStreetMap public tiles, which require network access and send tile
  requests to that provider. There is no geocoding or invented location fallback.

## Typed display contract

The backwards-compatible base remains `{type, title?, data: object[]}` or null.
New visuals add explicit top-level display metadata. `backend/visuals.py` and
`src/contracts.ts` validate it; `backend/agent.md` instructs the existing agent.
The backend still accepts old visuals without mappings. The UI deliberately
falls back for ambiguous legacy charts instead of guessing field roles.

```json
{
  "type": "line",
  "title": "Returned temperatures",
  "x": {"field": "inspected_at", "label": "Inspection", "format": "date"},
  "y": [{"field": "temperature_c", "label": "Temperature", "unit": "°C", "format": "number", "decimals": 1}],
  "data": [{"inspected_at": "2026-10-15", "temperature_c": 41.0123}]
}
```

A display field is `{field, label?, unit?, format?, decimals?}`. Supported formats:
`text`, `number`, `date`, `datetime`, `percent`. Percent numbers are percentage
points (not multiplied by 100). Dates are displayed in UTC. Formatting never
changes underlying values; numeric table cells expose raw values on hover.

| Type | Mapping |
|---|---|
| `status_card` | Optional ordered `columns: DisplayField[]`; exactly one row. Displays explicit `is_producing` or `production_status`/`status`, never a temperature inference. |
| `table` | Optional ordered `columns: DisplayField[]`; otherwise all returned keys. |
| `line`, `bar` | `x: DisplayField`, `y: DisplayField[]`; optional `series: string` for long-form groups. Different units use separate axes (at most two). Duplicate points require backend aggregation. |
| `map` | `latitude: string`, `longitude: string`, optional `well_id: string`, and `columns` for popup details. Invalid coordinates are listed, not placed. |
| `heatmap` | `row: DisplayField`, `column: DisplayField`, `value: DisplayField`. Duplicate cells require backend aggregation. |

Optional `result_limit: {truncated: boolean, total?: number, limit?: number}`
displays backend-supplied limits without claiming the result is complete.

## Verification

```bash
cd UI
npm run typecheck
npm run build
npm test
npx playwright install chromium
npm run test:e2e
```

Component and desktop/mobile browser tests use **captured real responses**, never
live application fixtures. `src/test/fixtures/captured-responses.json` records
provenance. HTTP interception is restricted to test code. Regenerate historical
captures with `node scripts/capture-fixtures.mjs`; older captures add only
explicit, documented display annotations, never invented rows.

For fresh end-to-end provider/MCP checks, build a **disposable** DB from the root:

```bash
.venv/bin/python ingest/ingest.py --data dataset/flytbase-ahc-swe-asset-intelligence-dataset/sample-data --dataset sample --db data/ui-verification.db
.venv/bin/python ingest/ingest.py --data dataset/flytbase-ahc-swe-asset-intelligence-dataset/sample-data --dataset test --db data/ui-verification.db --as-of 2026-10-10
OPENCODE_MODEL='opencode-go/gpt-6-luna#low' WELL_COPILOT_DB=data/ui-verification.db .venv/bin/python -m uvicorn backend.api:app --host 127.0.0.1 --port 8001
```

Then, in another terminal from the root:

```bash
.venv/bin/python UI/scripts/verify_live.py --api-url http://127.0.0.1:8001 --allow-writes
```

The script tests all six explicit visual requests, a fresh well question and
session-aware follow-up, empty results, and (with `--allow-writes`) correction
audit IDs, cross-user shared correction visibility and private memory isolation.
If `test` is also loaded, it exercises a fresh conversation in that dataset.
This spends real model tokens and intentionally writes only to the chosen DB.
It saves responses under `data/ui-live-results.json` for review. After a successful
run, `cd UI && node scripts/capture-fixtures.mjs --live` replaces rendering test
snapshots with unmodified fresh responses.

Deferred by design: sidebar/history, authentication, streaming, citation drawers,
correction forms, extra agent/GenUI frameworks and generated executable HTML.
