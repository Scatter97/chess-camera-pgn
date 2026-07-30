from __future__ import annotations

import json
import math
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable

import chess
import chess.engine


DEFAULT_ANALYSIS_SECONDS = 0.12
PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}


class AnalysisUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class PositionEvaluation:
    centipawns: int
    mate: int | None
    best_move_uci: str | None


@dataclass(frozen=True)
class MoveReview:
    ply: int
    move_number: int
    white: bool
    san: str
    uci: str
    classification: str
    accuracy: float
    centipawn_loss: int
    evaluation_after: int
    mate_after: int | None
    best_move_uci: str | None
    best_move_san: str | None


@dataclass(frozen=True)
class GameReview:
    engine_name: str
    seconds_per_position: float
    white_accuracy: float
    black_accuracy: float
    moves: list[MoveReview]

    def classification_counts(self, white: bool) -> dict[str, int]:
        counts: dict[str, int] = {}
        for move in self.moves:
            if move.white != white:
                continue
            counts[move.classification] = counts.get(move.classification, 0) + 1
        return counts


def find_stockfish(explicit_path: str | None = None) -> Path | None:
    """Find a user-installed Stockfish binary without downloading anything."""
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path).expanduser())
    environment_path = os.environ.get("STOCKFISH_PATH")
    if environment_path:
        candidates.append(Path(environment_path).expanduser())
    discovered = shutil.which("stockfish")
    if discovered:
        candidates.append(Path(discovered))

    for directory in (Path("engines"), Path("stockfish"), Path(".")):
        if not directory.exists():
            continue
        candidates.extend(sorted(directory.glob("stockfish*")))

    for candidate in candidates:
        if not candidate.is_file():
            continue
        if os.name == "nt" and candidate.suffix.lower() != ".exe":
            continue
        if os.name != "nt" and not os.access(candidate, os.X_OK):
            continue
        return candidate.resolve()
    return None


def move_accuracy(centipawn_loss: int) -> float:
    """Convert centipawn loss to a transparent 0–100 accuracy estimate."""
    loss = max(0, min(1200, int(centipawn_loss)))
    return round(100.0 * math.exp(-loss / 250.0), 1)


def _is_apparent_sacrifice(board: chess.Board, move: chess.Move) -> bool:
    piece = board.piece_at(move.from_square)
    if piece is None or piece.piece_type in {chess.PAWN, chess.KING}:
        return False
    captured = board.piece_at(move.to_square)
    captured_value = PIECE_VALUES[captured.piece_type] if captured else 0
    moving_value = PIECE_VALUES[piece.piece_type]
    after = board.copy(stack=False)
    after.push(move)
    is_attacked = after.is_attacked_by(not piece.color, move.to_square)
    return is_attacked and moving_value >= captured_value + 2


def classify_move(
    board: chess.Board,
    move: chess.Move,
    centipawn_loss: int,
    best_move: chess.Move | None,
    best_evaluation: PositionEvaluation,
    after_evaluation: PositionEvaluation,
) -> str:
    """Classify a move using documented, engine-independent thresholds."""
    is_best = best_move == move
    if (
        is_best
        and centipawn_loss <= 15
        and _is_apparent_sacrifice(board, move)
    ):
        return "Brilliant"

    missed_mate = (
        best_evaluation.mate is not None
        and best_evaluation.mate > 0
        and (
            after_evaluation.mate is None
            or after_evaluation.mate <= 0
        )
    )
    missed_winning_chance = (
        best_evaluation.centipawns >= 250
        and after_evaluation.centipawns < 100
        and centipawn_loss >= 180
    )
    if missed_mate or missed_winning_chance:
        return "Miss"
    if is_best or centipawn_loss <= 8:
        return "Best"
    if centipawn_loss <= 25:
        return "Excellent"
    if centipawn_loss <= 60:
        return "Good"
    if centipawn_loss <= 120:
        return "Inaccuracy"
    if centipawn_loss <= 250:
        return "Mistake"
    return "Blunder"


