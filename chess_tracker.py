from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import chess
import chess.pgn
import cv2
import numpy as np

from clock_reader import format_pgn_clock


BOARD_PIXELS = 800
SQUARE_PIXELS = BOARD_PIXELS // 8


@dataclass(frozen=True)
class RankedMove:
    move: chess.Move
    score: float
    expected_squares: frozenset[chess.Square]


@dataclass(frozen=True)
class MoveFit:
    score: float
    observed_squares: frozenset[chess.Square]
    explained_squares: frozenset[chess.Square]


@dataclass(frozen=True)
class ConsensusAnalysis:
    move: chess.Move | None
    ranked: list[RankedMove]
    scores: dict[chess.Square, float]
    frame: np.ndarray
    valid_votes: int
    confidence: float
    ambiguous: bool


def move_changed_squares(board: chess.Board, move: chess.Move) -> frozenset[chess.Square]:
    """Return every physical square expected to change for a legal move."""
    changed = {move.from_square, move.to_square}

    if board.is_castling(move):
        rank = chess.square_rank(move.from_square)
        if chess.square_file(move.to_square) > chess.square_file(move.from_square):
            changed.update({chess.square(7, rank), chess.square(5, rank)})
        else:
            changed.update({chess.square(0, rank), chess.square(3, rank)})

    if board.is_en_passant(move):
        capture_rank = chess.square_rank(move.from_square)
        changed.add(chess.square(chess.square_file(move.to_square), capture_rank))

    return frozenset(changed)


def rank_legal_moves(
    board: chess.Board, square_scores: dict[chess.Square, float]
) -> list[RankedMove]:
    """
    Rank legal moves against observed per-square visual changes.

    A good move explains high-change squares and leaves little unexplained
    change elsewhere. Scores are useful for ordering, not as probabilities.
    """
    all_squares = set(chess.SQUARES)
    ranked: list[RankedMove] = []

    for move in board.legal_moves:
        expected = move_changed_squares(board, move)
        explained = float(np.mean([square_scores[sq] for sq in expected]))
        unexpected_values = sorted(
            (square_scores[sq] for sq in all_squares - set(expected)), reverse=True
        )
        unexpected = float(np.mean(unexpected_values[:3])) if unexpected_values else 0.0
        size_penalty = max(0, len(expected) - 2) * 0.35
        score = explained - (0.72 * unexpected) - size_penalty
        ranked.append(RankedMove(move, score, expected))

    # The camera cannot distinguish promotion piece types. Prefer queen unless
    # the user explicitly chooses an underpromotion.
    promotion_order = {
        chess.QUEEN: 4,
        chess.ROOK: 3,
        chess.BISHOP: 2,
        chess.KNIGHT: 1,
        None: 0,
    }
    ranked.sort(
        key=lambda item: (item.score, promotion_order[item.move.promotion]),
        reverse=True,
    )
    return ranked


def square_change_scores(reference: np.ndarray, current: np.ndarray) -> dict[int, float]:
    """Measure structural/color change in each square of two warped board images."""
    ref_lab = cv2.cvtColor(reference, cv2.COLOR_BGR2LAB)
    cur_lab = cv2.cvtColor(current, cv2.COLOR_BGR2LAB)
    ref_gray = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY)
    cur_gray = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)

    scores: dict[int, float] = {}
    margin = int(SQUARE_PIXELS * 0.12)

    for rank_from_top in range(8):
        for file_index in range(8):
            y0 = rank_from_top * SQUARE_PIXELS + margin
            y1 = (rank_from_top + 1) * SQUARE_PIXELS - margin
            x0 = file_index * SQUARE_PIXELS + margin
            x1 = (file_index + 1) * SQUARE_PIXELS - margin

            color_delta = cv2.absdiff(
                ref_lab[y0:y1, x0:x1], cur_lab[y0:y1, x0:x1]
            )
            color_score = float(np.mean(color_delta))

            ref_edges = cv2.Canny(ref_gray[y0:y1, x0:x1], 60, 150)
            cur_edges = cv2.Canny(cur_gray[y0:y1, x0:x1], 60, 150)
            edge_score = float(np.mean(cv2.absdiff(ref_edges, cur_edges))) / 8.0

            chess_rank = 7 - rank_from_top
            square = chess.square(file_index, chess_rank)
            scores[square] = color_score + edge_score

    return scores


