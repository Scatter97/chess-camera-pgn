from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Callable

import cv2
import numpy as np

import piece_theme_system
from pregame_ui import Button, clicked_action, draw_button


AUTO_ACCEPT_ENABLED_KEY = "advanced_auto_accept_enabled"
AUTO_ACCEPT_THRESHOLD_KEY = "advanced_auto_accept_threshold"
DEFAULT_AUTO_ACCEPT_THRESHOLD = 0.95
MIN_AUTO_ACCEPT_THRESHOLD = 0.50
MAX_AUTO_ACCEPT_THRESHOLD = 0.99


def load_config(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def save_config(path: Path, config: dict[str, object]) -> None:
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")


def auto_accept_settings(path: Path) -> tuple[bool, float]:
    config = load_config(path)
    enabled = bool(config.get(AUTO_ACCEPT_ENABLED_KEY, False))
    try:
        threshold = float(
            config.get(AUTO_ACCEPT_THRESHOLD_KEY, DEFAULT_AUTO_ACCEPT_THRESHOLD)
        )
    except (TypeError, ValueError):
        threshold = DEFAULT_AUTO_ACCEPT_THRESHOLD
    threshold = min(MAX_AUTO_ACCEPT_THRESHOLD, max(MIN_AUTO_ACCEPT_THRESHOLD, threshold))
    return enabled, threshold


def save_auto_accept_settings(path: Path, enabled: bool, threshold: float) -> None:
    config = load_config(path)
    config[AUTO_ACCEPT_ENABLED_KEY] = bool(enabled)
    config[AUTO_ACCEPT_THRESHOLD_KEY] = min(
        MAX_AUTO_ACCEPT_THRESHOLD,
        max(MIN_AUTO_ACCEPT_THRESHOLD, float(threshold)),
    )
    save_config(path, config)


def _threshold_from_x(x: int, left: int, width: int) -> float:
    progress = min(1.0, max(0.0, (x - left) / max(1, width)))
    value = MIN_AUTO_ACCEPT_THRESHOLD + progress * (
        MAX_AUTO_ACCEPT_THRESHOLD - MIN_AUTO_ACCEPT_THRESHOLD
    )
    return round(value, 2)


def advanced_detection_screen(app_module: ModuleType) -> None:
    """Configure confidence-based automatic approval with immediate saving."""
    enabled, threshold = auto_accept_settings(app_module.CONFIG_PATH)
    window = "Chess Camera - Advanced Detection"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 780, 520)
    queue: list[str] = []
    buttons: list[Button] = []
    slider_active = False
    slider_left, slider_width = 50, 670
    message = "Changes save immediately and apply when a game starts."

    def persist() -> None:
        save_auto_accept_settings(app_module.CONFIG_PATH, enabled, threshold)

    def mouse(event: int, x: int, y: int, _flags: int, _data: object) -> None:
        nonlocal slider_active, threshold
        if event == cv2.EVENT_LBUTTONDOWN:
            action = clicked_action(buttons, x, y)
            if action == "threshold_slider":
                slider_active = True
                threshold = _threshold_from_x(x, slider_left, slider_width)
                persist()
            return
        if event == cv2.EVENT_MOUSEMOVE and slider_active and _flags & cv2.EVENT_FLAG_LBUTTON:
            threshold = _threshold_from_x(x, slider_left, slider_width)
            persist()
            return
        if event != cv2.EVENT_LBUTTONUP:
            return
        if slider_active:
            threshold = _threshold_from_x(x, slider_left, slider_width)
            persist()
            slider_active = False
            return
        action = clicked_action(buttons, x, y)
        if action:
            queue.append(action)

    cv2.setMouseCallback(window, mouse)
    while True:
        view = np.zeros((520, 780, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        app_module.put_text(
            view,
            "Advanced Detection",
            (48, 58),
            (100, 220, 255),
            0.92,
        )
        app_module.put_text(
            view,
            "Automatically approve a legal move only when confidence meets your limit.",
            (48, 98),
            (175, 185, 200),
            0.48,
        )

        toggle = Button(
            "toggle_auto_threshold",
            f"CONFIDENCE AUTO-APPROVAL: {'ON' if enabled else 'OFF'}",
            48,
            135,
            500,
            58,
            active=enabled,
        )
        slider = Button(
            "threshold_slider",
            "",
            slider_left,
            265,
            slider_width,
            42,
            enabled=enabled,
        )
        back = Button("back", "BACK", 515, 425, 205, 58)
        buttons = [toggle, slider, back]
        draw_button(view, toggle)
        draw_button(view, back)

        app_module.put_text(
            view,
            f"Auto-approval confidence: {threshold:.0%}",
            (50, 238),
            (120, 255, 170) if enabled else (135, 140, 150),
            0.64,
        )
        track_y = 286
        cv2.line(view, (slider_left, track_y), (slider_left + slider_width, track_y), (70, 75, 84), 12)
        progress = (threshold - MIN_AUTO_ACCEPT_THRESHOLD) / (
            MAX_AUTO_ACCEPT_THRESHOLD - MIN_AUTO_ACCEPT_THRESHOLD
        )
        knob_x = slider_left + int(round(slider_width * progress))
        if enabled:
            cv2.line(view, (slider_left, track_y), (knob_x, track_y), (78, 150, 105), 12)
            cv2.circle(view, (knob_x, track_y), 12, (120, 255, 170), -1, cv2.LINE_AA)
            cv2.circle(view, (knob_x, track_y), 12, (230, 245, 235), 2, cv2.LINE_AA)
        else:
            cv2.circle(view, (knob_x, track_y), 12, (90, 94, 102), -1, cv2.LINE_AA)

        app_module.put_text(
            view,
            "Moves below this confidence remain available for manual approval.",
            (50, 340),
            (175, 185, 200),
            0.47,
        )
        app_module.put_text(
            view,
            "This setting overrides the pregame Manual/Automatic choice when enabled.",
            (50, 372),
            (175, 185, 200),
            0.45,
        )
        app_module.put_text(
            view,
            message[:90],
            (48, 495),
            (120, 220, 255),
            0.43,
        )

        cv2.imshow(window, view)
        key = cv2.waitKey(20) & 0xFF
        action = queue.pop(0) if queue else None
        if action == "toggle_auto_threshold":
            enabled = not enabled
            persist()
            message = (
                f"Auto-approval is ON at {threshold:.0%}."
                if enabled
                else "Confidence auto-approval is OFF."
            )
        elif action == "back" or key == 27:
            cv2.destroyWindow(window)
            return
        try:
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                return
        except cv2.error:
            return


def _cycle(values: tuple[str, ...], current: str, amount: int) -> str:
    if not values:
        return ""
    try:
        index = values.index(current)
    except ValueError:
        index = 0
    return values[(index + amount) % len(values)]


def _save_appearance(
    path: Path,
    piece_pack: str,
    sound_pack: str,
    sounds: bool,
    highlights: bool,
) -> None:
    config = load_config(path)
    config[piece_theme_system.PIECE_PACK_KEY] = piece_pack
    config[piece_theme_system.SOUND_PACK_KEY] = sound_pack
    config[piece_theme_system.SOUND_ENABLED_KEY] = sounds
    config[piece_theme_system.MOVE_HIGHLIGHTS_KEY] = highlights
    save_config(path, config)
    piece_theme_system.clear_image_cache()


def appearance_sound_screen(app_module: ModuleType) -> None:
    """Select built-in/custom piece and sound packs."""
    piece_theme_system.ensure_bundled_assets()
    config_path = app_module.CONFIG_PATH
    pieces = piece_theme_system.available_piece_packs()
    sounds_available = piece_theme_system.available_sound_packs()
    piece_pack = piece_theme_system.selected_piece_pack(config_path)
    sound_pack = piece_theme_system.selected_sound_pack(config_path)
    sounds = piece_theme_system.sounds_enabled(config_path)
    highlights = piece_theme_system.highlights_enabled(config_path)
    window = "Chess Camera - Board Appearance and Sounds"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 860, 650)
    queue: list[str] = []
    buttons: list[Button] = []
    message = "Built-in packs are generated locally. Custom folders are supported."

    def persist() -> None:
        _save_appearance(
            config_path,
            piece_pack,
            sound_pack,
            sounds,
            highlights,
        )

    def mouse(event: int, x: int, y: int, _flags: int, _data: object) -> None:
        if event == cv2.EVENT_LBUTTONUP:
            action = clicked_action(buttons, x, y)
            if action:
                queue.append(action)

    cv2.setMouseCallback(window, mouse)
    while True:
        view = np.zeros((650, 860, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        app_module.put_text(view, "Board Appearance and Sounds", (48, 58), (100, 220, 255), 0.90)
        app_module.put_text(
            view,
            "The selected piece pack is used on live, correction, history, and review boards.",
            (48, 94),
            (175, 185, 200),
            0.44,
        )

        app_module.put_text(view, "Piece pack", (48, 145), (120, 220, 255), 0.60)
        app_module.put_text(view, piece_pack or "No valid pack found", (250, 145), (120, 255, 170), 0.58)
        previous_piece = Button("previous_piece", "<", 48, 170, 80, 48, enabled=bool(pieces))
        next_piece = Button("next_piece", ">", 140, 170, 80, 48, enabled=bool(pieces))
        open_pieces = Button("open_piece_folder", "OPEN CUSTOM PIECE FOLDER", 250, 170, 430, 48)

        app_module.put_text(view, "Move sound pack", (48, 275), (120, 220, 255), 0.60)
        app_module.put_text(view, sound_pack or "No valid pack found", (250, 275), (120, 255, 170), 0.58)
        previous_sound = Button("previous_sound", "<", 48, 300, 80, 48, enabled=bool(sounds_available))
        next_sound = Button("next_sound", ">", 140, 300, 80, 48, enabled=bool(sounds_available))
        open_sounds = Button("open_sound_folder", "OPEN CUSTOM SOUND FOLDER", 250, 300, 430, 48)

        sound_toggle = Button(
            "toggle_sounds",
            f"PIECE SOUNDS: {'ON' if sounds else 'OFF'}",
            48,
            385,
            270,
            52,
            active=sounds,
        )
        test_sound = Button("test_sound", "TEST MOVE SOUND", 335, 385, 270, 52, enabled=bool(sound_pack))
        highlight_toggle = Button(
            "toggle_highlights",
            f"CAMERA MOVE HIGHLIGHTS: {'ON' if highlights else 'OFF'}",
            48,
            455,
            557,
            52,
            active=highlights,
        )
        back = Button("back", "BACK", 620, 555, 190, 56)
        buttons = [
            previous_piece,
            next_piece,
            open_pieces,
            previous_sound,
            next_sound,
            open_sounds,
            sound_toggle,
            test_sound,
            highlight_toggle,
            back,
        ]
        for button in buttons:
            draw_button(view, button)
        app_module.put_text(view, message[:94], (48, 610), (120, 220, 255), 0.43)

        cv2.imshow(window, view)
        key = cv2.waitKey(20) & 0xFF
        action = queue.pop(0) if queue else None
        if action == "previous_piece":
            piece_pack = _cycle(pieces, piece_pack, -1)
            persist()
            message = f"Piece pack changed to {piece_pack}."
        elif action == "next_piece":
            piece_pack = _cycle(pieces, piece_pack, 1)
            persist()
            message = f"Piece pack changed to {piece_pack}."
        elif action == "previous_sound":
            sound_pack = _cycle(sounds_available, sound_pack, -1)
            persist()
            message = f"Sound pack changed to {sound_pack}."
        elif action == "next_sound":
            sound_pack = _cycle(sounds_available, sound_pack, 1)
            persist()
            message = f"Sound pack changed to {sound_pack}."
        elif action == "toggle_sounds":
            sounds = not sounds
            persist()
            message = f"Piece sounds are {'ON' if sounds else 'OFF'}."
        elif action == "toggle_highlights":
            highlights = not highlights
            persist()
            message = f"Camera move highlights are {'ON' if highlights else 'OFF'}."
        elif action == "test_sound":
            piece_theme_system.play_named_sound(config_path, "move", force=True)
            message = f"Played the {sound_pack} move sound."
        elif action == "open_piece_folder":
            opened = piece_theme_system.open_asset_folder("pieces")
            message = (
                "Opened the piece_packs folder. Restart this screen after adding a pack."
                if opened
                else "Could not open the folder automatically. Open piece_packs manually."
            )
        elif action == "open_sound_folder":
            opened = piece_theme_system.open_asset_folder("sounds")
            message = (
                "Opened the sound_packs folder. Restart this screen after adding a pack."
                if opened
                else "Could not open the folder automatically. Open sound_packs manually."
            )
        elif action == "back" or key == 27:
            cv2.destroyWindow(window)
            return
        try:
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                return
        except cv2.error:
            return


def install(app_module: ModuleType, navigation_module: ModuleType) -> None:
    """Install the new settings hub and confidence-threshold runtime behavior."""
    if getattr(navigation_module, "_feature_settings_installed", False):
        return

    original_wizard: Callable = app_module.run_pregame_wizard
    original_threshold = float(app_module.AUTO_CONFIDENCE)

    def run_pregame_wizard(*args: object, **kwargs: object):
        result = original_wizard(*args, **kwargs)
        enabled, threshold = auto_accept_settings(app_module.CONFIG_PATH)
        app_module.AUTO_CONFIDENCE = threshold if enabled else original_threshold
        if result is None:
            return None
        setup, board_corners, phone_corners, profile, engine_path = result
        if enabled and not setup.bullet_mode:
            setup = replace(setup, auto_accept=True)
        return setup, board_corners, phone_corners, profile, engine_path

    app_module.run_pregame_wizard = run_pregame_wizard

    original_settings = navigation_module.settings_screen

    def settings_hub() -> None:
        window = "Chess Camera - Settings"
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window, 780, 550)
        queue: list[str] = []
        buttons = [
            Button("existing", "CAMERA, ENGINE, AND TRAINING", 85, 130, 610, 68),
            Button("advanced_detection", "ADVANCED DETECTION", 85, 220, 610, 68),
            Button("appearance", "BOARD APPEARANCE AND SOUNDS", 85, 310, 610, 68),
            Button("back", "BACK", 255, 445, 270, 58),
        ]

        def mouse(event: int, x: int, y: int, _flags: int, _data: object) -> None:
            if event == cv2.EVENT_LBUTTONUP:
                action = clicked_action(buttons, x, y)
                if action:
                    queue.append(action)

        cv2.setMouseCallback(window, mouse)
        while True:
            view = np.zeros((550, 780, 3), dtype=np.uint8)
            view[:] = (28, 31, 37)
            app_module.put_text(view, "Settings", (85, 70), (100, 220, 255), 1.0)
            app_module.put_text(
                view,
                "Choose a settings group.",
                (85, 105),
                (175, 185, 200),
                0.50,
            )
            for button in buttons:
                draw_button(view, button)
            cv2.imshow(window, view)
            key = cv2.waitKey(25) & 0xFF
            action = queue.pop(0) if queue else None
            if action == "existing":
                cv2.destroyWindow(window)
                original_settings()
                cv2.namedWindow(window, cv2.WINDOW_NORMAL)
                cv2.resizeWindow(window, 780, 550)
                cv2.setMouseCallback(window, mouse)
            elif action == "advanced_detection":
                cv2.destroyWindow(window)
                advanced_detection_screen(app_module)
                cv2.namedWindow(window, cv2.WINDOW_NORMAL)
                cv2.resizeWindow(window, 780, 550)
                cv2.setMouseCallback(window, mouse)
            elif action == "appearance":
                cv2.destroyWindow(window)
                appearance_sound_screen(app_module)
                cv2.namedWindow(window, cv2.WINDOW_NORMAL)
                cv2.resizeWindow(window, 780, 550)
                cv2.setMouseCallback(window, mouse)
            elif action == "back" or key == 27:
                cv2.destroyWindow(window)
                return
            try:
                if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                    return
            except cv2.error:
                return

    navigation_module.settings_screen = settings_hub
    navigation_module._feature_settings_installed = True
