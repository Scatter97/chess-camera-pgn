from pathlib import Path

import chess
import chess.pgn

from clock_reader import format_pgn_clock, parse_clock_text
from chess_tracker import (
    legal_move_fit,
    move_changed_squares,
    rank_legal_moves,
    write_pgn,
)


def blank_scores() -> dict[int, float]:
    return {square: 0.0 for square in chess.SQUARES}


def test_normal_move_changes_two_squares() -> None:
    board = chess.Board()
    move = chess.Move.from_uci("e2e4")
    assert move_changed_squares(board, move) == {chess.E2, chess.E4}


def test_castling_includes_rook_squares() -> None:
    board = chess.Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    move = chess.Move.from_uci("e1g1")
    assert move_changed_squares(board, move) == {
        chess.E1,
        chess.G1,
        chess.H1,
        chess.F1,
    }


def test_en_passant_includes_captured_pawn() -> None:
    board = chess.Board("8/8/8/3pP3/8/8/8/4K2k w - d6 0 1")
    move = chess.Move.from_uci("e5d6")
    assert move_changed_squares(board, move) == {
        chess.E5,
        chess.D6,
        chess.D5,
    }


def test_ranker_finds_e2e4() -> None:
    board = chess.Board()
    scores = blank_scores()
    scores[chess.E2] = 25.0
    scores[chess.E4] = 23.0
    ranked = rank_legal_moves(board, scores)
    assert ranked[0].move == chess.Move.from_uci("e2e4")


def test_legal_move_has_high_fit() -> None:
    board = chess.Board()
    scores = blank_scores()
    scores[chess.E2] = 25.0
    scores[chess.E4] = 23.0
    candidate = rank_legal_moves(board, scores)[0]
    assert legal_move_fit(candidate, scores).score > 0.9


def test_illegal_move_has_low_fit() -> None:
    board = chess.Board()
    scores = blank_scores()
    scores[chess.E2] = 25.0
    scores[chess.E5] = 24.0  # e2-e5 is not legal from the starting position
    candidate = rank_legal_moves(board, scores)[0]
    assert legal_move_fit(candidate, scores).score < 0.66


def test_pgn_round_trip(tmp_path: Path) -> None:
    moves = [
        chess.Move.from_uci("e2e4"),
        chess.Move.from_uci("e7e5"),
        chess.Move.from_uci("g1f3"),
    ]
    target = tmp_path / "game.pgn"
    write_pgn(moves, target)

    with target.open(encoding="utf-8") as source:
        game = chess.pgn.read_game(source)
    assert game is not None
    assert list(game.mainline_moves()) == moves


def test_clock_text_parsing_and_formatting() -> None:
    assert parse_clock_text("0:59") == 59
    assert parse_clock_text("10:00") == 600
    assert parse_clock_text("1:02:03") == 3723
    assert parse_clock_text("9.8") == 9.8
    assert format_pgn_clock(59) == "0:00:59"
    assert format_pgn_clock(65.4) == "0:01:05.4"


def test_pgn_contains_per_move_clocks(tmp_path: Path) -> None:
    moves = [chess.Move.from_uci("e2e4"), chess.Move.from_uci("e7e5")]
    target = tmp_path / "timed_game.pgn"
    write_pgn(moves, target, clocks=[59.0, 58.4])
    text = target.read_text(encoding="utf-8")
    assert "[%clk 0:00:59]" in text
    assert "[%clk 0:00:58.4]" in text
