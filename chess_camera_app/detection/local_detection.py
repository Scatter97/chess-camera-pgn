from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Callable

import chess
import cv2
import numpy as np

from chess_camera_app.calibration import camera_advanced
from chess_camera_app.ui import pregame_ui
from chess_camera_app.ui import ui_support as ui
from chess_camera_app.game.chess_tracker import (
    BOARD_MARGIN_PIXELS,
    SQUARE_PIXELS,
    ConsensusAnalysis,
    MoveFit,
    RankedMove,
    average_square_scores,
    move_changed_squares,
    prepare_comparison_frame,
    select_consensus_move,
)
from chess_camera_app.ui.pregame_ui import Button


SENSITIVITY_OPTIONS = ("low", "normal", "high")
DEFAULT_SENSITIVITY = "normal"


@dataclass(frozen=True)
class SensitivityProfile:
    motion_threshold: float
    max_unstable_squares: int
    occlusion_grace_seconds: float


PROFILES = {
    "low": SensitivityProfile(1.25, 6, 0.20),
    "normal": SensitivityProfile(1.80, 12, 0.35),
    "high": SensitivityProfile(2.50, 18, 0.55),
}


@dataclass
class LocalDetectionState:
    enabled: bool = False
    sensitivity: str = DEFAULT_SENSITIVITY
    current_unstable: frozenset[chess.Square] = frozenset()
    ignore_until: dict[chess.Square, float] = field(default_factory=dict)
    last_motion_scores: dict[chess.Square, float] = field(default_factory=dict)
    original_square_change_scores: Callable[
        [np.ndarray, np.ndarray],
        dict[chess.Square, float],
    ] | None = None


STATE = LocalDetectionState()


