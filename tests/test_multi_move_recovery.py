from __future__ import annotations

from pathlib import Path

import chess

from chess_camera_app.game import multi_move_recovery as recovery
from chess_camera_app.runtime import runtime_multi_move_patch
from chess_camera_app.game.chess_tracker import move_changed_squares


def _scores(*active: chess.Square) -> dict[chess.Square, float]:
    values = {square: 0.0 for square in chess.SQUARES}
    for square in active:
        values[square] = 22.0
    return values


def _event(
    board: chess.Board,
    move: chess.Move,
    timestamp: float,
) -> recovery.ChangeEvent:
    squares = move_changed_squares(board, move)
    scores = _scores(*squares)
    return recovery.ChangeEvent(timestamp, squares, scores, 0.95)


def test_two_ply_recovery_finds_legal_sequence() -> None:
    board = chess.Board()
    scores = _scores(chess.E2, chess.E4, chess.E7, chess.E5)

    result = recovery.search_sequences(board, scores, max_depth=2)

    assert result is not None
    assert result.candidates
    assert tuple(move.uci() for move in result.candidates[0].moves) == (
        "e2e4",
        "e7e5",
    )
    assert result.candidates[0].final_position_score >= 0.90


def test_temporal_events_disambiguate_three_ply_sequence() -> None:
    board = chess.Board()
    first = chess.Move.from_uci("e2e4")
    second = chess.Move.from_uci("e7e5")
    third = chess.Move.from_uci("g1f3")

    event_board = board.copy(stack=False)
    events = [_event(event_board, first, 1.0)]
    event_board.push(first)
    events.append(_event(event_board, second, 2.0))
    event_board.push(second)
    events.append(_event(event_board, third, 3.0))

    scores = _scores(
        chess.E2,
        chess.E4,
        chess.E7,
        chess.E5,
        chess.G1,
        chess.F3,
    )
    result = recovery.search_sequences(
        board,
        scores,
        events,
        max_depth=3,
        beam_width=180,
    )

    assert result is not None
    assert tuple(move.uci() for move in result.candidates[0].moves) == (
        "e2e4",
        "e7e5",
        "g1f3",
    )
    assert result.candidates[0].temporal_score > 0.85
    assert result.ambiguous is False


def test_same_final_position_without_timing_is_marked_ambiguous() -> None:
    board = chess.Board()
    scores = _scores(
        chess.E2,
        chess.E4,
        chess.E7,
        chess.E5,
        chess.G1,
        chess.F3,
    )

    result = recovery.search_sequences(
        board,
        scores,
        max_depth=3,
        beam_width=180,
    )

    assert result is not None
    matching = [
        candidate
        for candidate in result.candidates
        if candidate.final_board.board_fen()
        == result.candidates[0].final_board.board_fen()
    ]
    assert len(matching) >= 2
    assert result.ambiguous is True


def test_settings_are_clamped_and_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "camera_config.json"
    recovery.save_settings(
        path,
        recovery.RecoverySettings(
            enabled=True,
            max_depth=9,
            auto_accept=True,
            auto_threshold=0.40,
        ),
    )

    loaded = recovery.load_settings(path)

    assert loaded.enabled is True
    assert loaded.max_depth == 3
    assert loaded.auto_accept is True
    assert loaded.auto_threshold == recovery.MIN_AUTO_THRESHOLD


def test_experimental_runtime_patch_compiles() -> None:
    source = Path("chess_camera_app/core/app.py").read_text(encoding="utf-8")
    patched = runtime_multi_move_patch.apply_source_patches(source)

    assert "multi_move_ui.search_sequences" in patched
    assert "multi_move_history.observe" in patched
    compile(patched, "chess_camera_app/core/app.py", "exec")


def test_experimental_startup_isolated_from_stable_runtime() -> None:
    startup = Path("chess_camera.py").read_text(encoding="utf-8")

    assert "runtime_multi_move_patch.install(app)" in startup
    assert "multi_move_settings.install(feature_settings, app)" in startup
    assert "runtime_0397_patch.install(app)" not in startup

