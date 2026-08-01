from pathlib import Path

import chess
import pytest

from chess_camera_app.game.bot_engine import choose_move


def test_bot_requires_an_existing_engine() -> None:
    with pytest.raises(FileNotFoundError):
        choose_move(chess.Board(), Path("missing-stockfish"))


def test_bot_rejects_finished_games(tmp_path: Path) -> None:
    engine = tmp_path / "engine"
    engine.touch()
    board = chess.Board("7k/5Q2/7K/8/8/8/8/8 b - - 0 1")
    with pytest.raises(ValueError):
        choose_move(board, engine)
