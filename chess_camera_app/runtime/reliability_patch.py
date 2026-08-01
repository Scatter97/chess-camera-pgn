from __future__ import annotations

import inspect
import json
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import chess
import cv2
import numpy as np

from chess_camera_app.calibration.board_profiles import BoardProfile, BoardProfileStore
from chess_camera_app.ui.pregame_ui import Button


@dataclass(frozen=True)
class TrainingSample:
    move_uci: str
    scores: dict[chess.Square, float]
    expected_squares: tuple[chess.Square, ...]
    weight: int


_INSTALLED = False
_APP: Any | None = None
_PROFILE_BINDINGS: list[tuple[BoardProfileStore, BoardProfile]] = []


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(
            f"Could not install 0.39 reliability patch: {label} anchor "
            f"matched {count} times instead of once."
        )
    return source.replace(old, new, 1)


def make_training_sample(
    move: chess.Move,
    scores: dict[chess.Square, float],
    expected_squares: Iterable[chess.Square],
    weight: int = 1,
) -> TrainingSample:
    return TrainingSample(
        move.uci(),
        {square: float(value) for square, value in scores.items()},
        tuple(expected_squares),
        max(1, int(weight)),
    )


def _normalized_score_vector(
    scores: dict[chess.Square, float],
) -> np.ndarray:
    vector = np.asarray(
        [float(scores.get(square, 0.0)) for square in chess.SQUARES],
        dtype=np.float64,
    )
    maximum = float(np.max(vector))
    if maximum > 0:
        vector /= maximum
    return vector


def remove_training_sample(
    profile: BoardProfile,
    sample: TrainingSample | None,
) -> bool:
    """Reverse one accepted observation, including its learned noise values."""
    if sample is None:
        return False

    pattern = profile.move_patterns.get(sample.move_uci)
    if pattern is not None and pattern.count > 0:
        remove_count = min(pattern.count, sample.weight)
        remaining = pattern.count - remove_count
        if remaining <= 0:
            profile.move_patterns.pop(sample.move_uci, None)
        else:
            old_mean = np.asarray(pattern.mean_scores, dtype=np.float64)
            removed = _normalized_score_vector(sample.scores)
            restored = (
                (old_mean * pattern.count) - (removed * remove_count)
            ) / remaining
            pattern.mean_scores = np.clip(restored, 0.0, None).tolist()
            pattern.count = remaining

    expected = set(sample.expected_squares)
    for square in chess.SQUARES:
        if square in expected:
            continue
        count = profile.noise_count[square]
        if count <= 0:
            continue
        removed_value = min(25.0, float(sample.scores.get(square, 0.0)))
        if count == 1:
            profile.noise_mean[square] = 0.0
            profile.noise_count[square] = 0
        else:
            restored_noise = (
                (profile.noise_mean[square] * count) - removed_value
            ) / (count - 1)
            profile.noise_mean[square] = max(0.0, restored_noise)
            profile.noise_count[square] = count - 1
    return True


def virtual_square_from_point(x: int, y: int) -> chess.Square | None:
    board_size = 520
    cell = board_size // 8
    left = (620 - board_size) // 2
    top = 40
    if not (left <= x < left + board_size and top <= y < top + board_size):
        return None
    file_index = (x - left) // cell
    rank_from_top = (y - top) // cell
    return chess.square(int(file_index), 7 - int(rank_from_top))


def legal_editor_move(
    board: chess.Board,
    from_square: chess.Square,
    to_square: chess.Square,
) -> chess.Move | None:
    candidates = [
        move
        for move in board.legal_moves
        if move.from_square == from_square and move.to_square == to_square
    ]
    if not candidates:
        return None
    for promotion in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, None):
        for move in candidates:
            if move.promotion == promotion:
                return move
    return candidates[0]


def preview_board(board: chess.Board, move: chess.Move | None) -> chess.Board:
    preview = board.copy(stack=False)
    if move is not None and move in preview.legal_moves:
        preview.push(move)
    return preview


