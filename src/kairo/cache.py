"""In-memory semantic cache: FAISS flat inner-product index over *document*
embeddings (L2-normalised, so inner product == cosine). Not thread-safe;
safe under a single asyncio loop because no method awaits."""

import time
from dataclasses import dataclass

import faiss
import numpy as np

from .types import Chunk, Retrieved


@dataclass
class _Entry:
    chunk: Chunk
    embedding: np.ndarray
    score: float
    expires_at: float
    last_access: float


def _unit(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32).reshape(-1)
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


class SemanticCache:
    def __init__(self, dim: int, max_size: int = 2000, ttl: float = 300.0,
                 dedup: float = 0.95, clock=time.monotonic):
        self.dim, self.max_size, self.ttl, self.dedup = dim, max_size, ttl, dedup
        self._clock = clock
        self._entries: list[_Entry] = []
        self._index = faiss.IndexFlatIP(dim)

    def __len__(self) -> int:
        return len(self._entries)

    def _rebuild(self) -> None:
        self._index = faiss.IndexFlatIP(self.dim)
        if self._entries:
            self._index.add(np.stack([e.embedding for e in self._entries]))

    def _purge_expired(self) -> None:
        now = self._clock()
        live = [e for e in self._entries if e.expires_at > now]
        if len(live) != len(self._entries):
            self._entries = live
            self._rebuild()

    def put(self, chunk: Chunk, embedding: np.ndarray, score: float = 0.0) -> bool:
        """Add a chunk; returns False if it refreshed a near-duplicate instead."""
        self._purge_expired()
        vec = _unit(embedding)
        now = self._clock()
        if self._entries:
            sims, ids = self._index.search(vec[None, :], 1)
            if sims[0][0] > self.dedup:
                e = self._entries[int(ids[0][0])]
                e.expires_at = now + self.ttl
                e.last_access = now
                e.score = max(e.score, score)
                return False
        self._entries.append(_Entry(chunk, vec, score, now + self.ttl, now))
        self._index.add(vec[None, :])
        if len(self._entries) > self.max_size:
            lru = min(range(len(self._entries)), key=lambda i: self._entries[i].last_access)
            del self._entries[lru]
            self._rebuild()
        return True

    def get(self, query: np.ndarray, k: int = 10, tau: float = 0.40) -> list[Retrieved]:
        self._purge_expired()
        if not self._entries:
            return []
        q = _unit(query)
        sims, ids = self._index.search(q[None, :], min(k, len(self._entries)))
        now = self._clock()
        out = []
        for s, i in zip(sims[0], ids[0]):
            if i < 0 or s < tau:
                continue
            e = self._entries[int(i)]
            e.last_access = now
            out.append(Retrieved(e.chunk, e.embedding, float(s)))
        return out
