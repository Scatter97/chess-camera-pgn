from __future__ import annotations

from pathlib import Path

import chess

import local_detection
import local_detection_runtime
from chess_tracker import move_changed_squares


# LOW is the strictest option. NORMAL keeps the original move-evidence floor,
# while HIGH accepts weaker visual changes for difficult camera setups.
MOVE_EVIDENCE_THRESHOLDS = {
    "low": 11.0,
    "normal": 7.0,
    "high": 6.5,
}
OCCLUSION_SCORE_THRESHOLDS = {
    "low": 6.5,
    "normal": 7.5,
    "high": 9.0,
}
MASS_CHANGE_SQUARES = {
    "low": 5,
    "normal": 7,
    "high": 9,
}
OCCLUSION_CLEAR_THRESHOLD = 4.0


def move_evidence_threshold() -> float:
    return MOVE_EVIDENCE_THRESHOLDS.get(
        local_detection.STATE.sensitivity,
        MOVE_EVIDENCE_THRESHOLDS["normal"],
    )


def _neighbors(square: chess.Square) -> set[chess.Square]:
    file_index = chess.square_file(square)
    rank_index = chess.square_rank(square)
    result: set[chess.Square] = set()
    for file_delta in (-1, 0, 1):
        for rank_delta in (-1, 0, 1):
            new_file = file_index + file_delta
            new_rank = rank_index + rank_delta
            if 0 <= new_file < 8 and 0 <= new_rank < 8:
                result.add(chess.square(new_file, new_rank))
    return result


def broad_occlusion_squares(
    scores: dict[chess.Square, float],
) -> frozenset[chess.Square]:
    """Find dense changes caused by paper, a hand, or another obstruction."""
    sensitivity = local_detection.STATE.sensitivity
    score_threshold = OCCLUSION_SCORE_THRESHOLDS.get(
        sensitivity,
        OCCLUSION_SCORE_THRESHOLDS["normal"],
    )
    active = {
        square
        for square, score in scores.items()
        if score >= score_threshold
    }
    if len(active) < MASS_CHANGE_SQUARES.get(
        sensitivity,
        MASS_CHANGE_SQUARES["normal"],
    ):
        return frozenset()

    dense: set[chess.Square] = set()
    for square in active:
        neighborhood = _neighbors(square)
        # Corners and edges have fewer possible neighbors, so use a density
        # ratio rather than one fixed neighbor count.
        required = max(4, (len(neighborhood) * 3 + 4) // 5)
        if len(neighborhood.intersection(active)) >= required:
            dense.add(square)

    if len(dense) < 4:
        return frozenset()

    # Fill dense boundaries but do not absorb a one- or two-square protrusion,
    # which is more likely to be the real move beside the obstruction.
    expanded = set(dense)
    for square in active - dense:
        neighborhood = _neighbors(square)
        required = max(3, (len(neighborhood) + 1) // 2)
        if len(neighborhood.intersection(dense)) >= required:
            expanded.add(square)
    return frozenset(expanded)


def update_persistent_occlusion(
    raw_scores: dict[chess.Square, float],
    unstable: frozenset[chess.Square],
) -> frozenset[chess.Square]:
    """Keep only dense blocked regions masked until the reference returns."""
    state = local_detection.STATE
    persistent = set(getattr(state, "blocked_squares", frozenset()))

    # Do not turn every currently moving square into a persistent obstruction.
    # The real origin and destination squares are commonly unstable during the
    # same frame as a hand or paper obstruction. Persisting all unstable squares
    # made legitimate moves remain masked even after the hand had settled.
    _ = unstable
    persistent.update(broad_occlusion_squares(raw_scores))
    persistent = {
        square
        for square in persistent
        if raw_scores.get(square, 0.0) >= OCCLUSION_CLEAR_THRESHOLD
    }
    state.blocked_squares = frozenset(persistent)
    return state.blocked_squares


def stable_legal_move_visible(
    board: chess.Board,
    scores: dict[chess.Square, float],
    unstable: frozenset[chess.Square],
    blocked: frozenset[chess.Square] = frozenset(),
) -> bool:
    """Require two strong, stable move squares outside any blocked region."""
    threshold = move_evidence_threshold()
    for move in board.legal_moves:
        expected = move_changed_squares(board, move)
        if expected.intersection(unstable) or expected.intersection(blocked):
            continue
        required_visible = min(2, len(expected))
        visible = sum(
            1
            for square in expected
            if scores.get(square, 0.0) >= threshold
        )
        if visible >= required_visible:
            return True
    return False


def filter_change_scores(
    board: chess.Board | None,
    raw_scores: dict[chess.Square, float],
    unstable: frozenset[chess.Square],
) -> dict[chess.Square, float]:
    """Mask obstructions without hiding a real move after it settles."""
    blocked = update_persistent_occlusion(raw_scores, unstable)
    masked = set(unstable).union(blocked)
    filtered = {
        square: (0.0 if square in masked else value)
        for square, value in raw_scores.items()
    }

    if board is None:
        return filtered
    if stable_legal_move_visible(board, filtered, unstable, blocked):
        return filtered

    # A broad obstruction must never become a fake move after it stops moving.
    # Wait for a complete legal move to appear outside the obstruction.
    if blocked or unstable:
        return {square: 0.0 for square in chess.SQUARES}

    # LOW mode rejects weak two-square noise. Strong stable illegal changes
    # still pass through to the normal illegal-move correction workflow.
    if max(filtered.values(), default=0.0) < move_evidence_threshold():
        return {square: 0.0 for square in chess.SQUARES}
    return filtered


def install() -> None:
    """Install broad-occlusion masking into the active Local64 runtime."""
    if getattr(local_detection_runtime, "_occlusion_fix_installed", False):
        return

    state = local_detection.STATE
    state.blocked_squares = frozenset()

    original_configure = local_detection.configure

    def configure(config_path: Path) -> None:
        original_configure(config_path)
        state.blocked_squares = frozenset()

    local_detection.configure = configure
    local_detection_runtime.stable_legal_move_visible = stable_legal_move_visible
    local_detection_runtime.filter_change_scores = filter_change_scores
    local_detection_runtime._occlusion_fix_installed = True
