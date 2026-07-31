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
import ui_support as ui
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


def review_game(item: ui.HistoryGame) -> None:
    try:
        import chess.pgn

        with item.path.open(encoding="utf-8", errors="replace") as handle:
            game = chess.pgn.read_game(handle)
        if game is None:
            app.show_result_popup(
                "Cannot review game",
                "The selected PGN could not be read.",
            )
            return

        engine = configured_engine()
        if engine is None:
            app.show_result_popup(
                "Stockfish not found",
                "Open Settings from the main menu and choose a trusted UCI engine file.",
            )
            return

        moves = list(game.mainline_moves())
        review = app.analyze_game(
            moves,
            engine,
            progress=app.show_analysis_progress,
        )
        app.save_analysis_report(
            review,
            item.path.with_suffix(".analysis.json"),
        )
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
            subprocess.run(
                command,
                input=text,
                text=True,
                check=True,
                timeout=5,
            )
            return True
        except (OSError, subprocess.SubprocessError):
            continue
    return False


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
        ui._put(view, "Settings", (42, 58), (100, 220, 255), 0.95, 2)
        ui._put(view, "ANALYSIS ENGINE", (42, 115), (165, 175, 190), 0.50)
        ui._put(view, engine_name[:52], (42, 155), (120, 255, 170), 0.58)
        path_text = str(engine) if engine else "No executable selected"
        ui._put(view, path_text[-75:], (42, 190), (175, 185, 200), 0.43)
        ui._put(
            view,
            "Choose Stockfish or another trusted UCI-compatible engine executable.",
            (42, 230),
            (175, 185, 200),
            0.46,
        )

        choose = Button(
            "choose",
            "CHOOSE ENGINE FILE...",
            42,
            270,
            430,
            58,
            active=True,
        )
        back = Button("back", "BACK", 505, 270, 210, 58)
        buttons = [choose, back]
        for button in buttons:
            pregame_ui.draw_button(view, button)

        if message:
            ui._put(view, message[:70], (42, 380), (120, 220, 255), 0.46)

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

        try:
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                return
        except cv2.error:
            return


def install_navigation_patches() -> None:
    original_apply = app.apply_setup_action
    original_wizard = app.run_pregame_wizard

    def apply_action(setup: object, action: str):
        if action == "main_menu":
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

    app.apply_setup_action = apply_action
    app.run_pregame_wizard = wizard


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
        ui._put(view, "Game saved", (55, 68), (100, 220, 255), 1.0, 2)
        ui._put(
            view,
            "Rematch keeps both players, the event and the time control.",
            (55, 125),
            (185, 195, 210),
            0.50,
        )
        ui._put(
            view,
            "You can edit them again on the game-setup page.",
            (55, 160),
            (185, 195, 210),
            0.50,
        )
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
        try:
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                return "home"
        except cv2.error:
            return "home"


def latest_mtime() -> float | None:
    try:
        return (GAMES_DIR / "latest_game.pgn").stat().st_mtime
    except OSError:
        return None
