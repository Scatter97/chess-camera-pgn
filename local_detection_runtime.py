from __future__ import annotations

from pathlib import Path
from types import ModuleType

import chess
import cv2
import numpy as np

import camera_advanced
import local_detection
import pregame_ui
import ui_support as ui
from chess_tracker import move_changed_squares
from pregame_ui import Button


# A hand or object can stop moving before the normal detection delay expires.
# Keep recently moving unrelated squares ignored long enough for the actual
# move squares to settle and be analyzed.
LOCAL_OCCLUSION_GRACE_SECONDS = {
    "low": 2.0,
    "normal": 2.5,
    "high": 3.0,
}


def apply_extended_occlusion_grace() -> None:
    """Keep recently blocked unrelated squares ignored during local detection."""
    for name, grace_seconds in LOCAL_OCCLUSION_GRACE_SECONDS.items():
        profile = local_detection.PROFILES[name]
        local_detection.PROFILES[name] = local_detection.SensitivityProfile(
            profile.motion_threshold,
            profile.max_unstable_squares,
            max(profile.occlusion_grace_seconds, grace_seconds),
        )


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


def filter_change_scores(
    board: chess.Board | None,
    raw_scores: dict[chess.Square, float],
    unstable: frozenset[chess.Square],
) -> dict[chess.Square, float]:
    """Hide moving squares but preserve complete legal or fully stable changes."""
    filtered = {
        square: (0.0 if square in unstable else value)
        for square, value in raw_scores.items()
    }
    if board is None or not unstable:
        return filtered
    if stable_legal_move_visible(board, filtered, unstable):
        return filtered

    # The hand is still over an affected square or only part of a move is
    # visible. Zero evidence makes the main loop wait instead of raising an
    # illegal-move warning before the move squares have settled.
    return {square: 0.0 for square in chess.SQUARES}


def local_frame_motion_score(
    previous: np.ndarray,
    current: np.ndarray,
    sample_timestamp: float,
) -> float:
    """Update per-square motion without requiring the whole board to be still."""
    state = local_detection.STATE
    last_timestamp = getattr(state, "last_sample_timestamp", -1.0)
    if sample_timestamp != last_timestamp:
        state.last_sample_timestamp = sample_timestamp
        local_detection.update_motion_state(previous, current)

    # The main loop's global stability timer must continue even when unrelated
    # squares are moving. square_change_scores() below separately blocks
    # detection until the squares belonging to one legal move are stable.
    return 0.0


def save_experimental_settings(
    config_path: Path,
    enabled: bool,
    sensitivity: str,
) -> None:
    """Persist the local-detection toggle immediately."""
    if sensitivity not in local_detection.SENSITIVITY_OPTIONS:
        sensitivity = local_detection.DEFAULT_SENSITIVITY
    config = local_detection.load_config(config_path)
    config["local_detection_beta"] = bool(enabled)
    config["local_detection_sensitivity"] = sensitivity
    local_detection.save_config(config_path, config)
    local_detection.configure(config_path)


def experimental_settings_screen(config_path: Path) -> None:
    """Show an immediate ON/OFF toggle for 64-square beta detection."""
    enabled, sensitivity = local_detection.normalized_settings(config_path)
    window = "Chess Camera - Experimental Features"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 760, 500)
    queue: list[str] = []
    buttons: list[Button] = []
    message = "Changes save immediately. Normal sensitivity is recommended."

    def mouse(
        event: int,
        x: int,
        y: int,
        _flags: int,
        _data: object,
    ) -> None:
        if event == cv2.EVENT_LBUTTONUP:
            action = pregame_ui.clicked_action(buttons, x, y)
            if action:
                queue.append(action)

    cv2.setMouseCallback(window, mouse)
    while True:
        view = np.zeros((500, 760, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        ui._put(
            view,
            "Experimental Features",
            (48, 62),
            (100, 220, 255),
            0.95,
            2,
        )
        ui._put(
            view,
            "64-SQUARE LOCAL DETECTION (BETA)",
            (48, 125),
            (165, 175, 190),
            0.50,
        )
        ui._put(
            view,
            "Unrelated squares may stay blocked or moving while move squares settle.",
            (48, 165),
            (185, 195, 210),
            0.46,
        )
        ui._put(
            view,
            f"Sensitivity: {sensitivity.upper()}",
            (48, 285),
            (120, 220, 255),
            0.62,
        )

        buttons = [
            Button(
                "toggle",
                f"64-SQUARE BETA: {'ON' if enabled else 'OFF'}",
                48,
                195,
                410,
                58,
                active=enabled,
            ),
            Button("previous", "< SENSITIVITY", 390, 260, 145, 46),
            Button("next", "SENSITIVITY >", 550, 260, 145, 46),
            Button("back", "BACK", 490, 380, 205, 58),
        ]
        for item in buttons:
            pregame_ui.draw_button(view, item)

        ui._put(
            view,
            message[:86],
            (48, 468),
            (120, 220, 255),
            0.43,
        )
        cv2.imshow(window, view)
        key = cv2.waitKey(20) & 0xFF
        action = queue.pop(0) if queue else None

        if action == "toggle":
            enabled = not enabled
            save_experimental_settings(config_path, enabled, sensitivity)
            message = (
                "64-square beta detection is ON."
                if enabled
                else "64-square beta detection is OFF."
            )
        elif action == "previous":
            index = local_detection.SENSITIVITY_OPTIONS.index(sensitivity)
            sensitivity = local_detection.SENSITIVITY_OPTIONS[
                (index - 1) % len(local_detection.SENSITIVITY_OPTIONS)
            ]
            save_experimental_settings(config_path, enabled, sensitivity)
            message = f"Sensitivity changed to {sensitivity.upper()}."
        elif action == "next":
            index = local_detection.SENSITIVITY_OPTIONS.index(sensitivity)
            sensitivity = local_detection.SENSITIVITY_OPTIONS[
                (index + 1) % len(local_detection.SENSITIVITY_OPTIONS)
            ]
            save_experimental_settings(config_path, enabled, sensitivity)
            message = f"Sensitivity changed to {sensitivity.upper()}."
        elif action == "back" or key == 27:
            cv2.destroyWindow(window)
            return

        try:
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                return
        except cv2.error:
            return


def install(target: ModuleType) -> None:
    """Add true local stability gating and an immediate beta toggle."""
    if getattr(target, "_local_detection_runtime_installed", False):
        return

    original_open = target.open_camera
    original_frame_motion = target.frame_motion_score
    original_square_change_scores = target.square_change_scores
    original_virtual_board = target.render_virtual_board

    state = local_detection.STATE
    state.board = None
    state.last_sample_timestamp = -1.0
    apply_extended_occlusion_grace()

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
        return local_frame_motion_score(
            previous,
            current,
            camera_advanced.RUNTIME.last_detection,
        )

    def square_change_scores(
        reference: np.ndarray,
        current: np.ndarray,
    ) -> dict[chess.Square, float]:
        raw_scores = original_square_change_scores(reference, current)
        if not state.enabled:
            return raw_scores
        return filter_change_scores(
            state.board,
            raw_scores,
            state.current_unstable,
        )

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
    local_detection.experimental_settings_screen = experimental_settings_screen
    target._local_detection_runtime_installed = True
