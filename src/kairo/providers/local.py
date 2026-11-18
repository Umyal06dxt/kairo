"""Local ONNX embeddings (fastembed): ~5 ms per query on CPU vs ~700 ms for an API round trip."""

import asyncio

import numpy as np

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"  # 384-d


def _normalise(m: np.ndarray) -> np.ndarray:
    m = np.asarray(m, dtype=np.float32)
    n = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.where(n == 0, 1.0, n)


class LocalEmbedder:
    def __init__(self, model: str = DEFAULT_MODEL, query_prefix: str = ""):
        from fastembed import TextEmbedding  # lazy: optional dependency
        self.model_name, self.query_prefix = model, query_prefix
        self._model = TextEmbedding(model)
        self.dim = len(next(iter(self._model.embed(["dimension probe"]))))

    def _embed_sync(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return _normalise(np.stack(list(self._model.embed(texts))))

    async def embed(self, texts: list[str]) -> np.ndarray:
        return await asyncio.get_running_loop().run_in_executor(None, self._embed_sync, texts)

    async def embed_queries(self, texts: list[str]) -> np.ndarray:
        """Queries may need an instruction prefix (model-dependent); documents never do."""
        return await self.embed([self.query_prefix + t for t in texts])
