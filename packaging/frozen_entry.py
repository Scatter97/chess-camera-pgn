from __future__ import annotations

import sys

from runtime_paths import bootstrap_runtime


# The installed app uses platform-standard writable data folders before any
# module-level relative paths are created.
bootstrap_runtime()

# frozen_app.py is generated from app.py with the 0.39 runtime source patches
# applied before PyInstaller performs its analysis.
import frozen_app as app  # type: ignore[import-not-found]  # noqa: E402

app._RUNTIME_039_PATCHED = True
sys.modules["app"] = app

import chess_camera  # noqa: E402


def main() -> None:
    chess_camera.main()


if __name__ == "__main__":
    main()
