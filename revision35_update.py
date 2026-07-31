from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

import app
import pregame_ui
import revision35 as base
from pregame_ui import Button

CONFIG_PATH = app.CONFIG_PATH
GAMES_DIR = Path("games")


class ReturnToHome(RuntimeError):
    pass


LAST_SETUP: Any | None = None
REMATCH_SETUP: Any | None = None
IN_INITIAL_SETUP = False


def _config() -> dict[str, object]:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _save_config(data: dict[str, object]) -> None:
    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def configured_engine() -> Path | None:
    value = _config().get("engine_path")
    return app.find_stockfish(str(value) if value else None)


def review_game(item: base.HistoryGame) -> None:
    try:
        import chess.pgn

        with item.path.open(encoding="utf-8", errors="replace") as handle:
            game = chess.pgn.read_game(handle)
        if game is None:
            app.show_result_popup("Cannot review game", "The selected PGN could not be read.")
            return
        engine = configured_engine()
        if engine is None:
            app.show_result_popup(
                "Stockfish not found",
                "Open Settings from the main menu and choose a trusted UCI engine file.",
            )
            return
        moves = list(game.mainline_moves())
        review = app.analyze_game(moves, engine, progress=app.show_analysis_progress)
        app.save_analysis_report(review, item.path.with_suffix(".analysis.json"))
        try:
            cv2.destroyWindow("Stockfish post-game analysis")
        except cv2.error:
            pass
        app.show_game_review(review, moves, item.white, item.black)
    except Exception as error:
        app.show_result_popup("Review failed", str(error))


