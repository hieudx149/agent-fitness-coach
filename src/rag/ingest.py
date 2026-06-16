"""Ingest knowledge base markdown files into Qdrant.

Pipeline: read .md files → chunk → embed (FPT passages) → upsert to Qdrant.
Idempotent via deterministic point IDs from chunk hash — re-running overwrites
existing points rather than duplicating.
"""
import logging
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from src.config import get_settings
from src.llm.fpt_client import FPTClient
from src.rag.chunker import Chunk, chunk_markdown

logger = logging.getLogger(__name__)


def _ensure_collection(client: QdrantClient, name: str, dim: int, recreate: bool) -> None:
    existing = {c.name for c in client.get_collections().collections}
    if recreate and name in existing:
        client.delete_collection(name)
        existing.discard(name)
        logger.info("Dropped existing collection: %s", name)
    if name not in existing:
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection: %s (dim=%d, cosine)", name, dim)


def _collect_chunks(kb_dir: Path) -> list[Chunk]:
    all_chunks: list[Chunk] = []
    for md_file in sorted(kb_dir.glob("*.md")):
        file_chunks = chunk_markdown(md_file)
        logger.info(
            "Chunked %s → %d chunks (avg %d tokens)",
            md_file.name,
            len(file_chunks),
            sum(c.token_count for c in file_chunks) // max(len(file_chunks), 1),
        )
        all_chunks.extend(file_chunks)
    return all_chunks


async def ingest_directory(
    kb_dir: Path,
    qdrant_client: QdrantClient | None = None,
    fpt_client: FPTClient | None = None,
    recreate: bool = False,
) -> dict:
    settings = get_settings()
    qdrant_client = qdrant_client or QdrantClient(url=settings.qdrant_url)
    fpt_client = fpt_client or FPTClient()

    all_chunks = _collect_chunks(kb_dir)
    if not all_chunks:
        logger.warning("No markdown files found in %s", kb_dir)
        return {"chunks": 0, "files": 0, "collection": settings.qdrant_collection}

    logger.info("Embedding %d chunks via FPT (model=%s)...",
                len(all_chunks), fpt_client.embedding_model)
    embeddings = await fpt_client.embed(
        [c.text for c in all_chunks],
        input_type="passage",
    )

    _ensure_collection(
        qdrant_client,
        settings.qdrant_collection,
        settings.fpt_embedding_dimensions,
        recreate,
    )

    points = [
        PointStruct(
            id=chunk.chunk_id,
            vector=vector,
            payload={
                "source_file": chunk.source_file,
                "section_title": chunk.section_title,
                "text": chunk.text,
                "token_count": chunk.token_count,
                "chunk_index": chunk.chunk_index,
            },
        )
        for chunk, vector in zip(all_chunks, embeddings)
    ]
    qdrant_client.upsert(collection_name=settings.qdrant_collection, points=points)
    logger.info("Upserted %d points to '%s'", len(points), settings.qdrant_collection)

    return {
        "chunks": len(all_chunks),
        "files": len({c.source_file for c in all_chunks}),
        "collection": settings.qdrant_collection,
    }
