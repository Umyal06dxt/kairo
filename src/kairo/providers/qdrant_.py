"""Qdrant vector store (Qdrant Cloud in production; ':memory:' works for tests)."""

import asyncio
import uuid

import numpy as np
from qdrant_client import AsyncQdrantClient, models

from ..types import Chunk, Retrieved


class QdrantStore:
    def __init__(self, dim: int, collection: str = "kairo", url: str | None = None,
                 api_key: str | None = None, client: AsyncQdrantClient | None = None):
        self.dim, self.collection = dim, collection
        self._client = client or AsyncQdrantClient(url=url, api_key=api_key)
        self._ready = False
        self._lock = asyncio.Lock()  # Fast Talker and Slow Thinker may race on first use

    async def _ensure(self) -> None:
        if self._ready:
            return
        async with self._lock:
            if self._ready:
                return
            if not await self._client.collection_exists(self.collection):
                await self._client.create_collection(
                    self.collection,
                    vectors_config=models.VectorParams(size=self.dim,
                                                       distance=models.Distance.COSINE),
                )
            self._ready = True

    async def add(self, chunks: list[Chunk], embeddings: np.ndarray) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings differ in length")
        if not chunks:
            return
        await self._ensure()
        points = [
            models.PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, c.id)),  # Qdrant ids must be uuid/uint
                vector=np.asarray(e, dtype=np.float32).tolist(),
                payload={"chunk_id": c.id, "text": c.text, "meta": c.meta},
            )
            for c, e in zip(chunks, embeddings)
        ]
        await self._client.upsert(self.collection, points=points, wait=True)

    async def search(self, vec: np.ndarray, k: int) -> list[Retrieved]:
        await self._ensure()
        res = await self._client.query_points(
            self.collection, query=np.asarray(vec, dtype=np.float32).tolist(),
            limit=k, with_payload=True, with_vectors=True)
        out = []
        for p in res.points:
            pl = p.payload or {}
            out.append(Retrieved(Chunk(pl.get("chunk_id", str(p.id)), pl.get("text", ""),
                                       pl.get("meta", {})),
                                 np.asarray(p.vector, dtype=np.float32), float(p.score)))
        return out
