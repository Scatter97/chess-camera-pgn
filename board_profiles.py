from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import chess
import numpy as np


PROFILE_VERSION = 2
DEFAULT_PROFILE_NAME = "Default board"
GUIDED_TRAINING_LINE = (
    "e2e4",
    "e7e5",
    "g1f3",
    "b8c6",
    "f1b5",
    "a7a6",
    "b5a4",
    "g8f6",
)


def _score_vector(scores: dict[chess.Square, float]) -> list[float]:
    return [float(scores.get(square, 0.0)) for square in chess.SQUARES]


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-._")
    return cleaned or "board"


@dataclass
class MovePattern:
    count: int = 0
    mean_scores: list[float] = field(default_factory=lambda: [0.0] * 64)

    def add(self, scores: dict[chess.Square, float], weight: int = 1) -> None:
        vector = np.asarray(_score_vector(scores), dtype=np.float64)
        maximum = float(np.max(vector))
        if maximum > 0:
            vector /= maximum
        repetitions = max(1, int(weight))
        old_count = self.count
        new_count = old_count + repetitions
        current = np.asarray(self.mean_scores, dtype=np.float64)
        updated = ((current * old_count) + (vector * repetitions)) / new_count
        self.mean_scores = updated.tolist()
        self.count = new_count


@dataclass
class BoardProfile:
    name: str
    board_corners: list[list[float]] | None = None
    phone_corners: list[list[float]] | None = None
    white_camera_edge: str = "bottom"
    bottom_clock_is_white: bool = True
    learning_enabled: bool = True
    move_patterns: dict[str, MovePattern] = field(default_factory=dict)
    rejected_patterns: dict[str, MovePattern] = field(default_factory=dict)
    noise_mean: list[float] = field(default_factory=lambda: [0.0] * 64)
    noise_count: list[int] = field(default_factory=lambda: [0] * 64)

    @property
    def sample_count(self) -> int:
        return sum(pattern.count for pattern in self.move_patterns.values())

    def learned_patterns(self) -> dict[str, list[float]]:
        return {
            uci: pattern.mean_scores
            for uci, pattern in self.move_patterns.items()
            if pattern.count > 0
        }

    def learned_rejections(self) -> dict[str, list[float]]:
        return {
            uci: pattern.mean_scores
            for uci, pattern in self.rejected_patterns.items()
            if pattern.count > 0
        }

    def reset_training(self) -> None:
        """Clear learned move data without changing this board's calibration."""
        self.move_patterns.clear()
        self.rejected_patterns.clear()
        self.noise_mean = [0.0] * 64
        self.noise_count = [0] * 64

    def adjusted_scores(
        self, scores: dict[chess.Square, float]
    ) -> dict[chess.Square, float]:
        """Reduce recurring false changes learned on non-moving squares."""
        adjusted: dict[chess.Square, float] = {}
        for square in chess.SQUARES:
            noise = self.noise_mean[square] if self.noise_count[square] else 0.0
            adjusted[square] = max(0.0, float(scores.get(square, 0.0)) - 0.65 * noise)
        return adjusted

    def observe_move(
        self,
        move: chess.Move,
        scores: dict[chess.Square, float],
        expected_squares: Iterable[chess.Square],
        weight: int = 1,
        force: bool = False,
    ) -> None:
        if not self.learning_enabled and not force:
            return
        pattern = self.move_patterns.setdefault(move.uci(), MovePattern())
        pattern.add(scores, weight)
        expected = set(expected_squares)
        for square in chess.SQUARES:
            if square in expected:
                continue
            value = min(25.0, float(scores.get(square, 0.0)))
            count = self.noise_count[square]
            self.noise_mean[square] = (
                (self.noise_mean[square] * count) + value
            ) / (count + 1)
            self.noise_count[square] = count + 1

    def observe_rejection(
        self,
        move: chess.Move,
        scores: dict[chess.Square, float],
        weight: int = 3,
    ) -> None:
        """Learn that this visual signature should not select this move."""
        if not self.learning_enabled:
            return
        pattern = self.rejected_patterns.setdefault(move.uci(), MovePattern())
        pattern.add(scores, weight)

    def to_dict(self) -> dict[str, object]:
        return {
            "version": PROFILE_VERSION,
            "name": self.name,
            "board_corners": self.board_corners,
            "phone_corners": self.phone_corners,
            "white_camera_edge": self.white_camera_edge,
            "bottom_clock_is_white": self.bottom_clock_is_white,
            "learning_enabled": self.learning_enabled,
            "move_patterns": {
                uci: {
                    "count": pattern.count,
                    "mean_scores": pattern.mean_scores,
                }
                for uci, pattern in self.move_patterns.items()
            },
            "rejected_patterns": {
                uci: {
                    "count": pattern.count,
                    "mean_scores": pattern.mean_scores,
                }
                for uci, pattern in self.rejected_patterns.items()
            },
            "noise_mean": self.noise_mean,
            "noise_count": self.noise_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> BoardProfile:
        def load_patterns(key: str) -> dict[str, MovePattern]:
            patterns: dict[str, MovePattern] = {}
            raw_patterns = data.get(key, {})
            if not isinstance(raw_patterns, dict):
                return patterns
            for uci, raw in raw_patterns.items():
                if not isinstance(uci, str) or not isinstance(raw, dict):
                    continue
                values = raw.get("mean_scores", [0.0] * 64)
                if not isinstance(values, list) or len(values) != 64:
                    continue
                patterns[uci] = MovePattern(
                    count=max(0, int(raw.get("count", 0))),
                    mean_scores=[float(value) for value in values],
                )
            return patterns

        patterns = load_patterns("move_patterns")
        rejected_patterns = load_patterns("rejected_patterns")
        noise_mean = data.get("noise_mean", [0.0] * 64)
        noise_count = data.get("noise_count", [0] * 64)
        if not isinstance(noise_mean, list) or len(noise_mean) != 64:
            noise_mean = [0.0] * 64
        if not isinstance(noise_count, list) or len(noise_count) != 64:
            noise_count = [0] * 64
        edge = str(data.get("white_camera_edge", "bottom"))
        if edge not in {"bottom", "top", "left", "right"}:
            edge = "bottom"
        return cls(
            name=str(data.get("name", DEFAULT_PROFILE_NAME)),
            board_corners=data.get("board_corners"),  # type: ignore[arg-type]
            phone_corners=data.get("phone_corners"),  # type: ignore[arg-type]
            white_camera_edge=edge,
            bottom_clock_is_white=bool(data.get("bottom_clock_is_white", True)),
            learning_enabled=bool(data.get("learning_enabled", True)),
            move_patterns=patterns,
            rejected_patterns=rejected_patterns,
            noise_mean=[float(value) for value in noise_mean],
            noise_count=[max(0, int(value)) for value in noise_count],
        )


class BoardProfileStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.profiles: list[BoardProfile] = []

    def load(self) -> list[BoardProfile]:
        self.profiles = []
        if self.directory.exists():
            for path in sorted(self.directory.glob("*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        self.profiles.append(BoardProfile.from_dict(data))
                except (OSError, ValueError, TypeError):
                    continue
        return self.profiles

    def ensure_default(
        self,
        board_corners: list[list[float]] | None = None,
        phone_corners: list[list[float]] | None = None,
        white_camera_edge: str = "bottom",
        bottom_clock_is_white: bool = True,
    ) -> BoardProfile:
        if self.profiles:
            return self.profiles[0]
        profile = BoardProfile(
            DEFAULT_PROFILE_NAME,
            board_corners=board_corners,
            phone_corners=phone_corners,
            white_camera_edge=white_camera_edge,
            bottom_clock_is_white=bottom_clock_is_white,
        )
        self.profiles.append(profile)
        self.save(profile)
        return profile

    def get(self, name: str) -> BoardProfile | None:
        return next((profile for profile in self.profiles if profile.name == name), None)

    def create_from(self, source: BoardProfile | None = None) -> BoardProfile:
        used = {profile.name for profile in self.profiles}
        number = 1
        while f"Board {number}" in used:
            number += 1
        profile = BoardProfile(
            name=f"Board {number}",
            board_corners=source.board_corners if source else None,
            phone_corners=source.phone_corners if source else None,
            white_camera_edge=source.white_camera_edge if source else "bottom",
            bottom_clock_is_white=(
                source.bottom_clock_is_white if source else True
            ),
        )
        self.profiles.append(profile)
        self.save(profile)
        return profile

    def cycle(self, current_name: str, direction: int) -> BoardProfile:
        if not self.profiles:
            return self.ensure_default()
        index = next(
            (
                index
                for index, profile in enumerate(self.profiles)
                if profile.name == current_name
            ),
            0,
        )
        return self.profiles[(index + direction) % len(self.profiles)]

    def save(self, profile: BoardProfile) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{_safe_filename(profile.name)}.json"
        path.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")

    def rename(self, profile: BoardProfile, new_name: str) -> None:
        """Rename a profile and its file, rejecting empty or duplicate names."""
        cleaned = new_name.strip()
        if not cleaned:
            raise ValueError("Board preset name cannot be empty.")
        if any(
            other is not profile and other.name.casefold() == cleaned.casefold()
            for other in self.profiles
        ):
            raise ValueError(f'A board preset named "{cleaned}" already exists.')

        old_name = profile.name
        old_path = self.directory / f"{_safe_filename(old_name)}.json"
        new_path = self.directory / f"{_safe_filename(cleaned)}.json"
        if new_path != old_path and new_path.exists():
            raise ValueError(
                "That name would use the same file as another board preset."
            )
        profile.name = cleaned
        try:
            self.save(profile)
        except OSError:
            profile.name = old_name
            raise
        if new_path != old_path and old_path.exists():
            old_path.unlink()
