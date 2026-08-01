from __future__ import annotations

import chess
import cv2
import numpy as np
from datetime import datetime

from chess_camera_app.core import app
from chess_camera_app.core import app_navigation as navigation
from chess_camera_app.game.bot_engine import BotSettings, choose_move
from chess_camera_app.ui import pregame_ui
from chess_camera_app.ui import ui_support as ui
from chess_camera_app.ui.pregame_ui import Button


WINDOW_NAME = "Chess Camera - Bot Game"
BOARD_LEFT, BOARD_TOP, BOARD_SIZE = 35, 115, 560


def _save_bot_game(board: chess.Board, otb: bool) -> str:
    """Save a bot game in the normal games folder so History can review it."""
    moves = list(board.move_stack)
    if not moves:
        return "Make at least one move before saving."
    result = board.result(claim_draw=True) if board.is_game_over(claim_draw=True) else "*"
    headers = {
        "Event": "OTB Bot Game" if otb else "Virtual Bot Game",
        "Site": "Local",
        "Date": datetime.now().strftime("%Y.%m.%d"),
        "White": "Player",
        "Black": "Stockfish",
        "Result": result,
        "Termination": "Game over" if result != "*" else "Saved unfinished game",
    }
    timestamped = (
        navigation.GAMES_DIR
        / (datetime.now().strftime("bot_game_%Y-%m-%d_%H-%M-%S") + ".pgn")
    )
    app.write_pgn(moves, app.OUTPUT_PATH, result=result, headers=headers)
    app.write_pgn(moves, timestamped, result=result, headers=headers)
    return f"Saved {timestamped.name}."


def _square_at(x: int, y: int) -> chess.Square | None:
    if not (BOARD_LEFT <= x < BOARD_LEFT + BOARD_SIZE and BOARD_TOP <= y < BOARD_TOP + BOARD_SIZE):
        return None
    file_index = (x - BOARD_LEFT) * 8 // BOARD_SIZE
    rank_index = 7 - ((y - BOARD_TOP) * 8 // BOARD_SIZE)
    return chess.square(file_index, rank_index)


def show_virtual_bot_game(otb: bool = False) -> None:
    """Play a local Stockfish game on-screen, or use it as an OTB move assistant."""
    engine_path = navigation.configured_engine()
    board = chess.Board()
    selected: chess.Square | None = None
    pending_bot: chess.Move | None = None
    message = "Choose a Stockfish engine in Settings before starting." if engine_path is None else "You are White. Make a move."
    buttons: list[Button] = []
    queue: list[str] = []

    def mouse(event: int, x: int, y: int, _flags: int, _data: object) -> None:
        nonlocal selected
        if event != cv2.EVENT_LBUTTONUP:
            return
        action = pregame_ui.clicked_action(buttons, x, y)
        if action:
            queue.append(action)
            return
        if pending_bot is not None or board.turn != chess.WHITE:
            return
        square = _square_at(x, y)
        if square is None:
            return
        if selected is None:
            if board.color_at(square) == chess.WHITE:
                selected = square
            return
        move = chess.Move(selected, square)
        selected = None
        if move in board.legal_moves:
            board.push(move)
            queue.append("bot_move")

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, 1080, 760)
    cv2.setMouseCallback(WINDOW_NAME, mouse)
    while True:
        view = np.zeros((760, 1080, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        ui._put(view, "OTB Bot Game" if otb else "Virtual Bot Game", (35, 52), (100, 220, 255), 0.9, 2)
        ui._put(view, "Local Stockfish — no internet required", (35, 82), (165, 175, 190), 0.46)
        view[BOARD_TOP:BOARD_TOP + BOARD_SIZE, BOARD_LEFT:BOARD_LEFT + BOARD_SIZE] = cv2.resize(app.render_virtual_board(board), (BOARD_SIZE, BOARD_SIZE))
        if selected is not None:
            file_index, rank_index = chess.square_file(selected), chess.square_rank(selected)
            cell = BOARD_SIZE // 8
            x, y = BOARD_LEFT + file_index * cell, BOARD_TOP + (7 - rank_index) * cell
            cv2.rectangle(view, (x, y), (x + cell, y + cell), (0, 235, 255), 3)
        confirm = Button("confirm", "CONFIRM PHYSICAL BOT MOVE", 635, 230, 390, 50, active=True)
        save = Button("save", "SAVE PGN", 635, 660, 170, 48, enabled=bool(board.move_stack))
        back = Button("back", "MAIN MENU", 760, 660, 220, 48)
        buttons = [save, back] + ([confirm] if otb and pending_bot is not None else [])
        for button in buttons:
            pregame_ui.draw_button(view, button)
        ui._put(view, "BOT MOVE" if pending_bot else "YOUR MOVE", (635, 142), (165, 175, 190), 0.46)
        if pending_bot is not None:
            ui._put(view, board.san(pending_bot), (635, 186), (120, 255, 170), 0.8, 2)
            if otb:
                ui._put(view, "Move this piece on the real board, then confirm.", (635, 305), (210, 215, 225), 0.42)
        ui._put(view, message[:62], (635, 590), (210, 215, 225), 0.42)
        cv2.imshow(WINDOW_NAME, view)
        action = queue.pop(0) if queue else None
        key = cv2.waitKey(20) & 0xFF
        if action == "bot_move" and engine_path is not None and not board.is_game_over():
            try:
                pending_bot = choose_move(board, engine_path, BotSettings())
                if not otb:
                    board.push(pending_bot)
                    message, pending_bot = "Bot moved. Your turn.", None
            except Exception as error:
                message = f"Bot could not move: {error}"
        elif action == "confirm" and pending_bot is not None:
            board.push(pending_bot)
            pending_bot = None
            message = "Bot move recorded. Your turn."
        elif action == "save":
            message = _save_bot_game(board, otb)
        elif action == "back" or key == 27:
            cv2.destroyWindow(WINDOW_NAME)
            return
