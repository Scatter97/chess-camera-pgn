from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import chess
import chess.syzygy
import cv2
import numpy as np

from chess_camera_app.core import app
from chess_camera_app.core import app_navigation as navigation
from chess_camera_app.content import content_library
from chess_camera_app.content import content_manager_ui
from chess_camera_app.ui import pregame_ui
from chess_camera_app.ui import ui_support as ui
from chess_camera_app.ui.pregame_ui import Button


WINDOW_NAME = "Chess Camera - Endgame Explorer"
MAX_TABLEBASE_PIECES = 7
MAX_VISIBLE_MOVES = 9
TABLEBASE_EXTENSIONS = ("*.rtbw", "*.rtbz")
LAST_ENDGAME_FEN_KEY = "last_endgame_explorer_fen"
DEFAULT_ENDGAME_FEN = "7k/8/8/8/8/8/4K3/5Q2 w - - 0 1"
EDITOR_SIZE = 448
EDITOR_ORIGIN = (28, 108)
EDITOR_SQUARE = EDITOR_SIZE // 8
EDITOR_TRAY = ("P", "N", "B", "R", "Q", "K")


@dataclass(frozen=True)
class TablebaseMove:
    move: chess.Move
    wdl: int
    dtz: int


@dataclass(frozen=True)
class TablebaseProbe:
    wdl: int
    dtz: int
    moves: tuple[TablebaseMove, ...]


def _configured_tablebase_directory() -> tuple[Path | None, str]:
    return content_library.active_tablebase_directory(app.CONFIG_PATH)


def _save_tablebase_directory(directory: Path) -> None:
    content_library.activate_custom_tablebase(app.CONFIG_PATH, directory)


def _contains_tablebase_files(directory: Path) -> bool:
    return all(any(directory.glob(pattern)) for pattern in TABLEBASE_EXTENSIONS)


def _choose_tablebase_directory(current: Path | None) -> tuple[Path | None, str | None]:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        return None, "The system folder picker is unavailable. Install python3-tk."

    root: object | None = None
    try:
        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except tk.TclError:
            pass
        selected = filedialog.askdirectory(
            parent=root,
            title="Choose a Syzygy tablebase folder",
            initialdir=str(current or Path.cwd()),
        )
    except tk.TclError as error:
        return None, f"Could not open the folder picker: {error}"
    finally:
        if root is not None:
            try:
                root.destroy()  # type: ignore[attr-defined]
            except tk.TclError:
                pass

    if not selected:
        return None, None
    directory = Path(selected)
    if not directory.is_dir():
        return None, "The selected tablebase folder could not be found."
    if not _contains_tablebase_files(directory):
        return None, "That folder needs both Syzygy .rtbw and .rtbz files."
    return directory, None


def _position_is_covered_candidate(board: chess.Board) -> tuple[bool, str | None]:
    if len(board.piece_map()) > MAX_TABLEBASE_PIECES:
        return False, f"Syzygy supports positions with up to {MAX_TABLEBASE_PIECES} pieces."
    if board.castling_rights:
        return False, "Syzygy tablebases do not cover positions with castling rights."
    if not board.is_valid():
        return False, "Load a valid legal chess position before probing the tablebase."
    return True, None


def probe_position(tablebase: object, board: chess.Board) -> TablebaseProbe:
    """Probe one position using only supported python-chess Syzygy APIs."""
    wdl = int(tablebase.probe_wdl(board))  # type: ignore[attr-defined]
    dtz = int(tablebase.probe_dtz(board))  # type: ignore[attr-defined]
    moves: list[TablebaseMove] = []
    for move in board.legal_moves:
        child = board.copy(stack=False)
        child.push(move)
        # After a move it is the opponent's turn, so invert WDL/DTZ back to
        # the current player's perspective.
        moves.append(TablebaseMove(
            move,
            -int(tablebase.probe_wdl(child)),  # type: ignore[attr-defined]
            -int(tablebase.probe_dtz(child)),  # type: ignore[attr-defined]
        ))
    moves.sort(key=lambda move: (-move.wdl, abs(move.dtz), move.move.uci()))
    return TablebaseProbe(wdl, dtz, tuple(moves))