def _evaluation_from_info(
    info: dict[str, object],
    point_of_view: chess.Color,
) -> PositionEvaluation:
    score = info.get("score")
    if not isinstance(score, chess.engine.PovScore):
        return PositionEvaluation(0, None, None)
    pov_score = score.pov(point_of_view)
    centipawns = int(pov_score.score(mate_score=100_000) or 0)
    mate = pov_score.mate()
    pv = info.get("pv")
    best_move_uci = None
    if isinstance(pv, list) and pv and isinstance(pv[0], chess.Move):
        best_move_uci = pv[0].uci()
    return PositionEvaluation(centipawns, mate, best_move_uci)


def build_game_review(
    moves: Iterable[chess.Move],
    evaluations: list[PositionEvaluation],
    engine_name: str,
    seconds_per_position: float,
) -> GameReview:
    move_list = list(moves)
    if len(evaluations) != len(move_list) + 1:
        raise ValueError("A review needs one evaluation for every game position.")

    board = chess.Board()
    reviews: list[MoveReview] = []
    for index, move in enumerate(move_list):
        mover = board.turn
        before = evaluations[index]
        raw_after = evaluations[index + 1]
        # Evaluations are stored from the player-to-move point of view for
        # each position. Reverse the next position into the mover's view.
        after = PositionEvaluation(
            -raw_after.centipawns,
            -raw_after.mate if raw_after.mate is not None else None,
            raw_after.best_move_uci,
        )
        best_move = (
            chess.Move.from_uci(before.best_move_uci)
            if before.best_move_uci
            else None
        )
        best_move_san = (
            board.san(best_move)
            if best_move is not None and best_move in board.legal_moves
            else None
        )
        san = board.san(move)
        loss = max(0, before.centipawns - after.centipawns)
        classification = classify_move(
            board,
            move,
            loss,
            best_move,
            before,
            after,
        )
        reviews.append(
            MoveReview(
                ply=index + 1,
                move_number=board.fullmove_number,
                white=mover == chess.WHITE,
                san=san,
                uci=move.uci(),
                classification=classification,
                accuracy=move_accuracy(loss),
                centipawn_loss=loss,
                evaluation_after=after.centipawns,
                mate_after=after.mate,
                best_move_uci=before.best_move_uci,
                best_move_san=best_move_san,
            )
        )
        board.push(move)

    white_values = [move.accuracy for move in reviews if move.white]
    black_values = [move.accuracy for move in reviews if not move.white]
    return GameReview(
        engine_name=engine_name,
        seconds_per_position=seconds_per_position,
        white_accuracy=round(sum(white_values) / len(white_values), 1)
        if white_values
        else 0.0,
        black_accuracy=round(sum(black_values) / len(black_values), 1)
        if black_values
        else 0.0,
        moves=reviews,
    )


def analyze_game(
    moves: Iterable[chess.Move],
    stockfish_path: Path,
    seconds_per_position: float = DEFAULT_ANALYSIS_SECONDS,
    progress: Callable[[int, int], None] | None = None,
) -> GameReview:
    move_list = list(moves)
    boards = [chess.Board()]
    for move in move_list:
        next_board = boards[-1].copy(stack=False)
        next_board.push(move)
        boards.append(next_board)

    try:
        engine = chess.engine.SimpleEngine.popen_uci(str(stockfish_path))
    except (OSError, chess.engine.EngineError) as error:
        raise AnalysisUnavailable(f"Could not start Stockfish: {error}") from error

    evaluations: list[PositionEvaluation] = []
    try:
        engine_name = str(engine.id.get("name", "Stockfish"))
        total = len(boards)
        for index, board in enumerate(boards):
            if progress:
                progress(index, total)
            info = engine.analyse(
                board,
                chess.engine.Limit(time=max(0.02, seconds_per_position)),
            )
            evaluations.append(_evaluation_from_info(info, board.turn))
        if progress:
            progress(total, total)
    except (chess.engine.EngineError, chess.engine.EngineTerminatedError) as error:
        raise AnalysisUnavailable(f"Stockfish analysis failed: {error}") from error
    finally:
        try:
            engine.quit()
        except (chess.engine.EngineError, chess.engine.EngineTerminatedError):
            pass

    return build_game_review(
        move_list,
        evaluations,
        engine_name,
        seconds_per_position,
    )


def save_analysis_report(review: GameReview, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(review)
    data["white_counts"] = review.classification_counts(chess.WHITE)
    data["black_counts"] = review.classification_counts(chess.BLACK)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
