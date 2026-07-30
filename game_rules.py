from __future__ import annotations

from dataclasses import dataclass

import chess


@dataclass(frozen=True)
class GameOutcome:
    result: str
    title: str
    message: str


def automatic_outcome(board: chess.Board) -> GameOutcome | None:
    """Return an ending that is automatic under standard chess rules."""
    if board.is_checkmate():
        winner = "Black" if board.turn == chess.WHITE else "White"
        result = "0-1" if winner == "Black" else "1-0"
        return GameOutcome(result, "Checkmate", f"Checkmate - {winner} wins.")
    if board.is_stalemate():
        return GameOutcome("1/2-1/2", "Stalemate", "Draw by stalemate.")
    if board.is_insufficient_material():
        return GameOutcome(
            "1/2-1/2",
            "Insufficient material",
            "Draw because checkmate is not possible with the remaining material.",
        )
    if board.is_fivefold_repetition():
        return GameOutcome(
            "1/2-1/2",
            "Fivefold repetition",
            "Automatic draw by fivefold repetition.",
        )
    if board.is_seventyfive_moves():
        return GameOutcome(
            "1/2-1/2",
            "75-move rule",
            "Automatic draw because 75 moves were completed without a pawn move or capture.",
        )
    return None


def claimable_draw_reasons(board: chess.Board) -> list[str]:
    """Return draw conditions that the app asks both players to accept."""
    reasons: list[str] = []
    if board.is_repetition(3):
        reasons.append("Threefold repetition")
    if board.halfmove_clock >= 100:
        reasons.append("50-move rule")
    return reasons


def claimable_draw_reason(board: chess.Board) -> str | None:
    """Return the first claimable draw reason, if any."""
    reasons = claimable_draw_reasons(board)
    return reasons[0] if reasons else None
