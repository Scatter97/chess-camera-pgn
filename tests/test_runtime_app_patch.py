from pathlib import Path

from chess_camera_app.runtime.runtime_app_patch import apply_source_patches


def test_runtime_patch_matches_current_app_source() -> None:
    source = Path("chess_camera_app/core/app.py").read_text(encoding="utf-8")
    patched = apply_source_patches(source)

    compile(patched, "chess_camera_app/core/app.py", "exec")

    assert "illegal_edit_mode = False" in patched
    assert "training_move_snapshots" in patched
    assert 'click_action == "correct_illegal"' in patched
    assert 'click_action == "continue_correction"' in patched
