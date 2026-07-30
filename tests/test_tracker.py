from pathlib import Path
import json
import sys
import time

import chess
import chess.pgn
import cv2
import numpy as np

from board_profiles import BoardProfile, BoardProfileStore
from app import (
    apply_setup_suggestion,
    apply_midgame_clock_adjustment,
    detection_profile,
    frame_motion_score,
    illegal_warning_button,
    manual_correction_candidates,
    manual_clock_player_for_key,
    most_used_values,
    normalize_usage_counts,
    pause_clock_for_illegal_move,
    render_camera_panel,
    render_grid_verification,
    render_virtual_board,
    resume_clock_after_illegal_move,
    remember_used_value,
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
    BOARD_MARGIN_PIXELS,
    RankedMove,
    WARP_PIXELS,
    analyze_frame_consensus,
    board_looks_restored,
    legal_move_fit,
    move_changed_squares,
    orient_board_image,
    prepare_comparison_frame,
    rank_legal_moves,
    select_consensus_move,
    square_change_scores,
    warp_board,
    write_pgn,
)
from game_rules import automatic_outcome, claimable_draw_reason, timeout_outcome
from game_analysis import (
    PositionEvaluation,
    build_game_review,
    classify_move,
    find_stockfish,
    move_accuracy,
    probe_uci_engine,
    save_analysis_report,
)
from pregame_ui import (
    Button,
    DEFAULT_PINNED_TIME_CONTROLS,
    GameSetup,
    apply_time_slider_value,
    apply_setup_action,
    button_text_scale,
    clicked_action,
    draw_button,
    normalize_pinned_time_controls,
    render_setup_screen,
    slider_value_from_x,
    toggle_pinned_time_control,
    update_text_field,
)


def blank_scores() -> dict[int, float]:
    return {square: 0.0 for square in chess.SQUARES}


def test_native_camera_backends() -> None:
    assert select_camera_backend("linux") == cv2.CAP_V4L2
    assert select_camera_backend("linux2") == cv2.CAP_V4L2
    assert select_camera_backend("win32") == cv2.CAP_DSHOW
    assert select_camera_backend("darwin") == cv2.CAP_AVFOUNDATION


def test_camera_diagnostics_are_outside_the_preview() -> None:
    board_view = np.full((300, 300, 3), (10, 20, 30), dtype=np.uint8)

    panel = render_camera_panel(board_view, "NORMAL", 5.1, 0.5, False)

    assert panel.shape == (620, 300, 3)
    assert tuple(panel[100, 100]) == (10, 20, 30)
    assert tuple(panel[29, 80]) == (80, 220, 120)
    assert tuple(panel[29, 220]) == (20, 20, 20)


def test_virtual_board_tracks_position_and_last_move() -> None:
    board = chess.Board()
    starting_view = render_virtual_board(board)
    assert starting_view.shape == (620, 620, 3)

    move = chess.Move.from_uci("e2e4")
    board.push(move)
    moved_view = render_virtual_board(board, move)
    assert moved_view.shape == starting_view.shape
    assert not np.array_equal(starting_view, moved_view)


def test_fast_detection_profile_and_reduced_motion_score() -> None:
    assert detection_profile(False, False) == ("NORMAL", 1.15, 1.0)
    assert detection_profile(True, False) == ("FAST", 0.35, 0.35)
    assert detection_profile(False, True) == ("BULLET", 0.22, 0.18)

    still = np.zeros((800, 800, 3), dtype=np.uint8)
    changed = still.copy()
    changed[200:600, 200:600] = 255
    assert frame_motion_score(still, still) == 0.0
    assert frame_motion_score(still, changed) > 1.6


