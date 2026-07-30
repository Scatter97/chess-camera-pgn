from pathlib import Path
import time

import chess
import chess.pgn
import cv2
import numpy as np

from app import (
    manual_clock_player_for_key,
    render_virtual_board,
    select_camera_backend,
    select_promotion_candidate,
)
from builtin_clock import BuiltInChessClock, ClockSettings, ManualClockController
from clock_reader import (
    BackgroundClockReader,
    BothClocks,
    ClockReading,
    detect_active_clock_side,
    format_pgn_clock,
    parse_clock_text,
)
from chess_tracker import (
    RankedMove,
    legal_move_fit,
    move_changed_squares,
    rank_legal_moves,
    write_pgn,
)
from game_rules import automatic_outcome, claimable_draw_reason
from pregame_ui import (
    GameSetup,
    apply_setup_action,
    clicked_action,
    render_setup_screen,
    update_text_field,
)


def blank_scores() -> dict[int, float]:
    return {square: 0.0 for square in chess.SQUARES}


def test_native_camera_backends() -> None:
    assert select_camera_backend("linux") == cv2.CAP_V4L2
    assert select_camera_backend("linux2") == cv2.CAP_V4L2
    assert select_camera_backend("win32") == cv2.CAP_DSHOW
    assert select_camera_backend("darwin") == cv2.CAP_AVFOUNDATION


def test_virtual_board_tracks_position_and_last_move() -> None:
    board = chess.Board()
    starting_view = render_virtual_board(board)
    assert starting_view.shape == (620, 620, 3)

    move = chess.Move.from_uci("e2e4")
    board.push(move)
    moved_view = render_virtual_board(board, move)
    assert moved_view.shape == starting_view.shape
    assert not np.array_equal(starting_view, moved_view)


def test_background_clock_reader_returns_tagged_result() -> None:
    expected = BothClocks(
        ClockReading("1:00", 60.0, 0.99),
        ClockReading("0:59", 59.0, 0.98),
    )

    class FakeReader:
        def read(self, _frame: np.ndarray, _corners: list[list[float]]) -> BothClocks:
            return expected

    worker = BackgroundClockReader(reader_factory=FakeReader)
    frame = np.zeros((20, 20, 3), dtype=np.uint8)
    assert worker.submit_move(frame, [[0, 0], [19, 0], [19, 19], [0, 19]], "m1")

    deadline = time.monotonic() + 2.0
    results = []
    while not results and time.monotonic() < deadline:
        results = worker.poll()
        time.sleep(0.01)
    assert worker.close(timeout=2.0)
    assert len(results) == 1
    assert results[0].tag == "m1"
    assert results[0].clocks == expected
    assert results[0].error is None


def test_active_clock_side_detection() -> None:
    frame = np.zeros((960, 480, 3), dtype=np.uint8)
    frame[:430] = (50, 50, 50)
    frame[550:] = (190, 150, 110)
    corners = [[0, 0], [479, 0], [479, 959], [0, 959]]
    assert detect_active_clock_side(frame, corners) == "bottom"

    frame[:430] = (190, 150, 110)
    frame[550:] = (50, 50, 50)
    assert detect_active_clock_side(frame, corners) == "top"


def test_normal_move_changes_two_squares() -> None:
    board = chess.Board()
    move = chess.Move.from_uci("e2e4")
    assert move_changed_squares(board, move) == {chess.E2, chess.E4}


def test_castling_includes_rook_squares() -> None:
    board = chess.Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    move = chess.Move.from_uci("e1g1")
    assert move_changed_squares(board, move) == {
        chess.E1,
        chess.G1,
        chess.H1,
        chess.F1,
    }


def test_en_passant_includes_captured_pawn() -> None:
    board = chess.Board("8/8/8/3pP3/8/8/8/4K2k w - d6 0 1")
    move = chess.Move.from_uci("e5d6")
    assert move_changed_squares(board, move) == {
        chess.E5,
        chess.D6,
        chess.D5,
    }


def test_ranker_finds_e2e4() -> None:
    board = chess.Board()
    scores = blank_scores()
    scores[chess.E2] = 25.0
    scores[chess.E4] = 23.0
    ranked = rank_legal_moves(board, scores)
    assert ranked[0].move == chess.Move.from_uci("e2e4")


def test_legal_move_has_high_fit() -> None:
    board = chess.Board()
    scores = blank_scores()
    scores[chess.E2] = 25.0
    scores[chess.E4] = 23.0
    candidate = rank_legal_moves(board, scores)[0]
    assert legal_move_fit(candidate, scores).score > 0.9


