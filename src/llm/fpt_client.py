"""Async client for FPT Cloud embedding and reranking APIs.

API spec reference: specs/FPT_AI_Model.md.
Used by RAG ingest (passage embeddings), retriever (query embeddings + rerank).
"""
import asyncio
import logging
from typing import Literal

import httpx

from src.config import get_settings

logger = logging.getLogger(__name__)


class FPTClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 3,
    ):
        settings = get_settings()
        self.api_key = api_key or settings.fpt_api_key
        self.base_url = (base_url or settings.fpt_base_url).rstrip("/")
        self.embedding_model = settings.fpt_embedding_model
        self.embedding_dimensions = settings.fpt_embedding_dimensions
        self.reranker_model = settings.fpt_reranker_model
        self.timeout = timeout
        self.max_retries = max_retries

        if not self.api_key:
            raise ValueError("FPT_API_KEY is required (set in .env)")

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def _request_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        payload: dict,
    ) -> dict:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = await client.post(
                    url,
                    json=payload,
                    headers=self._headers,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt == self.max_retries - 1:
                    break
                wait = 2**attempt
                logger.warning(
                    "FPT request failed (attempt %d/%d): %s — retrying in %ds",
                    attempt + 1,
                    self.max_retries,
                    exc,
                    wait,
                )
                await asyncio.sleep(wait)
        assert last_exc is not None
        raise last_exc

    async def embed(
        self,
        texts: list[str],
        input_type: Literal["passage", "query"] = "passage",
        batch_size: int = 32,
    ) -> list[list[float]]:
        """Embed a list of texts. Auto-batches if list exceeds batch_size."""
        if not texts:
            return []

        url = f"{self.base_url}/embeddings"
        embeddings: list[list[float]] = []

        async with httpx.AsyncClient() as client:
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                payload = {
                    "model": self.embedding_model,
                    "input": batch,
                    "dimensions": self.embedding_dimensions,
                    "encoding_format": "float",
                    "input_text_truncate": "end",
                    "input_type": input_type,
                }
                data = await self._request_with_retry(client, url, payload)
                for item in data["data"]:
                    embeddings.append(item["embedding"])

        if len(embeddings) != len(texts):
            raise RuntimeError(
                f"FPT returned {len(embeddings)} embeddings for {len(texts)} inputs"
            )
        return embeddings

    async def embed_query(self, query: str) -> list[float]:
        results = await self.embed([query], input_type="query")
        return results[0]

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[tuple[int, float]]:
        """Rerank documents by relevance to query.

        Returns list of (original_index, relevance_score) sorted desc by score.
        """
        if not documents:
            return []

        url = f"{self.base_url}/rerank"
        payload = {
            "model": self.reranker_model,
            "query": query,
            "documents": documents,
            "top_n": top_n if top_n is not None else len(documents),
        }
        async with httpx.AsyncClient() as client:
            data = await self._request_with_retry(client, url, payload)

        return [(item["index"], item["relevance_score"]) for item in data["results"]]
