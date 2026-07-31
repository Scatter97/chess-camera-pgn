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


def test_filter_keeps_legal_move_and_hides_unrelated_motion() -> None:
    board = chess.Board()
    scores = {square: 0.0 for square in chess.SQUARES}
    scores[chess.E2] = 20.0
    scores[chess.E4] = 19.0
    scores[chess.A8] = 30.0

    filtered = local_detection_runtime.filter_change_scores(
        board,
        scores,
        frozenset({chess.A8}),
    )

    assert filtered[chess.E2] == 20.0
    assert filtered[chess.E4] == 19.0
    assert filtered[chess.A8] == 0.0


def test_filter_defers_incomplete_move_while_destination_moves() -> None:
    board = chess.Board()
    scores = {square: 0.0 for square in chess.SQUARES}
    scores[chess.E2] = 20.0
    scores[chess.E4] = 19.0

    filtered = local_detection_runtime.filter_change_scores(
        board,
        scores,
        frozenset({chess.E4}),
    )

    assert max(filtered.values()) == 0.0


def test_filter_passes_fully_stable_illegal_changes_for_recovery() -> None:
    board = chess.Board()
    scores = {square: 0.0 for square in chess.SQUARES}
    scores[chess.E2] = 20.0
    scores[chess.E5] = 19.0

    filtered = local_detection_runtime.filter_change_scores(
        board,
        scores,
        frozenset(),
    )

    assert filtered[chess.E2] == 20.0
    assert filtered[chess.E5] == 19.0