def test_accuracy_boost_alignment_reduces_camera_and_light_noise() -> None:
    rng = np.random.default_rng(16)
    reference = rng.integers(20, 210, (800, 800, 3), dtype=np.uint8)
    transform = np.float32([[1, 0, 4], [0, 1, -3]])
    moved = cv2.warpAffine(
        reference,
        transform,
        (800, 800),
        borderMode=cv2.BORDER_REFLECT,
    )
    moved = np.clip(moved.astype(np.int16) + 18, 0, 255).astype(np.uint8)

    prepared = prepare_comparison_frame(reference, moved)
    raw_error = np.mean(
        np.abs(reference[12:-12, 12:-12].astype(np.int16) - moved[12:-12, 12:-12])
    )
    prepared_error = np.mean(
        np.abs(
            reference[12:-12, 12:-12].astype(np.int16)
            - prepared[12:-12, 12:-12]
        )
    )
    assert prepared_error < raw_error * 0.35


def test_accuracy_boost_requires_two_matching_frame_votes() -> None:
    e4 = chess.Move.from_uci("e2e4")
    d4 = chess.Move.from_uci("d2d4")
    assert select_consensus_move([e4, e4, d4]) == e4
    assert select_consensus_move([e4, d4]) is None


def test_accuracy_consensus_finds_move_across_lighting_changes() -> None:
    rng = np.random.default_rng(160)
    reference = rng.integers(
        35,
        195,
        (WARP_PIXELS, WARP_PIXELS, 3),
        dtype=np.uint8,
    )
    changed = reference.copy()
    e_file_start = BOARD_MARGIN_PIXELS + 4 * 100
    e2_rank_start = BOARD_MARGIN_PIXELS + 6 * 100
    e4_rank_start = BOARD_MARGIN_PIXELS + 4 * 100
    changed[e2_rank_start : e2_rank_start + 100, e_file_start : e_file_start + 100] = (
        245,
        20,
        210,
    )
    changed[e4_rank_start : e4_rank_start + 100, e_file_start : e_file_start + 100] = (
        245,
        20,
        210,
    )
    frames = [
        np.clip(changed.astype(np.int16) + offset, 0, 255).astype(np.uint8)
        for offset in (-7, 0, 9)
    ]

    result = analyze_frame_consensus(
        chess.Board(),
        reference,
        frames,
        fit_threshold=0.66,
    )

    assert result.move == chess.Move.from_uci("e2e4")
    assert result.valid_votes == 3
    assert result.frame.shape == reference.shape


def test_grid_verification_labels_all_squares() -> None:
    board_image = np.zeros(
        (WARP_PIXELS, WARP_PIXELS, 3),
        dtype=np.uint8,
    )
    verification = render_grid_verification(board_image)
    assert verification.shape == board_image.shape
    assert np.count_nonzero(verification) > 5000


def test_board_orientation_supports_all_four_camera_sides() -> None:
    board_image = np.arange(27, dtype=np.uint8).reshape(3, 3, 3)
    assert np.array_equal(
        orient_board_image(board_image, "bottom"),
        board_image,
    )
    assert np.array_equal(
        orient_board_image(board_image, "top"),
        cv2.rotate(board_image, cv2.ROTATE_180),
    )
    assert np.array_equal(
        orient_board_image(board_image, "left"),
        cv2.rotate(board_image, cv2.ROTATE_90_COUNTERCLOCKWISE),
    )
    assert np.array_equal(
        orient_board_image(board_image, "right"),
        cv2.rotate(board_image, cv2.ROTATE_90_CLOCKWISE),
    )


def test_padded_warp_keeps_space_outside_board() -> None:
    frame = np.zeros((300, 300, 3), dtype=np.uint8)
    frame[50:251, 50:251] = (100, 150, 200)
    corners = [[50, 50], [250, 50], [250, 250], [50, 250]]
    warped = warp_board(frame, corners)

    assert warped.shape == (WARP_PIXELS, WARP_PIXELS, 3)
    assert BOARD_MARGIN_PIXELS > 0
    assert np.mean(warped[BOARD_MARGIN_PIXELS + 20, BOARD_MARGIN_PIXELS + 20]) > 0


