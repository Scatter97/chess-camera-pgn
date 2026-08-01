from __future__ import annotations

import chess
import numpy as np

from chess_camera_app.detection import local_detection
from chess_camera_app.detection import local_detection_runtime


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


def test_local_motion_does_not_wait_for_entire_board(monkeypatch) -> None:
    previous = np.zeros((120, 120, 3), dtype=np.uint8)
    current = np.full((120, 120, 3), 255, dtype=np.uint8)
    calls: list[bool] = []

    local_detection.STATE.last_sample_timestamp = -1.0

    def mark_sample(_previous, _current, now=None):
        calls.append(True)
        local_detection.STATE.current_unstable = frozenset(chess.SQUARES)
        return False

    monkeypatch.setattr(local_detection, "update_motion_state", mark_sample)

    assert (
        local_detection_runtime.local_frame_motion_score(
            previous,
            current,
            sample_timestamp=10.0,
        )
        == 0.0
    )
    assert calls == [True]

    # Reusing the same camera sample must not clear per-square motion state.
    assert (
        local_detection_runtime.local_frame_motion_score(
            previous,
            current,
            sample_timestamp=10.0,
        )
        == 0.0
    )
    assert calls == [True]


def test_toggle_settings_persist_immediately(tmp_path) -> None:
    config_path = tmp_path / "camera_config.json"
    config_path.write_text("{}", encoding="utf-8")

    local_detection_runtime.save_experimental_settings(
        config_path,
        True,
        "high",
    )

    assert local_detection.normalized_settings(config_path) == (True, "high")


def test_extended_occlusion_grace_covers_normal_detection_delay() -> None:
    local_detection_runtime.apply_extended_occlusion_grace()

    assert (
        local_detection.PROFILES["normal"].occlusion_grace_seconds
        >= 2.5
    )
