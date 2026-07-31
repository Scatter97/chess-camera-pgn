from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

import chess
import cv2
import numpy as np

from chess_tracker import move_changed_squares


PIECE_PACK_DIRECTORY = Path("piece_packs")
SOUND_PACK_DIRECTORY = Path("sound_packs")
PIECE_PACK_KEY = "piece_pack"
SOUND_PACK_KEY = "sound_pack"
SOUND_ENABLED_KEY = "piece_sounds_enabled"
MOVE_HIGHLIGHTS_KEY = "move_highlights_enabled"

PIECE_FILES: dict[tuple[bool, int], str] = {
    (chess.WHITE, chess.KING): "wK.png",
    (chess.WHITE, chess.QUEEN): "wQ.png",
    (chess.WHITE, chess.ROOK): "wR.png",
    (chess.WHITE, chess.BISHOP): "wB.png",
    (chess.WHITE, chess.KNIGHT): "wN.png",
    (chess.WHITE, chess.PAWN): "wP.png",
    (chess.BLACK, chess.KING): "bK.png",
    (chess.BLACK, chess.QUEEN): "bQ.png",
    (chess.BLACK, chess.ROOK): "bR.png",
    (chess.BLACK, chess.BISHOP): "bB.png",
    (chess.BLACK, chess.KNIGHT): "bN.png",
    (chess.BLACK, chess.PAWN): "bP.png",
}
SOUND_EVENTS = ("move", "capture", "check", "castle", "promotion")


@dataclass
class ThemeRuntime:
    config_path: Path = Path("camera_config.json")
    last_fingerprint: tuple[str, ...] = ()
    last_move_squares: frozenset[chess.Square] = frozenset()
    image_cache: dict[tuple[str, int], np.ndarray] = field(default_factory=dict)


STATE = ThemeRuntime()


def _read_config(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def _piece_colors(white: bool) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    if white:
        return (238, 241, 244, 255), (28, 31, 38, 255)
    return (42, 46, 55, 255), (232, 235, 240, 255)


def _filled_polygon(
    image: np.ndarray,
    points: list[tuple[int, int]],
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int],
    thickness: int = 4,
) -> None:
    polygon = np.asarray(points, dtype=np.int32)
    cv2.fillPoly(image, [polygon], fill, cv2.LINE_AA)
    cv2.polylines(image, [polygon], True, outline, thickness, cv2.LINE_AA)