def prepare_corrected_clock(
    clock: Any,
    manual_clock: Any,
    moving_white: bool,
    now: float,
    clock_source: str,
) -> float | None:
    """Record the corrected legal move and start the opponent's clock."""
    if clock_source != "builtin":
        return None
    if manual_clock.pending is not None and manual_clock.ready_for(moving_white):
        recorded = manual_clock.consume(moving_white)
        clock.start(now, not moving_white)
        return recorded
    clock.start(now, moving_white)
    return float(clock.complete_move(moving_white, now))


def _remember_profile(store: BoardProfileStore, profile: BoardProfile) -> None:
    if not any(
        known_store is store and known_profile is profile
        for known_store, known_profile in _PROFILE_BINDINGS
    ):
        _PROFILE_BINDINGS.append((store, profile))


def _install_profile_registry() -> None:
    if getattr(BoardProfileStore, "_reliability_registry_installed", False):
        return

    original_load = BoardProfileStore.load
    original_save = BoardProfileStore.save
    original_ensure_default = BoardProfileStore.ensure_default
    original_create_from = BoardProfileStore.create_from

    def load(store: BoardProfileStore) -> list[BoardProfile]:
        profiles = original_load(store)
        for profile in profiles:
            _remember_profile(store, profile)
        return profiles

    def save(store: BoardProfileStore, profile: BoardProfile) -> None:
        _remember_profile(store, profile)
        original_save(store, profile)

    def ensure_default(store: BoardProfileStore, *args: Any, **kwargs: Any) -> BoardProfile:
        profile = original_ensure_default(store, *args, **kwargs)
        _remember_profile(store, profile)
        return profile

    def create_from(store: BoardProfileStore, *args: Any, **kwargs: Any) -> BoardProfile:
        profile = original_create_from(store, *args, **kwargs)
        _remember_profile(store, profile)
        return profile

    BoardProfileStore.load = load  # type: ignore[assignment]
    BoardProfileStore.save = save  # type: ignore[assignment]
    BoardProfileStore.ensure_default = ensure_default  # type: ignore[assignment]
    BoardProfileStore.create_from = create_from  # type: ignore[assignment]
    BoardProfileStore._reliability_registry_installed = True  # type: ignore[attr-defined]


def _active_profile_binding() -> tuple[BoardProfileStore, BoardProfile] | None:
    if _APP is None:
        return None
    active_name = ""
    config_path = Path(_APP.CONFIG_PATH)
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            active_name = str(raw.get("active_profile", ""))
    except (OSError, ValueError, TypeError):
        pass

    for store, profile in reversed(_PROFILE_BINDINGS):
        if not active_name or profile.name == active_name:
            return store, profile

    store = BoardProfileStore(Path(_APP.PROFILE_DIRECTORY))
    store.load()
    profile = store.get(active_name) if active_name else None
    if profile is None and store.profiles:
        profile = store.profiles[0]
    if profile is None:
        return None
    _remember_profile(store, profile)
    return store, profile


def _matching_bindings(name: str) -> list[tuple[BoardProfileStore, BoardProfile]]:
    matches = [
        (store, profile)
        for store, profile in _PROFILE_BINDINGS
        if profile.name == name
    ]
    unique: list[tuple[BoardProfileStore, BoardProfile]] = []
    seen: set[tuple[int, int]] = set()
    for store, profile in matches:
        key = (id(store), id(profile))
        if key not in seen:
            seen.add(key)
            unique.append((store, profile))
    return unique


def _save_matching_profiles(name: str) -> None:
    for store, profile in _matching_bindings(name):
        store.save(profile)


