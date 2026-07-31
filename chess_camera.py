from __future__ import annotations

import cv2
import numpy as np

import app
import app_navigation as navigation
import chess960_generator
import game_history
import game_session
import opening_explorer
import pregame_ui
import ui_support as ui
from pregame_ui import Button
from version import APP_VERSION, VERSION_LABEL


def home_screen() -> str:
    """Show a scalable feature grid with room for future tools."""
    window = f"Chess Camera {APP_VERSION}"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 1120, 760)

    buttons = [
        Button("start", "START OTB GAME", 55, 180, 310, 105, active=True),
        Button("history", "GAME HISTORY", 405, 180, 310, 105),
        Button("chess960", "CHESS960 GENERATOR", 755, 180, 310, 105),
        Button("opening", "OPENING EXPLORER", 55, 360, 310, 105),
        Button("settings", "SETTINGS", 405, 360, 310, 105),
        Button(
            "future",
            "MORE FEATURES SOON",
            755,
            360,
            310,
            105,
            enabled=False,
        ),
        Button("exit", "EXIT", 430, 635, 260, 56),
    ]
    queue: list[str] = []

    def mouse(event: int, x: int, y: int, _flags: int, _data: object) -> None:
        if event == cv2.EVENT_LBUTTONUP:
            action = pregame_ui.clicked_action(buttons, x, y)
            if action:
                queue.append(action)

    cv2.setMouseCallback(window, mouse)
    while True:
        view = np.zeros((760, 1120, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        ui._put(view, "Chess Camera", (55, 78), (100, 220, 255), 1.25, 2)
        ui._put(view, VERSION_LABEL, (57, 120), (120, 255, 170), 0.62)
        ui._put(
            view,
            "Record games, review them, and use local chess tools.",
            (57, 155),
            (165, 175, 190),
            0.52,
        )

        for button in buttons:
            pregame_ui.draw_button(view, button)

        descriptions = [
            ("Camera recording and PGN", 75, 320),
            ("Saved games and analysis", 425, 320),
            ("Random legal start position", 775, 320),
            ("Built-in or custom book", 75, 500),
            ("Engine and app options", 425, 500),
            ("Reserved expansion space", 775, 500),
        ]
        for text, x, y in descriptions:
            ui._put(view, text, (x, y), (175, 185, 200), 0.40)

        ui._put(
            view,
            "Feature cards can be replaced or expanded in later versions.",
            (320, 725),
            (135, 145, 160),
            0.42,
        )

        cv2.imshow(window, view)
        key = cv2.waitKey(25) & 0xFF
        action = queue.pop(0) if queue else None
        if action in {
            "start",
            "history",
            "chess960",
            "opening",
            "settings",
            "exit",
        }:
            cv2.destroyWindow(window)
            return action
        if key == 27:
            cv2.destroyWindow(window)
            return "exit"
        try:
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                return "exit"
        except cv2.error:
            return "exit"


def main() -> None:
    ui.install_profile_creation_prompt()
    navigation.install_navigation_patches()
    game_session.install_consolidated_setup_ui()
    app.draw_evaluation_bar = game_history.draw_evaluation_bar_left

    while True:
        action = home_screen()
        if action == "history":
            game_history.show_game_history()
        elif action == "chess960":
            chess960_generator.show_chess960_generator()
        elif action == "opening":
            opening_explorer.show_opening_explorer()
        elif action == "settings":
            navigation.settings_screen()
        elif action == "start":
            saved = game_session.run_game()
            while saved:
                post_action = navigation.post_game_screen()
                if post_action != "rematch" or navigation.LAST_SETUP is None:
                    break
                navigation.REMATCH_SETUP = navigation.LAST_SETUP
                saved = game_session.run_game()
        else:
            return


if __name__ == "__main__":
    main()
