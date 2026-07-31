from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

import app
import app_navigation as navigation
import pregame_ui
import ui_support as ui
from pregame_ui import Button


def draw_evaluation_bar_left(
    view: np.ndarray,
    centipawns: int,
    mate: int | None,
) -> None:
    """Draw the review evaluation bar on the left side of the board."""
    top, bottom = 90, 610
    left, right = 20, 41
    white_fraction = app.evaluation_bar_fraction(centipawns, mate)
    split = top + int(round((bottom - top) * (1.0 - white_fraction)))
    cv2.rectangle(view, (left, top), (right, split), (38, 41, 47), -1)
    cv2.rectangle(view, (left, split), (right, bottom), (238, 238, 238), -1)
    cv2.rectangle(view, (left, top), (right, bottom), (115, 125, 142), 2)
    app.put_text(
        view,
        app._analysis_eval_text(centipawns, mate),
        (17, 78),
        (235, 235, 240),
        0.36,
    )


def _analysis_files_for_game(item: ui.HistoryGame) -> list[Path]:
    paths = [
        item.path.with_suffix(".analysis.json"),
        navigation.GAMES_DIR / f"{item.path.stem}_analysis.json",
    ]
    if item.path.name == "latest_game.pgn":
        paths.append(navigation.GAMES_DIR / "latest_analysis.json")

    unique: list[Path] = []
    for path in paths:
        if path not in unique:
            unique.append(path)
    return unique


def delete_history_game(item: ui.HistoryGame) -> tuple[bool, str]:
    confirmed = app.ask_yes_no(
        "Delete recorded game?",
        (
            f'Delete "{item.white} vs {item.black}" and its saved analysis? '
            "This cannot be undone."
        ),
    )
    if not confirmed:
        return False, "Game was not deleted."

    errors: list[str] = []
    for path in [item.path, *_analysis_files_for_game(item)]:
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            errors.append(f"{path.name}: {error}")

    if errors:
        return False, "Could not delete every file: " + "; ".join(errors)
    return True, "Game deleted."


