from __future__ import annotations

import json
import time

import chess
import numpy as np

import local_detection
from chess_tracker import RankedMove, move_changed_squares


def reset_state() -> None:
    local_detection.STATE.enabled = True
    local_detection.STATE.sensitivity = "normal"
    local_detection.STATE.current_unstable = frozenset()
    local_detection.STATE.ignore_until.clear()
    local_detection.STATE.last_motion_scores.clear()


def test_settings_default_off_and_normal(tmp_path) -> None:
    config = tmp_path / "camera_config.json"
    assert local_detection.normalized_settings(config) == (False, "normal")


def test_settings_load_saved_beta_values(tmp_path) -> None:
    config = tmp_path / "camera_config.json"
    config.write_text(
        json.dumps(
            {
                "local_detection_beta": True,
                "local_detection_sensitivity": "high",
            }
        ),
        encoding="utf-8",
    )
    assert local_detection.normalized_settings(config) == (True, "high")


def test_local_motion_allows_unrelated_square_to_move() -> None:
    reset_state()
    previous = np.zeros((1000, 1000, 3), dtype=np.uint8)
    current = previous.copy()
    current[110:190, 110:190] = 255

    ready = local_detection.update_motion_state(previous, current, now=10.0)

    assert ready
    assert chess.A8 in local_detection.STATE.current_unstable


def test_local_motion_rejects_too_many_unstable_squares() -> None:
    reset_state()
    previous = np.zeros((1000, 1000, 3), dtype=np.uint8)
    current = previous.copy()
    for file_index in range(8):
        for rank_from_top in range(2):
            y0 = 100 + rank_from_top * 100 + 10
            x0 = 100 + file_index * 100 + 10
            current[y0 : y0 + 80, x0 : x0 + 80] = 255

    assert not local_detection.update_motion_state(
        previous,
        current,
        now=10.0,
    )


def test_candidate_scores_keep_move_squares_and_ignore_moving_hand() -> None:
    reset_state()
    board = chess.Board()
    move = chess.Move.from_uci("e2e4")
    expected = move_changed_squares(board, move)
    local_detection.STATE.current_unstable = frozenset({chess.A8})
    local_detection.STATE.ignore_until[chess.A8] = time.monotonic() + 5.0

    scores = {square: 0.0 for square in chess.SQUARES}
    scores[chess.E2] = 20.0
    scores[chess.E4] = 19.0
    scores[chess.A8] = 30.0

    filtered = local_detection.scores_for_candidate(scores, expected)

    assert filtered[chess.E2] == 20.0
    assert filtered[chess.E4] == 19.0
    assert filtered[chess.A8] == 0.0


def test_legal_move_fit_ignores_unrelated_recent_motion() -> None:
    reset_state()
    board = chess.Board()
    move = chess.Move.from_uci("e2e4")
    expected = move_changed_squares(board, move)
    candidate = RankedMove(move, 0.0, expected)
    local_detection.STATE.current_unstable = frozenset({chess.A8})
    local_detection.STATE.ignore_until[chess.A8] = time.monotonic() + 5.0

    scores = {square: 0.0 for square in chess.SQUARES}
    scores[chess.E2] = 20.0
    scores[chess.E4] = 20.0
    scores[chess.A8] = 30.0

    fit = local_detection.legal_move_fit(candidate, scores)

    assert fit.score == 1.0
    assert fit.explained_squares == expected


def test_castling_and_en_passant_expected_squares_are_preserved() -> None:
    reset_state()

    castle_board = chess.Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    castle = chess.Move.from_uci("e1g1")
    castle_expected = move_changed_squares(castle_board, castle)
    assert castle_expected == frozenset(
        {chess.E1, chess.G1, chess.H1, chess.F1}
    )

    ep_board = chess.Board("8/8/8/3pP3/8/8/8/8 w - d6 0 1")
    en_passant = chess.Move.from_uci("e5d6")
    ep_expected = move_changed_squares(ep_board, en_passant)
    assert ep_expected == frozenset(
        {chess.E5, chess.D6, chess.D5}
    )
