# Well Tell — Time-Boxed UI MVP Plan

## Goal

Build a chat-first Asset Intelligence Copilot UI on top of the validated backend. Answers should include the appropriate inline visual, supporting citations, and conversation-aware follow-ups.

Preserve the existing agent, data retrieval, memory, corrections, and citation checks. This plan does not replace the backend or introduce a second agent framework.

**Time-crunch decision:** ship one working chat screen with simple user/dataset selectors, citation chips, and all six inline visual types. Everything else is deferred. This document supersedes the broader phased UI scope discussed earlier.

## MVP scope and exclusions

**Build now:**

- Single-screen chat with Markdown answers and citation chips.
- Simple user and loaded-dataset selectors, new chat, and session-aware follow-ups.
- Status card, table, line chart, bar chart, map, and heatmap.
- Basic loading, empty, malformed-visual, and HTTP-error states.
- Only the small visual-contract changes needed to render charts reliably.

**Do not build for this deadline:**

- Sidebar, conversation-history browser, or durable frontend chat restoration.
- Citation/source-preview drawers or source-resolution endpoints.
- OpenUI, OUI-1, CopilotKit, AG-UI, streaming, or a second model call.
- Complex generated layouts, advanced table controls, or a full design system.
- Correction forms or a propose/approve/apply workflow; use existing chat feedback.
- New authentication or public multi-tenant deployment.

## Architecture decision

Start with **controlled generative UI**: the agent selects a visual and supplies structured data; the frontend renders it using registered, typed React components.

This matches the challenge requirement: status cards, tables, line charts, bar charts, maps, and heatmaps generated for each question and shown inline in chat. Users can explicitly request a visual; otherwise the agent chooses one.

### Options considered

| Option | Role | Decision |
| --- | --- | --- |
| OUI-1 | A specialized model that generates OpenUI Lang | Not needed initially; retain the current model and agent. |
| OpenUI | Framework for rendering and composing registered components | Preferred future composition layer if richer generated layouts justify it. |
| CopilotKit OpenIntelligentUI | Reference app combining chat, agent infrastructure, native components, and sandboxed generated HTML/JS | Use as inspiration rather than adopting the entire application stack. |

OpenIntelligentUI's documented application uses Next.js, a CopilotKit runtime, AG-UI, and a Python LangGraph/Deep Agent backend. Integration with our backend is possible through an adapter, but is not the shortest path for the current API.

OpenUI can work with our existing model; neither OUI-1 nor the hosted OpenUI Gateway is required. However, our current API returns JSON visual specifications, while the OpenUI renderer expects OpenUI Lang. It is not a drop-in renderer for the existing response.

**Initial approach:** render the current JSON contract directly. Consider OpenUI after all required visuals work reliably. Avoid arbitrary model-generated HTML/JavaScript for the initial product.

## Proposed frontend stack

| Layer | Proposed choice |
| --- | --- |
| Application | React + TypeScript + Vite |
| Styling and primitives | Tailwind CSS; use only a few shadcn/ui components if they save time |
| Tables | Native HTML table with horizontal scrolling; no table framework initially |
| Line and bar charts | Recharts |
| Maps | React Leaflet with an attributed tile provider |
| Heatmaps | Small accessible grid component initially |
| Runtime response validation | Zod |
| Generative UI | Small typed component registry; no additional GenUI framework for the MVP |

Vite is sufficient because FastAPI already owns the backend. No additional application server or model call is needed just to render a chart. Verify package compatibility and pin versions during implementation.

## Current backend contract

The existing `POST /chat` request accepts:

```json
{
  "user_id": "U-201",
  "session_id": null,
  "question": "Is WELL-0001 producing? Show its status card.",
  "dataset_id": "sample"
}
```

The response contains:

```text
session_id
answer
citations: string[]
visual: { type, title?, data: object[] } | null
tool_calls: { name, status }[]
```

Supported visual types are `status_card`, `table`, `line`, `bar`, `map`, and `heatmap`.

Other available endpoints:

- `GET /health`: loaded datasets and well counts.
- `GET /ready`: backend dependency readiness.
- `GET /docs`: HTTP API documentation.

### Existing limitations relevant to the UI

- `/chat` returns a complete response, not a live event stream.
- Visual rows are generic objects; chart axis/series mappings are not yet a strict contract.
- Citations are strings, not source-preview payloads.
- Tool-call summaries contain names and statuses, not complete evidence or live progress.
- There are no HTTP endpoints yet for listing users, fetching evaluation dates, resolving citations, or browsing conversation history.
- `user_id` is caller-supplied for a local/trusted demo, not authenticated identity.

