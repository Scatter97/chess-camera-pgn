from __future__ import annotations

import csv
import struct
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

import chess
import chess.polyglot


ENTRY_STRUCT = struct.Struct(">QHHI")


def encode_polyglot_move(board: chess.Board, move: chess.Move) -> int:
    """Encode a legal standard-chess move using the Polyglot move format."""
    from_square = move.from_square
    to_square = move.to_square

    if board.is_kingside_castling(move):
        to_square = chess.H1 if board.turn == chess.WHITE else chess.H8
    elif board.is_queenside_castling(move):
        to_square = chess.A1 if board.turn == chess.WHITE else chess.A8

    promotion = move.promotion - 1 if move.promotion else 0
    return to_square | (from_square << 6) | (promotion << 12)


def count_uci_lines(uci_lines: Iterable[str]) -> Counter[tuple[int, int]]:
    """Count position/move pairs from legal UCI opening lines."""
    counts: Counter[tuple[int, int]] = Counter()

    for line_number, raw_line in enumerate(uci_lines, start=1):
        line = raw_line.strip()
        if not line:
            continue

        board = chess.Board()
        for token in line.split():
            try:
                move = chess.Move.from_uci(token)
            except ValueError as error:
                raise ValueError(
                    f"Invalid UCI move {token!r} on opening line {line_number}."
                ) from error

            if move not in board.legal_moves:
                raise ValueError(
                    f"Illegal move {token!r} on opening line {line_number}: "
                    f"{board.fen()}"
                )

            key = chess.polyglot.zobrist_hash(board)
            raw_move = encode_polyglot_move(board, move)
            counts[(key, raw_move)] += 1
            board.push(move)

    return counts


def write_polyglot_book(
    counts: Counter[tuple[int, int]],
    output_path: Path,
) -> int:
    """Write sorted Polyglot records and return the number of records."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    sorted_entries = sorted(
        counts.items(),
        key=lambda item: (item[0][0], item[0][1]),
    )

    with temporary_path.open("wb") as output:
        for (key, raw_move), count in sorted_entries:
            weight = min(65_535, max(1, count))
            output.write(ENTRY_STRUCT.pack(key, raw_move, weight, 0))

    temporary_path.replace(output_path)

    # Verify that python-chess can open the generated file.
    with chess.polyglot.open_reader(str(output_path)) as reader:
        list(reader.find_all(chess.Board()))

    return len(sorted_entries)


def build_polyglot_book(
    uci_lines: Iterable[str],
    output_path: Path,
) -> int:
    return write_polyglot_book(count_uci_lines(uci_lines), output_path)


def build_polyglot_book_from_tsv(
    source_path: Path,
    output_path: Path,
) -> int:
    """Build a book from a TSV file containing a column named ``uci``."""
    with source_path.open("r", encoding="utf-8", newline="") as source:
        rows = csv.DictReader(source, delimiter="\t")
        if rows.fieldnames is None or "uci" not in rows.fieldnames:
            raise ValueError(f"{source_path} must contain a tab-separated 'uci' column.")
        lines = [
            (row.get("uci") or "").strip()
            for row in rows
            if (row.get("uci") or "").strip()
        ]

    if not lines:
        raise ValueError(f"{source_path} contains no opening lines.")

    return build_polyglot_book(lines, output_path)
