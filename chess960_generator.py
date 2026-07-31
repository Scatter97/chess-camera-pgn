from __future__ import annotations

import random

import chess
import cv2
import numpy as np

import pregame_ui
import revision35 as base
import revision35_update as update
from pregame_ui import Button


WINDOW_NAME = "Chess Camera - Chess960 Position Generator"


def _new_position() -> tuple[int, chess.Board]:
    position_number = random.randrange(960)
    return position_number, chess.Board.from_chess960_pos(position_number)


def _piece_label(piece: chess.Piece) -> str:
    return piece.symbol().upper()


def _render_board(board: chess.Board, size: int = 560) -> np.ndarray:
    square_size = size // 8
    board_size = square_size * 8
    image = np.zeros((board_size, board_size, 3), dtype=np.uint8)

    light = (210, 220, 225)
    dark = (95, 120, 135)
    white_piece = (245, 245, 245)
    black_piece = (35, 38, 44)

    for display_rank in range(8):
        rank = 7 - display_rank
        for file_index in range(8):
            x1 = file_index * square_size
            y1 = display_rank * square_size
            x2 = x1 + square_size
            y2 = y1 + square_size
            color = light if (file_index + rank) % 2 else dark
            cv2.rectangle(image, (x1, y1), (x2, y2), color, -1)

            square = chess.square(file_index, rank)
            piece = board.piece_at(square)
            if piece is None:
                continue

            label = _piece_label(piece)
            scale = 1.25
            thickness = 3
            (text_width, text_height), _ = cv2.getTextSize(
                label,
                cv2.FONT_HERSHEY_SIMPLEX,
                scale,
                thickness,
            )
            text_x = x1 + (square_size - text_width) // 2
            text_y = y1 + (square_size + text_height) // 2
            text_color = white_piece if piece.color == chess.WHITE else black_piece
            outline = black_piece if piece.color == chess.WHITE else white_piece
            cv2.putText(
                image,
                label,
                (text_x, text_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                scale,
                outline,
                thickness + 3,
                cv2.LINE_AA,
            )
            cv2.putText(
                image,
                label,
                (text_x, text_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                scale,
                text_color,
                thickness,
                cv2.LINE_AA,
            )

    for file_index, file_name in enumerate("abcdefgh"):
        base._put(
            image,
            file_name,
            (file_index * square_size + 5, board_size - 7),
            (55, 60, 68),
            0.35,
        )
    return image


def show_chess960_generator() -> None:
    position_number, board = _new_position()
    message = ""
    buttons: list[Button] = []
    queue: list[str] = []

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, 1180, 760)

    def mouse(event: int, x: int, y: int, _flags: int, _data: object) -> None:
        if event == cv2.EVENT_LBUTTONUP:
            action = pregame_ui.clicked_action(buttons, x, y)
            if action:
                queue.append(action)

    cv2.setMouseCallback(WINDOW_NAME, mouse)

    while True:
        view = np.zeros((760, 1180, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        base._put(view, "Chess960 Position Generator", (38, 52), (100, 220, 255), 0.95, 2)
        base._put(
            view,
            "Generate one of the 960 legal Chess960 starting positions.",
            (40, 83),
            (165, 175, 190),
            0.50,
        )

        board_image = _render_board(board)
        view[120:680, 40:600] = board_image

        base._put(view, f"Position #{position_number}", (650, 155), (120, 255, 170), 0.80, 2)
        base._put(view, "White back rank", (650, 205), (165, 175, 190), 0.48)
        back_rank = " ".join(
            board.piece_at(chess.square(file_index, 0)).symbol().upper()
            for file_index in range(8)
        )
        base._put(view, back_rank, (650, 242), (235, 235, 240), 0.72, 2)
        base._put(
            view,
            "The bishops are on opposite colors, and the king is between the rooks.",
            (650, 292),
            (185, 195, 210),
            0.43,
        )

        fen = board.fen()
        base._put(view, "FEN", (650, 350), (100, 220, 255), 0.50)
        base._put(view, fen[:63], (650, 382), (210, 215, 225), 0.40)
        if len(fen) > 63:
            base._put(view, fen[63:126], (650, 410), (210, 215, 225), 0.40)

        generate = Button("generate", "GENERATE ANOTHER", 650, 480, 440, 58, active=True)
        copy_fen = Button("copy", "COPY FEN", 650, 555, 210, 52)
        back = Button("back", "BACK", 880, 555, 210, 52)
        buttons = [generate, copy_fen, back]
        for button in buttons:
            pregame_ui.draw_button(view, button)

        base._put(
            view,
            "Press Space or R to generate another position.",
            (650, 650),
            (145, 155, 170),
            0.42,
        )
        if message:
            base._put(view, message, (650, 690), (120, 220, 255), 0.43)

        cv2.imshow(WINDOW_NAME, view)
        key = cv2.waitKey(25) & 0xFF
        action = queue.pop(0) if queue else None

        if action == "generate" or key in (ord("r"), ord("R"), 32):
            position_number, board = _new_position()
            message = ""
        elif action == "copy" or key in (ord("c"), ord("C")):
            copied = update.copy_text(fen)
            message = "FEN copied to clipboard." if copied else "Could not copy FEN."
        elif action == "back" or key == 27:
            cv2.destroyWindow(WINDOW_NAME)
            cv2.waitKey(1)
            return

        try:
            if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                return
        except cv2.error:
            return
