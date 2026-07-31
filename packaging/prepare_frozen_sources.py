from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime_multi_move_patch import apply_source_patches


GENERATED_DIRECTORY = ROOT / "build" / "generated"
GENERATED_APP = GENERATED_DIRECTORY / "frozen_app.py"


def main() -> Path:
    """Write app.py with stable and experimental runtime patches applied."""
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    patched = apply_source_patches(source)
    GENERATED_DIRECTORY.mkdir(parents=True, exist_ok=True)
    (GENERATED_DIRECTORY / "__init__.py").write_text("", encoding="utf-8")
    GENERATED_APP.write_text(
        patched
        + "\n\n# PyInstaller uses this already-patched module directly.\n"
        + "_RUNTIME_039_PATCHED = True\n"
        + "_RUNTIME_0397_PATCHED = True\n"
        + "_RUNTIME_MULTI_MOVE_PATCHED = True\n",
        encoding="utf-8",
    )
    print(f"Generated {GENERATED_APP.relative_to(ROOT)}")
    return GENERATED_APP


if __name__ == "__main__":
    main()
