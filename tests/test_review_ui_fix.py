from __future__ import annotations

import chess

from review_ui_fix import board_after_selected_move


def test_review_board_includes_selected_move() -> None:
    moves = [
        chess.Move.from_uci("e2e4"),
        chess.Move.from_uci("e7e5"),
        chess.Move.from_uci("g1f3"),
    ]

    after_first = board_after_selected_move(moves, 0)
    assert after_first.piece_at(chess.E4) == chess.Piece(chess.PAWN, chess.WHITE)
    assert after_first.piece_at(chess.E2) is None
    assert after_first.turn == chess.BLACK

    after_second = board_after_selected_move(moves, 1)
    assert after_second.piece_at(chess.E5) == chess.Piece(chess.PAWN, chess.BLACK)
    assert after_second.turn == chess.WHITE


def test_review_board_clamps_selected_index() -> None:
    moves = [chess.Move.from_uci("h2h4")]
    board = board_after_selected_move(moves, 99)
    assert board.piece_at(chess.H4) == chess.Piece(chess.PAWN, chess.WHITE)
