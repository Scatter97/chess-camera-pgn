from __future__ import annotations

from types import ModuleType

import cv2
import numpy as np


def install(calibration_ui: ModuleType) -> None:
    """Remove the decorative fixed rectangle from the live calibration preview."""
    if getattr(calibration_ui, "_fixed_guide_removed", False):
        return

    original_render_select = calibration_ui.render_select

    def render_select(
        capture: cv2.VideoCapture,
        frame: np.ndarray,
        points: list[tuple[int, int]],
        labels: list[str],
        help_text: str,
        title: str,
        show_debug: bool,
    ):
        result = original_render_select(
            capture,
            frame,
            points,
            labels,
            help_text,
            title,
            show_debug,
        )
        canvas, scale, ox, oy, actual, buttons = result
        area = calibration_ui.Rect(*calibration_ui.PREVIEW)
        preview, _, _, _ = calibration_ui.fit(frame, area)

        margin_x = max(35, int(preview.shape[1] * 0.14))
        margin_y = max(28, int(preview.shape[0] * 0.12))
        right = preview.shape[1] - margin_x
        bottom = preview.shape[0] - margin_y

        # Restore the source pixels covered by the old one-pixel guide.
        canvas[oy + margin_y, ox + margin_x : ox + right + 1] = preview[
            margin_y,
            margin_x : right + 1,
        ]
        canvas[oy + bottom, ox + margin_x : ox + right + 1] = preview[
            bottom,
            margin_x : right + 1,
        ]
        canvas[oy + margin_y : oy + bottom + 1, ox + margin_x] = preview[
            margin_y : bottom + 1,
            margin_x,
        ]
        canvas[oy + margin_y : oy + bottom + 1, ox + right] = preview[
            margin_y : bottom + 1,
            right,
        ]

        # Redraw user-selected geometry because it is the only outline that
        # should remain visible in the preview.
        display_points = [
            calibration_ui.to_display(point, scale, ox, oy)
            for point in points
        ]
        if len(display_points) > 1:
            cv2.polylines(
                canvas,
                [np.asarray(display_points, dtype=np.int32)],
                len(display_points) == 4,
                (95, 232, 145),
                3,
                cv2.LINE_AA,
            )
        for index, position in enumerate(display_points):
            cv2.circle(canvas, position, 12, (20, 28, 24), -1, cv2.LINE_AA)
            cv2.circle(canvas, position, 10, (95, 232, 145), 3, cv2.LINE_AA)
            label = (
                labels[index]
                .replace("image ", "")
                .replace("screen ", "")
                .title()
            )
            calibration_ui.put(
                canvas,
                f"{index + 1}  {label}",
                (position[0] + 15, position[1] - 11),
                scale=0.42,
            )
        return canvas, scale, ox, oy, actual, buttons

    calibration_ui.render_select = render_select
    calibration_ui._fixed_guide_removed = True
