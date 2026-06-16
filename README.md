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

UI sẽ available tại `http://localhost:8000` sau Phase 7. API docs (Swagger) tại `/docs`.

## Architecture (target)

```
User ──► UI (vanilla HTML + Tailwind + JS)
            │ POST /api/v1/chat
            ▼
       Guardrails (medical / eating / out-of-scope)
            │ (refuse → return ngay)
            ▼ safe
       Coach Agent (LLM tool-calling, gpt-4o-mini)
            ├──► rag_search()       → RAG module (Qdrant + FPT)
            └──► analyze_history()  → Analysis module (stats engine)
```

3 features của exercise PDF được implement thành 3 module nội bộ (`src/rag/`, `src/analysis/`, `src/agent/`) nhưng chỉ expose 1 endpoint `/api/v1/chat`. Agent tự quyết tool nào, thứ tự nào.

## Implementation plan

Triển khai theo 8 phase, mỗi phase 1 commit. Xem chi tiết ở thiết kế nội bộ.

| Phase | Mô tả | Status |
|---|---|---|
| 0 | Scaffold (FastAPI + Docker + Qdrant) | ✅ |
| 1 | RAG ingest (chunker + FPT embed + Qdrant) | ⏳ |
| 2 | RAG retriever + `rag_search` tool | ⏳ |
| 3 | Guardrails (medical/eating/out-of-scope) | ⏳ |
| 4 | Workout analysis tool | ⏳ |
| 5 | Coach Agent + `/chat` endpoint | ⏳ |
| 6 | Evaluation pipeline | ⏳ |
| 7 | Chat UI (Perplexity-style tool traces) | ⏳ |
| 8 | Docs + polish | ⏳ |

README đầy đủ (architecture diagram, API docs, cost estimate, design decisions, metering bonus) sẽ được hoàn thành ở Phase 8.

## Tech stack

| Layer | Choice | Lý do |
|---|---|---|
| Language | Python 3.11 + FastAPI | Async LLM I/O, Pydantic validation |
| Embedding | FPT `multilingual-e5-large` (1024d) | Cost-effective, multilingual robust |
| Reranker | FPT `bge-reranker-v2-m3` | Cải thiện precision với KB nhỏ |
| Main LLM | OpenAI `gpt-4o-mini` | Function calling chắc chắn, latency thấp |
| Judge LLM | OpenAI `gpt-4o` | Mạnh hơn pipeline cho eval công bằng |
| Vector DB | Qdrant | UI dashboard, metadata filtering mạnh |
| Containerization | Docker Compose | `docker compose up` 1 lệnh |

## License

Private — submission for Everfit AI Engineer recruitment.
