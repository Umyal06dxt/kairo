"""Local FAISS vector store (flat inner product over unit vectors == cosine)."""

import json
from pathlib import Path

import faiss
import numpy as np

from ..types import Chunk, Retrieved


def _unit_rows(m: np.ndarray) -> np.ndarray:
    m = np.ascontiguousarray(m, dtype=np.float32)
    n = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.where(n == 0, 1.0, n)


class FaissStore:
    def __init__(self, dim: int):
        self.dim = dim
        self._index = faiss.IndexFlatIP(dim)
        self._chunks: list[Chunk] = []
        self.meta: dict = {}  # e.g. {"embedder": "local:BAAI/bge-small-en-v1.5"}

    def __len__(self) -> int:
        return len(self._chunks)

    async def add(self, chunks: list[Chunk], embeddings: np.ndarray) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings differ in length")
        if not chunks:
            return
        self._index.add(_unit_rows(embeddings))
        self._chunks.extend(chunks)

    async def search(self, vec: np.ndarray, k: int) -> list[Retrieved]:
        if not self._chunks:
            return []
        q = _unit_rows(np.asarray(vec).reshape(1, -1))
        sims, ids = self._index.search(q, min(k, len(self._chunks)))
        return [Retrieved(self._chunks[i], self._index.reconstruct(int(i)), float(s))
                for s, i in zip(sims[0], ids[0]) if i >= 0]

    def save(self, path: str | Path, meta: dict | None = None) -> None:
        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(p / "index.faiss"))
        (p / "chunks.json").write_text(json.dumps(
            [{"id": c.id, "text": c.text, "meta": c.meta} for c in self._chunks]))
        (p / "meta.json").write_text(json.dumps(meta or self.meta))

    @classmethod
    def load(cls, path: str | Path) -> "FaissStore":
        p = Path(path)
        index = faiss.read_index(str(p / "index.faiss"))
        store = cls(index.d)
        store._index = index
        store._chunks = [Chunk(d["id"], d["text"], d.get("meta", {}))
                         for d in json.loads((p / "chunks.json").read_text())]
        if (p / "meta.json").exists():
            store.meta = json.loads((p / "meta.json").read_text())
        return store
