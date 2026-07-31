from __future__ import annotations

import itertools
import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Iterable

import chess
import cv2
import numpy as np

from chess_tracker import move_changed_squares, square_change_scores
from pregame_ui import Button, clicked_action, draw_button


ENABLED_KEY = "experimental_multi_move_enabled"
MAX_DEPTH_KEY = "experimental_multi_move_max_depth"
AUTO_ACCEPT_KEY = "experimental_multi_move_auto_accept"
AUTO_THRESHOLD_KEY = "experimental_multi_move_auto_threshold"

DEFAULT_MAX_DEPTH = 3
DEFAULT_AUTO_THRESHOLD = 0.97
MIN_AUTO_THRESHOLD = 0.80
MAX_AUTO_THRESHOLD = 0.995
DEFAULT_BEAM_WIDTH = 140
DEFAULT_MIN_POSITION_FIT = 0.62


@dataclass(frozen=True)
class RecoverySettings:
    enabled: bool = False
    max_depth: int = DEFAULT_MAX_DEPTH
    auto_accept: bool = False
    auto_threshold: float = DEFAULT_AUTO_THRESHOLD
    beam_width: int = DEFAULT_BEAM_WIDTH
    min_position_fit: float = DEFAULT_MIN_POSITION_FIT


@dataclass(frozen=True)
class ChangeEvent:
    timestamp: float
    squares: frozenset[chess.Square]
    scores: dict[chess.Square, float]
    confidence: float


@dataclass(frozen=True)
class SequenceCandidate:
    moves: tuple[chess.Move, ...]
    final_board: chess.Board
    expected_squares: frozenset[chess.Square]
    final_position_score: float
    temporal_score: float
    change_score: float
    total_score: float


@dataclass(frozen=True)
class MultiMoveRecoveryResult:
    candidates: tuple[SequenceCandidate, ...]
    confidence: float
    ambiguous: bool
    observed_squares: frozenset[chess.Square]


@dataclass(frozen=True)
class _SearchNode:
    board: chess.Board
    moves: tuple[chess.Move, ...]
    move_square_sets: tuple[frozenset[chess.Square], ...]
    priority: float


def _read_config(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, TypeError, ValueError):
        return {}


def _write_config(path: Path, config: dict[str, object]) -> None:
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")


def load_settings(path: Path) -> RecoverySettings:
    config = _read_config(path)
    try:
        depth = int(config.get(MAX_DEPTH_KEY, DEFAULT_MAX_DEPTH))
    except (TypeError, ValueError):
        depth = DEFAULT_MAX_DEPTH
    depth = min(3, max(2, depth))
    try:
        threshold = float(config.get(AUTO_THRESHOLD_KEY, DEFAULT_AUTO_THRESHOLD))
    except (TypeError, ValueError):
        threshold = DEFAULT_AUTO_THRESHOLD
    threshold = min(MAX_AUTO_THRESHOLD, max(MIN_AUTO_THRESHOLD, threshold))
    return RecoverySettings(
        enabled=bool(config.get(ENABLED_KEY, False)),
        max_depth=depth,
        auto_accept=bool(config.get(AUTO_ACCEPT_KEY, False)),
        auto_threshold=threshold,
    )


def save_settings(path: Path, settings: RecoverySettings) -> None:
    config = _read_config(path)
    config[ENABLED_KEY] = bool(settings.enabled)
    config[MAX_DEPTH_KEY] = min(3, max(2, int(settings.max_depth)))
    config[AUTO_ACCEPT_KEY] = bool(settings.auto_accept)
    config[AUTO_THRESHOLD_KEY] = min(
        MAX_AUTO_THRESHOLD,
        max(MIN_AUTO_THRESHOLD, float(settings.auto_threshold)),
    )
    _write_config(path, config)


def active_squares(
    scores: dict[chess.Square, float],
) -> frozenset[chess.Square]:
    strongest = max(scores.values(), default=0.0)
    if strongest < 7.0:
        return frozenset()
    threshold = max(7.0, strongest * 0.34)
    return frozenset(square for square, value in scores.items() if value >= threshold)


def position_changed_squares(
    before: chess.Board,
    after: chess.Board,
) -> frozenset[chess.Square]:
    return frozenset(
        square
        for square in chess.SQUARES
        if before.piece_at(square) != after.piece_at(square)
    )


