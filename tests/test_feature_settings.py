from pathlib import Path

import feature_settings


def test_auto_accept_settings_round_trip(tmp_path: Path) -> None:
    config_path = tmp_path / "camera_config.json"
    config_path.write_text("{}", encoding="utf-8")

    feature_settings.save_auto_accept_settings(config_path, True, 0.91)

    assert feature_settings.auto_accept_settings(config_path) == (True, 0.91)


def test_auto_accept_threshold_is_clamped(tmp_path: Path) -> None:
    config_path = tmp_path / "camera_config.json"
    config_path.write_text("{}", encoding="utf-8")

    feature_settings.save_auto_accept_settings(config_path, True, 2.0)
    assert feature_settings.auto_accept_settings(config_path) == (
        True,
        feature_settings.MAX_AUTO_ACCEPT_THRESHOLD,
    )

    feature_settings.save_auto_accept_settings(config_path, True, 0.1)
    assert feature_settings.auto_accept_settings(config_path) == (
        True,
        feature_settings.MIN_AUTO_ACCEPT_THRESHOLD,
    )


def test_threshold_slider_uses_full_range() -> None:
    assert feature_settings._threshold_from_x(50, 50, 670) == 0.50
    assert feature_settings._threshold_from_x(720, 50, 670) == 0.99
