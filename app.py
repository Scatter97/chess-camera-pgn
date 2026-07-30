from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import chess
import cv2
import numpy as np

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
    move_with_promotion,
    orient_board_image,
    rank_legal_moves,
    square_change_scores,
    warp_board,
    write_pgn,
)
from game_rules import GameOutcome, automatic_outcome, claimable_draw_reasons
from pregame_ui import (
    Button,
    GameSetup,
    apply_setup_action,
    clicked_action,
    draw_button,
    render_setup_screen,
    update_text_field,
)


CONFIG_PATH = Path("camera_config.json")
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
) -> None:
    CONFIG_PATH.write_text(
        json.dumps(
            {
                "board_corners": board_corners,
                "phone_corners": phone_corners,
                "bottom_clock_is_white": bottom_clock_is_white,
                "white_camera_edge": white_camera_edge,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


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


def render_virtual_board(
    board: chess.Board, last_move: chess.Move | None = None
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
        (width - 35, center_y + 105),
        (0, 0, 110),
        -1,
    )
    cv2.rectangle(
        view,
        (35, center_y - 115),
        (width - 35, center_y + 105),
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
    return view


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


def run_pregame_wizard(
    capture: cv2.VideoCapture,
    setup: GameSetup,
    board_corners: list[list[float]],
    phone_corners: list[list[float]],
    allow_cancel: bool,
) -> tuple[GameSetup, list[list[float]], list[list[float]]] | None:
    """Run the clickable game-settings step after camera calibration."""
    window = "Chess Camera - Step 2: Game Settings"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 1100, 820)
    current_buttons: list[Button] = []
    click_queue: list[str] = []
    focused_field: str | None = None
    message = ""

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
        preview = raw if ok else None
        screen, current_buttons = render_setup_screen(
            setup,
            focused_field,
            camera_preview=preview,
            message=message,
        )
        cv2.imshow(window, screen)
        key = cv2.waitKey(20) & 0xFF
        action = click_queue.pop(0) if click_queue else None

        if action in {"focus_white", "focus_black", "focus_event"}:
            focused_field = action.removeprefix("focus_")
            continue
        if action == "calibrate_board":
            focused_field = None
            board_corners = calibrate_board(capture)
            save_config(
                board_corners,
                phone_corners,
                setup.bottom_clock_is_white,
                setup.white_camera_edge,
            )
            message = "Board calibration updated."
            continue
        if action == "calibrate_phone":
            focused_field = None
            phone_corners = calibrate_phone(capture)
            save_config(
                board_corners,
                phone_corners,
                setup.bottom_clock_is_white,
                setup.white_camera_edge,
            )
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
        if action == "start" or (key in (10, 13) and focused_field is None):
            save_config(
                board_corners,
                phone_corners,
                setup.bottom_clock_is_white,
                setup.white_camera_edge,
            )
            cv2.destroyWindow(window)
            return setup, board_corners, phone_corners

        if action is not None:
            focused_field = None
            setup = apply_setup_action(setup, action)
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
        save_config(
            board_corners,
            phone_corners,
            bottom_clock_is_white,
            white_camera_edge,
        )

        setup = GameSetup(
            bottom_clock_is_white=bottom_clock_is_white,
            white_camera_edge=white_camera_edge,
        )
        wizard_result = run_pregame_wizard(
            capture,
            setup,
            board_corners,
            phone_corners,
            allow_cancel=False,
        )
        if wizard_result is None:
            return
        setup, board_corners, phone_corners = wizard_result
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
                board.reset()
                moves.clear()
                move_clocks.clear()
                move_clock_tokens.clear()
                reference = warped.copy()
                previous = warped.copy()
                pending.clear()
                pending_frame = None
                pending_event_time = None
                accuracy_frames.clear()
                manual_clock.reset()
                illegal_warning = False
                illegal_clock_side = None
                game_result = "*"
                game_finished = False
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
                        consensus_result.ranked
                        if consensus_result is not None
                        else rank_legal_moves(board, scores)
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
                                board.push(candidate)
                                moves.append(candidate)
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

            camera_panel = np.zeros(
                (620, CAMERA_PANEL_WIDTH, 3), dtype=np.uint8
            )
            camera_panel[:] = (25, 28, 34)
            camera_preview = cv2.resize(board_view, (240, 240))
            camera_panel[:240, 30:270] = camera_preview
            cv2.rectangle(camera_panel, (30, 0), (269, 239), (115, 125, 142), 2)
            put_text(
                camera_panel,
                "SMALL CAMERA PREVIEW",
                (38, 24),
                (255, 255, 255),
                0.46,
            )
            put_text(
                camera_panel,
                f"{detection_mode_name} | {display_fps:.1f} FPS",
                (38, 47),
                (120, 255, 170) if fast_mode else (120, 220, 255),
                0.39,
            )
            cv2.rectangle(camera_panel, (38, 55), (262, 63), (20, 20, 20), -1)
            progress_width = int(224 * stability_progress)
            if progress_width:
                cv2.rectangle(
                    camera_panel,
                    (38, 55),
                    (38 + progress_width, 63),
                    (80, 220, 120),
                    -1,
                )

            combined = np.hstack([virtual_view, panel, camera_panel])
            button_x = VIRTUAL_VIEW_WIDTH + INFO_PANEL_WIDTH + 12
            if clock_source == "builtin" and manual_clock_switch:
                clock_key_label = (
                    "CLOCK PRESSED - WAITING"
                    if manual_clock.pending is not None
                    else "A: WHITE CLOCK | L: BLACK CLOCK"
                )
                put_text(
                    combined,
                    clock_key_label,
                    (button_x + 7, 270),
                    (80, 220, 255),
                    0.42,
                )
            game_buttons = [
                Button("accept", "ACCEPT MOVE", button_x, 298, 276, 38, active=bool(pending) and not game_finished, enabled=bool(pending) and not game_finished),
                Button("previous", "Previous", button_x, 344, 132, 34, enabled=bool(pending) and not game_finished),
                Button("next", "Next", button_x + 144, 344, 132, 34, enabled=bool(pending) and not game_finished),
                Button("promote_q", "Queen", button_x, 386, 132, 32, enabled=bool(pending) and not game_finished),
                Button("promote_r", "Rook", button_x + 144, 386, 132, 32, enabled=bool(pending) and not game_finished),
                Button("promote_b", "Bishop", button_x, 426, 132, 32, enabled=bool(pending) and not game_finished),
                Button("promote_n", "Knight", button_x + 144, 426, 132, 32, enabled=bool(pending) and not game_finished),
                Button("undo", "Undo", button_x, 466, 132, 34, enabled=bool(moves) or manual_clock.pending is not None),
                Button("new_game", "New game", button_x + 144, 466, 132, 34),
                Button("offer_draw", "Offer draw", button_x, 508, 132, 34, enabled=not game_finished and manual_clock.pending is None),
                Button("resign", "Resign", button_x + 144, 508, 132, 34, enabled=not game_finished and manual_clock.pending is None),
                Button("quit", "Finish & save", button_x, 552, 276, 30),
            ]
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
                    allow_cancel=True,
                )
                cv2.namedWindow("Chess Camera PGN", cv2.WINDOW_NORMAL)
                cv2.setMouseCallback("Chess Camera PGN", on_game_mouse)
                if wizard_result is None:
                    if clock_source == "builtin" and resume_clock_side is not None:
                        builtin_clock.start(time.monotonic(), resume_clock_side)
                    status = "Setup cancelled. Current game resumed."
                else:
                    setup, board_corners, phone_corners = wizard_result
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
                    if (
                        clock_source == "builtin"
                        and manual_clock_switch
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
                        if manual_clock_switch:
                            move_clocks.append(
                                manual_clock.consume(board.turn)
                            )
                        else:
                            move_clocks.append(
                                builtin_clock.complete_move(board.turn, event_time)
                            )
                    board.push(selected_move)
                    moves.append(selected_move)
                    outcome_time = (
                        now
                        if clock_source == "builtin" and manual_clock_switch
                        else event_time
                    )
                    position_notice = evaluate_position(outcome_time)
                    reference = pending_frame.copy()
                    pending.clear()
                    pending_frame = None
                    pending_event_time = None
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
