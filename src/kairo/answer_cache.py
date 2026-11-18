"""Speculative answer cache: answers pre-drafted (in the background) for questions the
Slow Thinker predicts the user will ask. A match skips LLM generation entirely.

Inspired by Speculative RAG (draft with a cheap pass, verify before trusting): serving
is gated by a high question-question similarity AND a cache-evidence check done by the
Fast Talker (the draft's supporting chunks must be retrievable for the real question)."""

import time
from dataclasses import dataclass

import numpy as np


@dataclass
class Draft:
    question: str
    vec: np.ndarray
    answer: str
    chunk_ids: list[str]
    created: float
    expires_at: float
    uses: int = 0


def _unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32).reshape(-1)
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


class AnswerCache:
    def __init__(self, dim: int, ttl: float = 300.0, max_size: int = 200,
                 dedup: float = 0.97, clock=time.monotonic):
        self.dim, self.ttl, self.max_size, self.dedup, self._clock = dim, ttl, max_size, dedup, clock
        self._drafts: list[Draft] = []

    def __len__(self) -> int:
        return len(self._drafts)

    def _purge(self) -> None:
        now = self._clock()
        self._drafts = [d for d in self._drafts if d.expires_at > now]

    def put(self, question: str, vec, answer: str, chunk_ids: list[str]) -> bool:
        """Store a draft; replaces a near-identical question. Returns True if added."""
        self._purge()
        v, now = _unit(vec), self._clock()
        for i, d in enumerate(self._drafts):
            if float(d.vec @ v) > self.dedup:
                self._drafts[i] = Draft(question, v, answer, chunk_ids, now, now + self.ttl, d.uses)
                return False
        self._drafts.append(Draft(question, v, answer, chunk_ids, now, now + self.ttl))
        if len(self._drafts) > self.max_size:
            self._drafts.pop(0)  # oldest
        return True

    def get(self, qvec, theta: float) -> tuple[Draft, float] | None:
        self._purge()
        if not self._drafts:
            return None
        q = _unit(qvec)
        sims = np.stack([d.vec for d in self._drafts]) @ q
        i = int(np.argmax(sims))
        if sims[i] < theta:
            return None
        return self._drafts[i], float(sims[i])

    def snapshot(self) -> list[dict]:
        self._purge()
        now = self._clock()
        return [{"question": d.question, "answer": d.answer, "uses": d.uses,
                 "age_s": round(now - d.created, 1), "chunk_ids": d.chunk_ids}
                for d in self._drafts]