def prepare_comparison_frame(
    reference: np.ndarray,
    current: np.ndarray,
    max_shift: float = 8.0,
) -> np.ndarray:
    """Align a stable frame and compensate for a global lighting change."""
    ref_gray = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY).astype(np.float32)
    cur_gray = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY).astype(np.float32)
    shift, response = cv2.phaseCorrelate(ref_gray, cur_gray)
    dx, dy = shift
    aligned = current
    if response >= 0.02 and abs(dx) <= max_shift and abs(dy) <= max_shift:
        transform = np.float32([[1, 0, -dx], [0, 1, -dy]])
        aligned = cv2.warpAffine(
            current,
            transform,
            (current.shape[1], current.shape[0]),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT,
        )

    ref_lab = cv2.cvtColor(reference, cv2.COLOR_BGR2LAB)
    aligned_lab = cv2.cvtColor(aligned, cv2.COLOR_BGR2LAB).astype(np.int16)
    light_delta = int(
        round(float(np.median(ref_lab[:, :, 0]) - np.median(aligned_lab[:, :, 0])))
    )
    aligned_lab[:, :, 0] = np.clip(
        aligned_lab[:, :, 0] + light_delta,
        0,
        255,
    )
    return cv2.cvtColor(aligned_lab.astype(np.uint8), cv2.COLOR_LAB2BGR)


def average_square_scores(
    score_sets: list[dict[chess.Square, float]],
) -> dict[chess.Square, float]:
    if not score_sets:
        return {square: 0.0 for square in chess.SQUARES}
    return {
        square: float(np.mean([scores[square] for scores in score_sets]))
        for square in chess.SQUARES
    }


def select_consensus_move(
    votes: list[chess.Move],
    required_votes: int = 2,
) -> chess.Move | None:
    """Return a unique move supported by enough independent frame readings."""
    if not votes:
        return None
    counts = Counter(votes)
    move, count = counts.most_common(1)[0]
    tied = sum(1 for value in counts.values() if value == count) > 1
    return move if count >= required_votes and not tied else None


def analyze_frame_consensus(
    board: chess.Board,
    reference: np.ndarray,
    frames: list[np.ndarray],
    fit_threshold: float,
) -> ConsensusAnalysis:
    """Analyze three stable frames and require two to agree on a legal move."""
    if not frames:
        raise ValueError("At least one frame is required for consensus analysis.")

    prepared = [prepare_comparison_frame(reference, frame) for frame in frames]
    score_sets = [square_change_scores(reference, frame) for frame in prepared]
    votes: list[chess.Move] = []
    all_candidates: list[chess.Move] = []
    vote_confidences: list[tuple[chess.Move, float]] = []
    for scores in score_sets:
        ranked = rank_legal_moves(board, scores)
        if not ranked:
            continue
        all_candidates.append(ranked[0].move)
        fit = legal_move_fit(ranked[0], scores)
        if fit.score >= fit_threshold:
            votes.append(ranked[0].move)
            vote_confidences.append(
                (ranked[0].move, confidence_for(ranked, scores))
            )

    move = select_consensus_move(votes)
    ambiguous = move is None and select_consensus_move(all_candidates) is None
    averaged_scores = average_square_scores(score_sets)
    ranked = rank_legal_moves(board, averaged_scores)
    if move is not None:
        ranked.sort(key=lambda candidate: candidate.move != move)
    confidence_values = [
        value for voted_move, value in vote_confidences if voted_move == move
    ]
    confidence = (
        float(np.mean(confidence_values))
        if confidence_values
        else confidence_for(ranked, averaged_scores)
    )
    median_frame = np.median(np.stack(prepared), axis=0).astype(np.uint8)
    return ConsensusAnalysis(
        move,
        ranked,
        averaged_scores,
        median_frame,
        len(votes),
        confidence,
        ambiguous,
    )


