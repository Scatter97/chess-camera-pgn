from __future__ import annotations

import chess

import local64_occlusion_fix
import local_detection
import local_detection_runtime


def _scores() -> dict[chess.Square, float]:
    return {square: 0.0 for square in chess.SQUARES}


def _reset(sensitivity: str = "low") -> None:
    local_detection.STATE.sensitivity = sensitivity
    local_detection.STATE.blocked_squares = frozenset()


def test_half_board_paper_is_masked_but_move_elsewhere_remains() -> None:
    _reset("low")
    board = chess.Board()
    scores = _scores()

    for square in chess.SQUARES:
        if chess.square_file(square) <= 3:
            scores[square] = 30.0
    scores[chess.E2] = 20.0
    scores[chess.E4] = 19.0

    filtered = local64_occlusion_fix.filter_change_scores(
        board,
        scores,
        frozenset(),
    )

    assert filtered[chess.E2] == 20.0
    assert filtered[chess.E4] == 19.0
    assert all(
        filtered[square] == 0.0
        for square in chess.SQUARES
        if chess.square_file(square) <= 3
    )


def test_half_board_paper_cannot_become_a_fake_move() -> None:
    _reset("low")
    board = chess.Board()
    scores = _scores()

    for square in chess.SQUARES:
        if chess.square_file(square) <= 3:
            scores[square] = 30.0

    filtered = local64_occlusion_fix.filter_change_scores(
        board,
        scores,
        frozenset(),
    )

    assert max(filtered.values()) == 0.0


def test_low_mode_rejects_weak_two_square_noise() -> None:
    _reset("low")
    board = chess.Board()
    scores = _scores()
    scores[chess.E2] = 8.0
    scores[chess.E4] = 8.0

    filtered = local64_occlusion_fix.filter_change_scores(
        board,
        scores,
        frozenset(),
    )

    assert max(filtered.values()) == 0.0


def test_high_mode_accepts_the_same_responsive_move_evidence() -> None:
    _reset("high")
    board = chess.Board()
    scores = _scores()
    scores[chess.E2] = 8.0
    scores[chess.E4] = 8.0

    filtered = local64_occlusion_fix.filter_change_scores(
        board,
        scores,
        frozenset(),
    )

    assert filtered[chess.E2] == 8.0
    assert filtered[chess.E4] == 8.0


def test_install_replaces_runtime_filter() -> None:
    local_detection_runtime._occlusion_fix_installed = False
    local64_occlusion_fix.install()

    assert (
        local_detection_runtime.filter_change_scores
        is local64_occlusion_fix.filter_change_scores
    )
