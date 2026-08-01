from __future__ import annotations

import copy
import json
from pathlib import Path
from types import ModuleType

import cv2
import numpy as np

from chess_camera_app.calibration.board_profiles import BoardProfile, BoardProfileStore
from chess_camera_app.ui.pregame_ui import Button, clicked_action, draw_button


REMOVE_UNDONE_KEY = "training_remove_undone_moves"
KEEP_REJECTED_KEY = "training_keep_rejected_examples"


def _read_config(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _write_config(path: Path, data: dict[str, object]) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def remove_undone_enabled(config_path: Path | None = None) -> bool:
    path = config_path or Path("camera_config.json")
    return bool(_read_config(path).get(REMOVE_UNDONE_KEY, True))


def keep_rejected_enabled(config_path: Path | None = None) -> bool:
    path = config_path or Path("camera_config.json")
    return bool(_read_config(path).get(KEEP_REJECTED_KEY, True))


def profile_snapshot(profile: BoardProfile) -> dict[str, object]:
    """Capture a deep copy of the profile before one game move is learned."""
    return copy.deepcopy(profile.to_dict())


def restore_profile(
    profile: BoardProfile,
    snapshot: dict[str, object],
) -> None:
    """Restore training and calibration in-place so existing references remain valid."""
    restored = BoardProfile.from_dict(copy.deepcopy(snapshot))
    profile.__dict__.clear()
    profile.__dict__.update(restored.__dict__)


def _counts(profile: BoardProfile) -> tuple[int, int]:
    accepted = sum(pattern.count for pattern in profile.move_patterns.values())
    rejected = sum(pattern.count for pattern in profile.rejected_patterns.values())
    return accepted, rejected


def show_training_settings(app_module: ModuleType) -> None:
    window = "Chess Camera - Board Training"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 820, 620)

    store = BoardProfileStore(app_module.PROFILE_DIRECTORY)
    store.load()
    config = _read_config(app_module.CONFIG_PATH)
    profile = store.get(str(config.get("active_profile", "")))
    if profile is None:
        profile = store.ensure_default()

    remove_undone = bool(config.get(REMOVE_UNDONE_KEY, True))
    keep_rejected = bool(config.get(KEEP_REJECTED_KEY, True))
    message = ""
    queue: list[str] = []
    buttons: list[Button] = []

    def mouse(event: int, x: int, y: int, _flags: int, _data: object) -> None:
        if event == cv2.EVENT_LBUTTONUP:
            action = clicked_action(buttons, x, y)
            if action:
                queue.append(action)

    cv2.setMouseCallback(window, mouse)

    while True:
        accepted, rejected = _counts(profile)
        view = np.zeros((620, 820, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        app_module.put_text(
            view,
            "Advanced Board Training",
            (42, 58),
            (100, 220, 255),
            0.92,
        )
        app_module.put_text(
            view,
            f"Preset: {profile.name[:42]}",
            (42, 102),
            (120, 255, 170),
            0.58,
        )
        app_module.put_text(
            view,
            f"Accepted samples: {accepted}    Rejected samples: {rejected}",
            (42, 140),
            (175, 185, 200),
            0.48,
        )

        learn = Button(
            "toggle_learn",
            f"Learn from confirmed games: {'ON' if profile.learning_enabled else 'OFF'}",
            42,
            185,
            520,
            54,
            active=profile.learning_enabled,
        )
        undo = Button(
            "toggle_undo",
            f"Remove undone moves: {'ON' if remove_undone else 'OFF'}",
            42,
            255,
            520,
            54,
            active=remove_undone,
        )
        rejected_button = Button(
            "toggle_rejected",
            f"Keep rejected examples: {'ON' if keep_rejected else 'OFF'}",
            42,
            325,
            520,
            54,
            active=keep_rejected,
        )
        previous = Button("previous_profile", "PREVIOUS", 590, 185, 185, 48)
        next_button = Button("next_profile", "NEXT", 590, 245, 185, 48)
        clear = Button("clear_training", "CLEAR TRAINING DATA", 590, 325, 185, 54)
        back = Button("back", "BACK", 590, 520, 185, 54)
        buttons = [learn, undo, rejected_button, previous, next_button, clear, back]
        for button in buttons:
            draw_button(view, button)

        app_module.put_text(
            view,
            "Undo cleanup restores the exact training state from before that move.",
            (42, 425),
            (175, 185, 200),
            0.46,
        )
        app_module.put_text(
            view,
            "Rejected examples help stop the same false detection from returning.",
            (42, 458),
            (175, 185, 200),
            0.46,
        )
        if message:
            app_module.put_text(
                view,
                message[:72],
                (42, 560),
                (120, 220, 255),
                0.46,
            )

        cv2.imshow(window, view)
        key = cv2.waitKey(25) & 0xFF
        action = queue.pop(0) if queue else None

        if action == "toggle_learn":
            profile.learning_enabled = not profile.learning_enabled
            store.save(profile)
            message = "Learning preference saved."
        elif action == "toggle_undo":
            remove_undone = not remove_undone
            config[REMOVE_UNDONE_KEY] = remove_undone
            _write_config(app_module.CONFIG_PATH, config)
            message = "Undo cleanup preference saved."
        elif action == "toggle_rejected":
            keep_rejected = not keep_rejected
            config[KEEP_REJECTED_KEY] = keep_rejected
            _write_config(app_module.CONFIG_PATH, config)
            message = "Rejected-example preference saved."
        elif action == "previous_profile":
            profile = store.cycle(profile.name, -1)
            config["active_profile"] = profile.name
            _write_config(app_module.CONFIG_PATH, config)
            message = f"Selected {profile.name}."
        elif action == "next_profile":
            profile = store.cycle(profile.name, 1)
            config["active_profile"] = profile.name
            _write_config(app_module.CONFIG_PATH, config)
            message = f"Selected {profile.name}."
        elif action == "clear_training":
            confirmed = app_module.ask_yes_no(
                "Clear training data?",
                (
                    f'Clear accepted and rejected training for "{profile.name}"? '
                    "Calibration and orientation will be kept."
                ),
            )
            cv2.namedWindow(window, cv2.WINDOW_NORMAL)
            cv2.setMouseCallback(window, mouse)
            if confirmed:
                profile.reset_training()
                store.save(profile)
                message = "Training data cleared; calibration was kept."
            else:
                message = "Training data was not changed."
        elif action == "back" or key == 27:
            cv2.destroyWindow(window)
            return

        try:
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                return
        except cv2.error:
            return


def install(app_module: ModuleType, navigation_module: ModuleType) -> None:
    """Add Board Training to Settings without hiding existing app settings."""
    original_settings = navigation_module.settings_screen

    def settings_hub() -> None:
        window = "Chess Camera - Settings"
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window, 760, 430)
        queue: list[str] = []
        buttons = [
            Button(
                "existing",
                "ENGINE, CAMERA & DETECTION",
                95,
                145,
                570,
                68,
                active=True,
            ),
            Button(
                "training",
                "ADVANCED BOARD TRAINING",
                95,
                235,
                570,
                68,
            ),
            Button("back", "BACK", 260, 340, 240, 54),
        ]

        def mouse(
            event: int,
            x: int,
            y: int,
            _flags: int,
            _data: object,
        ) -> None:
            if event == cv2.EVENT_LBUTTONUP:
                action = clicked_action(buttons, x, y)
                if action:
                    queue.append(action)

        cv2.setMouseCallback(window, mouse)
        while True:
            view = np.zeros((430, 760, 3), dtype=np.uint8)
            view[:] = (28, 31, 37)
            app_module.put_text(
                view,
                "Settings",
                (95, 72),
                (100, 220, 255),
                1.0,
            )
            app_module.put_text(
                view,
                "Choose which settings group to open.",
                (95, 110),
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
                cv2.resizeWindow(window, 760, 430)
                cv2.setMouseCallback(window, mouse)
            elif action == "training":
                cv2.destroyWindow(window)
                show_training_settings(app_module)
                cv2.namedWindow(window, cv2.WINDOW_NORMAL)
                cv2.resizeWindow(window, 760, 430)
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