def board_looks_restored(scores: dict[int, float]) -> bool:
    """
    Recognize the last recorded position while tolerating one noisy square.

    Reflections and tiny piece-placement differences can leave one square with
    a moderate score after a piece is returned. A real displaced piece normally
    changes either two squares or one square very strongly.
    """
    strongest = sorted(scores.values(), reverse=True)[:2]
    if not strongest:
        return True
    if strongest[0] >= 12.0:
        return False
    second = strongest[1] if len(strongest) > 1 else 0.0
    return strongest[0] + second < 13.5


def confidence_for(ranked: list[RankedMove], scores: dict[int, float]) -> float:
    """Return a conservative 0..1 confidence for the top candidate."""
    if not ranked:
        return 0.0
    strongest_change = max(scores.values(), default=0.0)
    if strongest_change < 7.0:
        return 0.0
    margin = ranked[0].score - (ranked[1].score if len(ranked) > 1 else 0.0)
    evidence = min(1.0, strongest_change / 24.0)
    separation = min(1.0, max(0.0, margin) / 9.0)
    return evidence * separation


def legal_move_fit(candidate: RankedMove, scores: dict[int, float]) -> MoveFit:
    """
    Measure how completely a legal move explains the observed board change.

    This is separate from move ranking: ranking answers "which legal move is
    closest?", while this score answers "does any legal move actually fit?"
    """
    strongest = max(scores.values(), default=0.0)
    if strongest < 7.0:
        return MoveFit(0.0, frozenset(), frozenset())

    active_threshold = max(7.0, strongest * 0.34)
    observed = frozenset(
        square for square, value in scores.items() if value >= active_threshold
    )
    explained = observed.intersection(candidate.expected_squares)

    # A normal move must visibly affect an origin and destination. The weighted
    # precision term also penalizes unexplained squares, such as e2 and e5 when
    # only e2-e3/e4 are legal.
    required_visible = min(2, len(candidate.expected_squares))
    coverage = min(1.0, len(explained) / max(1, required_visible))
    observed_energy = sum(scores[square] for square in observed)
    explained_energy = sum(scores[square] for square in explained)
    precision = explained_energy / observed_energy if observed_energy else 0.0
    fit = (0.62 * precision) + (0.38 * coverage)
    return MoveFit(float(fit), observed, frozenset(explained))


def warp_board(frame: np.ndarray, corners: Iterable[Iterable[float]]) -> np.ndarray:
    source = np.asarray(list(corners), dtype=np.float32)
    destination = np.asarray(
        [
            [0, 0],
            [BOARD_PIXELS - 1, 0],
            [BOARD_PIXELS - 1, BOARD_PIXELS - 1],
            [0, BOARD_PIXELS - 1],
        ],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(source, destination)
    return cv2.warpPerspective(frame, matrix, (BOARD_PIXELS, BOARD_PIXELS))


def write_pgn(
    moves: list[chess.Move],
    path: Path,
    result: str = "*",
    clocks: list[float | None] | None = None,
    headers: dict[str, str] | None = None,
) -> None:
    game = chess.pgn.Game()
    game.headers["Event"] = "Camera-recorded game"
    game.headers["Site"] = "Local chessboard"
    game.headers["Result"] = result
    if headers:
        for name, value in headers.items():
            cleaned = str(value).strip()
            if cleaned:
                game.headers[str(name)] = cleaned

    node = game
    board = game.board()
    for index, move in enumerate(moves):
        if move not in board.legal_moves:
            raise ValueError(f"Illegal move in history: {move.uci()}")
        node = node.add_variation(move)
        if clocks is not None and index < len(clocks) and clocks[index] is not None:
            node.comment = f"[%clk {format_pgn_clock(clocks[index])}]"
        board.push(move)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as output:
        print(game, file=output, end="\n\n")


def move_with_promotion(move: chess.Move, piece_type: chess.PieceType) -> chess.Move:
    return chess.Move(move.from_square, move.to_square, promotion=piece_type)
