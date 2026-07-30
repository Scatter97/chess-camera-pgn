from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClockSettings:
    white_initial_seconds: float = 300.0
    black_initial_seconds: float = 300.0
    white_increment_seconds: float = 0.0
    black_increment_seconds: float = 0.0


@dataclass(frozen=True)
class _ClockSnapshot:
    white_seconds: float
    black_seconds: float
    active_white: bool


class BuiltInChessClock:
    """Two-sided Fischer-increment chess clock driven by accepted moves."""

    def __init__(self, settings: ClockSettings | None = None) -> None:
        self.settings = settings or ClockSettings()
        self.white_seconds = self.settings.white_initial_seconds
        self.black_seconds = self.settings.black_initial_seconds
        self.active_white: bool | None = None
        self.started_at: float | None = None
        self.history: list[_ClockSnapshot] = []

    def reset(self, settings: ClockSettings | None = None) -> None:
        if settings is not None:
            self.settings = settings
        self.white_seconds = max(0.0, self.settings.white_initial_seconds)
        self.black_seconds = max(0.0, self.settings.black_initial_seconds)
        self.active_white = None
        self.started_at = None
        self.history.clear()

    def start(self, now: float, white_to_move: bool = True) -> None:
        self.active_white = white_to_move
        self.started_at = now

    def remaining(self, player_is_white: bool, now: float) -> float:
        base = self.white_seconds if player_is_white else self.black_seconds
        if (
            self.active_white == player_is_white
            and self.started_at is not None
        ):
            base -= max(0.0, now - self.started_at)
        return max(0.0, base)

    def complete_move(self, player_is_white: bool, event_time: float) -> float:
        if self.active_white is None or self.started_at is None:
            self.start(event_time, player_is_white)
        if self.active_white != player_is_white:
            raise ValueError("The completed move does not match the active clock.")

        current = self.remaining(player_is_white, event_time)
        if player_is_white:
            self.white_seconds = current
        else:
            self.black_seconds = current

        self.history.append(
            _ClockSnapshot(
                self.white_seconds,
                self.black_seconds,
                player_is_white,
            )
        )

        increment = (
            self.settings.white_increment_seconds
            if player_is_white
            else self.settings.black_increment_seconds
        )
        recorded = current + max(0.0, increment)
        if player_is_white:
            self.white_seconds = recorded
        else:
            self.black_seconds = recorded

        self.active_white = not player_is_white
        self.started_at = event_time
        return recorded

    def undo(self, now: float) -> bool:
        if not self.history:
            return False
        snapshot = self.history.pop()
        self.white_seconds = snapshot.white_seconds
        self.black_seconds = snapshot.black_seconds
        self.active_white = snapshot.active_white
        self.started_at = now
        return True

    def pause(self, now: float) -> None:
        if self.active_white is not None:
            current = self.remaining(self.active_white, now)
            if self.active_white:
                self.white_seconds = current
            else:
                self.black_seconds = current
        self.active_white = None
        self.started_at = None
