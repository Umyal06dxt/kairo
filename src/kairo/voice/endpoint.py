"""Energy-based voice-activity endpointing and sentence splitting (pure logic)."""

import re
from collections import deque
from typing import AsyncIterator

import numpy as np


class Endpointer:
    """Feed fixed-size float32 frames; returns a whole utterance once speech
    is followed by `silence_ms` of quiet (or `max_s` is reached).

    Level is measured only in the speech band (`band` Hz) so low-frequency
    rumble/hum is ignored, and the trigger threshold adapts to the background
    noise: max(`threshold`, `floor_mult` x tracked noise floor)."""

    def __init__(self, sr: int = 16000, threshold: float = 0.01, silence_ms: int = 700,
                 min_speech_ms: int = 250, max_s: float = 30.0, preroll_frames: int = 6,
                 band: tuple[float, float] = (200.0, 3800.0), floor_mult: float = 3.0,
                 calib_frames: int = 15):
        self.sr, self.threshold = sr, threshold
        self.calib_frames = calib_frames  # frames used at startup to learn the noise floor
        self._calib: list[float] = []
        self.band, self.floor_mult = band, floor_mult
        self._silence_samples = sr * silence_ms // 1000
        self._min_speech = sr * min_speech_ms // 1000
        self._max = int(sr * max_s)
        self._preroll: deque[np.ndarray] = deque(maxlen=preroll_frames)
        self._floor: float | None = 0.0 if calib_frames == 0 else None
        self.reset()

    def reset(self) -> None:
        self._frames: list[np.ndarray] = []
        self._speaking = False
        self._silent = 0
        self._speech = 0
        self._preroll.clear()

    def band_rms(self, frame: np.ndarray) -> float:
        """RMS of the frame's energy inside the speech band."""
        n = len(frame)
        if n == 0:
            return 0.0
        w = np.hanning(n)  # window: stops strong low-frequency rumble leaking into the band
        power = np.abs(np.fft.rfft(frame * w)) ** 2
        freqs = np.fft.rfftfreq(n, 1.0 / self.sr)
        sel = (freqs >= self.band[0]) & (freqs <= self.band[1])
        return float(np.sqrt(2.0 * power[sel].sum() / np.mean(w ** 2)) / n)  # Parseval

    @property
    def effective_threshold(self) -> float:
        floor = self._floor if self._floor is not None else 0.0
        return max(self.threshold, self.floor_mult * floor)

    def feed(self, frame: np.ndarray) -> np.ndarray | None:
        frame = np.asarray(frame, dtype=np.float32)
        level = self.band_rms(frame)
        if self._floor is None:  # calibration: assume background only, learn the floor
            self._calib.append(level)
            self._preroll.append(frame)
            if len(self._calib) >= self.calib_frames:
                self._floor = float(np.percentile(self._calib, 25))
            return None
        loud = level >= self.effective_threshold
        if not self._speaking:
            if not loud:
                # track noise floor: falls fast, rises slowly
                a = 0.3 if level < self._floor else 0.02
                self._floor += a * (level - self._floor)
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
