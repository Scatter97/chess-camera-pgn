from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

import cv2
import numpy as np
from rapidocr import RapidOCR


PHONE_WIDTH = 480
PHONE_HEIGHT = 960


@dataclass(frozen=True)
class ClockReading:
    text: str | None
    seconds: float | None
    confidence: float


@dataclass(frozen=True)
class BothClocks:
    top: ClockReading
    bottom: ClockReading


def parse_clock_text(text: str) -> float | None:
    """Convert Lichess m:ss, h:mm:ss, or short decimal displays to seconds."""
    cleaned = (
        text.strip()
        .replace("O", "0")
        .replace("o", "0")
        .replace("I", "1")
        .replace("l", "1")
        .replace(",", ".")
        .replace(" ", "")
    )

    hms = re.search(r"(?<!\d)(\d{1,2}):(\d{2}):(\d{2})(?:\.(\d))?", cleaned)
    if hms:
        hours, minutes, seconds = (int(hms.group(i)) for i in range(1, 4))
        if minutes < 60 and seconds < 60:
            tenths = int(hms.group(4) or 0) / 10
            return hours * 3600 + minutes * 60 + seconds + tenths

    ms = re.search(r"(?<!\d)(\d{1,3}):(\d{2})(?:\.(\d))?", cleaned)
    if ms:
        minutes, seconds = int(ms.group(1)), int(ms.group(2))
        if seconds < 60:
            tenths = int(ms.group(3) or 0) / 10
            return minutes * 60 + seconds + tenths

    short = re.fullmatch(r"(\d{1,2})\.(\d)", cleaned)
    if short:
        return int(short.group(1)) + int(short.group(2)) / 10
    return None


def format_pgn_clock(seconds: float) -> str:
    """Format seconds for a standard PGN [%clk H:MM:SS] comment."""
    safe = max(0.0, float(seconds))
    hours = int(safe // 3600)
    minutes = int((safe % 3600) // 60)
    remaining = safe % 60
    if abs(remaining - round(remaining)) < 0.04:
        second_text = f"{int(round(remaining)):02d}"
    else:
        second_text = f"{remaining:04.1f}"
    return f"{hours}:{minutes:02d}:{second_text}"


def warp_phone(frame: np.ndarray, corners: Iterable[Iterable[float]]) -> np.ndarray:
    source = np.asarray(list(corners), dtype=np.float32)
    destination = np.asarray(
        [
            [0, 0],
            [PHONE_WIDTH - 1, 0],
            [PHONE_WIDTH - 1, PHONE_HEIGHT - 1],
            [0, PHONE_HEIGHT - 1],
        ],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(source, destination)
    return cv2.warpPerspective(frame, matrix, (PHONE_WIDTH, PHONE_HEIGHT))


def split_and_rotate(phone: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Extract Lichess's two player areas and rotate sideways digits upright.

    The center control strip is intentionally excluded.
    """
    top = phone[: int(PHONE_HEIGHT * 0.45)]
    bottom = phone[int(PHONE_HEIGHT * 0.55) :]
    return (
        cv2.rotate(top, cv2.ROTATE_90_COUNTERCLOCKWISE),
        cv2.rotate(bottom, cv2.ROTATE_90_COUNTERCLOCKWISE),
    )


class LichessClockReader:
    def __init__(self) -> None:
        self._engine = RapidOCR()

    @staticmethod
    def _extract(result: object) -> list[tuple[str, float]]:
        texts = getattr(result, "txts", None)
        scores = getattr(result, "scores", None)
        if texts is not None:
            values = list(scores) if scores is not None else [0.0] * len(texts)
            return [(str(text), float(score)) for text, score in zip(texts, values)]

        # Compatibility with RapidOCR 1.x/2.x tuple-style output.
        if isinstance(result, tuple) and result and isinstance(result[0], list):
            extracted = []
            for row in result[0]:
                if isinstance(row, (list, tuple)) and len(row) >= 3:
                    extracted.append((str(row[1]), float(row[2])))
            return extracted
        return []

    def _read_one(self, image: np.ndarray) -> ClockReading:
        result = self._engine(image)
        candidates: list[ClockReading] = []
        for text, confidence in self._extract(result):
            seconds = parse_clock_text(text)
            if seconds is not None:
                candidates.append(ClockReading(text, seconds, confidence))
        if not candidates:
            return ClockReading(None, None, 0.0)
        return max(candidates, key=lambda item: item.confidence)

    def read(self, frame: np.ndarray, corners: Iterable[Iterable[float]]) -> BothClocks:
        phone = warp_phone(frame, corners)
        top, bottom = split_and_rotate(phone)
        return BothClocks(self._read_one(top), self._read_one(bottom))

