from pathlib import Path

import chess
import pytest

from chess_camera_app.game.bot_engine import choose_move
from chess_camera_app.game import bot_games
from chess_camera_app.game.chess_tracker import ConsensusAnalysis
import numpy as np


def test_bot_requires_an_existing_engine() -> None:
    with pytest.raises(FileNotFoundError):
        choose_move(chess.Board(), Path("missing-stockfish"))


def test_bot_rejects_finished_games(tmp_path: Path) -> None:
    engine = tmp_path / "engine"
    engine.touch()
    board = chess.Board("7k/5Q2/7K/8/8/8/8/8 b - - 0 1")
    with pytest.raises(ValueError):
        choose_move(board, engine)


def test_bot_game_save_writes_a_history_pgn(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(bot_games.app, "OUTPUT_PATH", tmp_path / "latest_game.pgn")
    monkeypatch.setattr(bot_games.navigation, "GAMES_DIR", tmp_path / "games")
    board = chess.Board()
    board.push_san("e4")

    message = bot_games._save_bot_game(board, otb=False)

    assert message.startswith("Saved bot_game_")
    assert (tmp_path / "latest_game.pgn").is_file()
    saved = list((tmp_path / "games").glob("bot_game_*.pgn"))
    assert len(saved) == 1
    assert "Virtual Bot Game" in saved[0].read_text(encoding="utf-8")


def test_camera_confirmation_requires_the_expected_stable_move() -> None:
    expected = chess.Move.from_uci("e7e5")
    analysis = ConsensusAnalysis(
        move=expected,
        ranked=[],
        scores={},
        frame=np.zeros((2, 2, 3), dtype=np.uint8),
        valid_votes=2,
        confidence=0.75,
        ambiguous=False,
    )

    assert bot_games._analysis_confirms_expected(analysis, expected)
    assert not bot_games._analysis_confirms_expected(analysis, chess.Move.from_uci("g8f6"))
    assert not bot_games._analysis_confirms_expected(
        ConsensusAnalysis(expected, [], {}, analysis.frame, 1, 0.95, False), expected
    )
