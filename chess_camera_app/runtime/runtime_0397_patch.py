from __future__ import annotations

from pathlib import Path
from types import ModuleType

from chess_camera_app.runtime import runtime_app_patch


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(
            f"Cannot install {label}: expected one source marker, found {count}."
        )
    return source.replace(old, new, 1)


def apply_source_patches(source: str) -> str:
    """Apply 0.39 reliability patches plus the 0.39.6 board-sync editor."""
    source = runtime_app_patch.apply_source_patches(source)

    source = _replace_once(
        source,
        "from chess_camera_app.game import illegal_correction as illegal_ui\n"
        "from chess_camera_app.ui import training_settings as training_ui\n\n",
        "from chess_camera_app.game import illegal_correction as illegal_ui\n"
        "from chess_camera_app.game import manual_board_sync as manual_sync\n"
        "from chess_camera_app.ui import training_settings as training_ui\n\n",
        "manual-sync import",
    )

    source = _replace_once(
        source,
        '''        illegal_edit_scores: dict[chess.Square, float] = {}
        status = "Game starting. Make White's first move."
''',
        '''        illegal_edit_scores: dict[chess.Square, float] = {}
        manual_edit_mode = False
        manual_edit_board: chess.Board | None = None
        manual_drag_from: chess.Square | None = None
        manual_edit_message = ""
        manual_edit_moves: list[chess.Move] = []
        manual_resume_side: bool | None = None
        status = "Game starting. Make White's first move."
''',
        "manual-sync state",
    )

    source = _replace_once(
        source,
        '''            nonlocal illegal_drag_from, illegal_edit_message

            if illegal_edit_mode:
''',
        '''            nonlocal illegal_drag_from, illegal_edit_message
            nonlocal manual_drag_from, manual_edit_message

            if manual_edit_mode:
                if event == cv2.EVENT_LBUTTONDOWN:
                    square = manual_sync.virtual_square_at(x, y)
                    if (
                        square is not None
                        and manual_edit_board is not None
                        and manual_edit_board.piece_at(square) is not None
                    ):
                        manual_drag_from = square
                        manual_edit_message = (
                            f"Selected {chess.square_name(square)}. "
                            "Drag it to a legal destination."
                        )
                    return
                if event != cv2.EVENT_LBUTTONUP:
                    return
                action = clicked_action(game_buttons, x, y)
                if action is not None:
                    game_click_queue.append(action)
                    manual_drag_from = None
                    return
                target = manual_sync.virtual_square_at(x, y)
                if (
                    manual_drag_from is not None
                    and target is not None
                    and manual_edit_board is not None
                ):
                    synced_move = manual_sync.apply_legal_drag(
                        manual_edit_board,
                        manual_drag_from,
                        target,
                        choose_promotion_piece,
                    )
                    if synced_move is None:
                        manual_edit_message = (
                            "That drag is not legal from the current synced position."
                        )
                    else:
                        manual_edit_moves.append(synced_move)
                        manual_edit_message = (
                            f"Added {synced_move.uci()}. Add another move or save."
                        )
                manual_drag_from = None
                return

            if illegal_edit_mode:
''',
        "manual-sync mouse handling",
    )

    source = _replace_once(
        source,
        '''                illegal_edit_frame = None
                illegal_edit_scores.clear()
                game_result = "*"
''',
        '''                illegal_edit_frame = None
                illegal_edit_scores.clear()
                manual_edit_mode = False
                manual_edit_board = None
                manual_drag_from = None
                manual_edit_message = ""
                manual_edit_moves.clear()
                manual_resume_side = None
                game_result = "*"
''',
        "new-game manual-sync reset",
    )

    source = _replace_once(
        source,
        '''                    if (
                        not pending
                        and not illegal_warning
                        and not illegal_edit_mode
                    ):
''',
        '''                    if (
                        not pending
                        and not illegal_warning
                        and not illegal_edit_mode
                        and not manual_edit_mode
                    ):
''',
        "manual-sync motion guard",
    )

    source = _replace_once(
        source,
        '''                and not pending
                and not game_finished
                and not illegal_edit_mode
                and analysis_ready
''',
        '''                and not pending
                and not game_finished
                and not illegal_edit_mode
                and not manual_edit_mode
                and analysis_ready
''',
        "manual-sync detection pause",
    )

    source = _replace_once(
        source,
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
        '''            display_board = (
                manual_edit_board
                if manual_edit_mode and manual_edit_board is not None
                else (
                    illegal_edit_board
                    if illegal_edit_mode and illegal_edit_board is not None
                    else board
                )
            )
            virtual_view = render_virtual_board(
                display_board,
                (
                    None
                    if illegal_edit_mode or manual_edit_mode
                    else (moves[-1] if moves else None)
                ),
            )
            if manual_edit_mode:
                virtual_view = manual_sync.draw_edit_overlay(
                    virtual_view,
                    manual_edit_message,
                )
            elif illegal_edit_mode:
                virtual_view = illegal_ui.draw_edit_overlay(
                    virtual_view,
                    illegal_edit_message,
                )
''',
        "manual-sync board rendering",
    )

    source = _replace_once(
        source,
        '''            if illegal_edit_mode:
                source_label = "ILLEGAL MOVE - DRAG BOARD TO FIX"
            elif auto_correction_pending:
''',
        '''            if manual_edit_mode:
                source_label = "MANUAL BOARD SYNC - LEGAL MOVES ONLY"
            elif illegal_edit_mode:
                source_label = "ILLEGAL MOVE - DRAG BOARD TO FIX"
            elif auto_correction_pending:
''',
        "manual-sync status label",
    )

    source = _replace_once(
        source,
        '''            warning_buttons: list[Button] = []
            if illegal_edit_mode:
                game_buttons = illegal_ui.edit_buttons(button_x, button_y)
            elif illegal_warning:
''',
        '''            if (
                not pending
                and not game_finished
                and not illegal_warning
                and not illegal_edit_mode
                and not manual_edit_mode
            ):
                game_buttons = [
                    button
                    for button in game_buttons
                    if not button.action.startswith("promote_")
                ]
                game_buttons.append(
                    Button(
                        "manual_edit_board",
                        "EDIT VIRTUAL BOARD",
                        button_x,
                        386 + button_y,
                        276,
                        38,
                        enabled=(
                            manual_clock.pending is None
                            and not auto_correction_pending
                        ),
                    )
                )

            warning_buttons: list[Button] = []
            if manual_edit_mode:
                game_buttons = manual_sync.edit_buttons(button_x, button_y)
            elif illegal_edit_mode:
                game_buttons = illegal_ui.edit_buttons(button_x, button_y)
            elif illegal_warning:
''',
        "manual-sync game controls",
    )

    source = _replace_once(
        source,
        '''            if illegal_warning and not illegal_edit_mode and (
''',
        '''            if (
                click_action == "manual_edit_board"
                and not game_finished
                and not pending
                and not illegal_warning
                and not illegal_edit_mode
            ):
                manual_resume_side = (
                    builtin_clock.active_white
                    if clock_source == "builtin"
                    else None
                )
                if clock_source == "builtin":
                    builtin_clock.pause(now)
                manual_edit_mode = True
                manual_edit_board = board.copy(stack=False)
                manual_drag_from = None
                manual_edit_message = (
                    "Drag a legal move. Multiple missed moves may be added."
                )
                manual_edit_moves.clear()
                pending.clear()
                pending_frame = None
                pending_event_time = None
                pending_scores.clear()
                accuracy_frames.clear()
                status = (
                    "Manual board sync is active. Add the legal moves needed "
                    "to match the physical board, then save."
                )
                continue

            if manual_edit_mode and (
                click_action == "cancel_manual_sync" or key in (27, ord("x"))
            ):
                manual_edit_mode = False
                manual_edit_board = None
                manual_drag_from = None
                manual_edit_message = ""
                manual_edit_moves.clear()
                if (
                    clock_source == "builtin"
                    and manual_resume_side is not None
                ):
                    builtin_clock.start(now, manual_resume_side)
                manual_resume_side = None
                status = "Manual board sync cancelled."
                continue

            if manual_edit_mode and click_action == "reset_manual_sync":
                manual_edit_board = board.copy(stack=False)
                manual_drag_from = None
                manual_edit_moves.clear()
                manual_edit_message = "Editor reset to the recorded position."
                continue

            if manual_edit_mode and click_action == "undo_manual_sync":
                if manual_edit_board is not None and manual_edit_moves:
                    manual_edit_board.pop()
                    removed_edit = manual_edit_moves.pop()
                    manual_edit_message = f"Removed {removed_edit.uci()} from the sync."
                else:
                    manual_edit_message = "No manual sync move to undo."
                continue

            if manual_edit_mode and click_action == "save_manual_sync":
                if manual_edit_board is None or not manual_edit_moves:
                    manual_edit_message = "Add at least one legal move before saving."
                    continue

                synced_count = len(manual_edit_moves)
                sync_failed = False
                for synced_move in manual_edit_moves:
                    if synced_move not in board.legal_moves:
                        sync_failed = True
                        break
                    board.push(synced_move)
                    moves.append(synced_move)
                    move_clocks.append(None)
                    move_clock_tokens.append(next_clock_token)
                    next_clock_token += 1
                    training_move_snapshots.append(None)

                if sync_failed:
                    manual_edit_message = (
                        "The recorded position changed. Reset the editor and retry."
                    )
                    continue

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
                reference = warped.copy()
                previous = reference.copy()
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
                manual_edit_mode = False
                manual_edit_board = None
                manual_drag_from = None
                manual_edit_message = ""
                manual_edit_moves.clear()
                manual_resume_side = None
                last_accept_time = now
                stable_since = None
                position_notice = evaluate_position(now)
                if clock_source == "builtin" and not game_finished:
                    builtin_clock.start(time.monotonic(), board.turn)
                if not game_finished and not position_notice:
                    status = (
                        f"Board synchronized with {synced_count} manual "
                        f"move{'s' if synced_count != 1 else ''}."
                    )
                continue

            if illegal_warning and not illegal_edit_mode and (
''',
        "manual-sync action flow",
    )

    return source


def install(app_module: ModuleType) -> None:
    """Recompile app.py once with all completed 0.39.7 runtime features."""
    if getattr(app_module, "_RUNTIME_0397_PATCHED", False):
        return
    source_path = Path(app_module.__file__).resolve()
    original = source_path.read_text(encoding="utf-8")
    patched = apply_source_patches(original)
    code = compile(patched, str(source_path), "exec")
    exec(code, app_module.__dict__)
    app_module._RUNTIME_0397_PATCHED = True
