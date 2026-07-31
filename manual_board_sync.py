from __future__ import annotations

from collections.abc import Callable

import chess
import cv2
import numpy as np

from pregame_ui import Button


BOARD_SIZE = 520
BOARD_LEFT = 50
BOARD_TOP = 40
BOARD_CELL = BOARD_SIZE // 8


def virtual_square_at(x: int, y: int) -> chess.Square | None:
    """Map a click in the live virtual-board panel to a chess square."""
    if not (
        BOARD_LEFT <= x < BOARD_LEFT + BOARD_SIZE
        and BOARD_TOP <= y < BOARD_TOP + BOARD_SIZE
    ):
        return None
    file_index = (x - BOARD_LEFT) // BOARD_CELL
    rank_from_top = (y - BOARD_TOP) // BOARD_CELL
    return chess.square(file_index, 7 - rank_from_top)


def legal_drag_move(
    board: chess.Board,
    from_square: chess.Square,
    to_square: chess.Square,
    choose_promotion_piece: Callable[[], chess.PieceType] | None = None,
) -> chess.Move | None:
    """Return the legal move represented by one drag, including promotion."""
    candidates = [
        move
        for move in board.legal_moves
        if move.from_square == from_square and move.to_square == to_square
    ]
    if not candidates:
        return None
    if any(move.promotion is not None for move in candidates):
        promotion = (
            choose_promotion_piece()
            if choose_promotion_piece is not None
            else chess.QUEEN
        )
        return next(
            (move for move in candidates if move.promotion == promotion),
            next(
                (move for move in candidates if move.promotion == chess.QUEEN),
                candidates[0],
            ),
        )
    return candidates[0]


def apply_legal_drag(
    board: chess.Board,
    from_square: chess.Square,
    to_square: chess.Square,
    choose_promotion_piece: Callable[[], chess.PieceType] | None = None,
) -> chess.Move | None:
    """Apply one legal move to an editable board and return that move."""
    move = legal_drag_move(
        board,
        from_square,
        to_square,
        choose_promotion_piece,
    )
    if move is None:
        return None
    board.push(move)
    return move


def edit_buttons(button_x: int, button_y: int) -> list[Button]:
    return [
        Button(
            "save_manual_sync",
            "SAVE BOARD SYNC",
            button_x,
            298 + button_y,
            276,
            44,
            active=True,
        ),
        Button(
            "undo_manual_sync",
            "UNDO EDIT",
            button_x,
            352 + button_y,
            132,
            40,
        ),
        Button(
            "reset_manual_sync",
            "RESET",
            button_x + 144,
            352 + button_y,
            132,
            40,
        ),
        Button(
            "cancel_manual_sync",
            "CANCEL",
            button_x,
            402 + button_y,
            276,
            40,
        ),
    ]


def draw_edit_overlay(
    virtual_view: np.ndarray,
    message: str = "",
) -> np.ndarray:
    """Mark the normal virtual board as the manual legal-move editor."""
    view = virtual_view.copy()
    cv2.rectangle(
        view,
        (6, 6),
        (view.shape[1] - 7, view.shape[0] - 7),
        (120, 255, 170),
        4,
    )
    cv2.rectangle(view, (45, 565), (575, 616), (28, 31, 37), -1)
    cv2.putText(
        view,
        "MANUAL SYNC - DRAG ONE OR MORE LEGAL MOVES",
        (58, 586),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.50,
        (120, 255, 170),
        2,
        cv2.LINE_AA,
    )
    if message:
        cv2.putText(
            view,
            message[:58],
            (58, 608),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.43,
            (120, 220, 255),
            1,
            cv2.LINE_AA,
        )
    return view
