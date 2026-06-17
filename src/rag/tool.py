"""rag_search() — public entry point for the Coach Agent (and direct callers).

This is the boundary between the agent and the RAG module. The agent only
knows about this function; everything below (retrieval, reranking, prompt
construction) is an implementation detail it should never touch.
"""
import logging
from typing import Any

from src.rag.generator import generate_answer
from src.rag.retriever import Retriever

logger = logging.getLogger(__name__)


async def rag_search(
    query: str,
    candidates: int | None = None,
    top_n: int | None = None,
) -> dict[str, Any]:
    """Retrieve relevant chunks from the knowledge base and generate a grounded answer.

    Args:
        query: natural language question
        candidates: ANN candidates from Qdrant; defaults to RAG_TOP_K_RETRIEVE
        top_n: chunks kept after reranking; defaults to RAG_TOP_K_RERANK

    Returns:
        {
            "answer": str,
            "citations": list[dict],
            "confidence": "high" | "low" | "none",
            "top_score": float (when chunks were retrieved),
            "usage": {prompt_tokens, completion_tokens, total_tokens},
        }
    """
    retriever = Retriever()
    chunks = await retriever.search(query, candidates=candidates, top_n=top_n)

    if not chunks:
        logger.info("rag_search: no retrieved chunks for query=%r", query[:80])
        return {
            "answer": "No relevant content found in the fitness knowledge base for this question.",
            "citations": [],
            "confidence": "none",
        }

    result = await generate_answer(query, chunks)
    logger.info(
        "rag_search: query=%r confidence=%s top_score=%s n_chunks=%d",
        query[:80],
        result.get("confidence"),
        result.get("top_score"),
        len(chunks),
    )
    return result
