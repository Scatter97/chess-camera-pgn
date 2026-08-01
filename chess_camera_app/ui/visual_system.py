"""Shared Knightboard v0.50 visual language for every OpenCV screen."""

from __future__ import annotations

import cv2
import numpy as np


# OpenCV is BGR, not RGB.
INK = (19, 23, 31)
SURFACE = (30, 36, 47)
SURFACE_RAISED = (39, 47, 61)
SURFACE_HOVER = (48, 58, 76)
BORDER = (82, 96, 119)
MUTED = (160, 172, 191)
TEXT = (244, 247, 251)
ACCENT = (224, 182, 92)
ACCENT_DARK = (133, 104, 48)
SUCCESS = (112, 210, 147)
DANGER = (101, 96, 220)


def canvas(height: int, width: int) -> np.ndarray:
    """Create the deep navy base used by Knightboard views."""
    view = np.zeros((height, width, 3), dtype=np.uint8)
    view[:] = INK
    # A restrained top gradient gives flat HighGUI windows depth without assets.
    for y in range(min(height, 150)):
        amount = int(12 * (1 - y / 150))
        view[y, :, :] = tuple(min(255, value + amount) for value in INK)
    return view


def rounded_rect(
    image: np.ndarray,
    left: int,
    top: int,
    right: int,
    bottom: int,
    fill: tuple[int, int, int],
    border: tuple[int, int, int] | None = None,
    radius: int = 14,
    thickness: int = 1,
) -> None:
    """Draw an antialiased rounded panel using only OpenCV primitives."""
    radius = max(1, min(radius, (right - left) // 2, (bottom - top) // 2))
    cv2.rectangle(image, (left + radius, top), (right - radius, bottom), fill, -1)
    cv2.rectangle(image, (left, top + radius), (right, bottom - radius), fill, -1)
    for center in ((left + radius, top + radius), (right - radius, top + radius),
                   (left + radius, bottom - radius), (right - radius, bottom - radius)):
        cv2.circle(image, center, radius, fill, -1, cv2.LINE_AA)
    if border is not None:
        cv2.line(image, (left + radius, top), (right - radius, top), border, thickness, cv2.LINE_AA)
        cv2.line(image, (left + radius, bottom), (right - radius, bottom), border, thickness, cv2.LINE_AA)
        cv2.line(image, (left, top + radius), (left, bottom - radius), border, thickness, cv2.LINE_AA)
        cv2.line(image, (right, top + radius), (right, bottom - radius), border, thickness, cv2.LINE_AA)
        for center in ((left + radius, top + radius), (right - radius, top + radius),
                       (left + radius, bottom - radius), (right - radius, bottom - radius)):
            cv2.circle(image, center, radius, border, thickness, cv2.LINE_AA)


def card(image: np.ndarray, left: int, top: int, right: int, bottom: int) -> None:
    rounded_rect(image, left, top, right, bottom, SURFACE, BORDER, 16)


def brand_header(image: np.ndarray, title: str, subtitle: str = "") -> None:
    """Put a consistent Knightboard identity bar at the top of a screen."""
    width = image.shape[1]
    rounded_rect(image, 20, 16, width - 20, 82, SURFACE, BORDER, 14)
    cv2.circle(image, (54, 49), 17, ACCENT, -1, cv2.LINE_AA)
    cv2.putText(image, "N", (46, 57), cv2.FONT_HERSHEY_DUPLEX, 0.58, INK, 2, cv2.LINE_AA)
    cv2.putText(image, "KNIGHTBOARD", (84, 43), cv2.FONT_HERSHEY_DUPLEX, 0.52, ACCENT, 1, cv2.LINE_AA)
    cv2.putText(image, title, (84, 68), cv2.FONT_HERSHEY_SIMPLEX, 0.62, TEXT, 2, cv2.LINE_AA)
    if subtitle:
        (tw, _), _ = cv2.getTextSize(subtitle, cv2.FONT_HERSHEY_SIMPLEX, 0.43, 1)
        cv2.putText(image, subtitle, (width - 42 - tw, 57), cv2.FONT_HERSHEY_SIMPLEX, 0.43, MUTED, 1, cv2.LINE_AA)


def install_window_branding() -> None:
    """Rename every legacy HighGUI title without changing each feature module."""
    if getattr(cv2, "_knightboard_window_branding", False):
        return
    original_named_window = cv2.namedWindow
    original_imshow = cv2.imshow
    original_callback = cv2.setMouseCallback
    original_destroy = cv2.destroyWindow
    original_put_text = cv2.putText

    def renamed(name: str) -> str:
        return name.replace("Chess Camera PGN", "Knightboard").replace("Chess Camera", "Knightboard")

    def named_window(name: str, flags: int = cv2.WINDOW_AUTOSIZE) -> None:
        original_named_window(renamed(name), flags)

    def imshow(name: str, image: np.ndarray) -> None:
        original_imshow(renamed(name), image)

    def callback(name: str, on_mouse, param=None) -> None:
        original_callback(renamed(name), on_mouse, param)

    def destroy(name: str) -> None:
        original_destroy(renamed(name))

    def put_text(image, text, org, font_face, font_scale, color, thickness=None,
                 line_type=None, bottom_left_origin=None):
        """Keep legacy modules visually rebranded until their next UI rewrite."""
        text = renamed(str(text))
        args = [image, text, org, font_face, font_scale, color]
        if thickness is not None:
            args.append(thickness)
        if line_type is not None:
            args.append(line_type)
        if bottom_left_origin is not None:
            args.append(bottom_left_origin)
        return original_put_text(*args)

    cv2.namedWindow = named_window  # type: ignore[assignment]
    cv2.imshow = imshow  # type: ignore[assignment]
    cv2.setMouseCallback = callback  # type: ignore[assignment]
    cv2.destroyWindow = destroy  # type: ignore[assignment]
    cv2.putText = put_text  # type: ignore[assignment]
    cv2._knightboard_window_branding = True  # type: ignore[attr-defined]
