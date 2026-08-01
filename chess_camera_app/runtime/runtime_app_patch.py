from __future__ import annotations

from pathlib import Path
from types import ModuleType


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(
            f"Cannot install {label}: expected one source marker, found {count}."
        )
    return source.replace(old, new, 1)


def apply_source_patches(source: str) -> str:
    """Inject the completed 0.39 game-state features into app.py at launch."""
    source = _replace_once(
        source,
        "import numpy as np\n\nfrom chess_camera_app.calibration.board_profiles import (",
        "import numpy as np\n\n"
        "from chess_camera_app.game import illegal_correction as illegal_ui\n"
        "from chess_camera_app.ui import training_settings as training_ui\n\n"
        "from chess_camera_app.calibration.board_profiles import (",
        "0.39 imports",
    )

    source = _replace_once(
        source,
        '''        board = chess.Board()
        moves: list[chess.Move] = []
        move_clocks: list[float | None] = []
''',
        '''        board = chess.Board()
        moves: list[chess.Move] = []
        training_move_snapshots: list[dict[str, object] | None] = []
        move_clocks: list[float | None] = []
''',
        "training snapshot state",
    )

    source = _replace_once(
        source,
        '''        illegal_warning = False
        illegal_clock_side: bool | None = None
        status = "Game starting. Make White's first move."
''',
        '''        illegal_warning = False
        illegal_clock_side: bool | None = None
        illegal_edit_mode = False
        illegal_edit_board: chess.Board | None = None
        illegal_drag_from: chess.Square | None = None
        illegal_edit_message = ""
        illegal_edit_frame: np.ndarray | None = None
        illegal_edit_scores: dict[chess.Square, float] = {}
        status = "Game starting. Make White's first move."
''',
        "illegal correction state",
    )

    source = _replace_once(
        source,
        '''        def on_game_mouse(
            event: int, x: int, y: int, _flags: int, _data: object
        ) -> None:
            if event != cv2.EVENT_LBUTTONUP:
                return
            action = clicked_action(game_buttons, x, y)
            if action is not None:
                game_click_queue.append(action)
''',
        '''        def on_game_mouse(
            event: int, x: int, y: int, _flags: int, _data: object
        ) -> None:
            nonlocal illegal_drag_from, illegal_edit_message

            if illegal_edit_mode:
                if event == cv2.EVENT_LBUTTONDOWN:
                    square = illegal_ui.virtual_square_at(x, y)
                    if (
                        square is not None
                        and illegal_edit_board is not None
                        and illegal_edit_board.piece_at(square) is not None
                    ):
                        illegal_drag_from = square
                        illegal_edit_message = (
                            f"Selected {chess.square_name(square)}. "
                            "Drag it to the destination square."
                        )
                    return
                if event != cv2.EVENT_LBUTTONUP:
                    return
                action = clicked_action(game_buttons, x, y)
                if action is not None:
                    game_click_queue.append(action)
                    illegal_drag_from = None
                    return
                target = illegal_ui.virtual_square_at(x, y)
                if (
                    illegal_drag_from is not None
                    and target is not None
                    and illegal_edit_board is not None
                ):
                    moved = illegal_ui.apply_drag(
                        illegal_edit_board,
                        illegal_drag_from,
                        target,
                        choose_promotion_piece,
                    )
                    illegal_edit_message = (
                        "Piece moved. Press Continue to validate the position."
                        if moved
                        else "No piece was moved."
                    )
                illegal_drag_from = None
                return

            if event != cv2.EVENT_LBUTTONUP:
                return
            action = clicked_action(game_buttons, x, y)
            if action is not None:
                game_click_queue.append(action)
''',
        "drag-and-drop mouse handling",
    )

    source = _replace_once(
        source,
        '''                moves.clear()
                move_clocks.clear()
                move_clock_tokens.clear()
''',
        '''                moves.clear()
                training_move_snapshots.clear()
                move_clocks.clear()
                move_clock_tokens.clear()
''',
        "new-game training reset",
    )

    source = _replace_once(
        source,
        '''                illegal_warning = False
                illegal_clock_side = None
                game_result = "*"
''',
        '''                illegal_warning = False
                illegal_clock_side = None
                illegal_edit_mode = False
                illegal_edit_board = None
                illegal_drag_from = None
                illegal_edit_message = ""
                illegal_edit_frame = None
                illegal_edit_scores.clear()
                game_result = "*"
''',
        "new-game correction reset",
    )

    source = _replace_once(
        source,
        '''                    if not pending and not illegal_warning:
                        status = "Waiting for hands and pieces to stop moving..."
''',
        '''                    if (
                        not pending
                        and not illegal_warning
                        and not illegal_edit_mode
                    ):
                        status = "Waiting for hands and pieces to stop moving..."
''',
        "correction motion guard",
    )

    source = _replace_once(
        source,
        '''                and not pending
                and not game_finished
                and analysis_ready
''',
        '''                and not pending
                and not game_finished
                and not illegal_edit_mode
                and analysis_ready
''',
        "correction detection pause",
    )

    source = _replace_once(
        source,
        '''                        illegal_warning = True
                        pending.clear()
''',
        '''                        illegal_warning = True
                        illegal_edit_frame = warped.copy()
                        illegal_edit_scores = raw_scores.copy()
                        pending.clear()
''',
        "capture illegal visual evidence",
    )

    source = _replace_once(
        source,
        '''                                if (
                                    not bullet_mode
                                    and confidence >= AUTO_CONFIDENCE
                                ):
                                    profile.observe_move(
                                        candidate,
                                        pending_scores,
                                        pending[0].expected_squares,
                                    )
                                    profile_store.save(profile)
                                board.push(candidate)
                                moves.append(candidate)
''',
        '''                                training_snapshot = None
                                if (
                                    not bullet_mode
                                    and confidence >= AUTO_CONFIDENCE
                                ):
                                    training_snapshot = training_ui.profile_snapshot(
                                        profile
                                    )
                                    profile.observe_move(
                                        candidate,
                                        pending_scores,
                                        pending[0].expected_squares,
                                    )
                                    profile_store.save(profile)
                                board.push(candidate)
                                moves.append(candidate)
                                training_move_snapshots.append(training_snapshot)
''',
        "auto-move training snapshot",
    )

    source = _replace_once(
        source,
        '''            virtual_view = render_virtual_board(
                board, moves[-1] if moves else None
            )
''',
        '''            display_board = (
                illegal_edit_board
                if illegal_edit_mode and illegal_edit_board is not None
                else board
            )
            virtual_view = render_virtual_board(
                display_board,
                None if illegal_edit_mode else (moves[-1] if moves else None),
            )
            if illegal_edit_mode:
                virtual_view = illegal_ui.draw_edit_overlay(
                    virtual_view,
                    illegal_edit_message,
                )
''',
        "editable virtual-board rendering",
    )

    source = _replace_once(
        source,
        '''            if auto_correction_pending:
                source_label = "MANUAL CORRECTION - AUTO NEXT MOVE"
''',
        '''            if illegal_edit_mode:
                source_label = "ILLEGAL MOVE - DRAG BOARD TO FIX"
            elif auto_correction_pending:
                source_label = "MANUAL CORRECTION - AUTO NEXT MOVE"
''',
        "correction status label",
    )

    source = _replace_once(
        source,
        '''            if illegal_warning:
                game_buttons.append(
                    illegal_warning_button(combined.shape[1], combined.shape[0])
                )
            for game_button in game_buttons:
                draw_button(combined, game_button)
            if illegal_warning:
                combined = draw_illegal_warning(combined)
''',
        '''            warning_buttons: list[Button] = []
            if illegal_edit_mode:
                game_buttons = illegal_ui.edit_buttons(button_x, button_y)
            elif illegal_warning:
                warning_buttons = illegal_ui.warning_buttons(
                    combined.shape[1],
                    combined.shape[0],
                )
                game_buttons.extend(warning_buttons)
            for game_button in game_buttons:
                draw_button(combined, game_button)
            if illegal_warning and not illegal_edit_mode:
                combined = illegal_ui.draw_warning(combined, warning_buttons)
''',
        "illegal warning and editor buttons",
    )

    source = _replace_once(
        source,
        '''            if illegal_warning and (
                click_action == "dismiss_illegal" or key in (27, ord("x"))
            ):
                # Manual recovery is for cases where the physical position has
                # been restored but camera noise prevents the automatic check.
                # Re-baseline on the current image without changing the logical
                # chess position or recording a move.
                reference = warped.copy()
                previous = warped.copy()
                stable_since = None
                accuracy_frames.clear()
                illegal_warning = False
                last_accept_time = now
                if clock_source == "builtin":
                    resume_clock_after_illegal_move(
                        builtin_clock,
                        illegal_clock_side,
                        now,
                    )
                illegal_clock_side = None
                status = (
                    "Illegal warning dismissed and camera resynchronized. "
                    "The clock resumed."
                    if clock_source == "builtin"
                    else
                    "Illegal warning dismissed and camera resynchronized."
                )
                continue
''',
        '''            if illegal_warning and not illegal_edit_mode and (
                click_action == "restore_illegal" or key in (27, ord("x"))
            ):
                reference = warped.copy()
                previous = warped.copy()
                stable_since = None
                accuracy_frames.clear()
                illegal_warning = False
                last_accept_time = now
                if clock_source == "builtin":
                    resume_clock_after_illegal_move(
                        builtin_clock,
                        illegal_clock_side,
                        now,
                    )
                illegal_clock_side = None
                illegal_edit_frame = None
                illegal_edit_scores.clear()
                status = (
                    "Restored position accepted. The clock resumed."
                    if clock_source == "builtin"
                    else "Restored position accepted. Resume the phone clock."
                )
                continue

            if illegal_warning and click_action == "correct_illegal":
                illegal_warning = False
                illegal_edit_mode = True
                illegal_edit_board = board.copy(stack=False)
                illegal_drag_from = None
                illegal_edit_message = (
                    "Drag the moved piece to its destination, then press Continue."
                )
                status = (
                    "Correction mode: edit the virtual board to the position "
                    "immediately after the legal move."
                )
                continue

            if illegal_edit_mode and (
                click_action == "cancel_correction" or key in (27, ord("x"))
            ):
                illegal_edit_mode = False
                illegal_edit_board = None
                illegal_drag_from = None
                illegal_edit_message = ""
                illegal_warning = True
                status = "Correction cancelled. Restore the physical position or try again."
                continue

            if illegal_edit_mode and click_action == "reset_correction":
                illegal_edit_board = board.copy(stack=False)
                illegal_drag_from = None
                illegal_edit_message = "Virtual board reset to the last legal position."
                continue

            if illegal_edit_mode and click_action == "continue_correction":
                if illegal_edit_board is None:
                    illegal_edit_message = "Correction board is unavailable. Press Reset."
                    continue
                corrected_move = illegal_ui.matching_legal_move(
                    board,
                    illegal_edit_board,
                )
                if corrected_move is None:
                    illegal_edit_message = (
                        "That is not exactly one legal move. Adjust the board and retry."
                    )
                    status = illegal_edit_message
                    continue

                san = board.san(corrected_move)
                move_index = len(moves)
                token = next_clock_token
                next_clock_token += 1
                move_clock_tokens.append(token)
                event_time = now
                if clock_source == "ocr":
                    move_clocks.append(None)
                    clock_worker.submit_move(
                        raw,
                        phone_corners,
                        (
                            "move",
                            move_index,
                            token,
                            board.turn,
                            bottom_clock_is_white,
                            event_time,
                        ),
                    )
                else:
                    builtin_clock.start(
                        event_time,
                        illegal_clock_side
                        if illegal_clock_side is not None
                        else board.turn,
                    )
                    move_clocks.append(
                        builtin_clock.complete_move(board.turn, event_time)
                    )

                training_snapshot = (
                    training_ui.profile_snapshot(profile)
                    if profile.learning_enabled
                    else None
                )
                if profile.learning_enabled:
                    profile.observe_move(
                        corrected_move,
                        illegal_edit_scores,
                        move_changed_squares(board, corrected_move),
                        weight=4,
                    )
                    profile_store.save(profile)

                board.push(corrected_move)
                moves.append(corrected_move)
                training_move_snapshots.append(training_snapshot)
                last_auto_move = None
                last_auto_scores.clear()
                last_auto_frame = None
                last_auto_event_time = None
                auto_correction_pending = False
                correction_clock_value = None
                illegal_edit_mode = False
                illegal_edit_board = None
                illegal_drag_from = None
                illegal_edit_message = ""
                illegal_warning = False
                illegal_clock_side = None
                reference = (
                    illegal_edit_frame.copy()
                    if illegal_edit_frame is not None
                    else warped.copy()
                )
                previous = reference.copy()
                illegal_edit_frame = None
                illegal_edit_scores.clear()
                pending.clear()
                pending_frame = None
                pending_event_time = None
                pending_scores.clear()
                accuracy_frames.clear()
                save_game(
                    moves,
                    move_clocks,
                    setup.pgn_headers(),
                    game_result,
                )
                last_accept_time = now
                stable_since = None
                position_notice = evaluate_position(now)
                if not game_finished and not position_notice:
                    status = f"Corrected and recorded {san}. The clock resumed."
                continue
''',
        "working illegal correction flow",
    )

    source = _replace_once(
        source,
        '''                profile.observe_rejection(
                    rejected_move,
                    last_auto_scores,
                    weight=3,
                )
                profile_store.save(profile)
''',
        '''                removed_training_snapshot = (
                    training_move_snapshots.pop()
                    if training_move_snapshots
                    else None
                )
                if (
                    removed_training_snapshot is not None
                    and training_ui.remove_undone_enabled(CONFIG_PATH)
                ):
                    training_ui.restore_profile(
                        profile,
                        removed_training_snapshot,
                    )
                if training_ui.keep_rejected_enabled(CONFIG_PATH):
                    profile.observe_rejection(
                        rejected_move,
                        last_auto_scores,
                        weight=3,
                    )
                profile_store.save(profile)
''',
        "wrong-detection training cleanup",
    )

    source = _replace_once(
        source,
        '''                moves.pop()
                move_clocks.pop()
                move_clock_tokens.pop()
                game_result = "*"
''',
        '''                removed_training_snapshot = (
                    training_move_snapshots.pop()
                    if training_move_snapshots
                    else None
                )
                if (
                    removed_training_snapshot is not None
                    and training_ui.remove_undone_enabled(CONFIG_PATH)
                ):
                    training_ui.restore_profile(
                        profile,
                        removed_training_snapshot,
                    )
                    profile_store.save(profile)
                moves.pop()
                move_clocks.pop()
                move_clock_tokens.pop()
                game_result = "*"
''',
        "undo training cleanup",
    )

    source = _replace_once(
        source,
        '''                    selected_pattern = pending[pending_index]
                    profile.observe_move(
                        selected_move,
                        pending_scores,
                        selected_pattern.expected_squares,
                        weight=(
                            4
                            if was_auto_correction
                            else (2 if pending_index != 0 else 1)
                        ),
                    )
                    profile_store.save(profile)
                    board.push(selected_move)
                    moves.append(selected_move)
''',
        '''                    selected_pattern = pending[pending_index]
                    training_snapshot = (
                        training_ui.profile_snapshot(profile)
                        if profile.learning_enabled
                        else None
                    )
                    profile.observe_move(
                        selected_move,
                        pending_scores,
                        selected_pattern.expected_squares,
                        weight=(
                            4
                            if was_auto_correction
                            else (2 if pending_index != 0 else 1)
                        ),
                    )
                    profile_store.save(profile)
                    board.push(selected_move)
                    moves.append(selected_move)
                    training_move_snapshots.append(training_snapshot)
''',
        "manual-move training snapshot",
    )

    return source


def install(app_module: ModuleType) -> None:
    """Recompile app.py once with the completed 0.39 state-machine changes."""
    if getattr(app_module, "_RUNTIME_039_PATCHED", False):
        return
    source_path = Path(app_module.__file__).resolve()
    original = source_path.read_text(encoding="utf-8")
    patched = apply_source_patches(original)
    code = compile(patched, str(source_path), "exec")
    exec(code, app_module.__dict__)
    app_module._RUNTIME_039_PATCHED = True
