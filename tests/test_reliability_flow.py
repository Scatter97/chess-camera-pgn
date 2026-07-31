from pathlib import Path

import chess
import pytest

from board_profiles import BoardProfile
from builtin_clock import BuiltInChessClock, ClockSettings
from training_settings import profile_snapshot, restore_profile


def _move_scores() -> dict[chess.Square, float]:
    scores = {square: 0.0 for square in chess.SQUARES}
    scores[chess.E2] = 20.0
    scores[chess.E4] = 20.0
    return scores


def test_detection_wrong_removes_accepted_sample_and_keeps_rejection() -> None:
    profile = BoardProfile("Test board")
    move = chess.Move.from_uci("e2e4")
    scores = _move_scores()
    before_move = profile_snapshot(profile)

    profile.observe_move(move, scores, {chess.E2, chess.E4})
    assert profile.sample_count == 1

    restore_profile(profile, before_move)
    profile.observe_rejection(move, scores, weight=3)

    assert profile.sample_count == 0
    assert profile.rejected_patterns[move.uci()].count == 3


def test_corrected_move_resumes_with_opponents_clock_running() -> None:
    clock = BuiltInChessClock(
        ClockSettings(
            white_initial_seconds=300.0,
            black_initial_seconds=300.0,
            white_increment_seconds=2.0,
            black_increment_seconds=2.0,
        )
    )
    clock.start(0.0, white_to_move=True)
    retrying_side = clock.active_white
    clock.pause(5.0)

    assert retrying_side is chess.WHITE
    assert clock.active_white is None
    assert clock.white_seconds == pytest.approx(295.0)

    correction_time = 10.0
    clock.start(correction_time, retrying_side)
    recorded = clock.complete_move(chess.WHITE, correction_time)

    assert recorded == pytest.approx(297.0)
    assert clock.active_white is chess.BLACK
    assert clock.remaining(chess.BLACK, 12.0) == pytest.approx(298.0)


def test_release_startup_installs_completed_reliability_features() -> None:
    startup = Path("chess_camera.py").read_text(encoding="utf-8")

    assert (
        "runtime_0397_patch.install(app)" in startup
        or "runtime_multi_move_patch.install(app)" in startup
    )
    assert "training_settings.install(app, navigation)" in startup
    assert "piece_theme_system.install(app)" in startup
    assert "feature_settings.install(app, navigation)" in startup