def test_first_and_eighth_rank_changes_are_detected_in_outer_margin() -> None:
    reference = np.zeros((WARP_PIXELS, WARP_PIXELS, 3), dtype=np.uint8)
    current = reference.copy()
    e_file_start = BOARD_MARGIN_PIXELS + 4 * 100
    current[
        BOARD_MARGIN_PIXELS + 800 : WARP_PIXELS,
        e_file_start : e_file_start + 100,
    ] = 255
    current[
        0:BOARD_MARGIN_PIXELS,
        e_file_start : e_file_start + 100,
    ] = 255

    scores = square_change_scores(reference, current)

    assert scores[chess.E1] > 7.0
    assert scores[chess.E8] > 7.0
    assert scores[chess.D1] == 0.0


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


def test_restored_board_tolerates_one_noisy_square() -> None:
    restored = blank_scores()
    restored[chess.E2] = 9.0
    restored[chess.E4] = 3.0
    assert board_looks_restored(restored)

    two_changed_squares = blank_scores()
    two_changed_squares[chess.E2] = 8.0
    two_changed_squares[chess.E5] = 8.0
    assert not board_looks_restored(two_changed_squares)

    one_strongly_changed_square = blank_scores()
    one_strongly_changed_square[chess.E2] = 18.0
    assert not board_looks_restored(one_strongly_changed_square)


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


def test_builtin_clock_reports_only_the_active_flagged_player() -> None:
    clock = BuiltInChessClock(ClockSettings(5, 20))
    clock.start(100.0, white_to_move=True)

    assert clock.flagged_player(104.9) is None
    assert clock.flagged_player(105.0) is chess.WHITE
    clock.pause(105.0)
    assert clock.flagged_player(200.0) is None


def test_timeout_result_awards_the_game_to_the_opponent() -> None:
    white_flag = timeout_outcome(True, "Alice", "Bob")
    black_flag = timeout_outcome(False, "Alice", "Bob")

    assert white_flag.result == "0-1"
    assert white_flag.title == "Time expired"
    assert white_flag.message == "Alice's time ran out. Bob wins."
    assert black_flag.result == "1-0"
    assert black_flag.message == "Bob's time ran out. Alice wins."


def test_clickable_pregame_settings_update_clock_and_modes() -> None:
    setup = GameSetup()
    setup = apply_setup_action(setup, "clock_builtin")
    setup = apply_setup_action(setup, "shared_minus60")
    setup = apply_setup_action(setup, "shared_inc_plus")
    assert setup.clock_settings.white_initial_seconds == 240
    assert setup.clock_settings.black_initial_seconds == 240
    assert setup.clock_settings.white_increment_seconds == 1
    assert setup.clock_settings.black_increment_seconds == 1

    setup = apply_setup_action(setup, "advanced_clock_toggle")
    setup = apply_setup_action(setup, "white_minus60")
    setup = apply_setup_action(setup, "black_plus10")
    setup = apply_setup_action(setup, "black_inc_plus")
    setup = apply_setup_action(setup, "mode_fast")
    setup = apply_setup_action(setup, "accuracy_toggle")
    setup = apply_setup_action(setup, "white_edge_left")
    assert setup.fast_mode
    assert not setup.bullet_mode
    assert setup.accuracy_boost
    assert setup.white_camera_edge == "left"
    setup = apply_setup_action(setup, "mode_bullet")
    setup = apply_setup_action(setup, "clock_switch_manual")

    assert setup.clock_source == "builtin"
    assert setup.separate_time_controls
    assert setup.clock_settings.white_initial_seconds == 180
    assert setup.clock_settings.black_initial_seconds == 250
    assert setup.clock_settings.black_increment_seconds == 2
    assert setup.bullet_mode
    assert not setup.fast_mode
    assert not setup.accuracy_boost
    assert setup.auto_accept
    assert setup.manual_clock_switch


def test_switching_back_to_shared_time_copies_white_settings() -> None:
    setup = GameSetup(
        clock_source="builtin",
        separate_time_controls=True,
        clock_settings=ClockSettings(180, 300, 2, 5),
    )

    setup = apply_setup_action(setup, "advanced_clock_toggle")

    assert not setup.separate_time_controls
    assert setup.clock_settings == ClockSettings(180, 180, 2, 2)


