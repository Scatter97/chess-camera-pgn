from __future__ import annotations

import chess

import local_detection_runtime


def test_stable_move_requires_both_origin_and_destination() -> None:
    board = chess.Board()
    scores = {square: 0.0 for square in chess.SQUARES}
    scores[chess.E2] = 20.0

    assert not local_detection_runtime.stable_legal_move_visible(
        board,
        scores,
        frozenset(),
    )


def test_stable_move_allows_complete_legal_move_with_unrelated_motion() -> None:
    board = chess.Board()
    scores = {square: 0.0 for square in chess.SQUARES}
    scores[chess.E2] = 20.0
    scores[chess.E4] = 19.0
    scores[chess.A8] = 30.0

    assert local_detection_runtime.stable_legal_move_visible(
        board,
        scores,
        frozenset({chess.A8}),
    )


def test_unstable_destination_defers_move() -> None:
    board = chess.Board()
    scores = {square: 0.0 for square in chess.SQUARES}
    scores[chess.E2] = 20.0
    scores[chess.E4] = 19.0

    assert not local_detection_runtime.stable_legal_move_visible(
        board,
        scores,
        frozenset({chess.E4}),
    )
