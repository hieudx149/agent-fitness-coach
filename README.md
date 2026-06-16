# AI Workout Coach

> **Everfit AI Engineer take-home** — an intelligent assistant that answers fitness questions from a knowledge base, analyzes a user's training history, and orchestrates these capabilities through a coach agent.

**Status**: 🚧 In progress — see [implementation plan](#implementation-plan) below.

## Quickstart

```bash
cp .env.example .env
# Fill in FPT_API_KEY and OPENAI_API_KEY in .env
docker compose up --build
# Once up:
curl http://localhost:8000/api/v1/health
```

The chat UI will be available at `http://localhost:8000` after Phase 7. API docs (Swagger) live at `/docs`.

## Architecture (target)

```
User ──► UI (vanilla HTML + Tailwind + JS)
            │ POST /api/v1/chat
            ▼
       Guardrails (medical / eating disorder / out-of-scope)
            │ (refuse → return immediately)
            ▼ safe
       Coach Agent (LLM tool-calling, gpt-4o-mini)
            ├──► rag_search()       → RAG module (Qdrant + FPT)
            └──► analyze_history()  → Analysis module (stats engine)
```

The exercise PDF defines three features. They are implemented as three internal modules (`src/rag/`, `src/analysis/`, `src/agent/`) but exposed through a single `/api/v1/chat` endpoint. The Coach Agent decides which tools to call, and in what order.

## Implementation plan

Delivered in 8 phases, one commit per phase. See the internal design doc for full details.

| Phase | Description | Status |
|---|---|---|
| 0 | Scaffold (FastAPI + Docker + Qdrant) | ✅ |
| 1 | RAG ingest (chunker + FPT embed + Qdrant) | 🚧 |
| 2 | RAG retriever + `rag_search` tool | ⏳ |
| 3 | Guardrails (medical / eating / out-of-scope) | ⏳ |
| 4 | Workout analysis tool | ⏳ |
| 5 | Coach Agent + `/chat` endpoint | ⏳ |
| 6 | Evaluation pipeline | ⏳ |
| 7 | Chat UI (Perplexity-style tool traces) | ⏳ |
| 8 | Docs + polish | ⏳ |

The full README (architecture diagram, API docs, cost estimate, design decisions, metering bonus) will be finalized in Phase 8.

## Tech stack

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.11 + FastAPI | Async LLM I/O, Pydantic validation |
| Embedding | FPT `multilingual-e5-large` (1024d) | Cost-effective, multilingual-robust |
| Reranker | FPT `bge-reranker-v2-m3` | Boosts precision on a small KB |
| Main LLM | OpenAI `gpt-4o-mini` | Reliable function calling, low latency |
| Judge LLM | OpenAI `gpt-4o` | Stronger than the pipeline model for fair eval |
| Vector DB | Qdrant | Dashboard UI, strong metadata filtering |
| Containerization | Docker Compose | Single-command bring-up |

## License

Private — submission for the Everfit AI Engineer recruitment exercise.