def show_game_history() -> None:
    window = "Chess Camera - Game History"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 1180, 760)
    selected = 0
    scroll = 0
    message = ""
    queue: list[str] = []
    buttons: list[Button] = []

    def mouse(event: int, x: int, y: int, flags: int, _data: object) -> None:
        nonlocal scroll
        if event == cv2.EVENT_MOUSEWHEEL:
            delta = (int(flags) >> 16) & 0xFFFF
            if delta & 0x8000:
                delta -= 0x10000
            scroll += -1 if delta > 0 else 1
        elif event == cv2.EVENT_LBUTTONUP:
            action = pregame_ui.clicked_action(buttons, x, y)
            if action:
                queue.append(action)

    cv2.setMouseCallback(window, mouse)
    while True:
        games = ui.load_history()
        visible = 8
        scroll = max(0, min(scroll, max(0, len(games) - visible)))
        if games:
            selected = max(0, min(selected, len(games) - 1))
            if selected < scroll:
                scroll = selected
            if selected >= scroll + visible:
                scroll = selected - visible + 1
        else:
            selected = 0
            scroll = 0

        view = np.zeros((760, 1180, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        ui._put(view, "Game History", (35, 48), (100, 220, 255), 0.95, 2)
        ui._put(
            view,
            "Recorded over-the-board games",
            (35, 80),
            (165, 175, 190),
            0.50,
        )
        buttons = []

        if not games:
            ui._put(
                view,
                "No completed games found in the games folder.",
                (40, 145),
                scale=0.62,
            )

        for row, item in enumerate(games[scroll : scroll + visible]):
            index = scroll + row
            y = 110 + row * 70
            active = index == selected
            fill = (52, 90, 72) if active else (43, 47, 55)
            cv2.rectangle(view, (35, y), (770, y + 58), fill, -1)
            cv2.rectangle(
                view,
                (35, y),
                (770, y + 58),
                (120, 255, 170) if active else (85, 92, 105),
                2,
            )
            ui._put(
                view,
                f"{item.white[:20]}  {item.result}  {item.black[:20]}",
                (50, y + 25),
                scale=0.58,
            )
            ui._put(
                view,
                f"{item.date}   {item.moves} moves   {item.time_control}",
                (50, y + 48),
                (165, 175, 190),
                0.43,
            )
            buttons.append(Button(f"select_{index}", "", 35, y, 735, 58))

        back = Button("back", "BACK", 35, 690, 170, 48)
        buttons.append(back)
        pregame_ui.draw_button(view, back)
        ui._put(
            view,
            "Scroll with the mouse wheel or use the keyboard arrows.",
            (230, 721),
            (135, 145, 160),
            0.42,
        )

        if games:
            item = games[selected]
            ui._put(view, "GAME DETAILS", (820, 115), (100, 220, 255), 0.58)
            details = [
                f"White: {item.white}",
                f"Black: {item.black}",
                f"Result: {item.result}",
                f"How it ended: {item.termination}",
                f"Moves: {item.moves}",
                f"Time control: {item.time_control}",
                f"Date: {item.date}",
                f"Event: {item.event}",
                (
                    f"White accuracy: {item.white_accuracy:.1f}%"
                    if item.white_accuracy is not None
                    else "White accuracy: Not reviewed"
                ),
                (
                    f"Black accuracy: {item.black_accuracy:.1f}%"
                    if item.black_accuracy is not None
                    else "Black accuracy: Not reviewed"
                ),
            ]
            for index, line in enumerate(details):
                ui._put(view, line[:43], (820, 160 + index * 38), scale=0.50)

            review = Button(
                "review",
                "REVIEW WITH STOCKFISH",
                820,
                545,
                315,
                52,
                active=True,
            )
            copy_pgn = Button("copy_pgn", "COPY PGN", 820, 610, 150, 52)
            delete = Button("delete", "DELETE", 985, 610, 150, 52)
            buttons.extend((review, copy_pgn, delete))
            for item_button in (review, copy_pgn, delete):
                pregame_ui.draw_button(view, item_button)

        if message:
            ui._put(view, message[:55], (820, 710), (120, 220, 255), 0.43)

        cv2.imshow(window, view)
        key = cv2.waitKey(25) & 0xFF
        action = queue.pop(0) if queue else None

        if action and action.startswith("select_"):
            selected = int(action.split("_", 1)[1])
            message = ""
        elif key in (82, ord("w")):
            scroll -= 1
        elif key in (84, ord("s")):
            scroll += 1
        elif action == "review" and games:
            navigation.review_game(games[selected])
            cv2.namedWindow(window, cv2.WINDOW_NORMAL)
            cv2.setMouseCallback(window, mouse)
        elif action == "copy_pgn" and games:
            try:
                copied = navigation.copy_text(
                    games[selected].path.read_text(encoding="utf-8")
                )
                message = (
                    "PGN copied to clipboard." if copied else "Could not copy PGN."
                )
            except OSError as error:
                message = f"Could not read PGN: {error}"
        elif action == "delete" and games:
            deleted, message = delete_history_game(games[selected])
            cv2.namedWindow(window, cv2.WINDOW_NORMAL)
            cv2.setMouseCallback(window, mouse)
            if deleted:
                selected = max(0, selected - 1)
        elif action == "back" or key == 27:
            cv2.destroyWindow(window)
            return

        try:
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                return
        except cv2.error:
            return


def forget_saved_board_calibration() -> None:
    """Remove only board-corner calibration; keep other saved settings."""
    data = navigation._config()
    data.pop("board_corners", None)
    data.pop("corners", None)
    navigation._save_config(data)

    try:
        store = app.BoardProfileStore(app.PROFILE_DIRECTORY)
        store.load()
        profile = store.get(str(data.get("active_profile", "")))
        if profile is not None:
            profile.board_corners = None
            store.save(profile)
    except (OSError, ValueError, TypeError):
        pass
