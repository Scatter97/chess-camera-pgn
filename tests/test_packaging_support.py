from __future__ import annotations

from pathlib import Path

from chess_camera_app.runtime import runtime_paths


ROOT = Path(__file__).resolve().parents[1]


def test_packaging_definitions_are_present() -> None:
    required = (
        "build_windows_exe.bat",
        "packaging/ChessCamera.spec",
        "packaging/build_deb.sh",
        "packaging/build_macos.sh",
        "packaging/frozen_entry.py",
        "packaging/prepare_frozen_sources.py",
        "packaging/requirements-build.txt",
    )
    for relative_path in required:
        assert (ROOT / relative_path).is_file(), relative_path


def test_frozen_entry_uses_writable_runtime_and_prepatched_app() -> None:
    entry = (ROOT / "packaging/frozen_entry.py").read_text(encoding="utf-8")
    assert "bootstrap_runtime()" in entry
    assert "import frozen_app as app" in entry
    assert 'sys.modules["app"] = app' in entry


def test_frozen_source_builder_includes_multi_move_runtime_patch() -> None:
    builder = (ROOT / "packaging/prepare_frozen_sources.py").read_text(
        encoding="utf-8"
    )
    assert "from chess_camera_app.runtime.runtime_multi_move_patch import apply_source_patches" in builder
    assert "_RUNTIME_MULTI_MOVE_PATCHED = True" in builder


def test_pyinstaller_spec_includes_camera_permission_and_ocr_data() -> None:
    spec = (ROOT / "packaging/ChessCamera.spec").read_text(encoding="utf-8")
    assert 'collect_data_files("rapidocr")' in spec
    assert 'collect_dynamic_libs("onnxruntime")' in spec
    assert "NSCameraUsageDescription" in spec
    assert 'name="ChessCamera.app"' in spec


def test_explicit_runtime_data_directory_is_respected(
    monkeypatch,
    tmp_path: Path,
) -> None:
    selected = tmp_path / "portable-data"
    monkeypatch.setenv(runtime_paths.DATA_ENVIRONMENT_VARIABLE, str(selected))
    assert runtime_paths.default_data_root() == selected.resolve()