def _piece_icon(piece_type: int, white: bool, size: int = 128) -> np.ndarray:
    """Generate an original Staunton-inspired transparent piece sprite."""
    image = np.zeros((size, size, 4), dtype=np.uint8)
    fill, outline = _piece_colors(white)

    def ellipse(center: tuple[int, int], axes: tuple[int, int], color, thickness: int = -1) -> None:
        cv2.ellipse(image, center, axes, 0, 0, 360, color, thickness, cv2.LINE_AA)

    def base() -> None:
        _filled_polygon(
            image,
            [(24, 104), (31, 91), (97, 91), (104, 104), (99, 113), (29, 113)],
            fill,
            outline,
        )
        cv2.line(image, (34, 90), (94, 90), outline, 4, cv2.LINE_AA)

    if piece_type == chess.PAWN:
        ellipse((64, 38), (18, 18), outline)
        ellipse((64, 38), (14, 14), fill)
        _filled_polygon(
            image,
            [(49, 54), (79, 54), (85, 86), (43, 86)],
            fill,
            outline,
        )
        base()
    elif piece_type == chess.ROOK:
        _filled_polygon(
            image,
            [(35, 23), (47, 23), (47, 34), (58, 34), (58, 23),
             (70, 23), (70, 34), (81, 34), (81, 23), (93, 23),
             (90, 48), (38, 48)],
            fill,
            outline,
        )
        _filled_polygon(image, [(43, 48), (85, 48), (89, 88), (39, 88)], fill, outline)
        base()
    elif piece_type == chess.KNIGHT:
        _filled_polygon(
            image,
            [(39, 88), (45, 66), (55, 51), (50, 39), (65, 19),
             (89, 32), (96, 53), (82, 62), (76, 88)],
            fill,
            outline,
        )
        _filled_polygon(image, [(52, 46), (66, 36), (80, 43), (68, 54)], outline, outline, 2)
        ellipse((78, 39), (3, 3), outline)
        base()
    elif piece_type == chess.BISHOP:
        ellipse((64, 34), (19, 23), outline)
        ellipse((64, 34), (15, 19), fill)
        cv2.line(image, (69, 20), (57, 48), outline, 5, cv2.LINE_AA)
        _filled_polygon(image, [(49, 53), (79, 53), (88, 88), (40, 88)], fill, outline)
        base()
    elif piece_type == chess.QUEEN:
        crown = [(32, 39), (39, 21), (52, 38), (64, 17), (76, 38), (89, 21), (96, 39), (88, 52), (40, 52)]
        _filled_polygon(image, crown, fill, outline)
        for x, y in ((39, 20), (64, 16), (89, 20)):
            ellipse((x, y), (6, 6), outline)
            ellipse((x, y), (3, 3), fill)
        _filled_polygon(image, [(45, 52), (83, 52), (91, 88), (37, 88)], fill, outline)
        base()
    else:
        cv2.line(image, (64, 12), (64, 36), outline, 8, cv2.LINE_AA)
        cv2.line(image, (52, 22), (76, 22), outline, 8, cv2.LINE_AA)
        cv2.line(image, (64, 12), (64, 36), fill, 3, cv2.LINE_AA)
        cv2.line(image, (52, 22), (76, 22), fill, 3, cv2.LINE_AA)
        ellipse((64, 44), (19, 17), outline)
        ellipse((64, 44), (15, 13), fill)
        _filled_polygon(image, [(46, 57), (82, 57), (91, 88), (37, 88)], fill, outline)
        base()
    return image


def _write_tone(
    path: Path,
    frequencies: tuple[float, ...],
    duration: float,
    softness: float,
) -> None:
    sample_rate = 22050
    sample_count = max(1, int(sample_rate * duration))
    timeline = np.arange(sample_count, dtype=np.float64) / sample_rate
    signal = np.zeros(sample_count, dtype=np.float64)
    for index, frequency in enumerate(frequencies):
        signal += np.sin(2.0 * math.pi * frequency * timeline + index * 0.37)
    signal /= max(1, len(frequencies))
    envelope = np.exp(-timeline * softness)
    attack = np.minimum(1.0, timeline / 0.006)
    signal *= envelope * attack
    peak = float(np.max(np.abs(signal))) or 1.0
    samples = np.asarray(signal / peak * 0.48 * 32767.0, dtype=np.int16)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(samples.tobytes())


def _ensure_piece_pack() -> None:
    directory = PIECE_PACK_DIRECTORY / "Classic Vector"
    directory.mkdir(parents=True, exist_ok=True)
    manifest = directory / "manifest.json"
    if not manifest.exists():
        _write_json(
            manifest,
            {
                "name": "Classic Vector",
                "author": "Chess Camera built-in",
                "format": "wK.png, wQ.png, wR.png, wB.png, wN.png, wP.png and black equivalents",
            },
        )
    for (white, piece_type), filename in PIECE_FILES.items():
        path = directory / filename
        if not path.exists():
            cv2.imwrite(str(path), _piece_icon(piece_type, white))


def _ensure_sound_pack(
    name: str,
    definitions: dict[str, tuple[tuple[float, ...], float, float]],
) -> None:
    directory = SOUND_PACK_DIRECTORY / name
    directory.mkdir(parents=True, exist_ok=True)
    manifest = directory / "manifest.json"
    if not manifest.exists():
        _write_json(
            manifest,
            {
                "name": name,
                "author": "Chess Camera built-in",
                "events": list(SOUND_EVENTS),
            },
        )
    for event, (frequencies, duration, softness) in definitions.items():
        path = directory / f"{event}.wav"
        if not path.exists():
            _write_tone(path, frequencies, duration, softness)


