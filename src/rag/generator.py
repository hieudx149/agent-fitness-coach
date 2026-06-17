"""Grounded answer generator: retrieved chunks + question → LLM answer with citations.

Design:
- The LLM sees the chunks formatted with `[n]` indices so it can cite inline.
- The system prompt enforces context-only answering and refusal on insufficient info.
- We attach a structured citations[] payload regardless of what the model writes
  inline — that way the UI can render source cards even if the model forgets to
  cite, and downstream evaluation (source_attribution metric) has something
  deterministic to check.
"""
import logging
from typing import Any

from src.config import get_settings
from src.llm.openai_client import get_openai_client
from src.rag.retriever import RetrievedChunk

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a fitness knowledge assistant. Answer using ONLY the provided context excerpts.

Rules:
1. If the context does not contain enough information, say so explicitly. Do not invent facts or rely on outside knowledge.
2. Cite sources inline using bracketed references like [1], [2] matching the context numbering.
3. Be concise and specific. Reference exercise names, rep ranges, and principles when relevant.
4. If the question is off-topic from fitness, strength training, or workout programming, respond that it is out of scope rather than guessing."""


def _format_context(chunks: list[RetrievedChunk]) -> str:
    blocks = []
    for i, chunk in enumerate(chunks, 1):
        header = f"[{i}] Source: {chunk.source_file} — Section: {chunk.section_title}"
        blocks.append(f"{header}\n{chunk.text}")
    return "\n\n---\n\n".join(blocks)


def _build_citations(chunks: list[RetrievedChunk]) -> list[dict[str, Any]]:
    return [
        {
            "index": i,
            "source_file": chunk.source_file,
            "section_title": chunk.section_title,
            "chunk_id": chunk.chunk_id,
            "score": round(chunk.score, 4),
            "snippet": chunk.text[:240] + ("..." if len(chunk.text) > 240 else ""),
        }
        for i, chunk in enumerate(chunks, 1)
    ]


async def generate_answer(
    question: str,
    chunks: list[RetrievedChunk],
) -> dict[str, Any]:
    if not chunks:
        return {
            "answer": "I don't have enough information in the knowledge base to answer that.",
            "citations": [],
            "confidence": "none",
        }

    settings = get_settings()
    client = get_openai_client()

    context = _format_context(chunks)
    user_message = f"Context:\n\n{context}\n\nQuestion: {question}"

    response = await client.chat.completions.create(
        model=settings.openai_chat_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=settings.llm_temperature,
        top_p=settings.llm_top_p,
        max_tokens=600,
    )
    answer = (response.choices[0].message.content or "").strip()

    top_score = chunks[0].score
    confidence = "high" if top_score >= settings.rag_rerank_threshold else "low"

    return {
        "answer": answer,
        "citations": _build_citations(chunks),
        "confidence": confidence,
        "top_score": round(top_score, 4),
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        },
    }