def load_config(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def save_config(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def normalized_settings(path: Path) -> tuple[bool, str]:
    config = load_config(path)
    sensitivity = str(
        config.get("local_detection_sensitivity", DEFAULT_SENSITIVITY)
    ).lower()
    if sensitivity not in SENSITIVITY_OPTIONS:
        sensitivity = DEFAULT_SENSITIVITY
    return bool(config.get("local_detection_beta", False)), sensitivity


def configure(path: Path) -> None:
    enabled, sensitivity = normalized_settings(path)
    STATE.enabled = enabled
    STATE.sensitivity = sensitivity
    STATE.current_unstable = frozenset()
    STATE.ignore_until.clear()
    STATE.last_motion_scores.clear()


def square_motion_scores(
    previous: np.ndarray,
    current: np.ndarray,
) -> dict[chess.Square, float]:
    """Measure motion independently inside each of the 64 playing squares."""
    if previous.shape != current.shape:
        return {square: 255.0 for square in chess.SQUARES}

    previous_gray = cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY)
    current_gray = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
    inset = max(5, int(SQUARE_PIXELS * 0.12))
    scores: dict[chess.Square, float] = {}

    for rank_from_top in range(8):
        for file_index in range(8):
            y0 = BOARD_MARGIN_PIXELS + rank_from_top * SQUARE_PIXELS + inset
            y1 = BOARD_MARGIN_PIXELS + (rank_from_top + 1) * SQUARE_PIXELS - inset
            x0 = BOARD_MARGIN_PIXELS + file_index * SQUARE_PIXELS + inset
            x1 = BOARD_MARGIN_PIXELS + (file_index + 1) * SQUARE_PIXELS - inset
            region_previous = previous_gray[y0:y1, x0:x1]
            region_current = current_gray[y0:y1, x0:x1]
            score = float(np.mean(cv2.absdiff(region_previous, region_current)))
            square = chess.square(file_index, 7 - rank_from_top)
            scores[square] = score
    return scores


def update_motion_state(
    previous: np.ndarray,
    current: np.ndarray,
    now: float | None = None,
) -> bool:
    """Return whether enough independent squares are stable for local analysis."""
    timestamp = time.monotonic() if now is None else now
    profile = PROFILES[STATE.sensitivity]
    scores = square_motion_scores(previous, current)
    unstable = frozenset(
        square
        for square, score in scores.items()
        if score >= profile.motion_threshold
    )

    for square in unstable:
        STATE.ignore_until[square] = timestamp + profile.occlusion_grace_seconds
    STATE.ignore_until = {
        square: deadline
        for square, deadline in STATE.ignore_until.items()
        if deadline > timestamp
    }
    STATE.current_unstable = unstable
    STATE.last_motion_scores = scores
    return len(unstable) <= profile.max_unstable_squares


def ignored_unexpected_squares(
    expected: frozenset[chess.Square] | set[chess.Square],
    now: float | None = None,
) -> frozenset[chess.Square]:
    timestamp = time.monotonic() if now is None else now
    recently_moving = {
        square
        for square, deadline in STATE.ignore_until.items()
        if deadline > timestamp
    }
    ignored = set(STATE.current_unstable).union(recently_moving)
    ignored.difference_update(expected)
    return frozenset(ignored)


def scores_for_candidate(
    scores: dict[chess.Square, float],
    expected: frozenset[chess.Square],
) -> dict[chess.Square, float]:
    if not STATE.enabled:
        return scores
    ignored = ignored_unexpected_squares(expected)
    if not ignored:
        return scores
    return {
        square: (0.0 if square in ignored else value)
        for square, value in scores.items()
    }


def rank_legal_moves(
    board: chess.Board,
    square_scores: dict[chess.Square, float],
    learned_patterns: dict[str, list[float]] | None = None,
    rejected_patterns: dict[str, list[float]] | None = None,
) -> list[RankedMove]:
    """Rank moves while ignoring only recently moving unrelated squares."""
    all_squares = set(chess.SQUARES)
    ranked: list[RankedMove] = []

    for move in board.legal_moves:
        expected = move_changed_squares(board, move)
        candidate_scores = scores_for_candidate(square_scores, expected)
        explained = float(np.mean([candidate_scores[sq] for sq in expected]))
        unexpected_values = sorted(
            (
                candidate_scores[sq]
                for sq in all_squares - set(expected)
            ),
            reverse=True,
        )
        unexpected = (
            float(np.mean(unexpected_values[:3]))
            if unexpected_values
            else 0.0
        )
        size_penalty = max(0, len(expected) - 2) * 0.35
        score = explained - (0.72 * unexpected) - size_penalty

        observed = np.asarray(
            [candidate_scores[square] for square in chess.SQUARES],
            dtype=np.float64,
        )
        observed_norm = float(np.linalg.norm(observed))

        if learned_patterns:
            pattern = learned_patterns.get(move.uci())
            if pattern is not None and len(pattern) == 64:
                learned = np.asarray(pattern, dtype=np.float64)
                learned_norm = float(np.linalg.norm(learned))
                if observed_norm > 0 and learned_norm > 0:
                    similarity = float(
                        np.dot(observed, learned)
                        / (observed_norm * learned_norm)
                    )
                    score += max(0.0, similarity - 0.45) * 5.0

        if rejected_patterns:
            rejected = rejected_patterns.get(move.uci())
            if rejected is not None and len(rejected) == 64:
                learned_rejection = np.asarray(rejected, dtype=np.float64)
                rejection_norm = float(np.linalg.norm(learned_rejection))
                if observed_norm > 0 and rejection_norm > 0:
                    similarity = float(
                        np.dot(observed, learned_rejection)
                        / (observed_norm * rejection_norm)
                    )
                    score -= max(0.0, similarity - 0.45) * 6.0

        ranked.append(RankedMove(move, score, expected))

    promotion_order = {
        chess.QUEEN: 4,
        chess.ROOK: 3,
        chess.BISHOP: 2,
        chess.KNIGHT: 1,
        None: 0,
    }
    ranked.sort(
        key=lambda item: (
            item.score,
            promotion_order[item.move.promotion],
        ),
        reverse=True,
    )
    return ranked


def legal_move_fit(
    candidate: RankedMove,
    scores: dict[chess.Square, float],
) -> MoveFit:
    candidate_scores = scores_for_candidate(scores, candidate.expected_squares)
    strongest = max(candidate_scores.values(), default=0.0)
    if strongest < 7.0:
        return MoveFit(0.0, frozenset(), frozenset())

    active_threshold = max(7.0, strongest * 0.34)
    observed = frozenset(
        square
        for square, value in candidate_scores.items()
        if value >= active_threshold
    )
    explained = observed.intersection(candidate.expected_squares)
    required_visible = min(2, len(candidate.expected_squares))
    coverage = min(1.0, len(explained) / max(1, required_visible))
    observed_energy = sum(candidate_scores[square] for square in observed)
    explained_energy = sum(candidate_scores[square] for square in explained)
    precision = explained_energy / observed_energy if observed_energy else 0.0
    fit = (0.62 * precision) + (0.38 * coverage)
    return MoveFit(float(fit), observed, frozenset(explained))


def confidence_for(
    ranked: list[RankedMove],
    scores: dict[chess.Square, float],
) -> float:
    if not ranked:
        return 0.0
    candidate_scores = scores_for_candidate(
        scores,
        ranked[0].expected_squares,
    )
    strongest_change = max(candidate_scores.values(), default=0.0)
    if strongest_change < 7.0:
        return 0.0
    margin = ranked[0].score - (
        ranked[1].score if len(ranked) > 1 else 0.0
    )
    evidence = min(1.0, strongest_change / 24.0)
    separation = min(1.0, max(0.0, margin) / 9.0)
    return evidence * separation


def board_looks_restored(scores: dict[chess.Square, float]) -> bool:
    filtered = scores_for_candidate(scores, frozenset())
    strongest = sorted(filtered.values(), reverse=True)[:2]
    if not strongest:
        return True
    if strongest[0] >= 12.0:
        return False
    second = strongest[1] if len(strongest) > 1 else 0.0
    return strongest[0] + second < 13.5


def analyze_frame_consensus(
    board: chess.Board,
    reference: np.ndarray,
    frames: list[np.ndarray],
    fit_threshold: float,
) -> ConsensusAnalysis:
    if not frames:
        raise ValueError("At least one frame is required for consensus analysis.")

    prepared = [
        prepare_comparison_frame(reference, frame)
        for frame in frames
    ]
    score_function = STATE.original_square_change_scores
    if score_function is None:
        raise RuntimeError("Local detection was not installed correctly.")
    score_sets = [
        score_function(reference, frame)
        for frame in prepared
    ]
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
    ambiguous = (
        move is None
        and select_consensus_move(all_candidates) is None
    )
    averaged_scores = average_square_scores(score_sets)
    ranked = rank_legal_moves(board, averaged_scores)
    if move is not None:
        ranked.sort(key=lambda candidate: candidate.move != move)
    confidence_values = [
        value
        for voted_move, value in vote_confidences
        if voted_move == move
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


def experimental_settings_screen(config_path: Path) -> None:
    enabled, sensitivity = normalized_settings(config_path)
    window = "Chess Camera - Experimental Features"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 760, 500)
    queue: list[str] = []
    buttons: list[Button] = []
    message = "Beta feature. Normal sensitivity is recommended."

    def mouse(
        event: int,
        x: int,
        y: int,
        _flags: int,
        _data: object,
    ) -> None:
        if event == cv2.EVENT_LBUTTONUP:
            action = pregame_ui.clicked_action(buttons, x, y)
            if action:
                queue.append(action)

    cv2.setMouseCallback(window, mouse)
    while True:
        view = np.zeros((500, 760, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        ui._put(
            view,
            "Experimental Features",
            (48, 62),
            (100, 220, 255),
            0.95,
            2,
        )
        ui._put(
            view,
            "64-SQUARE LOCAL DETECTION (BETA)",
            (48, 125),
            (165, 175, 190),
            0.50,
        )
        ui._put(
            view,
            "Allows unrelated squares to keep moving while the move squares settle.",
            (48, 165),
            (185, 195, 210),
            0.46,
        )
        ui._put(
            view,
            f"Feature: {'ON' if enabled else 'OFF'}",
            (48, 225),
            (120, 255, 170) if enabled else (180, 185, 195),
            0.65,
        )
        ui._put(
            view,
            f"Sensitivity: {sensitivity.upper()}",
            (48, 275),
            (120, 220, 255),
            0.62,
        )
        buttons = [
            Button(
                "toggle",
                "TURN OFF" if enabled else "TURN ON",
                470,
                194,
                220,
                48,
                active=not enabled,
            ),
            Button("previous", "< SENSITIVITY", 390, 254, 145, 46),
            Button("next", "SENSITIVITY >", 550, 254, 145, 46),
            Button(
                "save",
                "SAVE EXPERIMENTAL SETTINGS",
                48,
                365,
                410,
                58,
                active=True,
            ),
            Button("back", "BACK", 490, 365, 205, 58),
        ]
        for item in buttons:
            pregame_ui.draw_button(view, item)
        ui._put(
            view,
            message[:86],
            (48, 468),
            (120, 220, 255),
            0.43,
        )
        cv2.imshow(window, view)
        key = cv2.waitKey(20) & 0xFF
        action = queue.pop(0) if queue else None

        if action == "toggle":
            enabled = not enabled
        elif action == "previous":
            index = SENSITIVITY_OPTIONS.index(sensitivity)
            sensitivity = SENSITIVITY_OPTIONS[
                (index - 1) % len(SENSITIVITY_OPTIONS)
            ]
        elif action == "next":
            index = SENSITIVITY_OPTIONS.index(sensitivity)
            sensitivity = SENSITIVITY_OPTIONS[
                (index + 1) % len(SENSITIVITY_OPTIONS)
            ]
        elif action == "save":
            config = load_config(config_path)
            config["local_detection_beta"] = enabled
            config["local_detection_sensitivity"] = sensitivity
            save_config(config_path, config)
            configure(config_path)
            message = (
                "Saved. The next game will use 64-square local detection."
                if enabled
                else "Saved. Standard full-board stability detection will be used."
            )
        elif action == "back" or key == 27:
            cv2.destroyWindow(window)
            return

        try:
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                return
        except cv2.error:
            return


def settings_hub(
    target: ModuleType,
    engine_settings: Callable[[], None],
) -> None:
    window = "Chess Camera - Settings"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 760, 570)
    buttons = [
        Button(
            "camera",
            "ADVANCED CAMERA SETTINGS",
            85,
            135,
            590,
            68,
            active=True,
        ),
        Button(
            "experimental",
            "EXPERIMENTAL FEATURES",
            85,
            225,
            590,
            68,
        ),
        Button(
            "engine",
            "ANALYSIS ENGINE SETTINGS",
            85,
            315,
            590,
            68,
        ),
        Button("back", "BACK", 245, 455, 270, 58),
    ]
    queue: list[str] = []

    def mouse(
        event: int,
        x: int,
        y: int,
        _flags: int,
        _data: object,
    ) -> None:
        if event == cv2.EVENT_LBUTTONUP:
            action = pregame_ui.clicked_action(buttons, x, y)
            if action:
                queue.append(action)

    cv2.setMouseCallback(window, mouse)
    while True:
        view = np.zeros((570, 760, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        ui._put(view, "Settings", (55, 65), (100, 220, 255), 1.0, 2)
        ui._put(
            view,
            "Configure cameras, beta detection, or the local analysis engine.",
            (55, 103),
            (175, 185, 200),
            0.46,
        )
        for item in buttons:
            pregame_ui.draw_button(view, item)
        cv2.imshow(window, view)
        key = cv2.waitKey(20) & 0xFF
        action = queue.pop(0) if queue else None

        if action == "camera":
            cv2.destroyWindow(window)
            camera_advanced.camera_settings_screen(
                target,
                target.CONFIG_PATH,
            )
            cv2.namedWindow(window, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(window, 760, 570)
            cv2.setMouseCallback(window, mouse)
        elif action == "experimental":
            cv2.destroyWindow(window)
            experimental_settings_screen(target.CONFIG_PATH)
            cv2.namedWindow(window, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(window, 760, 570)
            cv2.setMouseCallback(window, mouse)
        elif action == "engine":
            cv2.destroyWindow(window)
            engine_settings()
            cv2.namedWindow(window, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(window, 760, 570)
            cv2.setMouseCallback(window, mouse)
        elif action == "back" or key == 27:
            cv2.destroyWindow(window)
            return

        try:
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                return
        except cv2.error:
            return


def install(
    target: ModuleType,
    navigation: ModuleType,
    engine_settings: Callable[[], None],
) -> None:
    if getattr(target, "_local_detection_installed", False):
        return

    original_open = target.open_camera
    original_frame_motion = target.frame_motion_score
    original_rank = target.rank_legal_moves
    original_fit = target.legal_move_fit
    original_confidence = target.confidence_for
    original_restored = target.board_looks_restored
    original_consensus = target.analyze_frame_consensus
    original_panel = target.render_camera_panel
    STATE.original_square_change_scores = target.square_change_scores

    def open_camera(index: int):
        configure(target.CONFIG_PATH)
        return original_open(index)

    def frame_motion(
        previous: np.ndarray,
        current: np.ndarray,
        sample_step: int = 3,
    ) -> float:
        if not STATE.enabled:
            return original_frame_motion(previous, current, sample_step)
        return 0.0 if update_motion_state(previous, current) else 10.0

    def ranked(
        board: chess.Board,
        scores: dict[chess.Square, float],
        learned_patterns: dict[str, list[float]] | None = None,
        rejected_patterns: dict[str, list[float]] | None = None,
    ) -> list[RankedMove]:
        if not STATE.enabled:
            return original_rank(
                board,
                scores,
                learned_patterns,
                rejected_patterns,
            )
        return rank_legal_moves(
            board,
            scores,
            learned_patterns,
            rejected_patterns,
        )

    def fit_move(
        candidate: RankedMove,
        scores: dict[chess.Square, float],
    ) -> MoveFit:
        if not STATE.enabled:
            return original_fit(candidate, scores)
        return legal_move_fit(candidate, scores)

    def confidence(
        candidates: list[RankedMove],
        scores: dict[chess.Square, float],
    ) -> float:
        if not STATE.enabled:
            return original_confidence(candidates, scores)
        return confidence_for(candidates, scores)

    def restored(scores: dict[chess.Square, float]) -> bool:
        if not STATE.enabled:
            return original_restored(scores)
        return board_looks_restored(scores)

    def consensus(
        board: chess.Board,
        reference: np.ndarray,
        frames: list[np.ndarray],
        fit_threshold: float,
    ) -> ConsensusAnalysis:
        if not STATE.enabled:
            return original_consensus(
                board,
                reference,
                frames,
                fit_threshold,
            )
        return analyze_frame_consensus(
            board,
            reference,
            frames,
            fit_threshold,
        )

    def camera_panel(
        board_view: np.ndarray,
        detection_mode_name: str,
        display_fps: float,
        stability_progress: float,
        fast_mode: bool,
    ) -> np.ndarray:
        label = detection_mode_name
        if STATE.enabled:
            label = f"{detection_mode_name} / LOCAL64"
        return original_panel(
            board_view,
            label,
            display_fps,
            stability_progress,
            fast_mode,
        )

    target.open_camera = open_camera
    target.frame_motion_score = frame_motion
    target.rank_legal_moves = ranked
    target.legal_move_fit = fit_move
    target.confidence_for = confidence
    target.board_looks_restored = restored
    target.analyze_frame_consensus = consensus
    target.render_camera_panel = camera_panel
    navigation.settings_screen = lambda: settings_hub(
        target,
        engine_settings,
    )
    configure(target.CONFIG_PATH)
    target._local_detection_installed = True