def _ensure_readmes() -> None:
    piece_readme = PIECE_PACK_DIRECTORY / "README.txt"
    if not piece_readme.exists():
        piece_readme.write_text(
            "Custom piece packs\n"
            "==================\n"
            "Create one folder per pack inside piece_packs. Include twelve transparent PNG files:\n"
            "wK.png wQ.png wR.png wB.png wN.png wP.png\n"
            "bK.png bQ.png bR.png bB.png bN.png bP.png\n"
            "A 128x128 image size is recommended. manifest.json is optional.\n",
            encoding="utf-8",
        )
    sound_readme = SOUND_PACK_DIRECTORY / "README.txt"
    if not sound_readme.exists():
        sound_readme.write_text(
            "Custom move sound packs\n"
            "=======================\n"
            "Create one folder per pack inside sound_packs. Add WAV files named:\n"
            "move.wav capture.wav check.wav castle.wav promotion.wav\n"
            "Only move.wav is required; missing event files fall back to move.wav.\n",
            encoding="utf-8",
        )


def ensure_bundled_assets() -> None:
    """Materialize the original built-in piece and sound packs on first launch."""
    try:
        PIECE_PACK_DIRECTORY.mkdir(parents=True, exist_ok=True)
        SOUND_PACK_DIRECTORY.mkdir(parents=True, exist_ok=True)
        _ensure_piece_pack()
        _ensure_sound_pack(
            "Classic Wood",
            {
                "move": ((180.0, 270.0), 0.105, 28.0),
                "capture": ((130.0, 205.0, 315.0), 0.145, 23.0),
                "check": ((420.0, 620.0), 0.190, 14.0),
                "castle": ((165.0, 245.0, 330.0), 0.180, 18.0),
                "promotion": ((390.0, 520.0, 760.0), 0.245, 11.0),
            },
        )
        _ensure_sound_pack(
            "Soft Digital",
            {
                "move": ((510.0,), 0.085, 24.0),
                "capture": ((330.0, 470.0), 0.120, 20.0),
                "check": ((660.0, 880.0), 0.170, 13.0),
                "castle": ((440.0, 550.0), 0.155, 17.0),
                "promotion": ((520.0, 660.0, 990.0), 0.230, 10.0),
            },
        )
        _ensure_readmes()
    except (OSError, cv2.error, wave.Error):
        # Read-only installs still work with the original letter renderer and no sound.
        return


def _valid_piece_pack(directory: Path) -> bool:
    return directory.is_dir() and all(
        (directory / filename).is_file() for filename in PIECE_FILES.values()
    )


def available_piece_packs() -> tuple[str, ...]:
    ensure_bundled_assets()
    try:
        names = sorted(
            directory.name
            for directory in PIECE_PACK_DIRECTORY.iterdir()
            if _valid_piece_pack(directory)
        )
    except OSError:
        names = []
    return tuple(names)


def available_sound_packs() -> tuple[str, ...]:
    ensure_bundled_assets()
    try:
        names = sorted(
            directory.name
            for directory in SOUND_PACK_DIRECTORY.iterdir()
            if directory.is_dir() and (directory / "move.wav").is_file()
        )
    except OSError:
        names = []
    return tuple(names)


def _selected_name(config_path: Path, key: str, available: tuple[str, ...]) -> str:
    configured = str(_read_config(config_path).get(key, ""))
    if configured in available:
        return configured
    return available[0] if available else ""


def selected_piece_pack(config_path: Path | None = None) -> str:
    path = config_path or STATE.config_path
    return _selected_name(path, PIECE_PACK_KEY, available_piece_packs())


