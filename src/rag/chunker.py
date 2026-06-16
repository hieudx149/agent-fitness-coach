"""Header-aware markdown chunker.

Strategy:
1. Split by H2 (`## `) headers — each section is a semantic unit (Form, Common Mistakes, etc).
2. If a section exceeds max_tokens, sub-chunk with token overlap.
3. Always prepend the H1 title so each chunk is self-contained for retrieval.

Token counting uses tiktoken cl100k_base as approximation — the FPT embedding
model (multilingual-e5-large) tokenizes differently, but cl100k is close enough
to keep chunks under the 512-token model limit safely.
"""
import hashlib
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import tiktoken

_ENCODER = tiktoken.get_encoding("cl100k_base")
_H1_RE = re.compile(r"^#\s+(.+?)$", re.MULTILINE)
_H2_SPLIT_RE = re.compile(r"^##\s+(.+?)$", re.MULTILINE)


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    source_file: str
    section_title: str
    text: str
    token_count: int
    chunk_index: int


def count_tokens(text: str) -> int:
    return len(_ENCODER.encode(text))


def _extract_h1(content: str) -> str:
    match = _H1_RE.search(content)
    return match.group(1).strip() if match else ""


def _split_by_h2(content: str, h1: str) -> list[tuple[str, str]]:
    """Returns [(section_title, section_text), ...] with H1 prepended to each section."""
    parts = _H2_SPLIT_RE.split(content)
    if len(parts) == 1:
        return [(h1 or "Document", content.strip())]

    sections: list[tuple[str, str]] = []
    preamble = parts[0].strip()
    if preamble:
        intro = f"# {h1}\n\n{preamble}" if h1 else preamble
        sections.append((h1 or "Introduction", intro))

    for title, body in zip(parts[1::2], parts[2::2]):
        title = title.strip()
        body = body.strip()
        section_text = f"# {h1}\n## {title}\n\n{body}" if h1 else f"## {title}\n\n{body}"
        sections.append((title, section_text))
    return sections


def _split_section_by_tokens(text: str, max_tokens: int, overlap: int) -> list[str]:
    """Sub-chunk a long section by token windows with overlap."""
    tokens = _ENCODER.encode(text)
    if len(tokens) <= max_tokens:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunks.append(_ENCODER.decode(tokens[start:end]))
        if end >= len(tokens):
            break
        start = end - overlap
    return chunks


def _make_chunk_id(source_file: str, chunk_index: int) -> str:
    """Deterministic UUID derived from source file + chunk position.

    Same file at same position always yields same ID — re-ingesting overwrites
    rather than duplicating in Qdrant.
    """
    raw = hashlib.sha256(f"{source_file}:{chunk_index}".encode()).hexdigest()
    return str(uuid.UUID(hex=raw[:32]))


def chunk_markdown(
    file_path: Path,
    max_tokens: int = 500,
    overlap_tokens: int = 50,
) -> list[Chunk]:
    content = file_path.read_text(encoding="utf-8")
    source_file = file_path.name
    h1 = _extract_h1(content)
    sections = _split_by_h2(content, h1)

    chunks: list[Chunk] = []
    chunk_index = 0
    for section_title, section_text in sections:
        sub_texts = _split_section_by_tokens(section_text, max_tokens, overlap_tokens)
        for sub_text in sub_texts:
            chunks.append(
                Chunk(
                    chunk_id=_make_chunk_id(source_file, chunk_index),
                    source_file=source_file,
                    section_title=section_title,
                    text=sub_text,
                    token_count=count_tokens(sub_text),
                    chunk_index=chunk_index,
                )
            )
            chunk_index += 1
    return chunks
