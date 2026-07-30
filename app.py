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

from clock_reader import BackgroundClockReader, BothClocks, format_pgn_clock
from chess_tracker import (
    BOARD_PIXELS,
    RankedMove,
    confidence_for,
    legal_move_fit,
    move_with_promotion,
    rank_legal_moves,
    square_change_scores,
    warp_board,
    write_pgn,
)


CONFIG_PATH = Path("camera_config.json")
OUTPUT_PATH = Path("games/latest_game.pgn")
STABLE_SECONDS = 1.15
AUTO_CONFIDENCE = 0.73
MIN_CHANGE = 7.0
LEGAL_FIT_THRESHOLD = 0.66
RETURNED_BOARD_THRESHOLD = 5.2
CLOCK_PREVIEW_INTERVAL = 1.5


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
        ["a8 corner", "h8 corner", "h1 corner", "a1 corner"],
        "White must be nearest the camera. Keep the whole board and phone visible.",
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
) -> None:
    CONFIG_PATH.write_text(
        json.dumps(
            {
                "board_corners": board_corners,
                "phone_corners": phone_corners,
                "bottom_clock_is_white": bottom_clock_is_white,
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
        x0, y0 = file_index * cell, rank_from_top * cell
        cv2.rectangle(
            overlay, (x0, y0), (x0 + cell, y0 + cell), (0, 215, 255), -1
        )
    if highlighted:
        view = cv2.addWeighted(overlay, 0.26, view, 0.74, 0)

    for index in range(9):
        value = index * cell
        cv2.line(view, (value, 0), (value, BOARD_PIXELS), (255, 255, 255), 1)
        cv2.line(view, (0, value), (BOARD_PIXELS, value), (255, 255, 255), 1)
    return view


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


def save_game(moves: list[chess.Move], clocks: list[float | None]) -> None:
    write_pgn(moves, OUTPUT_PATH, clocks=clocks)


def reading_label(reading: object) -> str:
    seconds = getattr(reading, "seconds", None)
    confidence = getattr(reading, "confidence", 0.0)
    if seconds is None:
        return "--:--"
    return f"{format_pgn_clock(seconds)} ({confidence:.0%})"


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
        else:
            board_corners = calibrate_board(capture)
            phone_corners = calibrate_phone(capture)
            bottom_clock_is_white = True
        save_config(board_corners, phone_corners, bottom_clock_is_white)

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
        auto_accept = False
        illegal_warning = False
        status = "Place all pieces in the starting position, then press S."
        last_accept_time = 0.0
        last_clock_request = 0.0
        latest_clocks: BothClocks | None = None
        clock_error: str | None = None
        clock_worker = BackgroundClockReader()

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
                save_game(moves, move_clocks)

        cv2.namedWindow("Chess Camera PGN", cv2.WINDOW_NORMAL)

        while True:
            ok, raw = capture.read()
            if not ok:
                continue
            warped = warp_board(raw, board_corners)
            now = time.monotonic()

            collect_clock_results()
            if (
                now - last_clock_request >= CLOCK_PREVIEW_INTERVAL
                and clock_worker.submit_periodic(raw, phone_corners)
            ):
                last_clock_request = now

            if previous is not None:
                motion = float(
                    np.mean(
                        cv2.absdiff(
                            cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY),
                            cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY),
                        )
                    )
                )
                if motion < 1.6:
                    stable_since = stable_since or now
                else:
                    stable_since = None
                    if not pending:
                        status = "Waiting for hands and pieces to stop moving..."
            previous = warped.copy()

            scores: dict[int, float] = {}
            if (
                reference is not None
                and not pending
                and stable_since is not None
                and now - stable_since >= STABLE_SECONDS
                and now - last_accept_time >= 1.0
            ):
                scores = square_change_scores(reference, warped)
                strongest_change = max(scores.values(), default=0.0)

                if illegal_warning and strongest_change < RETURNED_BOARD_THRESHOLD:
                    illegal_warning = False
                    stable_since = None
                    status = "Board restored. You may now play a legal move."
                elif strongest_change >= MIN_CHANGE:
                    ranked_moves = rank_legal_moves(board, scores)
                    best_fit = (
                        legal_move_fit(ranked_moves[0], scores) if ranked_moves else None
                    )
                    if best_fit is None or best_fit.score < LEGAL_FIT_THRESHOLD:
                        illegal_warning = True
                        pending.clear()
                        pending_frame = None
                        status = (
                            "Illegal move detected. Return every changed piece "
                            "to the last legal position."
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
                        pending_frame = warped.copy()
                        confidence = confidence_for(pending, scores)
                        if pending:
                            candidate = pending[0].move
                            status = (
                                f"Candidate: {board.san(candidate)} "
                                f"(confidence {confidence:.0%}). ENTER accepts; arrows change."
                            )
                            if auto_accept and confidence >= AUTO_CONFIDENCE:
                                move_index = len(moves)
                                token = next_clock_token
                                next_clock_token += 1
                                move_clock_tokens.append(token)
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
                                        now,
                                    ),
                                )
                                board.push(candidate)
                                moves.append(candidate)
                                reference = pending_frame.copy()
                                pending.clear()
                                pending_frame = None
                                save_game(moves, move_clocks)
                                last_accept_time = now
                                stable_since = None
                                status = f"Auto-recorded {format_moves(moves)}"

            selected = pending[pending_index] if pending else None
            highlighted = set(selected.expected_squares) if selected else set()
            board_view = draw_grid(warped, highlighted)
            board_view = cv2.resize(board_view, (620, 620))

            panel = np.zeros((620, 500, 3), dtype=np.uint8)
            panel[:] = (31, 34, 40)
            put_text(panel, "Physical Chess to PGN", (25, 40), (100, 220, 255), 0.85)
            put_text(panel, f"Turn: {'White' if board.turn else 'Black'}", (25, 82))
            put_text(panel, f"Moves: {len(moves)}", (25, 112))
            put_text(panel, f"Auto accept: {'ON' if auto_accept else 'OFF'}", (25, 142))
            if latest_clocks is not None:
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
                put_text(
                    panel,
                    f"White clock: {reading_label(white_reading)}",
                    (25, 172),
                    (120, 220, 255),
                    0.56,
                )
                put_text(
                    panel,
                    f"Black clock: {reading_label(black_reading)}",
                    (25, 198),
                    (120, 220, 255),
                    0.56,
                )
            else:
                put_text(panel, "Clocks: reading phone...", (25, 172), scale=0.56)
            mapping = "bottom=White" if bottom_clock_is_white else "top=White"
            put_text(panel, f"Clock mapping: {mapping}", (25, 224), scale=0.52)

            if selected:
                put_text(
                    panel,
                    f"Selected: {board.san(selected.move)} [{selected.move.uci()}]",
                    (25, 263),
                    (80, 255, 120),
                    0.72,
                )
                put_text(
                    panel,
                    f"Choice {pending_index + 1}/{len(pending)}",
                    (25, 292),
                    scale=0.58,
                )

            y = 330
            words = status.split()
            line = ""
            for word in words:
                if len(line) + len(word) > 47:
                    put_text(panel, line, (25, y), scale=0.56)
                    y += 27
                    line = word
                else:
                    line = f"{line} {word}".strip()
            if line:
                put_text(panel, line, (25, y), scale=0.56)

            if clock_error:
                put_text(panel, "Clock OCR unavailable", (25, 405), (80, 80, 255), 0.52)
            elif clock_worker.busy:
                put_text(panel, "Clock OCR: background", (25, 405), (120, 220, 255), 0.52)
            put_text(panel, "Controls", (25, 438), (100, 220, 255), 0.68)
            controls = [
                "ENTER accept | arrows candidate",
                "Q/R/B/N promotion | U undo",
                "A auto accept | S new game",
                "C calibrate all | K phone only",
                "F swap clock sides | ESC quit",
            ]
            for row, label in enumerate(controls):
                put_text(panel, label, (25, 470 + row * 27), scale=0.51)

            combined = np.hstack([board_view, panel])
            if illegal_warning:
                combined = draw_illegal_warning(combined)
            cv2.imshow("Chess Camera PGN", combined)
            key = cv2.waitKey(1) & 0xFF

            if key in (27, ord("x")):
                break
            if key == ord("c"):
                board_corners = calibrate_board(capture)
                phone_corners = calibrate_phone(capture)
                save_config(board_corners, phone_corners, bottom_clock_is_white)
                reference = None
                previous = None
                pending.clear()
                illegal_warning = False
                status = "Calibration saved. Press S with pieces at the start."
            elif key == ord("k"):
                phone_corners = calibrate_phone(capture)
                save_config(board_corners, phone_corners, bottom_clock_is_white)
                latest_clocks = None
                last_clock_request = 0.0
                status = "Phone calibration saved."
            elif key == ord("f"):
                bottom_clock_is_white = not bottom_clock_is_white
                save_config(board_corners, phone_corners, bottom_clock_is_white)
                status = (
                    "Clock sides swapped. "
                    + ("Bottom is White." if bottom_clock_is_white else "Top is White.")
                )
            elif key == ord("s"):
                board.reset()
                moves.clear()
                move_clocks.clear()
                move_clock_tokens.clear()
                reference = warped.copy()
                pending.clear()
                pending_frame = None
                illegal_warning = False
                save_game(moves, move_clocks)
                last_accept_time = now
                stable_since = None
                status = "Game started. Make White's first move."
            elif key == ord("a"):
                auto_accept = not auto_accept
                status = f"Automatic confirmation {'enabled' if auto_accept else 'disabled'}."
            elif key == ord("u") and moves:
                moves.pop()
                move_clocks.pop()
                move_clock_tokens.pop()
                board.reset()
                for move in moves:
                    board.push(move)
                reference = warped.copy()
                pending.clear()
                pending_frame = None
                illegal_warning = False
                save_game(moves, move_clocks)
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
                    san = board.san(selected_move)
                    move_index = len(moves)
                    token = next_clock_token
                    next_clock_token += 1
                    move_clock_tokens.append(token)
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
                            now,
                        ),
                    )
                    board.push(selected_move)
                    moves.append(selected_move)
                    reference = pending_frame.copy()
                    pending.clear()
                    pending_frame = None
                    save_game(moves, move_clocks)
                    last_accept_time = now
                    stable_since = None
                    status = f"Recorded {san}. Recent: {format_moves(moves)}"

        # Finish exact move-time captures before writing the final timestamped PGN.
        clock_worker.close()
        collect_clock_results()
        if moves:
            timestamped = Path("games") / (
                datetime.now().strftime("game_%Y-%m-%d_%H-%M-%S") + ".pgn"
            )
            write_pgn(moves, timestamped, clocks=move_clocks)
            print(f"Saved PGN to {OUTPUT_PATH} and {timestamped}")
    finally:
        if clock_worker is not None:
            clock_worker.close()
        capture.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
