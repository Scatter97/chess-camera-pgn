from __future__ import annotations

from types import ModuleType
from typing import Iterable

import chess

import local_detection
import local_detection_v2


def install(module: ModuleType) -> None:
    """Feed trustworthy V2 timeline evidence into multi-move recovery."""
    if getattr(module, "_local64_v2_bridge_installed", False):
        return
    original_search = module.search_sequences

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