def _position_fit(
    expected: frozenset[chess.Square],
    scores: dict[chess.Square, float],
) -> tuple[float, frozenset[chess.Square]]:
    observed = active_squares(scores)
    if not expected or not observed:
        return 0.0, observed

    strongest = max(scores.values(), default=0.0)
    threshold = max(7.0, strongest * 0.34)
    explained = observed.intersection(expected)
    observed_energy = sum(scores[square] for square in observed)
    explained_energy = sum(scores[square] for square in explained)
    precision = explained_energy / observed_energy if observed_energy else 0.0
    coverage = len(explained) / max(1, len(expected))
    visibility = float(
        np.mean(
            [min(1.0, scores[square] / threshold) for square in expected]
        )
    )
    fit = (0.52 * precision) + (0.33 * coverage) + (0.15 * visibility)
    return float(min(1.0, max(0.0, fit))), observed


def _change_quality(
    expected: frozenset[chess.Square],
    scores: dict[chess.Square, float],
) -> float:
    if not expected:
        return 0.0
    expected_values = [scores.get(square, 0.0) for square in expected]
    unexpected_values = sorted(
        (
            value
            for square, value in scores.items()
            if square not in expected
        ),
        reverse=True,
    )[: max(2, min(5, len(expected)))]
    explained = float(np.mean(expected_values)) if expected_values else 0.0
    unexpected = float(np.mean(unexpected_values)) if unexpected_values else 0.0
    evidence = min(1.0, explained / 18.0)
    cleanliness = explained / max(1.0, explained + unexpected)
    return float((0.65 * evidence) + (0.35 * cleanliness))


