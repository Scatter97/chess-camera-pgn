from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import chess
import numpy as np

from chess_camera_app.detection import local_detection
from chess_camera_app.detection import local_detection_v2 as v2
from chess_camera_app.game.chess_tracker import BOARD_MARGIN_PIXELS, SQUARE_PIXELS


def _frame() -> np.ndarray:
    size = BOARD_MARGIN_PIXELS * 2 + SQUARE_PIXELS * 8
    return np.zeros((size, size, 3), dtype=np.uint8)


def _paint_square(
    frame: np.ndarray,
    square: chess.Square,
    value: int = 220,
    fraction: float = 0.34,
) -> None:
    file_index = chess.square_file(square)
    rank_from_top = 7 - chess.square_rank(square)
    center_x = (
        BOARD_MARGIN_PIXELS
        + file_index * SQUARE_PIXELS
        + SQUARE_PIXELS // 2
    )
    center_y = (
        BOARD_MARGIN_PIXELS
        + rank_from_top * SQUARE_PIXELS
        + SQUARE_PIXELS // 2
    )
    radius = max(2, int(SQUARE_PIXELS * fraction / 2.0))
    frame[
        center_y - radius : center_y + radius,
        center_x - radius : center_x + radius,
    ] = value


def test_every_square_maps_to_one_two_by_two_zone() -> None:
    zones = {v2.zone_for_square(square) for square in chess.SQUARES}
    assert zones == set(range(16))
    assert all(len(v2.squares_for_zone(zone)) == 4 for zone in zones)
    assert v2.zone_for_square(chess.A8) == 0
    assert v2.zone_for_square(chess.H1) == 15


def test_unrelated_moving_zone_does_not_hide_stable_move_squares() -> None:
    local_detection.STATE.sensitivity = "normal"
    reference = _frame()
    current = reference.copy()
    _paint_square(current, chess.E2)
    _paint_square(current, chess.E4)
    previous = current.copy()
    _paint_square(current, chess.A8, fraction=0.50)

    v2.RUNTIME.reset(reference, 0.0)
    scores = v2.observe(reference, previous, current, 0.25)

    assert scores[chess.E2] > 0
    assert scores[chess.E4] > 0
    assert scores[chess.A8] == 0
    assert (
        v2.RUNTIME.zone_status[v2.zone_for_square(chess.A8)]
        == v2.ZoneStatus.MOVING
    )
    assert (
        v2.RUNTIME.zone_status[v2.zone_for_square(chess.E2)]
        == v2.ZoneStatus.CLEAR
    )


def test_stationary_broad_object_marks_zone_blocked() -> None:
    local_detection.STATE.sensitivity = "normal"
    reference = _frame()
    current = reference.copy()
    x0, y0, x1, y1 = v2.zone_bounds(0)
    current[y0:y1, x0:x1] = 180

    v2.RUNTIME.reset(reference, 0.0)
    scores = v2.observe(reference, current.copy(), current, 0.25)

    assert v2.RUNTIME.zone_status[0] == v2.ZoneStatus.BLOCKED
    assert all(scores[square] == 0 for square in v2.squares_for_zone(0))


def test_rolling_buffer_prunes_snapshots_older_than_ten_seconds() -> None:
    frame = np.zeros((8, 8, 3), dtype=np.uint8)
    v2.RUNTIME.snapshots.clear()
    v2.RUNTIME.events.clear()
    v2.RUNTIME.snapshots.append(
        v2.BoardSnapshot(0.0, frame, tuple(), {})
    )
    v2.RUNTIME.snapshots.append(
        v2.BoardSnapshot(5.0, frame, tuple(), {})
    )
    v2.RUNTIME.events.append(
        v2.TemporalEvent(
            0.0,
            frozenset({chess.E2}),
            {chess.E2: 9.0},
            0.8,
        )
    )

    v2._prune(10.1)

    assert [item.timestamp for item in v2.RUNTIME.snapshots] == [5.0]
    assert not v2.RUNTIME.events


def test_multi_move_bridge_adds_temporal_evidence_for_hidden_squares() -> None:
    @dataclass(frozen=True)
    class ChangeEvent:
        timestamp: float
        squares: frozenset[chess.Square]
        scores: dict[chess.Square, float]
        confidence: float

    captured: dict[str, object] = {}

    def search_sequences(board, scores, events=(), **kwargs):
        captured["scores"] = scores
        captured["events"] = tuple(events)
        captured["kwargs"] = kwargs
        return "ok"

    module = SimpleNamespace(
        ChangeEvent=ChangeEvent,
        search_sequences=search_sequences,
    )
    v2.RUNTIME.latest_scores = {
        square: 0.0 for square in chess.SQUARES
    }
    v2.RUNTIME.latest_known_squares = frozenset(
        set(chess.SQUARES) - {chess.E2}
    )
    v2.RUNTIME.events.clear()
    v2.RUNTIME.events.append(
        v2.TemporalEvent(
            1.0,
            frozenset({chess.E2}),
            {chess.E2: 15.0},
            0.9,
        )
    )

    v2.install_multi_move(module)
    result = module.search_sequences(chess.Board(), {}, max_depth=3)

    assert result == "ok"
    assert captured["scores"][chess.E2] == 15.0
    assert len(captured["events"]) == 1
    assert captured["kwargs"] == {"max_depth": 3}
