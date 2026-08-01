from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

import chess
import chess.polyglot
import cv2
import numpy as np

from chess_camera_app.core import app
from chess_camera_app.core import app_navigation as navigation
from chess_camera_app.content import content_library
from chess_camera_app.content import content_manager_ui
from chess_camera_app.ui import pregame_ui
from chess_camera_app.ui import ui_support as ui
from chess_camera_app.analysis.opening_book_builder import build_polyglot_book_from_tsv
from chess_camera_app.ui.pregame_ui import Button


WINDOW_NAME = "Chess Camera - Opening Explorer"
BOOK_DIRECTORY = Path("books")
DEFAULT_BOOK_SOURCE = BOOK_DIRECTORY / "default_openings.tsv"
DEFAULT_BOOK_PATH = BOOK_DIRECTORY / "chess_camera_default.bin"
MAX_VISIBLE_MOVES = 9


@lru_cache(maxsize=4)
def _opening_name_lines(source_path: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    path = Path(source_path)
    if not path.is_file():
        return ()
    with path.open("r", encoding="utf-8", newline="") as source:
        rows = csv.DictReader(source, delimiter="\t")
        return tuple(
            (str(row.get("name") or "").strip(), tuple(str(row.get("uci") or "").split()))
            for row in rows
            if str(row.get("name") or "").strip() and str(row.get("uci") or "").strip()
        )


def opening_name(board: chess.Board, source_path: Path = DEFAULT_BOOK_SOURCE) -> str | None:
    """Return the longest matching named line for the current move history."""
    played = tuple(move.uci() for move in board.move_stack)
    best: str | None = None
    best_length = -1
    for name, line in _opening_name_lines(str(source_path)):
        if len(line) <= len(played) and played[:len(line)] == line and len(line) > best_length:
            best, best_length = name, len(line)
    return best


def _ensure_builtin_book() -> tuple[Path | None, str | None]:
    """Create or refresh the bundled CC0-derived Polyglot book."""
    try:
        needs_build = (
            not DEFAULT_BOOK_PATH.is_file()
            or (
                DEFAULT_BOOK_SOURCE.is_file()
                and DEFAULT_BOOK_SOURCE.stat().st_mtime
                > DEFAULT_BOOK_PATH.stat().st_mtime
            )
        )
        if needs_build:
            if not DEFAULT_BOOK_SOURCE.is_file():
                return None, f"Built-in source is missing: {DEFAULT_BOOK_SOURCE}"
            build_polyglot_book_from_tsv(DEFAULT_BOOK_SOURCE, DEFAULT_BOOK_PATH)

        with chess.polyglot.open_reader(str(DEFAULT_BOOK_PATH)) as reader:
            list(reader.find_all(chess.Board()))
    except (OSError, ValueError, IndexError) as error:
        return None, f"Could not prepare the built-in opening book: {error}"

    return DEFAULT_BOOK_PATH, None


def _save_book_choice(mode: str, path: Path | None = None) -> None:
    data = navigation._config()
    data[content_library.OPENING_BOOK_MODE_KEY] = mode
    if path is not None:
        data[content_library.OPENING_BOOK_PATH_KEY] = str(path)
    elif mode == "builtin":
        data.pop(content_library.OPENING_BOOK_PATH_KEY, None)
    navigation._save_config(data)


def _configured_book() -> tuple[Path | None, str, str | None]:
    """Return the active book, source mode, and an optional status message."""
    builtin_path, builtin_error = _ensure_builtin_book()
    downloaded_path = content_library.downloaded_opening_book(app.CONFIG_PATH)
    data = navigation._config()
    configured = data.get(content_library.OPENING_BOOK_PATH_KEY)
    custom_path = Path(configured) if isinstance(configured, str) else None
    mode = data.get(content_library.OPENING_BOOK_MODE_KEY)

    if mode == "downloaded":
        if downloaded_path is not None:
            return downloaded_path, "downloaded", builtin_error
        fallback = "Downloaded opening database is missing; using the built-in book."
        return builtin_path, "builtin", builtin_error or fallback

    if mode == "custom":
        if custom_path is not None and custom_path.is_file():
            return custom_path, "custom", builtin_error
        fallback = "Custom book is missing; using the built-in book."
        return builtin_path, "builtin", builtin_error or fallback

    if mode not in {"builtin", "custom", "downloaded"}:
        if custom_path is not None and custom_path.is_file():
            return custom_path, "custom", builtin_error

    return builtin_path, "builtin", builtin_error


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

    try:
        with chess.polyglot.open_reader(str(path)) as reader:
            list(reader.find_all(chess.Board()))
    except (OSError, ValueError, IndexError) as error:
        return None, f"That file is not a readable Polyglot book: {error}"

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
    rendered = app.render_virtual_board(board)
    return cv2.resize(rendered, (size, size), interpolation=cv2.INTER_AREA)


def show_opening_explorer() -> None:
    board = chess.Board()
    book_path, source_mode, startup_message = _configured_book()
    message = startup_message or ""
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

        downloaded_path = content_library.downloaded_opening_book(app.CONFIG_PATH)
        view = np.zeros((780, 1280, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        ui._put(view, "Opening Explorer", (38, 52), (100, 220, 255), 0.95, 2)
        ui._put(
            view,
            "Explore built-in, downloaded, or custom Polyglot opening books.",
            (40, 83),
            (165, 175, 190),
            0.50,
        )

        position_image = _render_position(board)
        view[120:680, 35:595] = position_image

        if book_path is None:
            book_name = "No readable opening book"
        elif source_mode == "builtin":
            book_name = f"Built-in: {book_path.name}"
        elif source_mode == "downloaded":
            book_name = f"Downloaded: {book_path.name}"
        else:
            book_name = f"Custom: {book_path.name}"

        ui._put(view, "ACTIVE BOOK", (640, 122), (165, 175, 190), 0.46)
        ui._put(view, book_name[:48], (640, 154), (120, 255, 170), 0.58)
        ui._put(
            view,
            f"Position after {board.ply()} half-moves",
            (640, 190),
            (210, 215, 225),
            0.46,
        )
        name = opening_name(board)
        ui._put(view, "OPENING", (640, 212), (165, 175, 190), 0.42)
        ui._put(view, (name or "Unnamed position")[:52], (730, 212), (255, 220, 120), 0.46)

        choose = Button("choose_book", "CHOOSE CUSTOM BOOK...", 985, 112, 245, 44)
        builtin = Button(
            "use_builtin",
            "USE BUILT-IN",
            985,
            164,
            245,
            44,
            enabled=source_mode != "builtin",
        )
        downloaded = Button(
            "use_downloaded",
            "USE DOWNLOADED",
            640,
            218,
            180,
            44,
            enabled=downloaded_path is not None and source_mode != "downloaded",
        )
        manage = Button("manage_data", "DATA MANAGER", 835, 218, 180, 44)
        menu = Button("back", "MAIN MENU", 1030, 218, 200, 44)
        reset = Button(
            "reset",
            "RESET",
            640,
            270,
            150,
            42,
            enabled=bool(board.move_stack),
        )
        undo = Button(
            "undo",
            "BACK MOVE",
            805,
            270,
            160,
            42,
            enabled=bool(board.move_stack),
        )
        buttons = [choose, builtin, downloaded, manage, menu, reset, undo]
        for button in buttons:
            pregame_ui.draw_button(view, button)

        ui._put(view, "BOOK MOVES", (640, 338), (100, 220, 255), 0.54)
        if book_path is None:
            ui._put(
                view,
                "No readable book is active. Open Data Manager or choose a .bin file.",
                (640, 374),
                (185, 195, 210),
                0.43,
            )
        elif not entries and not book_error:
            ui._put(
                view,
                "This position has no moves in the active book.",
                (640, 374),
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
                y = 354 + index * 39
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
        ui._put(view, "FEN", (40, 725), (100, 220, 255), 0.42)
        ui._put(view, fen[:88], (85, 725), (185, 195, 210), 0.36)
        if message:
            ui._put(view, message[:82], (640, 745), (120, 220, 255), 0.40)

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
                source_mode = "custom"
                _save_book_choice("custom", selected)
                board.reset()
                message = f"Loaded custom book: {selected.name}"
        elif action == "use_builtin":
            builtin_path, error = _ensure_builtin_book()
            if error:
                message = error
            elif builtin_path is not None:
                book_path = builtin_path
                source_mode = "builtin"
                _save_book_choice("builtin")
                board.reset()
                message = "Using the built-in CC0-derived opening book."
        elif action == "use_downloaded":
            if content_library.activate_downloaded_opening(app.CONFIG_PATH):
                book_path, source_mode, status = _configured_book()
                board.reset()
                message = status or "Using the downloaded expanded opening database."
            else:
                message = "The downloaded opening database could not be found."
        elif action == "manage_data":
            cv2.destroyWindow(WINDOW_NAME)
            content_manager_ui.show_content_manager(app, navigation)
            cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(WINDOW_NAME, 1280, 780)
            cv2.setMouseCallback(WINDOW_NAME, mouse)
            book_path, source_mode, status = _configured_book()
            message = status or "Opening-library status refreshed."
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
