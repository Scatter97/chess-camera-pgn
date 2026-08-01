from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Callable

import cv2
import numpy as np

from chess_camera_app.ui import pregame_ui
from chess_camera_app.ui import ui_support as ui
from chess_camera_app.ui.pregame_ui import Button

FPS_OPTIONS = (3, 5, 10, 15)
RES_OPTIONS = ((320, 240), (640, 480), (960, 540), (1280, 720))
DEFAULT_FPS = 5
DEFAULT_RES = (640, 480)


@dataclass(frozen=True)
class Camera:
    index: int
    name: str
    path: str


@dataclass
class Runtime:
    camera_index: int = 0
    camera_name: str = "Camera 0"
    backend: str = ""
    input_size: tuple[int, int] = (0, 0)
    driver_fps: float = 0.0
    target_fps: int = DEFAULT_FPS
    detection_size: tuple[int, int] = DEFAULT_RES
    show_debug: bool = True
    latest_preview: np.ndarray | None = None
    cached_warp: np.ndarray | None = None
    last_detection: float = 0.0
    sample_started: float = 0.0
    sample_count: int = 0
    measured_fps: float = 0.0


RUNTIME = Runtime()
_ORIGINAL_OPEN: Callable[[int], cv2.VideoCapture] | None = None
_ORIGINAL_WARP: Callable[[np.ndarray, list[list[float]]], np.ndarray] | None = None