def show_board_training_settings() -> None:
    """Show accepted/rejected sample controls for the active board preset."""
    if _APP is None:
        return
    binding = _active_profile_binding()
    if binding is None:
        return
    _store, active_profile = binding
    window = "Board Training Settings"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 660, 455)
    buttons: list[Button] = []
    queue: list[str] = []
    message = "Changes are saved to this board preset."

    def mouse(event: int, x: int, y: int, _flags: int, _data: object) -> None:
        if event != cv2.EVENT_LBUTTONUP:
            return
        action = _APP.clicked_action(buttons, x, y)
        if action:
            queue.append(action)

    cv2.setMouseCallback(window, mouse)
    while True:
        view = np.zeros((455, 660, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        _APP.put_text(view, "Board Training", (32, 48), (100, 220, 255), 0.86)
        _APP.put_text(view, active_profile.name[:38], (32, 82), (175, 185, 200), 0.52)
        accepted = active_profile.sample_count
        rejected = sum(
            pattern.count for pattern in active_profile.rejected_patterns.values()
        )
        _APP.put_text(
            view,
            f"Accepted samples: {accepted}",
            (32, 128),
            (120, 255, 170),
            0.58,
        )
        _APP.put_text(
            view,
            f"Rejected samples: {rejected}",
            (330, 128),
            (120, 220, 255),
            0.58,
        )
        buttons = [
            Button(
                "toggle_learning",
                f"Automatic learning: {'ON' if active_profile.learning_enabled else 'OFF'}",
                32,
                160,
                596,
                48,
                active=active_profile.learning_enabled,
            ),
            Button("clear_accepted", "Clear accepted samples", 32, 225, 285, 48),
            Button("clear_rejected", "Clear rejected samples", 343, 225, 285, 48),
            Button("reset_all", "Reset all training", 32, 290, 285, 48),
            Button("close", "CLOSE", 343, 290, 285, 48),
        ]
        for button in buttons:
            _APP.draw_button(view, button)
        _APP.put_text(view, message[:70], (32, 385), (165, 175, 190), 0.48)
        _APP.put_text(
            view,
            "Calibration and board orientation are never changed here.",
            (32, 420),
            (135, 145, 160),
            0.45,
        )
        cv2.imshow(window, view)
        key = cv2.waitKey(20) & 0xFF
        action = queue.pop(0) if queue else None
        if action == "toggle_learning":
            new_value = not active_profile.learning_enabled
            for _bound_store, profile in _matching_bindings(active_profile.name):
                profile.learning_enabled = new_value
            _save_matching_profiles(active_profile.name)
            message = f"Automatic learning {'enabled' if new_value else 'disabled'}."
        elif action == "clear_accepted":
            confirmed = _APP.ask_yes_no(
                "Clear accepted samples?",
                "Remove accepted move patterns and learned board noise?",
            )
            if confirmed:
                for _bound_store, profile in _matching_bindings(active_profile.name):
                    profile.move_patterns.clear()
                    profile.noise_mean = [0.0] * 64
                    profile.noise_count = [0] * 64
                _save_matching_profiles(active_profile.name)
                message = "Accepted samples cleared."
                cv2.namedWindow(window, cv2.WINDOW_NORMAL)
                cv2.setMouseCallback(window, mouse)
        elif action == "clear_rejected":
            confirmed = _APP.ask_yes_no(
                "Clear rejected samples?",
                "Remove all detection-wrong examples for this board?",
            )
            if confirmed:
                for _bound_store, profile in _matching_bindings(active_profile.name):
                    profile.rejected_patterns.clear()
                _save_matching_profiles(active_profile.name)
                message = "Rejected samples cleared."
                cv2.namedWindow(window, cv2.WINDOW_NORMAL)
                cv2.setMouseCallback(window, mouse)
        elif action == "reset_all":
            confirmed = _APP.ask_yes_no(
                "Reset all board training?",
                "Clear accepted samples, rejected samples, and learned noise?",
            )
            if confirmed:
                for _bound_store, profile in _matching_bindings(active_profile.name):
                    profile.reset_training()
                _save_matching_profiles(active_profile.name)
                message = "All board training reset."
                cv2.namedWindow(window, cv2.WINDOW_NORMAL)
                cv2.setMouseCallback(window, mouse)
        elif action == "close" or key == 27:
            cv2.destroyWindow(window)
            cv2.waitKey(1)
            return
        try:
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                return
        except cv2.error:
            return


def draw_editor_banner(image: np.ndarray) -> np.ndarray:
    if _APP is None:
        return image
    view = image.copy()
    overlay = view.copy()
    width = view.shape[1]
    cv2.rectangle(overlay, (0, 0), (width, 96), (0, 0, 165), -1)
    view = cv2.addWeighted(overlay, 0.82, view, 0.18, 0)
    _APP.put_text(
        view,
        "CORRECT THE VIRTUAL BOARD",
        (28, 38),
        (255, 255, 255),
        0.88,
    )
    _APP.put_text(
        view,
        "Drag the move on the virtual board, then press Continue.",
        (28, 75),
        (225, 235, 245),
        0.58,
    )
    return view


def _install_illegal_warning_ui(app_module: Any) -> None:
    def correction_button(width: int, height: int) -> Button:
        return Button(
            "correct_illegal",
            "MOVE WAS LEGAL - CORRECT BOARD",
            max(20, width // 2 - 230),
            height - 105,
            460,
            55,
            active=True,
        )

    def warning(image: np.ndarray) -> np.ndarray:
        view = image.copy()
        overlay = view.copy()
        height, width = view.shape[:2]
        cv2.rectangle(overlay, (0, 0), (width, height), (0, 0, 205), -1)
        view = cv2.addWeighted(overlay, 0.88, view, 0.12, 0)
        app_module.put_text(
            view,
            "ILLEGAL MOVE DETECTED",
            (max(30, width // 2 - 260), max(90, height // 2 - 82)),
            (255, 255, 255),
            1.22,
        )
        app_module.put_text(
            view,
            "Restore the last legal position, or correct the virtual board.",
            (max(30, width // 2 - 350), max(140, height // 2 - 25)),
            (235, 240, 250),
            0.68,
        )
        app_module.put_text(
            view,
            "The built-in clock is paused while this warning is open.",
            (max(30, width // 2 - 325), max(180, height // 2 + 18)),
            (225, 230, 240),
            0.58,
        )
        app_module.draw_button(view, correction_button(width, height))
        return view

    app_module.illegal_warning_button = correction_button
    app_module.draw_illegal_warning = warning


def patch_main_source(source: str) -> str:
    source = textwrap.dedent(source)

    source = _replace_once(
        source,
        """        illegal_warning = False\n        illegal_clock_side: bool | None = None\n""",
        """        illegal_warning = False\n        illegal_clock_side: bool | None = None\n        illegal_editor_active = False\n        illegal_editor_move: chess.Move | None = None\n        illegal_drag_square: chess.Square | None = None\n        training_history: list[object | None] = []\n""",
        "game reliability state",
    )

    source = _replace_once(
        source,
        """                manual_clock.reset()\n                illegal_warning = False\n                illegal_clock_side = None\n                game_result = \"*\"\n""",
        """                manual_clock.reset()\n                illegal_warning = False\n                illegal_clock_side = None\n                illegal_editor_active = False\n                illegal_editor_move = None\n                illegal_drag_square = None\n                training_history.clear()\n                game_result = \"*\"\n""",
        "new-game reliability reset",
    )

    source = _replace_once(
        source,
        """        def on_game_mouse(\n            event: int, x: int, y: int, _flags: int, _data: object\n        ) -> None:\n            if event != cv2.EVENT_LBUTTONUP:\n                return\n            action = clicked_action(game_buttons, x, y)\n            if action is not None:\n                game_click_queue.append(action)\n""",
        """        def on_game_mouse(\n            event: int, x: int, y: int, _flags: int, _data: object\n        ) -> None:\n            nonlocal illegal_drag_square, illegal_editor_move, status\n            if illegal_warning and illegal_editor_active:\n                if event == cv2.EVENT_LBUTTONDOWN:\n                    square = _reliability_virtual_square(x, y)\n                    piece = board.piece_at(square) if square is not None else None\n                    if piece is not None and piece.color == board.turn:\n                        illegal_drag_square = square\n                        status = f\"Drag {chess.square_name(square)} to the destination square.\"\n                    else:\n                        illegal_drag_square = None\n                    return\n                if event == cv2.EVENT_LBUTTONUP and illegal_drag_square is not None:\n                    target = _reliability_virtual_square(x, y)\n                    source_square = illegal_drag_square\n                    illegal_drag_square = None\n                    selected_move = (\n                        _reliability_legal_editor_move(board, source_square, target)\n                        if target is not None\n                        else None\n                    )\n                    if selected_move is None:\n                        status = \"That drag is not a legal move. Try again.\"\n                    else:\n                        illegal_editor_move = selected_move\n                        status = (\n                            f\"Selected {board.san(selected_move)}. \"\n                            \"Press Continue to update the PGN.\"\n                        )\n                    return\n            if event != cv2.EVENT_LBUTTONUP:\n                return\n            action = clicked_action(game_buttons, x, y)\n            if illegal_warning and illegal_editor_active and action not in {\n                \"continue_illegal\",\n                \"cancel_illegal\",\n            }:\n                return\n            if action is not None:\n                game_click_queue.append(action)\n""",
        "illegal editor mouse handler",
    )

    source = _replace_once(
        source,
        """            virtual_view = render_virtual_board(\n                board, moves[-1] if moves else None\n            )\n""",
        """            virtual_board = (\n                _reliability_preview_board(board, illegal_editor_move)\n                if (\n                    illegal_warning\n                    and illegal_editor_active\n                    and illegal_editor_move is not None\n                )\n                else board\n            )\n            virtual_last_move = (\n                illegal_editor_move\n                if illegal_warning and illegal_editor_active\n                else (moves[-1] if moves else None)\n            )\n            virtual_view = render_virtual_board(virtual_board, virtual_last_move)\n""",
        "illegal editor board preview",
    )

    source = _replace_once(
        source,
        """            if illegal_warning:\n                game_buttons.append(\n                    illegal_warning_button(combined.shape[1], combined.shape[0])\n                )\n            for game_button in game_buttons:\n                draw_button(combined, game_button)\n            if illegal_warning:\n                combined = draw_illegal_warning(combined)\n""",
        """            if illegal_warning:\n                if illegal_editor_active:\n                    center_x = combined.shape[1] // 2\n                    game_buttons.extend(\n                        (\n                            Button(\n                                \"continue_illegal\",\n                                \"CONTINUE\",\n                                center_x - 215,\n                                combined.shape[0] - 72,\n                                200,\n                                48,\n                                active=illegal_editor_move is not None,\n                                enabled=illegal_editor_move is not None,\n                            ),\n                            Button(\n                                \"cancel_illegal\",\n                                \"Cancel correction\",\n                                center_x + 15,\n                                combined.shape[0] - 72,\n                                200,\n                                48,\n                            ),\n                        )\n                    )\n                else:\n                    game_buttons.append(\n                        illegal_warning_button(combined.shape[1], combined.shape[0])\n                    )\n            for game_button in game_buttons:\n                draw_button(combined, game_button)\n            if illegal_warning:\n                combined = (\n                    _reliability_draw_editor_banner(combined)\n                    if illegal_editor_active\n                    else draw_illegal_warning(combined)\n                )\n                if illegal_editor_active:\n                    for game_button in game_buttons[-2:]:\n                        draw_button(combined, game_button)\n""",
        "illegal editor buttons",
    )

    source = _replace_once(
        source,
        """            if illegal_warning and (\n                click_action == \"dismiss_illegal\" or key in (27, ord(\"x\"))\n            ):\n                # Manual recovery is for cases where the physical position has\n                # been restored but camera noise prevents the automatic check.\n                # Re-baseline on the current image without changing the logical\n                # chess position or recording a move.\n                reference = warped.copy()\n                previous = warped.copy()\n                stable_since = None\n                accuracy_frames.clear()\n                illegal_warning = False\n                last_accept_time = now\n                if clock_source == \"builtin\":\n                    resume_clock_after_illegal_move(\n                        builtin_clock,\n                        illegal_clock_side,\n                        now,\n                    )\n                illegal_clock_side = None\n                status = (\n                    \"Illegal warning dismissed and camera resynchronized. \"\n                    \"The clock resumed.\"\n                    if clock_source == \"builtin\"\n                    else\n                    \"Illegal warning dismissed and camera resynchronized.\"\n                )\n                continue\n""",
        """            if illegal_warning and click_action == \"correct_illegal\":\n                illegal_editor_active = True\n                illegal_editor_move = None\n                illegal_drag_square = None\n                status = (\n                    \"Drag the legal move on the virtual board. \"\n                    \"The clock stays paused until Continue.\"\n                )\n                continue\n\n            if (\n                illegal_warning\n                and illegal_editor_active\n                and click_action == \"cancel_illegal\"\n            ):\n                illegal_editor_active = False\n                illegal_editor_move = None\n                illegal_drag_square = None\n                status = (\n                    \"Correction cancelled. Restore the last legal physical \"\n                    \"position or reopen correction mode.\"\n                )\n                continue\n\n            if (\n                illegal_warning\n                and illegal_editor_active\n                and click_action == \"continue_illegal\"\n            ):\n                if illegal_editor_move is None:\n                    status = \"Drag a legal move before pressing Continue.\"\n                    continue\n                selected_move = illegal_editor_move\n                pending = [\n                    RankedMove(\n                        selected_move,\n                        1.0,\n                        move_changed_squares(board, selected_move),\n                    )\n                ]\n                pending_index = 0\n                pending_frame = warped.copy()\n                pending_event_time = now\n                pending_scores = (\n                    square_change_scores(reference, warped)\n                    if reference is not None\n                    else {}\n                )\n                correction_clock_value = _reliability_prepare_corrected_clock(\n                    builtin_clock,\n                    manual_clock,\n                    board.turn,\n                    now,\n                    clock_source,\n                )\n                auto_correction_pending = True\n                illegal_warning = False\n                illegal_clock_side = None\n                illegal_editor_active = False\n                illegal_editor_move = None\n                illegal_drag_square = None\n                previous = warped.copy()\n                stable_since = None\n                accuracy_frames.clear()\n                last_accept_time = now\n                status = \"Corrected move validated. Updating the game and PGN...\"\n                key = 13\n                click_action = \"accept\"\n\n            if illegal_warning and illegal_editor_active and key in (27, ord(\"x\")):\n                illegal_editor_active = False\n                illegal_editor_move = None\n                illegal_drag_square = None\n                status = \"Correction editor closed; the illegal warning remains active.\"\n                continue\n\n            if illegal_warning and key in (27, ord(\"x\")):\n                # Keyboard-only camera recovery remains available for cases\n                # where the physical board is already restored.\n                reference = warped.copy()\n                previous = warped.copy()\n                stable_since = None\n                accuracy_frames.clear()\n                illegal_warning = False\n                illegal_editor_active = False\n                illegal_editor_move = None\n                illegal_drag_square = None\n                last_accept_time = now\n                if clock_source == \"builtin\":\n                    resume_clock_after_illegal_move(\n                        builtin_clock,\n                        illegal_clock_side,\n                        now,\n                    )\n                illegal_clock_side = None\n                status = (\n                    \"Illegal warning dismissed and camera resynchronized. \"\n                    \"The clock resumed.\"\n                    if clock_source == \"builtin\"\n                    else \"Illegal warning dismissed and camera resynchronized.\"\n                )\n                continue\n""",
        "illegal correction action",
    )

    source = _replace_once(
        source,
        """                    if board_looks_restored(scores):\n                        illegal_warning = False\n                        if clock_source == \"builtin\":\n""",
        """                    if board_looks_restored(scores):\n                        illegal_warning = False\n                        illegal_editor_active = False\n                        illegal_editor_move = None\n                        illegal_drag_square = None\n                        if clock_source == \"builtin\":\n""",
        "automatic illegal recovery reset",
    )

    source = _replace_once(
        source,
        """                        illegal_warning = True\n                        pending.clear()\n""",
        """                        illegal_warning = True\n                        illegal_editor_active = False\n                        illegal_editor_move = None\n                        illegal_drag_square = None\n                        pending.clear()\n""",
        "illegal warning initialization",
    )

    source = _replace_once(
        source,
        """                                if (\n                                    not bullet_mode\n                                    and confidence >= AUTO_CONFIDENCE\n                                ):\n                                    profile.observe_move(\n                                        candidate,\n                                        pending_scores,\n                                        pending[0].expected_squares,\n                                    )\n                                    profile_store.save(profile)\n                                board.push(candidate)\n""",
        """                                learned_sample = None\n                                if (\n                                    not bullet_mode\n                                    and confidence >= AUTO_CONFIDENCE\n                                ):\n                                    profile.observe_move(\n                                        candidate,\n                                        pending_scores,\n                                        pending[0].expected_squares,\n                                    )\n                                    profile_store.save(profile)\n                                    if profile.learning_enabled:\n                                        learned_sample = _reliability_make_training_sample(\n                                            candidate,\n                                            pending_scores,\n                                            pending[0].expected_squares,\n                                        )\n                                training_history.append(learned_sample)\n                                board.push(candidate)\n""",
        "automatic accepted training sample",
    )

    source = _replace_once(
        source,
        """                    selected_pattern = pending[pending_index]\n                    profile.observe_move(\n                        selected_move,\n                        pending_scores,\n                        selected_pattern.expected_squares,\n                        weight=(\n                            4\n                            if was_auto_correction\n                            else (2 if pending_index != 0 else 1)\n                        ),\n                    )\n                    profile_store.save(profile)\n                    board.push(selected_move)\n""",
        """                    selected_pattern = pending[pending_index]\n                    training_weight = (\n                        4\n                        if was_auto_correction\n                        else (2 if pending_index != 0 else 1)\n                    )\n                    profile.observe_move(\n                        selected_move,\n                        pending_scores,\n                        selected_pattern.expected_squares,\n                        weight=training_weight,\n                    )\n                    profile_store.save(profile)\n                    training_history.append(\n                        _reliability_make_training_sample(\n                            selected_move,\n                            pending_scores,\n                            selected_pattern.expected_squares,\n                            training_weight,\n                        )\n                        if profile.learning_enabled\n                        else None\n                    )\n                    board.push(selected_move)\n""",
        "manual accepted training sample",
    )

    source = _replace_once(
        source,
        """                moves.pop()\n                board.pop()\n                game_result = \"*\"\n""",
        """                moves.pop()\n                board.pop()\n                _reliability_remove_training_sample(\n                    profile,\n                    training_history.pop() if training_history else None,\n                )\n                game_result = \"*\"\n""",
        "detection-wrong accepted sample removal",
    )

    source = _replace_once(
        source,
        """                moves.pop()\n                move_clocks.pop()\n                move_clock_tokens.pop()\n""",
        """                _reliability_remove_training_sample(\n                    profile,\n                    training_history.pop() if training_history else None,\n                )\n                profile_store.save(profile)\n                moves.pop()\n                move_clocks.pop()\n                move_clock_tokens.pop()\n""",
        "undo accepted sample removal",
    )

    source = _replace_once(
        source,
        """                illegal_warning = False\n                illegal_clock_side = None\n                save_game(\n""",
        """                illegal_warning = False\n                illegal_clock_side = None\n                illegal_editor_active = False\n                illegal_editor_move = None\n                illegal_drag_square = None\n                save_game(\n""",
        "undo illegal editor reset",
    )

    return source


def install(app_module: Any) -> None:
    """Install the 0.39.4 and 0.39.5 reliability behavior once."""
    global _APP, _INSTALLED
    _APP = app_module
    if _INSTALLED:
        return
    _install_profile_registry()
    _install_illegal_warning_ui(app_module)

    app_module._reliability_virtual_square = virtual_square_from_point
    app_module._reliability_legal_editor_move = legal_editor_move
    app_module._reliability_preview_board = preview_board
    app_module._reliability_prepare_corrected_clock = prepare_corrected_clock
    app_module._reliability_draw_editor_banner = draw_editor_banner
    app_module._reliability_make_training_sample = make_training_sample
    app_module._reliability_remove_training_sample = remove_training_sample

    source = patch_main_source(inspect.getsource(app_module.main))
    exec(compile(source, str(app_module.__file__), "exec"), app_module.__dict__)
    _INSTALLED = True
