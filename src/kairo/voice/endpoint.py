"""Energy-based voice-activity endpointing and sentence splitting (pure logic)."""

import re
from collections import deque
from typing import AsyncIterator

import numpy as np


class Endpointer:
    """Feed fixed-size float32 frames; returns a whole utterance once speech
    is followed by `silence_ms` of quiet (or `max_s` is reached)."""

    def __init__(self, sr: int = 16000, threshold: float = 0.015, silence_ms: int = 700,
                 min_speech_ms: int = 250, max_s: float = 30.0, preroll_frames: int = 6):
        self.sr, self.threshold = sr, threshold
        self._silence_samples = sr * silence_ms // 1000
        self._min_speech = sr * min_speech_ms // 1000
        self._max = int(sr * max_s)
        self._preroll: deque[np.ndarray] = deque(maxlen=preroll_frames)
        self.reset()

    def reset(self) -> None:
        self._frames: list[np.ndarray] = []
        self._speaking = False
        self._silent = 0
        self._speech = 0
        self._preroll.clear()

    def feed(self, frame: np.ndarray) -> np.ndarray | None:
        frame = np.asarray(frame, dtype=np.float32)
        loud = float(np.sqrt(np.mean(frame ** 2))) >= self.threshold if len(frame) else False
        if not self._speaking:
            if not loud:
                self._preroll.append(frame)
                return None
            self._speaking = True
            self._frames = list(self._preroll)
            self._preroll.clear()
        self._frames.append(frame)
        if loud:
            self._silent = 0
            self._speech += len(frame)
        else:
            self._silent += len(frame)
        total = sum(len(f) for f in self._frames)
        if self._silent >= self._silence_samples or total >= self._max:
            audio = np.concatenate(self._frames)
            enough = self._speech >= self._min_speech
            self.reset()
            return audio if enough else None
        return None


_END = re.compile(r"(?<=[.!?])\s+")


async def split_sentences(tokens: AsyncIterator[str], min_chars: int = 12) -> AsyncIterator[str]:
    """Group streamed tokens into sentences so TTS can start before the LLM finishes."""
    buf = ""
    async for tok in tokens:
        buf += tok
        parts = _END.split(buf)
        carry = ""
        for s in parts[:-1]:
            s = (carry + " " + s).strip() if carry else s.strip()
            if len(s) >= min_chars:
                yield s
                carry = ""
            else:  # too short to speak alone (e.g. "Dr."): join with the next sentence
                carry = s
        buf = (carry + " " + parts[-1]).strip() if carry else parts[-1]
    if buf.strip():
        yield buf.strip()
