from __future__ import annotations

import cv2
import numpy as np

import app
import chess960_generator
import pregame_ui
import revision35 as base
import revision35_final as final
import revision35_patch2 as patch2
import revision35_update as update
from pregame_ui import Button


VERSION_LABEL = "Rev. 35 (Main Menu Update)"


def home_screen() -> str:
    window = "Chess Camera - Rev. 35"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 960, 760)
    buttons = [
        Button("start", "START RECORDED OTB GAME", 220, 175, 520, 82, active=True),
        Button("history", "GAME HISTORY", 220, 280, 520, 68),
        Button("chess960", "CHESS960 POSITION GENERATOR", 220, 370, 520, 68),
        Button("settings", "SETTINGS", 220, 460, 520, 68),
        Button("exit", "EXIT", 350, 570, 260, 58),
    ]
    queue: list[str] = []

    def mouse(event: int, x: int, y: int, _flags: int, _data: object) -> None:
        if event == cv2.EVENT_LBUTTONUP:
            action = pregame_ui.clicked_action(buttons, x, y)
            if action:
                queue.append(action)

    cv2.setMouseCallback(window, mouse)
    while True:
        view = np.zeros((760, 960, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        base._put(view, "Chess Camera", (70, 90), (100, 220, 255), 1.25, 2)
        base._put(view, VERSION_LABEL, (72, 132), (120, 255, 170), 0.62)
        base._put(
            view,
            "Record physical chess games and generate Chess960 positions.",
            (72, 165),
            (165, 175, 190),
            0.52,
        )
        for button in buttons:
            pregame_ui.draw_button(view, button)
        base._put(
            view,
            "More features can be added here later.",
            (305, 720),
            (135, 145, 160),
            0.45,
        )
        cv2.imshow(window, view)
        key = cv2.waitKey(25) & 0xFF
        action = queue.pop(0) if queue else None
        if action in {"start", "history", "chess960", "settings", "exit"}:
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
    base.install_setup_patches()
    update.install_navigation_patches()
    final.install_consolidated_setup_ui()
    app.draw_evaluation_bar = patch2.draw_evaluation_bar_left

    while True:
        action = home_screen()
        if action == "history":
            patch2.show_game_history()
        elif action == "chess960":
            chess960_generator.show_chess960_generator()
        elif action == "settings":
            update.settings_screen()
        elif action == "start":
            saved = final.run_game()
            while saved:
                post_action = update.post_game_screen()
                if post_action != "rematch" or update.LAST_SETUP is None:
                    break
                update.REMATCH_SETUP = update.LAST_SETUP
                saved = final.run_game()
        else:
            return


if __name__ == "__main__":
    main()
