from pathlib import Path

import chess
import cv2
import numpy as np

import piece_theme_system


def _redirect_assets(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        piece_theme_system,
        "PIECE_PACK_DIRECTORY",
        tmp_path / "piece_packs",
    )
    monkeypatch.setattr(
        piece_theme_system,
        "SOUND_PACK_DIRECTORY",
        tmp_path / "sound_packs",
    )
    piece_theme_system.clear_image_cache()


def test_bundled_assets_include_piece_pack_and_two_sound_packs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _redirect_assets(monkeypatch, tmp_path)

    piece_theme_system.ensure_bundled_assets()

    assert "Classic Vector" in piece_theme_system.available_piece_packs()
    sound_packs = piece_theme_system.available_sound_packs()
    assert "Classic Wood" in sound_packs
    assert "Soft Digital" in sound_packs
    for event in piece_theme_system.SOUND_EVENTS:
        assert (
            piece_theme_system.SOUND_PACK_DIRECTORY
            / "Classic Wood"
            / f"{event}.wav"
        ).is_file()


def test_custom_piece_pack_is_discovered(monkeypatch, tmp_path: Path) -> None:
    _redirect_assets(monkeypatch, tmp_path)
    directory = piece_theme_system.PIECE_PACK_DIRECTORY / "My Pieces"
    directory.mkdir(parents=True)
    sprite = np.zeros((32, 32, 4), dtype=np.uint8)
    sprite[:, :, 3] = 255
    for filename in piece_theme_system.PIECE_FILES.values():
        assert cv2.imwrite(str(directory / filename), sprite)

    assert "My Pieces" in piece_theme_system.available_piece_packs()


def test_generated_piece_icon_has_visible_alpha() -> None:
    image = piece_theme_system._piece_icon(chess.KNIGHT, chess.WHITE)

    assert image.shape == (128, 128, 4)
    assert int(image[:, :, 3].max()) == 255
    assert int(np.count_nonzero(image[:, :, 3])) > 500


def test_sound_event_tracks_move_and_capture_squares() -> None:
    quiet = piece_theme_system._sound_event([chess.Move.from_uci("e2e4")])
    assert quiet is not None
    event, changed = quiet
    assert event == "move"
    assert chess.E2 in changed
    assert chess.E4 in changed

    capture_moves = [
        chess.Move.from_uci("e2e4"),
        chess.Move.from_uci("d7d5"),
        chess.Move.from_uci("e4d5"),
    ]
    capture = piece_theme_system._sound_event(capture_moves)
    assert capture is not None
    assert capture[0] == "capture"