def selected_sound_pack(config_path: Path | None = None) -> str:
    path = config_path or STATE.config_path
    return _selected_name(path, SOUND_PACK_KEY, available_sound_packs())


def sounds_enabled(config_path: Path | None = None) -> bool:
    path = config_path or STATE.config_path
    return bool(_read_config(path).get(SOUND_ENABLED_KEY, True))


def highlights_enabled(config_path: Path | None = None) -> bool:
    path = config_path or STATE.config_path
    return bool(_read_config(path).get(MOVE_HIGHLIGHTS_KEY, True))


def clear_image_cache() -> None:
    STATE.image_cache.clear()


def _load_piece_image(pack: str, filename: str, size: int) -> np.ndarray | None:
    path = PIECE_PACK_DIRECTORY / pack / filename
    key = (str(path.resolve()), size)
    cached = STATE.image_cache.get(key)
    if cached is not None:
        return cached
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        return None
    if image.ndim != 3:
        return None
    if image.shape[2] == 3:
        alpha = np.full(image.shape[:2] + (1,), 255, dtype=np.uint8)
        image = np.concatenate([image, alpha], axis=2)
    if image.shape[2] != 4:
        return None
    resized = cv2.resize(image, (size, size), interpolation=cv2.INTER_AREA)
    STATE.image_cache[key] = resized
    return resized


def _alpha_blend(target: np.ndarray, sprite: np.ndarray, x: int, y: int) -> None:
    height, width = sprite.shape[:2]
    if x < 0 or y < 0 or x + width > target.shape[1] or y + height > target.shape[0]:
        return
    region = target[y : y + height, x : x + width]
    alpha = sprite[:, :, 3:4].astype(np.float32) / 255.0
    foreground = sprite[:, :, :3].astype(np.float32)
    background = region.astype(np.float32)
    region[:] = np.asarray(
        foreground * alpha + background * (1.0 - alpha),
        dtype=np.uint8,
    )


