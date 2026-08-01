from pathlib import Path

from chess_camera_app.runtime.runtime_0397_patch import apply_source_patches


def test_runtime_0397_patch_matches_current_app_source() -> None:
    source = Path("chess_camera_app/core/app.py").read_text(encoding="utf-8")
    patched = apply_source_patches(source)

    compile(patched, "chess_camera_app/core/app.py", "exec")

    assert "manual_edit_mode = False" in patched
    assert 'click_action == "manual_edit_board"' in patched
    assert 'click_action == "save_manual_sync"' in patched
    assert "manual_sync.apply_legal_drag" in patched
    assert "training_move_snapshots.append(None)" in patched
