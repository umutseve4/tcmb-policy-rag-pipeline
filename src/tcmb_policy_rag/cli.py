from __future__ import annotations

import argparse
from pathlib import Path

from .core import Store, format_result, grounded_answer, ingest_url


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TCMB PPK ingestion and cited retrieval")
    parser.add_argument("--database", type=Path, default=Path("data/policy.db"))
    subparsers = parser.add_subparsers(dest="command", required=True)
    ingest = subparsers.add_parser("ingest", help="ingest one TCMB PPK URL")
    ingest.add_argument("url")
    ingest.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    ask = subparsers.add_parser("ask", help="retrieve a citation-backed answer")
    ask.add_argument("question")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    store = Store(args.database)
    try:
        if args.command == "ingest":
            result = ingest_url(store, args.url, args.raw_dir)
        else:
            result = grounded_answer(store, args.question)
        print(format_result(result))
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