def _fallback_piece(
    canvas: np.ndarray,
    piece: chess.Piece,
    center: tuple[int, int],
) -> None:
    if piece.color == chess.WHITE:
        fill, outline, text_color = (242, 242, 242), (35, 35, 35), (25, 25, 25)
    else:
        fill, outline, text_color = (38, 41, 47), (235, 235, 235), (245, 245, 245)
    cv2.circle(canvas, center, 25, fill, -1, cv2.LINE_AA)
    cv2.circle(canvas, center, 25, outline, 2, cv2.LINE_AA)
    label = piece.symbol().upper()
    (text_width, text_height), _ = cv2.getTextSize(
        label, cv2.FONT_HERSHEY_DUPLEX, 0.86, 2
    )
    cv2.putText(
        canvas,
        label,
        (center[0] - text_width // 2, center[1] + text_height // 2),
        cv2.FONT_HERSHEY_DUPLEX,
        0.86,
        text_color,
        2,
        cv2.LINE_AA,
    )


def render_virtual_board(
    app_module: ModuleType,
    board: chess.Board,
    last_move: chess.Move | None = None,
    suggested_move: chess.Move | None = None,
) -> np.ndarray:
    """Render the live/review/editor board with the selected PNG piece pack."""
    try:
        import local_detection

        local_detection.STATE.board = board.copy(stack=False)
    except (ImportError, AttributeError):
        pass

    if last_move is None and board.board_fen() == chess.Board().board_fen():
        STATE.last_move_squares = frozenset()
        if not board.move_stack:
            STATE.last_fingerprint = ()

    canvas = np.zeros(
        (app_module.VIRTUAL_VIEW_HEIGHT, app_module.VIRTUAL_VIEW_WIDTH, 3),
        dtype=np.uint8,
    )
    canvas[:] = (31, 34, 40)
    board_size = 520
    cell = board_size // 8
    left = (app_module.VIRTUAL_VIEW_WIDTH - board_size) // 2
    top = 40
    light_square = (181, 217, 240)
    dark_square = (99, 136, 181)
    last_move_color = (40, 205, 245)
    check_color = (70, 70, 225)
    app_module.put_text(canvas, "Virtual Board", (left, 28), (100, 220, 255), 0.65)
    last_squares = (
        {last_move.from_square, last_move.to_square} if last_move else set()
    )
    checked_king = board.king(board.turn) if board.is_check() else None
    pack = selected_piece_pack()

    for rank_from_top in range(8):
        chess_rank = 7 - rank_from_top
        for file_index in range(8):
            square = chess.square(file_index, chess_rank)
            x0 = left + file_index * cell
            y0 = top + rank_from_top * cell
            color = light_square if (file_index + chess_rank) % 2 == 1 else dark_square
            cv2.rectangle(canvas, (x0, y0), (x0 + cell, y0 + cell), color, -1)
            if square in last_squares:
                overlay = canvas.copy()
                cv2.rectangle(
                    overlay,
                    (x0, y0),
                    (x0 + cell, y0 + cell),
                    last_move_color,
                    -1,
                )
                canvas = cv2.addWeighted(overlay, 0.48, canvas, 0.52, 0)
            if square == checked_king:
                cv2.rectangle(
                    canvas,
                    (x0 + 2, y0 + 2),
                    (x0 + cell - 2, y0 + cell - 2),
                    check_color,
                    4,
                )
            piece = board.piece_at(square)
            if piece is None:
                continue
            center = (x0 + cell // 2, y0 + cell // 2)
            filename = PIECE_FILES.get((piece.color, piece.piece_type), "")
            sprite = _load_piece_image(pack, filename, 58) if pack and filename else None
            if sprite is None:
                _fallback_piece(canvas, piece, center)
            else:
                _alpha_blend(canvas, sprite, center[0] - 29, center[1] - 29)

    if suggested_move is not None:
        def square_center(square: chess.Square) -> tuple[int, int]:
            file_index = chess.square_file(square)
            rank_from_top = 7 - chess.square_rank(square)
            return (
                left + file_index * cell + cell // 2,
                top + rank_from_top * cell + cell // 2,
            )

        start = square_center(suggested_move.from_square)
        end = square_center(suggested_move.to_square)
        cv2.arrowedLine(canvas, start, end, (25, 45, 25), 10, cv2.LINE_AA, tipLength=0.23)
        cv2.arrowedLine(canvas, start, end, (95, 235, 125), 5, cv2.LINE_AA, tipLength=0.23)

    for file_index, file_name in enumerate("abcdefgh"):
        app_module.put_text(
            canvas,
            file_name,
            (left + file_index * cell + cell // 2 - 4, top + board_size + 18),
            scale=0.42,
        )
    for rank_from_top in range(8):
        app_module.put_text(
            canvas,
            str(8 - rank_from_top),
            (left - 16, top + rank_from_top * cell + cell // 2 + 5),
            scale=0.40,
        )

    if board.is_checkmate():
        state, state_color = "CHECKMATE", (70, 70, 255)
    elif board.is_stalemate():
        state, state_color = "STALEMATE", (120, 220, 255)
    elif board.is_check():
        state = f"{'White' if board.turn else 'Black'} to move - CHECK"
        state_color = (70, 70, 255)
    else:
        state = f"{'White' if board.turn else 'Black'} to move"
        state_color = (120, 255, 150)
    app_module.put_text(canvas, state, (left + 230, 610), state_color, 0.56)
    return canvas


def _sound_event(moves: list[chess.Move]) -> tuple[str, frozenset[chess.Square]] | None:
    if not moves:
        return None
    board = chess.Board()
    for move in moves[:-1]:
        if move not in board.legal_moves:
            return None
        board.push(move)
    last = moves[-1]
    if last not in board.legal_moves:
        return None
    changed = frozenset(move_changed_squares(board, last))
    capture = board.is_capture(last)
    castle = board.is_castling(last)
    promotion = last.promotion is not None
    board.push(last)
    if board.is_check():
        event = "check"
    elif promotion:
        event = "promotion"
    elif castle:
        event = "castle"
    elif capture:
        event = "capture"
    else:
        event = "move"
    return event, changed


def _play_wav(path: Path) -> None:
    if not path.is_file():
        return
    if sys.platform == "win32":
        try:
            import winsound

            winsound.PlaySound(
                str(path),
                winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
            )
        except (ImportError, RuntimeError):
            return
        return

    commands: list[list[str]] = []
    if sys.platform == "darwin" and shutil.which("afplay"):
        commands.append(["afplay", str(path)])
    if shutil.which("paplay"):
        commands.append(["paplay", str(path)])
    if shutil.which("aplay"):
        commands.append(["aplay", "-q", str(path)])
    if shutil.which("ffplay"):
        commands.append(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)]
        )
    if not commands:
        return
    try:
        subprocess.Popen(
            commands[0],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return


def play_named_sound(
    config_path: Path | None = None,
    event: str = "move",
    force: bool = False,
) -> None:
    path = config_path or STATE.config_path
    if not force and not sounds_enabled(path):
        return
    pack = selected_sound_pack(path)
    if not pack:
        return
    directory = SOUND_PACK_DIRECTORY / pack
    selected = directory / f"{event}.wav"
    if not selected.is_file():
        selected = directory / "move.wav"
    _play_wav(selected)


def open_asset_folder(kind: str) -> bool:
    ensure_bundled_assets()
    directory = PIECE_PACK_DIRECTORY if kind == "pieces" else SOUND_PACK_DIRECTORY
    try:
        directory = directory.resolve()
        if sys.platform == "win32":
            os.startfile(str(directory))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(directory)])
        else:
            subprocess.Popen(["xdg-open", str(directory)])
        return True
    except (OSError, AttributeError):
        return False


def install(app_module: ModuleType) -> None:
    """Install themed rendering, camera move highlights, and move sounds."""
    if getattr(app_module, "_piece_theme_system_installed", False):
        return
    ensure_bundled_assets()
    STATE.config_path = app_module.CONFIG_PATH
    original_draw_grid = app_module.draw_grid
    original_save_game = app_module.save_game

    def draw_grid(board_image: np.ndarray, highlighted: set[int]) -> np.ndarray:
        active = set(highlighted)
        if not active and highlights_enabled(STATE.config_path):
            active.update(STATE.last_move_squares)
        return original_draw_grid(board_image, active)

    def themed_board(
        board: chess.Board,
        last_move: chess.Move | None = None,
        suggested_move: chess.Move | None = None,
    ) -> np.ndarray:
        return render_virtual_board(
            app_module,
            board,
            last_move,
            suggested_move,
        )

    def save_game(*args: object, **kwargs: object) -> None:
        original_save_game(*args, **kwargs)
        moves_value = args[0] if args else kwargs.get("moves", [])
        if not isinstance(moves_value, list) or not all(
            isinstance(move, chess.Move) for move in moves_value
        ):
            return
        fingerprint = tuple(move.uci() for move in moves_value)
        previous = STATE.last_fingerprint
        if fingerprint == previous:
            return
        is_extension = (
            len(fingerprint) > len(previous)
            and fingerprint[: len(previous)] == previous
        )
        result = _sound_event(moves_value)
        STATE.last_fingerprint = fingerprint
        if result is None:
            STATE.last_move_squares = frozenset()
            return
        event, changed = result
        STATE.last_move_squares = changed
        if is_extension:
            play_named_sound(STATE.config_path, event)

    app_module.draw_grid = draw_grid
    app_module.render_virtual_board = themed_board
    app_module.save_game = save_game
    app_module._piece_theme_system_installed = True