## Request and rendering flow

```text
User question
  -> React sends question + user + dataset + session
  -> Existing FastAPI /chat
  -> Existing agent retrieves evidence and selects a visual
  -> Backend validates answer, citations, and basic visual shape
  -> Frontend validates the detailed visual contract
  -> Registered component renders inline in the assistant message
```

The frontend must not recalculate production status, downtime, compliance deadlines, or other domain rules. Domain calculations stay in the backend's derived views and tools.

## UX and layout

Build a focused operational workspace rather than a large fixed dashboard.

```text
Header: Well Tell | Dataset selector | User selector | New chat
Main: Conversation with inline visuals and citation chips
Footer: Question composer
```

### Core behavior

- Render Markdown answers with raw HTML disabled or safely sanitized.
- Show visuals inline, not only in a separate dashboard.
- Keep source citations visible beneath each answer.
- Show the dataset's evaluation date only when available from trusted metadata or the answer; never substitute the wall-clock date or imply the data is live.
- Start a separate conversation context when changing user or dataset.
- Clear displayed messages and the session ID when switching users or datasets; do not keep a history browser for the MVP.
- Provide loading, empty, unavailable, and error states.
- Do not populate the landing screen with invented metrics or charts.
- Use responsive layouts, keyboard-accessible controls, readable units, and explicit status labels rather than color alone.

### Interaction model

**Local interactions, without a model call:**

- Scroll displayed tables and inspect chart tooltips.
- Select map markers and inspect returned well details.
- Explore heatmap cells using the data already returned.

**Analytical follow-ups, using the same chat session:**

- Type a follow-up to investigate a well, explain evidence, or request another visual, such as “show this as a table.”
- Add dedicated follow-up buttons only if time remains; typed follow-ups are sufficient for the MVP.

Local controls must not imply they queried additional data. Follow-up actions should send the relevant selected values explicitly. No visual interaction should silently mutate backend data.

## Step 1 — Working chat end to end

Build the application in `UI/`.

- Scaffold React, TypeScript, Vite, and the styling foundation.
- Configure a development proxy to FastAPI; use an equivalent same-origin route/proxy for deployment.
- Add the application shell, composer, and message rendering.
- Integrate `/health`, `/ready`, and `/chat`.
- Populate datasets from `/health`. Populate the demo user picker from a small generated/static metadata list sourced from the actual dataset, not invented identities. This is not an authentication boundary. Refresh that list if dataset users change; add a metadata endpoint only if necessary, not as a prerequisite.
- Store and reuse the returned session ID for follow-ups.
- Add new-chat behavior and explicit user/dataset context separation.
- Render Markdown answers and citation chips.
- Prevent duplicate submissions within a conversation.
- Show an honest waiting indicator while a request is running; do not simulate live tool activity.
- Handle HTTP failures and preserve unsent drafts.

**Exit criterion:** a real question runs end to end through the existing backend, and a follow-up retains the correct session, user, and dataset.

## Step 2 — All six visual types

Create a typed visual registry:

| Visual type | Frontend component |
| --- | --- |
| `status_card` | `WellStatusCard` |
| `table` | `ResultsTable` |
| `line` | `TimeSeriesChart` |
| `bar` | `ComparisonChart` |
| `map` | `WellMap` |
| `heatmap` | `AreaMonthHeatmap` |

### Strengthen the visual contract

This is the main integration risk. Before integrating charts, make the smallest backward-compatible addition to the current visual specification to supply explicit mappings where needed. Keep `type`, `title`, and `data`; do not introduce a new UI language or a general layout schema.

- Table columns and display labels.
- X-axis, Y-axis, series, and category fields.
- Units and number/date formatting.
- Map latitude, longitude, well ID, and display fields.
- Heatmap row, column, and value fields.
- Missing-value handling; display result-limit metadata if the backend supplies it.

Validate these fields on the backend and frontend. Do not guess which numeric column belongs on a chart axis. Preserve existing backend evaluations when extending the contract.

### Reliability rules

- Render data from the response, not frontend fixtures or independent business calculations.
- Treat missing values as missing, not zero.
- Handle empty results without inventing rows or metrics.
- Keep full underlying values while formatting numbers for display.
- Show readable fallback data when a visual cannot render safely.
- Preserve the answer and citations even when visual rendering fails.
- Attribute map tiles and show a useful unavailable state when network access fails.

**Exit criterion:** all six visuals render from real responses, including explicit user requests and empty/malformed-data cases.

## Step 3 — Demo verification and essential polish