def _probe_directory(
    directory: Path | None,
    board: chess.Board,
) -> tuple[TablebaseProbe | None, str | None]:
    if directory is None:
        return None, "Choose a custom folder or download tablebases in Data Manager."
    covered, message = _position_is_covered_candidate(board)
    if not covered:
        return None, message
    try:
        with chess.syzygy.open_tablebase(str(directory)) as tablebase:
            return probe_position(tablebase, board), None
    except chess.syzygy.MissingTableError:
        return None, "The active folder does not contain the Syzygy files for this position."
    except (OSError, ValueError) as error:
        return None, f"Could not read the active tablebase: {error}"


def _wdl_label(wdl: int) -> str:
    labels = {
        2: "Win",
        1: "Cursed win",
        0: "Draw",
        -1: "Blessed loss",
        -2: "Loss",
    }
    return labels.get(wdl, "Unknown")


def _result_label(board: chess.Board, wdl: int) -> str:
    """Return the actual game result, rather than only the side-to-move result."""
    if wdl == 0:
        return "DRAW"
    winner = board.turn if wdl > 0 else not board.turn
    return "WHITE WINS" if winner == chess.WHITE else "BLACK WINS"


def _render_position(board: chess.Board, size: int = 560) -> np.ndarray:
    rendered = app.render_virtual_board(board)
    return cv2.resize(rendered, (size, size), interpolation=cv2.INTER_AREA)


