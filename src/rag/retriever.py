"""Two-stage retriever: Qdrant ANN search → FPT cross-encoder rerank.

Why two stages? Embedding-only retrieval surfaces lexically/semantically
close chunks but can miss the *most* relevant one when the top-k is small.
Reranking with a cross-encoder (bge-reranker-v2-m3) scores each candidate
against the query directly, giving us a sharper top-N at minimal extra cost.
"""
import logging
from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient

from src.config import get_settings
from src.llm.fpt_client import FPTClient

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    text: str
    source_file: str
    section_title: str
    chunk_id: str
    score: float  # rerank score in [0, 1]


class Retriever:
    def __init__(
        self,
        qdrant_client: AsyncQdrantClient | None = None,
        fpt_client: FPTClient | None = None,
    ):
        settings = get_settings()
        self.qdrant_client = qdrant_client or AsyncQdrantClient(url=settings.qdrant_url)
        self.fpt_client = fpt_client or FPTClient()
        self.collection = settings.qdrant_collection

    async def search(
        self,
        query: str,
        candidates: int | None = None,
        top_n: int | None = None,
    ) -> list[RetrievedChunk]:
        """Two-stage retrieve. None args fall back to RAG_TOP_K_RETRIEVE / RAG_TOP_K_RERANK."""
        settings = get_settings()
        candidates = candidates if candidates is not None else settings.rag_top_k_retrieve
        top_n = top_n if top_n is not None else settings.rag_top_k_rerank

        query_vec = await self.fpt_client.embed_query(query)

        response = await self.qdrant_client.query_points(
            collection_name=self.collection,
            query=query_vec,
            limit=candidates,
            with_payload=True,
        )
        hits = response.points
        if not hits:
            logger.info("No Qdrant hits for query: %s", query[:80])
            return []

        documents = [h.payload["text"] for h in hits]
        ranked = await self.fpt_client.rerank(query, documents, top_n=top_n)

        results: list[RetrievedChunk] = []
        for original_idx, score in ranked:
            hit = hits[original_idx]
            results.append(
                RetrievedChunk(
                    text=hit.payload["text"],
                    source_file=hit.payload["source_file"],
                    section_title=hit.payload["section_title"],
                    chunk_id=str(hit.id),
                    score=score,
                )
            )
        return results
