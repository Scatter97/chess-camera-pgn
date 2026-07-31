from __future__ import annotations

import json
import sys
import time

import numpy as np

import camera_advanced


def test_normalized_settings_loads_saved_values(tmp_path) -> None:
    config = tmp_path / "camera_config.json"
    config.write_text(
        json.dumps(
            {
                "camera_index": 10,
                "detection_fps": 10,
                "detection_resolution": [960, 540],
                "camera_debug_overlay": False,
            }
        ),
        encoding="utf-8",
    )

    assert camera_advanced.normalized_settings(config) == (
        10,
        10,
        (960, 540),
        False,
    )


def test_normalized_settings_falls_back_for_invalid_values(tmp_path) -> None:
    config = tmp_path / "camera_config.json"
    config.write_text(
        json.dumps(
            {
                "camera_index": "not-a-number",
                "detection_fps": 99,
                "detection_resolution": [123, 456],
            }
        ),
        encoding="utf-8",
    )

    assert camera_advanced.normalized_settings(config) == (
        0,
        camera_advanced.DEFAULT_FPS,
        camera_advanced.DEFAULT_RES,
        True,
    )


def test_explicit_camera_argument_overrides_saved_camera(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["chess_camera.py", "--camera", "0"])
    assert camera_advanced.explicit_camera_argument()

    monkeypatch.setattr(sys, "argv", ["chess_camera.py"])
    assert not camera_advanced.explicit_camera_argument()


def test_detection_warp_resizes_and_scales_corners(monkeypatch) -> None:
    received: dict[str, object] = {}

    def fake_warp(frame: np.ndarray, corners: list[list[float]]) -> np.ndarray:
        received["shape"] = frame.shape
        received["corners"] = corners
        return np.zeros((1000, 1000, 3), dtype=np.uint8)

    monkeypatch.setattr(camera_advanced, "_ORIGINAL_WARP", fake_warp)
    camera_advanced.RUNTIME.cached_warp = None
    camera_advanced.RUNTIME.last_detection = 0.0
    camera_advanced.RUNTIME.target_fps = 5
    camera_advanced.RUNTIME.detection_size = (640, 480)
    camera_advanced.RUNTIME.sample_started = time.monotonic()
    camera_advanced.RUNTIME.sample_count = 0

    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    corners = [[0.0, 0.0], [1920.0, 0.0], [1920.0, 1080.0], [0.0, 1080.0]]
    result = camera_advanced.patched_warp()(frame, corners)

    assert result.shape == (1000, 1000, 3)
    assert received["shape"] == (480, 640, 3)
    assert received["corners"] == [
        [0.0, 0.0],
        [640.0, 0.0],
        [640.0, 480.0],
        [0.0, 480.0],
    ]


def test_detection_warp_reuses_cache_until_next_sample(monkeypatch) -> None:
    calls = 0

    def fake_warp(frame: np.ndarray, corners: list[list[float]]) -> np.ndarray:
        nonlocal calls
        calls += 1
        return np.full((1000, 1000, 3), calls, dtype=np.uint8)

    monkeypatch.setattr(camera_advanced, "_ORIGINAL_WARP", fake_warp)
    camera_advanced.RUNTIME.cached_warp = None
    camera_advanced.RUNTIME.last_detection = 0.0
    camera_advanced.RUNTIME.target_fps = 3
    camera_advanced.RUNTIME.detection_size = (320, 240)
    camera_advanced.RUNTIME.sample_started = time.monotonic()
    camera_advanced.RUNTIME.sample_count = 0

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    corners = [[0.0, 0.0], [640.0, 0.0], [640.0, 480.0], [0.0, 480.0]]
    warp = camera_advanced.patched_warp()

    first = warp(frame, corners)
    second = warp(frame, corners)

    assert calls == 1
    assert np.array_equal(first, second)