def load_config(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def save_config(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def normalized_settings(path: Path) -> tuple[int, int, tuple[int, int], bool]:
    config = load_config(path)
    try:
        camera = max(0, int(config.get("camera_index", 0)))
    except (TypeError, ValueError):
        camera = 0
    try:
        fps = int(config.get("detection_fps", DEFAULT_FPS))
    except (TypeError, ValueError):
        fps = DEFAULT_FPS
    fps = fps if fps in FPS_OPTIONS else DEFAULT_FPS
    raw_size = config.get("detection_resolution", list(DEFAULT_RES))
    try:
        size = (int(raw_size[0]), int(raw_size[1]))  # type: ignore[index]
    except (TypeError, ValueError, IndexError):
        size = DEFAULT_RES
    size = size if size in RES_OPTIONS else DEFAULT_RES
    return camera, fps, size, bool(config.get("camera_debug_overlay", True))


def explicit_camera_argument() -> bool:
    return any(
        arg == "--camera" or arg.startswith("--camera=")
        for arg in sys.argv[1:]
    )


def linux_name(index: int) -> str:
    try:
        value = Path(f"/sys/class/video4linux/video{index}/name").read_text(
            encoding="utf-8"
        ).strip()
    except OSError:
        value = ""
    return value or f"Video device {index}"


def cameras(target: ModuleType, current: int) -> list[Camera]:
    found: list[Camera] = []
    if sys.platform.startswith("linux"):
        for path in sorted(Path("/dev").glob("video*")):
            match = re.fullmatch(r"video(\d+)", path.name)
            if match:
                index = int(match.group(1))
                found.append(Camera(index, linux_name(index), str(path)))
    else:
        backend = target.select_camera_backend()
        for index in range(10):
            capture = cv2.VideoCapture(index, backend)
            try:
                if capture.isOpened():
                    found.append(Camera(index, f"Camera {index}", str(index)))
            finally:
                capture.release()
    if not found or all(item.index != current for item in found):
        found.append(Camera(current, f"Camera {current}", str(current)))
    return sorted(found, key=lambda item: item.index)


def cycle(options: tuple, current, amount: int):
    try:
        index = options.index(current)
    except ValueError:
        index = 0
    return options[(index + amount) % len(options)]


def put(
    image: np.ndarray,
    text: str,
    position: tuple[int, int],
    color: tuple[int, int, int] = (235, 238, 244),
    scale: float = 0.39,
) -> None:
    cv2.putText(
        image,
        text,
        position,
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        (8, 9, 12),
        3,
        cv2.LINE_AA,
    )
    cv2.putText(
        image,
        text,
        position,
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        color,
        1,
        cv2.LINE_AA,
    )


def fit(image: np.ndarray, width: int, height: int) -> np.ndarray:
    result = np.zeros((height, width, 3), dtype=np.uint8)
    result[:] = (17, 19, 24)
    h, w = image.shape[:2]
    scale = min(width / max(1, w), height / max(1, h))
    rw, rh = max(1, int(w * scale)), max(1, int(h * scale))
    resized = cv2.resize(image, (rw, rh), interpolation=cv2.INTER_AREA)
    x, y = (width - rw) // 2, (height - rh) // 2
    result[y : y + rh, x : x + rw] = resized
    return result


def patched_open(config_path: Path):
    original = _ORIGINAL_OPEN
    if original is None:
        raise RuntimeError("Advanced camera settings were not installed correctly.")

    def open_camera(index: int) -> cv2.VideoCapture:
        saved_camera, fps, size, show_debug = normalized_settings(config_path)
        selected = index if explicit_camera_argument() else saved_camera
        capture = original(selected)
        try:
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except cv2.error:
            pass
        RUNTIME.camera_index = selected
        RUNTIME.camera_name = (
            linux_name(selected)
            if sys.platform.startswith("linux")
            else f"Camera {selected}"
        )
        try:
            RUNTIME.backend = capture.getBackendName()
        except (cv2.error, AttributeError):
            RUNTIME.backend = "OpenCV"
        RUNTIME.input_size = (
            int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )
        RUNTIME.driver_fps = max(0.0, float(capture.get(cv2.CAP_PROP_FPS)))
        RUNTIME.target_fps = fps
        RUNTIME.detection_size = size
        RUNTIME.show_debug = show_debug
        RUNTIME.latest_preview = None
        RUNTIME.cached_warp = None
        RUNTIME.last_detection = 0.0
        RUNTIME.sample_started = time.monotonic()
        RUNTIME.sample_count = 0
        RUNTIME.measured_fps = 0.0
        return capture

    return open_camera


def patched_warp():
    original = _ORIGINAL_WARP
    if original is None:
        raise RuntimeError("Advanced camera settings were not installed correctly.")

    def warp_board(frame: np.ndarray, corners: list[list[float]]) -> np.ndarray:
        RUNTIME.latest_preview = frame.copy()
        source_h, source_w = frame.shape[:2]
        RUNTIME.input_size = (source_w, source_h)
        now = time.monotonic()
        due = (
            RUNTIME.cached_warp is None
            or now - RUNTIME.last_detection >= 1.0 / max(1, RUNTIME.target_fps)
        )
        if due:
            width, height = RUNTIME.detection_size
            small = cv2.resize(
                frame,
                (width, height),
                interpolation=(
                    cv2.INTER_AREA if width < source_w else cv2.INTER_LINEAR
                ),
            )
            sx, sy = width / max(1, source_w), height / max(1, source_h)
            adjusted = [[float(x) * sx, float(y) * sy] for x, y in corners]
            RUNTIME.cached_warp = original(small, adjusted)
            RUNTIME.last_detection = now
            RUNTIME.sample_count += 1
            elapsed = now - RUNTIME.sample_started
            if elapsed >= 0.75:
                RUNTIME.measured_fps = RUNTIME.sample_count / elapsed
                RUNTIME.sample_count = 0
                RUNTIME.sample_started = now
        return RUNTIME.cached_warp.copy()

    return warp_board


def render_camera_panel(
    board_view: np.ndarray,
    detection_mode_name: str,
    display_fps: float,
    stability_progress: float,
    fast_mode: bool,
) -> np.ndarray:
    panel = np.zeros((620, 300, 3), dtype=np.uint8)
    panel[:] = (25, 28, 34)
    source = (
        RUNTIME.latest_preview
        if RUNTIME.latest_preview is not None
        else board_view
    )
    panel[36:182, 20:280] = fit(source, 260, 146)
    cv2.rectangle(panel, (20, 36), (279, 181), (112, 122, 138), 2)
    put(
        panel,
        f"{detection_mode_name} detection",
        (20, 19),
        (120, 255, 170) if fast_mode else (120, 220, 255),
    )
    if RUNTIME.show_debug:
        put(
            panel,
            f"Preview {display_fps:.1f} FPS | Detect {RUNTIME.measured_fps:.1f}/{RUNTIME.target_fps}",
            (20, 204),
            (120, 255, 170),
            0.34,
        )
        put(
            panel,
            f"Input {RUNTIME.input_size[0]}x{RUNTIME.input_size[1]} | Detection {RUNTIME.detection_size[0]}x{RUNTIME.detection_size[1]}",
            (20, 224),
            (185, 195, 210),
            0.32,
        )
        put(
            panel,
            f"Camera {RUNTIME.camera_index}: {RUNTIME.camera_name[:23]}",
            (20, 244),
            (185, 195, 210),
            0.32,
        )
        put(
            panel,
            f"{RUNTIME.backend} | Driver {RUNTIME.driver_fps:.1f} FPS",
            (20, 263),
            (145, 155, 170),
            0.31,
        )
    cv2.rectangle(panel, (20, 272), (280, 279), (18, 19, 22), -1)
    progress = int(260 * min(1.0, max(0.0, stability_progress)))
    if progress:
        cv2.rectangle(
            panel,
            (20, 272),
            (20 + progress, 279),
            (80, 220, 120),
            -1,
        )
    return panel


def test_preview(camera: Camera) -> str:
    original = _ORIGINAL_OPEN
    if original is None:
        return "Camera test is unavailable."
    try:
        capture = original(camera.index)
    except RuntimeError as error:
        return str(error)
    window = f"Camera Test - {camera.name}"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 960, 600)
    started, frames, measured = time.monotonic(), 0, 0.0
    try:
        while True:
            ok, frame = capture.read()
            if ok:
                frames += 1
                measured = frames / max(0.001, time.monotonic() - started)
                view = frame.copy()
                put(
                    view,
                    f"Camera {camera.index} | {frame.shape[1]}x{frame.shape[0]} | {measured:.1f} FPS",
                    (24, 36),
                    (120, 255, 170),
                    0.62,
                )
                put(
                    view,
                    "Enter or Esc closes the test",
                    (24, 70),
                    scale=0.48,
                )
                cv2.imshow(window, view)
            key = cv2.waitKey(1) & 0xFF
            if key in (10, 13, 27):
                return f"Camera test reached {measured:.1f} preview FPS."
            try:
                if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                    return f"Camera test reached {measured:.1f} preview FPS."
            except cv2.error:
                return f"Camera test reached {measured:.1f} preview FPS."
    finally:
        capture.release()
        try:
            cv2.destroyWindow(window)
        except cv2.error:
            pass


def camera_settings_screen(target: ModuleType, config_path: Path) -> None:
    selected, fps, resolution, debug = normalized_settings(config_path)
    available = cameras(target, selected)
    position = next(
        (i for i, item in enumerate(available) if item.index == selected),
        0,
    )
    window = "Chess Camera - Advanced Camera Settings"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 900, 650)
    queue: list[str] = []
    buttons: list[Button] = []
    message = "Preview FPS is unlimited. Detection uses the settings below."

    def mouse(event: int, x: int, y: int, _flags: int, _data: object) -> None:
        if event == cv2.EVENT_LBUTTONUP:
            action = pregame_ui.clicked_action(buttons, x, y)
            if action:
                queue.append(action)

    cv2.setMouseCallback(window, mouse)
    while True:
        camera = available[position]
        view = np.zeros((650, 900, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        ui._put(
            view,
            "Advanced Camera Settings",
            (42, 55),
            (100, 220, 255),
            0.92,
            2,
        )
        ui._put(
            view,
            "Preview FPS: MAXIMUM (no software limit)",
            (42, 98),
            (120, 255, 170),
            0.54,
        )
        ui._put(view, "CAMERA", (42, 150), (165, 175, 190), 0.47)
        ui._put(
            view,
            f"Camera {camera.index}: {camera.name[:58]}",
            (42, 187),
            (230, 234, 240),
            0.58,
        )
        ui._put(
            view,
            camera.path[-80:],
            (42, 215),
            (145, 155, 170),
            0.40,
        )
        ui._put(view, "DETECTION", (42, 335), (165, 175, 190), 0.47)
        ui._put(
            view,
            f"Detection FPS: {fps}",
            (42, 377),
            (120, 220, 255),
            0.58,
        )
        ui._put(
            view,
            f"Detection resolution: {resolution[0]} x {resolution[1]}",
            (42, 420),
            (120, 220, 255),
            0.58,
        )
        ui._put(
            view,
            f"Live debug statistics: {'ON' if debug else 'OFF'}",
            (42, 463),
            (230, 234, 240),
            0.52,
        )
        buttons = [
            Button("camera_prev", "< CAMERA", 42, 245, 145, 44),
            Button("camera_next", "CAMERA >", 202, 245, 145, 44),
            Button("refresh", "REFRESH", 362, 245, 145, 44),
            Button("test", "TEST PREVIEW", 522, 245, 185, 44, active=True),
            Button("fps_prev", "- FPS", 590, 350, 115, 42),
            Button("fps_next", "+ FPS", 720, 350, 115, 42),
            Button("res_prev", "< RES", 590, 401, 115, 42),
            Button("res_next", "RES >", 720, 401, 115, 42),
            Button("debug", "TOGGLE DEBUG", 590, 452, 245, 42),
            Button(
                "save",
                "SAVE CAMERA SETTINGS",
                42,
                535,
                400,
                56,
                active=True,
            ),
            Button("back", "BACK", 472, 535, 220, 56),
        ]
        for item in buttons:
            pregame_ui.draw_button(view, item)
        ui._put(view, message[:90], (42, 625), (120, 220, 255), 0.43)
        cv2.imshow(window, view)
        key = cv2.waitKey(20) & 0xFF
        action = queue.pop(0) if queue else None
        if action == "camera_prev":
            position = (position - 1) % len(available)
        elif action == "camera_next":
            position = (position + 1) % len(available)
        elif action == "refresh":
            current = available[position].index
            available = cameras(target, current)
            position = next(
                (i for i, item in enumerate(available) if item.index == current),
                0,
            )
            message = f"Found {len(available)} camera device(s)."
        elif action == "test":
            message = test_preview(available[position])
            cv2.namedWindow(window, cv2.WINDOW_NORMAL)
            cv2.setMouseCallback(window, mouse)
        elif action == "fps_prev":
            fps = cycle(FPS_OPTIONS, fps, -1)
        elif action == "fps_next":
            fps = cycle(FPS_OPTIONS, fps, 1)
        elif action == "res_prev":
            resolution = cycle(RES_OPTIONS, resolution, -1)
        elif action == "res_next":
            resolution = cycle(RES_OPTIONS, resolution, 1)
        elif action == "debug":
            debug = not debug
        elif action == "save":
            chosen = available[position]
            config = load_config(config_path)
            config.update(
                {
                    "camera_index": chosen.index,
                    "camera_name": chosen.name,
                    "detection_fps": fps,
                    "detection_resolution": list(resolution),
                    "camera_debug_overlay": debug,
                }
            )
            save_config(config_path, config)
            message = "Saved. Recalibrate the board after changing cameras."
        elif action == "back" or key == 27:
            cv2.destroyWindow(window)
            return
        try:
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                return
        except cv2.error:
            return


def settings_hub(
    target: ModuleType,
    original_settings: Callable[[], None],
) -> None:
    window = "Chess Camera - Settings"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 760, 480)
    buttons = [
        Button(
            "camera",
            "ADVANCED CAMERA SETTINGS",
            85,
            150,
            590,
            72,
            active=True,
        ),
        Button("engine", "ANALYSIS ENGINE SETTINGS", 85, 245, 590, 72),
        Button("back", "BACK", 245, 365, 270, 58),
    ]
    queue: list[str] = []

    def mouse(event: int, x: int, y: int, _flags: int, _data: object) -> None:
        if event == cv2.EVENT_LBUTTONUP:
            action = pregame_ui.clicked_action(buttons, x, y)
            if action:
                queue.append(action)

    cv2.setMouseCallback(window, mouse)
    while True:
        view = np.zeros((480, 760, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        ui._put(view, "Settings", (55, 65), (100, 220, 255), 1.0, 2)
        ui._put(
            view,
            "Configure camera performance or the local analysis engine.",
            (55, 105),
            (175, 185, 200),
            0.48,
        )
        for item in buttons:
            pregame_ui.draw_button(view, item)
        cv2.imshow(window, view)
        key = cv2.waitKey(20) & 0xFF
        action = queue.pop(0) if queue else None
        if action == "camera":
            cv2.destroyWindow(window)
            camera_settings_screen(target, target.CONFIG_PATH)
            cv2.namedWindow(window, cv2.WINDOW_NORMAL)
            cv2.setMouseCallback(window, mouse)
        elif action == "engine":
            cv2.destroyWindow(window)
            original_settings()
            cv2.namedWindow(window, cv2.WINDOW_NORMAL)
            cv2.setMouseCallback(window, mouse)
        elif action == "back" or key == 27:
            cv2.destroyWindow(window)
            return
        try:
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                return
        except cv2.error:
            return


def install(target: ModuleType, navigation: ModuleType) -> None:
    global _ORIGINAL_OPEN, _ORIGINAL_WARP
    if getattr(target, "_advanced_camera_installed", False):
        return
    _ORIGINAL_OPEN = target.open_camera
    _ORIGINAL_WARP = target.warp_board
    original_settings = navigation.settings_screen
    target.open_camera = patched_open(target.CONFIG_PATH)
    target.warp_board = patched_warp()
    target.render_camera_panel = render_camera_panel
    navigation.settings_screen = lambda: settings_hub(target, original_settings)
    target._advanced_camera_installed = True
