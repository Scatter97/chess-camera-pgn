from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
ICON_DIRECTORY = ROOT / "build" / "icons"
PNG_PATH = ICON_DIRECTORY / "Knightboard.png"
ICO_PATH = ICON_DIRECTORY / "Knightboard.ico"
ICNS_PATH = ICON_DIRECTORY / "Knightboard.icns"


def _icon(size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), (30, 34, 42, 255))
    draw = ImageDraw.Draw(image)
    margin = max(4, size // 14)
    radius = max(8, size // 9)
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=radius,
        fill=(42, 48, 58, 255),
        outline=(100, 220, 255, 255),
        width=max(2, size // 40),
    )

    board_margin = size // 5
    board_size = size - board_margin * 2
    cell = board_size // 8
    light = (220, 231, 238, 255)
    dark = (92, 126, 166, 255)
    for rank in range(8):
        for file_index in range(8):
            left = board_margin + file_index * cell
            top = board_margin + rank * cell
            right = board_margin + (file_index + 1) * cell
            bottom = board_margin + (rank + 1) * cell
            draw.rectangle(
                (left, top, right, bottom),
                fill=light if (rank + file_index) % 2 == 0 else dark,
            )

    # Simple white knight silhouette over the board.
    scale = size / 256.0
    points = [
        (91, 190),
        (103, 151),
        (126, 126),
        (115, 101),
        (144, 64),
        (188, 86),
        (204, 127),
        (179, 145),
        (169, 190),
    ]
    scaled = [(int(x * scale), int(y * scale)) for x, y in points]
    outline_width = max(3, size // 42)
    draw.polygon(scaled, fill=(245, 246, 248, 255))
    draw.line(scaled + [scaled[0]], fill=(25, 28, 34, 255), width=outline_width, joint="curve")
    draw.ellipse(
        (
            int(164 * scale),
            int(91 * scale),
            int(175 * scale),
            int(102 * scale),
        ),
        fill=(25, 28, 34, 255),
    )
    draw.rounded_rectangle(
        (
            int(75 * scale),
            int(186 * scale),
            int(187 * scale),
            int(213 * scale),
        ),
        radius=max(3, size // 32),
        fill=(245, 246, 248, 255),
        outline=(25, 28, 34, 255),
        width=outline_width,
    )
    return image


def _write_icns() -> None:
    if sys.platform != "darwin" or shutil.which("iconutil") is None:
        return
    iconset = ICON_DIRECTORY / "Knightboard.iconset"
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir(parents=True)
    for points in (16, 32, 128, 256, 512):
        _icon(points).save(iconset / f"icon_{points}x{points}.png")
        _icon(points * 2).save(iconset / f"icon_{points}x{points}@2x.png")
    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset), "-o", str(ICNS_PATH)],
        check=True,
    )
    shutil.rmtree(iconset)


def main() -> None:
    ICON_DIRECTORY.mkdir(parents=True, exist_ok=True)
    image = _icon(512)
    image.save(PNG_PATH)
    image.save(
        ICO_PATH,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    _write_icns()
    print(f"Generated icons in {ICON_DIRECTORY.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