def test_shared_time_sliders_update_both_players() -> None:
    setup = GameSetup(clock_source="builtin")
    setup = apply_time_slider_value(setup, "slider_shared_minutes", 12)
    setup = apply_time_slider_value(setup, "slider_shared_increment", 7)

    assert setup.clock_settings == ClockSettings(720, 720, 7, 7)


def test_advanced_time_sliders_update_only_the_selected_player() -> None:
    setup = GameSetup(clock_source="builtin", separate_time_controls=True)
    setup = apply_time_slider_value(setup, "slider_white_minutes", 3)
    setup = apply_time_slider_value(setup, "slider_black_increment", 5)

    assert setup.clock_settings == ClockSettings(180, 300, 0, 5)


def test_slider_mouse_position_maps_to_its_full_range() -> None:
    minute_slider = Button("slider_shared_minutes", "", 600, 180, 460, 28)
    increment_slider = Button("slider_shared_increment", "", 600, 240, 460, 28)

    assert slider_value_from_x(minute_slider.action, minute_slider, 600) == 1
    assert slider_value_from_x(minute_slider.action, minute_slider, 1060) == 180
    assert slider_value_from_x(increment_slider.action, increment_slider, 600) == 0
    assert slider_value_from_x(increment_slider.action, increment_slider, 1060) == 60
    assert slider_value_from_x(minute_slider.action, minute_slider, 830) == 20
    assert slider_value_from_x(increment_slider.action, increment_slider, 830) == 10


def test_midgame_clock_adjustments_are_independent_and_clamped() -> None:
    white, black = apply_midgame_clock_adjustment(5, 20, "white_minus10")
    assert (white, black) == (0, 20)
    white, black = apply_midgame_clock_adjustment(white, black, "black_plus60")
    assert (white, black) == (0, 80)


def test_paused_builtin_clock_can_be_set_to_exact_remaining_times() -> None:
    clock = BuiltInChessClock(ClockSettings(60, 60))
    clock.start(100.0, white_to_move=False)
    clock.pause(110.0)

    clock.set_remaining(75, 95)

    assert clock.remaining(True, 200.0) == 75
    assert clock.remaining(False, 200.0) == 95


def test_pregame_text_fields_and_click_targets() -> None:
    setup = GameSetup(white_name="")
    for character in "Josh":
        setup = update_text_field(setup, "white", ord(character))
    screen, buttons = render_setup_screen(setup, "white")

    assert setup.white_name == "Josh"
    assert screen.shape == (920, 1100, 3)
    start = next(button for button in buttons if button.action == "start")
    manual_clock_option = next(
        button for button in buttons if button.action == "clock_switch_manual"
    )
    advanced_clock = next(
        button for button in buttons if button.action == "advanced_clock_toggle"
    )
    bullet_option = next(
        button for button in buttons if button.action == "mode_bullet"
    )
    assert clicked_action(buttons, start.x + 5, start.y + 5) == "start"
    assert manual_clock_option.label == "Player keys A / L"
    assert advanced_clock.label == "Advanced: separate clocks"
    assert bullet_option.label == "Bullet (BETA)"
    white_left = next(
        button for button in buttons if button.action == "white_edge_left"
    )
    assert clicked_action(buttons, white_left.x + 5, white_left.y + 5) == (
        "white_edge_left"
    )
    train = next(button for button in buttons if button.action == "profile_train")
    assert clicked_action(buttons, train.x + 5, train.y + 5) == "profile_train"
    engine = next(button for button in buttons if button.action == "select_engine")
    assert clicked_action(buttons, engine.x + 5, engine.y + 5) == "select_engine"
    rename = next(button for button in buttons if button.action == "profile_rename")
    reset = next(
        button for button in buttons if button.action == "profile_reset_training"
    )
    swap = next(button for button in buttons if button.action == "swap_players")
    assert rename.label == "Rename preset"
    assert reset.label == "Reset training"
    assert swap.label == "Swap sides"


