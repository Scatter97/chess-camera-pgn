from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


APP_DIRECTORY_NAME = "chess-camera"
APP_DISPLAY_NAME = "ChessCamera"
DATA_ENVIRONMENT_VARIABLE = "CHESS_CAMERA_DATA_DIR"


def is_frozen() -> bool:
    """Return whether the app is running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    """Return the read-only root that contains bundled application resources."""
    temporary_root = getattr(sys, "_MEIPASS", None)
    if temporary_root:
        return Path(str(temporary_root)).resolve()
    return Path(__file__).resolve().parent


def default_data_root() -> Path:
    """Return a writable per-user data folder for packaged installations."""
    configured = os.environ.get(DATA_ENVIRONMENT_VARIABLE)
    if configured:
        return Path(configured).expanduser().resolve()

    # Source checkouts keep their current behavior and store generated files in
    # the repository folder. Installed builds use platform-standard user paths.
    if not is_frozen():
        return Path.cwd().resolve()

    home = Path.home()
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        return base / APP_DISPLAY_NAME
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / APP_DISPLAY_NAME

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg_data_home).expanduser() if xdg_data_home else home / ".local" / "share"
    return base / APP_DIRECTORY_NAME


def _copy_bundled_books(target_root: Path) -> None:
    """Seed the writable opening-book directory without replacing user files."""
    source = bundle_root() / "books"
    destination = target_root / "books"
    if not source.is_dir():
        return
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        target = destination / item.name
        try:
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            elif not target.exists():
                shutil.copy2(item, target)
        except OSError:
            # A missing optional opening book must not stop camera recording.
            continue


def bootstrap_runtime() -> Path:
    """Prepare writable folders and make relative app paths package-safe."""
    root = default_data_root()
    root.mkdir(parents=True, exist_ok=True)
    for folder in (
        "board_profiles",
        "books",
        "engines",
        "games",
        "piece_packs",
        "sound_packs",
    ):
        (root / folder).mkdir(parents=True, exist_ok=True)

    _copy_bundled_books(root)
    os.environ[DATA_ENVIRONMENT_VARIABLE] = str(root)
    os.chdir(root)
    return root
