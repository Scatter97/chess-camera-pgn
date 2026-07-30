from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import chess
import cv2
import numpy as np

from board_profiles import (
    GUIDED_TRAINING_LINE,
    BoardProfile,
    BoardProfileStore,
)
from builtin_clock import BuiltInChessClock, ClockSettings, ManualClockController
from clock_reader import (
    BackgroundClockReader,
    BothClocks,
    detect_active_clock_side,
    format_pgn_clock,
)
from chess_tracker import (
    BOARD_MARGIN_PIXELS,
    BOARD_PIXELS,
    RankedMove,
    WARP_PIXELS,
    analyze_frame_consensus,
    board_looks_restored,
    confidence_for,
    legal_move_fit,
    move_changed_squares,
    move_with_promotion,
    orient_board_image,
    rank_legal_moves,
    square_change_scores,
    warp_board,
    write_pgn,
)
from game_rules import (
    GameOutcome,
    automatic_outcome,
    claimable_draw_reasons,
    timeout_outcome,
)
from game_analysis import (
    DEFAULT_ANALYSIS_SECONDS,
    AnalysisUnavailable,
    GameReview,
    analyze_game,
    find_stockfish,
    probe_uci_engine,
    save_analysis_report,
)
from pregame_ui import (
    Button,
    DEFAULT_PINNED_TIME_CONTROLS,
    GameSetup,
    TIME_CONTROL_PRESETS,
    apply_time_slider_value,
    apply_setup_action,
    clicked_action,
    draw_button,
    normalize_pinned_time_controls,
    render_setup_screen,
    slider_value_from_x,
    toggle_pinned_time_control,
    update_text_field,
)


CONFIG_PATH = Path("camera_config.json")
PROFILE_DIRECTORY = Path("board_profiles")
OUTPUT_PATH = Path("games/latest_game.pgn")
STABLE_SECONDS = 1.15
FAST_STABLE_SECONDS = 0.35
BULLET_STABLE_SECONDS = 0.22
BULLET_SWITCH_SETTLE_SECONDS = 0.12
FAST_ACCEPT_COOLDOWN = 0.35
BULLET_ACCEPT_COOLDOWN = 0.18
AUTO_CONFIDENCE = 0.73
MIN_CHANGE = 7.0
LEGAL_FIT_THRESHOLD = 0.66
CLOCK_PREVIEW_INTERVAL = 1.5
VIRTUAL_VIEW_WIDTH = 620
VIRTUAL_VIEW_HEIGHT = 620
INFO_PANEL_WIDTH = 480
CAMERA_PANEL_WIDTH = 300
CAMERA_PREVIEW_TOP = 38
CAMERA_PREVIEW_SIZE = 240
GAME_BUTTON_Y_OFFSET = 30
ACCURACY_FRAME_COUNT = 3
ACCURACY_SAMPLE_INTERVAL = 0.06


def put_text(
    image: np.ndarray,
    text: str,
    position: tuple[int, int],
    color: tuple[int, int, int] = (245, 245, 245),
    scale: float = 0.62,
) -> None:
    cv2.putText(
        image,
        text,
        position,
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        (10, 10, 10),
        4,
        cv2.LINE_AA,
    )
    cv2.putText(
        image,
        text,
        position,
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        color,
        1,
        cv2.LINE_AA,
    )


def select_camera_backend(platform_name: str | None = None) -> int:
    """Choose the native camera backend for Windows, Ubuntu/Linux, or macOS."""
    name = platform_name or sys.platform
    if name.startswith("linux"):
        return cv2.CAP_V4L2
    if name.startswith("win"):
        return cv2.CAP_DSHOW
    if name == "darwin":
        return cv2.CAP_AVFOUNDATION
    return cv2.CAP_ANY


def open_camera(index: int) -> cv2.VideoCapture:
    backend = select_camera_backend()
    capture = cv2.VideoCapture(index, backend)
    if not capture.isOpened() and backend != cv2.CAP_ANY:
        capture.release()
        capture = cv2.VideoCapture(index, cv2.CAP_ANY)
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    if not capture.isOpened():
        raise RuntimeError(
            f"Could not open camera {index}. Close other camera apps or try --camera 1."
        )
    return capture


def calibrate_quadrilateral(
    capture: cv2.VideoCapture,
    window: str,
    labels: list[str],
    help_text: str,
) -> list[list[float]]:
    points: list[tuple[int, int]] = []

    def click(event: int, x: int, y: int, _flags: int, _data: object) -> None:
        if event == cv2.EVENT_LBUTTONDOWN and len(points) < 4:
            points.append((x, y))

    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(window, click)

    while True:
        ok, frame = capture.read()
        if not ok:
            continue
        view = frame.copy()

        if len(points) < 4:
            instruction = f"Click {labels[len(points)]} ({len(points) + 1}/4)"
        else:
            instruction = "Press ENTER to save, R to redo, or Q to quit"

        put_text(view, instruction, (25, 40), (80, 255, 255), 0.8)
        put_text(
            view,
            help_text,
            (25, 75),
            scale=0.6,
        )

        for index, point in enumerate(points):
            cv2.circle(view, point, 9, (40, 240, 40), -1)
            put_text(view, labels[index], (point[0] + 12, point[1] - 8), scale=0.55)
        if len(points) > 1:
            cv2.polylines(
                view, [np.asarray(points, dtype=np.int32)], False, (40, 240, 40), 3
            )
        if len(points) == 4:
            cv2.polylines(
                view, [np.asarray(points, dtype=np.int32)], True, (40, 240, 40), 3
            )

        cv2.imshow(window, view)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
            raise KeyboardInterrupt
        if key == ord("r"):
            points.clear()
        if key in (10, 13) and len(points) == 4:
            cv2.destroyWindow(window)
            return [[float(x), float(y)] for x, y in points]


def calibrate_board(capture: cv2.VideoCapture) -> list[list[float]]:
    return calibrate_quadrilateral(
        capture,
        "Calibration 1/2 - click board corners",
        ["image top-left", "image top-right", "image bottom-right", "image bottom-left"],
        "Use the corners as seen on screen. Keep some space around every board edge.",
    )


def calibrate_phone(capture: cv2.VideoCapture) -> list[list[float]]:
    return calibrate_quadrilateral(
        capture,
        "Calibration 2/2 - click phone screen corners",
        ["screen top-left", "screen top-right", "screen bottom-right", "screen bottom-left"],
        "Click the lit screen edges as seen by the camera, not the phone case.",
    )


def save_config(
    board_corners: list[list[float]],
    phone_corners: list[list[float]],
    bottom_clock_is_white: bool,
    white_camera_edge: str,
    active_profile: str = "Default board",
    engine_path: Path | None = None,
    pinned_time_controls: tuple[str, ...] = DEFAULT_PINNED_TIME_CONTROLS,
    player_name_usage: dict[str, int] | None = None,
    event_name_usage: dict[str, int] | None = None,
) -> None:
    CONFIG_PATH.write_text(
        json.dumps(
            {
                "board_corners": board_corners,
                "phone_corners": phone_corners,
                "bottom_clock_is_white": bottom_clock_is_white,
                "white_camera_edge": white_camera_edge,
                "active_profile": active_profile,
                "engine_path": str(engine_path) if engine_path else None,
                "pinned_time_controls": list(pinned_time_controls),
                "player_name_usage": player_name_usage or {},
                "event_name_usage": event_name_usage or {},
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def normalize_usage_counts(raw: object) -> dict[str, int]:
    """Load safe, non-empty local suggestion counters from configuration."""
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, int] = {}
    for value, count in raw.items():
        if not isinstance(value, str):
            continue
        cleaned = value.strip()
        try:
            numeric_count = int(count)
        except (TypeError, ValueError):
            continue
        if cleaned and numeric_count > 0:
            normalized[cleaned] = numeric_count
    return normalized


def most_used_values(counts: dict[str, int], limit: int = 3) -> tuple[str, ...]:
    return tuple(
        value
        for value, _count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0].casefold()),
        )[: max(0, limit)]
    )


def remember_used_value(counts: dict[str, int], value: str) -> None:
    cleaned = value.strip()
    if cleaned:
        counts[cleaned] = counts.get(cleaned, 0) + 1


def apply_setup_suggestion(
    setup: GameSetup,
    action: str,
    player_suggestions: tuple[str, ...],
    event_suggestions: tuple[str, ...],
) -> GameSetup:
    parts = action.split("_")
    if len(parts) != 3 or parts[0] != "suggest":
        return setup
    field = parts[1]
    suggestions = event_suggestions if field == "event" else player_suggestions
    try:
        value = suggestions[int(parts[2])]
    except (ValueError, IndexError):
        return setup
    attribute = {
        "white": "white_name",
        "black": "black_name",
        "event": "event_name",
    }.get(field)
    return replace(setup, **{attribute: value}) if attribute else setup