def test_long_button_label_is_drawn_inside_its_box() -> None:
    button = Button("wrong_detection", "Detection wrong", 10, 15, 132, 34)

    scale = button_text_scale(button)
    text_width = cv2.getTextSize(
        button.label,
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        1,
    )[0][0]
    assert scale < 0.53
    assert text_width <= button.width - 12


def test_player_swap_and_editable_suggestions() -> None:
    setup = GameSetup(white_name="Alice", black_name="Bob", event_name="")
    setup = apply_setup_action(setup, "swap_players")
    assert setup.white_name == "Bob"
    assert setup.black_name == "Alice"

    setup = apply_setup_suggestion(
        setup,
        "suggest_event_0",
        ("Alice", "Bob"),
        ("Club night",),
    )
    setup = update_text_field(setup, "event", ord("!"))
    assert setup.event_name == "Club night!"

    _screen, buttons = render_setup_screen(
        setup,
        "white",
        player_suggestions=("Alice", "Bob"),
        event_suggestions=("Club night",),
    )
    assert any(button.action == "suggest_white_0" for button in buttons)
    assert not any(button.action == "suggest_event_0" for button in buttons)


def test_usage_counts_make_most_used_local_suggestions() -> None:
    counts = normalize_usage_counts(
        {" Bob ": 2, "Alice": 4, "Invalid": 0, 3: 5, "Bad": "x"}
    )
    remember_used_value(counts, " Bob ")
    remember_used_value(counts, "Carol")

    assert counts == {"Bob": 3, "Alice": 4, "Carol": 1}
    assert most_used_values(counts, 2) == ("Alice", "Bob")


def test_pinned_time_control_applies_to_both_players() -> None:
    setup = GameSetup(clock_source="builtin")

    setup = apply_setup_action(setup, "apply_preset_3+2")

    assert setup.clock_settings == ClockSettings(180, 180, 2, 2)


def test_advanced_clocks_hide_preset_controls() -> None:
    setup = GameSetup(clock_source="builtin", separate_time_controls=True)

    _screen, buttons = render_setup_screen(setup, None)

    assert not any(button.action == "choose_pinned_presets" for button in buttons)
    assert not any(button.action.startswith("apply_preset_") for button in buttons)


def test_ocr_keeps_preset_controls_visible_but_disabled() -> None:
    setup = GameSetup(clock_source="ocr")

    _screen, buttons = render_setup_screen(setup, None)

    chooser = next(
        button for button in buttons if button.action == "choose_pinned_presets"
    )
    presets = [
        button for button in buttons if button.action.startswith("apply_preset_")
    ]
    assert not chooser.enabled
    assert len(presets) == len(DEFAULT_PINNED_TIME_CONTROLS)
    assert all(not button.enabled for button in presets)


def test_pinned_preset_selection_is_known_unique_and_limited() -> None:
    selected: tuple[str, ...] = ()
    for label in ("1+0", "2+1", "3+0", "3+2", "5+0", "5+3", "10+0"):
        selected = toggle_pinned_time_control(selected, label)

    assert len(selected) == 6
    assert "10+0" not in selected
    assert toggle_pinned_time_control(selected, "3+0") == tuple(
        label for label in selected if label != "3+0"
    )
    assert normalize_pinned_time_controls(["3+2", "bad", "3+2", "1+0"]) == (
        "1+0",
        "3+2",
    )


def test_board_profiles_persist_calibration_and_training(tmp_path: Path) -> None:
    store = BoardProfileStore(tmp_path / "profiles")
    profile = store.ensure_default(
        board_corners=[[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]],
        phone_corners=[[9.0, 10.0]] * 4,
        white_camera_edge="left",
        bottom_clock_is_white=False,
    )
    board = chess.Board()
    move = chess.Move.from_uci("e2e4")
    scores = blank_scores()
    scores[chess.E2] = 25.0
    scores[chess.E4] = 23.0
    scores[chess.A1] = 4.0
    profile.observe_move(move, scores, move_changed_squares(board, move), weight=3)
    store.save(profile)

    reloaded_store = BoardProfileStore(tmp_path / "profiles")
    reloaded = reloaded_store.load()[0]
    assert reloaded.name == "Default board"
    assert reloaded.white_camera_edge == "left"
    assert not reloaded.bottom_clock_is_white
    assert reloaded.sample_count == 3
    assert reloaded.move_patterns["e2e4"].mean_scores[chess.E2] == 1.0
    assert reloaded.noise_mean[chess.A1] == 4.0