def test_illegal_move_has_low_fit() -> None:
    board = chess.Board()
    scores = blank_scores()
    scores[chess.E2] = 25.0
    scores[chess.E5] = 24.0  # e2-e5 is not legal from the starting position
    candidate = rank_legal_moves(board, scores)[0]
    assert legal_move_fit(candidate, scores).score < 0.66


def test_pgn_round_trip(tmp_path: Path) -> None:
    moves = [
        chess.Move.from_uci("e2e4"),
        chess.Move.from_uci("e7e5"),
        chess.Move.from_uci("g1f3"),
    ]
    target = tmp_path / "game.pgn"
    write_pgn(moves, target)

    with target.open(encoding="utf-8") as source:
        game = chess.pgn.read_game(source)
    assert game is not None
    assert list(game.mainline_moves()) == moves


def test_clock_text_parsing_and_formatting() -> None:
    assert parse_clock_text("0:59") == 59
    assert parse_clock_text("10:00") == 600
    assert parse_clock_text("1:02:03") == 3723
    assert parse_clock_text("9.8") == 9.8
    assert format_pgn_clock(59) == "0:00:59"
    assert format_pgn_clock(65.4) == "0:01:05.4"


def test_pgn_contains_per_move_clocks(tmp_path: Path) -> None:
    moves = [chess.Move.from_uci("e2e4"), chess.Move.from_uci("e7e5")]
    target = tmp_path / "timed_game.pgn"
    write_pgn(moves, target, clocks=[59.0, 58.4])
    text = target.read_text(encoding="utf-8")
    assert "[%clk 0:00:59]" in text
    assert "[%clk 0:00:58.4]" in text


def test_pgn_contains_player_information(tmp_path: Path) -> None:
    target = tmp_path / "players.pgn"
    write_pgn(
        [],
        target,
        headers={
            "Event": "Friday Match",
            "White": "Alice",
            "Black": "Bob",
        },
    )
    text = target.read_text(encoding="utf-8")
    assert '[Event "Friday Match"]' in text
    assert '[White "Alice"]' in text
    assert '[Black "Bob"]' in text


def test_builtin_clock_supports_asymmetric_time_and_increment() -> None:
    clock = BuiltInChessClock(
        ClockSettings(
            white_initial_seconds=60,
            black_initial_seconds=120,
            white_increment_seconds=2,
            black_increment_seconds=5,
        )
    )
    clock.start(100.0)

    assert clock.complete_move(True, 110.0) == 52.0
    assert clock.remaining(False, 120.0) == 110.0
    assert clock.complete_move(False, 125.0) == 110.0
    assert clock.remaining(True, 130.0) == 47.0


def test_builtin_clock_undo_restores_movers_clock() -> None:
    clock = BuiltInChessClock(
        ClockSettings(
            white_initial_seconds=60,
            black_initial_seconds=120,
            white_increment_seconds=2,
            black_increment_seconds=5,
        )
    )
    clock.start(100.0)
    clock.complete_move(True, 110.0)
    clock.complete_move(False, 125.0)

    assert clock.undo(130.0)
    assert clock.active_white is False
    assert clock.remaining(False, 130.0) == 105.0
    assert clock.remaining(True, 130.0) == 52.0


def test_clickable_pregame_settings_update_clock_and_modes() -> None:
    setup = GameSetup()
    setup = apply_setup_action(setup, "clock_builtin")
    setup = apply_setup_action(setup, "white_minus60")
    setup = apply_setup_action(setup, "black_plus10")
    setup = apply_setup_action(setup, "black_inc_plus")
    setup = apply_setup_action(setup, "mode_bullet")
    setup = apply_setup_action(setup, "clock_switch_manual")

    assert setup.clock_source == "builtin"
    assert setup.clock_settings.white_initial_seconds == 240
    assert setup.clock_settings.black_initial_seconds == 310
    assert setup.clock_settings.black_increment_seconds == 1
    assert setup.bullet_mode
    assert setup.auto_accept
    assert setup.manual_clock_switch


def test_pregame_text_fields_and_click_targets() -> None:
    setup = GameSetup(white_name="")
    for character in "Josh":
        setup = update_text_field(setup, "white", ord(character))
    screen, buttons = render_setup_screen(setup, "white")

    assert setup.white_name == "Josh"
    assert screen.shape == (760, 1100, 3)
    start = next(button for button in buttons if button.action == "start")
    manual_clock_option = next(
        button for button in buttons if button.action == "clock_switch_manual"
    )
    assert clicked_action(buttons, start.x + 5, start.y + 5) == "start"
    assert manual_clock_option.label == "Player keys A / L"