def _editor_square_at(x: int, y: int) -> chess.Square | None:
    left, top = EDITOR_ORIGIN
    if not (left <= x < left + EDITOR_SIZE and top <= y < top + EDITOR_SIZE):
        return None
    file_index = (x - left) // EDITOR_SQUARE
    rank_index = 7 - ((y - top) // EDITOR_SQUARE)
    return chess.square(file_index, rank_index)


def _editor_tray_piece(x: int, y: int) -> chess.Piece | None:
    # Black tray is at the top; White tray is at the bottom.
    if 28 <= x < 508 and 58 <= y < 96:
        colour = chess.BLACK
        index = (x - 28) // 80
    elif 28 <= x < 508 and 570 <= y < 608:
        colour = chess.WHITE
        index = (x - 28) // 80
    else:
        return None
    if not 0 <= index < len(EDITOR_TRAY):
        return None
    return chess.Piece(chess.PIECE_SYMBOLS.index(EDITOR_TRAY[index].lower()), colour)


def _apply_editor_drag(
    board: chess.Board,
    source_piece: chess.Piece | None,
    source_square: chess.Square | None,
    destination: chess.Square | None,
) -> None:
    """Apply one tray/board drag without creating a chess move history."""
    if source_piece is None:
        return
    if source_square is not None:
        board.remove_piece_at(source_square)
    if destination is not None:
        board.set_piece_at(destination, source_piece)
    board.clear_stack()
    board.castling_rights = chess.BB_EMPTY
    board.ep_square = None


def _draw_editor_tray(view: np.ndarray, colour: chess.Color, y: int) -> None:
    text_colour = (220, 225, 235) if colour == chess.WHITE else (100, 110, 125)
    label = "BLACK PIECES — drag onto the board" if colour == chess.BLACK else "WHITE PIECES — drag onto the board"
    ui._put(view, label, (28, y - 8), text_colour, 0.42)
    for index, symbol in enumerate(EDITOR_TRAY):
        left = 28 + index * 80
        cv2.rectangle(view, (left, y), (left + 70, y + 32), (90, 100, 115), 2)
        ui._put(view, symbol, (left + 26, y + 25), text_colour, 0.65, 2)


def show_position_editor(current: chess.Board) -> chess.Board | None:
    """Edit an endgame with drag-and-drop trays above and below the board."""
    board = current.copy(stack=False)
    window = "Chess Camera - Endgame Position Setup"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 700, 650)
    drag_piece: chess.Piece | None = None
    drag_square: chess.Square | None = None
    buttons = [
        Button("clear", "CLEAR", 520, 132, 145, 42),
        Button("turn", "SIDE TO MOVE", 520, 184, 145, 42),
        Button("cancel", "CANCEL", 520, 500, 145, 42),
        Button("use", "USE POSITION", 520, 552, 145, 42, active=True),
    ]
    queue: list[str] = []

    def mouse(event: int, x: int, y: int, _flags: int, _data: object) -> None:
        nonlocal drag_piece, drag_square
        if event == cv2.EVENT_LBUTTONDOWN:
            drag_piece = _editor_tray_piece(x, y)
            drag_square = None
            if drag_piece is None:
                drag_square = _editor_square_at(x, y)
                drag_piece = board.piece_at(drag_square) if drag_square is not None else None
            return
        if event != cv2.EVENT_LBUTTONUP:
            return
        action = pregame_ui.clicked_action(buttons, x, y)
        if action:
            queue.append(action)
            drag_piece = None
            drag_square = None
            return
        _apply_editor_drag(board, drag_piece, drag_square, _editor_square_at(x, y))
        drag_piece = None
        drag_square = None

    cv2.setMouseCallback(window, mouse)
    message = "Drag a tray piece onto a square. Drag a board piece away to remove it."
    while True:
        view = np.zeros((650, 700, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        ui._put(view, "Set up an endgame position", (28, 34), (100, 220, 255), 0.72, 2)
        _draw_editor_tray(view, chess.BLACK, 64)
        view[EDITOR_ORIGIN[1]:EDITOR_ORIGIN[1] + EDITOR_SIZE, EDITOR_ORIGIN[0]:EDITOR_ORIGIN[0] + EDITOR_SIZE] = _render_position(board, EDITOR_SIZE)
        _draw_editor_tray(view, chess.WHITE, 576)
        for button in buttons:
            pregame_ui.draw_button(view, button)
        ui._put(view, "White to move" if board.turn else "Black to move", (520, 258), (120, 255, 170), 0.48)
        ui._put(view, message[:46], (520, 300), (200, 205, 215), 0.38)
        cv2.imshow(window, view)
        action = queue.pop(0) if queue else None
        key = cv2.waitKey(20) & 0xFF
        if action == "clear":
            board.clear()
            board.turn = chess.WHITE
            message = "Board cleared. Add both kings before using the position."
        elif action == "turn":
            board.turn = not board.turn
        elif action == "use":
            if board.is_valid() and len(board.pieces(chess.KING, chess.WHITE)) == 1 and len(board.pieces(chess.KING, chess.BLACK)) == 1:
                cv2.destroyWindow(window)
                return board
            message = "Use one white king, one black king, and a legal position."
        elif action == "cancel" or key == 27:
            cv2.destroyWindow(window)
            return None


def _fen_board(value: str) -> tuple[chess.Board | None, str | None]:
    try:
        board = chess.Board(value.strip())
    except ValueError as error:
        return None, f"That FEN is not valid: {error}"
    if not board.is_valid():
        return None, "That FEN does not describe a legal chess position."
    return board, None


def _load_starting_board(initial_fen: str | None = None) -> tuple[chess.Board, str]:
    """Use an incoming or remembered endgame FEN instead of the full starting board."""
    candidates: list[tuple[str, str]] = []
    if initial_fen:
        candidates.append((initial_fen, "Loaded the selected endgame position."))

    data = content_library._load_config(app.CONFIG_PATH)
    saved_fen = data.get(LAST_ENDGAME_FEN_KEY)
    if isinstance(saved_fen, str) and saved_fen.strip():
        candidates.append((saved_fen, "Restored the last Endgame Explorer position."))

    candidates.append((
        DEFAULT_ENDGAME_FEN,
        "Loaded a sample tablebase endgame. Use LOAD FEN for another position.",
    ))

    for fen, message in candidates:
        board, error = _fen_board(fen)
        if board is not None:
            return board, message

    return chess.Board(DEFAULT_ENDGAME_FEN), "Loaded a sample tablebase endgame."


def _save_last_fen(board: chess.Board) -> None:
    data = content_library._load_config(app.CONFIG_PATH)
    data[LAST_ENDGAME_FEN_KEY] = board.fen()
    content_library._save_config(app.CONFIG_PATH, data)


def _move_buttons(
    board: chess.Board,
    moves: Iterable[TablebaseMove],
) -> list[Button]:
    buttons: list[Button] = []
    for index, item in enumerate(moves):
        if index >= MAX_VISIBLE_MOVES:
            break
        try:
            san = board.san(item.move)
        except ValueError:
            continue
        label = f"{san}  {_wdl_label(item.wdl)}  DTZ {item.dtz:+d}"
        buttons.append(
            Button(f"move:{item.move.uci()}", label, 640, 390 + index * 36, 575, 30)
        )
    return buttons


def show_endgame_explorer(initial_fen: str | None = None) -> None:
    board, message = _load_starting_board(initial_fen)
    tablebase_directory, source_mode = _configured_tablebase_directory()
    last_fen = ""
    probe: TablebaseProbe | None = None
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
        current_fen = board.fen()
        if current_fen != last_fen:
            _save_last_fen(board)
            probe, probe_message = _probe_directory(tablebase_directory, board)
            if probe_message is not None:
                message = probe_message
            elif probe is not None:
                message = "Exact local tablebase result for the side to move."
            last_fen = current_fen

        downloaded_directory = content_library.downloaded_tablebase_directory(
            app.CONFIG_PATH
        )
        view = np.zeros((780, 1280, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        ui._put(view, "Endgame Explorer", (38, 52), (100, 220, 255), 0.95, 2)
        ui._put(
            view,
            "Explore downloaded or custom Syzygy tablebases without sending positions online.",
            (40, 83),
            (165, 175, 190),
            0.48,
        )
        view[120:680, 35:595] = _render_position(board)

        if tablebase_directory is None:
            folder_name = "No tablebase active"
        elif source_mode == "downloaded":
            folder_name = f"Downloaded: {tablebase_directory.name}"
        else:
            folder_name = f"Custom: {tablebase_directory.name}"
        ui._put(view, "ACTIVE TABLEBASE", (640, 122), (165, 175, 190), 0.46)
        ui._put(view, folder_name[:50], (640, 154), (120, 255, 170), 0.58)
        ui._put(
            view,
            f"{len(board.piece_map())} pieces | {'White' if board.turn else 'Black'} to move",
            (640, 190),
            (210, 215, 225),
            0.46,
        )

        choose = Button("choose_folder", "CHOOSE CUSTOM FOLDER...", 970, 112, 260, 44)
        downloaded = Button(
            "use_downloaded",
            "USE DOWNLOADED",
            970,
            164,
            260,
            44,
            enabled=downloaded_directory is not None and source_mode != "downloaded",
        )
        setup = Button("setup", "SET UP BOARD", 640, 218, 160, 44)
        fen = Button("load_fen", "FEN INPUT...", 810, 218, 140, 44)
        copy_fen = Button("copy_fen", "COPY FEN", 960, 218, 120, 44)
        reset = Button("reset", "RESET", 1090, 218, 100, 44, enabled=bool(board.move_stack))
        undo = Button("undo", "BACK MOVE", 640, 270, 160, 40, enabled=bool(board.move_stack))
        manage = Button("manage_data", "DATA", 810, 270, 140, 40)
        menu = Button("back", "MAIN MENU", 985, 700, 245, 44)
        buttons = [choose, downloaded, setup, fen, copy_fen, reset, undo, manage, menu]
        if probe is not None:
            buttons.extend(_move_buttons(board, probe.moves))
        for button in buttons:
            pregame_ui.draw_button(view, button)

        if probe is not None:
            ui._put(view, "TABLEBASE RESULT", (640, 304), (100, 220, 255), 0.54)
            ui._put(view, _result_label(board, probe.wdl), (640, 340), (120, 255, 170), 0.72, 2)
            ui._put(view, f"DTZ {probe.dtz:+d}", (810, 340), (210, 215, 225), 0.54)
            ui._put(view, "ROOT MOVES", (640, 376), (165, 175, 190), 0.44)
        else:
            ui._put(view, "TABLEBASE STATUS", (640, 304), (100, 220, 255), 0.54)
            ui._put(view, message[:78], (640, 342), (210, 215, 225), 0.44)

        ui._put(view, "FEN", (40, 718), (165, 175, 190), 0.42)
        ui._put(view, board.fen()[:118], (40, 748), (210, 215, 225), 0.38)
        ui._put(view, message[:115], (640, 670), (185, 195, 210), 0.40)
        cv2.imshow(WINDOW_NAME, view)

        key = cv2.waitKey(25) & 0xFF
        action = queue.pop(0) if queue else None
        if action == "choose_folder":
            selected, error = _choose_tablebase_directory(tablebase_directory)
            cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
            cv2.setMouseCallback(WINDOW_NAME, mouse)
            if error:
                message = error
            elif selected is not None:
                tablebase_directory = selected
                source_mode = "custom"
                _save_tablebase_directory(selected)
                last_fen = ""
                message = f"Selected custom tablebase folder: {selected.name}."
        elif action == "use_downloaded":
            if content_library.activate_downloaded_tablebase(app.CONFIG_PATH):
                tablebase_directory, source_mode = _configured_tablebase_directory()
                last_fen = ""
                message = "Using downloaded 3/4/5-piece Syzygy tablebases."
            else:
                message = "The downloaded tablebase package could not be found."
        elif action == "manage_data":
            cv2.destroyWindow(WINDOW_NAME)
            content_manager_ui.show_content_manager(app, navigation)
            cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(WINDOW_NAME, 1280, 780)
            cv2.setMouseCallback(WINDOW_NAME, mouse)
            tablebase_directory, source_mode = _configured_tablebase_directory()
            last_fen = ""
            message = "Tablebase-library status refreshed."
        elif action == "setup":
            edited = show_position_editor(board)
            if edited is not None:
                board = edited
                last_fen = ""
                message = "Using the position from the board setup editor."
        elif action == "load_fen":
            value = app.prompt_for_text(
                "Endgame position",
                "Paste a FEN with Ctrl+V, or type one. CLEAR empties the input.",
                board.fen(),
            )
            if value is not None:
                loaded, error = _fen_board(value)
                if error:
                    message = error
                elif loaded is not None:
                    board = loaded
                    last_fen = ""
        elif action == "copy_fen":
            message = (
                "FEN copied to the clipboard."
                if app.copy_text_to_clipboard(board.fen())
                else "Could not access the system clipboard."
            )
        elif action == "reset":
            board = chess.Board(DEFAULT_ENDGAME_FEN)
            last_fen = ""
        elif action == "undo":
            if board.move_stack:
                board.pop()
                last_fen = ""
        elif action and action.startswith("move:"):
            move = chess.Move.from_uci(action.removeprefix("move:"))
            if move in board.legal_moves:
                board.push(move)
                last_fen = ""
        elif action == "back" or key == 27:
            cv2.destroyWindow(WINDOW_NAME)
            return

        try:
            if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                return
        except cv2.error:
            return
