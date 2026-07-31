from __future__ import annotations

from types import ModuleType

import chess
import numpy as np

import camera_advanced
import local_detection
from chess_tracker import move_changed_squares


def stable_legal_move_visible(
    board: chess.Board,
    scores: dict[chess.Square, float],
    unstable: frozenset[chess.Square],
) -> bool:
    """Return True only when a complete legal move has stable visual evidence."""
    for move in board.legal_moves:
        expected = move_changed_squares(board, move)
        if expected.intersection(unstable):
            continue
        required_visible = min(2, len(expected))
        visible = sum(
            1
            for square in expected
            if scores.get(square, 0.0) >= 7.0
        )
        if visible >= required_visible:
            return True
    return False


def install(target: ModuleType) -> None:
    """Add distinct-sample timing and affected-square stability safeguards."""
    if getattr(target, "_local_detection_runtime_installed", False):
        return

    original_open = target.open_camera
    original_frame_motion = target.frame_motion_score
    original_square_change_scores = target.square_change_scores
    original_virtual_board = target.render_virtual_board

    state = local_detection.STATE
    state.board = None
    state.last_sample_timestamp = -1.0

    def open_camera(index: int):
        state.board = None
        state.last_sample_timestamp = -1.0
        return original_open(index)

    def frame_motion(
        previous: np.ndarray,
        current: np.ndarray,
        sample_step: int = 3,
    ) -> float:
        if not state.enabled:
            return original_frame_motion(previous, current, sample_step)

        sample_timestamp = camera_advanced.RUNTIME.last_detection
        profile = local_detection.PROFILES[state.sensitivity]
        if sample_timestamp == state.last_sample_timestamp:
            ready = (
                len(state.current_unstable)
                <= profile.max_unstable_squares
            )
            return 0.0 if ready else 10.0

        state.last_sample_timestamp = sample_timestamp
        return original_frame_motion(previous, current, sample_step)

    def square_change_scores(
        reference: np.ndarray,
        current: np.ndarray,
    ) -> dict[chess.Square, float]:
        raw_scores = original_square_change_scores(reference, current)
        if not state.enabled:
            return raw_scores

        filtered = {
            square: (
                0.0
                if square in state.current_unstable
                else value
            )
            for square, value in raw_scores.items()
        }
        board = state.board
        if board is None:
            return filtered
        if stable_legal_move_visible(
            board,
            filtered,
            state.current_unstable,
        ):
            return filtered

        # The hand is still over an affected square or only part of a move is
        # visible. Zero evidence makes the main loop wait instead of raising an
        # illegal-move warning before the move squares have settled.
        return {square: 0.0 for square in chess.SQUARES}

    def render_virtual_board(
        board: chess.Board,
        last_move: chess.Move | None = None,
        suggested_move: chess.Move | None = None,
    ) -> np.ndarray:
        state.board = board.copy(stack=False)
        return original_virtual_board(
            board,
            last_move,
            suggested_move,
        )

    target.open_camera = open_camera
    target.frame_motion_score = frame_motion
    target.square_change_scores = square_change_scores
    target.render_virtual_board = render_virtual_board

    # Accuracy Boost calls the score function stored by local_detection.
    state.original_square_change_scores = square_change_scores
    target._local_detection_runtime_installed = True
