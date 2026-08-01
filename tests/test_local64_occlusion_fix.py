from __future__ import annotations

import chess

from chess_camera_app.detection import local64_occlusion_fix
from chess_camera_app.detection import local_detection
from chess_camera_app.detection import local_detection_runtime


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


def test_normal_mode_accepts_standard_move_evidence() -> None:
    _reset("normal")
    board = chess.Board()
    scores = _scores()
    scores[chess.E2] = 7.5
    scores[chess.E4] = 7.5

    filtered = local64_occlusion_fix.filter_change_scores(
        board,
        scores,
        frozenset(),
    )

    assert filtered[chess.E2] == 7.5
    assert filtered[chess.E4] == 7.5


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


def test_moving_move_squares_do_not_become_persistently_blocked() -> None:
    _reset("normal")
    board = chess.Board()
    scores = _scores()
    paper = {
        square
        for square in chess.SQUARES
        if chess.square_file(square) <= 3
    }
    for square in paper:
        scores[square] = 30.0
    scores[chess.E2] = 18.0
    scores[chess.E4] = 17.0

    # While the move and obstruction are both moving, detection should wait.
    first = local64_occlusion_fix.filter_change_scores(
        board,
        scores,
        frozenset(paper.union({chess.E2, chess.E4})),
    )
    assert max(first.values()) == 0.0
    assert chess.E2 not in local_detection.STATE.blocked_squares
    assert chess.E4 not in local_detection.STATE.blocked_squares

    # Once the move squares settle, the same real move must become visible even
    # though the paper remains over the other half of the board.
    second = local64_occlusion_fix.filter_change_scores(
        board,
        scores,
        frozenset(),
    )
    assert second[chess.E2] == 18.0
    assert second[chess.E4] == 17.0


def test_install_replaces_runtime_filter() -> None:
    local_detection_runtime._occlusion_fix_installed = False
    local64_occlusion_fix.install()

    assert (
        local_detection_runtime.filter_change_scores
        is local64_occlusion_fix.filter_change_scores
    )
