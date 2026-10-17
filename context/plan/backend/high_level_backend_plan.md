# High-Level Backend Plan — Well Copilot (OpenCode agents)

## The flow, crisp

```
User question
   → FastAPI (you send {user_id, session_id, question})
     → OpenCode session (prompt endpoint) with our "copilot" agent
       → Agent (the LLM) reasons and calls tools from OUR well-copilot MCP server:
            query_db(sql)      → SQLite DB we built by ingesting the dataset
            search_docs(q)     → FTS index over manuals/SOPs/reports/notes (same SQLite)
            remember / recall  → shared facts + per-user memory (same SQLite)
            record_correction  → corrections with scope (same SQLite)
       → Agent writes the answer with citations (+ visual spec JSON)
   → FastAPI returns {answer, visual, citations} to the frontend
```

## Two small clarifications so we're 100% aligned

1. **The SQLite DB is built by us** — `ingest.py` reads `dataset/.../sample-data/` (JSONL/JSON/MD files) and creates tables. When the test dataset drops, we re-run ingest pointed at the new folder. Same schema → nothing else changes.
2. **The DB holds two kinds of truth**:
   - (a) the ingested raw data (read-only for the agent), and
   - (b) run-time knowledge — corrections, shared facts, memory (written via MCP tools).
   - Corrections are applied at read time in the SQL views, so they automatically change every later answer.

## One correction to the flow in spirit

FastAPI doesn't "call agents" in the plural sense — it creates/maintains **one OpenCode session per user conversation**, and all sessions use the same single `copilot` agent definition. The *users* differ (private memory = their own sessions), the *agent* is shared.

## Why this is accurate and new-data-proof

- All math/counting happens in SQL/views inside the MCP tools — the agent just decides *which* query to run and narrates results. That's where the accuracy comes from.
- Ingest script (`ingest.py`) rebuilds SQLite from any dataset folder → test dataset = one command.
- The 18 example questions become `eval.py` — we measure accuracy against expected answers before the demo.

## Planned pieces

| Piece | What it does |
|---|---|
| `ingest.py` | Reads sample-data/ (JSONL/JSON/MD) → SQLite tables + FTS5 index |
| `views.py` / SQL views | Domain logic: production status (temp delta ≥ 15/20 °C), downtime (7 days per failed inspection), corrected spills, etc. |
| `mcp_server.py` | FastMCP server exposing `query_db`, `search_docs`, `get_doc`, `remember`, `recall`, `record_correction` |
| `opencode.json` | Defines the `copilot` agent: system prompt with domain rules, citation + conflict rules, visual guidance; model = free OpenCode model; MCP server registered |
| `api.py` | FastAPI: maps frontend requests → OpenCode sessions (one per user conversation); returns {answer, visual, citations} |
| `eval.py` | Runs the 18 example questions against expected answers → accuracy measurement |
