import chess

from chess_camera_app.calibration.board_profiles import BoardProfile
from chess_camera_app.ui.training_settings import profile_snapshot, restore_profile


def test_restore_profile_removes_undone_training_sample() -> None:
    profile = BoardProfile("Test board")
    before = profile_snapshot(profile)
    move = chess.Move.from_uci("e2e4")
    scores = {square: 0.0 for square in chess.SQUARES}
    scores[chess.E2] = 20.0
    scores[chess.E4] = 20.0

    profile.observe_move(move, scores, {chess.E2, chess.E4})
    assert profile.sample_count == 1

    restore_profile(profile, before)
    assert profile.sample_count == 0
    assert profile.name == "Test board"
