from __future__ import annotations

from dataclasses import replace
from types import ModuleType
from typing import Callable

import cv2
import numpy as np

import multi_move_recovery
from pregame_ui import Button, clicked_action, draw_button


def recovery_settings_screen(app_module: ModuleType) -> None:
    settings = multi_move_recovery.load_settings(app_module.CONFIG_PATH)
    window = "Chess Camera - Experimental Multi-Move Recovery"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 820, 620)
    queue: list[str] = []
    buttons: list[Button] = []
    message = "Changes save immediately. This feature is experimental."

    def persist() -> None:
        multi_move_recovery.save_settings(app_module.CONFIG_PATH, settings)

    def mouse(event: int, x: int, y: int, _flags: int, _data: object) -> None:
        if event == cv2.EVENT_LBUTTONUP:
            action = clicked_action(buttons, x, y)
            if action:
                queue.append(action)

    cv2.setMouseCallback(window, mouse)
    while True:
        view = np.zeros((620, 820, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        app_module.put_text(
            view,
            "Experimental Multi-Move Recovery",
            (48, 58),
            (100, 220, 255),
            0.88,
        )
        app_module.put_text(
            view,
            "Searches legal two- or three-ply sequences when one move cannot explain the board.",
            (48, 96),
            (175, 185, 200),
            0.43,
        )
        app_module.put_text(
            view,
            "Ambiguous sequences always require confirmation.",
            (48, 124),
            (175, 185, 200),
            0.43,
        )

        enabled = Button(
            "toggle_enabled",
            f"MULTI-MOVE RECOVERY: {'ON' if settings.enabled else 'OFF'}",
            48,
            160,
            540,
            58,
            active=settings.enabled,
        )
        depth = Button(
            "toggle_depth",
            f"MAXIMUM RECOVERY: {settings.max_depth} HALF-MOVES",
            48,
            245,
            540,
            54,
            enabled=settings.enabled,
        )
        automatic = Button(
            "toggle_auto",
            f"AUTO-ACCEPT CERTAIN SEQUENCES: {'ON' if settings.auto_accept else 'OFF'}",
            48,
            330,
            540,
            54,
            active=settings.auto_accept,
            enabled=settings.enabled,
        )
        threshold_down = Button(
            "threshold_down",
            "-",
            48,
            425,
            85,
            48,
            enabled=settings.enabled and settings.auto_accept,
        )
        threshold_up = Button(
            "threshold_up",
            "+",
            145,
            425,
            85,
            48,
            enabled=settings.enabled and settings.auto_accept,
        )
        back = Button("back", "BACK", 590, 520, 180, 56)
        buttons = [
            enabled,
            depth,
            automatic,
            threshold_down,
            threshold_up,
            back,
        ]
        for button in buttons:
            draw_button(view, button)

        app_module.put_text(
            view,
            f"Automatic acceptance threshold: {settings.auto_threshold:.0%}",
            (260, 458),
            (
                (120, 255, 170)
                if settings.enabled and settings.auto_accept
                else (135, 140, 150)
            ),
            0.57,
        )
        app_module.put_text(
            view,
            "Recommended while testing: recovery ON, depth 3, automatic acceptance OFF.",
            (48, 510),
            (80, 160, 255),
            0.43,
        )
        app_module.put_text(
            view,
            message[:94],
            (48, 590),
            (120, 220, 255),
            0.42,
        )

        cv2.imshow(window, view)
        key = cv2.waitKey(20) & 0xFF
        action = queue.pop(0) if queue else None
        if action == "toggle_enabled":
            settings = replace(settings, enabled=not settings.enabled)
            persist()
            message = (
                "Experimental multi-move recovery enabled."
                if settings.enabled
                else "Experimental multi-move recovery disabled."
            )
        elif action == "toggle_depth":
            settings = replace(
                settings,
                max_depth=2 if settings.max_depth == 3 else 3,
            )
            persist()
            message = f"Maximum recovery depth set to {settings.max_depth} half-moves."
        elif action == "toggle_auto":
            settings = replace(settings, auto_accept=not settings.auto_accept)
            persist()
            message = (
                f"Certain sequences may auto-accept at {settings.auto_threshold:.0%}."
                if settings.auto_accept
                else "Recovered sequences require player confirmation."
            )
        elif action == "threshold_down":
            settings = replace(
                settings,
                auto_threshold=max(
                    multi_move_recovery.MIN_AUTO_THRESHOLD,
                    round(settings.auto_threshold - 0.01, 3),
                ),
            )
            persist()
            message = f"Automatic threshold set to {settings.auto_threshold:.0%}."
        elif action == "threshold_up":
            settings = replace(
                settings,
                auto_threshold=min(
                    multi_move_recovery.MAX_AUTO_THRESHOLD,
                    round(settings.auto_threshold + 0.01, 3),
                ),
            )
            persist()
            message = f"Automatic threshold set to {settings.auto_threshold:.0%}."
        elif action == "back" or key == 27:
            cv2.destroyWindow(window)
            return
        try:
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                return
        except cv2.error:
            return


def install(
    feature_settings_module: ModuleType,
    app_module: ModuleType,
) -> None:
    """Add an experimental sub-page without changing stable settings code."""
    if getattr(feature_settings_module, "_multi_move_settings_installed", False):
        return

    original_screen: Callable = feature_settings_module.advanced_detection_screen

    def advanced_detection_hub(_app_module: ModuleType) -> None:
        window = "Chess Camera - Advanced Detection"
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window, 780, 470)
        queue: list[str] = []
        buttons = [
            Button(
                "confidence",
                "CONFIDENCE AUTO-APPROVAL",
                85,
                130,
                610,
                68,
            ),
            Button(
                "multi_move",
                "EXPERIMENTAL MULTI-MOVE RECOVERY",
                85,
                225,
                610,
                68,
                active=True,
            ),
            Button("back", "BACK", 255, 365, 270, 58),
        ]

        def mouse(event: int, x: int, y: int, _flags: int, _data: object) -> None:
            if event == cv2.EVENT_LBUTTONUP:
                action = clicked_action(buttons, x, y)
                if action:
                    queue.append(action)

        cv2.setMouseCallback(window, mouse)
        while True:
            view = np.zeros((470, 780, 3), dtype=np.uint8)
            view[:] = (28, 31, 37)
            app_module.put_text(
                view,
                "Advanced Detection",
                (85, 70),
                (100, 220, 255),
                1.0,
            )
            app_module.put_text(
                view,
                "Stable options remain separate from experimental recovery.",
                (85, 105),
                (175, 185, 200),
                0.46,
            )
            for button in buttons:
                draw_button(view, button)
            cv2.imshow(window, view)
            key = cv2.waitKey(25) & 0xFF
            action = queue.pop(0) if queue else None
            if action == "confidence":
                cv2.destroyWindow(window)
                original_screen(app_module)
                cv2.namedWindow(window, cv2.WINDOW_NORMAL)
                cv2.resizeWindow(window, 780, 470)
                cv2.setMouseCallback(window, mouse)
            elif action == "multi_move":
                cv2.destroyWindow(window)
                recovery_settings_screen(app_module)
                cv2.namedWindow(window, cv2.WINDOW_NORMAL)
                cv2.resizeWindow(window, 780, 470)
                cv2.setMouseCallback(window, mouse)
            elif action == "back" or key == 27:
                cv2.destroyWindow(window)
                return
            try:
                if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                    return
            except cv2.error:
                return

    feature_settings_module.advanced_detection_screen = advanced_detection_hub
    feature_settings_module._multi_move_settings_installed = True
