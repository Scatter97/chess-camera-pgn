from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import chess
import chess.engine


@dataclass(frozen=True)
class BotSettings:
    move_time_seconds: float = 0.5
    skill_level: int = 12


def choose_move(
    board: chess.Board,
    engine_path: Path,
    settings: BotSettings = BotSettings(),
) -> chess.Move:
    """Return one local UCI-engine move for a legal virtual or OTB bot turn."""
    if board.is_game_over():
        raise ValueError("Cannot ask the bot to move after the game has ended.")
    if not engine_path.is_file():
        raise FileNotFoundError("Choose a valid Stockfish/UCI engine in Settings.")

    engine = chess.engine.SimpleEngine.popen_uci(str(engine_path), timeout=5.0)
    try:
        try:
            engine.configure({"Skill Level": max(0, min(20, settings.skill_level))})
        except chess.engine.EngineError:
            # Other UCI engines may not provide Stockfish's Skill Level option.
            pass
        result = engine.play(
            board,
            chess.engine.Limit(time=max(0.05, settings.move_time_seconds)),
        )
        return result.move
    finally:
        engine.quit()
