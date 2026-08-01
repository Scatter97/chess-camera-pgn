from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path

import chess.pgn

from chess_camera_app.analysis.opening_book_builder import build_polyglot_book


DATASET_FILES = ("a.tsv", "b.tsv", "c.tsv", "d.tsv", "e.tsv")


def pgn_to_uci(pgn_text: str) -> str | None:
    document = f'[Result "*"]\n\n{pgn_text} *\n'
    game = chess.pgn.read_game(io.StringIO(document))
    if game is None or game.errors:
        return None
    return " ".join(move.uci() for move in game.mainline_moves())


def collect_lines(source_directory: Path) -> tuple[list[str], int]:
    lines: list[str] = []
    skipped = 0

    for filename in DATASET_FILES:
        path = source_directory / filename
        if not path.is_file():
            raise FileNotFoundError(f"Missing dataset file: {path}")

        print(f"Reading {path.name}...")
        with path.open("r", encoding="utf-8", newline="") as source:
            rows = csv.DictReader(source, delimiter="\t")
            for row in rows:
                pgn_text = (row.get("pgn") or "").strip()
                if not pgn_text:
                    continue
                uci = pgn_to_uci(pgn_text)
                if uci:
                    lines.append(uci)
                else:
                    skipped += 1

    return lines, skipped


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build a Polyglot opening book from the CC0 "
            "lichess-org/chess-openings TSV dataset."
        )
    )
    parser.add_argument(
        "source",
        type=Path,
        help="Path to a cloned lichess-org/chess-openings repository.",
    )
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        default=Path("books/chess_camera_default.bin"),
        help="Output Polyglot .bin path.",
    )
    args = parser.parse_args()

    lines, skipped = collect_lines(args.source)
    records = build_polyglot_book(lines, args.output)

    print()
    print(f"Created: {args.output}")
    print(f"Opening lines: {len(lines):,}")
    print(f"Polyglot records: {records:,}")
    print(f"Skipped invalid rows: {skipped:,}")
    print(f"File size: {args.output.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