def test_board_profile_can_be_renamed_without_losing_data(tmp_path: Path) -> None:
    store = BoardProfileStore(tmp_path / "profiles")
    profile = store.ensure_default(
        board_corners=[[1.0, 2.0]] * 4,
        white_camera_edge="right",
    )
    old_path = store.directory / "Default-board.json"

    store.rename(profile, "Tournament board")

    assert profile.name == "Tournament board"
    assert not old_path.exists()
    assert (store.directory / "Tournament-board.json").exists()
    reloaded = BoardProfileStore(store.directory).load()[0]
    assert reloaded.board_corners == [[1.0, 2.0]] * 4
    assert reloaded.white_camera_edge == "right"


def test_board_profile_rename_rejects_empty_and_duplicate_names(
    tmp_path: Path,
) -> None:
    store = BoardProfileStore(tmp_path / "profiles")
    first = store.ensure_default()
    second = store.create_from(first)

    for invalid_name in ("", "  ", second.name.upper()):
        try:
            store.rename(first, invalid_name)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected rename to reject {invalid_name!r}")
    assert first.name == "Default board"


def test_reset_training_preserves_board_preset_calibration() -> None:
    corners = [[1.0, 2.0]] * 4
    phone = [[3.0, 4.0]] * 4
    profile = BoardProfile(
        "Keep calibration",
        board_corners=corners,
        phone_corners=phone,
        white_camera_edge="left",
        bottom_clock_is_white=False,
    )
    move = chess.Move.from_uci("e2e4")
    scores = blank_scores()
    scores[chess.E2] = 20.0
    scores[chess.E4] = 18.0
    profile.observe_move(move, scores, {chess.E2, chess.E4})
    profile.observe_rejection(move, scores)

    profile.reset_training()

    assert profile.sample_count == 0
    assert profile.move_patterns == {}
    assert profile.rejected_patterns == {}
    assert profile.noise_mean == [0.0] * 64
    assert profile.noise_count == [0] * 64
    assert profile.board_corners == corners
    assert profile.phone_corners == phone
    assert profile.white_camera_edge == "left"
    assert not profile.bottom_clock_is_white


def test_learned_move_signature_breaks_an_ambiguous_ranking() -> None:
    board = chess.Board()
    scores = blank_scores()
    scores[chess.E2] = 22.0
    scores[chess.E3] = 18.0
    scores[chess.E4] = 18.0
    pattern = [0.0] * 64
    pattern[chess.E2] = 1.0
    pattern[chess.E4] = 0.95

    ranked = rank_legal_moves(board, scores, {"e2e4": pattern})

    assert ranked[0].move == chess.Move.from_uci("e2e4")


def test_rejected_signature_penalizes_the_wrong_move() -> None:
    board = chess.Board()
    scores = blank_scores()
    scores[chess.E2] = 22.0
    scores[chess.E3] = 18.0
    scores[chess.E4] = 18.0
    rejected = [0.0] * 64
    rejected[chess.E2] = 1.0
    rejected[chess.E4] = 0.95

    ranked = rank_legal_moves(board, scores, None, {"e2e4": rejected})

    assert ranked[0].move != chess.Move.from_uci("e2e4")


def test_manual_correction_keeps_rejected_move_as_last_choice() -> None:
    board = chess.Board()
    scores = blank_scores()
    scores[chess.E2] = 24.0
    scores[chess.E4] = 22.0
    rejected_move = chess.Move.from_uci("e2e4")
    profile = BoardProfile("Correction")
    profile.observe_rejection(rejected_move, scores)

    candidates = manual_correction_candidates(
        board,
        scores,
        rejected_move,
        profile,
    )

    assert candidates
    assert candidates[-1].move == rejected_move
    assert candidates[0].move != rejected_move


