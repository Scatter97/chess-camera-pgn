from __future__ import annotations

from dataclasses import replace

import cv2
import numpy as np

import app
import app_navigation as navigation
import game_history
import pregame_ui
import ui_support as ui
from pregame_ui import Button


SESSION_BOARD_CALIBRATED = False


def board_options_menu() -> str | None:
    """Show board actions and always allow the modal window to close."""
    window = "Board Options"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 480, 300)
    buttons = [
        Button("profile_rename", "Rename preset", 65, 82, 350, 52),
        Button("profile_reset_training", "Reset training", 65, 149, 350, 52),
        Button("cancel", "CLOSE", 155, 222, 170, 46),
    ]
    queue: list[str] = []

    def mouse(event: int, x: int, y: int, _flags: int, _data: object) -> None:
        if event == cv2.EVENT_LBUTTONUP:
            action = pregame_ui.clicked_action(buttons, x, y)
            if action:
                queue.append(action)

    cv2.setMouseCallback(window, mouse)
    while True:
        view = np.zeros((300, 480, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        ui._put(view, "Board Options", (65, 50), (100, 220, 255), 0.80, 2)
        for button in buttons:
            pregame_ui.draw_button(view, button)
        ui._put(
            view,
            "Esc or the window X closes this menu.",
            (88, 292),
            (145, 155, 170),
            0.40,
        )

        cv2.imshow(window, view)
        key = cv2.waitKey(20) & 0xFF
        action = queue.pop(0) if queue else None

        if action in {"profile_rename", "profile_reset_training"}:
            cv2.destroyWindow(window)
            cv2.waitKey(1)
            return action
        if action == "cancel" or key == 27:
            cv2.destroyWindow(window)
            cv2.waitKey(1)
            return None
        try:
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                return None
        except cv2.error:
            return None


def install_consolidated_setup_ui() -> None:
    """Use one setup renderer instead of stacking overlapping patches."""
    original_apply = app.apply_setup_action

    def render(*args: object, **kwargs: object):
        view, buttons = pregame_ui.render_setup_screen(*args, **kwargs)
        focused_field = kwargs.get("focused_field")
        if focused_field is None and len(args) >= 2:
            focused_field = args[1]

        buttons = [
            button
            for button in buttons
            if button.action
            not in {"profile_rename", "profile_reset_training", "swap_players"}
        ]

        cv2.rectangle(view, (420, 132), (535, 218), (28, 31, 37), -1)
        swap = Button("swap_players", "", 463, 145, 58, 58)
        buttons.append(swap)
        pregame_ui.draw_button(view, swap)
        cv2.arrowedLine(
            view,
            (480, 190),
            (480, 158),
            (120, 255, 170),
            3,
            cv2.LINE_AA,
            tipLength=0.30,
        )
        cv2.arrowedLine(
            view,
            (503, 158),
            (503, 190),
            (120, 220, 255),
            3,
            cv2.LINE_AA,
            tipLength=0.30,
        )

        clear_button: Button | None = None
        if focused_field == "white":
            clear_button = Button("clear_white_name", "X", 375, 130, 30, 28)
        elif focused_field == "black":
            clear_button = Button("clear_black_name", "X", 375, 204, 30, 28)
        elif focused_field == "event":
            clear_button = Button("clear_event_name", "X", 495, 278, 30, 28)
        if clear_button is not None:
            buttons.append(clear_button)
            pregame_ui.draw_button(view, clear_button)

        cv2.rectangle(view, (145, 767), (540, 820), (28, 31, 37), -1)
        options = Button("board_options", "Board options", 155, 772, 375, 42)
        buttons.append(options)
        pregame_ui.draw_button(view, options)

        if navigation.IN_INITIAL_SETUP:
            buttons = [button for button in buttons if button.action != "start"]
            cv2.rectangle(view, (721, 832), (1099, 919), (28, 31, 37), -1)
            back = Button("main_menu", "BACK", 738, 840, 122, 58)
            start = Button("start", "START GAME", 880, 840, 180, 58, active=True)
            buttons.extend((back, start))
            pregame_ui.draw_button(view, back)
            pregame_ui.draw_button(view, start)

        return view, buttons

    def clicked(buttons: list[Button], x: int, y: int) -> str | None:
        for button in buttons:
            if button.action.startswith("clear_") and button.contains(x, y):
                return button.action

        action = pregame_ui.clicked_action(buttons, x, y)
        if action == "board_options":
            return board_options_menu()
        return action

    def apply_action(
        setup: pregame_ui.GameSetup,
        action: str,
    ) -> pregame_ui.GameSetup:
        if action == "clear_white_name":
            return replace(setup, white_name="")
        if action == "clear_black_name":
            return replace(setup, black_name="")
        if action == "clear_event_name":
            return replace(setup, event_name="")
        return original_apply(setup, action)

    app.render_setup_screen = render
    app.clicked_action = clicked
    app.apply_setup_action = apply_action


def run_game() -> bool:
    global SESSION_BOARD_CALIBRATED

    if not SESSION_BOARD_CALIBRATED:
        game_history.forget_saved_board_calibration()

    before = navigation.latest_mtime()
    try:
        app.main()
    except navigation.ReturnToHome:
        SESSION_BOARD_CALIBRATED = True
        return False
    except KeyboardInterrupt:
        return False

    SESSION_BOARD_CALIBRATED = True
    after = navigation.latest_mtime()
    return (
        after is not None
        and after != before
        and navigation.LAST_SETUP is not None
    )
