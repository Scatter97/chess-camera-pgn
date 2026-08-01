from __future__ import annotations

import hashlib
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import ModuleType
from typing import Iterable

import chess
import cv2
import numpy as np

import camera_advanced
import local_detection
import pregame_ui
import ui_support as ui
from chess_tracker import (
    BOARD_MARGIN_PIXELS,
    SQUARE_PIXELS,
    move_changed_squares,
    square_change_scores as raw_square_change_scores,
)
from pregame_ui import Button


BUFFER_SECONDS = 10.0
DEFAULT_CAPTURE_INTERVAL = 0.25
CAPTURE_INTERVALS = {"normal": 0.30, "fast": 0.20, "bullet": 0.12}
MAX_SNAPSHOTS = 96
EVENT_MERGE_SECONDS = 0.35
RECOVERY_SECONDS = {"low": 0.26, "normal": 0.20, "high": 0.15}
PIXEL_CHANGE_THRESHOLDS = {"low": 15, "normal": 19, "high": 24}
ZONE_OCCLUSION_FRACTIONS = {"low": 0.31, "normal": 0.37, "high": 0.44}
SQUARE_OCCLUSION_FRACTIONS = {"low": 0.48, "normal": 0.57, "high": 0.66}
SQUARE_ACTIVE_THRESHOLDS = {"low": 10.0, "normal": 7.0, "high": 6.3}


class ZoneStatus(str, Enum):
    CLEAR = "clear"
    MOVING = "moving"
    BLOCKED = "blocked"
    RECOVERING = "recovering"


@dataclass(frozen=True)
class ZoneObservation:
    zone: int
    status: ZoneStatus
    motion_score: float
    changed_fraction: float
    largest_component_fraction: float
    active_squares: frozenset[chess.Square]
    stable_for: float
    confidence: float


@dataclass(frozen=True)
class BoardSnapshot:
    timestamp: float
    image: np.ndarray
    zones: tuple[ZoneObservation, ...]
    square_scores: dict[chess.Square, float]


@dataclass(frozen=True)
class TemporalEvent:
    timestamp: float
    squares: frozenset[chess.Square]
    scores: dict[chess.Square, float]
    confidence: float


@dataclass(frozen=True)
class RecoveryEvidence:
    square_scores: dict[chess.Square, float]
    events: tuple[TemporalEvent, ...]
    known_squares: frozenset[chess.Square]
    latest_frame: np.ndarray | None


@dataclass
class DetectionV2Runtime:
    board: chess.Board | None = None
    previous_frame: np.ndarray | None = None
    reference_frame: np.ndarray | None = None
    latest_frame: np.ndarray | None = None
    reference_fingerprint: bytes | None = None
    zone_status: dict[int, ZoneStatus] = field(default_factory=dict)
    zone_since: dict[int, float] = field(default_factory=dict)
    zone_observations: dict[int, ZoneObservation] = field(default_factory=dict)
    snapshots: deque[BoardSnapshot] = field(default_factory=lambda: deque(maxlen=MAX_SNAPSHOTS))
    events: deque[TemporalEvent] = field(default_factory=lambda: deque(maxlen=32))
    last_clear_crops: dict[int, np.ndarray] = field(default_factory=dict)
    last_snapshot_time: float = -1.0
    latest_scores: dict[chess.Square, float] = field(default_factory=dict)
    latest_known_squares: frozenset[chess.Square] = frozenset()
    mode_name: str = "normal"
    last_state_signature: tuple[str, ...] = tuple()

    def reset(self, reference: np.ndarray | None = None, timestamp: float | None = None) -> None:
        now = time.monotonic() if timestamp is None else float(timestamp)
        self.previous_frame = reference.copy() if reference is not None else None
        self.reference_frame = reference.copy() if reference is not None else None
        self.latest_frame = reference.copy() if reference is not None else None
        self.reference_fingerprint = frame_fingerprint(reference) if reference is not None else None
        self.zone_status = {zone: ZoneStatus.CLEAR for zone in range(16)}
        self.zone_since = {zone: now for zone in range(16)}
        self.zone_observations.clear()
        self.snapshots.clear()
        self.events.clear()
        self.last_clear_crops.clear()
        self.last_snapshot_time = -1.0
        self.latest_scores.clear()
        self.latest_known_squares = frozenset(chess.SQUARES)
        self.last_state_signature = tuple(ZoneStatus.CLEAR.value for _ in range(16))
        if reference is not None:
            for zone in range(16):
                self.last_clear_crops[zone] = crop_zone(reference, zone).copy()