def _event_similarity(
    expected: frozenset[chess.Square],
    event: ChangeEvent,
) -> float:
    if not expected or not event.squares:
        return 0.0
    intersection = expected.intersection(event.squares)
    precision = len(intersection) / len(event.squares)
    recall = len(intersection) / len(expected)
    f1 = (
        2.0 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    event_energy = sum(event.scores.get(square, 0.0) for square in event.squares)
    explained_energy = sum(event.scores.get(square, 0.0) for square in intersection)
    energy = explained_energy / event_energy if event_energy else 0.0
    return float((0.70 * f1) + (0.20 * energy) + (0.10 * event.confidence))


def _temporal_score(
    move_square_sets: tuple[frozenset[chess.Square], ...],
    events: tuple[ChangeEvent, ...],
) -> float:
    if not move_square_sets:
        return 0.0
    if not events:
        # Neutral rather than zero: final-position evidence can still recover
        # moves, but the result is more likely to be marked ambiguous.
        return 0.45

    useful_events = events[-6:]
    move_count = len(move_square_sets)
    event_count = len(useful_events)
    best = 0.0

    if event_count >= move_count:
        for event_indices in itertools.combinations(range(event_count), move_count):
            score = float(
                np.mean(
                    [
                        _event_similarity(move_square_sets[index], useful_events[event_index])
                        for index, event_index in enumerate(event_indices)
                    ]
                )
            )
            best = max(best, score)
    else:
        for move_indices in itertools.combinations(range(move_count), event_count):
            score = float(
                np.mean(
                    [
                        _event_similarity(move_square_sets[move_index], useful_events[index])
                        for index, move_index in enumerate(move_indices)
                    ]
                )
            )
            score *= event_count / move_count
            best = max(best, score)
    return best


def _candidate_from_node(
    start_board: chess.Board,
    node: _SearchNode,
    scores: dict[chess.Square, float],
    events: tuple[ChangeEvent, ...],
) -> SequenceCandidate:
    expected = position_changed_squares(start_board, node.board)
    final_fit, _observed = _position_fit(expected, scores)
    temporal = _temporal_score(node.move_square_sets, events)
    change = _change_quality(expected, scores)
    length_penalty = max(0, len(node.moves) - 2) * 0.012
    total = (
        (0.72 * final_fit)
        + (0.20 * temporal)
        + (0.08 * change)
        - length_penalty
    )
    return SequenceCandidate(
        moves=node.moves,
        final_board=node.board.copy(stack=False),
        expected_squares=expected,
        final_position_score=final_fit,
        temporal_score=temporal,
        change_score=change,
        total_score=float(max(0.0, min(1.0, total))),
    )


def _node_priority(
    start_board: chess.Board,
    board: chess.Board,
    move_square_sets: tuple[frozenset[chess.Square], ...],
    scores: dict[chess.Square, float],
    events: tuple[ChangeEvent, ...],
) -> float:
    expected = position_changed_squares(start_board, board)
    fit, _observed = _position_fit(expected, scores)
    temporal = _temporal_score(move_square_sets, events)
    return float((0.80 * fit) + (0.20 * temporal))


def search_sequences(
    board: chess.Board,
    scores: dict[chess.Square, float],
    events: Iterable[ChangeEvent] = (),
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
    beam_width: int = DEFAULT_BEAM_WIDTH,
    top_n: int = 5,
) -> MultiMoveRecoveryResult | None:
    """Search legal two- or three-ply sequences that explain a stable frame."""
    max_depth = min(3, max(2, int(max_depth)))
    beam_width = max(20, int(beam_width))
    event_tuple = tuple(events)
    start = board.copy(stack=False)
    frontier = (
        _SearchNode(start.copy(stack=False), tuple(), tuple(), 0.0),
    )
    candidates: list[SequenceCandidate] = []

    for depth in range(1, max_depth + 1):
        expanded: list[_SearchNode] = []
        for node in frontier:
            for move in node.board.legal_moves:
                move_squares = move_changed_squares(node.board, move)
                next_board = node.board.copy(stack=False)
                next_board.push(move)
                move_sets = (*node.move_square_sets, move_squares)
                priority = _node_priority(
                    start,
                    next_board,
                    move_sets,
                    scores,
                    event_tuple,
                )
                expanded.append(
                    _SearchNode(
                        board=next_board,
                        moves=(*node.moves, move),
                        move_square_sets=move_sets,
                        priority=priority,
                    )
                )

        if not expanded:
            break
        expanded.sort(key=lambda node: node.priority, reverse=True)
        frontier = tuple(expanded[:beam_width])
        if depth >= 2:
            candidates.extend(
                _candidate_from_node(start, node, scores, event_tuple)
                for node in frontier
            )

    candidates = [
        candidate
        for candidate in candidates
        if candidate.final_position_score >= 0.45
    ]
    if not candidates:
        return None

    candidates.sort(key=lambda candidate: candidate.total_score, reverse=True)
    unique: list[SequenceCandidate] = []
    seen_sequences: set[tuple[str, ...]] = set()
    for candidate in candidates:
        key = tuple(move.uci() for move in candidate.moves)
        if key in seen_sequences:
            continue
        seen_sequences.add(key)
        unique.append(candidate)
        if len(unique) >= max(2, top_n):
            break

    best = unique[0]
    second = unique[1] if len(unique) > 1 else None
    separation = best.total_score - (second.total_score if second else 0.0)
    separation_score = min(1.0, max(0.0, separation) / 0.18)
    confidence = (
        (0.72 * best.final_position_score)
        + (0.18 * best.temporal_score)
        + (0.10 * separation_score)
    )

    same_final_position = (
        second is not None
        and best.final_board.board_fen() == second.final_board.board_fen()
        and best.moves != second.moves
    )
    promotion_involved = any(move.promotion is not None for move in best.moves)
    ambiguous = (
        second is not None
        and (
            separation < 0.065
            or (same_final_position and separation < 0.12)
        )
    ) or promotion_involved

    return MultiMoveRecoveryResult(
        candidates=tuple(unique[:top_n]),
        confidence=float(min(1.0, max(0.0, confidence))),
        ambiguous=ambiguous,
        observed_squares=active_squares(scores),
    )


def sequence_san(board: chess.Board, moves: Iterable[chess.Move]) -> str:
    working = board.copy(stack=False)
    labels: list[str] = []
    for move in moves:
        if move not in working.legal_moves:
            labels.append(move.uci())
            break
        labels.append(working.san(move))
        working.push(move)
    return " → ".join(labels)


class FrameEventBuffer:
    """Extract completed movement bursts from a rolling warped-board stream."""

    def __init__(
        self,
        *,
        max_events: int = 8,
        movement_threshold: float = 1.6,
        settle_seconds: float = 0.12,
    ) -> None:
        self.max_events = max(2, int(max_events))
        self.movement_threshold = float(movement_threshold)
        self.settle_seconds = float(settle_seconds)
        self._events: deque[ChangeEvent] = deque(maxlen=self.max_events)
        self._previous: np.ndarray | None = None
        self._segment_start: np.ndarray | None = None
        self._moving = False
        self._stable_since: float | None = None

    def reset(
        self,
        frame: np.ndarray | None = None,
        timestamp: float | None = None,
    ) -> None:
        del timestamp
        self._events.clear()
        self._previous = frame.copy() if frame is not None else None
        self._segment_start = frame.copy() if frame is not None else None
        self._moving = False
        self._stable_since = None

    def events(self) -> tuple[ChangeEvent, ...]:
        return tuple(self._events)

    def observe(
        self,
        frame: np.ndarray,
        timestamp: float,
        motion_score: float,
    ) -> ChangeEvent | None:
        if self._previous is None:
            self.reset(frame, timestamp)
            return None

        produced: ChangeEvent | None = None
        if motion_score >= self.movement_threshold:
            if not self._moving:
                self._moving = True
                self._segment_start = self._previous.copy()
            self._stable_since = None
        elif self._moving:
            if self._stable_since is None:
                self._stable_since = timestamp
            elif timestamp - self._stable_since >= self.settle_seconds:
                start = self._segment_start
                if start is not None:
                    scores = square_change_scores(start, frame)
                    squares = active_squares(scores)
                    strongest = max(scores.values(), default=0.0)
                    if strongest >= 7.0 and squares:
                        confidence = min(1.0, strongest / 24.0)
                        produced = ChangeEvent(
                            timestamp=timestamp,
                            squares=squares,
                            scores=scores,
                            confidence=confidence,
                        )
                        self._events.append(produced)
                self._moving = False
                self._stable_since = None
                self._segment_start = frame.copy()
        elif self._segment_start is None:
            self._segment_start = frame.copy()

        self._previous = frame.copy()
        return produced


def show_recovery_dialog(
    app_module: ModuleType,
    board: chess.Board,
    result: MultiMoveRecoveryResult,
    settings: RecoverySettings,
) -> tuple[chess.Move, ...] | None:
    """Preview recovered sequences and return the player-approved choice."""
    if not result.candidates:
        return None
    if (
        settings.auto_accept
        and not result.ambiguous
        and result.confidence >= settings.auto_threshold
    ):
        return result.candidates[0].moves

    window = "Chess Camera - Experimental Multi-Move Recovery"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 1180, 720)
    queue: list[str] = []
    buttons: list[Button] = []
    selected = 0

    def mouse(event: int, x: int, y: int, _flags: int, _data: object) -> None:
        if event == cv2.EVENT_LBUTTONUP:
            action = clicked_action(buttons, x, y)
            if action:
                queue.append(action)

    cv2.setMouseCallback(window, mouse)
    while True:
        candidate = result.candidates[selected]
        view = np.zeros((720, 1180, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        board_view = app_module.render_virtual_board(
            candidate.final_board,
            candidate.moves[-1] if candidate.moves else None,
        )
        view[50:670, 20:640] = board_view

        app_module.put_text(
            view,
            "EXPERIMENTAL MULTI-MOVE RECOVERY",
            (675, 58),
            (100, 220, 255),
            0.78,
        )
        app_module.put_text(
            view,
            f"Candidate {selected + 1}/{len(result.candidates)}",
            (675, 105),
            (120, 255, 170),
            0.62,
        )
        app_module.put_text(
            view,
            f"Recovered {len(candidate.moves)} half-moves",
            (675, 145),
            (235, 235, 240),
            0.58,
        )
        san = sequence_san(board, candidate.moves)
        words = san.split(" → ")
        for row, label in enumerate(words[:3]):
            app_module.put_text(
                view,
                f"{row + 1}. {label}",
                (695, 195 + row * 42),
                (235, 235, 240),
                0.68,
            )
        app_module.put_text(
            view,
            f"Overall confidence: {result.confidence:.0%}",
            (675, 350),
            (120, 220, 255),
            0.58,
        )
        app_module.put_text(
            view,
            f"Final board fit: {candidate.final_position_score:.0%}",
            (675, 386),
            (180, 190, 205),
            0.50,
        )
        app_module.put_text(
            view,
            f"Movement-order evidence: {candidate.temporal_score:.0%}",
            (675, 418),
            (180, 190, 205),
            0.50,
        )
        warning = (
            "Move order is ambiguous. Confirm carefully."
            if result.ambiguous
            else "The sequence is legal and matches the observed board changes."
        )
        app_module.put_text(
            view,
            warning,
            (675, 468),
            (80, 160, 255) if result.ambiguous else (120, 255, 170),
            0.47,
        )

        previous = Button(
            "previous",
            "PREVIOUS",
            675,
            520,
            160,
            48,
            enabled=len(result.candidates) > 1,
        )
        next_button = Button(
            "next",
            "NEXT",
            850,
            520,
            160,
            48,
            enabled=len(result.candidates) > 1,
        )
        accept = Button(
            "accept",
            "ACCEPT SEQUENCE",
            675,
            590,
            335,
            56,
            active=True,
        )
        cancel = Button(
            "cancel",
            "USE NORMAL CORRECTION",
            675,
            658,
            335,
            42,
        )
        buttons = [previous, next_button, accept, cancel]
        for button in buttons:
            draw_button(view, button)

        cv2.imshow(window, view)
        key = cv2.waitKey(20) & 0xFF
        action = queue.pop(0) if queue else None
        if action == "previous" or key in (81, 2424832, ord(",")):
            selected = (selected - 1) % len(result.candidates)
        elif action == "next" or key in (83, 2555904, ord(".")):
            selected = (selected + 1) % len(result.candidates)
        elif action == "accept" or key in (10, 13):
            cv2.destroyWindow(window)
            return result.candidates[selected].moves
        elif action == "cancel" or key == 27:
            cv2.destroyWindow(window)
            return None
        try:
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                return None
        except cv2.error:
            return None