def prompt_for_text(title: str, label: str, current: str) -> str | None:
    """Show a small editable OpenCV text prompt."""
    window = title
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 680, 260)
    value = current
    buttons = [
        Button("save", "SAVE", 135, 180, 180, 52, active=True),
        Button("cancel", "Cancel", 365, 180, 180, 52),
    ]
    clicks: list[str] = []

    def on_mouse(
        event: int, x: int, y: int, _flags: int, _data: object
    ) -> None:
        if event == cv2.EVENT_LBUTTONUP:
            action = clicked_action(buttons, x, y)
            if action:
                clicks.append(action)

    cv2.setMouseCallback(window, on_mouse)
    while True:
        view = np.zeros((260, 680, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        put_text(view, title, (34, 48), (100, 220, 255), 0.82)
        put_text(view, label, (34, 88), (165, 175, 190), 0.50)
        cv2.rectangle(view, (34, 102), (646, 153), (46, 50, 58), -1)
        cv2.rectangle(view, (34, 102), (646, 153), (120, 255, 170), 2)
        put_text(view, value[-44:] or "Type a name", (48, 136), scale=0.59)
        for button in buttons:
            draw_button(view, button)
        cv2.imshow(window, view)
        key = cv2.waitKey(20) & 0xFF
        action = clicks.pop(0) if clicks else None
        if action == "save" or key in (10, 13):
            cv2.destroyWindow(window)
            return value.strip()
        if action == "cancel" or key == 27:
            cv2.destroyWindow(window)
            return None
        if key in (8, 127):
            value = value[:-1]
        elif 32 <= key <= 126 and len(value) < 40:
            value += chr(key)


def choose_uci_engine_file(
    current_path: Path | None = None,
) -> tuple[Path | None, str | None]:
    """Open the operating system file picker for a UCI engine executable."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        return None, (
            "The system file picker is unavailable. On Ubuntu, install "
            "python3-tk and restart the app."
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
            str(current_path.parent)
            if current_path is not None and current_path.exists()
            else str(Path.cwd())
        )
        selected = filedialog.askopenfilename(
            parent=root,
            title="Choose a trusted UCI chess-engine executable",
            initialdir=initial_directory,
            filetypes=[
                ("Chess engine executable", "*.exe")
                if sys.platform == "win32"
                else ("Executable files", "*"),
                ("All files", "*"),
            ],
        )
    except tk.TclError as error:
        return None, f"Could not open the system file picker: {error}"
    finally:
        if root is not None:
            try:
                root.destroy()  # type: ignore[attr-defined]
            except tk.TclError:
                pass

    if not selected:
        return None, None
    return Path(selected), None


def draw_grid(board_image: np.ndarray, highlighted: set[int]) -> np.ndarray:
    view = board_image.copy()
    cell = BOARD_PIXELS // 8
    overlay = view.copy()

    for square in highlighted:
        file_index = chess.square_file(square)
        rank_from_top = 7 - chess.square_rank(square)
        x0 = BOARD_MARGIN_PIXELS + file_index * cell
        y0 = BOARD_MARGIN_PIXELS + rank_from_top * cell
        cv2.rectangle(
            overlay, (x0, y0), (x0 + cell, y0 + cell), (0, 215, 255), -1
        )
    if highlighted:
        view = cv2.addWeighted(overlay, 0.26, view, 0.74, 0)

    for index in range(9):
        value = BOARD_MARGIN_PIXELS + index * cell
        cv2.line(
            view,
            (value, BOARD_MARGIN_PIXELS),
            (value, BOARD_MARGIN_PIXELS + BOARD_PIXELS),
            (255, 255, 255),
            1,
        )
        cv2.line(
            view,
            (BOARD_MARGIN_PIXELS, value),
            (BOARD_MARGIN_PIXELS + BOARD_PIXELS, value),
            (255, 255, 255),
            1,
        )
    return view


def render_grid_verification(board_image: np.ndarray) -> np.ndarray:
    """Draw labels on all 64 calibrated squares for a pregame visual check."""
    view = draw_grid(board_image, set())
    for rank_from_top in range(8):
        for file_index in range(8):
            square_name = chess.square_name(
                chess.square(file_index, 7 - rank_from_top)
            )
            x = BOARD_MARGIN_PIXELS + file_index * 100 + 7
            y = BOARD_MARGIN_PIXELS + rank_from_top * 100 + 23
            put_text(view, square_name, (x, y), (40, 245, 255), 0.45)
    put_text(
        view,
        "Grid follows board edges; tall edge pieces may extend into the outer margin.",
        (24, WARP_PIXELS - 18),
        (255, 255, 255),
        0.48,
    )
    return view


def render_camera_panel(
    board_view: np.ndarray,
    detection_mode_name: str,
    display_fps: float,
    stability_progress: float,
    fast_mode: bool,
) -> np.ndarray:
    """Render camera diagnostics above, rather than over, the board image."""
    panel = np.zeros((620, CAMERA_PANEL_WIDTH, 3), dtype=np.uint8)
    panel[:] = (25, 28, 34)
    preview = cv2.resize(
        board_view,
        (CAMERA_PREVIEW_SIZE, CAMERA_PREVIEW_SIZE),
    )
    preview_bottom = CAMERA_PREVIEW_TOP + CAMERA_PREVIEW_SIZE
    panel[CAMERA_PREVIEW_TOP:preview_bottom, 30:270] = preview
    cv2.rectangle(
        panel,
        (30, CAMERA_PREVIEW_TOP),
        (269, preview_bottom - 1),
        (115, 125, 142),
        2,
    )
    put_text(
        panel,
        f"{detection_mode_name} | {display_fps:.1f} FPS",
        (38, 17),
        (120, 255, 170) if fast_mode else (120, 220, 255),
        0.39,
    )
    cv2.rectangle(panel, (38, 25), (262, 33), (20, 20, 20), -1)
    progress_width = int(224 * min(1.0, max(0.0, stability_progress)))
    if progress_width:
        cv2.rectangle(
            panel,
            (38, 25),
            (38 + progress_width, 33),
            (80, 220, 120),
            -1,
        )
    return panel


def show_grid_verification(
    capture: cv2.VideoCapture,
    board_corners: list[list[float]],
    white_camera_edge: str,
) -> None:
    window = "Chess Camera - 64 Square Check"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 900, 900)
    while True:
        ok, raw = capture.read()
        if ok:
            board_view = orient_board_image(
                warp_board(raw, board_corners),
                white_camera_edge,
            )
            labeled = render_grid_verification(board_view)
            cv2.imshow(window, labeled)
        key = cv2.waitKey(20) & 0xFF
        if key in (10, 13, 27):
            cv2.destroyWindow(window)
            return


def run_guided_move_training(
    capture: cv2.VideoCapture,
    board_corners: list[list[float]],
    white_camera_edge: str,
    profile: BoardProfile,
    profile_store: BoardProfileStore,
) -> int:
    """Ask for a legal move sequence and learn each before/after signature."""
    window = "Chess Camera - Guided Board Training"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 1100, 760)
    click_queue: list[str] = []
    current_buttons: list[Button] = []
    board = chess.Board()
    reference: np.ndarray | None = None
    step = 0
    recorded = 0
    message = "Set up the normal starting position, then capture the baseline."

    def on_mouse(
        event: int, x: int, y: int, _flags: int, _data: object
    ) -> None:
        if event != cv2.EVENT_LBUTTONUP:
            return
        action = clicked_action(current_buttons, x, y)
        if action is not None:
            click_queue.append(action)

    cv2.setMouseCallback(window, on_mouse)

    while True:
        ok, raw = capture.read()
        if not ok:
            continue
        warped = orient_board_image(
            warp_board(raw, board_corners),
            white_camera_edge,
        )
        screen = np.zeros((760, 1100, 3), dtype=np.uint8)
        screen[:] = (28, 31, 37)
        preview = cv2.resize(draw_grid(warped, set()), (700, 700))
        screen[30:730, 20:720] = preview
        put_text(
            screen,
            f"Train profile: {profile.name}",
            (750, 50),
            (100, 220, 255),
            0.72,
        )
        put_text(
            screen,
            f"Saved samples: {profile.sample_count}",
            (750, 82),
            (165, 175, 190),
            0.5,
        )

        current_buttons = []
        if reference is None:
            put_text(screen, "1. Arrange the starting position.", (750, 135), scale=0.52)
            put_text(screen, "2. Remove both hands.", (750, 165), scale=0.52)
            begin = Button("baseline", "CAPTURE START", 750, 205, 300, 52, active=True)
            current_buttons.append(begin)
            draw_button(screen, begin)
        elif step < len(GUIDED_TRAINING_LINE):
            move = chess.Move.from_uci(GUIDED_TRAINING_LINE[step])
            san = board.san(move)
            put_text(
                screen,
                f"Move {step + 1}/{len(GUIDED_TRAINING_LINE)}",
                (750, 135),
                (165, 175, 190),
                0.5,
            )
            put_text(screen, f"Please play: {san}", (750, 185), (120, 255, 170), 0.78)
            put_text(screen, f"Squares: {move.uci()}", (750, 220), scale=0.55)
            put_text(screen, "Then remove your hand and click", (750, 270), scale=0.48)
            record = Button("record", "RECORD THIS MOVE", 750, 300, 300, 52, active=True)
            current_buttons.append(record)
            draw_button(screen, record)
        else:
            put_text(screen, "Training complete", (750, 155), (120, 255, 170), 0.78)
            put_text(screen, "Reset the physical board before", (750, 205), scale=0.5)
            put_text(screen, "starting a game.", (750, 235), scale=0.5)

        finish = Button(
            "finish_training",
            "FINISH",
            750,
            620,
            145,
            48,
            active=step >= len(GUIDED_TRAINING_LINE),
        )
        current_buttons.append(finish)
        draw_button(screen, finish)
        put_text(
            screen,
            message[:43],
            (750, 570),
            (100, 220, 255),
            0.45,
        )
        cv2.imshow(window, screen)
        key = cv2.waitKey(20) & 0xFF
        action = click_queue.pop(0) if click_queue else None

        if action == "baseline":
            reference = warped.copy()
            message = "Baseline saved. Make the requested move."
            continue
        if action == "record" and reference is not None:
            move = chess.Move.from_uci(GUIDED_TRAINING_LINE[step])
            expected = move_changed_squares(board, move)
            scores = square_change_scores(reference, warped)
            fit = legal_move_fit(RankedMove(move, 0.0, expected), scores)
            if fit.score < 0.60:
                message = "Could not verify that move. Check it and try again."
                continue
            profile.observe_move(move, scores, expected, weight=3, force=True)
            profile_store.save(profile)
            board.push(move)
            reference = warped.copy()
            step += 1
            recorded += 1
            message = "Move learned. Continue from the current position."
            continue
        if action == "finish_training" or key == 27:
            cv2.destroyWindow(window)
            return recorded


def render_virtual_board(
    board: chess.Board,
    last_move: chess.Move | None = None,
    suggested_move: chess.Move | None = None,
) -> np.ndarray:
    """Render the recorded chess position with White at the bottom."""
    canvas = np.zeros((VIRTUAL_VIEW_HEIGHT, VIRTUAL_VIEW_WIDTH, 3), dtype=np.uint8)
    canvas[:] = (31, 34, 40)

    board_size = 520
    cell = board_size // 8
    left = (VIRTUAL_VIEW_WIDTH - board_size) // 2
    top = 40
    light_square = (181, 217, 240)
    dark_square = (99, 136, 181)
    last_move_color = (40, 205, 245)
    check_color = (70, 70, 225)

    put_text(canvas, "Virtual Board", (left, 28), (100, 220, 255), 0.65)
    last_squares = (
        {last_move.from_square, last_move.to_square} if last_move else set()
    )
    checked_king = board.king(board.turn) if board.is_check() else None

    for rank_from_top in range(8):
        chess_rank = 7 - rank_from_top
        for file_index in range(8):
            square = chess.square(file_index, chess_rank)
            x0 = left + file_index * cell
            y0 = top + rank_from_top * cell
            color = (
                light_square
                if (file_index + chess_rank) % 2 == 1
                else dark_square
            )
            cv2.rectangle(canvas, (x0, y0), (x0 + cell, y0 + cell), color, -1)

            if square in last_squares:
                overlay = canvas.copy()
                cv2.rectangle(
                    overlay,
                    (x0, y0),
                    (x0 + cell, y0 + cell),
                    last_move_color,
                    -1,
                )
                canvas = cv2.addWeighted(overlay, 0.48, canvas, 0.52, 0)
            if square == checked_king:
                cv2.rectangle(
                    canvas,
                    (x0 + 2, y0 + 2),
                    (x0 + cell - 2, y0 + cell - 2),
                    check_color,
                    4,
                )

            piece = board.piece_at(square)
            if piece is not None:
                center = (x0 + cell // 2, y0 + cell // 2)
                if piece.color == chess.WHITE:
                    fill, outline, text_color = (
                        (242, 242, 242),
                        (35, 35, 35),
                        (25, 25, 25),
                    )
                else:
                    fill, outline, text_color = (
                        (38, 41, 47),
                        (235, 235, 235),
                        (245, 245, 245),
                    )
                cv2.circle(canvas, center, 25, fill, -1, cv2.LINE_AA)
                cv2.circle(canvas, center, 25, outline, 2, cv2.LINE_AA)
                label = piece.symbol().upper()
                (text_width, text_height), _ = cv2.getTextSize(
                    label, cv2.FONT_HERSHEY_DUPLEX, 0.86, 2
                )
                cv2.putText(
                    canvas,
                    label,
                    (
                        center[0] - text_width // 2,
                        center[1] + text_height // 2,
                    ),
                    cv2.FONT_HERSHEY_DUPLEX,
                    0.86,
                    text_color,
                    2,
                    cv2.LINE_AA,
                )

    if suggested_move is not None:
        def square_center(square: chess.Square) -> tuple[int, int]:
            file_index = chess.square_file(square)
            rank_from_top = 7 - chess.square_rank(square)
            return (
                left + file_index * cell + cell // 2,
                top + rank_from_top * cell + cell // 2,
            )

        start = square_center(suggested_move.from_square)
        end = square_center(suggested_move.to_square)
        cv2.arrowedLine(
            canvas,
            start,
            end,
            (25, 45, 25),
            10,
            cv2.LINE_AA,
            tipLength=0.23,
        )
        cv2.arrowedLine(
            canvas,
            start,
            end,
            (95, 235, 125),
            5,
            cv2.LINE_AA,
            tipLength=0.23,
        )

    for file_index, file_name in enumerate("abcdefgh"):
        put_text(
            canvas,
            file_name,
            (left + file_index * cell + cell // 2 - 4, top + board_size + 18),
            scale=0.42,
        )
    for rank_from_top in range(8):
        put_text(
            canvas,
            str(8 - rank_from_top),
            (left - 16, top + rank_from_top * cell + cell // 2 + 5),
            scale=0.40,
        )

    if board.is_checkmate():
        state = "CHECKMATE"
        state_color = (70, 70, 255)
    elif board.is_stalemate():
        state = "STALEMATE"
        state_color = (120, 220, 255)
    elif board.is_check():
        state = f"{'White' if board.turn else 'Black'} to move - CHECK"
        state_color = (70, 70, 255)
    else:
        state = f"{'White' if board.turn else 'Black'} to move"
        state_color = (120, 255, 150)

    put_text(canvas, state, (left + 230, 610), state_color, 0.56)
    return canvas


ANALYSIS_COLORS = {
    "Brilliant": (235, 170, 80),
    "Best": (105, 210, 105),
    "Excellent": (130, 220, 150),
    "Good": (165, 205, 170),
    "Inaccuracy": (70, 210, 245),
    "Mistake": (40, 145, 245),
    "Blunder": (70, 70, 235),
    "Miss": (180, 90, 225),
}


def show_analysis_progress(current: int, total: int) -> None:
    window = "Stockfish post-game analysis"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 680, 240)
    view = np.zeros((240, 680, 3), dtype=np.uint8)
    view[:] = (28, 31, 37)
    put_text(view, "Analyzing game locally...", (32, 58), (100, 220, 255), 0.85)
    completed = min(total, max(0, current))
    percentage = completed / max(1, total)
    put_text(
        view,
        f"Position {completed}/{total}  ({percentage:.0%})",
        (32, 108),
        scale=0.58,
    )
    cv2.rectangle(view, (32, 145), (648, 176), (55, 60, 70), -1)
    cv2.rectangle(
        view,
        (32, 145),
        (32 + int(616 * percentage), 176),
        (70, 190, 110),
        -1,
    )
    put_text(
        view,
        "Camera detection and clocks are no longer running.",
        (32, 215),
        (160, 170, 185),
        0.46,
    )
    cv2.imshow(window, view)
    cv2.waitKey(1)


def _analysis_eval_text(centipawns: int, mate: int | None) -> str:
    if mate is not None:
        return f"{'+' if mate > 0 else '-'}M{abs(mate)}"
    sign = "+" if centipawns >= 0 else ""
    return f"{sign}{centipawns / 100:.2f}"


def evaluation_bar_fraction(centipawns: int, mate: int | None) -> float:
    """Return White's share of a vertical evaluation bar."""
    if mate is not None:
        return 1.0 if mate > 0 else 0.0
    return 0.5 + 0.5 * math.tanh(centipawns / 400.0)


def review_scroll_start(
    start: int,
    total: int,
    delta: int,
    visible_count: int = 9,
) -> int:
    maximum = max(0, total - visible_count)
    return min(maximum, max(0, start + delta))


def ensure_review_move_visible(
    current: int,
    start: int,
    total: int,
    visible_count: int = 9,
) -> int:
    if current < start:
        return current
    if current >= start + visible_count:
        return review_scroll_start(
            current - visible_count + 1,
            total,
            0,
            visible_count,
        )
    return review_scroll_start(start, total, 0, visible_count)


def mouse_wheel_direction(flags: int) -> int:
    """Decode OpenCV's signed mouse-wheel delta without optional bindings."""
    delta = (int(flags) >> 16) & 0xFFFF
    if delta & 0x8000:
        delta -= 0x10000
    if delta == 0:
        delta = int(flags)
    return 1 if delta > 0 else (-1 if delta < 0 else 0)


def draw_evaluation_bar(
    view: np.ndarray,
    centipawns: int,
    mate: int | None,
) -> None:
    top, bottom = 90, 610
    left, right = 648, 669
    white_fraction = evaluation_bar_fraction(centipawns, mate)
    split = top + int(round((bottom - top) * (1.0 - white_fraction)))
    cv2.rectangle(view, (left, top), (right, split), (38, 41, 47), -1)
    cv2.rectangle(view, (left, split), (right, bottom), (238, 238, 238), -1)
    cv2.rectangle(view, (left, top), (right, bottom), (115, 125, 142), 2)
    put_text(
        view,
        _analysis_eval_text(centipawns, mate),
        (644, 78),
        (235, 235, 240),
        0.36,
    )


def show_game_review(
    review: GameReview,
    moves: list[chess.Move],
    white_name: str,
    black_name: str,
) -> None:
    window = "Chess Camera - Post-game Review"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 1220, 720)
    current = 0
    scroll_start = 0
    click_queue: list[str] = []
    buttons: list[Button] = []

    def on_mouse(
        event: int, x: int, y: int, _flags: int, _data: object
    ) -> None:
        if event == cv2.EVENT_MOUSEWHEEL:
            direction = mouse_wheel_direction(_flags)
            if direction:
                click_queue.append(
                    "scroll_up" if direction > 0 else "scroll_down"
                )
            return
        if event != cv2.EVENT_LBUTTONUP:
            return
        action = clicked_action(buttons, x, y)
        if action is not None:
            click_queue.append(action)

    cv2.setMouseCallback(window, on_mouse)
    while True:
        selected = review.moves[current]
        board = chess.Board()
        for move in moves[:current]:
            board.push(move)
        best_move = (
            chess.Move.from_uci(selected.best_move_uci)
            if selected.best_move_uci
            else None
        )
        if best_move is not None and best_move not in board.legal_moves:
            best_move = None
        board_view = render_virtual_board(
            board,
            suggested_move=best_move,
        )
        view = np.zeros((720, 1220, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        view[50:670, 20:640] = board_view
        draw_evaluation_bar(
            view,
            selected.evaluation_after_white,
            selected.mate_after_white,
        )

        put_text(view, "Post-game Review", (675, 42), (100, 220, 255), 0.9)
        put_text(
            view,
            f"{(white_name or 'White')[:20]}: {review.white_accuracy:.1f}% | "
            f"Avg loss {review.white_average_centipawn_loss:.1f} cp",
            (700, 82),
            (235, 235, 240),
            0.52,
        )
        put_text(
            view,
            f"{(black_name or 'Black')[:20]}: {review.black_accuracy:.1f}% | "
            f"Avg loss {review.black_average_centipawn_loss:.1f} cp",
            (700, 110),
            (185, 190, 200),
            0.52,
        )
        put_text(
            view,
            f"{selected.move_number}{'.' if selected.white else '...'} "
            f"{selected.san}  -  {selected.classification}",
            (675, 154),
            ANALYSIS_COLORS.get(selected.classification, (235, 235, 235)),
            0.73,
        )
        put_text(
            view,
            f"Move accuracy {selected.accuracy:.1f}% | "
            f"loss {selected.centipawn_loss} cp | "
            f"White eval {_analysis_eval_text(selected.evaluation_after_white, selected.mate_after_white)}",
            (675, 190),
            (185, 195, 210),
            0.48,
        )
        best_text = (
            f"Stockfish suggests {selected.best_move_san} "
            f"({selected.best_move_uci})"
            if selected.best_move_san and selected.best_move_uci != selected.uci
            else "Played an engine-best move."
        )
        put_text(view, best_text[:57], (675, 220), (120, 220, 255), 0.48)

        white_counts = review.classification_counts(chess.WHITE)
        black_counts = review.classification_counts(chess.BLACK)
        count_order = [
            "Brilliant",
            "Best",
            "Excellent",
            "Good",
            "Inaccuracy",
            "Mistake",
            "Blunder",
            "Miss",
        ]
        for row, label in enumerate(count_order):
            y = 266 + row * 31
            put_text(
                view,
                label,
                (675, y),
                ANALYSIS_COLORS[label],
                0.48,
            )
            put_text(view, str(white_counts.get(label, 0)), (835, y), scale=0.48)
            put_text(view, str(black_counts.get(label, 0)), (895, y), scale=0.48)
        put_text(view, "W", (835, 244), (235, 235, 240), 0.45)
        put_text(view, "B", (895, 244), (185, 190, 200), 0.45)

        visible = review.moves[scroll_start : scroll_start + 9]
        put_text(view, "Move list", (975, 254), (100, 220, 255), 0.55)
        move_buttons: list[Button] = []
        for row, move_review in enumerate(visible):
            index = scroll_start + row
            y = 286 + row * 33
            move_buttons.append(
                Button(f"select_move_{index}", "", 965, y - 23, 233, 30)
            )
            if index == current:
                cv2.rectangle(view, (965, y - 23), (1198, y + 7), (55, 65, 72), -1)
            prefix = f"{move_review.move_number}{'.' if move_review.white else '...'}"
            put_text(
                view,
                f"{prefix} {move_review.san[:8]}",
                (975, y),
                scale=0.46,
            )
            put_text(
                view,
                move_review.classification[:10],
                (1080, y),
                ANALYSIS_COLORS.get(move_review.classification, (230, 230, 230)),
                0.43,
            )

        navigation_buttons = [
            Button("previous", "PREVIOUS", 675, 610, 150, 48, enabled=current > 0),
            Button(
                "next",
                "NEXT",
                840,
                610,
                150,
                48,
                enabled=current < len(review.moves) - 1,
            ),
            Button("close", "CLOSE", 1005, 610, 185, 48, active=True),
            Button(
                "scroll_up",
                "^",
                1140,
                228,
                26,
                26,
                enabled=scroll_start > 0,
            ),
            Button(
                "scroll_down",
                "v",
                1172,
                228,
                26,
                26,
                enabled=scroll_start + 9 < len(review.moves),
            ),
        ]
        buttons = move_buttons + navigation_buttons
        for button in navigation_buttons:
            draw_button(view, button)
        put_text(
            view,
            f"Engine: {review.engine_name} | Labels are Chess Camera estimates.",
            (675, 700),
            (145, 155, 170),
            0.42,
        )
        cv2.imshow(window, view)
        key = cv2.waitKey(20) & 0xFF
        action = click_queue.pop(0) if click_queue else None
        if action == "previous" or key in (81, 2424832, ord(",")):
            current = max(0, current - 1)
        elif action == "next" or key in (83, 2555904, ord(".")):
            current = min(len(review.moves) - 1, current + 1)
        elif action is not None and action.startswith("select_move_"):
            try:
                current = min(
                    len(review.moves) - 1,
                    max(0, int(action.removeprefix("select_move_"))),
                )
            except ValueError:
                pass
        elif action == "scroll_up":
            scroll_start = review_scroll_start(
                scroll_start,
                len(review.moves),
                -3,
            )
        elif action == "scroll_down":
            scroll_start = review_scroll_start(
                scroll_start,
                len(review.moves),
                3,
            )
        elif action == "close" or key in (10, 13, 27):
            cv2.destroyWindow(window)
            return
        if action in {"previous", "next"} or key in (
            81,
            83,
            2424832,
            2555904,
            ord(","),
            ord("."),
        ):
            scroll_start = ensure_review_move_visible(
                current,
                scroll_start,
                len(review.moves),
            )
        if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
            return


def create_post_game_review(
    moves: list[chess.Move],
    stockfish_path: Path | None,
) -> GameReview | None:
    if not moves:
        show_result_popup("Review unavailable", "No moves have been recorded.")
        return None
    if stockfish_path is None:
        show_result_popup(
            "Stockfish not found",
            "Install Stockfish, place its executable in the engines folder, "
            "or launch with --stockfish followed by its full path.",
        )
        return None
    try:
        review = analyze_game(
            moves,
            stockfish_path,
            DEFAULT_ANALYSIS_SECONDS,
            show_analysis_progress,
        )
    except AnalysisUnavailable as error:
        cv2.destroyWindow("Stockfish post-game analysis")
        show_result_popup("Analysis failed", str(error))
        return None
    cv2.destroyWindow("Stockfish post-game analysis")
    save_analysis_report(review, Path("games/latest_analysis.json"))
    timestamped = Path("games") / (
        datetime.now().strftime("analysis_%Y-%m-%d_%H-%M-%S") + ".json"
    )
    save_analysis_report(review, timestamped)
    return review


def draw_illegal_warning(image: np.ndarray) -> np.ndarray:
    """Draw a large, unmistakable red warning over the combined display."""
    view = image.copy()
    overlay = view.copy()
    height, width = view.shape[:2]
    cv2.rectangle(overlay, (0, 0), (width, height), (0, 0, 205), -1)
    view = cv2.addWeighted(overlay, 0.72, view, 0.28, 0)

    title = "ILLEGAL MOVE"
    subtitle = "RETURN THE PIECES TO THE LAST LEGAL POSITION"
    (title_width, title_height), _ = cv2.getTextSize(
        title, cv2.FONT_HERSHEY_DUPLEX, 2.25, 5
    )
    (sub_width, _), _ = cv2.getTextSize(
        subtitle, cv2.FONT_HERSHEY_SIMPLEX, 0.82, 2
    )
    title_x = max(20, (width - title_width) // 2)
    subtitle_x = max(20, (width - sub_width) // 2)
    center_y = height // 2

    cv2.rectangle(
        view,
        (35, center_y - 115),
        (width - 35, center_y + 175),
        (0, 0, 110),
        -1,
    )
    cv2.rectangle(
        view,
        (35, center_y - 115),
        (width - 35, center_y + 175),
        (255, 255, 255),
        4,
    )
    cv2.putText(
        view,
        title,
        (title_x, center_y - 15 + title_height // 3),
        cv2.FONT_HERSHEY_DUPLEX,
        2.25,
        (255, 255, 255),
        5,
        cv2.LINE_AA,
    )
    cv2.putText(
        view,
        subtitle,
        (subtitle_x, center_y + 65),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.82,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    draw_button(view, illegal_warning_button(width, height))
    return view


def illegal_warning_button(width: int, height: int) -> Button:
    """Return the clickable manual-recovery button for an illegal warning."""
    return Button(
        "dismiss_illegal",
        "DISMISS WARNING (ESC / X)",
        max(20, width // 2 - 165),
        height // 2 + 95,
        330,
        54,
        active=True,
    )


def select_promotion_candidate(
    candidates: list[RankedMove],
    piece_type: chess.PieceType,
) -> list[RankedMove]:
    """Apply one promotion choice and remove duplicate piece variants."""
    if not candidates or candidates[0].move.promotion is None:
        return candidates

    primary = candidates[0]
    chosen_move = move_with_promotion(primary.move, piece_type)
    chosen = RankedMove(chosen_move, primary.score, primary.expected_squares)
    remaining = [
        candidate
        for candidate in candidates[1:]
        if not (
            candidate.move.from_square == primary.move.from_square
            and candidate.move.to_square == primary.move.to_square
            and candidate.move.promotion is not None
        )
    ]
    return [chosen, *remaining]


def manual_correction_candidates(
    board: chess.Board,
    scores: dict[chess.Square, float],
    rejected_move: chess.Move,
    profile: BoardProfile,
) -> list[RankedMove]:
    """Rank alternatives manually while keeping the rejected move available."""
    ranked = rank_legal_moves(
        board,
        profile.adjusted_scores(scores) if profile.learning_enabled else scores,
        profile.learned_patterns() if profile.learning_enabled else None,
        profile.learned_rejections() if profile.learning_enabled else None,
    )
    alternatives = [
        candidate for candidate in ranked if candidate.move != rejected_move
    ][:7]
    rejected = next(
        (candidate for candidate in ranked if candidate.move == rejected_move),
        None,
    )
    if rejected is not None:
        alternatives.append(rejected)
    return alternatives


def choose_promotion_piece() -> chess.PieceType:
    """Show a modal promotion chooser; Enter and window-close default to Queen."""
    window = "Choose promotion piece"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 640, 260)
    buttons = [
        Button("queen", "QUEEN", 28, 122, 135, 70, active=True),
        Button("rook", "ROOK", 178, 122, 135, 70),
        Button("bishop", "BISHOP", 328, 122, 135, 70),
        Button("knight", "KNIGHT", 478, 122, 135, 70),
    ]
    click_queue: list[str] = []

    def on_mouse(
        event: int, x: int, y: int, _flags: int, _data: object
    ) -> None:
        if event != cv2.EVENT_LBUTTONUP:
            return
        action = clicked_action(buttons, x, y)
        if action is not None:
            click_queue.append(action)

    cv2.setMouseCallback(window, on_mouse)
    piece_for_action = {
        "queen": chess.QUEEN,
        "rook": chess.ROOK,
        "bishop": chess.BISHOP,
        "knight": chess.KNIGHT,
    }
    key_for_piece = {
        ord("q"): chess.QUEEN,
        ord("r"): chess.ROOK,
        ord("b"): chess.BISHOP,
        ord("n"): chess.KNIGHT,
    }

    while True:
        view = np.zeros((260, 640, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        put_text(
            view,
            "Pawn promotion",
            (28, 43),
            (100, 220, 255),
            0.9,
        )
        put_text(
            view,
            "Choose a piece. Press ENTER for the default Queen.",
            (28, 83),
            (225, 225, 230),
            0.57,
        )
        for button in buttons:
            draw_button(view, button)
        put_text(
            view,
            "Keyboard: Q / R / B / N",
            (205, 231),
            (160, 170, 185),
            0.48,
        )
        cv2.imshow(window, view)
        key = cv2.waitKey(20) & 0xFF
        action = click_queue.pop(0) if click_queue else None

        if action in piece_for_action:
            cv2.destroyWindow(window)
            return piece_for_action[action]
        if key in (10, 13):
            cv2.destroyWindow(window)
            return chess.QUEEN
        if key in key_for_piece:
            cv2.destroyWindow(window)
            return key_for_piece[key]
        if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
            return chess.QUEEN


def save_game(
    moves: list[chess.Move],
    clocks: list[float | None],
    headers: dict[str, str] | None = None,
    result: str = "*",
) -> None:
    write_pgn(
        moves,
        OUTPUT_PATH,
        result=result,
        clocks=clocks,
        headers=headers,
    )


def reading_label(reading: object) -> str:
    seconds = getattr(reading, "seconds", None)
    confidence = getattr(reading, "confidence", 0.0)
    if seconds is None:
        return "--:--"
    return f"{format_pgn_clock(seconds)} ({confidence:.0%})"


def format_display_clock(seconds: float) -> str:
    safe = max(0.0, seconds)
    hours = int(safe // 3600)
    minutes = int((safe % 3600) // 60)
    remaining = safe % 60
    if safe < 10:
        return f"{int(remaining):01d}.{int((remaining % 1) * 10):01d}"
    if hours:
        return f"{hours}:{minutes:02d}:{int(remaining):02d}"
    return f"{minutes}:{int(remaining):02d}"


def configure_builtin_clock(
    current: ClockSettings,
) -> ClockSettings | None:
    """Open a cross-platform pre-game editor for asymmetric time controls."""
    window = "Built-in clock setup"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 760, 500)

    def noop(_value: int) -> None:
        pass

    cv2.createTrackbar(
        "White minutes", window, int(current.white_initial_seconds // 60), 180, noop
    )
    cv2.createTrackbar(
        "White seconds", window, int(current.white_initial_seconds % 60), 59, noop
    )
    cv2.createTrackbar(
        "White increment", window, int(current.white_increment_seconds), 60, noop
    )
    cv2.createTrackbar(
        "Black minutes", window, int(current.black_initial_seconds // 60), 180, noop
    )
    cv2.createTrackbar(
        "Black seconds", window, int(current.black_initial_seconds % 60), 59, noop
    )
    cv2.createTrackbar(
        "Black increment", window, int(current.black_increment_seconds), 60, noop
    )

    warning = ""
    while True:
        white_initial = (
            cv2.getTrackbarPos("White minutes", window) * 60
            + cv2.getTrackbarPos("White seconds", window)
        )
        black_initial = (
            cv2.getTrackbarPos("Black minutes", window) * 60
            + cv2.getTrackbarPos("Black seconds", window)
        )
        white_increment = cv2.getTrackbarPos("White increment", window)
        black_increment = cv2.getTrackbarPos("Black increment", window)

        view = np.zeros((310, 760, 3), dtype=np.uint8)
        view[:] = (31, 34, 40)
        put_text(view, "Built-in Chess Clock", (25, 42), (100, 220, 255), 0.86)
        put_text(
            view,
            f"White: {format_display_clock(white_initial)} + {white_increment}s",
            (25, 100),
            (235, 235, 235),
            0.76,
        )
        put_text(
            view,
            f"Black: {format_display_clock(black_initial)} + {black_increment}s",
            (25, 145),
            (170, 190, 255),
            0.76,
        )
        put_text(
            view,
            "Adjust the six sliders above.",
            (25, 205),
            scale=0.58,
        )
        put_text(
            view,
            "ENTER saves | ESC cancels",
            (25, 240),
            (120, 255, 150),
            0.62,
        )
        if warning:
            put_text(view, warning, (25, 280), (70, 70, 255), 0.55)
        cv2.imshow(window, view)

        key = cv2.waitKey(25) & 0xFF
        if key == 27:
            cv2.destroyWindow(window)
            return None
        if key in (10, 13):
            if white_initial < 1 or black_initial < 1:
                warning = "Each player needs at least one second."
                continue
            cv2.destroyWindow(window)
            return ClockSettings(
                float(white_initial),
                float(black_initial),
                float(white_increment),
                float(black_increment),
            )


def apply_midgame_clock_adjustment(
    white_seconds: float,
    black_seconds: float,
    action: str,
) -> tuple[float, float]:
    """Apply one safe quick adjustment to a paused clock pair."""
    changes = {
        "white_minus60": (True, -60.0),
        "white_minus10": (True, -10.0),
        "white_plus10": (True, 10.0),
        "white_plus60": (True, 60.0),
        "black_minus60": (False, -60.0),
        "black_minus10": (False, -10.0),
        "black_plus10": (False, 10.0),
        "black_plus60": (False, 60.0),
    }
    change = changes.get(action)
    if change is None:
        return white_seconds, black_seconds
    player_is_white, amount = change
    if player_is_white:
        white_seconds = min(36000.0, max(0.0, white_seconds + amount))
    else:
        black_seconds = min(36000.0, max(0.0, black_seconds + amount))
    return white_seconds, black_seconds


def adjust_builtin_clock(clock: BuiltInChessClock) -> bool:
    """Let the user adjust a paused built-in clock and confirm or cancel."""
    window = "Adjust clocks"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 760, 430)
    original_white = clock.white_seconds
    original_black = clock.black_seconds
    white_seconds = original_white
    black_seconds = original_black
    click_queue: list[str] = []
    buttons: list[Button] = []

    def on_mouse(
        event: int, x: int, y: int, _flags: int, _data: object
    ) -> None:
        if event != cv2.EVENT_LBUTTONUP:
            return
        action = clicked_action(buttons, x, y)
        if action is not None:
            click_queue.append(action)

    cv2.setMouseCallback(window, on_mouse)
    while True:
        view = np.zeros((430, 760, 3), dtype=np.uint8)
        view[:] = (31, 34, 40)
        put_text(view, "Adjust Built-in Clocks", (28, 45), (100, 220, 255), 0.84)
        put_text(
            view,
            "Both clocks are paused. Changes apply only after Confirm.",
            (28, 78),
            (175, 185, 200),
            0.50,
        )
        buttons = []
        for player, seconds, y, prefix, color in (
            ("White", white_seconds, 125, "white", (235, 235, 235)),
            ("Black", black_seconds, 235, "black", (170, 190, 255)),
        ):
            put_text(
                view,
                f"{player}: {format_display_clock(seconds)}",
                (30, y),
                color,
                0.72,
            )
            for index, (suffix, label) in enumerate(
                (
                    ("minus60", "-1m"),
                    ("minus10", "-10s"),
                    ("plus10", "+10s"),
                    ("plus60", "+1m"),
                )
            ):
                button = Button(
                    f"{prefix}_{suffix}",
                    label,
                    250 + index * 118,
                    y - 34,
                    105,
                    40,
                )
                buttons.append(button)
                draw_button(view, button)
        confirm = Button("confirm", "CONFIRM", 250, 340, 210, 54, active=True)
        cancel = Button("cancel", "Cancel", 480, 340, 210, 54)
        buttons.extend((confirm, cancel))
        draw_button(view, confirm)
        draw_button(view, cancel)
        put_text(
            view,
            "Enter confirms | Esc cancels",
            (30, 375),
            (165, 175, 190),
            0.48,
        )
        cv2.imshow(window, view)
        key = cv2.waitKey(20) & 0xFF
        action = click_queue.pop(0) if click_queue else None
        if action in {
            "white_minus60",
            "white_minus10",
            "white_plus10",
            "white_plus60",
            "black_minus60",
            "black_minus10",
            "black_plus10",
            "black_plus60",
        }:
            white_seconds, black_seconds = apply_midgame_clock_adjustment(
                white_seconds,
                black_seconds,
                action,
            )
            continue
        if action == "confirm" or key in (10, 13):
            clock.set_remaining(white_seconds, black_seconds)
            cv2.destroyWindow(window)
            return True
        if action == "cancel" or key == 27:
            cv2.destroyWindow(window)
            return False


def choose_pinned_time_controls(
    current: tuple[str, ...],
) -> tuple[str, ...] | None:
    """Open a preset picker; return the confirmed selection or None."""
    window = "Choose pinned time controls"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 760, 470)
    selected = current
    click_queue: list[str] = []
    buttons: list[Button] = []
    message = "Select up to six presets."

    def on_mouse(
        event: int, x: int, y: int, _flags: int, _data: object
    ) -> None:
        if event != cv2.EVENT_LBUTTONUP:
            return
        action = clicked_action(buttons, x, y)
        if action is not None:
            click_queue.append(action)

    cv2.setMouseCallback(window, on_mouse)
    while True:
        view = np.zeros((470, 760, 3), dtype=np.uint8)
        view[:] = (31, 34, 40)
        put_text(view, "Choose Pinned Time Controls", (28, 45), (100, 220, 255), 0.82)
        put_text(
            view,
            "Selected presets appear in the empty setup area.",
            (28, 78),
            (175, 185, 200),
            0.50,
        )
        buttons = []
        for index, (label, _initial, _increment) in enumerate(
            TIME_CONTROL_PRESETS
        ):
            button = Button(
                f"toggle_preset_{label}",
                label,
                45 + (index % 4) * 175,
                115 + (index // 4) * 58,
                150,
                44,
                active=label in selected,
            )
            buttons.append(button)
            draw_button(view, button)
        confirm = Button("confirm", "CONFIRM", 250, 370, 210, 54, active=True)
        cancel = Button("cancel", "Cancel", 480, 370, 210, 54)
        buttons.extend((confirm, cancel))
        draw_button(view, confirm)
        draw_button(view, cancel)
        put_text(view, message, (45, 345), (120, 220, 255), 0.48)
        cv2.imshow(window, view)
        key = cv2.waitKey(20) & 0xFF
        action = click_queue.pop(0) if click_queue else None
        if action is not None and action.startswith("toggle_preset_"):
            label = action.removeprefix("toggle_preset_")
            updated = toggle_pinned_time_control(selected, label)
            if updated == selected and label not in selected and len(selected) >= 6:
                message = "Maximum six pinned presets. Remove one before adding another."
            else:
                selected = updated
                message = f"{len(selected)}/6 presets selected."
            continue
        if action == "confirm" or key in (10, 13):
            cv2.destroyWindow(window)
            return selected
        if action == "cancel" or key == 27:
            cv2.destroyWindow(window)
            return None


def run_pregame_wizard(
    capture: cv2.VideoCapture,
    setup: GameSetup,
    board_corners: list[list[float]],
    phone_corners: list[list[float]],
    profile: BoardProfile,
    profile_store: BoardProfileStore,
    engine_path: Path | None,
    allow_cancel: bool,
    player_name_usage: dict[str, int],
    event_name_usage: dict[str, int],
) -> tuple[
    GameSetup,
    list[list[float]],
    list[list[float]],
    BoardProfile,
    Path | None,
] | None:
    """Run the clickable game-settings step after camera calibration."""
    window = "Chess Camera - Step 2: Game Settings"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 1100, 920)
    current_buttons: list[Button] = []
    click_queue: list[str] = []
    focused_field: str | None = None
    active_slider_action: str | None = None
    message = ""
    setup = replace(
        setup,
        profile_name=profile.name,
        profile_samples=profile.sample_count,
        learning_enabled=profile.learning_enabled,
        engine_name=engine_path.name if engine_path else "Auto-detect",
    )

    def persist_profile() -> None:
        profile.board_corners = board_corners
        profile.phone_corners = phone_corners
        profile.white_camera_edge = setup.white_camera_edge
        profile.bottom_clock_is_white = setup.bottom_clock_is_white
        profile.learning_enabled = setup.learning_enabled
        profile_store.save(profile)
        save_config(
            board_corners,
            phone_corners,
            setup.bottom_clock_is_white,
            setup.white_camera_edge,
            profile.name,
            engine_path,
            setup.pinned_time_controls,
            player_name_usage,
            event_name_usage,
        )

    def select_profile(selected: BoardProfile) -> None:
        nonlocal profile, setup, board_corners, phone_corners
        persist_profile()
        profile = selected
        if profile.board_corners is not None:
            board_corners = profile.board_corners
        if profile.phone_corners is not None:
            phone_corners = profile.phone_corners
        setup = replace(
            setup,
            profile_name=profile.name,
            profile_samples=profile.sample_count,
            learning_enabled=profile.learning_enabled,
            white_camera_edge=profile.white_camera_edge,
            bottom_clock_is_white=profile.bottom_clock_is_white,
        )

    def on_mouse(
        event: int, x: int, y: int, _flags: int, _data: object
    ) -> None:
        nonlocal setup, active_slider_action

        def update_slider(action: str) -> None:
            nonlocal setup
            slider = next(
                (
                    button
                    for button in current_buttons
                    if button.action == action and button.enabled
                ),
                None,
            )
            if slider is None:
                return
            setup = apply_time_slider_value(
                setup,
                action,
                slider_value_from_x(action, slider, x),
            )

        if event == cv2.EVENT_LBUTTONDOWN:
            action = clicked_action(current_buttons, x, y)
            if action is not None and action.startswith("slider_"):
                active_slider_action = action
                update_slider(action)
            return
        if (
            event == cv2.EVENT_MOUSEMOVE
            and active_slider_action is not None
            and _flags & cv2.EVENT_FLAG_LBUTTON
        ):
            update_slider(active_slider_action)
            return
        if event != cv2.EVENT_LBUTTONUP:
            return
        if active_slider_action is not None:
            update_slider(active_slider_action)
            active_slider_action = None
            return
        action = clicked_action(current_buttons, x, y)
        if action is not None:
            click_queue.append(action)

    cv2.setMouseCallback(window, on_mouse)

    while True:
        player_suggestions = most_used_values(player_name_usage)
        event_suggestions = most_used_values(event_name_usage)
        ok, raw = capture.read()
        preview = raw if ok else None
        screen, current_buttons = render_setup_screen(
            setup,
            focused_field,
            camera_preview=preview,
            message=message,
            player_suggestions=player_suggestions,
            event_suggestions=event_suggestions,
        )
        cv2.imshow(window, screen)
        key = cv2.waitKey(20) & 0xFF
        action = click_queue.pop(0) if click_queue else None

        if action in {"focus_white", "focus_black", "focus_event"}:
            focused_field = action.removeprefix("focus_")
            continue
        if action is not None and action.startswith("suggest_"):
            setup = apply_setup_suggestion(
                setup,
                action,
                player_suggestions,
                event_suggestions,
            )
            focused_field = action.split("_")[1]
            continue
        if action == "calibrate_board":
            focused_field = None
            board_corners = calibrate_board(capture)
            persist_profile()
            message = "Board calibration updated."
            continue
        if action == "calibrate_phone":
            focused_field = None
            phone_corners = calibrate_phone(capture)
            persist_profile()
            message = "Phone calibration updated."
            continue
        if action == "verify_grid":
            focused_field = None
            show_grid_verification(
                capture,
                board_corners,
                setup.white_camera_edge,
            )
            message = "64-square grid checked."
            continue
        if action == "profile_previous":
            select_profile(profile_store.cycle(profile.name, -1))
            message = f"Selected {profile.name}."
            continue
        if action == "profile_next":
            select_profile(profile_store.cycle(profile.name, 1))
            message = f"Selected {profile.name}."
            continue
        if action == "profile_new":
            select_profile(profile_store.create_from(profile))
            message = f"Created {profile.name}; recalibrate if the camera changed."
            continue
        if action == "profile_rename":
            focused_field = None
            renamed = prompt_for_text(
                "Rename board preset",
                "New preset name",
                profile.name,
            )
            cv2.namedWindow(window, cv2.WINDOW_NORMAL)
            cv2.setMouseCallback(window, on_mouse)
            if renamed is None:
                message = "Board preset rename cancelled."
                continue
            try:
                profile_store.rename(profile, renamed)
            except (ValueError, OSError) as error:
                show_result_popup("Cannot rename preset", str(error))
                message = "Board preset name was not changed."
                continue
            setup = replace(setup, profile_name=profile.name)
            persist_profile()
            message = f"Renamed board preset to {profile.name}."
            continue
        if action == "profile_reset_training":
            focused_field = None
            confirmed = ask_yes_no(
                "Reset board training?",
                f'Clear all learned move data for "{profile.name}"? '
                "Calibration and orientation will be kept.",
            )
            cv2.namedWindow(window, cv2.WINDOW_NORMAL)
            cv2.setMouseCallback(window, on_mouse)
            if confirmed:
                profile.reset_training()
                profile_store.save(profile)
                setup = replace(setup, profile_samples=0)
                message = "Board training reset; calibration was kept."
            else:
                message = "Board training was not changed."
            continue
        if action == "profile_train":
            focused_field = None
            recorded = run_guided_move_training(
                capture,
                board_corners,
                setup.white_camera_edge,
                profile,
                profile_store,
            )
            setup = replace(setup, profile_samples=profile.sample_count)
            message = (
                f"Learned {recorded} guided moves. Reset the board before starting."
            )
            continue
        if action == "select_engine":
            focused_field = None
            selected, picker_error = choose_uci_engine_file(engine_path)
            if picker_error:
                show_result_popup("Engine picker unavailable", picker_error)
                message = "Engine selection was not changed."
                continue
            if selected is None:
                message = "Engine selection cancelled."
                continue
            resolved = find_stockfish(str(selected))
            if resolved is None:
                show_result_popup(
                    "Invalid engine executable",
                    "Choose an executable file. On Ubuntu or macOS, the file "
                    "must also have execute permission.",
                )
                message = "Engine selection was not changed."
                continue
            try:
                engine_name = probe_uci_engine(resolved)
            except AnalysisUnavailable as error:
                show_result_popup("Invalid UCI engine", str(error))
                message = "Engine selection was not changed."
                continue
            engine_path = resolved
            setup = replace(setup, engine_name=engine_name)
            persist_profile()
            message = f"Selected analysis engine: {engine_name}."
            continue
        if action == "choose_pinned_presets":
            focused_field = None
            selected_presets = choose_pinned_time_controls(
                setup.pinned_time_controls
            )
            cv2.namedWindow(window, cv2.WINDOW_NORMAL)
            cv2.setMouseCallback(window, on_mouse)
            if selected_presets is None:
                message = "Pinned presets were not changed."
            else:
                setup = replace(
                    setup,
                    pinned_time_controls=selected_presets,
                )
                persist_profile()
                message = f"Pinned {len(selected_presets)} time controls."
            continue
        if action == "start" or (key in (10, 13) and focused_field is None):
            remember_used_value(player_name_usage, setup.white_name)
            remember_used_value(player_name_usage, setup.black_name)
            remember_used_value(event_name_usage, setup.event_name)
            persist_profile()
            cv2.destroyWindow(window)
            return setup, board_corners, phone_corners, profile, engine_path

        if action is not None:
            focused_field = None
            setup = apply_setup_action(setup, action)
            if action == "learning_toggle":
                profile.learning_enabled = setup.learning_enabled
                profile_store.save(profile)
            message = ""

        if key == 27:
            if allow_cancel:
                cv2.destroyWindow(window)
                return None
            continue
        if key == 9:
            order = ["white", "black", "event"]
            if focused_field not in order:
                focused_field = order[0]
            else:
                focused_field = order[(order.index(focused_field) + 1) % len(order)]
        elif focused_field is not None and key != 255:
            if key in (10, 13):
                focused_field = None
            else:
                setup = update_text_field(setup, focused_field, key)


def clock_for_player(
    clocks: BothClocks | None,
    player_is_white: bool,
    bottom_clock_is_white: bool,
) -> float | None:
    if clocks is None:
        return None
    use_bottom = player_is_white == bottom_clock_is_white
    reading = clocks.bottom if use_bottom else clocks.top
    if reading.seconds is None or reading.confidence < 0.70:
        return None
    return reading.seconds


def format_moves(moves: list[chess.Move]) -> str:
    board = chess.Board()
    sans: list[str] = []
    for move in moves:
        sans.append(board.san(move))
        board.push(move)
    pairs = []
    for index in range(0, len(sans), 2):
        black = f" {sans[index + 1]}" if index + 1 < len(sans) else ""
        pairs.append(f"{index // 2 + 1}. {sans[index]}{black}")
    return "  ".join(pairs[-5:]) or "(no moves yet)"


def move_history_lines(moves: list[chess.Move], limit: int = 9) -> list[str]:
    board = chess.Board()
    sans: list[str] = []
    for move in moves:
        sans.append(board.san(move))
        board.push(move)
    lines = []
    for index in range(0, len(sans), 2):
        white = sans[index]
        black = sans[index + 1] if index + 1 < len(sans) else ""
        lines.append(f"{index // 2 + 1:>2}.  {white:<12} {black}")
    return lines[-limit:]


def draw_wrapped_text(
    image: np.ndarray,
    text: str,
    x: int,
    y: int,
    max_characters: int,
    max_lines: int = 3,
    color: tuple[int, int, int] = (245, 245, 245),
    scale: float = 0.52,
) -> None:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_characters:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    for row, line in enumerate(lines[:max_lines]):
        put_text(image, line, (x, y + row * 24), color, scale)


def show_result_popup(title: str, message: str) -> None:
    window = f"Game result - {title}"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 680, 280)
    ok_button = Button("ok", "OK", 250, 198, 180, 52, active=True)
    clicks: list[str] = []

    def on_mouse(
        event: int, x: int, y: int, _flags: int, _data: object
    ) -> None:
        if event == cv2.EVENT_LBUTTONUP and ok_button.contains(x, y):
            clicks.append("ok")

    cv2.setMouseCallback(window, on_mouse)
    while True:
        view = np.zeros((280, 680, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        put_text(view, title, (34, 52), (100, 220, 255), 0.92)
        draw_wrapped_text(view, message, 34, 103, 62, max_lines=3, scale=0.58)
        draw_button(view, ok_button)
        cv2.imshow(window, view)
        key = cv2.waitKey(20) & 0xFF
        if clicks or key in (10, 13, 27):
            cv2.destroyWindow(window)
            return
        if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
            return


def ask_yes_no(title: str, message: str) -> bool:
    window = title
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 680, 300)
    buttons = [
        Button("yes", "YES", 135, 216, 180, 54, active=True),
        Button("no", "NO", 365, 216, 180, 54),
    ]
    clicks: list[str] = []

    def on_mouse(
        event: int, x: int, y: int, _flags: int, _data: object
    ) -> None:
        if event != cv2.EVENT_LBUTTONUP:
            return
        action = clicked_action(buttons, x, y)
        if action is not None:
            clicks.append(action)

    cv2.setMouseCallback(window, on_mouse)
    while True:
        view = np.zeros((300, 680, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        put_text(view, title, (34, 52), (100, 220, 255), 0.86)
        draw_wrapped_text(view, message, 34, 103, 62, max_lines=4, scale=0.56)
        for button in buttons:
            draw_button(view, button)
        put_text(view, "Keyboard: Y / N", (256, 292), (150, 160, 175), 0.43)
        cv2.imshow(window, view)
        key = cv2.waitKey(20) & 0xFF
        action = clicks.pop(0) if clicks else None
        if action == "yes" or key == ord("y"):
            cv2.destroyWindow(window)
            return True
        if action == "no" or key in (ord("n"), 10, 13, 27):
            cv2.destroyWindow(window)
            return False
        if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
            return False


def ask_both_players_for_draw(
    reason: str,
    white_name: str,
    black_name: str,
) -> bool:
    white_accepts = ask_yes_no(
        reason,
        f"{white_name or 'White'}: Do you agree to a draw?",
    )
    black_accepts = ask_yes_no(
        reason,
        f"{black_name or 'Black'}: Do you agree to a draw?",
    )
    return white_accepts and black_accepts


def manual_clock_player_for_key(key: int) -> bool | None:
    if key in (ord("a"), ord("A")):
        return chess.WHITE
    if key in (ord("l"), ord("L")):
        return chess.BLACK
    return None


def detection_profile(
    fast_mode: bool,
    bullet_mode: bool,
) -> tuple[str, float, float]:
    if bullet_mode:
        return "BULLET", BULLET_STABLE_SECONDS, BULLET_ACCEPT_COOLDOWN
    if fast_mode:
        return "FAST", FAST_STABLE_SECONDS, FAST_ACCEPT_COOLDOWN
    return "NORMAL", STABLE_SECONDS, 1.0


def frame_motion_score(
    previous: np.ndarray,
    current: np.ndarray,
    sample_step: int = 3,
) -> float:
    """Measure movement on small frames while keeping full frames for move analysis."""
    previous_small = previous[::sample_step, ::sample_step]
    current_small = current[::sample_step, ::sample_step]
    previous_gray = cv2.cvtColor(previous_small, cv2.COLOR_BGR2GRAY)
    current_gray = cv2.cvtColor(current_small, cv2.COLOR_BGR2GRAY)
    return float(np.mean(cv2.absdiff(previous_gray, current_gray)))


def pause_clock_for_illegal_move(
    clock: BuiltInChessClock,
    manual_clock: ManualClockController,
    now: float,
) -> bool | None:
    """Pause the built-in clock and return the side that must retry."""
    if manual_clock.pending is not None:
        manual_clock.cancel(clock, now)
    retrying_side = clock.active_white
    clock.pause(now)
    return retrying_side


def resume_clock_after_illegal_move(
    clock: BuiltInChessClock,
    retrying_side: bool | None,
    now: float,
) -> None:
    if retrying_side is not None:
        clock.start(now, retrying_side)


def main() -> None:
    parser = argparse.ArgumentParser(description="Record a physical chess game as PGN.")
    parser.add_argument("--camera", type=int, default=0, help="Camera index (default: 0)")
    parser.add_argument(
        "--recalibrate", action="store_true", help="Ignore saved board corners"
    )
    parser.add_argument(
        "--engine",
        "--stockfish",
        dest="engine_path",
        type=str,
        default=None,
        help="Full path to a UCI chess-engine executable for post-game review",
    )
    args = parser.parse_args()

    capture = open_camera(args.camera)
    clock_worker: BackgroundClockReader | None = None
    try:
        config: dict[str, object] = {}
        if CONFIG_PATH.exists() and not args.recalibrate:
            config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            board_corners = config.get("board_corners", config.get("corners"))
            if board_corners is None:
                board_corners = calibrate_board(capture)
            phone_corners = config.get("phone_corners")
            if phone_corners is None:
                phone_corners = calibrate_phone(capture)
            bottom_clock_is_white = bool(config.get("bottom_clock_is_white", True))
            white_camera_edge = str(config.get("white_camera_edge", "bottom"))
            if white_camera_edge not in {"bottom", "top", "left", "right"}:
                white_camera_edge = "bottom"
        else:
            board_corners = calibrate_board(capture)
            phone_corners = calibrate_phone(capture)
            bottom_clock_is_white = True
            white_camera_edge = "bottom"
        configured_engine_path = (
            args.engine_path
            if args.engine_path is not None
            else config.get("engine_path")
        )
        stockfish_path = find_stockfish(
            str(configured_engine_path) if configured_engine_path else None
        )
        pinned_time_controls = normalize_pinned_time_controls(
            config.get("pinned_time_controls", DEFAULT_PINNED_TIME_CONTROLS)
        )
        player_name_usage = normalize_usage_counts(
            config.get("player_name_usage", {})
        )
        event_name_usage = normalize_usage_counts(
            config.get("event_name_usage", {})
        )

        profile_store = BoardProfileStore(PROFILE_DIRECTORY)
        profile_store.load()
        profile = profile_store.get(str(config.get("active_profile", "")))
        if profile is None:
            profile = profile_store.ensure_default(
                board_corners,
                phone_corners,
                white_camera_edge,
                bottom_clock_is_white,
            )
        if profile.board_corners is not None and not args.recalibrate:
            board_corners = profile.board_corners
        else:
            profile.board_corners = board_corners
        if profile.phone_corners is not None and not args.recalibrate:
            phone_corners = profile.phone_corners
        else:
            profile.phone_corners = phone_corners
        white_camera_edge = profile.white_camera_edge
        bottom_clock_is_white = profile.bottom_clock_is_white
        profile_store.save(profile)
        save_config(
            board_corners,
            phone_corners,
            bottom_clock_is_white,
            white_camera_edge,
            profile.name,
            stockfish_path,
            pinned_time_controls,
            player_name_usage,
            event_name_usage,
        )

        setup = GameSetup(
            bottom_clock_is_white=bottom_clock_is_white,
            white_camera_edge=white_camera_edge,
            profile_name=profile.name,
            profile_samples=profile.sample_count,
            learning_enabled=profile.learning_enabled,
            engine_name=stockfish_path.name if stockfish_path else "Auto-detect",
            pinned_time_controls=pinned_time_controls,
        )
        wizard_result = run_pregame_wizard(
            capture,
            setup,
            board_corners,
            phone_corners,
            profile,
            profile_store,
            stockfish_path,
            allow_cancel=False,
            player_name_usage=player_name_usage,
            event_name_usage=event_name_usage,
        )
        if wizard_result is None:
            return
        setup, board_corners, phone_corners, profile, stockfish_path = wizard_result
        bottom_clock_is_white = setup.bottom_clock_is_white

        board = chess.Board()
        moves: list[chess.Move] = []
        move_clocks: list[float | None] = []
        move_clock_tokens: list[int] = []
        next_clock_token = 1
        reference: np.ndarray | None = None
        previous: np.ndarray | None = None
        stable_since: float | None = None
        pending: list[RankedMove] = []
        pending_index = 0
        pending_frame: np.ndarray | None = None
        pending_event_time: float | None = None
        pending_scores: dict[chess.Square, float] = {}
        accuracy_frames: list[np.ndarray] = []
        accuracy_last_sample = 0.0
        auto_accept = setup.auto_accept
        fast_mode = setup.fast_mode
        bullet_mode = setup.bullet_mode
        accuracy_boost = setup.accuracy_boost
        clock_source = setup.clock_source
        manual_clock_switch = setup.manual_clock_switch
        builtin_settings = setup.clock_settings
        builtin_clock = BuiltInChessClock(builtin_settings)
        manual_clock = ManualClockController()
        illegal_warning = False
        illegal_clock_side: bool | None = None
        status = "Game starting. Make White's first move."
        start_pending = True
        last_accept_time = 0.0
        last_clock_request = 0.0
        latest_clocks: BothClocks | None = None
        clock_error: str | None = None
        active_clock_side: str | None = None
        last_active_clock_seen = 0.0
        bullet_capture_due: float | None = None
        clock_worker = BackgroundClockReader()
        game_buttons: list[Button] = []
        game_click_queue: list[str] = []
        game_result = "*"
        game_finished = False
        game_review: GameReview | None = None
        last_auto_move: chess.Move | None = None
        last_auto_scores: dict[chess.Square, float] = {}
        last_auto_frame: np.ndarray | None = None
        last_auto_event_time: float | None = None
        auto_correction_pending = False
        correction_clock_value: float | None = None
        dismissed_draw_claims: set[str] = set()
        fps_sample_started = time.monotonic()
        fps_sample_frames = 0
        display_fps = 0.0

        def collect_clock_results() -> None:
            nonlocal latest_clocks, clock_error
            clock_updated = False
            for result in clock_worker.poll():
                if result.error is not None:
                    clock_error = result.error
                    continue
                if result.clocks is None:
                    continue
                latest_clocks = result.clocks
                clock_error = None
                if (
                    isinstance(result.tag, tuple)
                    and len(result.tag) == 6
                    and result.tag[0] == "move"
                ):
                    _, move_index, token, player_is_white, mapping, _captured_at = (
                        result.tag
                    )
                    if (
                        isinstance(move_index, int)
                        and 0 <= move_index < len(move_clock_tokens)
                        and move_clock_tokens[move_index] == token
                    ):
                        move_clocks[move_index] = clock_for_player(
                            result.clocks, bool(player_is_white), bool(mapping)
                        )
                        clock_updated = True
            if clock_updated:
                save_game(
                    moves,
                    move_clocks,
                    setup.pgn_headers(),
                    game_result,
                )

        def finish_game(outcome: GameOutcome, event_time: float) -> None:
            nonlocal game_result, game_finished, status
            game_result = outcome.result
            game_finished = True
            if clock_source == "builtin":
                builtin_clock.pause(event_time)
            status = outcome.message
            save_game(
                moves,
                move_clocks,
                setup.pgn_headers(),
                game_result,
            )
            show_result_popup(outcome.title, outcome.message)

        def evaluate_position(event_time: float) -> bool:
            nonlocal status
            outcome = automatic_outcome(board)
            if outcome is not None:
                finish_game(outcome, event_time)
                return True

            reasons = [
                reason
                for reason in claimable_draw_reasons(board)
                if reason not in dismissed_draw_claims
            ]
            if not reasons:
                return False
            if clock_source == "builtin":
                builtin_clock.pause(event_time)
            for reason in reasons:
                accepted = ask_both_players_for_draw(
                    reason,
                    setup.white_name,
                    setup.black_name,
                )
                if accepted:
                    finish_game(
                        GameOutcome(
                            "1/2-1/2",
                            reason,
                            f"Draw agreed by both players under the {reason.lower()}.",
                        ),
                        time.monotonic(),
                    )
                    return True
                dismissed_draw_claims.add(reason)
                status = f"{reason} draw declined. The game continues."
            if clock_source == "builtin":
                builtin_clock.start(time.monotonic(), board.turn)
            return True

        cv2.namedWindow("Chess Camera PGN", cv2.WINDOW_NORMAL)

        def on_game_mouse(
            event: int, x: int, y: int, _flags: int, _data: object
        ) -> None:
            if event != cv2.EVENT_LBUTTONUP:
                return
            action = clicked_action(game_buttons, x, y)
            if action is not None:
                game_click_queue.append(action)

        cv2.setMouseCallback("Chess Camera PGN", on_game_mouse)

        while True:
            ok, raw = capture.read()
            if not ok:
                continue
            warped = orient_board_image(
                warp_board(raw, board_corners),
                setup.white_camera_edge,
            )
            now = time.monotonic()
            fps_sample_frames += 1
            fps_elapsed = now - fps_sample_started
            if fps_elapsed >= 0.5:
                display_fps = fps_sample_frames / fps_elapsed
                fps_sample_started = now
                fps_sample_frames = 0

            if start_pending:
                game_review = None
                board.reset()
                moves.clear()
                move_clocks.clear()
                move_clock_tokens.clear()
                reference = warped.copy()
                previous = warped.copy()
                pending.clear()
                pending_frame = None
                pending_event_time = None
                pending_scores.clear()
                accuracy_frames.clear()
                manual_clock.reset()
                illegal_warning = False
                illegal_clock_side = None
                game_result = "*"
                game_finished = False
                last_auto_move = None
                last_auto_scores.clear()
                last_auto_frame = None
                last_auto_event_time = None
                auto_correction_pending = False
                correction_clock_value = None
                dismissed_draw_claims.clear()
                builtin_clock.reset(builtin_settings)
                if clock_source == "builtin":
                    builtin_clock.start(now, white_to_move=True)
                save_game(
                    moves,
                    move_clocks,
                    setup.pgn_headers(),
                    game_result,
                )
                last_accept_time = now
                stable_since = None
                status = (
                    "Game started with the built-in clock."
                    if clock_source == "builtin"
                    else "Game started with Lichess OCR."
                )
                start_pending = False

            collect_clock_results()
            if clock_source == "builtin" and not game_finished:
                flagged_white = builtin_clock.flagged_player(now)
                if flagged_white is not None:
                    finish_game(
                        timeout_outcome(
                            flagged_white,
                            setup.white_name,
                            setup.black_name,
                        ),
                        now,
                    )
                    continue
            if (
                clock_source == "ocr"
                and
                now - last_clock_request >= CLOCK_PREVIEW_INTERVAL
                and clock_worker.submit_periodic(raw, phone_corners)
            ):
                last_clock_request = now

            if bullet_mode and clock_source == "ocr":
                detected_side = detect_active_clock_side(raw, phone_corners)
                if detected_side is not None:
                    last_active_clock_seen = now
                    if (
                        active_clock_side is not None
                        and detected_side != active_clock_side
                    ):
                        bullet_capture_due = now + BULLET_SWITCH_SETTLE_SECONDS
                    active_clock_side = detected_side

            if previous is not None:
                motion = frame_motion_score(previous, warped)
                if motion < 1.6:
                    stable_since = stable_since or now
                else:
                    stable_since = None
                    accuracy_frames.clear()
                    if not pending and not illegal_warning:
                        status = "Waiting for hands and pieces to stop moving..."
            previous = warped.copy()

            (
                detection_mode_name,
                stable_requirement,
                accept_cooldown,
            ) = detection_profile(
                fast_mode,
                bullet_mode,
            )
            stability_ready = (
                stable_since is not None
                and now - stable_since >= stable_requirement
            )
            stability_progress = (
                min(1.0, max(0.0, (now - stable_since) / stable_requirement))
                if stable_since is not None
                else 0.0
            )
            clock_boundary_ready = (
                bullet_mode
                and bullet_capture_due is not None
                and now >= bullet_capture_due
            )
            clock_side_available = (
                bullet_mode
                and clock_source == "ocr"
                and now - last_active_clock_seen < 0.5
            )
            if illegal_warning:
                # Always allow a stable restored board to clear the warning.
                analysis_ready = stability_ready
            else:
                analysis_ready = (
                    clock_boundary_ready
                    if bullet_mode and clock_side_available
                    else stability_ready
                )
            scores: dict[int, float] = {}
            raw_scores: dict[int, float] = {}
            if (
                reference is not None
                and not pending
                and not game_finished
                and analysis_ready
                and now - last_accept_time >= accept_cooldown
            ):
                analysis_event_time = (
                    max(0.0, now - BULLET_SWITCH_SETTLE_SECONDS)
                    if clock_boundary_ready
                    else (stable_since if stable_since is not None else now)
                )
                if clock_boundary_ready:
                    bullet_capture_due = None
                consensus_result = None
                analysis_deferred = False
                if accuracy_boost and not illegal_warning:
                    if now - accuracy_last_sample >= ACCURACY_SAMPLE_INTERVAL:
                        accuracy_frames.append(warped.copy())
                        accuracy_last_sample = now
                    if len(accuracy_frames) < ACCURACY_FRAME_COUNT:
                        status = (
                            "Accuracy Boost: checking stable frame "
                            f"{len(accuracy_frames)}/{ACCURACY_FRAME_COUNT}..."
                        )
                        analysis_deferred = True
                        scores = {}
                    else:
                        consensus_result = analyze_frame_consensus(
                            board,
                            reference,
                            accuracy_frames[:ACCURACY_FRAME_COUNT],
                            LEGAL_FIT_THRESHOLD,
                        )
                        accuracy_frames.clear()
                        scores = consensus_result.scores
                else:
                    scores = square_change_scores(reference, warped)
                raw_scores = scores.copy()
                if profile.learning_enabled:
                    scores = profile.adjusted_scores(scores)
                strongest_change = max(scores.values(), default=0.0)

                if analysis_deferred:
                    pass
                elif illegal_warning:
                    if board_looks_restored(scores):
                        illegal_warning = False
                        if clock_source == "builtin":
                            resume_clock_after_illegal_move(
                                builtin_clock,
                                illegal_clock_side,
                                now,
                            )
                        illegal_clock_side = None
                        stable_since = None
                        status = (
                            "Board restored. Clock resumed; you may now "
                            "play a legal move."
                            if clock_source == "builtin"
                            else "Board restored. You may now play a legal move."
                        )
                elif (
                    consensus_result is not None
                    and consensus_result.move is None
                    and (
                        consensus_result.valid_votes > 0
                        or consensus_result.ambiguous
                    )
                ):
                    stable_since = None
                    status = (
                        "Camera reading was ambiguous. Keep the board still; "
                        "Accuracy Boost is trying again."
                    )
                elif strongest_change >= MIN_CHANGE:
                    ranked_moves = (
                        rank_legal_moves(
                            board,
                            scores,
                            profile.learned_patterns()
                            if profile.learning_enabled
                            else None,
                            profile.learned_rejections()
                            if profile.learning_enabled
                            else None,
                        )
                    )
                    if (
                        consensus_result is not None
                        and consensus_result.move is not None
                    ):
                        ranked_moves.sort(
                            key=lambda candidate: (
                                candidate.move != consensus_result.move
                            )
                        )
                    best_fit = (
                        legal_move_fit(ranked_moves[0], scores) if ranked_moves else None
                    )
                    if best_fit is None or best_fit.score < LEGAL_FIT_THRESHOLD:
                        if clock_source == "builtin":
                            illegal_clock_side = pause_clock_for_illegal_move(
                                builtin_clock,
                                manual_clock,
                                now,
                            )
                        illegal_warning = True
                        pending.clear()
                        pending_frame = None
                        pending_event_time = None
                        pending_scores.clear()
                        status = (
                            "Illegal move detected. Return every changed piece "
                            "to the last legal position. "
                            + (
                                "The clock is paused."
                                if clock_source == "builtin"
                                else "Pause the Lichess clock on the phone."
                            )
                        )
                        stable_since = None
                        continue_detection = False
                    else:
                        illegal_warning = False
                        pending = ranked_moves[:8]
                        continue_detection = True

                    if not continue_detection:
                        # Rendering continues below so the red warning appears.
                        pass
                    else:
                        pending_index = 0
                        pending_frame = (
                            consensus_result.frame.copy()
                            if consensus_result is not None
                            else warped.copy()
                        )
                        pending_event_time = analysis_event_time
                        pending_scores = raw_scores.copy()
                        confidence = (
                            consensus_result.confidence
                            if consensus_result is not None
                            else confidence_for(pending, scores)
                        )
                        if pending:
                            candidate = pending[0].move
                            if candidate.promotion is not None:
                                chosen_piece = choose_promotion_piece()
                                pending = select_promotion_candidate(
                                    pending, chosen_piece
                                )
                                candidate = pending[0].move
                            status = (
                                f"Candidate: {board.san(candidate)} "
                                f"(confidence {confidence:.0%}). ENTER accepts; arrows change."
                            )
                            manual_clock_ready = (
                                clock_source != "builtin"
                                or not manual_clock_switch
                                or manual_clock.ready_for(board.turn)
                            )
                            if not manual_clock_ready:
                                status = (
                                    f"Candidate: {board.san(candidate)}. "
                                    f"Press {'A' if board.turn else 'L'} for "
                                    f"{'White' if board.turn else 'Black'}."
                                )
                            should_auto_accept = bullet_mode or (
                                auto_accept and confidence >= AUTO_CONFIDENCE
                            )
                            should_auto_accept = (
                                should_auto_accept and manual_clock_ready
                            )
                            if should_auto_accept:
                                move_index = len(moves)
                                token = next_clock_token
                                next_clock_token += 1
                                move_clock_tokens.append(token)
                                event_time = pending_event_time or now
                                if clock_source == "ocr":
                                    move_clocks.append(None)
                                    clock_worker.submit_move(
                                        raw,
                                        phone_corners,
                                        (
                                            "move",
                                            move_index,
                                            token,
                                            board.turn,
                                            bottom_clock_is_white,
                                            event_time,
                                        ),
                                    )
                                else:
                                    if manual_clock_switch:
                                        move_clocks.append(
                                            manual_clock.consume(board.turn)
                                        )
                                    else:
                                        move_clocks.append(
                                            builtin_clock.complete_move(
                                                board.turn, event_time
                                            )
                                        )
                                if (
                                    not bullet_mode
                                    and confidence >= AUTO_CONFIDENCE
                                ):
                                    profile.observe_move(
                                        candidate,
                                        pending_scores,
                                        pending[0].expected_squares,
                                    )
                                    profile_store.save(profile)
                                board.push(candidate)
                                moves.append(candidate)
                                last_auto_move = candidate
                                last_auto_scores = pending_scores.copy()
                                last_auto_frame = pending_frame.copy()
                                last_auto_event_time = event_time
                                auto_correction_pending = False
                                correction_clock_value = None
                                outcome_time = (
                                    now
                                    if clock_source == "builtin"
                                    and manual_clock_switch
                                    else event_time
                                )
                                position_notice = evaluate_position(outcome_time)
                                reference = pending_frame.copy()
                                pending.clear()
                                pending_frame = None
                                pending_event_time = None
                                pending_scores.clear()
                                accuracy_frames.clear()
                                save_game(
                                    moves,
                                    move_clocks,
                                    setup.pgn_headers(),
                                    game_result,
                                )
                                last_accept_time = now
                                stable_since = None
                                prefix = (
                                    "Bullet-recorded"
                                    if bullet_mode
                                    else (
                                        "Fast-recorded"
                                        if fast_mode
                                        else "Auto-recorded"
                                    )
                                )
                                if not game_finished and not position_notice:
                                    status = f"{prefix} {format_moves(moves)}"

            selected = pending[pending_index] if pending else None
            highlighted = set(selected.expected_squares) if selected else set()
            board_view = draw_grid(warped, highlighted)
            virtual_view = render_virtual_board(
                board, moves[-1] if moves else None
            )

            panel = np.zeros((620, INFO_PANEL_WIDTH, 3), dtype=np.uint8)
            panel[:] = (31, 34, 40)
            put_text(
                panel,
                setup.event_name[:36] or "Camera-recorded game",
                (22, 32),
                (100, 220, 255),
                0.68,
            )
            put_text(panel, setup.white_name[:28] or "White", (22, 72), scale=0.58)
            put_text(panel, setup.black_name[:28] or "Black", (250, 72), scale=0.58)

            white_clock_text = "--:--"
            black_clock_text = "--:--"
            if clock_source == "builtin":
                white_clock_text = format_display_clock(
                    builtin_clock.remaining(True, now)
                )
                black_clock_text = format_display_clock(
                    builtin_clock.remaining(False, now)
                )
            elif latest_clocks is not None:
                white_reading = (
                    latest_clocks.bottom
                    if bottom_clock_is_white
                    else latest_clocks.top
                )
                black_reading = (
                    latest_clocks.top
                    if bottom_clock_is_white
                    else latest_clocks.bottom
                )
                if white_reading.seconds is not None:
                    white_clock_text = format_display_clock(white_reading.seconds)
                if black_reading.seconds is not None:
                    black_clock_text = format_display_clock(black_reading.seconds)

            active_color = (120, 255, 170)
            idle_color = (185, 190, 200)
            display_active_white = (
                builtin_clock.active_white
                if clock_source == "builtin"
                and builtin_clock.active_white is not None
                else board.turn
            )
            put_text(
                panel,
                white_clock_text,
                (22, 130),
                active_color if display_active_white else idle_color,
                1.45,
            )
            put_text(
                panel,
                black_clock_text,
                (250, 130),
                active_color if not display_active_white else idle_color,
                1.45,
            )

            if bullet_mode:
                put_text(
                    panel,
                    "BULLET - LOWER ACCURACY",
                    (22, 172),
                    (0, 165, 255),
                    0.51,
                )
            else:
                put_text(
                    panel,
                    f"{detection_mode_name} | "
                    f"{'AUTO' if auto_accept else 'MANUAL'}"
                    f"{' | ACC' if accuracy_boost else ''}",
                    (22, 172),
                    (120, 255, 170) if fast_mode else (175, 185, 200),
                    0.51,
                )
            source_label = (
                (
                    "BUILT-IN | A/L KEYS"
                    if manual_clock_switch
                    else "BUILT-IN | CAMERA SWITCH"
                )
                if clock_source == "builtin"
                else "LICHESS OCR CLOCK"
            )
            if auto_correction_pending:
                source_label = "MANUAL CORRECTION - AUTO NEXT MOVE"
            put_text(panel, source_label, (260, 172), (120, 220, 255), 0.46)

            if game_finished:
                put_text(
                    panel,
                    f"GAME OVER  {game_result}",
                    (22, 213),
                    (80, 120, 255),
                    0.68,
                )
            elif selected:
                put_text(
                    panel,
                    f"Selected: {board.san(selected.move)} [{selected.move.uci()}]",
                    (22, 213),
                    (80, 255, 120),
                    0.64,
                )
                put_text(
                    panel,
                    f"Choice {pending_index + 1}/{len(pending)}",
                    (360, 213),
                    scale=0.45,
                )
            else:
                put_text(
                    panel,
                    f"{'White' if board.turn else 'Black'} to move",
                    (22, 213),
                    active_color,
                    0.62,
                )

            put_text(panel, "Moves", (22, 252), (100, 220, 255), 0.62)
            history = move_history_lines(moves)
            if history:
                for row, line in enumerate(history):
                    put_text(panel, line, (24, 280 + row * 27), scale=0.52)
            else:
                put_text(panel, "No moves recorded yet", (24, 280), (155, 165, 180), 0.5)

            cv2.line(panel, (20, 535), (460, 535), (75, 80, 90), 1)
            draw_wrapped_text(panel, status, 22, 562, 48, max_lines=2)
            if clock_source == "ocr" and clock_error:
                put_text(panel, "OCR unavailable", (330, 605), (80, 80, 255), 0.43)
            elif clock_source == "ocr" and clock_worker.busy:
                put_text(panel, "OCR reading...", (340, 605), (120, 220, 255), 0.43)

            camera_panel = render_camera_panel(
                board_view,
                detection_mode_name,
                display_fps,
                stability_progress,
                fast_mode,
            )

            combined = np.hstack([virtual_view, panel, camera_panel])
            button_x = VIRTUAL_VIEW_WIDTH + INFO_PANEL_WIDTH + 12
            button_y = GAME_BUTTON_Y_OFFSET
            game_buttons = [
                Button(
                    "adjust_clocks",
                    "Adjust clocks",
                    button_x,
                    252 + button_y,
                    132,
                    34,
                    enabled=(
                        clock_source == "builtin"
                        and not game_finished
                        and manual_clock.pending is None
                        and not illegal_warning
                    ),
                ),
                Button(
                    "wrong_detection",
                    "Detection wrong",
                    button_x + 144,
                    252 + button_y,
                    132,
                    34,
                    active=last_auto_move is not None,
                    enabled=(
                        last_auto_move is not None
                        and bool(moves)
                        and moves[-1] == last_auto_move
                        and not auto_correction_pending
                    ),
                ),
                Button("accept", "ACCEPT MOVE", button_x, 298 + button_y, 276, 38, active=bool(pending) and not game_finished, enabled=bool(pending) and not game_finished),
                Button("previous", "Previous", button_x, 344 + button_y, 132, 34, enabled=bool(pending) and not game_finished),
                Button("next", "Next", button_x + 144, 344 + button_y, 132, 34, enabled=bool(pending) and not game_finished),
                Button("promote_q", "Queen", button_x, 386 + button_y, 132, 32, enabled=bool(pending) and not game_finished),
                Button("promote_r", "Rook", button_x + 144, 386 + button_y, 132, 32, enabled=bool(pending) and not game_finished),
                Button("promote_b", "Bishop", button_x, 426 + button_y, 132, 32, enabled=bool(pending) and not game_finished),
                Button("promote_n", "Knight", button_x + 144, 426 + button_y, 132, 32, enabled=bool(pending) and not game_finished),
                Button("undo", "Undo", button_x, 466 + button_y, 132, 34, enabled=(bool(moves) or manual_clock.pending is not None) and not auto_correction_pending),
                Button("new_game", "New game", button_x + 144, 466 + button_y, 132, 34),
                Button("offer_draw", "Offer draw", button_x, 508 + button_y, 132, 34, enabled=not game_finished and manual_clock.pending is None),
                Button("resign", "Resign", button_x + 144, 508 + button_y, 132, 34, enabled=not game_finished and manual_clock.pending is None),
                Button(
                    "review",
                    "Review game",
                    button_x,
                    552 + button_y,
                    132,
                    34,
                    active=game_finished and bool(moves),
                    enabled=game_finished and bool(moves),
                ),
                Button("quit", "Finish & save", button_x + 144, 552 + button_y, 132, 34),
            ]
            if illegal_warning:
                game_buttons.append(
                    illegal_warning_button(combined.shape[1], combined.shape[0])
                )
            for game_button in game_buttons:
                draw_button(combined, game_button)
            if illegal_warning:
                combined = draw_illegal_warning(combined)
            cv2.imshow("Chess Camera PGN", combined)
            key = cv2.waitKey(1) & 0xFF
            click_action = game_click_queue.pop(0) if game_click_queue else None
            key_for_action = {
                "accept": 13,
                "previous": ord(","),
                "next": ord("."),
                "promote_q": ord("q"),
                "promote_r": ord("r"),
                "promote_b": ord("b"),
                "promote_n": ord("n"),
                "undo": ord("u"),
                "new_game": ord("s"),
                "quit": 27,
            }
            if click_action in key_for_action:
                key = key_for_action[click_action]

            if illegal_warning and (
                click_action == "dismiss_illegal" or key in (27, ord("x"))
            ):
                # Manual recovery is for cases where the physical position has
                # been restored but camera noise prevents the automatic check.
                # Re-baseline on the current image without changing the logical
                # chess position or recording a move.
                reference = warped.copy()
                previous = warped.copy()
                stable_since = None
                accuracy_frames.clear()
                illegal_warning = False
                last_accept_time = now
                if clock_source == "builtin":
                    resume_clock_after_illegal_move(
                        builtin_clock,
                        illegal_clock_side,
                        now,
                    )
                illegal_clock_side = None
                status = (
                    "Illegal warning dismissed and camera resynchronized. "
                    "The clock resumed."
                    if clock_source == "builtin"
                    else
                    "Illegal warning dismissed and camera resynchronized."
                )
                continue

            if click_action == "wrong_detection" and last_auto_move is not None:
                rejected_move = last_auto_move
                removed_clock = move_clocks.pop()
                move_clock_tokens.pop()
                moves.pop()
                board.pop()
                game_result = "*"
                game_finished = False
                game_review = None
                dismissed_draw_claims.clear()
                profile.observe_rejection(
                    rejected_move,
                    last_auto_scores,
                    weight=3,
                )
                profile_store.save(profile)
                pending = manual_correction_candidates(
                    board,
                    last_auto_scores,
                    rejected_move,
                    profile,
                )
                pending_index = 0
                pending_frame = (
                    last_auto_frame.copy()
                    if last_auto_frame is not None
                    else warped.copy()
                )
                pending_event_time = last_auto_event_time or now
                pending_scores = last_auto_scores.copy()
                correction_clock_value = removed_clock
                auto_correction_pending = True
                if (
                    clock_source == "builtin"
                    and builtin_clock.active_white is None
                ):
                    # A false checkmate/draw popup may have paused the clock.
                    # The original move time is already preserved, so the
                    # opponent's clock should run during manual correction.
                    builtin_clock.start(now, not board.turn)
                last_auto_move = None
                last_auto_scores.clear()
                last_auto_frame = None
                last_auto_event_time = None
                accuracy_frames.clear()
                save_game(
                    moves,
                    move_clocks,
                    setup.pgn_headers(),
                    game_result,
                )
                stable_since = None
                status = (
                    "Automatic detection undone. Select the correct move "
                    "manually; automatic confirmation resumes next move."
                )
                continue

            if click_action == "adjust_clocks":
                resume_side = builtin_clock.active_white
                builtin_clock.pause(now)
                changed = adjust_builtin_clock(builtin_clock)
                if resume_side is not None:
                    builtin_clock.start(time.monotonic(), resume_side)
                cv2.namedWindow("Chess Camera PGN", cv2.WINDOW_NORMAL)
                cv2.setMouseCallback("Chess Camera PGN", on_game_mouse)
                status = (
                    "Clock adjustment saved; the correct player's clock resumed."
                    if changed
                    else "Clock adjustment cancelled; the game clock resumed."
                )
                continue

            if click_action == "review":
                if game_review is None:
                    game_review = create_post_game_review(moves, stockfish_path)
                if game_review is not None:
                    show_game_review(
                        game_review,
                        moves,
                        setup.white_name,
                        setup.black_name,
                    )
                    status = (
                        "Post-game review saved to games/latest_analysis.json."
                    )
                cv2.namedWindow("Chess Camera PGN", cv2.WINDOW_NORMAL)
                cv2.setMouseCallback("Chess Camera PGN", on_game_mouse)
                continue

            manual_key_player = manual_clock_player_for_key(key)
            if manual_key_player is not None:
                if clock_source != "builtin" or not manual_clock_switch:
                    status = (
                        "A/L clock keys are available in built-in "
                        "Player keys mode."
                    )
                    continue
                if game_finished:
                    status = "The game is already finished."
                    continue
                if illegal_warning:
                    status = (
                        "Restore the last legal position before pressing "
                        "a clock key."
                    )
                    continue
                if auto_correction_pending:
                    status = (
                        "The clock time is already preserved. Select the "
                        "correct move and press Enter."
                    )
                    continue
                if manual_clock.pending is not None:
                    status = (
                        "A clock press is already waiting for the camera move. "
                        "Press Undo to cancel it."
                    )
                    continue
                if manual_key_player != board.turn:
                    expected_key = "A" if board.turn else "L"
                    expected_player = "White" if board.turn else "Black"
                    status = (
                        f"Wrong clock key. {expected_player} must press "
                        f"{expected_key}."
                    )
                    continue
                manual_clock.press(builtin_clock, manual_key_player, now)
                status = (
                    f"{'White' if manual_key_player else 'Black'} clock stopped. "
                    "Waiting for the camera move."
                )
                if pending and (auto_accept or bullet_mode):
                    key = 13
                else:
                    continue
            if click_action == "offer_draw" and not game_finished:
                offering_white = board.turn == chess.WHITE
                offerer = (
                    setup.white_name if offering_white else setup.black_name
                ) or ("White" if offering_white else "Black")
                opponent = (
                    setup.black_name if offering_white else setup.white_name
                ) or ("Black" if offering_white else "White")
                if clock_source == "builtin":
                    builtin_clock.pause(now)
                accepted = ask_yes_no(
                    "Draw offer",
                    f"{offerer} offers a draw. {opponent}: Do you accept?",
                )
                if accepted:
                    finish_game(
                        GameOutcome(
                            "1/2-1/2",
                            "Draw agreed",
                            "The players agreed to a draw.",
                        ),
                        time.monotonic(),
                    )
                else:
                    if clock_source == "builtin":
                        builtin_clock.start(time.monotonic(), board.turn)
                    status = f"{opponent} declined the draw offer."
                continue
            if click_action == "resign" and not game_finished:
                resigning_white = board.turn == chess.WHITE
                resigner = (
                    setup.white_name if resigning_white else setup.black_name
                ) or ("White" if resigning_white else "Black")
                winner = (
                    setup.black_name if resigning_white else setup.white_name
                ) or ("Black" if resigning_white else "White")
                if clock_source == "builtin":
                    builtin_clock.pause(now)
                confirmed = ask_yes_no(
                    "Confirm resignation",
                    f"{resigner}: Are you sure you want to resign?",
                )
                if confirmed:
                    finish_game(
                        GameOutcome(
                            "0-1" if resigning_white else "1-0",
                            "Resignation",
                            f"{resigner} resigned. {winner} wins.",
                        ),
                        time.monotonic(),
                    )
                else:
                    if clock_source == "builtin":
                        builtin_clock.start(time.monotonic(), board.turn)
                    status = "Resignation cancelled."
                continue
            if key in (27, ord("x")):
                break
            if key in (
                ord("s"),
                ord("b"),
                ord("c"),
                ord("f"),
                ord("g"),
                ord("k"),
                ord("t"),
            ) and not (pending and key == ord("b")):
                resume_clock_side = builtin_clock.active_white
                if clock_source == "builtin":
                    builtin_clock.pause(now)
                wizard_result = run_pregame_wizard(
                    capture,
                    setup,
                    board_corners,
                    phone_corners,
                    profile,
                    profile_store,
                    stockfish_path,
                    allow_cancel=True,
                    player_name_usage=player_name_usage,
                    event_name_usage=event_name_usage,
                )
                cv2.namedWindow("Chess Camera PGN", cv2.WINDOW_NORMAL)
                cv2.setMouseCallback("Chess Camera PGN", on_game_mouse)
                if wizard_result is None:
                    if clock_source == "builtin" and resume_clock_side is not None:
                        builtin_clock.start(time.monotonic(), resume_clock_side)
                    status = "Setup cancelled. Current game resumed."
                else:
                    (
                        setup,
                        board_corners,
                        phone_corners,
                        profile,
                        stockfish_path,
                    ) = wizard_result
                    bottom_clock_is_white = setup.bottom_clock_is_white
                    auto_accept = setup.auto_accept
                    fast_mode = setup.fast_mode
                    bullet_mode = setup.bullet_mode
                    accuracy_boost = setup.accuracy_boost
                    clock_source = setup.clock_source
                    manual_clock_switch = setup.manual_clock_switch
                    builtin_settings = setup.clock_settings
                    builtin_clock.reset(builtin_settings)
                    manual_clock.reset()
                    latest_clocks = None
                    last_clock_request = 0.0
                    active_clock_side = None
                    last_active_clock_seen = 0.0
                    bullet_capture_due = None
                    accuracy_frames.clear()
                    previous = None
                    last_auto_move = None
                    last_auto_scores.clear()
                    last_auto_frame = None
                    last_auto_event_time = None
                    auto_correction_pending = False
                    correction_clock_value = None
                    start_pending = True
                    status = "Starting the configured game..."
            elif key == ord("u") and (moves or manual_clock.pending is not None):
                if manual_clock.pending is not None:
                    manual_clock.cancel(builtin_clock, now)
                    status = "Manual clock press cancelled."
                    continue

                moves.pop()
                move_clocks.pop()
                move_clock_tokens.pop()
                game_result = "*"
                game_finished = False
                last_auto_move = None
                last_auto_scores.clear()
                last_auto_frame = None
                last_auto_event_time = None
                auto_correction_pending = False
                correction_clock_value = None
                dismissed_draw_claims.clear()
                board.reset()
                for move in moves:
                    board.push(move)
                if clock_source == "builtin":
                    builtin_clock.undo(now)
                reference = warped.copy()
                pending.clear()
                pending_frame = None
                pending_event_time = None
                pending_scores.clear()
                accuracy_frames.clear()
                illegal_warning = False
                illegal_clock_side = None
                save_game(
                    moves,
                    move_clocks,
                    setup.pgn_headers(),
                    game_result,
                )
                last_accept_time = now
                status = "Last move removed. Board view resynchronized."
            elif pending and key in (81, 2424832, ord(",")):
                pending_index = (pending_index - 1) % len(pending)
                status = f"Selected {board.san(pending[pending_index].move)}."
            elif pending and key in (83, 2555904, ord(".")):
                pending_index = (pending_index + 1) % len(pending)
                status = f"Selected {board.san(pending[pending_index].move)}."
            elif pending and key in (ord("q"), ord("r"), ord("b"), ord("n")):
                piece_type = {
                    ord("q"): chess.QUEEN,
                    ord("r"): chess.ROOK,
                    ord("b"): chess.BISHOP,
                    ord("n"): chess.KNIGHT,
                }[key]
                original = pending[pending_index]
                promoted = move_with_promotion(original.move, piece_type)
                if promoted in board.legal_moves:
                    pending[pending_index] = RankedMove(
                        promoted, original.score, original.expected_squares
                    )
                    status = f"Promotion set to {chess.piece_name(piece_type)}."
            elif pending and key in (10, 13):
                selected_move = pending[pending_index].move
                if selected_move in board.legal_moves and pending_frame is not None:
                    was_auto_correction = auto_correction_pending
                    if (
                        clock_source == "builtin"
                        and manual_clock_switch
                        and not was_auto_correction
                        and not manual_clock.ready_for(board.turn)
                    ):
                        status = (
                            f"Press {'A' if board.turn else 'L'} for "
                            f"{'White' if board.turn else 'Black'} before "
                            "accepting the move."
                        )
                        continue
                    san = board.san(selected_move)
                    move_index = len(moves)
                    token = next_clock_token
                    next_clock_token += 1
                    move_clock_tokens.append(token)
                    event_time = pending_event_time or now
                    if clock_source == "ocr":
                        move_clocks.append(None)
                        clock_worker.submit_move(
                            raw,
                            phone_corners,
                            (
                                "move",
                                move_index,
                                token,
                                board.turn,
                                bottom_clock_is_white,
                                event_time,
                            ),
                        )
                    else:
                        if was_auto_correction:
                            move_clocks.append(correction_clock_value)
                        elif manual_clock_switch:
                            move_clocks.append(
                                manual_clock.consume(board.turn)
                            )
                        else:
                            move_clocks.append(
                                builtin_clock.complete_move(board.turn, event_time)
                            )
                    selected_pattern = pending[pending_index]
                    profile.observe_move(
                        selected_move,
                        pending_scores,
                        selected_pattern.expected_squares,
                        weight=(
                            4
                            if was_auto_correction
                            else (2 if pending_index != 0 else 1)
                        ),
                    )
                    profile_store.save(profile)
                    board.push(selected_move)
                    moves.append(selected_move)
                    last_auto_move = None
                    last_auto_scores.clear()
                    last_auto_frame = None
                    last_auto_event_time = None
                    auto_correction_pending = False
                    correction_clock_value = None
                    outcome_time = (
                        now
                        if was_auto_correction
                        or (
                            clock_source == "builtin"
                            and manual_clock_switch
                        )
                        else event_time
                    )
                    position_notice = evaluate_position(outcome_time)
                    reference = pending_frame.copy()
                    pending.clear()
                    pending_frame = None
                    pending_event_time = None
                    pending_scores.clear()
                    accuracy_frames.clear()
                    save_game(
                        moves,
                        move_clocks,
                        setup.pgn_headers(),
                        game_result,
                    )
                    last_accept_time = now
                    stable_since = None
                    if not game_finished and not position_notice:
                        status = f"Recorded {san}. Recent: {format_moves(moves)}"

        # Finish exact move-time captures before writing the final timestamped PGN.
        clock_worker.close()
        collect_clock_results()
        if moves or game_result != "*":
            timestamped = Path("games") / (
                datetime.now().strftime("game_%Y-%m-%d_%H-%M-%S") + ".pgn"
            )
            write_pgn(
                moves,
                timestamped,
                result=game_result,
                clocks=move_clocks,
                headers=setup.pgn_headers(),
            )
            print(f"Saved PGN to {OUTPUT_PATH} and {timestamped}")
    finally:
        if clock_worker is not None:
            clock_worker.close()
        capture.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