RUNTIME = DetectionV2Runtime()


def frame_fingerprint(frame: np.ndarray) -> bytes:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA)
    return hashlib.blake2b(small.tobytes(), digest_size=8).digest()


def zone_for_square(square: chess.Square) -> int:
    return ((7 - chess.square_rank(square)) // 2) * 4 + chess.square_file(square) // 2


def squares_for_zone(zone: int) -> frozenset[chess.Square]:
    row, column = divmod(zone, 4)
    return frozenset(
        chess.square(file_index, 7 - rank_from_top)
        for rank_from_top in range(row * 2, row * 2 + 2)
        for file_index in range(column * 2, column * 2 + 2)
    )


def zone_bounds(zone: int) -> tuple[int, int, int, int]:
    row, column = divmod(zone, 4)
    return (
        BOARD_MARGIN_PIXELS + column * 2 * SQUARE_PIXELS,
        BOARD_MARGIN_PIXELS + row * 2 * SQUARE_PIXELS,
        BOARD_MARGIN_PIXELS + (column + 1) * 2 * SQUARE_PIXELS,
        BOARD_MARGIN_PIXELS + (row + 1) * 2 * SQUARE_PIXELS,
    )


def crop_zone(frame: np.ndarray, zone: int) -> np.ndarray:
    x0, y0, x1, y1 = zone_bounds(zone)
    return frame[y0:y1, x0:x1]


def _square_crop(zone_crop: np.ndarray, local_index: int) -> np.ndarray:
    row, column = divmod(local_index, 2)
    height, width = zone_crop.shape[:2]
    y0, y1 = row * height // 2, (row + 1) * height // 2
    x0, x1 = column * width // 2, (column + 1) * width // 2
    inset = max(3, min(height, width) // 24)
    return zone_crop[y0 + inset : y1 - inset, x0 + inset : x1 - inset]


def _difference_metrics(reference_crop: np.ndarray, current_crop: np.ndarray, sensitivity: str) -> tuple[float, float, tuple[float, float, float, float]]:
    if reference_crop.shape != current_crop.shape or reference_crop.size == 0:
        return 1.0, 1.0, (1.0, 1.0, 1.0, 1.0)
    threshold = PIXEL_CHANGE_THRESHOLDS.get(sensitivity, PIXEL_CHANGE_THRESHOLDS["normal"])
    reference_gray = cv2.cvtColor(reference_crop, cv2.COLOR_BGR2GRAY)
    current_gray = cv2.cvtColor(current_crop, cv2.COLOR_BGR2GRAY)
    mask = (cv2.absdiff(reference_gray, current_gray) >= threshold).astype(np.uint8)
    changed_fraction = float(np.mean(mask))
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    largest = 0.0 if count <= 1 else float(np.max(stats[1:, cv2.CC_STAT_AREA])) / max(1, mask.size)
    fractions: list[float] = []
    for local_index in range(4):
        ref_square = _square_crop(reference_crop, local_index)
        cur_square = _square_crop(current_crop, local_index)
        if ref_square.shape != cur_square.shape or ref_square.size == 0:
            fractions.append(1.0)
            continue
        ref_gray = cv2.cvtColor(ref_square, cv2.COLOR_BGR2GRAY)
        cur_gray = cv2.cvtColor(cur_square, cv2.COLOR_BGR2GRAY)
        fractions.append(float(np.mean(cv2.absdiff(ref_gray, cur_gray) >= threshold)))
    return changed_fraction, largest, (fractions[0], fractions[1], fractions[2], fractions[3])


def _classify_zone(zone: int, reference: np.ndarray, current: np.ndarray, raw_scores: dict[chess.Square, float], motion_scores: dict[chess.Square, float], now: float) -> ZoneObservation:
    sensitivity = local_detection.STATE.sensitivity
    prior = RUNTIME.zone_status.get(zone, ZoneStatus.CLEAR)
    zone_squares = squares_for_zone(zone)
    motion_threshold = local_detection.PROFILES[sensitivity].motion_threshold
    moving_values = [motion_scores.get(square, 0.0) for square in zone_squares]
    motion_score = max(moving_values, default=0.0)
    moving = any(value >= motion_threshold for value in moving_values)
    changed_fraction, largest_component, square_fractions = _difference_metrics(
        crop_zone(reference, zone), crop_zone(current, zone), sensitivity
    )
    active_threshold = SQUARE_ACTIVE_THRESHOLDS.get(sensitivity, SQUARE_ACTIVE_THRESHOLDS["normal"])
    active_squares = frozenset(square for square in zone_squares if raw_scores.get(square, 0.0) >= active_threshold)
    connected_threshold = max(0.20, ZONE_OCCLUSION_FRACTIONS.get(sensitivity, 0.37) * 0.72)
    blocked = (
        (changed_fraction >= ZONE_OCCLUSION_FRACTIONS.get(sensitivity, 0.37) and largest_component >= connected_threshold)
        or (max(square_fractions) >= SQUARE_OCCLUSION_FRACTIONS.get(sensitivity, 0.57) and largest_component >= connected_threshold)
        or len(active_squares) >= 3
    )
    if moving:
        status = ZoneStatus.MOVING
    elif blocked:
        status = ZoneStatus.BLOCKED
    elif prior in {ZoneStatus.MOVING, ZoneStatus.BLOCKED}:
        status = ZoneStatus.RECOVERING
    elif prior == ZoneStatus.RECOVERING:
        status = ZoneStatus.CLEAR if now - RUNTIME.zone_since.get(zone, now) >= RECOVERY_SECONDS.get(sensitivity, 0.20) else ZoneStatus.RECOVERING
    else:
        status = ZoneStatus.CLEAR
    if status != prior:
        RUNTIME.zone_since[zone] = now
    stable_for = now - RUNTIME.zone_since.get(zone, now)
    confidence = 1.0
    if status == ZoneStatus.MOVING:
        confidence = max(0.0, 1.0 - motion_score / max(1.0, motion_threshold * 4.0))
    elif status == ZoneStatus.BLOCKED:
        confidence = max(changed_fraction, largest_component)
    elif status == ZoneStatus.RECOVERING:
        confidence = min(1.0, stable_for / max(0.01, RECOVERY_SECONDS.get(sensitivity, 0.20)))
    return ZoneObservation(zone, status, motion_score, changed_fraction, largest_component, active_squares, stable_for, float(min(1.0, max(0.0, confidence))))


def _append_event(event: TemporalEvent) -> None:
    if not event.squares:
        return
    if RUNTIME.events and event.timestamp - RUNTIME.events[-1].timestamp <= EVENT_MERGE_SECONDS:
        previous = RUNTIME.events.pop()
        scores = dict(previous.scores)
        for square, value in event.scores.items():
            scores[square] = max(scores.get(square, 0.0), value)
        RUNTIME.events.append(TemporalEvent(event.timestamp, frozenset(set(previous.squares) | set(event.squares)), scores, (previous.confidence + event.confidence) / 2.0))
    else:
        RUNTIME.events.append(event)


def _capture_zone_events(current: np.ndarray, observations: Iterable[ZoneObservation], now: float) -> None:
    threshold = SQUARE_ACTIVE_THRESHOLDS.get(local_detection.STATE.sensitivity, 7.0)
    for observation in observations:
        if observation.status != ZoneStatus.CLEAR:
            continue
        zone = observation.zone
        current_crop = crop_zone(current, zone)
        previous_crop = RUNTIME.last_clear_crops.get(zone)
        if previous_crop is not None and previous_crop.shape == current_crop.shape:
            before = np.zeros_like(current)
            after = np.zeros_like(current)
            x0, y0, x1, y1 = zone_bounds(zone)
            before[y0:y1, x0:x1] = previous_crop
            after[y0:y1, x0:x1] = current_crop
            scores = raw_square_change_scores(before, after)
            active = frozenset(square for square in squares_for_zone(zone) if scores.get(square, 0.0) >= threshold)
            if active:
                filtered = {square: scores.get(square, 0.0) for square in active}
                _append_event(TemporalEvent(now, active, filtered, min(1.0, max(filtered.values(), default=0.0) / 22.0)))
        RUNTIME.last_clear_crops[zone] = current_crop.copy()


def _capture_interval() -> float:
    name = RUNTIME.mode_name.lower()
    if "bullet" in name:
        return CAPTURE_INTERVALS["bullet"]
    if "fast" in name:
        return CAPTURE_INTERVALS["fast"]
    if "normal" in name:
        return CAPTURE_INTERVALS["normal"]
    return DEFAULT_CAPTURE_INTERVAL


def _prune(now: float) -> None:
    while RUNTIME.snapshots and now - RUNTIME.snapshots[0].timestamp > BUFFER_SECONDS:
        RUNTIME.snapshots.popleft()
    while RUNTIME.events and now - RUNTIME.events[0].timestamp > BUFFER_SECONDS:
        RUNTIME.events.popleft()


def observe(reference: np.ndarray, previous: np.ndarray, current: np.ndarray, now: float | None = None) -> dict[chess.Square, float]:
    timestamp = time.monotonic() if now is None else float(now)
    fingerprint = frame_fingerprint(reference)
    if RUNTIME.reference_fingerprint != fingerprint:
        RUNTIME.reset(reference, timestamp)
    raw_scores = raw_square_change_scores(reference, current)
    motion_scores = local_detection.square_motion_scores(previous, current)
    observations = tuple(_classify_zone(zone, reference, current, raw_scores, motion_scores, timestamp) for zone in range(16))
    signature = tuple(item.status.value for item in observations)
    state_changed = signature != RUNTIME.last_state_signature
    for item in observations:
        RUNTIME.zone_status[item.zone] = item.status
        RUNTIME.zone_observations[item.zone] = item
    known_squares = frozenset(
        square
        for item in observations
        if item.status == ZoneStatus.CLEAR
        for square in squares_for_zone(item.zone)
    )
    filtered = {square: raw_scores.get(square, 0.0) if square in known_squares else 0.0 for square in chess.SQUARES}
    due = RUNTIME.last_snapshot_time < 0.0 or timestamp - RUNTIME.last_snapshot_time >= _capture_interval()
    if due or state_changed:
        _capture_zone_events(current, observations, timestamp)
        compact = cv2.resize(current, (256, 256), interpolation=cv2.INTER_AREA)
        RUNTIME.snapshots.append(BoardSnapshot(timestamp, compact, observations, dict(filtered)))
        RUNTIME.last_snapshot_time = timestamp
    RUNTIME.reference_frame = reference.copy()
    RUNTIME.previous_frame = previous.copy()
    RUNTIME.latest_frame = current.copy()
    RUNTIME.latest_scores = dict(filtered)
    RUNTIME.latest_known_squares = known_squares
    RUNTIME.last_state_signature = signature
    _prune(timestamp)
    return filtered


def candidate_zones_clear(board: chess.Board, move: chess.Move) -> bool:
    return all(RUNTIME.zone_status.get(zone_for_square(square), ZoneStatus.CLEAR) == ZoneStatus.CLEAR for square in move_changed_squares(board, move))


def stable_legal_move_visible(board: chess.Board, scores: dict[chess.Square, float]) -> bool:
    threshold = SQUARE_ACTIVE_THRESHOLDS.get(local_detection.STATE.sensitivity, 7.0)
    for move in board.legal_moves:
        if not candidate_zones_clear(board, move):
            continue
        expected = move_changed_squares(board, move)
        if sum(1 for square in expected if scores.get(square, 0.0) >= threshold) >= min(2, len(expected)):
            return True
    return False


def recovery_evidence() -> RecoveryEvidence:
    return RecoveryEvidence(dict(RUNTIME.latest_scores), tuple(RUNTIME.events), RUNTIME.latest_known_squares, RUNTIME.latest_frame.copy() if RUNTIME.latest_frame is not None else None)


def recovery_events() -> tuple[TemporalEvent, ...]:
    return tuple(RUNTIME.events)


def recovery_square_scores(fallback: dict[chess.Square, float] | None = None) -> dict[chess.Square, float]:
    return dict(RUNTIME.latest_scores) if RUNTIME.latest_scores else dict(fallback or {})


def snapshot_count() -> int:
    return len(RUNTIME.snapshots)


def install_multi_move(module: ModuleType) -> None:
    if getattr(module, "_local_detection_v2_installed", False):
        return
    original_search = module.search_sequences

    def search_sequences(board: chess.Board, scores: dict[chess.Square, float], events: Iterable[object] = (), **kwargs: object):
        evidence = recovery_evidence()
        merged_scores = dict(evidence.square_scores or scores)
        converted: list[object] = list(events)
        for event in evidence.events:
            converted.append(module.ChangeEvent(event.timestamp, event.squares, dict(event.scores), event.confidence))
            for square, value in event.scores.items():
                if square not in evidence.known_squares:
                    merged_scores[square] = max(merged_scores.get(square, 0.0), value)
        return original_search(board, merged_scores, converted, **kwargs)

    module.search_sequences = search_sequences
    module._local_detection_v2_installed = True


def _save_settings(config_path: Path, enabled: bool, sensitivity: str) -> None:
    if sensitivity not in local_detection.SENSITIVITY_OPTIONS:
        sensitivity = local_detection.DEFAULT_SENSITIVITY
    config = local_detection.load_config(config_path)
    config["local_detection_beta"] = bool(enabled)
    config["local_detection_sensitivity"] = sensitivity
    local_detection.save_config(config_path, config)
    local_detection.configure(config_path)
    RUNTIME.reset()


def experimental_settings_screen(config_path: Path) -> None:
    enabled, sensitivity = local_detection.normalized_settings(config_path)
    window = "Chess Camera - 64-Square Detection V2"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 860, 610)
    queue: list[str] = []
    buttons: list[Button] = []
    message = "Changes save immediately. Physical-board testing is recommended."

    def mouse(event: int, x: int, y: int, _flags: int, _data: object) -> None:
        if event == cv2.EVENT_LBUTTONUP:
            action = pregame_ui.clicked_action(buttons, x, y)
            if action:
                queue.append(action)

    cv2.setMouseCallback(window, mouse)
    while True:
        view = np.zeros((610, 860, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        ui._put(view, "64-Square Detection V2", (45, 58), (100, 220, 255), 0.95, 2)
        ui._put(view, "Sixteen independent 2x2 movement zones gate the 64-square detector.", (45, 96), (180, 190, 205), 0.46)
        ui._put(view, "Unrelated moving or blocked zones no longer stop a clear move zone.", (45, 124), (180, 190, 205), 0.46)
        ui._put(view, f"Feature: {'ON' if enabled else 'OFF'}", (45, 190), (120, 255, 170) if enabled else (190, 195, 205), 0.68, 2)
        ui._put(view, f"Sensitivity: {sensitivity.upper()}", (45, 238), (120, 220, 255), 0.60)
        ui._put(view, "Rolling temporal buffer: 10 seconds", (45, 300), (210, 215, 225), 0.50)
        ui._put(view, "Snapshots: Normal 0.30s | Fast 0.20s | Bullet 0.12s", (45, 330), (165, 175, 190), 0.44)
        ui._put(view, "Extra snapshots are captured whenever a movement-zone state changes.", (45, 360), (165, 175, 190), 0.44)
        buttons = [
            Button("toggle", f"64-SQUARE V2: {'ON' if enabled else 'OFF'}", 45, 405, 360, 58, active=enabled),
            Button("previous", "< SENSITIVITY", 435, 405, 175, 50),
            Button("next", "SENSITIVITY >", 625, 405, 175, 50),
            Button("back", "BACK", 590, 515, 210, 58),
        ]
        for button in buttons:
            pregame_ui.draw_button(view, button)
        ui._put(view, message[:96], (45, 574), (120, 220, 255), 0.42)
        cv2.imshow(window, view)
        key = cv2.waitKey(20) & 0xFF
        action = queue.pop(0) if queue else None
        if action == "toggle":
            enabled = not enabled
            _save_settings(config_path, enabled, sensitivity)
            message = f"64-Square Detection V2 is {'ON' if enabled else 'OFF'}."
        elif action in {"previous", "next"}:
            index = local_detection.SENSITIVITY_OPTIONS.index(sensitivity)
            sensitivity = local_detection.SENSITIVITY_OPTIONS[(index + (-1 if action == "previous" else 1)) % len(local_detection.SENSITIVITY_OPTIONS)]
            _save_settings(config_path, enabled, sensitivity)
            message = f"Sensitivity changed to {sensitivity.upper()}."
        elif action == "back" or key == 27:
            cv2.destroyWindow(window)
            return
        try:
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                return
        except cv2.error:
            return


def _draw_zone_status_map(panel: np.ndarray) -> None:
    if not local_detection.STATE.enabled:
        return
    origin_x, origin_y, cell = 20, 302, 28
    colors = {
        ZoneStatus.CLEAR: (80, 200, 110),
        ZoneStatus.MOVING: (80, 210, 240),
        ZoneStatus.BLOCKED: (70, 70, 225),
        ZoneStatus.RECOVERING: (210, 120, 200),
    }
    camera_advanced.put(panel, f"LOCAL64 V2 | {snapshot_count()} buffered", (origin_x, origin_y - 10), (120, 255, 170), 0.34)
    for zone in range(16):
        row, column = divmod(zone, 4)
        x0, y0 = origin_x + column * cell, origin_y + row * cell
        status = RUNTIME.zone_status.get(zone, ZoneStatus.CLEAR)
        cv2.rectangle(panel, (x0, y0), (x0 + cell - 3, y0 + cell - 3), colors[status], -1)
        cv2.rectangle(panel, (x0, y0), (x0 + cell - 3, y0 + cell - 3), (20, 22, 26), 1)
    camera_advanced.put(panel, "green clear | yellow moving", (145, origin_y + 28), (185, 195, 210), 0.29)
    camera_advanced.put(panel, "red blocked | purple recovering", (145, origin_y + 54), (185, 195, 210), 0.29)


def install(target: ModuleType) -> None:
    if getattr(target, "_local_detection_v2_installed", False):
        return
    original_open = target.open_camera
    original_frame_motion = target.frame_motion_score
    original_virtual_board = target.render_virtual_board
    original_panel = camera_advanced.render_camera_panel

    def open_camera(index: int):
        RUNTIME.reset()
        return original_open(index)

    def frame_motion(previous: np.ndarray, current: np.ndarray, sample_step: int = 3) -> float:
        if not local_detection.STATE.enabled:
            return original_frame_motion(previous, current, sample_step)
        timestamp = camera_advanced.RUNTIME.last_detection or time.monotonic()
        local_detection.update_motion_state(previous, current, timestamp)
        RUNTIME.previous_frame = previous.copy()
        RUNTIME.latest_frame = current.copy()
        return 0.0

    def square_scores(reference: np.ndarray, current: np.ndarray) -> dict[chess.Square, float]:
        if not local_detection.STATE.enabled:
            return raw_square_change_scores(reference, current)
        previous = RUNTIME.previous_frame if RUNTIME.previous_frame is not None and RUNTIME.previous_frame.shape == current.shape else current
        timestamp = camera_advanced.RUNTIME.last_detection or time.monotonic()
        return observe(reference, previous, current, timestamp)

    def render_virtual_board(board: chess.Board, last_move: chess.Move | None = None, suggested_move: chess.Move | None = None) -> np.ndarray:
        RUNTIME.board = board.copy(stack=False)
        return original_virtual_board(board, last_move, suggested_move)

    def render_camera_panel(board_view: np.ndarray, detection_mode_name: str, display_fps: float, stability_progress: float, fast_mode: bool) -> np.ndarray:
        RUNTIME.mode_name = detection_mode_name
        panel = original_panel(board_view, detection_mode_name, display_fps, stability_progress, fast_mode)
        _draw_zone_status_map(panel)
        return panel

    target.open_camera = open_camera
    target.frame_motion_score = frame_motion
    target.square_change_scores = square_scores
    target.render_virtual_board = render_virtual_board
    local_detection.STATE.original_square_change_scores = square_scores
    local_detection.experimental_settings_screen = experimental_settings_screen
    camera_advanced.render_camera_panel = render_camera_panel
    target._local_detection_v2_installed = True
    recovery_module = sys.modules.get("multi_move_recovery")
    if recovery_module is not None:
        install_multi_move(recovery_module)
