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
    def __init__(self, topics: list[str] | None = None, answer: str = "Okay."):
        self.topics = topics or []
        self.answer = answer

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