def test_rejected_patterns_persist_with_board_profile(tmp_path: Path) -> None:
    store = BoardProfileStore(tmp_path / "profiles")
    profile = store.ensure_default()
    move = chess.Move.from_uci("e2e4")
    scores = blank_scores()
    scores[chess.E2] = 20.0
    scores[chess.E4] = 18.0
    profile.observe_rejection(move, scores, weight=3)
    store.save(profile)

    reloaded = BoardProfileStore(tmp_path / "profiles").load()[0]

    assert reloaded.rejected_patterns["e2e4"].count == 3
    assert reloaded.rejected_patterns["e2e4"].mean_scores[chess.E2] == 1.0


def test_profile_learning_can_be_disabled() -> None:
    profile = BoardProfile("No learning", learning_enabled=False)
    board = chess.Board()
    move = chess.Move.from_uci("e2e4")
    profile.observe_move(
        move,
        {square: 10.0 for square in chess.SQUARES},
        move_changed_squares(board, move),
    )
    assert profile.sample_count == 0


def test_analysis_accuracy_and_classification_thresholds() -> None:
    assert move_accuracy(0) == 100.0
    assert move_accuracy(50) > move_accuracy(150) > move_accuracy(300)

    board = chess.Board()
    move = chess.Move.from_uci("e2e4")
    best = PositionEvaluation(30, None, "e2e4")
    after = PositionEvaluation(25, None, None)
    assert classify_move(board, move, 5, move, best, after) == "Best"
    assert classify_move(board, move, 40, None, best, after) == "Good"
    assert classify_move(board, move, 90, None, best, after) == "Inaccuracy"
    assert classify_move(board, move, 180, None, best, after) == "Mistake"
    assert classify_move(board, move, 320, None, best, after) == "Blunder"


def test_analysis_detects_miss_and_apparent_sacrifice() -> None:
    board = chess.Board()
    move = chess.Move.from_uci("d2d3")
    winning = PositionEvaluation(400, None, "d2d4")
    lost_chance = PositionEvaluation(-100, None, None)
    assert (
        classify_move(
            board,
            move,
            500,
            chess.Move.from_uci("d2d4"),
            winning,
            lost_chance,
        )
        == "Miss"
    )

    sacrifice_board = chess.Board("r3k3/p7/8/8/8/8/8/R3K3 w Q - 0 1")
    sacrifice = chess.Move.from_uci("a1a7")
    equal = PositionEvaluation(25, None, "a1a7")
    assert (
        classify_move(
            sacrifice_board,
            sacrifice,
            0,
            sacrifice,
            equal,
            equal,
        )
        == "Brilliant"
    )


def test_game_review_totals_and_json_export(tmp_path: Path) -> None:
    moves = [chess.Move.from_uci("e2e4"), chess.Move.from_uci("e7e5")]
    evaluations = [
        PositionEvaluation(30, None, "e2e4"),
        PositionEvaluation(-25, None, "e7e5"),
        PositionEvaluation(20, None, "g1f3"),
    ]
    review = build_game_review(moves, evaluations, "Testfish", 0.1)
    assert review.white_accuracy > 95
    assert review.black_accuracy > 80
    assert review.moves[0].classification == "Best"
    assert review.moves[1].classification == "Best"

    target = tmp_path / "analysis.json"
    save_analysis_report(review, target)
    text = target.read_text(encoding="utf-8")
    assert '"engine_name": "Testfish"' in text
    assert '"white_accuracy"' in text
    assert '"white_counts"' in text


def test_stockfish_path_can_be_supplied_explicitly(tmp_path: Path) -> None:
    executable = tmp_path / ("stockfish.exe" if sys.platform == "win32" else "stockfish")
    executable.write_text("", encoding="utf-8")
    executable.chmod(0o755)
    assert find_stockfish(str(executable)) == executable.resolve()


