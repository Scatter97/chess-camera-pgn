from __future__ import annotations

from types import ModuleType
from typing import Callable, Iterable

import chess

import local_detection
import local_detection_v2


def _closure_value(function: object, name: str) -> object | None:
    """Read one named closure value without depending on a wrapper type."""
    code = getattr(function, "__code__", None)
    closure = getattr(function, "__closure__", None)
    if code is None or not closure:
        return None
    for variable, cell in zip(code.co_freevars, closure):
        if variable != name:
            continue
        try:
            return cell.cell_contents
        except ValueError:
            return None
    return None


def _unwrap_generic_bridge(module: ModuleType) -> Callable[..., object]:
    """Return the real recovery search if the early V2 wrapper was installed."""
    current = module.search_sequences
    if getattr(module, "_local_detection_v2_installed", False):
        original = _closure_value(current, "original_search")
        if callable(original):
            module.search_sequences = original
            module._local_detection_v2_installed = False
            return original
    return current


def install(module: ModuleType) -> None:
    """Feed trustworthy V2 timeline evidence into multi-move recovery."""
    if getattr(module, "_local64_v2_bridge_installed", False):
        return
    original_search = _unwrap_generic_bridge(module)

    def search_sequences(
        board: chess.Board,
        scores: dict[chess.Square, float],
        events: Iterable[object] = (),
        **kwargs: object,
    ):
        runtime = local_detection_v2.RUNTIME
        if (
            not local_detection.STATE.enabled
            or runtime.reference_frame is None
            or runtime.latest_frame is None
            or not runtime.snapshots
        ):
            return original_search(board, scores, events, **kwargs)

        evidence = local_detection_v2.recovery_evidence()
        merged_scores = dict(evidence.square_scores or scores)
        converted: list[object] = list(events)
        for event in evidence.events:
            converted.append(
                module.ChangeEvent(
                    event.timestamp,
                    event.squares,
                    dict(event.scores),
                    event.confidence,
                )
            )
            # Backfill only squares hidden in the newest frame. Visible squares
            # always use their latest score.
            for square, value in event.scores.items():
                if square not in evidence.known_squares:
                    merged_scores[square] = max(
                        merged_scores.get(square, 0.0),
                        value,
                    )
        return original_search(board, merged_scores, converted, **kwargs)

    module.search_sequences = search_sequences
    module._local64_v2_bridge_installed = True
