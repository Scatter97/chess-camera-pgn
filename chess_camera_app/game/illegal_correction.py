from __future__ import annotations

from collections.abc import Callable

import chess
import cv2
import numpy as np

from chess_camera_app.ui.pregame_ui import Button, draw_button


BOARD_SIZE = 520
BOARD_LEFT = 50
BOARD_TOP = 40
BOARD_CELL = BOARD_SIZE // 8


def virtual_square_at(x: int, y: int) -> chess.Square | None:
    """Map a click in the virtual-board panel to a chess square."""
    if not (
        BOARD_LEFT <= x < BOARD_LEFT + BOARD_SIZE
        and BOARD_TOP <= y < BOARD_TOP + BOARD_SIZE
    ):
        return None
    file_index = (x - BOARD_LEFT) // BOARD_CELL
    rank_from_top = (y - BOARD_TOP) // BOARD_CELL
    return chess.square(file_index, 7 - rank_from_top)


def _matching_drag_moves(
    board: chess.Board,
    from_square: chess.Square,
    to_square: chess.Square,
) -> list[chess.Move]:
    return [
        move
        for move in board.legal_moves
        if move.from_square == from_square and move.to_square == to_square
    ]


def apply_drag(
    board: chess.Board,
    from_square: chess.Square,
    to_square: chess.Square,
    choose_promotion_piece: Callable[[], chess.PieceType] | None = None,
) -> bool:
    """Apply a board-editor drag, preferring a complete legal chess move."""
    piece = board.piece_at(from_square)
    if piece is None:
        return False

    legal = _matching_drag_moves(board, from_square, to_square)
    if legal:
        selected = legal[0]
        if any(move.promotion is not None for move in legal):
            promotion = (
                choose_promotion_piece()
                if choose_promotion_piece is not None
                else chess.QUEEN
            )
            selected = next(
                (move for move in legal if move.promotion == promotion),
                next(
                    (move for move in legal if move.promotion == chess.QUEEN),
                    legal[0],
                ),
            )
        board.push(selected)
        return True

    board.remove_piece_at(from_square)
    board.set_piece_at(to_square, piece)
    return True


def matching_legal_move(
    base_board: chess.Board,
    edited_board: chess.Board,
) -> chess.Move | None:
    """Find the single legal move whose resulting pieces match the edited board."""
    target = edited_board.board_fen()
    matches: list[chess.Move] = []
    for move in base_board.legal_moves:
        candidate = base_board.copy(stack=False)
        candidate.push(move)
        if candidate.board_fen() == target:
            matches.append(move)
    return matches[0] if len(matches) == 1 else None


def warning_buttons(width: int, height: int) -> list[Button]:
    center = width // 2
    y = height // 2 + 92
    return [
        Button(
            "restore_illegal",
            "RESTORED - RESUME",
            center - 350,
            y,
            330,
            56,
            active=True,
        ),
        Button(
            "correct_illegal",
            "MOVE WAS LEGAL - FIX BOARD",
            center + 20,
            y,
            330,
            56,
            active=True,
        ),
    ]


def edit_buttons(button_x: int, button_y: int) -> list[Button]:
    return [
        Button(
            "continue_correction",
            "CONTINUE",
            button_x,
            298 + button_y,
            276,
            44,
            active=True,
        ),
        Button(
            "reset_correction",
            "RESET BOARD",
            button_x,
            352 + button_y,
            132,
            40,
        ),
        Button(
            "cancel_correction",
            "CANCEL",
            button_x + 144,
            352 + button_y,
            132,
            40,
        ),
    ]


def draw_warning(image: np.ndarray, buttons: list[Button]) -> np.ndarray:
    """Draw the illegal-move choice overlay and redraw its active buttons."""
    view = image.copy()
    overlay = view.copy()
    height, width = view.shape[:2]
    cv2.rectangle(overlay, (0, 0), (width, height), (0, 0, 205), -1)
    view = cv2.addWeighted(overlay, 0.72, view, 0.28, 0)

    center_y = height // 2
    cv2.rectangle(
        view,
        (35, center_y - 135),
        (width - 35, center_y + 185),
        (0, 0, 110),
        -1,
    )
    cv2.rectangle(
        view,
        (35, center_y - 135),
        (width - 35, center_y + 185),
        (255, 255, 255),
        4,
    )
    cv2.putText(
        view,
        "ILLEGAL MOVE",
        (max(30, width // 2 - 250), center_y - 40),
        cv2.FONT_HERSHEY_DUPLEX,
        2.0,
        (255, 255, 255),
        5,
        cv2.LINE_AA,
    )
    cv2.putText(
        view,
        "Restore the pieces, or correct the virtual board if the move was legal.",
        (max(30, width // 2 - 430), center_y + 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.72,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    for button in buttons:
        draw_button(view, button)
    return view


def draw_edit_overlay(
    virtual_view: np.ndarray,
    message: str = "",
) -> np.ndarray:
    """Mark the existing virtual board as an active drag-and-drop editor."""
    view = virtual_view.copy()
    cv2.rectangle(
        view,
        (6, 6),
        (view.shape[1] - 7, view.shape[0] - 7),
        (0, 205, 255),
        4,
    )
    cv2.rectangle(view, (45, 565), (575, 616), (28, 31, 37), -1)
    cv2.putText(
        view,
        "DRAG PIECES TO THE POSITION AFTER THE MOVE",
        (58, 586),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.52,
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
