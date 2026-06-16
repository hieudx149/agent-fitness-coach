from pathlib import Path

from src.rag.chunker import chunk_markdown, count_tokens


def _write_md(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_chunks_carry_h1_context(tmp_path: Path):
    md = """# Bench Press

## Overview

The bench press is a compound chest exercise.

## Form

Keep your shoulder blades retracted.
"""
    chunks = chunk_markdown(_write_md(tmp_path, "bench.md", md))

    assert len(chunks) >= 2
    for chunk in chunks:
        assert "Bench Press" in chunk.text, "H1 must be prepended for self-contained retrieval"
        assert chunk.source_file == "bench.md"


def test_sections_split_by_h2_title():
    md = """# Title

## Section Alpha

Alpha content.

## Section Beta

Beta content.
"""
    path = Path("__test_h2.md")
    path.write_text(md, encoding="utf-8")
    try:
        chunks = chunk_markdown(path)
        titles = {c.section_title for c in chunks}
        assert "Section Alpha" in titles
        assert "Section Beta" in titles
    finally:
        path.unlink(missing_ok=True)


def test_long_section_subchunks_with_overlap(tmp_path: Path):
    long_body = "This is a sentence of moderate length about lifting. " * 200
    md = f"# Long Doc\n\n## Body\n\n{long_body}"
    chunks = chunk_markdown(_write_md(tmp_path, "long.md", md), max_tokens=200, overlap_tokens=20)

    assert len(chunks) >= 2, "Long section must produce multiple chunks"
    for chunk in chunks:
        assert chunk.token_count <= 220, f"chunk exceeded budget: {chunk.token_count}"


def test_chunk_ids_are_deterministic(tmp_path: Path):
    md = "# Det\n\n## A\n\nstable content.\n\n## B\n\nmore content."
    first = chunk_markdown(_write_md(tmp_path, "det.md", md))
    second = chunk_markdown(_write_md(tmp_path, "det.md", md))

    assert [c.chunk_id for c in first] == [c.chunk_id for c in second]


def test_no_h2_falls_back_to_whole_doc(tmp_path: Path):
    md = "# Only H1\n\nSome content with no H2 headings."
    chunks = chunk_markdown(_write_md(tmp_path, "noh2.md", md))

    assert len(chunks) == 1
    assert "Only H1" in chunks[0].text


def test_count_tokens_returns_positive_int():
    assert count_tokens("hello world") > 0
    assert count_tokens("") == 0