- Run real questions through all six visual renderers, then test a follow-up.
- Verify explicit visual requests, empty results, and missing values.
- Switch users to demonstrate existing backend memory behavior without retaining another user's visible messages.
- Exercise a correction through chat and display the returned answer and audit identifiers as supplied; do not build a separate feedback workflow.
- Verify switching datasets starts a new session and the test dataset works without sample-specific rendering assumptions.
- Confirm layout, map attribution, waiting indicators, and readable errors.
- Run type checking, a production build, focused rendering tests, and backend regression checks for any contract changes.

**Exit criterion:** the required demo works end to end with real data. Stop adding features and reserve remaining time for bugs and the recording.

## Deferred backlog — not part of this implementation

- Durable conversation-history sidebar and reload restoration.
- Backend metadata endpoint for dynamic user/date discovery if needed later.
- Citation resolution and evidence previews.
- Dedicated memory/conflict badges using structured backend metadata.
- Backend-enforced correction approval workflow.
- OpenUI component composition, richer layouts, streaming, and AG-UI integration.

The existing agent can write during a chat turn. A frontend confirmation alone does not prevent writes. Likewise, installing an OpenUI renderer alone does not make `/chat` stream. Neither extension is required to deliver this MVP.

## Error handling and safety

- `403`: explain that the conversation does not match the current user/dataset; do not attempt to bypass ownership checks.
- `404`: explain that the requested dataset is not loaded.
- `409`: indicate that the conversation already has a request in progress.
- `422`: surface actionable validation feedback.
- `502` / `503`: show backend/provider availability errors without fabricating an answer.
- `504` or an uncertain network outcome: do not automatically retry a turn that may have performed writes. Backend changes may already have committed.
- A browser-side cancellation must not be presented as proof that server execution or writes stopped.
- Do not expose provider credentials in browser code.
- Keep this a local/trusted demo until authentication and authorization are added.

## Validation and acceptance checklist

- [ ] Real end-to-end chat works with the existing backend.
- [ ] Follow-ups reuse the correct session.
- [ ] New chat starts a fresh session.
- [ ] User and dataset switches cannot reuse an incompatible session or expose private history.
- [ ] Any displayed evaluation date comes from trusted dataset metadata or the answer; no false live-data label appears.
- [ ] All six visual types render inline from real responses.
- [ ] Explicit visual requests are respected end to end.
- [ ] Chart mappings and units are explicit, not guessed.
- [ ] Empty data and missing values are handled honestly.
- [ ] Citation chips display the exact returned source identifiers.
- [ ] Pending, unavailable, malformed-visual, and HTTP-error states are covered.
- [ ] Potential write requests are not automatically retried after uncertain outcomes.
- [ ] Existing backend scenarios still work through the UI.
- [ ] Frontend type checking, production build, component tests, and browser smoke tests pass.

Use captured real responses for rendering regression tests, clearly separated from live application data. Include fresh end-to-end questions to avoid building only for the sample scenarios.

## Implementation priority

1. Confirm the small visual-mapping contract before building charts.
2. Connect chat and identity/dataset context; render text, citations, cards, and tables first.
3. Complete line/bar charts, map, and heatmap with clear fallbacks.
4. Verify real end-to-end scenarios and fix blockers.
5. Stop at the MVP; do not start the deferred backlog before the deadline.

### Rough time budget

| Work | Planning estimate |
| --- | --- |
| Connected chat, text/citations, status card, and table | 1–2 hours |
| Remaining visuals, selectors, and basic verification | Another 2–4 hours |

These are rough estimates for a demo-quality build with AI assistance, not guarantees. Contract inconsistencies, dependency setup, or map/network issues can extend them. The actual deadline has not been specified. If time runs short, prioritize working chat and reliable rendering first, and explicitly disclose any missing visual types rather than implying the full challenge requirement is complete.

**Bottom line:** ship one working chat screen against the current backend, with simple selectors, citations, and six reliable inline visuals. No backend rewrite, no GenUI framework integration, and no optional product features for this deadline.

## References

- Challenge brief: `context/FlytBase AHC SWE Hackathon#17Oct.txt`.
- Current API: `backend/api.py`.
- Response validation: `backend/opencode.py`.
- Existing response examples: `data/eval-final-results.json`.
- [OUI-1 announcement](https://www.openui.com/blog/oui-1).
- [OpenUI introduction](https://www.openui.com/docs).
- [OpenUI integration guide](https://www.openui.com/docs/getting-started).
- [OpenIntelligentUI architecture](https://github.com/CopilotKit/OpenIntelligentUI/blob/main/docs/architecture.md).
- [OpenIntelligentUI integration patterns](https://github.com/CopilotKit/OpenIntelligentUI/blob/main/docs/bring-to-your-app.md).
