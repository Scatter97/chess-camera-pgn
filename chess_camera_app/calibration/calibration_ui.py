from __future__ import annotations

import math
import time
from dataclasses import dataclass
from types import ModuleType

import cv2
import numpy as np


WIDTH, HEIGHT = 1200, 800
PREVIEW = (28, 118, 820, 570)
SIDEBAR_X = 878


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h


def put(
    image: np.ndarray,
    text: str,
    position: tuple[int, int],
    color: tuple[int, int, int] = (240, 243, 248),
    scale: float = 0.56,
    thickness: int = 1,
) -> None:
    cv2.putText(image, text, position, cv2.FONT_HERSHEY_SIMPLEX, scale,
                (8, 10, 14), max(3, thickness + 2), cv2.LINE_AA)
    cv2.putText(image, text, position, cv2.FONT_HERSHEY_SIMPLEX, scale,
                color, thickness, cv2.LINE_AA)


def button(
    image: np.ndarray,
    rect: Rect,
    label: str,
    *,
    primary: bool = False,
    enabled: bool = True,
) -> None:
    if not enabled:
        fill, border, text = (43, 47, 55), (72, 78, 88), (115, 122, 134)
    elif primary:
        fill, border, text = (58, 118, 82), (118, 246, 166), (247, 250, 252)
    else:
        fill, border, text = (48, 53, 62), (102, 112, 128), (232, 236, 242)
    cv2.rectangle(image, (rect.x, rect.y), (rect.x + rect.w, rect.y + rect.h), fill, -1)
    cv2.rectangle(image, (rect.x, rect.y), (rect.x + rect.w, rect.y + rect.h), border, 2)
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 1)
    put(image, label, (rect.x + max(8, (rect.w - tw) // 2),
                       rect.y + (rect.h + th) // 2), text, 0.52)


def fit(frame: np.ndarray, area: Rect) -> tuple[np.ndarray, float, int, int]:
    h, w = frame.shape[:2]
    scale = min(area.w / max(1, w), area.h / max(1, h))
    dw, dh = max(1, int(w * scale)), max(1, int(h * scale))
    resized = cv2.resize(frame, (dw, dh), interpolation=cv2.INTER_AREA)
    return resized, scale, area.x + (area.w - dw) // 2, area.y + (area.h - dh) // 2


def to_display(point: tuple[int, int], scale: float, ox: int, oy: int) -> tuple[int, int]:
    return ox + int(point[0] * scale), oy + int(point[1] * scale)


def to_source(
    point: tuple[int, int],
    scale: float,
    ox: int,
    oy: int,
    shape: tuple[int, ...],
) -> tuple[int, int]:
    h, w = shape[:2]
    x = int(round((point[0] - ox) / max(scale, 1e-9)))
    y = int(round((point[1] - oy) / max(scale, 1e-9)))
    return min(w - 1, max(0, x)), min(h - 1, max(0, y))


def geometry(points: list[tuple[int, int]], shape: tuple[int, ...]) -> tuple[int, list[str]]:
    if len(points) != 4:
        return 0, ["Select all four corners."]
    contour = np.asarray(points, dtype=np.int32)
    h, w = shape[:2]
    area_ratio = abs(float(cv2.contourArea(contour))) / max(1.0, float(w * h))
    convex = bool(cv2.isContourConvex(contour))
    edges = [math.dist(points[i], points[(i + 1) % 4]) for i in range(4)]
    balance = min(edges) / max(max(edges), 1.0)
    issues: list[str] = []
    if not convex:
        issues.append("Corners cross over. Select them in the shown order.")
    if area_ratio < 0.012:
        issues.append("The selected area is too small.")
    if min(edges) < 18:
        issues.append("Two selected corners are too close.")
    if balance < 0.08:
        issues.append("The selected shape is extremely narrow.")
    score = 100.0
    if not convex:
        score -= 55
    score -= max(0.0, 0.08 - area_ratio) * 260
    score -= max(0.0, 0.25 - balance) * 90
    return int(round(max(0.0, min(100.0, score)))), issues


def corrected_preview(frame: np.ndarray, points: list[tuple[int, int]]) -> np.ndarray:
    top = math.dist(points[0], points[1])
    bottom = math.dist(points[3], points[2])
    left = math.dist(points[0], points[3])
    right = math.dist(points[1], points[2])
    aspect = min(2.2, max(0.45, ((top + bottom) / 2) / max(1.0, (left + right) / 2)))
    if aspect >= 1:
        ow, oh = 540, max(220, int(540 / aspect))
    else:
        oh, ow = 500, max(220, int(500 * aspect))
    src = np.asarray(points, dtype=np.float32)
    dst = np.asarray([[0, 0], [ow - 1, 0], [ow - 1, oh - 1], [0, oh - 1]], dtype=np.float32)
    return cv2.warpPerspective(frame, cv2.getPerspectiveTransform(src, dst), (ow, oh))


def debug_lines(capture: cv2.VideoCapture, frame: np.ndarray) -> list[str]:
    h, w = frame.shape[:2]
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    try:
        backend = capture.getBackendName()
    except cv2.error:
        backend = "Unknown"
    return [
        f"Incoming frame: {w} x {h}",
        f"Camera-reported FPS: {fps:.1f}" if fps > 0 else "Camera-reported FPS: unknown",
        f"Backend: {backend or 'Unknown'}",
    ]


def draw_progress(image: np.ndarray, count: int, labels: list[str]) -> None:
    positions = [(925, 330), (1110, 330), (1110, 465), (925, 465)]
    cv2.polylines(image, [np.asarray(positions, dtype=np.int32)], True, (84, 94, 109), 2)
    pulse = 3 + int((math.sin(time.monotonic() * 5) + 1) * 2)
    for i, pos in enumerate(positions):
        active = i == count and count < 4
        done = i < count
        color = (95, 232, 145) if done else ((75, 222, 255) if active else (112, 121, 136))
        cv2.circle(image, pos, 10 + (pulse if active else 0), color, 2 if active else -1)
        put(image, str(i + 1), (pos[0] - 5, pos[1] + 5), (250, 250, 250), 0.38)
    if count < 4:
        label = labels[count].replace("image ", "").replace("screen ", "").title()
        put(image, f"Next: {label}", (904, 505), (90, 225, 255), 0.48)


def render_select(
    capture: cv2.VideoCapture,
    frame: np.ndarray,
    points: list[tuple[int, int]],
    labels: list[str],
    help_text: str,
    title: str,
    show_debug: bool,
) -> tuple[np.ndarray, float, int, int, Rect, dict[str, Rect]]:
    canvas = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    canvas[:] = (24, 27, 33)
    cv2.rectangle(canvas, (0, 0), (WIDTH, 92), (31, 35, 43), -1)
    put(canvas, title, (32, 47), (105, 224, 255), 0.92, 2)
    put(canvas, "Select the four visible corners in order.", (34, 76), (174, 183, 198), 0.49)

    area = Rect(*PREVIEW)
    preview, scale, ox, oy = fit(frame, area)
    cv2.rectangle(canvas, (area.x - 2, area.y - 2),
                  (area.x + area.w + 2, area.y + area.h + 2), (80, 89, 104), 2)

    display_points = [to_display(p, scale, ox, oy) for p in points]
    view = preview.copy()
    margin_x, margin_y = max(35, int(view.shape[1] * 0.14)), max(28, int(view.shape[0] * 0.12))
    cv2.rectangle(view, (margin_x, margin_y),
                  (view.shape[1] - margin_x, view.shape[0] - margin_y), (150, 166, 190), 1)
    if len(points) == 4:
        local = np.asarray([(x - ox, y - oy) for x, y in display_points], dtype=np.int32)
        dark = (view.astype(np.float32) * 0.34).astype(np.uint8)
        mask = np.zeros(view.shape[:2], dtype=np.uint8)
        cv2.fillConvexPoly(mask, local, 255)
        view = np.where(mask[..., None] > 0, view, dark)
    canvas[oy:oy + view.shape[0], ox:ox + view.shape[1]] = view

    if len(display_points) > 1:
        cv2.polylines(canvas, [np.asarray(display_points, dtype=np.int32)],
                      len(display_points) == 4, (95, 232, 145), 3, cv2.LINE_AA)
    for i, pos in enumerate(display_points):
        cv2.circle(canvas, pos, 12, (20, 28, 24), -1, cv2.LINE_AA)
        cv2.circle(canvas, pos, 10, (95, 232, 145), 3, cv2.LINE_AA)
        label = labels[i].replace("image ", "").replace("screen ", "").title()
        put(canvas, f"{i + 1}  {label}", (pos[0] + 15, pos[1] - 11), scale=0.42)

    status = "SELECTION COMPLETE" if len(points) == 4 else f"CORNER {len(points) + 1} OF 4"
    put(canvas, status, (SIDEBAR_X + 24, 145),
        (95, 232, 145) if len(points) == 4 else (75, 222, 255), 0.64, 2)
    help_chunks = [help_text[i:i + 46] for i in range(0, min(len(help_text), 92), 46)]
    for i, line in enumerate(help_chunks):
        put(canvas, line, (SIDEBAR_X + 24, 205 + i * 25), (168, 178, 193), 0.43)
    draw_progress(canvas, len(points), labels)

    buttons = {
        "undo": Rect(SIDEBAR_X + 24, 555, 118, 44),
        "reset": Rect(SIDEBAR_X + 156, 555, 118, 44),
        "debug": Rect(SIDEBAR_X + 24, 612, 250, 42),
        "cancel": Rect(SIDEBAR_X + 24, 670, 118, 44),
        "review": Rect(SIDEBAR_X + 156, 670, 118, 44),
    }
    button(canvas, buttons["undo"], "UNDO", enabled=bool(points))
    button(canvas, buttons["reset"], "RESET", enabled=bool(points))
    button(canvas, buttons["debug"], "HIDE DEBUG" if show_debug else "SHOW DEBUG")
    button(canvas, buttons["cancel"], "CANCEL")
    button(canvas, buttons["review"], "REVIEW", primary=True, enabled=len(points) == 4)

    if show_debug:
        for i, line in enumerate(debug_lines(capture, frame)):
            put(canvas, line, (32, 730 + i * 20), (139, 151, 169), 0.39)
    else:
        put(canvas, "Backspace undo | R reset | D debug | Esc cancel",
            (32, 752), (137, 148, 165), 0.43)

    actual = Rect(ox, oy, preview.shape[1], preview.shape[0])
    return canvas, scale, ox, oy, actual, buttons


def render_review(
    capture: cv2.VideoCapture,
    frame: np.ndarray,
    points: list[tuple[int, int]],
    title: str,
    show_debug: bool,
) -> tuple[np.ndarray, dict[str, Rect], list[str]]:
    canvas = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    canvas[:] = (24, 27, 33)
    cv2.rectangle(canvas, (0, 0), (WIDTH, 92), (31, 35, 43), -1)
    put(canvas, f"{title} - Review", (32, 47), (105, 224, 255), 0.90, 2)
    put(canvas, "Confirm that the selected area is straight and complete.",
        (34, 76), (174, 183, 198), 0.49)

    score, issues = geometry(points, frame.shape)
    left_area, right_area = Rect(28, 130, 540, 500), Rect(602, 130, 540, 500)
    source, scale, sx, sy = fit(frame, left_area)
    canvas[sy:sy + source.shape[0], sx:sx + source.shape[1]] = source
    source_points = [to_display(p, scale, sx, sy) for p in points]
    cv2.polylines(canvas, [np.asarray(source_points, dtype=np.int32)], True,
                  (95, 232, 145), 3, cv2.LINE_AA)
    for pos in source_points:
        cv2.circle(canvas, pos, 8, (95, 232, 145), -1, cv2.LINE_AA)

    corrected = corrected_preview(frame, points)
    shown, _, cx, cy = fit(corrected, right_area)
    canvas[cy:cy + shown.shape[0], cx:cx + shown.shape[1]] = shown
    cv2.rectangle(canvas, (cx - 2, cy - 2),
                  (cx + shown.shape[1] + 2, cy + shown.shape[0] + 2),
                  (95, 232, 145) if not issues else (65, 177, 255), 2)
    put(canvas, "SOURCE", (28, 115), (156, 169, 188), 0.45)
    put(canvas, "CORRECTED PREVIEW", (602, 115), (156, 169, 188), 0.45)
    put(canvas, f"Geometry quality: {score}%", (32, 668),
        (95, 232, 145) if not issues else (65, 177, 255), 0.62, 2)
    put(canvas, (issues[0] if issues else "The four corners form a valid perspective shape.")[:76],
        (32, 700), (65, 177, 255) if issues else (165, 177, 194), 0.46)

    buttons = {
        "redo": Rect(692, 668, 130, 48),
        "debug": Rect(836, 668, 130, 48),
        "confirm": Rect(980, 668, 162, 48),
        "cancel": Rect(980, 728, 162, 42),
    }
    button(canvas, buttons["redo"], "REDO")
    button(canvas, buttons["debug"], "DEBUG")
    button(canvas, buttons["confirm"], "CONFIRM", primary=True, enabled=not issues)
    button(canvas, buttons["cancel"], "CANCEL")
    if show_debug:
        for i, line in enumerate(debug_lines(capture, frame)):
            put(canvas, line, (32, 730 + i * 18), (132, 145, 163), 0.36)
    else:
        put(canvas, "Enter confirms | R selects again | Esc cancels",
            (610, 757), (137, 148, 165), 0.42)
    return canvas, buttons, issues


def calibrate_quadrilateral(
    capture: cv2.VideoCapture,
    window: str,
    labels: list[str],
    help_text: str,
) -> list[list[float]]:
    points: list[tuple[int, int]] = []
    clicks: list[tuple[int, int]] = []
    show_debug = False
    stage = "select"
    last_frame: np.ndarray | None = None
    title = "Phone Screen Calibration" if "phone" in window.lower() else "Board Calibration"

    def mouse(event: int, x: int, y: int, _flags: int, _data: object) -> None:
        if event == cv2.EVENT_LBUTTONUP:
            clicks.append((x, y))

    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, WIDTH, HEIGHT)
    cv2.setMouseCallback(window, mouse)

    try:
        while True:
            ok, frame = capture.read()
            if ok:
                last_frame = frame.copy()
            if last_frame is None:
                waiting = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
                waiting[:] = (24, 27, 33)
                put(waiting, title, (40, 70), (105, 224, 255), 1.0, 2)
                put(waiting, "Waiting for a camera frame...", (40, 125), (180, 190, 205), 0.64)
                cv2.imshow(window, waiting)
                if cv2.waitKey(20) & 0xFF == 27:
                    raise KeyboardInterrupt
                continue

            if stage == "select":
                canvas, scale, ox, oy, actual, buttons = render_select(
                    capture, last_frame, points, labels, help_text, title, show_debug
                )
                cv2.imshow(window, canvas)
                key = cv2.waitKey(20) & 0xFF
                click = clicks.pop(0) if clicks else None

                if key == 27:
                    raise KeyboardInterrupt
                if key in (8, 127) and points:
                    points.pop()
                    continue
                if key in (ord("r"), ord("R")):
                    points.clear()
                    continue
                if key in (ord("d"), ord("D")):
                    show_debug = not show_debug
                    continue
                if key in (10, 13) and len(points) == 4:
                    stage = "review"
                    continue

                if click:
                    if buttons["cancel"].contains(*click):
                        raise KeyboardInterrupt
                    if buttons["undo"].contains(*click) and points:
                        points.pop()
                    elif buttons["reset"].contains(*click):
                        points.clear()
                    elif buttons["debug"].contains(*click):
                        show_debug = not show_debug
                    elif buttons["review"].contains(*click) and len(points) == 4:
                        stage = "review"
                    elif len(points) < 4 and actual.contains(*click):
                        points.append(to_source(click, scale, ox, oy, last_frame.shape))
                        if len(points) == 4:
                            stage = "review"
                    continue
            else:
                canvas, buttons, issues = render_review(
                    capture, last_frame, points, title, show_debug
                )
                cv2.imshow(window, canvas)
                key = cv2.waitKey(20) & 0xFF
                click = clicks.pop(0) if clicks else None

                if key == 27:
                    raise KeyboardInterrupt
                if key in (ord("r"), ord("R")):
                    points.clear()
                    stage = "select"
                    continue
                if key in (ord("d"), ord("D")):
                    show_debug = not show_debug
                    continue
                if key in (10, 13) and not issues:
                    return [[float(x), float(y)] for x, y in points]
                if click:
                    if buttons["cancel"].contains(*click):
                        raise KeyboardInterrupt
                    if buttons["redo"].contains(*click):
                        points.clear()
                        stage = "select"
                    elif buttons["debug"].contains(*click):
                        show_debug = not show_debug
                    elif buttons["confirm"].contains(*click) and not issues:
                        return [[float(x), float(y)] for x, y in points]
                    continue

            try:
                if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                    raise KeyboardInterrupt
            except cv2.error:
                raise KeyboardInterrupt
    finally:
        try:
            cv2.destroyWindow(window)
            cv2.waitKey(1)
        except cv2.error:
            pass


def calibrate_board(capture: cv2.VideoCapture) -> list[list[float]]:
    return calibrate_quadrilateral(
        capture,
        "Chess Camera - Board Calibration",
        ["image top-left", "image top-right", "image bottom-right", "image bottom-left"],
        "Click the corners of the 8 x 8 playing grid. Keep table space around every edge.",
    )


def calibrate_phone(capture: cv2.VideoCapture) -> list[list[float]]:
    return calibrate_quadrilateral(
        capture,
        "Chess Camera - Phone Screen Calibration",
        ["screen top-left", "screen top-right", "screen bottom-right", "screen bottom-left"],
        "Click the lit screen edges, not the phone case.",
    )


def install(target: ModuleType) -> None:
    """Install the guided calibration wizard over the legacy raw-camera screen."""
    target.calibrate_quadrilateral = calibrate_quadrilateral
    target.calibrate_board = calibrate_board
    target.calibrate_phone = calibrate_phone
