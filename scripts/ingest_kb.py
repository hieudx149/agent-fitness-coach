"""CLI: ingest knowledge base into Qdrant.

Usage (from project root):
    python -m scripts.ingest_kb [--kb-dir DIR] [--recreate]

Inside docker:
    docker compose exec api python -m scripts.ingest_kb --recreate
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

from src.rag.ingest import ingest_directory


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest knowledge base into Qdrant")
    parser.add_argument(
        "--kb-dir",
        type=Path,
        default=Path("knowledge_base"),
        help="Directory containing markdown files (default: ./knowledge_base)",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop and recreate the Qdrant collection before ingesting",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if not args.kb_dir.is_dir():
        print(f"ERROR: knowledge base directory not found: {args.kb_dir}", file=sys.stderr)
        return 1

    result = asyncio.run(ingest_directory(args.kb_dir, recreate=args.recreate))
    print(
        f"\nIngested {result['chunks']} chunks from {result['files']} files "
        f"into collection '{result['collection']}'"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
