from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import chess
import chess.pgn
import cv2

import app


GAMES_DIR = Path("games")
_CLEAN_HIGHGUI_INSTALLED = False


@dataclass
class HistoryGame:
    path: Path
    white: str
    black: str
    result: str
    event: str
    date: str
    time_control: str
    termination: str
    plies: int
    white_accuracy: float | None = None
    black_accuracy: float | None = None

    @property
    def moves(self) -> int:
        return (self.plies + 1) // 2


def install_clean_highgui_windows() -> None:
    """Hide Ubuntu's Qt toolbar/status bar while keeping windows resizable."""
    global _CLEAN_HIGHGUI_INSTALLED

    if _CLEAN_HIGHGUI_INSTALLED or not sys.platform.startswith("linux"):
        return

    gui_normal = int(getattr(cv2, "WINDOW_GUI_NORMAL", 0))
    if gui_normal == 0:
        return

    original_named_window: Callable[..., None] = cv2.namedWindow

    def named_window(name: str, flags: int = cv2.WINDOW_AUTOSIZE) -> None:
        original_named_window(name, int(flags) | gui_normal)

    cv2.namedWindow = named_window  # type: ignore[assignment]
    _CLEAN_HIGHGUI_INSTALLED = True


def _put(
    image,
    text,
    xy,
    color=(240, 240, 240),
    scale=0.55,
    thickness=1,
) -> None:
    cv2.putText(
        image,
        text,
        xy,
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        (8, 8, 8),
        thickness + 3,
        cv2.LINE_AA,
    )
    cv2.putText(
        image,
        text,
        xy,
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        color,
        thickness,
        cv2.LINE_AA,
    )


def _read_analysis_for(pgn_path: Path) -> tuple[float | None, float | None]:
    candidates = [
        pgn_path.with_suffix(".analysis.json"),
        GAMES_DIR / f"{pgn_path.stem}_analysis.json",
    ]
    if pgn_path.name == "latest_game.pgn":
        candidates.insert(0, GAMES_DIR / "latest_analysis.json")

    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return float(data.get("white_accuracy")), float(data.get("black_accuracy"))
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return None, None


def load_history() -> list[HistoryGame]:
    GAMES_DIR.mkdir(exist_ok=True)
    games: list[HistoryGame] = []
    seen: set[Path] = set()
    paths = sorted(
        GAMES_DIR.glob("*.pgn"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    for path in paths:
        try:
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)

            with path.open(encoding="utf-8", errors="replace") as handle:
                game = chess.pgn.read_game(handle)
            if game is None:
                continue

            headers = game.headers
            plies = sum(1 for _ in game.mainline_moves())
            white_accuracy, black_accuracy = _read_analysis_for(path)
            games.append(
                HistoryGame(
                    path=path,
                    white=headers.get("White", "White"),
                    black=headers.get("Black", "Black"),
                    result=headers.get("Result", "*"),
                    event=headers.get("Event", "Recorded OTB Game"),
                    date=headers.get(
                        "Date",
                        path.stem.replace("game_", "").split("_")[0],
                    ),
                    time_control=headers.get("TimeControl", "Not recorded"),
                    termination=headers.get("Termination", "Not recorded"),
                    plies=plies,
                    white_accuracy=white_accuracy,
                    black_accuracy=black_accuracy,
                )
            )
        except (OSError, ValueError):
            continue

    return games


def install_profile_creation_prompt() -> None:
    """Ask for a name whenever a new board profile is created."""
    original_create = app.BoardProfileStore.create_from

    def create_named(store, source):
        created = original_create(store, source)
        name = app.prompt_for_text("Create new board", "Board name", created.name)
        if name:
            try:
                store.rename(created, name)
            except (ValueError, OSError):
                pass
        return created

    app.BoardProfileStore.create_from = create_named
