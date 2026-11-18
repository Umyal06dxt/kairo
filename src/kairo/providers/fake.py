"""Deterministic offline providers for tests and the offline benchmark."""

import asyncio
import re
import zlib

import numpy as np

from ..types import Chunk, Retrieved


class HashEmbedder:
    """Bag-of-words hashing: texts sharing words have higher cosine."""

    def __init__(self, dim: int = 64):
        self.dim = dim
        self.calls = 0

    async def embed(self, texts: list[str]) -> np.ndarray:
        self.calls += 1
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for r, t in enumerate(texts):
            for w in re.findall(r"[a-z0-9]+", t.lower()):
                out[r, zlib.crc32(w.encode()) % self.dim] += 1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.where(norms == 0, 1.0, norms)


class FakeLLM:
    def __init__(self, topics: list[str] | None = None, answer: str = "Okay.",
                 followups: list[tuple[str, str | None]] | None = None):
        self.topics = topics or []
        self.answer = answer
        self.followups = followups or []
        self.draft_calls: list[str] = []

    async def predict_followups(self, history, n):
        from .base import Prediction
        return [Prediction(t, q) for t, q in self.followups[:n]]

    async def draft_answer(self, question, context):
        self.draft_calls.append(question)
        return f"Draft: {question}"

    async def warmup(self):
        return None

    async def predict_topics(self, history, n):
        return self.topics[:n]

    async def stream_answer(self, question, context, history):
        for tok in self.answer.split(" "):
            yield tok + " "


class DelayedStore:
    """Wraps any store and adds fixed latency to search (simulates a remote DB)."""

    def __init__(self, inner, latency_s: float):
        self.inner, self.latency_s = inner, latency_s

    async def add(self, chunks, embeddings):
        await self.inner.add(chunks, embeddings)

    async def search(self, vec, k):
        await asyncio.sleep(self.latency_s)
        return await self.inner.search(vec, k)


class InMemoryStore:
    """Brute-force cosine store with optional injected latency."""

    def __init__(self, dim: int, latency_s: float = 0.0):
        self.latency_s = latency_s
        self.search_calls: list[int] = []  # k per call, for assertions
        self._chunks: list[Chunk] = []
        self._mat = np.zeros((0, dim), dtype=np.float32)

    async def add(self, chunks, embeddings):
        self._chunks.extend(chunks)
        self._mat = np.vstack([self._mat, np.asarray(embeddings, dtype=np.float32)])

    async def search(self, vec, k):
        self.search_calls.append(k)
        if self.latency_s:
            await asyncio.sleep(self.latency_s)
        if not self._chunks:
            return []
        sims = self._mat @ np.asarray(vec, dtype=np.float32).reshape(-1)
        top = np.argsort(-sims)[:k]
        return [Retrieved(self._chunks[i], self._mat[i], float(sims[i])) for i in top]


class ExtractiveLLM:
    """Offline stand-in for a real LLM: answers with the sentences of the retrieved context that
    best overlap the question. Lets the lab/benchmark run (and be meaningful for retrieval)
    without an API key. It never predicts follow-ups, so use the none/neighbors strategies."""

    _WORD = re.compile(r"[a-z0-9]+")
    _STOP = frozenset("a an the is are of to for and or in on do does i you my me it what how "
                      "can be there any your with at by from this that".split())

    def __init__(self, ttft_s: float = 0.0):
        self.ttft_s = ttft_s  # simulated time-to-first-token, so latency experiments are realistic

    def _words(self, text: str) -> set[str]:
        return {w for w in self._WORD.findall(text.lower()) if w not in self._STOP}

    async def predict_topics(self, history, n):
        return []

    async def stream_answer(self, question, context, history):
        if self.ttft_s:
            await asyncio.sleep(self.ttft_s)
        if not context:
            yield "I don't have that information."
            return
        q = self._words(question)
        sents = [s.strip() for c in context for s in re.split(r"(?<=[.!?])\s+", c.text) if s.strip()]
        ranked = sorted(sents, key=lambda s: -len(q & self._words(s)))
        answer = " ".join(ranked[:2])
        for w in answer.split(" "):
            yield w + " "