def test_promotion_popup_choice_replaces_duplicate_variants() -> None:
    expected_squares = frozenset({chess.A7, chess.A8})
    candidates = [
        RankedMove(chess.Move.from_uci("a7a8q"), 20.0, expected_squares),
        RankedMove(chess.Move.from_uci("a7a8r"), 20.0, expected_squares),
        RankedMove(chess.Move.from_uci("a7a8b"), 20.0, expected_squares),
        RankedMove(chess.Move.from_uci("a7a8n"), 20.0, expected_squares),
        RankedMove(
            chess.Move.from_uci("e1e2"),
            4.0,
            frozenset({chess.E1, chess.E2}),
        ),
    ]

    selected = select_promotion_candidate(candidates, chess.KNIGHT)

    assert selected[0].move == chess.Move.from_uci("a7a8n")
    assert [candidate.move for candidate in selected].count(
        chess.Move.from_uci("a7a8n")
    ) == 1
    assert chess.Move.from_uci("e1e2") in [candidate.move for candidate in selected]


def test_checkmate_and_stalemate_outcomes() -> None:
    checkmate = chess.Board()
    for move in ["f2f3", "e7e5", "g2g4", "d8h4"]:
        checkmate.push_uci(move)
    outcome = automatic_outcome(checkmate)
    assert outcome is not None
    assert outcome.result == "0-1"
    assert "Black wins" in outcome.message

    stalemate = chess.Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    outcome = automatic_outcome(stalemate)
    assert outcome is not None
    assert outcome.result == "1/2-1/2"
    assert outcome.title == "Stalemate"


def test_insufficient_material_is_automatic_draw() -> None:
    board = chess.Board("8/8/8/8/8/8/7k/K7 w - - 0 1")
    outcome = automatic_outcome(board)
    assert outcome is not None
    assert outcome.title == "Insufficient material"
    assert outcome.result == "1/2-1/2"


def test_threefold_claim_and_fivefold_automatic_draw() -> None:
    board = chess.Board()
    cycle = ["g1f3", "g8f6", "f3g1", "f6g8"]
    for _ in range(2):
        for move in cycle:
            board.push_uci(move)
    assert claimable_draw_reason(board) == "Threefold repetition"
    assert automatic_outcome(board) is None

    for _ in range(2):
        for move in cycle:
            board.push_uci(move)
    outcome = automatic_outcome(board)
    assert outcome is not None
    assert outcome.title == "Fivefold repetition"


def test_fifty_move_claim_and_seventy_five_move_automatic_draw() -> None:
    claimable = chess.Board("8/8/8/8/8/8/R6k/K7 w - - 100 51")
    assert claimable_draw_reason(claimable) == "50-move rule"
    assert automatic_outcome(claimable) is None

    automatic = chess.Board("8/8/8/8/8/8/R6k/K7 w - - 150 76")
    outcome = automatic_outcome(automatic)
    assert outcome is not None
    assert outcome.title == "75-move rule"


def test_pgn_writes_final_result(tmp_path: Path) -> None:
    target = tmp_path / "finished_game.pgn"
    write_pgn([], target, result="1/2-1/2")
    text = target.read_text(encoding="utf-8")
    assert '[Result "1/2-1/2"]' in text
    assert text.rstrip().endswith("1/2-1/2")


def test_manual_clock_press_waits_for_camera_move_and_can_be_cancelled() -> None:
    clock = BuiltInChessClock(
        ClockSettings(
            white_initial_seconds=60,
            black_initial_seconds=120,
            white_increment_seconds=2,
            black_increment_seconds=5,
        )
    )
    controller = ManualClockController()
    clock.start(100.0)

    record = controller.press(clock, True, 110.0)
    assert record.recorded_seconds == 52.0
    assert controller.ready_for(True)
    assert clock.active_white is False
    assert controller.consume(True) == 52.0
    assert controller.pending is None

    record = controller.press(clock, False, 120.0)
    assert record.recorded_seconds == 115.0
    assert controller.cancel(clock, 121.0)
    assert controller.pending is None
    assert clock.active_white is False


def test_manual_clock_keys_are_split_across_keyboard_sides() -> None:
    assert manual_clock_player_for_key(ord("a")) is chess.WHITE
    assert manual_clock_player_for_key(ord("A")) is chess.WHITE
    assert manual_clock_player_for_key(ord("l")) is chess.BLACK
    assert manual_clock_player_for_key(ord("L")) is chess.BLACK
    assert manual_clock_player_for_key(ord("x")) is None
