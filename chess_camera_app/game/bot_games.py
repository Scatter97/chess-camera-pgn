from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path

import chess
import cv2
import numpy as np

from chess_camera_app.core import app
from chess_camera_app.core import app_navigation as navigation
from chess_camera_app.game.bot_engine import BotSettings, choose_move
from chess_camera_app.game.chess_tracker import (
    ConsensusAnalysis,
    analyze_frame_consensus,
    orient_board_image,
    warp_board,
)
from chess_camera_app.ui import pregame_ui
from chess_camera_app.ui import ui_support as ui
from chess_camera_app.ui.pregame_ui import Button


WINDOW_NAME = "Chess Camera - Bot Game"
BOARD_LEFT, BOARD_TOP, BOARD_SIZE = 35, 115, 560


@dataclass
class CameraConfirmation:
    capture: cv2.VideoCapture
    corners: list[list[float]]
    white_camera_edge: str
    reference: np.ndarray | None = None
    frames: deque[np.ndarray] = None  # type: ignore[assignment]
    checks: int = 0

    def __post_init__(self) -> None:
        self.frames = deque(maxlen=3)

    def read_board(self) -> np.ndarray | None:
        ok, raw = self.capture.read()
        if not ok:
            return None
        return orient_board_image(warp_board(raw, self.corners), self.white_camera_edge)

    def reset_reference(self, board_image: np.ndarray) -> None:
        self.reference = board_image.copy()
        self.frames.clear()
        self.checks = 0

    def close(self) -> None:
        self.capture.release()


def _camera_calibration() -> tuple[list[list[float]], str, int] | None:
    """Load the saved board geometry used by the normal recorded-game mode."""
    try:
        data = json.loads(Path(app.CONFIG_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    corners = data.get("board_corners", data.get("corners"))
    if not isinstance(corners, list) or len(corners) != 4:
        return None
    try:
        normalized = [[float(point[0]), float(point[1])] for point in corners]
    except (TypeError, ValueError, IndexError):
        return None
    edge = str(data.get("white_camera_edge", "bottom"))
    if edge not in {"bottom", "top", "left", "right"}:
        edge = "bottom"
    try:
        camera_index = int(data.get("camera_index", 0))
    except (TypeError, ValueError):
        camera_index = 0
    return normalized, edge, camera_index


def _open_camera_confirmation() -> tuple[CameraConfirmation | None, str]:
    calibration = _camera_calibration()
    if calibration is None:
        return None, "Automatic confirmation needs a saved board calibration."
    corners, edge, camera_index = calibration
    try:
        return CameraConfirmation(app.open_camera(camera_index), corners, edge), "Automatic camera confirmation is on."
    except RuntimeError as error:
        return None, str(error)


def _analysis_confirms_expected(
    analysis: ConsensusAnalysis,
    expected: chess.Move,
) -> bool:
    """Require a stable, high-confidence camera reading of the bot's exact move."""
    return (
        analysis.move == expected
        and analysis.valid_votes >= 2
        and analysis.confidence >= 0.68
    )


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
    camera_confirmation: CameraConfirmation | None = None
    last_camera_board: np.ndarray | None = None
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
        camera_button = Button(
            "camera_off" if camera_confirmation is not None else "camera_on",
            "AUTO CAMERA: ON" if camera_confirmation is not None else "AUTO CAMERA: OFF",
            635,
            286,
            250,
            46,
            active=camera_confirmation is not None,
        )
        save = Button("save", "SAVE PGN", 635, 660, 170, 48, enabled=bool(board.move_stack))
        back = Button("back", "MAIN MENU", 760, 660, 220, 48)
        buttons = [save, back]
        if otb:
            buttons.append(camera_button)
            if pending_bot is not None:
                buttons.append(confirm)
        for button in buttons:
            pregame_ui.draw_button(view, button)
        ui._put(view, "BOT MOVE" if pending_bot else "YOUR MOVE", (635, 142), (165, 175, 190), 0.46)
        if pending_bot is not None:
            ui._put(view, board.san(pending_bot), (635, 186), (120, 255, 170), 0.8, 2)
            if otb:
                ui._put(view, "Camera confirms automatically; manual confirm stays available.", (635, 350), (210, 215, 225), 0.38)
        elif otb:
            ui._put(view, "Turn on Auto Camera after using the normal board calibration.", (635, 350), (210, 215, 225), 0.38)
        ui._put(view, message[:62], (635, 590), (210, 215, 225), 0.42)
        cv2.imshow(WINDOW_NAME, view)
        action = queue.pop(0) if queue else None
        key = cv2.waitKey(20) & 0xFF
        if camera_confirmation is not None:
            last_camera_board = camera_confirmation.read_board()
            if last_camera_board is not None and pending_bot is not None and camera_confirmation.reference is not None:
                camera_confirmation.frames.append(last_camera_board)
                if len(camera_confirmation.frames) == 3:
                    camera_confirmation.checks += 1
                    if camera_confirmation.checks % 5 == 0:
                        analysis = analyze_frame_consensus(
                            board,
                            camera_confirmation.reference,
                            list(camera_confirmation.frames),
                            fit_threshold=0.72,
                        )
                        if _analysis_confirms_expected(analysis, pending_bot):
                            board.push(pending_bot)
                            pending_bot = None
                            camera_confirmation.reset_reference(last_camera_board)
                            message = "Camera confirmed the bot move. Your turn."
                        elif analysis.move is not None and analysis.confidence >= 0.78:
                            try:
                                seen = board.san(analysis.move)
                            except ValueError:
                                seen = analysis.move.uci()
                            message = f"Camera saw {seen}; expected {board.san(pending_bot)}. Correct it or confirm manually."
        if action == "bot_move" and engine_path is not None and not board.is_game_over():
            try:
                pending_bot = choose_move(board, engine_path, BotSettings())
                if not otb:
                    board.push(pending_bot)
                    message, pending_bot = "Bot moved. Your turn.", None
                elif camera_confirmation is not None:
                    if last_camera_board is None:
                        last_camera_board = camera_confirmation.read_board()
                    if last_camera_board is not None:
                        camera_confirmation.reset_reference(last_camera_board)
                        message = "Move the bot piece. Camera is watching; manual confirm is also available."
                    else:
                        message = "Camera frame unavailable. Use manual confirmation or restart Auto Camera."
            except Exception as error:
                message = f"Bot could not move: {error}"
        elif action == "confirm" and pending_bot is not None:
            board.push(pending_bot)
            pending_bot = None
            if camera_confirmation is not None and last_camera_board is not None:
                camera_confirmation.reset_reference(last_camera_board)
            message = "Bot move recorded. Your turn."
        elif action == "camera_on":
            camera_confirmation, message = _open_camera_confirmation()
            if camera_confirmation is not None:
                last_camera_board = camera_confirmation.read_board()
                if last_camera_board is not None:
                    camera_confirmation.reset_reference(last_camera_board)
        elif action == "camera_off":
            if camera_confirmation is not None:
                camera_confirmation.close()
            camera_confirmation = None
            last_camera_board = None
            message = "Automatic camera confirmation is off. Manual confirmation is still available."
        elif action == "save":
            message = _save_bot_game(board, otb)
        elif action == "back" or key == 27:
            if camera_confirmation is not None:
                camera_confirmation.close()
            cv2.destroyWindow(WINDOW_NAME)
            return
