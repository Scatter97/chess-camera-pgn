from __future__ import annotations

from pathlib import Path
from types import ModuleType

import runtime_0397_patch


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(
            f"Cannot install {label}: expected one source marker, found {count}."
        )
    return source.replace(old, new, 1)


def _replace_count(
    source: str,
    old: str,
    new: str,
    expected_count: int,
    label: str,
) -> str:
    count = source.count(old)
    if count != expected_count:
        raise RuntimeError(
            f"Cannot install {label}: expected {expected_count} source markers, "
            f"found {count}."
        )
    return source.replace(old, new)


def apply_source_patches(source: str) -> str:
    """Apply stable 0.39.7 patches and experimental multi-move recovery."""
    source = runtime_0397_patch.apply_source_patches(source)

    source = _replace_once(
        source,
        "import illegal_correction as illegal_ui\n"
        "import manual_board_sync as manual_sync\n"
        "import training_settings as training_ui\n\n",
        "import illegal_correction as illegal_ui\n"
        "import manual_board_sync as manual_sync\n"
        "import multi_move_recovery as multi_move_ui\n"
        "import training_settings as training_ui\n\n",
        "experimental multi-move import",
    )

    source = _replace_once(
        source,
        '''        manual_edit_moves: list[chess.Move] = []
        manual_resume_side: bool | None = None
        status = "Game starting. Make White's first move."
''',
        '''        manual_edit_moves: list[chess.Move] = []
        manual_resume_side: bool | None = None
        multi_move_settings = multi_move_ui.load_settings(CONFIG_PATH)
        multi_move_history = multi_move_ui.FrameEventBuffer()
        status = "Game starting. Make White's first move."
''',
        "experimental multi-move state",
    )

    source = _replace_once(
        source,
        '''                manual_edit_moves.clear()
                manual_resume_side = None
                game_result = "*"
''',
        '''                manual_edit_moves.clear()
                manual_resume_side = None
                multi_move_settings = multi_move_ui.load_settings(CONFIG_PATH)
                multi_move_history.reset(reference, now)
                game_result = "*"
''',
        "new-game multi-move reset",
    )

    source = _replace_once(
        source,
        '''            if previous is not None:
                motion = frame_motion_score(previous, warped)
                if motion < 1.6:
''',
        '''            if previous is not None:
                motion = frame_motion_score(previous, warped)
                multi_move_history.observe(warped, now, motion)
                if motion < 1.6:
''',
        "rolling movement-event capture",
    )

    source = _replace_once(
        source,
        '''                    if best_fit is None or best_fit.score < LEGAL_FIT_THRESHOLD:
                        if clock_source == "builtin":
                            illegal_clock_side = pause_clock_for_illegal_move(
                                builtin_clock,
                                manual_clock,
                                now,
                            )
                        illegal_warning = True
                        illegal_edit_frame = warped.copy()
                        illegal_edit_scores = raw_scores.copy()
                        pending.clear()
                        pending_frame = None
                        pending_event_time = None
                        pending_scores.clear()
                        status = (
                            "Illegal move detected. Return every changed piece "
                            "to the last legal position. "
                            + (
                                "The clock is paused."
                                if clock_source == "builtin"
                                else "Pause the Lichess clock on the phone."
                            )
                        )
                        stable_since = None
                        continue_detection = False
                    else:
                        illegal_warning = False
                        pending = ranked_moves[:8]
                        continue_detection = True
''',
        '''                    if best_fit is None or best_fit.score < LEGAL_FIT_THRESHOLD:
                        recovery_result = None
                        recovered_sequence: tuple[chess.Move, ...] | None = None
                        recovery_clock_side: bool | None = None
                        if multi_move_settings.enabled and not bullet_mode:
                            recovery_result = multi_move_ui.search_sequences(
                                board,
                                scores,
                                multi_move_history.events(),
                                max_depth=multi_move_settings.max_depth,
                                beam_width=multi_move_settings.beam_width,
                            )
                            if (
                                recovery_result is not None
                                and recovery_result.candidates
                                and recovery_result.candidates[0].final_position_score
                                >= multi_move_settings.min_position_fit
                            ):
                                if clock_source == "builtin":
                                    recovery_clock_side = pause_clock_for_illegal_move(
                                        builtin_clock,
                                        manual_clock,
                                        now,
                                    )
                                recovered_sequence = multi_move_ui.show_recovery_dialog(
                                    sys.modules[__name__],
                                    board,
                                    recovery_result,
                                    multi_move_settings,
                                )
                                cv2.namedWindow("Chess Camera PGN", cv2.WINDOW_NORMAL)
                                cv2.setMouseCallback("Chess Camera PGN", on_game_mouse)

                        if recovered_sequence:
                            validation_board = board.copy(stack=False)
                            valid_sequence = True
                            for recovered_move in recovered_sequence:
                                if recovered_move not in validation_board.legal_moves:
                                    valid_sequence = False
                                    break
                                validation_board.push(recovered_move)

                            if valid_sequence:
                                recovered_sans: list[str] = []
                                for recovered_move in recovered_sequence:
                                    recovered_sans.append(board.san(recovered_move))
                                    board.push(recovered_move)
                                    moves.append(recovered_move)
                                    move_clocks.append(None)
                                    move_clock_tokens.append(next_clock_token)
                                    next_clock_token += 1
                                    training_move_snapshots.append(None)

                                game_result = "*"
                                game_finished = False
                                game_review = None
                                dismissed_draw_claims.clear()
                                last_auto_move = None
                                last_auto_scores.clear()
                                last_auto_frame = None
                                last_auto_event_time = None
                                auto_correction_pending = False
                                correction_clock_value = None
                                illegal_warning = False
                                illegal_clock_side = None
                                recovery_frame = (
                                    consensus_result.frame.copy()
                                    if consensus_result is not None
                                    else warped.copy()
                                )
                                reference = recovery_frame
                                previous = reference.copy()
                                pending.clear()
                                pending_frame = None
                                pending_event_time = None
                                pending_scores.clear()
                                accuracy_frames.clear()
                                multi_move_history.reset(reference, now)
                                save_game(
                                    moves,
                                    move_clocks,
                                    setup.pgn_headers(),
                                    game_result,
                                )
                                last_accept_time = now
                                stable_since = None
                                position_notice = evaluate_position(now)
                                if clock_source == "builtin" and not game_finished:
                                    builtin_clock.start(time.monotonic(), board.turn)
                                if not game_finished and not position_notice:
                                    status = (
                                        f"Recovered {len(recovered_sequence)} missed moves: "
                                        + " ".join(recovered_sans)
                                        + ". Exact individual move times were unavailable."
                                    )
                                continue_detection = False
                            else:
                                recovered_sequence = None

                        if not recovered_sequence:
                            if clock_source == "builtin":
                                illegal_clock_side = (
                                    recovery_clock_side
                                    if recovery_clock_side is not None
                                    else pause_clock_for_illegal_move(
                                        builtin_clock,
                                        manual_clock,
                                        now,
                                    )
                                )
                            illegal_warning = True
                            illegal_edit_frame = warped.copy()
                            illegal_edit_scores = raw_scores.copy()
                            pending.clear()
                            pending_frame = None
                            pending_event_time = None
                            pending_scores.clear()
                            status = (
                                "No certain legal move sequence explained the board. "
                                "Return every changed piece to the last legal position, "
                                "or use the correction editor. "
                                + (
                                    "The clock is paused."
                                    if clock_source == "builtin"
                                    else "Pause the Lichess clock on the phone."
                                )
                            )
                            stable_since = None
                            continue_detection = False
                    else:
                        illegal_warning = False
                        pending = ranked_moves[:8]
                        continue_detection = True
''',
        "multi-move fallback before illegal warning",
    )

    source = _replace_count(
        source,
        '''                                reference = pending_frame.copy()
                                pending.clear()
''',
        '''                                reference = pending_frame.copy()
                                multi_move_history.reset(reference, now)
                                pending.clear()
''',
        1,
        "automatic-move history reset",
    )

    source = _replace_count(
        source,
        '''                    reference = pending_frame.copy()
                    pending.clear()
''',
        '''                    reference = pending_frame.copy()
                    multi_move_history.reset(reference, now)
                    pending.clear()
''',
        1,
        "manual-move history reset",
    )

    source = _replace_once(
        source,
        '''                reference = warped.copy()
                previous = warped.copy()
                stable_since = None
                accuracy_frames.clear()
                illegal_warning = False
''',
        '''                reference = warped.copy()
                previous = warped.copy()
                multi_move_history.reset(reference, now)
                stable_since = None
                accuracy_frames.clear()
                illegal_warning = False
''',
        "restored-board history reset",
    )

    source = _replace_once(
        source,
        '''                previous = reference.copy()
                illegal_edit_frame = None
                illegal_edit_scores.clear()
''',
        '''                previous = reference.copy()
                multi_move_history.reset(reference, now)
                illegal_edit_frame = None
                illegal_edit_scores.clear()
''',
        "illegal-correction history reset",
    )

    source = _replace_once(
        source,
        '''                reference = warped.copy()
                previous = reference.copy()
                pending.clear()
''',
        '''                reference = warped.copy()
                previous = reference.copy()
                multi_move_history.reset(reference, now)
                pending.clear()
''',
        "manual-sync history reset",
    )

    source = _replace_once(
        source,
        '''                reference = warped.copy()
                pending.clear()
                pending_frame = None
''',
        '''                reference = warped.copy()
                multi_move_history.reset(reference, now)
                pending.clear()
                pending_frame = None
''',
        "undo history reset",
    )

    return source


def install(app_module: ModuleType) -> None:
    """Recompile app.py with the isolated experimental recovery framework."""
    if getattr(app_module, "_RUNTIME_MULTI_MOVE_PATCHED", False):
        return
    source_path = Path(app_module.__file__).resolve()
    original = source_path.read_text(encoding="utf-8")
    patched = apply_source_patches(original)
    code = compile(patched, str(source_path), "exec")
    exec(code, app_module.__dict__)
    app_module._RUNTIME_MULTI_MOVE_PATCHED = True