def test_selected_uci_engine_is_probed_for_name(tmp_path: Path) -> None:
    if sys.platform == "win32":
        return
    executable = tmp_path / "test-engine"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "for line in sys.stdin:\n"
        "    command = line.strip()\n"
        "    if command == 'uci':\n"
        "        print('id name TestFish', flush=True)\n"
        "        print('id author Chess Camera tests', flush=True)\n"
        "        print('uciok', flush=True)\n"
        "    elif command == 'isready':\n"
        "        print('readyok', flush=True)\n"
        "    elif command == 'quit':\n"
        "        break\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    assert probe_uci_engine(executable) == "TestFish"


def test_selected_engine_path_is_saved_in_config(
    tmp_path: Path, monkeypatch: object
) -> None:
    import app as app_module

    config_path = tmp_path / "camera_config.json"
    monkeypatch.setattr(app_module, "CONFIG_PATH", config_path)  # type: ignore[attr-defined]
    engine_path = tmp_path / "engine"
    app_module.save_config(
        [[0.0, 0.0]] * 4,
        [[1.0, 1.0]] * 4,
        True,
        "bottom",
        "Test board",
        engine_path,
    )
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["engine_path"] == str(engine_path)
    assert config["pinned_time_controls"] == list(DEFAULT_PINNED_TIME_CONTROLS)


def test_pinned_time_controls_are_saved_in_config(
    tmp_path: Path, monkeypatch: object
) -> None:
    import app as app_module

    config_path = tmp_path / "camera_config.json"
    monkeypatch.setattr(app_module, "CONFIG_PATH", config_path)  # type: ignore[attr-defined]
    app_module.save_config(
        [[0.0, 0.0]] * 4,
        [[1.0, 1.0]] * 4,
        True,
        "bottom",
        pinned_time_controls=("1+0", "3+2"),
    )

    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["pinned_time_controls"] == ["1+0", "3+2"]


def test_player_and_event_suggestions_are_saved_in_config(
    tmp_path: Path, monkeypatch: object
) -> None:
    import app as app_module

    config_path = tmp_path / "camera_config.json"
    monkeypatch.setattr(app_module, "CONFIG_PATH", config_path)  # type: ignore[attr-defined]
    app_module.save_config(
        [[0.0, 0.0]] * 4,
        [[1.0, 1.0]] * 4,
        True,
        "bottom",
        player_name_usage={"Alice": 3, "Bob": 2},
        event_name_usage={"Club night": 4},
    )

    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["player_name_usage"] == {"Alice": 3, "Bob": 2}
    assert config["event_name_usage"] == {"Club night": 4}


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


def test_illegal_move_pauses_and_resumes_the_retrying_clock() -> None:
    clock = BuiltInChessClock(
        ClockSettings(
            white_initial_seconds=60,
            black_initial_seconds=60,
        )
    )
    manual_clock = ManualClockController()
    clock.start(100.0, white_to_move=True)

    retrying_side = pause_clock_for_illegal_move(clock, manual_clock, 110.0)
    assert retrying_side is chess.WHITE
    assert clock.active_white is None
    assert clock.remaining(True, 120.0) == 50.0

    resume_clock_after_illegal_move(clock, retrying_side, 120.0)
    assert clock.active_white is chess.WHITE
    assert clock.remaining(True, 125.0) == 45.0


def test_illegal_move_cancels_an_early_manual_clock_press() -> None:
    clock = BuiltInChessClock(
        ClockSettings(
            white_initial_seconds=60,
            black_initial_seconds=60,
            white_increment_seconds=2,
        )
    )
    manual_clock = ManualClockController()
    clock.start(100.0, white_to_move=True)
    manual_clock.press(clock, True, 110.0)

    retrying_side = pause_clock_for_illegal_move(clock, manual_clock, 111.0)
    assert retrying_side is chess.WHITE
    assert manual_clock.pending is None
    assert clock.active_white is None
    assert clock.remaining(True, 120.0) == 50.0


def test_illegal_warning_has_a_centered_clickable_dismiss_button() -> None:
    button = illegal_warning_button(1400, 620)

    assert button.action == "dismiss_illegal"
    assert "ESC / X" in button.label
    assert button.contains(700, 430)
    assert button.enabled