def copy_text(text: str) -> bool:
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()
        return True
    except Exception:
        pass

    commands: list[list[str]] = []
    if sys.platform == "win32":
        commands.append(["clip"])
    elif sys.platform == "darwin":
        commands.append(["pbcopy"])
    else:
        if shutil.which("wl-copy"):
            commands.append(["wl-copy"])
        if shutil.which("xclip"):
            commands.append(["xclip", "-selection", "clipboard"])
    for command in commands:
        try:
            subprocess.run(command, input=text, text=True, check=True, timeout=5)
            return True
        except (OSError, subprocess.SubprocessError):
            continue
    return False


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
        games = base.load_history()
        visible = 8
        scroll = max(0, min(scroll, max(0, len(games) - visible)))
        if games:
            selected = max(0, min(selected, len(games) - 1))
            if selected < scroll:
                scroll = selected
            if selected >= scroll + visible:
                scroll = selected - visible + 1

        view = np.zeros((760, 1180, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        base._put(view, "Game History", (35, 48), (100, 220, 255), 0.95, 2)
        base._put(view, "Recorded over-the-board games", (35, 80), (165, 175, 190), 0.50)
        buttons = []

        if not games:
            base._put(view, "No completed games found in the games folder.", (40, 145), scale=0.62)
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
            base._put(view, f"{item.white[:20]}  {item.result}  {item.black[:20]}", (50, y + 25), scale=0.58)
            base._put(view, f"{item.date}   {item.moves} moves   {item.time_control}", (50, y + 48), (165, 175, 190), 0.43)
            buttons.append(Button(f"select_{index}", "", 35, y, 735, 58))

        back = Button("back", "BACK", 35, 690, 170, 48)
        up = Button("up", "UP", 225, 690, 110, 48, enabled=scroll > 0)
        down = Button("down", "DOWN", 350, 690, 110, 48, enabled=scroll + visible < len(games))
        buttons.extend((back, up, down))
        for button in (back, up, down):
            pregame_ui.draw_button(view, button)

        if games:
            item = games[selected]
            base._put(view, "GAME DETAILS", (820, 115), (100, 220, 255), 0.58)
            details = [
                f"White: {item.white}",
                f"Black: {item.black}",
                f"Result: {item.result}",
                f"How it ended: {item.termination}",
                f"Moves: {item.moves}",
                f"Time control: {item.time_control}",
                f"Date: {item.date}",
                f"Event: {item.event}",
                f"White accuracy: {item.white_accuracy:.1f}%" if item.white_accuracy is not None else "White accuracy: Not reviewed",
                f"Black accuracy: {item.black_accuracy:.1f}%" if item.black_accuracy is not None else "Black accuracy: Not reviewed",
            ]
            for index, line in enumerate(details):
                base._put(view, line[:43], (820, 160 + index * 38), scale=0.50)
            review = Button("review", "REVIEW WITH STOCKFISH", 820, 555, 315, 52, active=True)
            copy_pgn = Button("copy_pgn", "COPY PGN", 820, 620, 315, 52)
            buttons.extend((review, copy_pgn))
            pregame_ui.draw_button(view, review)
            pregame_ui.draw_button(view, copy_pgn)

        if message:
            base._put(view, message[:45], (820, 710), (120, 220, 255), 0.43)
        cv2.imshow(window, view)
        key = cv2.waitKey(25) & 0xFF
        action = queue.pop(0) if queue else None
        if action and action.startswith("select_"):
            selected = int(action.split("_", 1)[1])
            message = ""
        elif action == "up" or key in (82, ord("w")):
            scroll -= 1
        elif action == "down" or key in (84, ord("s")):
            scroll += 1
        elif action == "review" and games:
            review_game(games[selected])
            cv2.namedWindow(window, cv2.WINDOW_NORMAL)
            cv2.setMouseCallback(window, mouse)
        elif action == "copy_pgn" and games:
            try:
                copied = copy_text(games[selected].path.read_text(encoding="utf-8"))
                message = "PGN copied to clipboard." if copied else "Could not copy PGN."
            except OSError as error:
                message = f"Could not read PGN: {error}"
        elif action == "back" or key == 27:
            cv2.destroyWindow(window)
            return


def settings_screen() -> None:
    window = "Chess Camera - Settings"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 760, 440)
    engine = configured_engine()
    try:
        engine_name = app.probe_uci_engine(engine) if engine else "No engine selected"
    except app.AnalysisUnavailable:
        engine_name = engine.name if engine else "No engine selected"
    message = ""
    queue: list[str] = []
    buttons: list[Button] = []

    def mouse(event: int, x: int, y: int, _flags: int, _data: object) -> None:
        if event == cv2.EVENT_LBUTTONUP:
            action = pregame_ui.clicked_action(buttons, x, y)
            if action:
                queue.append(action)

    cv2.setMouseCallback(window, mouse)
    while True:
        view = np.zeros((440, 760, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        base._put(view, "Settings", (42, 58), (100, 220, 255), 0.95, 2)
        base._put(view, "ANALYSIS ENGINE", (42, 115), (165, 175, 190), 0.50)
        base._put(view, engine_name[:52], (42, 155), (120, 255, 170), 0.58)
        path_text = str(engine) if engine else "No executable selected"
        base._put(view, path_text[-75:], (42, 190), (175, 185, 200), 0.43)
        base._put(view, "Choose Stockfish or another trusted UCI-compatible engine executable.", (42, 230), (175, 185, 200), 0.46)
        choose = Button("choose", "CHOOSE ENGINE FILE...", 42, 270, 430, 58, active=True)
        back = Button("back", "BACK", 505, 270, 210, 58)
        buttons = [choose, back]
        for button in buttons:
            pregame_ui.draw_button(view, button)
        if message:
            base._put(view, message[:70], (42, 380), (120, 220, 255), 0.46)
        cv2.imshow(window, view)
        key = cv2.waitKey(25) & 0xFF
        action = queue.pop(0) if queue else None
        if action == "choose":
            selected, picker_error = app.choose_uci_engine_file(engine)
            cv2.namedWindow(window, cv2.WINDOW_NORMAL)
            cv2.setMouseCallback(window, mouse)
            if picker_error:
                message = picker_error
                continue
            if selected is None:
                message = "Engine selection cancelled."
                continue
            resolved = app.find_stockfish(str(selected))
            if resolved is None:
                message = "That file is not an executable engine."
                continue
            try:
                selected_name = app.probe_uci_engine(resolved)
            except app.AnalysisUnavailable as error:
                message = str(error)
                continue
            data = _config()
            data["engine_path"] = str(resolved)
            _save_config(data)
            engine, engine_name = resolved, selected_name
            message = f"Saved engine: {selected_name}"
        elif action == "back" or key == 27:
            cv2.destroyWindow(window)
            return


def install_navigation_patches() -> None:
    global IN_INITIAL_SETUP
    original_render = app.render_setup_screen
    original_apply = app.apply_setup_action
    original_wizard = app.run_pregame_wizard

    def render(*args: object, **kwargs: object):
        view, buttons = original_render(*args, **kwargs)
        if not IN_INITIAL_SETUP:
            return view, buttons
        buttons = [button for button in buttons if button.action != "start"]
        cv2.rectangle(view, (700, 832), (1070, 906), (28, 31, 37), -1)
        back = Button("revision35_home", "BACK", 710, 840, 135, 58)
        start = Button("start", "START GAME", 865, 840, 195, 58, active=True)
        buttons.extend((back, start))
        pregame_ui.draw_button(view, back)
        pregame_ui.draw_button(view, start)
        return view, buttons

    def apply_action(setup: object, action: str):
        if action == "revision35_home":
            raise ReturnToHome
        return original_apply(setup, action)

    def wizard(*args: object, **kwargs: object):
        global LAST_SETUP, REMATCH_SETUP, IN_INITIAL_SETUP
        positional = list(args)
        allow_cancel = bool(kwargs.get("allow_cancel", False))
        if len(positional) >= 8 and "allow_cancel" not in kwargs:
            allow_cancel = bool(positional[7])
        initial = not allow_cancel
        IN_INITIAL_SETUP = initial
        if initial and REMATCH_SETUP is not None:
            if len(positional) >= 2:
                positional[1] = REMATCH_SETUP
            else:
                kwargs["setup"] = REMATCH_SETUP
            REMATCH_SETUP = None
        if initial:
            if len(positional) >= 8:
                positional[7] = True
            else:
                kwargs["allow_cancel"] = True
        try:
            result = original_wizard(*positional, **kwargs)
        finally:
            IN_INITIAL_SETUP = False
        if initial and result is None:
            raise ReturnToHome
        if result is not None:
            LAST_SETUP = result[0]
        return result

    app.render_setup_screen = render
    app.apply_setup_action = apply_action
    app.run_pregame_wizard = wizard


def home_screen() -> str:
    window = "Chess Camera Revision 35"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 960, 680)
    buttons = [
        Button("start", "START RECORDED OTB GAME", 220, 195, 520, 82, active=True),
        Button("history", "GAME HISTORY", 220, 305, 520, 72),
        Button("settings", "SETTINGS", 220, 405, 520, 68),
        Button("exit", "EXIT", 350, 515, 260, 58),
    ]
    queue: list[str] = []

    def mouse(event: int, x: int, y: int, _flags: int, _data: object) -> None:
        if event == cv2.EVENT_LBUTTONUP:
            action = pregame_ui.clicked_action(buttons, x, y)
            if action:
                queue.append(action)

    cv2.setMouseCallback(window, mouse)
    while True:
        view = np.zeros((680, 960, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        base._put(view, "Chess Camera", (70, 90), (100, 220, 255), 1.25, 2)
        base._put(view, "Revision 35", (72, 130), (120, 255, 170), 0.65)
        base._put(view, "Record physical chess games and review them locally.", (72, 168), (165, 175, 190), 0.54)
        for button in buttons:
            pregame_ui.draw_button(view, button)
        base._put(view, "More features can be added here later.", (305, 640), (135, 145, 160), 0.45)
        cv2.imshow(window, view)
        key = cv2.waitKey(25) & 0xFF
        action = queue.pop(0) if queue else None
        if action in {"start", "history", "settings", "exit"}:
            cv2.destroyWindow(window)
            return action
        if key == 27:
            cv2.destroyWindow(window)
            return "exit"


def post_game_screen() -> str:
    window = "Game saved"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 760, 430)
    buttons = [
        Button("rematch", "REMATCH", 80, 235, 280, 68, active=True),
        Button("home", "MAIN MENU", 400, 235, 280, 68),
    ]
    queue: list[str] = []

    def mouse(event: int, x: int, y: int, _flags: int, _data: object) -> None:
        if event == cv2.EVENT_LBUTTONUP:
            action = pregame_ui.clicked_action(buttons, x, y)
            if action:
                queue.append(action)

    cv2.setMouseCallback(window, mouse)
    while True:
        view = np.zeros((430, 760, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        base._put(view, "Game saved", (55, 68), (100, 220, 255), 1.0, 2)
        base._put(view, "Rematch keeps both players, the event and the time control.", (55, 125), (185, 195, 210), 0.50)
        base._put(view, "You can edit them again on the game-setup page.", (55, 160), (185, 195, 210), 0.50)
        for button in buttons:
            pregame_ui.draw_button(view, button)
        cv2.imshow(window, view)
        key = cv2.waitKey(25) & 0xFF
        action = queue.pop(0) if queue else None
        if action in {"rematch", "home"}:
            cv2.destroyWindow(window)
            return action
        if key == 27:
            cv2.destroyWindow(window)
            return "home"


def latest_mtime() -> float | None:
    try:
        return (GAMES_DIR / "latest_game.pgn").stat().st_mtime
    except OSError:
        return None


def run_game() -> bool:
    before = latest_mtime()
    try:
        app.main()
    except ReturnToHome:
        return False
    after = latest_mtime()
    return after is not None and after != before and LAST_SETUP is not None


def main() -> None:
    global REMATCH_SETUP
    base.install_setup_patches()
    install_navigation_patches()
    while True:
        action = home_screen()
        if action == "history":
            show_game_history()
        elif action == "settings":
            settings_screen()
        elif action == "start":
            saved = run_game()
            while saved:
                post_action = post_game_screen()
                if post_action != "rematch" or LAST_SETUP is None:
                    break
                REMATCH_SETUP = LAST_SETUP
                saved = run_game()
        else:
            return


if __name__ == "__main__":
    main()
