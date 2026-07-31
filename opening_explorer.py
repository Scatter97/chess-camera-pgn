from __future__ import annotations

import sys
from pathlib import Path

import chess
import chess.polyglot
import cv2
import numpy as np

import app
import pregame_ui
import revision35 as base
import revision35_update as update
from pregame_ui import Button


WINDOW_NAME = "Chess Camera - Opening Explorer"
BOOK_DIRECTORY = Path("books")
MAX_VISIBLE_MOVES = 10


def _configured_book() -> Path | None:
    configured = update._config().get("opening_book_path")
    if isinstance(configured, str):
        path = Path(configured)
        if path.is_file():
            return path
    if BOOK_DIRECTORY.is_dir():
        return next(iter(sorted(BOOK_DIRECTORY.glob("*.bin"))), None)
    return None


def _save_book(path: Path) -> None:
    data = update._config()
    data["opening_book_path"] = str(path)
    update._save_config(data)


def _choose_book_file(current: Path | None) -> tuple[Path | None, str | None]:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        return None, (
            "The system file picker is unavailable. On Ubuntu, install python3-tk."
        )

    root: object | None = None
    try:
        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except tk.TclError:
            pass
        initial_directory = (
            str(current.parent)
            if current is not None and current.exists()
            else str(BOOK_DIRECTORY if BOOK_DIRECTORY.exists() else Path.cwd())
        )
        selected = filedialog.askopenfilename(
            parent=root,
            title="Choose a Polyglot opening book",
            initialdir=initial_directory,
            filetypes=[
                ("Polyglot opening book", "*.bin"),
                ("All files", "*"),
            ],
        )
    except tk.TclError as error:
        return None, f"Could not open the file picker: {error}"
    finally:
        if root is not None:
            try:
                root.destroy()  # type: ignore[attr-defined]
            except tk.TclError:
                pass

    if not selected:
        return None, None
    path = Path(selected)
    if not path.is_file():
        return None, "The selected opening book could not be found."
    return path, None


def _book_entries(
    book_path: Path | None,
    board: chess.Board,
) -> tuple[list[chess.polyglot.Entry], str | None]:
    if book_path is None:
        return [], None
    try:
        with chess.polyglot.open_reader(str(book_path)) as reader:
            entries = list(reader.find_all(board))
    except (OSError, ValueError, IndexError) as error:
        return [], f"Could not read opening book: {error}"
    entries.sort(key=lambda entry: (-entry.weight, entry.move.uci()))
    return entries, None


def _render_position(board: chess.Board, size: int = 560) -> np.ndarray:
    """Use the exact board and piece renderer used by live play and analysis."""
    rendered = app.render_virtual_board(board)
    return cv2.resize(rendered, (size, size), interpolation=cv2.INTER_AREA)


def show_opening_explorer() -> None:
    board = chess.Board()
    book_path = _configured_book()
    message = ""
    buttons: list[Button] = []
    queue: list[str] = []

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, 1280, 780)

    def mouse(event: int, x: int, y: int, _flags: int, _data: object) -> None:
        if event == cv2.EVENT_LBUTTONUP:
            action = pregame_ui.clicked_action(buttons, x, y)
            if action:
                queue.append(action)

    cv2.setMouseCallback(WINDOW_NAME, mouse)

    while True:
        entries, book_error = _book_entries(book_path, board)
        if book_error:
            message = book_error

        view = np.zeros((780, 1280, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        base._put(view, "Opening Explorer", (38, 52), (100, 220, 255), 0.95, 2)
        base._put(
            view,
            "Explore moves from a local Polyglot .bin opening book.",
            (40, 83),
            (165, 175, 190),
            0.50,
        )

        position_image = _render_position(board)
        view[120:680, 35:595] = position_image

        book_name = book_path.name if book_path else "No opening book selected"
        base._put(view, "POLYGLOT BOOK", (640, 122), (165, 175, 190), 0.46)
        base._put(view, book_name[:48], (640, 154), (120, 255, 170), 0.58)
        base._put(
            view,
            f"Position after {board.ply()} half-moves",
            (640, 190),
            (210, 215, 225),
            0.46,
        )

        choose = Button("choose_book", "CHOOSE BOOK...", 1005, 116, 225, 48)
        reset = Button("reset", "RESET", 640, 212, 150, 44, enabled=bool(board.move_stack))
        undo = Button("undo", "BACK MOVE", 805, 212, 160, 44, enabled=bool(board.move_stack))
        menu = Button("back", "MAIN MENU", 980, 212, 250, 44)
        buttons = [choose, reset, undo, menu]
        for button in buttons:
            pregame_ui.draw_button(view, button)

        base._put(view, "BOOK MOVES", (640, 302), (100, 220, 255), 0.54)
        if book_path is None:
            base._put(
                view,
                "Choose a Polyglot .bin file to view opening moves.",
                (640, 340),
                (185, 195, 210),
                0.46,
            )
        elif not entries and not book_error:
            base._put(
                view,
                "This position has no moves in the selected book.",
                (640, 340),
                (185, 195, 210),
                0.46,
            )
        else:
            total_weight = sum(entry.weight for entry in entries) or 1
            for index, entry in enumerate(entries[:MAX_VISIBLE_MOVES]):
                try:
                    san = board.san(entry.move)
                except (ValueError, AssertionError):
                    san = entry.move.uci()
                percent = 100.0 * entry.weight / total_weight
                y = 324 + index * 39
                move_button = Button(
                    f"play_{index}",
                    f"{san:<10}  {entry.weight:>6}  {percent:5.1f}%",
                    640,
                    y,
                    590,
                    34,
                    active=index == 0,
                )
                buttons.append(move_button)
                pregame_ui.draw_button(view, move_button)

        fen = board.fen()
        base._put(view, "FEN", (40, 725), (100, 220, 255), 0.42)
        base._put(view, fen[:88], (85, 725), (185, 195, 210), 0.36)
        if message:
            base._put(view, message[:82], (640, 745), (120, 220, 255), 0.40)

        cv2.imshow(WINDOW_NAME, view)
        key = cv2.waitKey(25) & 0xFF
        action = queue.pop(0) if queue else None

        if action == "choose_book":
            selected, error = _choose_book_file(book_path)
            cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
            cv2.setMouseCallback(WINDOW_NAME, mouse)
            if error:
                message = error
            elif selected is not None:
                book_path = selected
                _save_book(selected)
                board.reset()
                message = f"Loaded {selected.name}"
        elif action == "reset" or key in (ord("r"), ord("R")):
            board.reset()
            message = ""
        elif action == "undo" or key in (8, 127):
            if board.move_stack:
                board.pop()
            message = ""
        elif action is not None and action.startswith("play_"):
            try:
                index = int(action.removeprefix("play_"))
                entry = entries[index]
                if entry.move in board.legal_moves:
                    board.push(entry.move)
                    message = ""
            except (ValueError, IndexError):
                pass
        elif action == "back" or key == 27:
            cv2.destroyWindow(WINDOW_NAME)
            cv2.waitKey(1)
            return

        try:
            if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                return
        except cv2.error:
            return
