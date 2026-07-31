from __future__ import annotations

from types import ModuleType

import chess
import cv2
import numpy as np

import app
from pregame_ui import Button


def board_after_selected_move(
    moves: list[chess.Move],
    selected_index: int,
) -> chess.Board:
    """Return the position immediately after the selected recorded move."""
    if not moves:
        return chess.Board()
    index = max(0, min(selected_index, len(moves) - 1))
    board = chess.Board()
    for move in moves[: index + 1]:
        if move not in board.legal_moves:
            raise ValueError(f"Illegal move in review history: {move.uci()}")
        board.push(move)
    return board


def show_game_review(
    review: object,
    moves: list[chess.Move],
    white_name: str,
    black_name: str,
) -> None:
    """Show each selected move as the resulting position, not the position before it."""
    if not moves or not getattr(review, "moves", None):
        app.show_result_popup("Review unavailable", "No analyzed moves are available.")
        return

    window = "Chess Camera - Post-game Review"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 1220, 720)
    current = 0
    scroll_start = 0
    click_queue: list[str] = []
    buttons: list[Button] = []

    def on_mouse(
        event: int,
        x: int,
        y: int,
        flags: int,
        _data: object,
    ) -> None:
        if event == cv2.EVENT_MOUSEWHEEL:
            direction = app.mouse_wheel_direction(flags)
            if direction:
                click_queue.append(
                    "scroll_up" if direction > 0 else "scroll_down"
                )
            return
        if event != cv2.EVENT_LBUTTONUP:
            return
        action = app.clicked_action(buttons, x, y)
        if action is not None:
            click_queue.append(action)

    cv2.setMouseCallback(window, on_mouse)
    while True:
        selected = review.moves[current]
        board = board_after_selected_move(moves, current)
        last_move = moves[current]
        board_view = app.render_virtual_board(
            board,
            last_move=last_move,
            suggested_move=None,
        )

        view = np.zeros((720, 1220, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        view[50:670, 20:640] = board_view
        app.draw_evaluation_bar(
            view,
            selected.evaluation_after_white,
            selected.mate_after_white,
        )

        app.put_text(view, "Post-game Review", (675, 42), (100, 220, 255), 0.9)
        app.put_text(
            view,
            f"{(white_name or 'White')[:20]}: {review.white_accuracy:.1f}% | "
            f"Avg loss {review.white_average_centipawn_loss:.1f} cp",
            (700, 82),
            (235, 235, 240),
            0.52,
        )
        app.put_text(
            view,
            f"{(black_name or 'Black')[:20]}: {review.black_accuracy:.1f}% | "
            f"Avg loss {review.black_average_centipawn_loss:.1f} cp",
            (700, 110),
            (185, 190, 200),
            0.52,
        )
        app.put_text(
            view,
            f"{selected.move_number}{'.' if selected.white else '...'} "
            f"{selected.san}  -  {selected.classification}",
            (675, 154),
            app.ANALYSIS_COLORS.get(selected.classification, (235, 235, 235)),
            0.73,
        )
        app.put_text(
            view,
            "Board position shown after this move",
            (675, 181),
            (120, 255, 170),
            0.45,
        )
        app.put_text(
            view,
            f"Move accuracy {selected.accuracy:.1f}% | "
            f"loss {selected.centipawn_loss} cp | "
            f"White eval {app._analysis_eval_text(selected.evaluation_after_white, selected.mate_after_white)}",
            (675, 208),
            (185, 195, 210),
            0.48,
        )
        best_text = (
            f"Stockfish suggested {selected.best_move_san} "
            f"({selected.best_move_uci}) before this move"
            if selected.best_move_san and selected.best_move_uci != selected.uci
            else "Played an engine-best move."
        )
        app.put_text(view, best_text[:62], (675, 236), (120, 220, 255), 0.46)

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
            y = 278 + row * 31
            app.put_text(
                view,
                label,
                (675, y),
                app.ANALYSIS_COLORS[label],
                0.48,
            )
            app.put_text(view, str(white_counts.get(label, 0)), (835, y), scale=0.48)
            app.put_text(view, str(black_counts.get(label, 0)), (895, y), scale=0.48)
        app.put_text(view, "W", (835, 256), (235, 235, 240), 0.45)
        app.put_text(view, "B", (895, 256), (185, 190, 200), 0.45)

        visible = review.moves[scroll_start : scroll_start + 9]
        app.put_text(view, "Move list", (975, 254), (100, 220, 255), 0.55)
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
            app.put_text(
                view,
                f"{prefix} {move_review.san[:8]}",
                (975, y),
                scale=0.46,
            )
            app.put_text(
                view,
                move_review.classification[:10],
                (1080, y),
                app.ANALYSIS_COLORS.get(move_review.classification, (230, 230, 230)),
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
        for item in navigation_buttons:
            app.draw_button(view, item)
        app.put_text(
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
                scroll_start = app.ensure_review_move_visible(
                    current,
                    scroll_start,
                    len(review.moves),
                )
            except ValueError:
                pass
        elif action == "scroll_up":
            scroll_start = app.review_scroll_start(
                scroll_start,
                len(review.moves),
                -3,
            )
        elif action == "scroll_down":
            scroll_start = app.review_scroll_start(
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
            scroll_start = app.ensure_review_move_visible(
                current,
                scroll_start,
                len(review.moves),
            )
        try:
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                return
        except cv2.error:
            return


def install(target: ModuleType) -> None:
    target.show_game_review = show_game_review
